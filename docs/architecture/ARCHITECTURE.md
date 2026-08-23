# Project LADDER — Tier-Ranked Labor Marketplace
## Production Architecture & Implementation Blueprint · v1.0

Audience: senior engineering team kickoff. Scope: full system design, MVP cut, scale roadmap, and the launch experiment. Every recommendation is opinionated and justified; where this document contradicts the original brief, the contradiction is explicit and numbered.

---

## A. Executive Summary

**Verdict on the concept.** A categorical, evidence-based tier system is a genuinely strong organizing primitive for a labor marketplace. It compresses noisy signals into something users instantly understand and act on, and it creates a progression loop that neither LinkedIn nor Upwork has. But **three core mechanics in the original concept are inverted and would break the marketplace if built as written:**

1. **"Applicants can apply only to jobs of the same rank or higher" is backwards.** As specified, an F-ranked applicant can apply to *everything* (spam flood) while an SSS applicant can only see and apply to the top 0.1% of jobs (starvation → churn). Mid-tier employers get buried under applications from every rank above them. **Correction:** eligibility is a *capability floor* — you may apply to work at or below your capability, plus a limited one-tier stretch window. What the applicant *wants* becomes a soft *preference band* that orders the feed but never hard-blocks. See §I.
2. **"Jobs are shown only to applicants of the same rank or lower"** compounds error #1: SSS users would see an empty feed. Visibility must be *eligibility ∩ preference ∪ stretch*, which means top-ranked people see plenty of work below them and low-ranked people see a narrow, honest set. See §K.
3. **Pure percentile tiers are undefined at cold start** (top 0.1% of 200 users is nobody), distort with population mix (a flood of casual gig workers inflates everyone else), and force a fixed share of the population into low tiers even when everyone improves — perceived as unfair and legally awkward. **Correction:** absolute evidence gates are the primary determinant; percentiles only *cap* the top tiers (S/SS/SSS) once minimum population exists; a distinct **Unranked** state covers cold start; calibration runs per domain cohort on a schedule with hysteresis. See §Q.

**Stack verdict.** Keep ASP.NET Core + React. **Replace MongoDB with PostgreSQL.** The core domain is transactional and invariant-heavy (eligibility checks, application uniqueness, contract state machines, immutable rank events, audit). Calibration analytics is literally SQL window functions over distributions. And the product's entire premise is *structured* job data — which removes MongoDB's main advantage (schema flexibility). Defer Redis, OpenSearch, and a message broker until measured need; start with a transactional outbox on Postgres. Full argument in §S.

**MVP.** 14 weeks, single vertical (software development), deterministic rule-based ranking v1 (no ML), two-stage matching, tier-only public surface enforced by API contract tests, and the launch experiment: rank-gated matched feed vs. traditional relevance feed, measured on interview rate per application and bad-application rate. See §AF.

**Moat.** Not the UI, not the algorithm. The moat is the **verified outcome dataset** — who completed what work, at what level, for whom, with what result. Every mechanic in this document exists to make that dataset grow and stay trustworthy.

---

## B. Product Model

### B.1 Entities

```
User ──1:1── ApplicantProfile ──1:n── Evidence ─┐
   │              │                              │
   │              └── ApplicantRanking ───────────┤ (evidence feeds ranking)
   │                                             │
   └──n:m── Company (as member) ──1:n── Job ── JobRanking
                  │                    │              │
             CompanyRanking        Applications ←──── eligibility gate
                  │                    │
                  └── Contracts ── Reviews ── Reputation signals
                                        │
                       RankEvents (immutable audit trail for all ranks)
```

Three ranked entities, four orthogonal non-rank axes:

| Axis | Question it answers | Applies to |
|---|---|---|
| **Rank** | How capable / how difficult / how good? | Applicants, Jobs, Companies |
| **Confidence** | How sure are we about that rank? | All three |
| **Reputation** | How did historical transactions go? | Applicants, Companies, Jobs (feedback) |
| **Trust** | Is the account legitimate? | Users, Companies |
| **Fraud risk** (internal) | Should this account be restricted? | Users, Companies |

These five are never collapsed into one number. An S-rank applicant with Provisional confidence and Unverified trust behaves very differently in the marketplace than an S-rank applicant with Verified confidence and Verified trust — same rank, different privileges, different visibility weight.

### B.2 Concept corrections (read before building anything)

| # | Brief says | Why it fails | This document says |
|---|---|---|---|
| C1 | Apply only to jobs of same-or-higher rank | Top-user starvation; bottom-user spam; employer flood | Capability **floor** + 1-tier stretch window + soft preference band (§I) |
| C2 | Show jobs only to same-or-lower ranks | Empty feeds at top; breaks discovery | Visibility = eligible ∩ preference ∪ stretch (§K) |
| C3 | Percentile-defined tiers from day one | Undefined at small N; mix distortion; forced-bottom-decile unfairness | Absolute evidence gates primary; percentile caps top tiers only; Unranked state (§D, §Q) |
| C4 | One implied universal scale | "Top 0.1% of applicants" ≠ "top 0.1% of jobs" ≠ companies | Three independently calibrated systems sharing tier vocabulary (§D) |
| C5 | Rank as the product | A B frontend dev and B backend dev are both "B" yet terrible matches for each other's work | Rank = eligibility axis + feed prior; matching is multi-signal (§J) |
| C6 | Numerical scores "MAY" exist internally | "May" becomes "leak" under deadline pressure | Scores MUST NOT appear on any public surface; enforced by serializer contract tests (§U, §AC) |
| C7 | Rank changes driven by score drift alone | Rank anxiety; gaming via observation; legal exposure on automated adverse decisions | Rank changes only via evidence events or scheduled calibration, with hysteresis, reason codes, and appeal path (§R, §AA) |

### B.3 What the product is not

- Not a job board with badges. Eligibility gating changes *who sees what*, which changes market behavior.
- Not a game. Progression is evidence-gated; there is no XP, no streaks, no cosmetic loot.
- Not pay-to-win. Rank cannot be bought, boosted, or advertised into. Verification is priced at cost. Placement is never sold. (§AH)
- Not a credit score for humans. Tiers describe fit-for-work-level, are domain-scoped, explainable, and appealable.

---

## C. Rank System

### C.1 Pipeline (one shape, three instantiations)

```
Evidence & structured data
        ↓  (feature extraction — deterministic rules v1)
Feature vector (versioned snapshot)
        ↓  (scoring model vX — deterministic rubric v1)
InternalScore (0–1000)          [INTERNAL ONLY]
        ↓  (percentile vs. domain cohort)      [INTERNAL ONLY]
Percentile                      [INTERNAL ONLY]
        ↓  (tier map vX.Y + evidence gates + hysteresis)
Public Rank Tier (F…SSS / Unranked)  +  Confidence Tier
        ↓
Ranking row (current) + immutable RankEvent (if changed) + reason codes
```

Key properties:

- **Reads never compute rank.** The read path reads the current `rankings` row. Ranks change only through event-driven recalculation or scheduled batch. This gives consistency, auditability, cost control, and prevents timing-based inference of exact percentile.
- **Tier is the only public projection.** Internal score and percentile exist solely inside the ranking module and admin APIs. Public DTO types have no numeric rank fields — enforced by contract tests that reflect over the OpenAPI spec (§AC).
- **Every rank references `model_version`.** Historical reconstruction is guaranteed because feature vectors are snapshotted (hash + reference) at calculation time (§R).
- **Every change emits a RankEvent** with trigger, reason codes, and actor (`system` or admin id). Silent rank changes are impossible by construction (append-only table, no UPDATE grant).

