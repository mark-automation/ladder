"""Company employer-quality ranking — behavioral thresholds, no curve (blueprint G)."""
from .tiers import TIERS
from . import tiers as _t

RULES = _t.load_rules("rank-company-v1")


def quality_score(c: dict) -> float:
    """0..100 behavioral quality. Size/headcount/revenue appear nowhere (blueprint G)."""
    w = RULES["signal_weights"]
    resp = max(0.0, 1.0 - float(c.get("response_hours", 48)) / 72.0)
    disputes = float(c.get("dispute_rate", 0.05))
    dispute_score = max(0.0, 1.0 - disputes / RULES["dispute_rate_full_penalty"])
    comp_fair = float(c.get("comp_fairness", 70)) / 100.0
    score = (
        w["payment_reliability"]    * (float(c.get("payment_on_time_pct", 80)) / 100.0)
      + w["worker_satisfaction"]    * (max(0.0, min(1.0, (float(c.get("satisfaction_avg", 3)) - 2.0) / 3.0)))
      + w["contract_completion"]    * (float(c.get("completion_rate", 70)) / 100.0)
      + w["dispute_rate_inverse"]   * dispute_score
      + w["job_clarity"]            * (float(c.get("clarity_score", 50)) / 100.0)
      + w["responsiveness"]         * resp
      + w["compensation_fairness"]  * comp_fair
    )
    return round(min(100.0, max(0.0, score)), 1)


def rank_company(c: dict) -> dict:
    q = quality_score(c)
    n = int(c.get("contracts_completed", 0))
    tier = "F"
    for band in TIERS["company"]["map"]:
        if q >= band["min_quality"] and n >= band["min_contracts"]:
            tier = band["tier"]

    cfg = TIERS["company"]
    provisional = n < cfg["provisional_max_contracts"]
    if provisional:
        tier = min(tier, cfg["provisional_cap_tier"], key=lambda t: _idx(t))

    confidence = "Provisional" if provisional else ("Moderate" if n >= 40 else "Low")
    return {
        "rank_tier": tier,
        "confidence_tier": confidence,
        "internal_score": q,
        "percentile": None,   # behavioral thresholds, not a curve
        "model_version": f'{RULES["model"]}-{RULES["version"]}',
        "reason_codes": _reasons(q, n, tier),
    }


def _idx(t: str) -> int:
    from .tiers import RANK
    return RANK[t]


def _reasons(q, n, tier) -> list:
    codes = []
    nxt = None
    for band in TIERS["company"]["map"]:
        if band["tier"] == tier:
            i = TIERS["company"]["map"].index(band)
            if i + 1 < len(TIERS["company"]["map"]):
                nxt = TIERS["company"]["map"][i + 1]
            break
    if nxt:
        if q < nxt["min_quality"]:
            codes.append(f"NEED_QUALITY_{round(nxt['min_quality'] - q, 1)}_MORE_FOR_{nxt['tier']}")
        if n < nxt["min_contracts"]:
            codes.append(f"NEED_{nxt['min_contracts'] - n}_MORE_CONTRACTS_FOR_{nxt['tier']}")
    if n < TIERS["company"]["provisional_max_contracts"]:
        codes.append("PROVISIONAL_NEW_COMPANY_CAP")
    return codes or ["AT_TIER_REQUIREMENTS"]
