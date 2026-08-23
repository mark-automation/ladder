"""Hard eligibility — capability FLOOR + bounded stretch (blueprint I, correction C1).

Eligibility is deterministic and server-enforced; reason codes are returned for
every rejection so rejection becomes progression, not a dead end.
"""
from . import tiers as _t
from .tiers import RANK

ELIG = _t.load_rules("match-v1")["eligibility"]
CONF_ORDER = _t.load_rules("match-v1")["confidence_order"]
TRUST_ORDER = _t.load_rules("match-v1")["trust_levels"]


def check(applicant: dict, job: dict, applicant_rank: str, job_rank: str, *,
          stretch_open: int = 0) -> tuple[bool, str | None, bool]:
    """Returns (eligible, reason_code, is_stretch)."""
    if applicant.get("fraud_state", "Clear") not in ("Clear", "Watch"):
        return False, "ACCOUNT_RESTRICTED", False
    if job.get("status") != "published":
        return False, "JOB_CLOSED", False

    gap = RANK[job_rank] - RANK[applicant_rank]   # positive = job harder than capability
    stretch = gap > 0

    if gap > ELIG["stretch_max_tiers_above_difficulty"]:
        return False, "CAPABILITY_BELOW_FLOOR", stretch

    if stretch:
        conf = applicant.get("confidence_tier", "Provisional")
        if CONF_ORDER.index(conf) < CONF_ORDER.index(ELIG["stretch_requires_confidence"]):
            return False, "STRETCH_EVIDENCE_INSUFFICIENT", True
        trust = applicant.get("trust_level", "Unverified")
        if TRUST_ORDER.index(trust) < TRUST_ORDER.index(ELIG["stretch_min_trust"]):
            return False, "STRETCH_EVIDENCE_INSUFFICIENT", True
        if stretch_open >= ELIG["stretch_open_max"]:
            return False, "STRETCH_QUOTA", True

    held = set(applicant.get("credentials", []))
    required = set(job.get("credentials_required", []))
    missing = required - held
    if missing:
        return False, f"MISSING_REQUIRED_CREDENTIAL:{sorted(missing)[0]}", stretch

    if applicant.get("availability_hours", 0) < job.get("commitment_hours", 0):
        return False, "COMMITMENT_INCOMPATIBLE", stretch

    app_types = set(applicant.get("contract_types", []))
    if job.get("contract_type") not in app_types:
        return False, "CONTRACT_TYPE_INCOMPATIBLE", stretch

    if job.get("location_rule") == "same_country" and \
       applicant.get("country") != job.get("country", ""):
        return False, "LOCATION_RESTRICTED", stretch

    if applicant.get("min_comp", 0) > job.get("comp_max", 0):
        return False, "COMP_INCOMPATIBLE", stretch

    return True, None, stretch


def eligibility_matrix(applicant_rank: str) -> list[dict]:
    """9-cell row for the explorer UI: which job tiers can this capability pursue?"""
    out = []
    for job_tier in _t.ORDER:
        gap = RANK[job_tier] - RANK[applicant_rank]
        if gap < 0:
            state = "eligible"
        elif gap == 0:
            state = "eligible"
        elif gap == ELIG["stretch_max_tiers_above_difficulty"]:
            state = "stretch"
        else:
            state = "blocked"
        out.append({"job_tier": job_tier, "state": state})
    return out
