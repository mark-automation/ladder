"""Ladder — tier-ranked work marketplace. MVP slice of blueprint §AF."""
import json, os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db as dbm
from db import q, q1, ex, connect, init_db
from engines import tiers as T
from engines import applicant_rank as ar, job_rank as jr, company_rank as cr
from engines import matching as m
from engines.eligibility import check, eligibility_matrix
import seed as S

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

conn = connect()
init_db(conn)
S.seed(conn)

ADMIN_KEY = os.environ.get("LADDER_ADMIN_KEY", "ladder-demo-admin")
MODEL_VERSIONS = {
    "applicant": f'{ar.RULES["model"]}-{ar.RULES["version"]}',
    "job": f'{jr.RULES["model"]}-{jr.RULES["version"]}',
    "company": f'{cr.RULES["model"]}-{cr.RULES["version"]}',
}

app = FastAPI(title="Ladder", version="0.1.0",
              description="Categorical-tier labor marketplace — MVP slice.")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

REASON_COPY = {
    "CAPABILITY_BELOW_FLOOR": "This role needs more verified capability than your current tier.",
    "STRETCH_EVIDENCE_INSUFFICIENT": "Stretching one tier up needs Moderate confidence and Identity verification.",
    "STRETCH_QUOTA": "You already have the maximum open stretch applications (2).",
    "COMMITMENT_INCOMPATIBLE": "Your available hours don't cover this role's commitment.",
    "CONTRACT_TYPE_INCOMPATIBLE": "Contract type doesn't match what you offer.",
    "LOCATION_RESTRICTED": "This role is restricted to another country.",
    "COMP_INCOMPATIBLE": "The compensation band is below your stated minimum.",
    "ACCOUNT_RESTRICTED": "Your account can't apply right now.",
    "JOB_CLOSED": "This job isn't accepting applications.",
    "DUPLICATE_APPLICATION": "You already applied to this job.",
}


# ---------------------------------------------------------------- helpers ----

def rank_of(stype: str, sid: int) -> dict | None:
    return S.current_ranking(conn, stype, sid)


def tier_chip(stype_row_tier: str | None):
    t = stype_row_tier or "F"
    return {"tier": t, "idx": T.RANK[t], "label": T.TIERS["labels"][t]}


def job_public(row, co=None, jt=None) -> dict:
    d = dict(row)
    d.pop("benchmark_ratio", None)
    d["skills_required"] = S.jloads_(d.get("skills_required", "[]"), [])
    d["credentials_required"] = S.jloads_(d.get("credentials_required", "[]"), [])
    if co is not None:
        d["company"] = {"name": co["name"], "slug": co["slug"]}
        d["company_tier"] = (jt if jt else rank_of("company", co["id"]) or {}).get("rank_tier", "F")
    r = rank_of("job", row["id"]) or {}
    d["rank"] = r.get("rank_tier", "F")
    d["rank_label"] = "Estimated" if r.get("confidence_tier") == "Estimated" else "Calibrated"
    return d


def all_feed_entries(a: dict, arank: dict) -> list[dict]:
    """Eligibility + match for every published job, ordered eligible-first."""
    jobs = []
    for j in q(conn, "SELECT * FROM jobs WHERE status='published' ORDER BY id"):
        jd = S.job_context(j)
        co = q1(conn, "SELECT * FROM companies WHERE id=?", (jd["company_id"],))
        cot = (rank_of("company", co["id"]) or {}).get("rank_tier", "F")
        ok, code, stretch = check(a, jd, arank["rank_tier"], (rank_of("job", jd["id"]) or {}).get("rank_tier", "C"))
        entry = {"job": job_public(jd, co, {"rank_tier": cot}), "eligible": ok,
                 "stretch": stretch, "reason_code": code,
                 "reason_copy": REASON_COPY.get((code or "").split(":")[0])}
        if ok:
            mm = m.score_match(a, jd, dict(co), arank["rank_tier"],
                               entry["job"]["rank"], cot)
            entry |= {"match_class": mm["match_class"], "match_reasons": mm["reasons"]}
            entry["_sort"] = ({"Exceptional": 0, "Strong": 1, "Good": 2,
                               "Possible": 3, "Poor": 4}[mm["match_class"]], stretch, jd["id"])
        else:
            entry["_sort"] = (99, 0, jd["id"])
        jobs.append(entry)
    jobs.sort(key=lambda x: x["_sort"])
    return jobs


