"""Two-stage matching: hard eligibility then soft rubric (blueprint J).

Output is a match CLASS + reason codes. Raw scores never cross the public API
(invariant MATCH_NEVER_BYPASSES_HARD_ELIGIBILITY enforced by callers).
"""
import json
from . import tiers as _t
from .tiers import RANK, TIERS
from .eligibility import check

RULES = _t.load_rules("match-v1")
W = RULES["weights"]

LEVEL_VALUES = {"familiar": 0.25, "working": 0.5, "proficient": 0.75, "expert": 1.0}
MIN_LEVEL = {"familiar": 0, "working": 1, "proficient": 2, "expert": 3}


def _skills_coverage(applicant_skills: list, required: list) -> tuple[float, list]:
    held = {s["skill"]: s.get("level", "familiar") for s in applicant_skills}
    if not required:
        return 1.0, []
    got, missing = 0.0, []
    for req in required:
        lvl = held.get(req["skill"])
        if lvl is None:
            missing.append(req["skill"])
            continue
        need = MIN_LEVEL.get(req.get("min_level", "working"), 1)
        have = MIN_LEVEL.get(lvl, 0)
        if have >= need:
            got += 1.0
        elif have == need - 1:
            got += 0.5          # one band short — partial credit
            missing.append(req["skill"] + " (level)")
        else:
            missing.append(req["skill"])
    return got / len(required), missing


def _rank_fit(applicant_rank: str, job_rank: str) -> float:
    """Peak at equality; penalize under-qualified AND heavy over-qualification."""
    d = RANK[job_rank] - RANK[applicant_rank]
    if d == 0:
        return 1.0
    if d > 0:
        return max(0.0, 0.7 - 0.35 * (d - 1))   # stretch: harder fit
    return max(0.0, 1.0 - 0.18 * (-d))          # below level: mild decay


def _comp_alignment(applicant: dict, job: dict) -> float:
    lo, hi = job.get("comp_min", 0), job.get("comp_max", 0)
    want = applicant.get("min_comp", 0)
    if hi <= 0:
        return 0.5   # unknown comp — neutral
    if want > hi:
        return 0.0
    if want < lo:
        return 1.0
    span = max(1, hi - lo)
    return round(0.75 + 0.25 * (hi - want) / span, 4)


def _availability(applicant: dict, job: dict) -> float:
    a, j = applicant.get("availability_hours", 0), job.get("commitment_hours", 0)
    if a <= 0:
        return 0.0
    if a >= j:
        # generous slack still fine; huge mismatch (40h person, 10h job) is OK too
        return 1.0
    return round(a / j, 4)


def _timezone_overlap(applicant: dict, job: dict) -> float:
    d = abs(int(applicant.get("tz_offset", 0)) - int(job.get("tz_offset", 0)))
    return max(0.0, 1.0 - d / 12.0)


def _preference_band(applicant: dict, job_rank: str) -> float:
    lo, hi = applicant.get("preferred_min_tier", "F"), applicant.get("preferred_max_tier", "SSS")
    if RANK[lo] <= RANK[job_rank] <= RANK[hi]:
        return 1.0
    edge = min(abs(RANK[job_rank] - RANK[lo]), abs(RANK[job_rank] - RANK[hi]))
    return max(0.0, round(1.0 - 0.3 * edge, 4))


def _domain(applicant: dict, job: dict) -> float:
    domains = set(applicant.get("domains", []))
    if not domains:
        return 0.5
    return 1.0 if job.get("domain", "software") in domains else 0.2