### C.2 Rank is a group, not a number

Users join a class. The mental model we ship:

> "You're in A. Here's what A means, here's your evidence, here's exactly what separates you from S."

The internal 0–1000 score is a bucketing convenience. Two users with scores 803 and 847 are the same product object if both map to A. Product language, API payloads, DB caches on other modules, analytics dashboards for non-admin staff — all tier-only.

### C.3 Contextual ranks (multidimensional)

The schema carries `dimension` from day one (default `"core"`), but MVP ships exactly one dimension per entity within the launch vertical. Domain/capability sub-ranks ("Software Engineering: S, DevOps: A") are a Phase-3 product decision gated on data: we need ≥5k assessed applicants across ≥3 distinguishable skill families before splitting cohorts keeps percentiles statistically meaningful. Do not build multi-dimension UI now. The cost of adding dimensions later is zero because storage, versioning, events, and APIs are dimension-aware from day one.

### C.4 The Unranked state

Cold-started subjects are **Unranked**, not F. F means *evaluated and bottom*; Unranked means *insufficient data*. Unranked applicants get a Provisional estimate (capped at C) used internally for eligibility math but displayed as "Provisional estimate: ≤ C". This distinction prevents punishing new users before evaluation and prevents the marketplace from treating unevaluated accounts as bottom-feeders.

---
## D. Rank Tier Definitions

Three independently calibrated systems, one shared vocabulary. **Effective tier = min(evidence-gate tier, percentile-cap tier)** for applicants; jobs and companies use their own anchors below.

### D.1 Master table

| Tier | Applicant — evidence floor (ALL required) | Applicant — percentile cap (domain cohort) | Job — rubric anchor | Company — behavioral anchor |
|---|---|---|---|---|
| **Unranked** | No assessment, <1 evidence unit | — | n/a (jobs always get rubric rank) | New company |
| **F** | Assessed; integrity flag or bottom of cohort | bottom 3% | Routine single-task work; no specialization; IC-only; feature scope | <50 quality score, or n<3 contracts |
| **E** | Identity verified + assessment completed | ≤ 15th pct | Simple multi-step work; narrow skills | ≥50, n≥3 |
| **D** | + 1 verified external evidence (employment/portfolio) | ≤ 35th pct | Competent-junior work; some integration | ≥58, n≥5 |
| **C** | + assessment at "competent" band | ≤ 60th pct | Solid independent contributor scope; own a subsystem | ≥65, n≥10 |
| **B** | + 2 completed marketplace contracts (or 1 verified role ≥6 mo) | ≤ 80th pct | Mid-level: owns features end-to-end, mentors juniors occasionally | ≥72, n≥20 |
| **A** | + 5 contracts avg ≥4.3 **or** advanced assessment + verified production ownership | ≤ 95th pct | Senior: system-level design, technical ownership, team lead | ≥80, n≥40 |
| **S** | + 15 contracts avg ≥4.5, leadership/ownership evidence, confidence ≥ Moderate | ≤ 99th pct | Leads critical initiatives; department scope or deep architectural authority | ≥87, n≥75 |
| **SS** | + 40 contracts avg ≥4.7, repeat-client ratio ≥30%, confidence ≥ High, zero unresolved disputes | ≤ 99.9th pct | Company-wide technical scope or executive authority; rare skill combinations | ≥93, n≥150 + 12-mo history |
| **SSS** | + 75 contracts or 3-yr verified history, avg ≥4.8, confidence = Verified, **manual trust audit** | top 0.1% | Transformational scope; comp ≥99th domain percentile; rubric ≥97/100 AND top-0.1% composite among active jobs | ≥97, n≥300 + manual audit |

Notes:

- Floors and caps both bind. A user with S-level evidence in a cohort where they're only 90th percentile sits at A. A 99th-percentile user with evidence for B sits at B. This is the inflation firewall.
- `n` = completed contracts. Volume gates prevent small-sample companies from ranking high; they do **not** reference headcount or revenue anywhere.
- All thresholds are config, versioned per model release, and recalibrated quarterly (§Q).

### D.2 What each tier means publicly

Copy-deck language shipped to users (applicants):

- **F–E:** "Getting started — build your evidence."
- **D–C:** "Established — reliably independent work."
- **B:** "Proven professional — the marketplace backbone."
- **A:** "Advanced — senior-level complexity and ownership."
- **S:** "Exceptional — leads critical work." (~top 5% of assessed cohort)
- **SS:** "Elite." · **SSS:** "One-in-a-thousand, manually audited."

Jobs and companies use parallel language ("Complexity: S", "Employer quality: SS"). Same words, different calibration — users read tiers as *level*, which is exactly the abstraction we want.

---

## E. Applicant Ranking

### E.1 Evidence hierarchy and weights (internal)

| Evidence type | Weight | Verified by |
|---|---|---|
| Self-reported skill/role claim | 1 | nobody (baseline) |
| Portfolio artifact | 3 | file + metadata review |
| Verified employment / reference | 6 | employer contact, HR API, LinkedIn-equivalent check |
| Assessment result | 7 | proctored vertical-specific assessment |
| Marketplace contract executed | 8 | contract state machine |
| Completed contract with counterparty review | 10 | review pipeline |
| Repeated success (repeat client, rehire) | 12 | contract graph |

Evidence points decay 24 months half-life so ranks reflect *current* capability. Claims alone can never exceed Unranked→E territory: self-reported weight sums are capped at the E gate regardless of volume.

### E.2 Score composition v1 (`model_version = rank-applicant-v1`)

```
InternalScore(0–1000) =
    350 × f(skill_depth: assessment bands × skill rarity)
  + 250 × g(experience_complexity: parsed role level, scope, domain match)
  + 200 × h(marketplace_outcomes: completion rate, ratings, repeat rate)
  + 100 × i(verifications: identity, employment, licenses)
  + 100 × j(leadership/ownership signals from structured history & reviews)
```

Deterministic, auditable, unit-tested. Every input maps to a stored evidence row; every coefficient is config under version control. Percentile is computed within the applicant's **domain cohort** (launch: one cohort) over accounts active in trailing 180 days with ≥1 evidence unit.

### E.3 Caps and guards

- Provisional-confidence applicants: effective tier capped at **C**.
- Any unresolved fraud state ≥ Review: tier display frozen, applications restricted (§O). Rank is never *reduced* by fraud state — capability stays, participation stops (brief §22 honored).
- Rank decreases require either scheduled recalibration crossing a hysteresis band (−15 internal points below boundary) or an explicit negative event (lost dispute, verified misrepresentation → immediate event-driven recalc).
- Staleness: no new evidence in 12 months → confidence drops one level, badge shows "stale"; tier itself does not silently decay.

### E.4 Worked example (this exact trace ships as the "Why am I B?" screen)

```
Inputs: ID verified (+i), 1 assessment @ advanced backend band,
        2 completed contracts (avg 4.5), portfolio: 3 artifacts
Score:  612 → percentile 71st → percentile-band B; gate-tier B
Hysteresis check: previous C, boundary C→B crossed upward with margin ✓
RankEvent: C → B, trigger=EVIDENCE_ADDED(contract #8812),
           reasons=[CONTRACTS_COMPLETED_2, ASSESSMENT_ADVANCED]
Path to A (shown on progression screen):
  ✓ 5 completed contracts (have 2)
  □ avg rating ≥ 4.3 across 5+
  □ verified production ownership OR advanced assessment in 2nd domain
```