def require_admin(request: Request) -> None:
    key = request.headers.get("x-ladder-key") or request.query_params.get("key")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="admin realm")


# ------------------------------------------------------------------ pages ----

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    counts = {t: {"applicant": 0, "job": 0, "company": 0} for t in T.ORDER}
    for r in q(conn, """SELECT subject_type, rank_tier, COUNT(*) n FROM rankings
                        WHERE status='active' GROUP BY 1,2"""):
        if r["rank_tier"] in counts:
            counts[r["rank_tier"]][r["subject_type"]] = r["n"]
    return templates.TemplateResponse(request, "home.html", {
        "counts": counts, "order": T.ORDER, "labels": T.TIERS["labels"],
        "n_applicants": q1(conn, "SELECT COUNT(*) n FROM applicants")["n"],
        "n_jobs": q1(conn, "SELECT COUNT(*) n FROM jobs WHERE status='published'")["n"],
        "n_matches": q1(conn, "SELECT COUNT(*) n FROM matches")["n"],
    })


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, applicant: int = 1):
    row = q1(conn, "SELECT * FROM applicants WHERE id=?", (applicant,))
    if not row:
        raise HTTPException(404)
    a = S.applicant_context(row)
    arank = rank_of("applicant", applicant) or {}
    a["confidence_tier"] = arank.get("confidence_tier", "Provisional")
    entries = all_feed_entries(a, arank)
    return templates.TemplateResponse(request, "jobs.html", {
        "me": a, "my_rank": arank.get("rank_tier", "Unranked"),
        "my_confidence": arank.get("confidence_tier", "Provisional"),
        "entries": entries,
        "applicants": q(conn, "SELECT id, name FROM applicants ORDER BY id"),
        "n_eligible": sum(1 for e in entries if e["eligible"]),
    })


@app.get("/explorer", response_class=HTMLResponse)
def explorer(request: Request):
    dist = []
    for t in T.ORDER:
        row = {"tier": t, "label": T.TIERS["labels"][t]}
        for st in ("applicant", "job", "company"):
            row[st] = q1(conn, """SELECT COUNT(*) n FROM rankings WHERE status='active'
                          AND subject_type=? AND rank_tier=?""", (st, t))["n"]
        dist.append(row)
    matrices = {a: eligibility_matrix(a) for a in T.ORDER}
    return templates.TemplateResponse(request, "explorer.html", {
        "dist": dist, "order": T.ORDER, "matrices": matrices})


@app.get("/methodology", response_class=HTMLResponse)
def methodology(request: Request):
    return templates.TemplateResponse(request, "methodology.html", {
        "evidence_weights": ar.RULES["evidence_type_weights"],
        "gates": T.TIERS["applicant"]["gate_evidence_points"],
        "contract_gates": T.TIERS["applicant"]["gate_contracts_completed"],
        "caps": T.TIERS["applicant"]["percentile_caps"],
        "min_cohort": T.TIERS["applicant"]["min_cohort_for_caps"],
        "versions": MODEL_VERSIONS,
        "weights_match": m.W,
    })