def score_match(applicant: dict, job: dict, company: dict,
                applicant_rank: str, job_rank: str, company_tier: str) -> dict:
    cov, missing = _skills_coverage(applicant.get("skills", []),
                                    job.get("skills_required", []))
    parts = {
        "skills_coverage": cov,
        "rank_fit": _rank_fit(applicant_rank, job_rank),
        "comp_alignment": _comp_alignment(applicant, job),
        "availability_fit": _availability(applicant, job),
        "domain_experience": _domain(applicant, job),
        "preference_band": _preference_band(applicant, job_rank),
        "company_quality_prior": {"F": .2, "E": .35, "D": .5, "C": .65, "B": .8,
                                  "A": .9, "S": 1.0, "SS": 1.0, "SSS": 1.0}.get(company_tier, .5),
    }
    score = round(sum(W[k] * v for k, v in parts.items()), 4)
    if cov == 0 and job.get("skills_required"):
        score *= 0.5   # meets none of the required skills — hard quality floor

    tz = _timezone_overlap(applicant, job)
    score = round(score * (0.85 + 0.15 * tz), 4)   # timezone as modifier

    reasons = []
    n_req = len(job.get("skills_required", [])) or 1
    full = sum(1 for r in job.get("skills_required", [])
               if any(s["skill"] == r["skill"] and
                      MIN_LEVEL.get(s.get("level", "familiar"), 0) >=
                      MIN_LEVEL.get(r.get("min_level", "working"), 1)
                      for s in applicant.get("skills", [])))
    reasons.append(f"{full}/{len(job.get('skills_required', []))} skills at required level")
    if missing and full < len(job.get("skills_required", [])):
        reasons.append("gaps: " + ", ".join(missing[:3]))
    if parts["comp_alignment"] >= 0.75:
        reasons.append("comp aligned")
    elif parts["comp_alignment"] == 0.0:
        reasons.append("below applicant minimum")
    if parts["preference_band"] == 1.0:
        reasons.append("in preferred range")
    elif parts["preference_band"] < 0.6:
        reasons.append("outside preferred range")
    if tz < 0.5:
        reasons.append(f"timezone −{abs(int(applicant.get('tz_offset',0))-int(job.get('tz_offset',0)))}h")

    return {"match_score": score, "match_class": class_for(score), "reasons": reasons}


def class_for(score: float) -> str:
    for c in TIERS["match_classes"]:
        if score >= c["min"]:
            return c["label"]
    return "Poor"


def feed_for_applicant(applicant: dict, applicant_rank_row: dict, jobs_with_ctx: list) -> list:
    """Stage 1 filter + Stage 2 order. jobs_with_ctx: dicts with job+company+tiers."""
    out = []
    conf = applicant_rank_row.get("confidence_tier", "Provisional")
    app = {**applicant, "confidence_tier": conf}
    for entry in jobs_with_ctx:
        ok, code, stretch = check(app, entry["job"], applicant_rank_row["rank_tier"],
                                  entry["job_rank"])
        if not ok:
            out.append({"job_id": entry["job"]["id"], "eligible": False,
                        "reason_code": code, "stretch": False})
            continue
        m = score_match(app, entry["job"], entry["company"],
                        applicant_rank_row["rank_tier"], entry["job_rank"],
                        entry["company_tier"])
        out.append({"job_id": entry["job"]["id"], "eligible": True,
                    "stretch": stretch, **m})
    eligible = [x for x in out if x["eligible"]]
    eligible.sort(key=lambda x: (-x["match_score"], x["stretch"], x["job_id"]))
    return eligible + [x for x in out if not x["eligible"]]


def candidates_for_job(applicant_rows: list, job: dict, job_rank: str,
                       rank_lookup) -> list:
    """Company-side feed (blueprint §30): never sorted by rank alone."""
    results = []
    for row in applicant_rows:
        ar = rank_lookup(row)
        app = {**row, "confidence_tier": ar["confidence_tier"]}
        ok, code, stretch = check(app, job, ar["rank_tier"], job_rank)
        if not ok:
            continue
        company_stub = {"id": -1}
        m = score_match(app, job, company_stub, ar["rank_tier"], job_rank, "C")
        results.append({"applicant_id": row["id"], "rank_tier": ar["rank_tier"],
                        "confidence": ar["confidence_tier"],
                        "match_class": m["match_class"], "reasons": m["reasons"]})
    results.sort(key=lambda r: {"Exceptional": 0, "Strong": 1, "Good": 2,
                                "Possible": 3, "Poor": 4}[r["match_class"]])
    return results


def rules_json() -> str:
    return json.dumps({"weights": W, "classes": TIERS["match_classes"],
                       "eligibility": ELIG})
