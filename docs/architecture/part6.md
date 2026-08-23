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
