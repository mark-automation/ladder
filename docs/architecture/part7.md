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