---

## F. Job Ranking

Jobs are **rubric-ranked, not percentile-ranked**, because job difficulty is a property of the work, not of the posting population. Percentile enters only as a tail cap so SSS stays rare even if everyone posts grandiose jobs.

### F.1 Rubric v1 (`rank-job-v1`, 0–100)

| Dimension | Points | Anchors |
|---|---|---|
| Authority | 40 | IC 5 · Technical owner 15 · Team lead 25 · Dept lead 33 · Executive 40 |
| Scope | 35 | Single feature 5 · Product 15 · Department 25 · Company-wide 35 |
| Complexity | 25 | Skill breadth×rarity, integration count, ambiguity, outcome risk (scored checklist) |
| Compensation context | ±5 modifier | Ratio vs. local-market benchmark for the responsibility profile |

Tier map (illustrative, versioned): F<20 · E 20–34 · D 35–49 · C 50–62 · B 63–74 · A 75–84 · S 85–91 · SS 92–96 · SSS ≥97 **and** top-0.1% composite among active jobs with ≥50 qualified views.

### F.2 Feedback adjustments

A job's rank starts as pure rubric ("Estimated" badge until 50 qualified views). Post-interaction signals adjust within ±1 tier: hire-outcome quality, "job was as described" post-hire ratings, offer-acceptance rate. Signals cannot push beyond ±1 — that requires re-running the rubric (e.g., employer edits scope) which notifies applicants and re-gates eligibility (§AL).

### F.3 Compensation/responsibility mismatch (brief §11)

The comp-context modifier plus a dedicated detector classifies postings where compensation sits >35% below the local benchmark for their responsibility profile. Effect: job gets a "compensation below typical for this scope" label, its **quality prior** drops (feed ordering penalty, §J), repeated mismatches lower **company rank** (fairness signal, §G). It does not hard-block: low-cost markets, nonprofits, and equity-heavy deals exist. Context comes from benchmark tables per role-family × geography × seniority, seeded from public salary data and refined by platform outcomes.

---

## G. Company Ranking

**Behavioral thresholds only — no curve.** Company rank measures "is this a good place to work through," and there is no reason the whole platform can't eventually be B+. Size, brand, and headcount appear nowhere in the formula.

### G.1 Quality score v1 (`rank-company-v1`, 0–100)

| Signal | Weight | Source |
|---|---|---|
| Payment reliability (on-time %) | 25 | payment rails / escrow events |
| Worker satisfaction (review avg, value-weighted) | 20 | reviews |
| Contract completion rate | 15 | contracts |
| Dispute rate (inverse, lost disputes weighted more) | 12 | disputes |
| Job clarity (structure completeness, low cancellation-after-start) | 10 | jobs meta |
| Responsiveness (time-to-first-response on applications) | 8 | messaging/applications |
| Compensation fairness (mismatch flags inverse) | 10 | §F.3 detector |

Threshold matrix in §D.1. Provisional cap: new companies max **B** until 20 completed contracts. Small shops reach S/SS purely on behavior; a large company with terrible metrics cannot exceed D regardless of volume.

---

## H. Confidence / Reputation / Trust Model

Five axes, kept separate everywhere — storage, APIs, UI, and admin tooling.

### H.1 Confidence (in the rank)

How much evidence backs the tier. Tiers: **Provisional → Low → Moderate → High → Verified**, mapped to cumulative evidence points (§E.1 weights): <10 / 10+ / 30+ incl. 1 verified / 70+ incl. assessment + 2 marketplace contracts / 150+ incl. gov-ID + multiple independent sources + 6-mo history.

Displayed adjacent to rank always: `Rank A · Confidence: Moderate`. Two A-rank profiles are different products to an employer depending on this badge — and that's the honest representation.

### H.2 Reputation (historical performance)

Rolling 12-month transactional stats: completion rate, on-time rate, dispute rate, satisfaction average, response time. Shown as stats/badges ("98% completion · 41 contracts"), never merged into rank. A-rank freelancer with mediocre reputation and A-rank with stellar reputation differ in ordering weight (§J), not in tier.

### H.3 Trust (account legitimacy)

Levels: **Unverified → Email → Identity (gov ID/KYC) → Professional (employment/license verified) → Highly Verified (video + financial instrument)**. Trust gates *privileges*: sourcing search visibility requires Identity+; stretch applications require Moderate confidence + Identity; company posting requires Identity + payment instrument.

### H.4 Fraud risk (internal only)

State machine: `Clear → Watch → Review → Restricted → Suspended`. Never displayed, never blended into rank. Effects: Watch = enhanced logging; Review = reviews held, payouts held; Restricted = applications capped, sourcing hidden; Suspended = full exclusion from percentile populations and feeds. Adverse transitions beyond Watch require human confirmation (§AA) — automated adverse action on livelihoods without review is both a fairness and a legal failure (§AK).

---
## I. Eligibility Rules

**Hard rules, server-enforced at application time, deterministic, logged with reason codes.** Client-side gating is UX only; the API re-checks everything.

### I.1 The inversion, restated as law

> **Eligibility is a floor on capability, not a ceiling.**
> An applicant may apply to any job whose difficulty rank is **at or below their capability rank**, plus a bounded one-tier stretch window above.
> What they *prefer* is a soft band that orders the feed and never gates.

Why: the brief's original rule (`applicant ≤ job`) makes the best users starve and the newest users spam upward into every SSS job — maximizing exactly the low-quality-application flood the tier system exists to prevent. The floor rule does the opposite: employers are protected from unqualified volume, top users keep full liquidity, and stretch applications remain possible because that's how people grow.

### I.2 Hard eligibility rules v1

| # | Rule | Reason code on failure |
|---|---|---|
| 1 | Account in good standing (fraud state ≤ Watch) | `ACCOUNT_RESTRICTED` |
| 2 | Job published and open | `JOB_CLOSED` |
| 3 | Capability ≥ difficulty − 1 (one-tier stretch max) | `CAPABILITY_BELOW_FLOOR` |
| 4 | Stretch requires confidence ≥ Moderate + Identity trust | `STRETCH_EVIDENCE_INSUFFICIENT` |
| 5 | Max 2 open stretch applications at once | `STRETCH_QUOTA` |
| 6 | All must-have credentials/certifications held | `MISSING_REQUIRED_CREDENTIAL` |
| 7 | Applicant availability ≥ job commitment | `COMMITMENT_INCOMPATIBLE` |
| 8 | Contract type compatible with applicant's offered types | `CONTRACT_TYPE_INCOMPATIBLE` |
| 9 | Location/work-authorization restriction satisfied | `LOCATION_RESTRICTED` |
| 10 | Compensation floor: applicant min ≥ job max → block; else soft flag | `COMP_INCOMPATIBLE` |
| 11 | No duplicate active application for the job | `DUPLICATE_APPLICATION` |
| 12 | No active conflict (either party blocked the other) | `CONFLICT_PRESENT` |

Skills are deliberately **not** hard-gated (except credentials): skill fit belongs to matching, where partial overlap can still be a great hire. Eligibility matrix sample:

