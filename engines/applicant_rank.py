"""Applicant capability ranking — deterministic rubric v1 (blueprint E)."""
from .tiers import TIERS, RANK, tier_from_score, capped, map_confidence
from . import tiers as _t

RULES = _t.load_rules("rank-applicant-v1")


def _skill_depth(applicant: dict, evidences: list, assessments: list) -> float:
    """0..1 — assessment bands × skill breadth."""
    bands = RULES["assessment_bands"]
    levels = RULES["skill_level_values"]
    skills = applicant.get("skills", [])
    if not skills:
        return 0.0
    breadth = sum(levels.get(s.get("level", "familiar"), 0.25) for s in skills) / (len(skills) * 1.0)
    breadth = min(1.0, breadth)
    best_band = 0.0
    for a in assessments:
        best_band = max(best_band, bands.get(a.get("band", "novice"), 0.25))
    # assessment dominates (verified ability), breadth shapes it
    return min(1.0, 0.65 * best_band + 0.35 * breadth)


def _experience(applicant: dict) -> float:
    return RULES["experience_levels"].get(applicant.get("experience_level", "junior"), 0.3)


def _outcomes(evidences: list, contracts_completed: int, avg_rating: float) -> float:
    """0..1 — completed reviewed work + ratings."""
    completed_ev = [e for e in evidences if e["type"] in ("contract_completed_reviewed", "repeat_success")]
    base = min(1.0, len(completed_ev) / 6.0)
    rating_factor = max(0.0, min(1.0, (avg_rating - 3.0) / 2.0)) if avg_rating else 0.5
    volume = min(1.0, contracts_completed / 10.0)
    return min(1.0, 0.5 * base + 0.3 * rating_factor + 0.2 * volume)


def _verifications(evidences: list, identity_verified: bool) -> float:
    types = {e["type"] for e in evidences if e["verified"]}
    score = 0.3 if identity_verified else 0.0
    score += 0.4 if "verified_employment" in types else 0.0
    score += 0.3 if any(t in types for t in ("assessment", "portfolio")) else 0.0
    return min(1.0, score)


def _leadership(applicant: dict, evidences: list) -> float:
    claims = applicant.get("leadership_claims", [])
    verified_leadership = [e for e in evidences if e["type"] == "repeat_success"]
    return min(1.0, 0.2 * len(claims) + 0.25 * len(verified_leadership))


def evidence_points(evidences: list) -> int:
    w = RULES["evidence_type_weights"]
    return int(sum(w.get(e["type"], 0) * (1 if e["verified"] else 0.5) for e in evidences))


def rank_applicant(applicant: dict, evidences: list, assessments: list, *,
                   contracts_completed: int = 0, avg_rating: float = 0.0,
                   cohort_scores: list | None = None,
                   previous_tier: str | None = None) -> dict:
    """Returns full ranking record (internal fields included — caller filters for public)."""
    w = RULES["score_weights"]
    score = (
        w["skill_depth"] * _skill_depth(applicant, evidences, assessments)
      + w["experience_complexity"] * _experience(applicant)
      + w["marketplace_outcomes"] * _outcomes(evidences, contracts_completed, avg_rating)
      + w["verifications"] * _verifications(evidences, bool(applicant.get("identity_verified")))
      + w["leadership_ownership"] * _leadership(applicant, evidences)
    )
    score = round(min(1000.0, max(0.0, score)), 1)

    points = evidence_points(evidences)
    has_verified = any(e["verified"] for e in evidences)
    has_assessment = bool(assessments)
    identity_plus = bool(applicant.get("identity_verified")) and has_verified
    confidence = map_confidence(points, has_verified_evidence=has_verified,
                                has_assessment=has_assessment,
                                contracts_completed=contracts_completed,
                                identity_plus=identity_plus)

    # 1) gate tier: absolute evidence floors
    gates = TIERS["applicant"]["gate_evidence_points"]
    contract_gates = TIERS["applicant"]["gate_contracts_completed"]
    gate_tier = "F"
    for tier in TIERS["order"]:
        need_pts = gates.get(tier)
        need_contracts = contract_gates.get(tier, 0)
        if need_pts is None:      # F has no floor beyond being assessed
            gate_tier = tier
            continue
        if points >= need_pts and contracts_completed >= need_contracts:
            gate_tier = tier

    # self-reported claims alone can never exceed E
    only_claims = all(e["type"] == "claim" for e in evidences) and evidences
    if only_claims:
        gate_tier = capped(gate_tier, RULES["self_report_cap_tier"])

    # 2) percentile cap — only active when cohort is big enough (blueprint Q.1).
    #    Caps bind ONLY the top tiers S/SS/SSS; with no viable cohort they are inert.
    cap_tier = "SSS"
    percentile = None
    cfg = TIERS["applicant"]
    if cohort_scores and len(cohort_scores) >= cfg["min_cohort_for_caps"]:
        below = sum(1 for s in cohort_scores if s < score)
        percentile = round(100.0 * below / len(cohort_scores), 2)
        cap_tier = "A"   # below S's percentile floor → capped at A
        for tier in ("S", "SS", "SSS"):
            if percentile >= cfg["percentile_caps"][tier]:
                cap_tier = tier
            else:
                break
    effective = gate_tier if RANK[gate_tier] <= RANK[cap_tier] else cap_tier

    # 3) provisional cap
    if confidence == "Provisional":
        effective = capped(effective, cfg["provisional_cap_tier"])

    # 4) hysteresis: don't move tiers on a marginal score (blueprint Q.3)
    margin = cfg["hysteresis_margin"]
    if previous_tier and effective != previous_tier:
        boundary_score = _boundary_for(effective)
        if boundary_score is not None and abs(score - boundary_score) < margin:
            effective = previous_tier

    reasons = _reason_codes(points, contracts_completed, has_assessment, confidence, effective)
    return {
        "rank_tier": effective,
        "confidence_tier": confidence,
        "internal_score": score,
        "percentile": percentile,
        "evidence_points": points,
        "model_version": f'{RULES["model"]}-{RULES["version"]}',
        "reason_codes": reasons,
    }


def _boundary_for(tier: str) -> float | None:
    """Approximate internal-score boundary entering `tier` from below (for hysteresis)."""
    # score bands are derived from weights; boundaries at 1/9 increments is a v1 simplification
    idx = RANK[tier]
    return round(1000.0 * idx / len(TIERS["order"]), 1)


def _reason_codes(points, contracts, has_assessment, confidence, effective) -> list:
    codes = []
    gates = TIERS["applicant"]["gate_evidence_points"]
    cgates = TIERS["applicant"]["gate_contracts_completed"]
    nxt = TIERS["order"][min(RANK[effective] + 1, len(TIERS["order"]) - 1)]
    if RANK[nxt] > RANK[effective]:
        need_pts, need_c = gates.get(nxt), cgates.get(nxt, 0)
        if need_pts and points < need_pts:
            codes.append(f"NEED_EVIDENCE_{need_pts - points}_MORE_POINTS_FOR_{nxt}")
        if contracts < need_c:
            codes.append(f"NEED_{need_c - contracts}_MORE_CONTRACTS_FOR_{nxt}")
        if not has_assessment:
            codes.append(f"NEED_ASSESSMENT_FOR_{nxt}")
    if confidence == "Provisional":
        codes.append("CONFIDENCE_PROVISIONAL_CAP")
    if not codes:
        codes.append("AT_TIER_REQUIREMENTS")
    return codes
