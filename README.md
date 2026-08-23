# ▲ Ladder — Tier-Ranked Work Marketplace

MVP slice of **Project LADDER**: a labor marketplace where applicants, jobs and companies
each hold a categorical tier (**F E D C B A S SS SSS**), and tiers gate visibility,
eligibility and matching. Full blueprint: [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

**Live demo (static mirror):** https://mark-automation.github.io/ladder/
**Full product:** run locally (`python main.py` deps → uvicorn) for applications,
admin realm and recompute.

## What's implemented (blueprint §AF MVP)

| Area | Status |
|---|---|
| Deterministic ranking v1 (applicant evidence-gates · job rubric · company behavior) | ✅ `engines/` |
| Versioned rule configs | ✅ `rules/*-v1.json` |
| Immutable rank events w/ reasons + actor | ✅ `rank_events` append-only |
| Capability-floor eligibility + bounded stretch (corrected rule, §I) | ✅ `engines/eligibility.py` |
| Two-stage matching → match classes, no public scores | ✅ `engines/matching.py` |
| Public tier-only API + gated admin realm (internal scores) | ✅ `main.py` |
| Rank explain / progression UI, tier explorer, methodology page | ✅ templates |
| Static mirror → GitHub Pages | ✅ `gen_static.py` → `docs/` |
| Tests incl. 81-cell eligibility matrix + score-leak guard | ✅ 127 passing |

Deliberately empty in seed data: **SS / SSS** tiers (rarity is enforced; percentile caps
activate only above a 500-member cohort).

## Run locally

```bash
pip install -r requirements.txt      # fastapi, uvicorn
python main.py                       # seeds demo marketplace on first boot
uvicorn main:app --port 8600         # or: python -m uvicorn main:app --port 8600
```

- App: http://127.0.0.1:8600
- Admin realm: `/admin/rankings?key=ladder-demo-admin` (header `x-ladder-key` also accepted)
- Recompute all rankings: `POST /api/admin/recompute` (same key)
- Tests: `python -m pytest tests/ -q`

## Deploy the Pages mirror

```bash
uvicorn main:app --port 8600 &       # mirror fetches from the running server
python gen_static.py                 # rebuilds docs/ from live pages
git add docs && git commit -m "mirror" && git push   # Pages serves main:/docs
```

## Stack note (deviation from blueprint §AM)

Blueprint targets ASP.NET Core + PostgreSQL. This MVP runs **FastAPI + SQLite**
(no .NET SDK on this machine; no-install policy) while preserving every architectural
invariant: modular engine boundaries, versioned configs, immutable events, tier-only
public surface, admin realm separation. Porting later is mechanical — domain logic is
pure functions over versioned JSON rules.

## Layout

```
main.py            FastAPI app: pages + public API + admin realm
engines/           pure ranking/eligibility/matching logic (no I/O)
rules/*.json       versioned model configs (single source of truth)
seed.py            deterministic demo marketplace; computes ranks via engines
schema.sql         SQLite DDL (12-table MVP subset of §S.2)
tests/             127 tests: matrix, gates, caps, hysteresis, leak-guard, audit
templates/ static/ server-rendered UI + hand CSS (no build chain)
gen_static.py      live-server → docs/ mirror for GitHub Pages
docs/              Pages root: mirrored site + architecture blueprint
```