@app.get("/profile/{applicant_id}", response_class=HTMLResponse)
def profile_page(request: Request, applicant_id: int):
    row = q1(conn, "SELECT * FROM applicants WHERE id=?", (applicant_id,))
    if not row:
        raise HTTPException(404)
    a = S.applicant_context(row)
    r = rank_of("applicant", applicant_id) or {}
    evs = q(conn, """SELECT e.*, CASE e.verified WHEN 1 THEN 'verified' ELSE 'unverified'
                     END v FROM evidences e WHERE applicant_id=? ORDER BY points DESC""",
            (applicant_id,))
    events = q(conn, """SELECT * FROM rank_events WHERE subject_type='applicant' AND subject_id=?
                        ORDER BY id DESC LIMIT 10""", (applicant_id,))
    apps = q(conn, """SELECT ap.*, j.title FROM applications ap JOIN jobs j ON j.id=ap.job_id
                      WHERE ap.applicant_id=? ORDER BY ap.id DESC""", (applicant_id,))
    nxt = T.ORDER[min(T.RANK[r.get("rank_tier", "F")] + 1, 8)]
    return templates.TemplateResponse(request, "profile.html", {
        "a": a, "r": r, "chip": tier_chip(r.get("rank_tier")),
        "next_tier": nxt, "evidences": evs, "events": events, "applications": apps,
        "skills": S.jloads_(a["skills"], []),
        "contracts_done": q1(conn, "SELECT COUNT(*) n FROM contracts WHERE applicant_id=? AND state='completed'", (applicant_id,))["n"],
        "has_assessment": bool(q1(conn, "SELECT id FROM assessments WHERE applicant_id=?", (applicant_id,))),
        "gate_pts": T.TIERS["applicant"]["gate_evidence_points"].get(nxt),
        "contract_gate": T.TIERS["applicant"]["gate_contracts_completed"].get(nxt, 0),
    })


@app.get("/company/{slug}", response_class=HTMLResponse)
def company_page(request: Request, slug: str):
    co = q1(conn, "SELECT * FROM companies WHERE slug=?", (slug,))
    if not co:
        raise HTTPException(404)
    r = rank_of("company", co["id"]) or {}
    jobs = [job_public(j) for j in q(conn, "SELECT * FROM jobs WHERE company_id=? AND status='published'", (co["id"],))]
    return templates.TemplateResponse(request, "company.html", {
        "c": co, "r": r, "chip": tier_chip(r.get("rank_tier")), "jobs": jobs,
    })


@app.get("/admin/rankings", response_class=HTMLResponse)
def admin_page(request: Request):
    require_admin(request)
    rows = q(conn, """SELECT * FROM rankings WHERE status='active'
                      ORDER BY subject_type, internal_score DESC""")
    return templates.TemplateResponse(request, "admin_rankings.html", {"rows": rows})


# -------------------------------------------------------------------- api ----

@app.get("/api/health")
def health():
    return {"ok": True, "service": "ladder"}


@app.get("/api/jobs")
def api_jobs():
    out = []
    for j in q(conn, "SELECT * FROM jobs WHERE status='published' ORDER BY id"):
        co = q1(conn, "SELECT * FROM companies WHERE id=?", (j["company_id"],))
        jp = job_public(j, co)
        out.append({k: jp[k] for k in (
            "id", "title", "authority", "scope", "commitment_hours", "duration_months",
            "contract_type", "comp_min", "comp_max", "domain", "location_rule",
            "skills_required", "rank", "rank_label", "company", "company_tier")})
    return {"jobs": out}


@app.get("/api/applicants/{applicant_id}/rank")
def api_rank(applicant_id: int):
    r = rank_of("applicant", applicant_id)
    if not r:
        raise HTTPException(404)
    a = q1(conn, "SELECT name FROM applicants WHERE id=?", (applicant_id,))
    return {  # public projection ONLY — no internalScore/percentile here
        "name": a["name"], "rank": r["rank_tier"], "confidence": r["confidence_tier"],
        "model": r["model_version"].split("-v")[0].replace("rank-", ""),
    }


