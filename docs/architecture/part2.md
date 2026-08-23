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
