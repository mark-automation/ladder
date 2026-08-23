"""Tier vocabulary + shared helpers. Blueprint C.2/D."""
import json, os

_RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules")

def load_rules(name: str) -> dict:
    with open(os.path.join(_RULES_DIR, name + ".json"), "r", encoding="utf-8") as f:
        return json.load(f)

TIERS = load_rules("tiers")
ORDER = TIERS["order"]                      # F..SSS
RANK = {t: i for i, t in enumerate(ORDER)}  # tier -> index


def tier_index(tier: str) -> int:
    return RANK[tier]


def tier_distance(a: str, b: str) -> int:
    """Positive when b is above a."""
    return RANK[b] - RANK[a]


def tier_from_score(score: float, band_map: list) -> str:
    """band_map: [{tier, min, max}] ascending. Last band whose min <= score wins,
    so gaps between bands fall DOWNWARD (never inflate)."""
    tier = band_map[0]["tier"] if band_map else ORDER[0]
    for band in band_map:
        if score >= band["min"]:
            tier = band["tier"]
    return tier


def capped(tier: str, cap_tier: str) -> str:
    return tier if RANK[tier] <= RANK[cap_tier] else cap_tier


def map_confidence(points: int, *, has_verified_evidence: bool, has_assessment: bool,
                   contracts_completed: int, identity_plus: bool) -> str:
    """Highest confidence level whose evidence floors + requirements are all met."""
    conf = TIERS["applicant"]["confidence"]
    best = "Provisional"
    for level in ["Provisional", "Low", "Moderate", "High", "Verified"]:
        req = conf[level]
        if points < req.get("min_points", 0):
            continue
        if req.get("requires_verified_evidence") and not has_verified_evidence:
            continue
        if req.get("requires_assessment") and not has_assessment:
            continue
        if req.get("requires_contracts", 0) > contracts_completed:
            continue
        if req.get("requires_identity_plus") and not identity_plus:
            continue
        best = level
    return best
