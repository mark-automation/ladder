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