```
Capability C applicant vs difficulty: F✓ E✓ D✓ C✓ B(stretch) A✗ S✗ SS✗ SSS✗
Capability SSS applicant vs difficulty: F✓ E✓ D✓ C✓ B✓ A✓ S✓ SS✓ SSS✓
```

Every rejected application returns the reason code + human copy ("You're C; this role needs A-level scope. Here's your path to A") — turning rejection into progression, which is the product's emotional core.

---

## J. Matching Engine

Two stages. Stage 1 is SQL; Stage 2 is a deterministic weighted rubric whose output class is cached in the `matches` table (computed by workers on change events, not per request).

### J.1 Stage 1 — Hard eligibility

Indexed SQL over the candidate pool using §I rules. Output: eligible pairs only. No pair ever reaches Stage 2 or any feed without passing Stage 1 — invariant `MATCH_NEVER_BYPASSES_HARD_ELIGIBILITY`.

### J.2 Stage 2 — Soft ranking v1 (`match-v1`)

| Factor | Weight | Notes |
|---|---|---|
| Required-skills coverage (depth-weighted) | 30% | has/required ratio with seniority bands |
| Capability/difficulty fit | 20% | peak at equality; penalize under AND extreme over-qualification |
| Compensation alignment | 15% | overlap of expectation ranges |
| Availability/commitment fit | 10% | hours, timezone overlap |
| Domain experience | 10% | industry/domain history |
| Preference-band fit | 10% | inside preferred range scores full |
| Company quality prior | 5% | company quality score decile |

Output classes: **Exceptional ≥0.85 · Strong ≥0.70 · Good ≥0.55 · Possible ≥0.40 · Poor <0.40**. Users see class + up to three reason codes ("Strong Match: 8/9 skills, comp aligned, timezone −3h"). No numbers cross the API boundary. ML later replaces the rubric only as a *shadow scorer* calibrated against realized hires; it must beat `match-v1` on backtested hire prediction before promotion, and reason codes become SHAP-style factor attributions mapped to the same vocabulary.

### J.3 Match freshness

`matches` rows carry `stale` flags; recomputation triggers: job published/edited, applicant profile/rank/evidence changed, contract state changes, nightly staleness sweep. Feed reads are therefore O(indexed lookup), not O(scoring).

---

## K. Job Visibility

```
Visible set = hard-eligible jobs
    ordered: preference-band first → stretch labeled "above level"
                                  → below-band collapsed under "More below your range"
    ranked by: match class → freshness → company quality prior
    diversified: ≤3 jobs per company in top 10
```

- Below-capability work is visible but visually secondary — hiding it would strangle liquidity for the platform's highest-value users.
- Above-floor-but-beyond-stretch jobs are *invisible*, with a count + explanation ("12 jobs need more evidence than you have yet").
- Search (§W) respects the same visibility predicate; you cannot filter your way around ineligibility.
- Companies never gain query access to applicants who are ineligible for their jobs (prevents sourcing-fishing around the gate).

---

## L. Applicant Discovery

Two surfaces:

1. **Applicant feed** (§K) — the default daily surface.
2. **Company sourcing search** — companies search applicants by rank, skills, availability, location, domain. Requires Identity+ trust on the company, reveals only Marketplace-visible fields (§Z), and logs access (applicants can see "viewed by N companies"). Ordering uses the same match engine against a representative "open-to-work" profile rather than a specific job; results show tier + confidence, sorted by match class — explicitly **not** sorted by rank alone.

---

## M. Company Discovery

Public company pages: rank, confidence, reputation stats, active job tiers, industries, review highlights. Directory search filters by rank/industry/job-quality. Applicants see employer quality *before* applying — informed consent is part of the product's fairness story (nobody applies blind to a D-rank employer pretending otherwise). Company ranks are public by design; companies were told this at onboarding.

---
## N. Anti-Gaming

Structural principle: **the strongest evidence requires passing through payment and identity rails.** Everything gameable is capped by something harder to fake.

### N.1 Attack → mitigation matrix

| Attack | Detection signal | Mitigation |
|---|---|---|
| Fake experience/references | Verification failure, reference graph anomalies | External evidence weighted 6× claims; failed verifications become negative evidence |
| Bought/fake reviews | Review-graph analysis: reciprocity, timing clusters, text similarity, new-account reviewers | Reviews weighted by counterparty trust × contract value × relationship depth; ring reviews get zero weight retroactively |
| Fake contracts / self-dealing | Payment graph cycles, shared instruments/devices/addresses | Contracts only count with verified payment flow through platform rails |
| Strategic low-level contracts (rank farming) | Contract value/duration distribution vs. claimed tier | Rank evidence value scales with contract size & duration; ≥S tiers require substantial-contract minimums |
| Sybil accounts | Device fingerprint, payment instrument reuse, KYC uniqueness | One verified account per human; Identity+ required to exceed C; duplicate clusters → all restricted |
| Collusion rings (mutual hiring for reviews) | Strongly-connected components in the hire graph with low external connectivity | Ring members' mutual evidence discounted; manual fraud review |
| Company fake jobs / applicant fishing | Jobs with views but no intent signals; cloned postings | Posting requires Identity + payment instrument; low-quality prior suppresses feed presence (§F.3) |
| Comp manipulation then bait-and-switch | Post-hire "as described" ratings vs. posting delta | Delta feeds job rank calibration + company fairness score; material posting changes require republish + notify (§AL) |
| Cancellation abuse (interview-only postings) | Cancel-after-application rates | Counts against company clarity signal; applicant-side cancellations decay with account age |
| Observation gaming (probing eligibility boundaries) | Application pattern telemetry | Eligibility is deterministic — probing yields no information advantage beyond the reason codes everyone sees |

### N.2 Design stance

We do not chase a perfectly cheat-proof system (impossible); we ensure **cheating is expensive relative to earning**. The cheapest path to S-rank must always be doing real work. Quarterly red-team simulation (§AC) tests whether that invariant still holds.

---

## O. Fraud Prevention

### O.1 Separation enforced in both directions

- Fraud state never changes rank (capability preserved).
- Rank never excuses fraud (participation gated by trust/fraud state).

`Applicant · Rank S · Confidence High · Trust Verified · Fraud: Restricted` is a representable, correct state.

### O.2 Detection pipeline

Signals stream into `fraud_signals`: device/IP clustering, identity-document reuse, bank/payout instrument collisions, review-text n-gram similarity, timing regularity (bots), compensation outliers, velocity anomalies (contracts/hour, applications/hour). Rules engine v1 (deterministic thresholds) → case queue. ML anomaly detection arrives Phase 3 as *triage ranking* for investigators, never auto-adjudication.

### O.3 Response ladder

Watch (log + shadow-flag) → Review (hold payouts/reviews, human investigator ≤72h) → Restricted (application caps, sourcing hidden, user notified with reason category + appeal link) → Suspended (excluded from percentile population, feeds, search). Every adverse action above Watch requires human sign-off and opens an appeal ticket with SLA — required for fairness and for automated-decision-making compliance exposure (§AK).

---

## P. Cold Start

### P.1 New applicant

```
Unranked → onboarding assessment (vertical-specific, 30–45 min, free)
         → Provisional rank (≤C cap) → evidence verification raises confidence
         → first 2 contracts confirm tier → confidence climbs
```

The assessment is the cold-start killer: it converts zero-history users into evaluated users in under an hour and doubles as anti-fraud (ability check). Seeding strategy: concierge onboarding for the first ~500 applicants (human-reviewed profiles, white-glove verification) — labor-intensive, but it manufactures the trustworthy seed cohort every percentile system needs.

