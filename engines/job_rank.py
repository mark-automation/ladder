"""Job difficulty ranking — deterministic rubric v1 (blueprint F)."""
from .tiers import TIERS, tier_from_score
from . import tiers as _t

RULES = _t.load_rules("rank-job-v1")


def rank_job(job: dict) -> dict:
    """Rubric score 0-100 from structured job fields. Jobs are rubric-ranked,
    not percentile-ranked (blueprint F.1) — difficulty is a property of the work."""
    a_pts = RULES["authority_points"].get(job.get("authority", "individual_contributor"), 5)
    s_pts = RULES["scope_points"].get(job.get("scope", "single_feature"), 5)
    c_pts = max(0, min(RULES["complexity_max_points"], int(job.get("complexity_points", 10))))

    ratio = float(job.get("benchmark_ratio", 1.0))
    r = RULES["comp_modifier_rules"]
    if ratio >= 1.0:
        comp_mod = r["at_or_above_benchmark"]
        comp_flag = None
    elif ratio >= 0.85:
        comp_mod = r["within_15pct_below"]
        comp_flag = None
    elif ratio >= 0.65:
        comp_mod = r["below_15_to_35pct"]
        comp_flag = "comp_below_typical"
    else:
        comp_mod = r["below_35pct_plus"]
        comp_flag = "comp_significantly_below"

    score = round(min(100.0, a_pts + s_pts + c_pts + comp_mod), 1)
    tier = tier_from_score(score, TIERS["job"]["map"])

    # SSS anti-inflation: needs top-of-population composite AND real demand (F.1)
    if tier == "SSS":
        extra = TIERS["job"]["sss_extra"]
        views = int(job.get("views_qualified", 0))
        if views < extra["min_qualified_views"]:
            tier = "SS"
            comp_flag = comp_flag or "sss_held_insufficient_demand_data"

    confidence = "Estimated" if views_low(job) else "Calibrated"
    return {
        "rank_tier": tier,
        "confidence_tier": confidence,
        "internal_score": score,
        "percentile": None,   # jobs are not percentile-ranked
        "model_version": f'{RULES["model"]}-{RULES["version"]}',
        "reason_codes": [c for c in [
            f"authority={job.get('authority')}", f"scope={job.get('scope')}",
            comp_flag or None] if c],
    }


def views_low(job: dict) -> bool:
    return int(job.get("views_qualified", 0)) < TIERS["job"]["sss_extra"]["min_qualified_views"]
