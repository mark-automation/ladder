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
