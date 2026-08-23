"""The full 9×9 capability × difficulty matrix — blueprint invariant, correction C1."""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.eligibility import check
from engines.tiers import RANK

ORDER = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]

BASE_APP = dict(fraud_state="Clear", status_ok=True, availability_hours=40,
                contract_types=["contract", "part-time", "full-time"],
                credentials=[], min_comp=0, country="PH",
                confidence_tier="Verified", trust_level="Highly Verified")
BASE_JOB = dict(status="published", commitment_hours=40, contract_type="contract",
                credentials_required=[], location_rule="any", comp_max=99999)


def expected(at, jt):
    d = RANK[jt] - RANK[at]
    if d <= 0:
        return "eligible"
    if d == 1:
        return "stretch"
    return "blocked"


@pytest.mark.parametrize("at,jt", list(itertools.product(ORDER, ORDER)))
def test_capability_floor_matrix(at, jt):
    ok, code, stretch = check(dict(BASE_APP), dict(BASE_JOB), at, jt)
    want = expected(at, jt)
    if want == "eligible":
        assert ok and not stretch
    elif want == "stretch":
        assert ok and stretch
    else:
        assert not ok and code == "CAPABILITY_BELOW_FLOOR"


def test_stretch_requires_confidence_and_identity():
    app = {**BASE_APP, "confidence_tier": "Low", "trust_level": "Identity"}
    ok, code, _ = check(app, dict(BASE_JOB), "B", "A")
    assert not ok and code == "STRETCH_EVIDENCE_INSUFFICIENT"
    app2 = {**BASE_APP, "trust_level": "Email"}
    ok2, code2, _ = check(app2, dict(BASE_JOB), "B", "A")
    assert not ok2 and code2 == "STRETCH_EVIDENCE_INSUFFICIENT"


def test_stretch_quota():
    for i in range(2):
        ok, _, s = check(dict(BASE_APP), dict(BASE_JOB), "B", "A", stretch_open=i)
        assert ok and s
    ok, code, s = check(dict(BASE_APP), dict(BASE_JOB), "B", "A", stretch_open=2)
    assert not ok and code == "STRETCH_QUOTA" and s


@pytest.mark.parametrize("field,bad_code,job_patch,app_patch", [
    ("credentials", "MISSING_REQUIRED_CREDENTIAL",
     {"credentials_required": ["CAMS"]}, {}),
    ("commitment", "COMMITMENT_INCOMPATIBLE",
     {"commitment_hours": 50}, {}),
    ("contract_type", "CONTRACT_TYPE_INCOMPATIBLE",
     {"contract_type": "full-time"}, {"contract_types": ["contract"]}),
    ("location", "LOCATION_RESTRICTED",
     {"location_rule": "same_country", "country": "US"}, {}),
    ("comp", "COMP_INCOMPATIBLE",
     {"comp_max": 100}, {"min_comp": 500}),
])
def test_hard_rules(field, bad_code, job_patch, app_patch):
    job = {**BASE_JOB, **job_patch}
    app = {**BASE_APP, **app_patch}
    ok, code, _ = check(app, job, "A", "B")   # same-tier: no stretch noise
    assert not ok and code.split(":")[0] == bad_code


def test_suspended_and_closed():
    ok, code, _ = check({**BASE_APP, "fraud_state": "Suspended"}, dict(BASE_JOB), "A", "B")
    assert not ok and code == "ACCOUNT_RESTRICTED"
    ok2, code2, _ = check(dict(BASE_APP), {**BASE_JOB, "status": "closed"}, "A", "B")
    assert not ok2 and code2 == "JOB_CLOSED"