### P.2 New company

Business identity verification + payment instrument → Provisional ≤ B. First 3 hires are heavily weighted in the quality score so good small companies surface fast. Founding-employer program: free postings for 12 months in exchange for full structured job data + feedback participation.

### P.3 New job

Rubric-ranked immediately at creation (no history needed), flagged **Estimated** until interaction data exists. No chicken-and-egg because jobs are the one entity whose rank doesn't depend on marketplace history.

---

## Q. Ranking Calibration

### Q.1 Populations

Percentiles computed per entity-type × dimension × domain cohort over **active** subjects (trailing-180-day activity) with ≥1 evidence unit. Suspended accounts excluded from populations entirely. Minimum cohort: 500 assessed subjects before percentile caps activate; below that, gates alone determine tier.

### Q.2 Cadence

- **Event-driven recalc:** evidence added, contract completed, review submitted, dispute resolved, verification result.
- **Scheduled recalibration:** quarterly, batch, off-peak, with mandatory regression report (§AC) reviewed by a human before publish.
- **Drift-triggered:** tier-distribution monitors alarm when any tier drifts >20% relative from its quarterly baseline between scheduled runs.

### Q.3 Hysteresis and stability

Tier boundary crossing requires exceeding the boundary by ±15 internal points (or an explicit event). One-tier-per-recalc maximum except integrity events. Result: ranks move like careers, not like stock tickers — brief §54.11 satisfied without freezing the system.

### Q.4 Inflation defense recap

Absolute evidence floors (primary) + percentile caps at top tiers (secondary) + provisional caps + volume gates for companies + SSS manual audits + quarterly distribution review with a standing question: *"Is SSS still 0.1%?" If not, tighten caps before anything else.*

### Q.5 Fairness monitoring

