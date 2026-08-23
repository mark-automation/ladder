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