@app.get("/api/feed/{applicant_id}")
def api_feed(applicant_id: int):
    row = q1(conn, "SELECT * FROM applicants WHERE id=?", (applicant_id,))
    if not row:
        raise HTTPException(404)
    a = S.applicant_context(row)
    arank = rank_of("applicant", applicant_id) or {}
    a["confidence_tier"] = arank.get("confidence_tier", "Provisional")
    entries = all_feed_entries(a, arank)
    rec, blocked = [], []
    for e in entries:
        item = {"job_id": e["job"]["id"], "title": e["job"]["title"],
                "rank": e["job"]["rank"], "company": e["job"]["company"]["name"],
                "stretch": e["stretch"]}
        if e["eligible"]:
            rec.append(item | {"match_class": e["match_class"],
                               "reasons": e["match_reasons"]})
        else:
            blocked.append(item | {"reason_code": e["reason_code"]})
    return {"you": {"rank": arank.get("rank_tier"), "confidence": arank.get("confidence_tier")},
            "recommended": rec, "blocked": blocked}


@app.post("/api/jobs/{job_id}/apply")
async def api_apply(job_id: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(422, "body must be JSON {applicant_id}")
    applicant_id = int(body.get("applicant_id", 0))
    j = q1(conn, "SELECT * FROM jobs WHERE id=?", (job_id,))
    arow = q1(conn, "SELECT * FROM applicants WHERE id=?", (applicant_id,))
    if not j or not arow:
        raise HTTPException(404, "job or applicant not found")
    if q1(conn, "SELECT id FROM applications WHERE job_id=? AND applicant_id=?",
          (job_id, applicant_id)):
        return JSONResponse({"error": "DUPLICATE_APPLICATION",
                             "message": REASON_COPY["DUPLICATE_APPLICATION"]}, 409)
    a = S.applicant_context(arow)
    arank = rank_of("applicant", applicant_id) or {}
    a["confidence_tier"] = arank.get("confidence_tier", "Provisional")
    jd = S.job_context(j)
    jrank = (rank_of("job", job_id) or {}).get("rank_tier", "C")
    ok, code, stretch = check(a, jd, arank.get("rank_tier", "F"), jrank,
                              stretch_open=_open_stretch_count(applicant_id))
    if not ok:
        base = (code or "").split(":")[0]
        return JSONResponse({"error": base, "detail": code,
                             "message": REASON_COPY.get(base, code)}, 422)
    ex(conn, "INSERT INTO applications(job_id, applicant_id, status, stretch) VALUES (?,?, 'submitted', ?)",
       (job_id, applicant_id, int(stretch)))
    return {"status": "submitted", "stretch": stretch,
            "job": j["title"], "your_rank": arank.get("rank_tier"), "job_rank": jrank}


def _open_stretch_count(applicant_id: int) -> int:
    return q1(conn, """SELECT COUNT(*) n FROM applications WHERE applicant_id=?
                       AND status='submitted' AND stretch=1""", (applicant_id,))["n"]


@app.post("/api/admin/recompute")
async def api_recompute(request: Request):
    require_admin(request)
    changes = S.compute_all_rankings(conn, actor="admin-api", trigger="RECALC")
    return {"changed": changes, "matches_refreshed": q1(conn, "SELECT COUNT(*) n FROM matches")["n"]}


@app.get("/api/admin/rankings")
def api_admin_rankings(request: Request):
    require_admin(request)
    rows = []
    for r in q(conn, "SELECT * FROM rankings WHERE status='active' ORDER BY subject_type, internal_score DESC"):
        rows.append({
            "subjectType": r["subject_type"], "subjectId": r["subject_id"],
            "rank": r["rank_tier"], "confidence": r["confidence_tier"],
            "internalScore": r["internal_score"], "percentile": r["percentile"],
            "evidencePoints": r["evidence_points"], "modelVersion": r["model_version"],
            "calculatedAt": r["calculated_at"],
        })
    return {"rankings": rows}
