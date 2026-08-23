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