Dashboards track tier distributions segmented by geography, language, education, and access channel. Alarms fire on unexplained disparity (e.g., region X's A-rate half of platform mean at similar assessment scores). Prestige proxies ("worked at famous company") are explicitly excluded features from v1 scoring — verified *outcomes*, not brand names, earn rank. Quarterly audit reviews top-decision reason codes for proxy contamination.

---

## R. Ranking Versioning

```
ranking_models: id, name, version, config_json (hash-pinned), status(shadow/active/retired), deployed_at
rankings:       …, model_version FK, inputs_hash, calculated_at
rank_events:    …, model_version FK   [APPEND-ONLY]
```

- Every calculation pins its model version + input snapshot hash → historical reconstruction is exact.
- **Shadow mode:** new model versions compute alongside production for ≥2 weeks, writing `status=shadow` rows; diff reports quantify mass movement (any tier shifting >15% of its population blocks promotion).
- **Backtesting harness** replays historical evidence timelines through candidate models.
- **A/B:** cohort-assigned models allowed for matching weights; *rank itself is never A/B'd* (users must live in one reality).
- **Rollback = repointing active version**; rankings recompute from immutable inputs. No formula change ever silently rewrites history — RankEvents keep both the old and new world auditable.

---
## S. Database Architecture

### S.1 Why PostgreSQL replaces MongoDB

| Requirement | Postgres | MongoDB |
|---|---|---|
| Application uniqueness, eligibility atomicity | Constraints + serializable txns, native | Requires careful app-level discipline |
| Immutable audit (rank_events) | Append-only + grants; FKs to subjects | DIY integrity |
| Calibration analytics (percentiles, drift) | `percent_rank`, window functions — the core query of §Q | Aggregation pipeline, slower iteration |
| Structured jobs | JSONB **with JSON-schema validation** — flexibility without schema anarchy | Native, but the flexibility is a liability here: the product's premise *is* structure |
| One system to operate at MVP | ✓ | ✓ |

The brief invites this challenge; the data model of a marketplace with invariants, state machines, and statistical calibration is the canonical relational case. Keep .NET; swap the store.

### S.2 Table catalog (core columns only)

**Identity & profiles:** `users(id, email, auth refs, trust_level, fraud_state)` · `applicant_profiles(user_id, headline, visibility jsonb, availability jsonb, comp_expectations jsonb)` · `applicant_skills(profile_id, skill_id, level, verified bool)` · `skill_dictionary` · `applicant_experiences` · `companies(id, name, verification jsonb, quality_score_cached, rank_tier_cached)` · `company_members(company_id, user_id, role)`.

**Jobs:** `jobs(id, company_id, title, status[draft|published|closed], dimension, rank_tier_cached, rank_confidence, authority, scope, structure jsonb [responsibilities, outcomes], commitment jsonb [hours, duration, contract_type], compensation jsonb [min, max, currency, benchmark_ratio], required_credentials jsonb, location jsonb, comp_flag, quality_prior, version, published_at)`. Indexes: `(status, rank_tier)`, `(company_id)`, GIN on skills/structure.

**Marketplace loop:** `applications(id, job_id, applicant_id, status, stretch bool, UNIQUE(job_id, applicant_id))` · `matches(job_id, applicant_id, match_class, reasons jsonb, stale, PK(job_id, applicant_id))` · `contracts(id, job_id, applicant_id, state[offered→active→completed|cancelled|disputed], value, currency)` · `reviews(id, contract_id, author_subject, target_subject, rating, text, weight, status)`.

**Ranking:** `rankings(id, subject_type, subject_id, dimension, rank_tier, confidence_tier, internal_score, percentile, evidence_points, model_version, inputs_hash, previous_tier, status[active|shadow], calculated_at)` — unique active row per `(subject_type, subject_id, dimension)` · `rank_events(subject_type, subject_id, dimension, previous_tier, new_tier, trigger_type, trigger_ref, reason_codes jsonb, actor, model_version, created_at)` **append-only: REVOKE UPDATE/DELETE** · `ranking_models` · `rank_overrides(admin_id, subject, from, to, reason, evidence_ref, approver_admin_id)`.

**Evidence & trust:** `evidences(id, applicant_id, type, weight, verified_by, verified_at, payload_ref)` · `assessments` / `assessment_attempts` · `verifications` · `trust_events` · `fraud_signals` · `disputes`.

**Platform:** `outbox(id, topic, payload jsonb, created_at, processed_at)` · `audit_log` (append-only) · `notifications` · `idempotency_keys`.

### S.3 Denormalization policy

`rank_tier_cached` lives on `jobs`, `companies`, and feed-facing read models, updated exclusively by RankChanged consumers — never by ranking-unaware code paths. Cache tier (low cardinality), never score. Stale cache degrades gracefully to "Estimating…" UI states.

### S.4 Growth plan

Partition `applications`, `rank_events`, `audit_log` by month at ~10M rows. Read replica for analytics before year one. No sharding until a single vertical saturates a beefy primary — which, realistically, is past 1M users.

---

## T. Domain Architecture

**Modular monolith** (.NET 8), one deployable, module boundaries enforced by separate namespaces + separate DB schemas + an architecture-test that fails CI on cross-module table access.

```
┌─────────────────────────────────────────────────────┐
│ API Host (REST)                                     │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ Identity │ Profiles │ Jobs     │ Applications│ Contracts│
│ Profiles │ Applicants│ Search  │ Matching   │ Reviews │
│ Ranking  │ Reputation│ Trust&Safety│ Notifications│ Admin│
├──────────┴──────────┴──────────┴──────────┴─────────┤
│ In-process event bus → Transactional Outbox (PG)    │
├─────────────────────────────────────────────────────┤
│ Worker Hosts: rank recalcs · match recompute ·      │
│ outbox dispatch · calibration batch · fraud rules   │
└─────────────────────────────────────────────────────┘
```

Dependency law: modules publish events and read published read-models; only the owning module writes its tables. Ranking consumes events from every module but nothing writes to ranking tables except the ranking module. Extraction to services becomes justified only when team >~15 engineers or a workload has wildly divergent scaling — none exists in the MVP horizon. Microservices now would be resume-driven development.

---

## U. API Architecture

REST, `/v1`, JSON, RFC 7807 errors, cursor pagination, `Idempotency-Key` required on all POST mutations that create money-or-state (apply, contract transitions), OAuth2/OIDC JWTs, per-account rate limits (stricter for Unverified).

### U.1 Endpoint catalog (MVP)

```
POST /auth/register|login|refresh|logout
GET  /me                          GET /me/rank            (tier+confidence+reasons+progression)
GET  /me/rank/history             GET /me/progression
POST /verifications               GET  /verifications/{id}
POST /jobs                        PATCH /jobs/{id}        POST /jobs/{id}/publish
GET  /jobs/{id}                   GET  /feed/jobs         GET /jobs?search…
POST /jobs/{id}/apply             GET  /jobs/{id}/applications        (company-scoped)
POST /applications/{id}:accept|reject|interview|offer
GET  /matches/applicants?job_id=  (company sourcing)
GET  /applicants/{id}             (visibility-filtered)
POST /companies                   GET  /companies/{id}
POST /contracts                   POST /contracts/{id}:start|complete|cancel|dispute
POST /reviews                     GET  /reviews?subject=
# Admin (separate authz realm, internal):
GET  /admin/rankings              POST /admin/rankings/{subject}/recompute
POST /admin/rankings/override     GET  /admin/rank-events
GET  /admin/fraud-queue           POST /admin/cases/{id}:restrict|suspend|clear
```

### U.2 Public vs. internal payloads — enforced

```json
// Public — the ONLY shape users ever see:
{ "rank": "A", "confidence": "Moderate" }

// Admin realm only:
{ "rank": "A", "internalScore": 612, "percentile": 71.3,
  "modelVersion": "rank-applicant-v1", "reasonCodes": ["CONTRACTS_COMPLETED_2"] }
```

A CI contract test reflects over the OpenAPI spec and fails if any non-admin response schema contains numeric rank fields (`score`, `percentile`, `internal*`). The leak-prevention is mechanical, not cultural.

---

## V. Event Architecture

Transactional outbox in Postgres; worker dispatch; **at-least-once delivery + idempotent consumers** (event id dedupe table); per-aggregate ordering; exponential backoff retries; DLQ table + admin replay command. No Kafka day one — the outbox is one less distributed system while event volume fits comfortably in Postgres (it will, for years).

### V.1 Core events

`ApplicantRegistered` · `ApplicantEvidenceAdded` · `ApplicantRankChanged` · `CompanyRegistered` · `CompanyRankChanged` · `JobCreated/Published/Updated/Closed` · `JobRankChanged` · `ApplicationSubmitted/Accepted/Rejected` · `ContractStarted/Completed/Cancelled/Disputed` · `ReviewSubmitted/Removed` · `VerificationCompleted` · `FraudSignalRaised` · `AccountRestricted/Suspended/Reinstated`.

### V.2 Sync vs async

| Sync (request path) | Async (workers) |
|---|---|
| Eligibility check (reads cached tiers) | Rank recalculation |
| Application submission (uniqueness via constraint) | Match recomputation |
| Contract state transitions | Review weighting, fraud rules |
| Feed reads (cached matches) | Calibration batches, notifications, search indexing |

Failure stance: if the ranking subsystem is down, applications still flow using last-good cached tiers (§AL). Marketplace liquidity never depends on ranking freshness.

---

## W. Search Architecture

What lives where:

| Store | Contents |
|---|---|
| **Postgres** | System of record; eligibility queries; small-scale full-text (tsvector + trigram) fine to ~50–100k jobs |
| **Redis** (Phase 2) | Sessions, rate limits, hot feed caches, tier lookup cache |
| **OpenSearch** (Phase 3, trigger: >100k active jobs or search p95 >300ms) | Job/applicant/company discovery, faceted filters, relevance tuning |
| **Queue/outbox** | Event fan-out to indexers, match workers, notifications |
| **Warehouse** (Phase 4) | CDC-fed analytics; never the operational path |

Index documents mirror visibility rules exactly — the search layer can never expose what the DB would hide. Index updates ride domain events (eventual consistency ≤ seconds, acceptable for discovery; eligibility always re-checked against Postgres truth at apply time).

---
## X. Frontend Architecture

React SPA, module-per-domain folder structure mirroring backend modules, typed API client generated from OpenAPI.

### X.1 Rank UX system (the product's face)

- `RankBadge` — tier chip with distinct hue + label (never color alone; accessibility).
- `ConfidenceBadge` — Provisional/…/Verified, always adjacent to rank.
- `RankExplainDrawer` — "Why am I B?" → reason codes rendered as human copy + evidence list.
- `ProgressionPanel` — "Path to A": checklist of unmet gates with live status (§E.4). This is the retention mechanic; it must be truthful, which it can be because gates are deterministic.
- `MatchChip` — class label + reasons ("Strong Match: 8/9 skills").
- `EligibilityGate` — blocked actions render the specific reason code's copy + progression link. Rejection becomes onboarding.

Type discipline: public DTO types have no numeric rank fields — TypeScript makes score leakage unrepresentable in UI code, matching the §U contract test.

### X.2 Key screens

Applicant: feed (preference-band grouped), profile editor + evidence vault, rank dashboard (explain + progression), assessment flow, applications tracker.
Company: job wizard (structured sections — the rubric inputs), applicant feed per job, sourcing search, company dashboard (quality score breakdown + path to next tier).
Admin (separate app): case queue, rank inspector w/ full history timeline, override flow (dual-control), model diff viewer, calibration report review.

---

## Y. Security

| Layer | Controls |
|---|---|
| AuthN | OIDC, short-lived JWT + refresh rotation; WebAuthn for admin |
| AuthZ | RBAC (applicant/company-member/admin) **+ object-level policy checks on every handler** (owner/membership) — a user can never touch another user's ranking, applications, or evidence; enforced by authorization integration tests per endpoint |
| Company isolation | All company-scoped queries filtered by membership; no cross-company applicant data pre-application |
| Rate limiting | Per-account + per-IP tiers; stricter for Unverified; eligibility-probing patterns throttled |
| Uploads | Signed URLs, type/size allowlists, AV scan, private bucket, no direct public URLs — resumes/portfolios via expiring links gated by visibility rules (§Z) |
| Secrets | Vault/KMS; no secrets in config files or CI logs |
| Audit | Append-only audit_log for every privileged action and rank event; tamper-evident hashing |
| Admin | Separate realm, WebAuthn mandatory, IP allowlist, dual-control overrides (maker/checker) |
| Data | TLS everywhere, at-rest encryption, PII field-level encryption, minimal-retention purge jobs |

Threat-model reviews each phase; ranking-manipulation is treated as a first-class threat (§N), not an afterthought.

---

## Z. Privacy

Five visibility levels; every profile field maps to exactly one:

| Level | Contents | Who sees it |
|---|---|---|
| Public | Anon handle, avatar, rank, confidence, skill tags | Everyone incl. logged-out |
| Marketplace-visible | Headline, availability, domain stats, reputation summary | Any authenticated searcher (sourcing requires Identity+ company) |
| Application-visible | Resume, portfolio, detailed experience, contact | Companies of jobs applied to |
| Company-only | Internal hiring notes, interview feedback | That company's members |
| Private | Contact details, verifications docs, comp expectations, fraud state | Subject + admin realm only |

Rank is public-by-design — disclosed plainly at onboarding ("your tier is visible; here's what that means") because hiding it would break informed consent for a livelihood-affecting signal. GDPR posture: lawful basis = legitimate interest + consent for verifications; DSAR export + delete jobs; Art.-22-style human review + appeal for adverse automated rank/fraud decisions (§O.3, §AA).

---

## AA. Admin Architecture

Internal console capabilities: subject search → rank inspector (current row + full RankEvent timeline + input snapshot diff) · evidence verification queue · fraud case queue with response ladder (§O.3) · dispute workflow · job moderation · **manual overrides** requiring `{admin, reason, previous rank, new rank, evidence ref}` + second-admin approval for any move ≥2 tiers — overrides emit ordinary RankEvents with `actor=admin`, indistinguishable in audit from system events except by actor · model management (promote/shadow/rollback with diff report gate) · calibration report review · appeals queue with SLA timers.

Principle: admins are powerful but never silent. Every administrative action lands in the same immutable audit fabric as system actions.

---

## AB. Analytics

**North star: verified completed contracts per week** (marketplace velocity). Supporting cast:

- Funnel: view → application → response → interview → offer → contract → completion (per arm, per cohort)
- Matching quality: match-class vs. hire-rate calibration curves (is "Strong" actually strong?)
- Ranking health: tier distributions, transition matrices, stability index, SSS share ≤0.1%±tolerance, confidence mix
- Business: GMV, take rate, employer/applicant retention, CAC/LTV when paid channels start

MVP implementation: read-replica SQL + Metabase-class BI. Warehouse + CDC arrives when ad-hoc SQL hurts (~Phase 4). Event payloads are designed warehouse-ready from day one (versioned, typed) so the later migration is mechanical.

---

## AC. Testing

| Suite | What it locks down |
|---|---|
| Unit | Ranking rubrics (golden-file scores), eligibility matrix (all 81 capability×difficulty cells), match weights |
| Property-based | Invariants below hold for arbitrary inputs |
| Integration | Testcontainers Postgres; outbox delivery; idempotent consumers |
| Contract | OpenAPI schema tests **incl. the no-numeric-rank serializer guard** |
| Security | Per-endpoint authz matrix; visibility-level leaks; IDOR sweeps |
| Load | k6: feed p95 <300ms @500 RPS; apply p95 <500ms; recalc ≥5k subjects/min/worker |
| Ranking regression | Golden cohort (synthetic + anonymized real): a model change ships with its full before/after tier-diff report; >15% shift in any tier blocks promotion |
| Simulation | Agent-based marketplace: 10k synthetic applicants/jobs with ground-truth latent skill. Assertions: rank recovers ground-truth decile ≥80%; SSS population ≤0.3%; stable agents oscillate ≤1 tier/quarter; injected 5% collusion ring gains <1 tier |

Standing invariant list (CI-enforced): suspended users cannot apply · no cross-user ranking writes · unpublished/unranked jobs invisible · every ranking references a model version · every rank change has a RankEvent · public APIs expose zero internal scores · SSS stays rare · model changes never rewrite history · eligibility deterministic · matching never bypasses hard filters · percentile populations exclude suspended accounts.

---
## AD. Infrastructure

Staged, not big-bang:

| Stage | Trigger | Topology |
|---|---|---|
| 0 — Day 1 | launch | Single cloud VM/container host: API + worker hosts, managed Postgres, S3-compatible object storage, CDN for SPA. ~$150–400/mo |
| 1 | >2k DAU or DB CPU >50% | Split workers to own host; Redis (sessions/rate-limit/feed cache); daily PITR backups verified by restore drills |
| 2 | Search p95 >300ms or >50k jobs | OpenSearch cluster; Postgres read replica for BI |
| 3 | >100k jobs / multi-region demand | Managed queue if outbox latency hurts; multi-AZ everything; warehouse via CDC |

Target-state diagram (not day one):

```
React SPA → CDN → LB → ASP.NET Core Modular Monolith (API)
                          ├─ PostgreSQL primary (+replica)   ← system of record
                          ├─ Outbox → Workers (rank/match/fraud/index)
                          ├─ Redis (cache/sessions/rate limit)
                          ├─ OpenSearch (discovery)
                          └─ Object storage (resumes/portfolios/evidence)
Analytics: CDC → warehouse → BI
```

---

## AE. Scalability

| Scale | What breaks first | Introduce |
|---|---|---|
| 10k users | nothing | — (single box fine) |
| 100k users | feed read load, session store | Redis, worker separation, read replica, OpenSearch |
| 1M users | write throughput on hot tables, analytics contention | Partitioning (applications/rank_events/audit monthly), CDC→warehouse, dedicated match-calibration compute, consider event streaming only when fan-out genuinely demands it |
| 10M+ | single-writer ceiling | Shard by domain cohort × region (the dimension key already partitions naturally), CQRS read models, feature store for ML |

The modular monolith carries to ~1M users because the expensive paths (feed reads, matching) are already cache-and-worker shaped rather than request-path-shaped.

---

## AF. MVP

**Question the MVP answers:** *does rank-gated matching beat unrestricted search?* Everything else is scaffolding for that experiment.

- **Entities (12 tables):** users, applicant_profiles(+skills), companies, jobs(+structured sections), evidences, assessments, rankings, rank_events, applications, matches, contracts, reviews.
- **Screens (9):** onboarding+assessment · applicant profile · job wizard · job feed · rank dashboard w/ explain+progression · application flow · company applicant feed · company dashboard · admin shell (cases + rank inspector).
- **Ranking v1:** deterministic rubrics per §E/F/G, provisional caps, hysteresis, quarterly calibration stub.
- **Matching v1:** hard eligibility + weighted rubric + cached match classes.
- **Admin:** fraud ladder, overrides w/ dual control, model version view.
- **Analytics:** funnel + tier-distribution dashboards.
- **Explicitly postponed:** payments/escrow rails (contracts tracked manually with counterparty confirmation, marked lower confidence), messaging beyond basic contact, ML anything, multi-domain ranks, OpenSearch, mobile apps, enterprise features, public API.

**The launch experiment (brief §53):** new applicants stratified-randomized at signup into **control** (traditional search + relevance sort, ranks hidden) vs **treatment** (rank-gated feed + match classes). Employers see a blended pool; each application is arm-tagged. Primary metrics: employer-flagged-qualified rate, response rate, interview rate, hire rate per application. Guardrails: applications-per-job (liquidity), employer churn, applicant 7-day activation. Success = ≥25% relative interview-rate lift and ≥30% fewer bad-application flags with no liquidity loss; run 8 weeks or ≥500 hires. If treatment fails honestly — that is a *product* result: loosen gates, keep tiers as information-only, and iterate. The experiment is the product's constitution, which is why the schema keeps ranks even if gating dies.

---

## AG. Development Roadmap

| Phase | Weeks | Exit criteria |
|---|---|---|
| P0 Foundation | 1–6 | Auth, profiles, structured job CRUD, ranking v1 live, eligibility engine, feed v0, admin shell, CI invariant suite green |
| P1 Marketplace loop | 7–14 | Applications, matching, contracts (manual confirm), reviews, rank events + explain UI, assessment pipeline, **experiment launched** |
| P2 Trust depth | 15–22 | ID verification integration, external employment verification, company ranks full, Redis, search hardening, anti-fraud rules v1 |
| P3 Scale + intelligence | 23+ | Payment rails/escrow, ML shadow scoring vs. rubric, OpenSearch if triggered, warehouse, second-vertical decision gate |

---

## AH. Business Model

Employer-funded, always. Analysis:

| Model | Verdict |
|---|---|
| Pay-per-post | ❌ incentivizes volume over quality; poisons the structured-data asset |
| **Success fee on hires** | ✅ core model long-term (~12% of first-year contract value; aligns platform with outcome quality) |
| **Employer subscription** | ✅ secondary: sourcing search + applicant-feed access + verified hiring tools ($299–999/mo tiers post-validation) |
| Premium recruiting / enterprise talent pools | ✅ later — private marketplaces for SS/SSS sourcing is a natural enterprise product |
| Applicant-paid anything touching eligibility/rank | ❌ never — perverse incentives destroy evidence integrity (brief §54.13 honored absolutely) |
| Selling placement/boosts | ❌ never — placement-for-pay makes rank meaningless and is the fastest route to killing the moat |

Launch: free for both sides for 12 months (founding-cohort program). Verification priced at cost, never margin — verification is trust infrastructure, not profit center.

---

## AI. Marketplace Strategy

Vertical scorecard against brief §47 criteria (structure-ability, comparability, measurable skills, evaluable outcomes, comp data, demand, rank differentiation):

| Vertical | Score | Note |
|---|---|---|
| **Software development (mid-senior contract)** | ★★★★★ | Structured skills, rich comp data, evaluable outcomes, high contract value justifies verification friction |
| AI/automation ops | ★★★★ | Hot demand; thinner comp benchmarks; strong #2 and natural expansion |
| Design | ★★★ | Portfolio-evaluable but outcomes subjective |
| Marketing/Sales | ★★ | Attribution too noisy for early outcome data |
| Ops/VA | ★★ | Low complexity variance — tiers wouldn't differentiate |

**Launch: software-development contracting, global English-first**, comp-normalized by geography band. One vertical concentrates liquidity until match quality proves itself; expansion is gated on the calibration infrastructure supporting independent cohorts (which §Q already requires).

---

## AJ. Technical Risks

| Risk | Mitigation |
|---|---|
| Recalibration shock (mass tier shifts) | Hysteresis + regression-report promotion gate + staged rollout + rollback-by-version |
| Gaming arms race outruns rules engine | Structural rails (payment/identity) first; ML triage Phase 3; quarterly red-team simulation |
| Match-cache staleness → bad feeds | Stale flags + nightly sweep + change-event recompute; freshness SLO monitored |
| Postgres FTS ceiling pre-OpenSearch | Trigger metric watched from day 1; migration is additive (indexers ride existing events) |
| Outbox lag under burst | Per-aggregate ordering + backlog alarms + worker autoscaling; sync path never blocks on async consumers |
| Model-migration bug corrupts history | Inputs snapshot hashes make recomputation exact; shadow mode mandatory |

---

## AK. Product Risks

| Risk | Mitigation |
|---|---|
| Cold-start liquidity failure | Single vertical + concierge seeding + assessment-based instant evaluation + founding programs both sides |
| Employer resentment at being ranked | Transparency (published methodology summary), behavioral-only criteria, fast appeals; frame as "quality certification," market it as candidate-magnet |
| Rank anxiety / perceived unfairness among applicants | Explainability everywhere, deterministic progression paths, appeal rights, no silent downgrades |
| Regulatory exposure (automated decision-making on livelihoods; EU AI Act-class scrutiny of employment ranking systems) | Human review of adverse actions, appeal SLAs, transparency reports, audit fabric, fairness monitoring — designed in from §O/§AA, not bolted on |
| Disintermediation (off-platform deals) | On-platform completion is the *only* path to rank-relevant evidence — the moat itself is the lock-in |
| Tier system becomes decoration if experiment fails | Experiment-first roadmap; ranks survive as pure information layer if gating loses |

---

## AL. Ranking Failure Modes

| Failure | Behavior |
|---|---|
| Ranking service down | Applications continue on last-good cached tiers; recalc queue drains on recovery. Liquidity never waits on ranking |
| Calibration batch fails | Previous distributions retained; alarm; rerun. No partial publishes |
| Search outage | Feed falls back to indexed DB queries (relevance-degraded, eligibility intact); banner "reduced discovery" |
| Redis outage | Straight-to-Postgres reads; rate limits fall back to local token buckets; latency SLO degrades gracefully |
| Queue/DLQ backlog | Backlog alarms; consumer idempotency makes replay safe; admin replay tooling |
| Job materially edited after applications | Comp↓/scope↑ changes force republish + applicant notification + rank re-rubric; applicants may withdraw cleanly |
| Applicant suspended mid-funnel | Active applications frozen, contracts enter dispute workflow, subject excluded from populations |
| Company suspended | Jobs delisted instantly; active contracts continue under admin supervision; payouts escrow-held |
| Review removal (fraud) | Retroactive weight zeroing + affected rankings flagged for recalc |
| Model migration mid-flight | Versions coexist (`active`/`shadow`); reads pinned per-subject to latest completed calc — never half-migrated states |

---

## AM. Final Recommended Architecture

```
React SPA (tier-only types)
   ↓ HTTPS
ASP.NET Core 8 Modular Monolith  ── Identity · Profiles · Jobs · Applications
   │                              · Matching · Ranking · Reputation · Trust&Safety
   │                              · Contracts · Notifications · Admin
   ├── PostgreSQL 16              ← system of record, JSONB job structure,
   │                                 append-only rank_events/audit, outbox
   ├── Worker Hosts               ← rank recalcs · match recompute · calibration
   │                                 · fraud rules · indexers  (consume outbox)
   ├── Object Storage (S3/R2)     ← resumes, portfolios, evidence artifacts
   ├── Redis        (Stage 1+)    ← sessions · rate limits · feed caches
   ├── OpenSearch   (Stage 2+)    ← discovery when >~100k jobs
   └── Warehouse    (Stage 4)     ← CDC-fed analytics
```

**Chosen over alternatives:** MongoDB (loses to relational invariants + SQL calibration analytics — §S.1); microservices (no scaling justification before ~15 engineers — §T); Kafka day-one (outbox wins until volume demands more — §V); ML-first ranking (deterministic rubrics win on auditability, explainability, cold-start, and time-to-launch; ML enters as shadow scorer only after outcome data exists — §J.2).

**One-sentence summary:** a .NET modular monolith on PostgreSQL runs a deterministic, versioned, evidence-gated ranking system whose only public projection is categorical tiers; workers maintain cached match classes; every rank change is an immutable explained event; and the entire MVP exists to run one honest experiment — whether tier-gated visibility produces better hiring than open search.

---

*End of blueprint · Project LADDER v1.0 · Sections A–AM complete.*
