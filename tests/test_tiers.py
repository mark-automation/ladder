import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.tiers import ORDER, RANK, tier_distance, capped, tier_from_score, map_confidence
from engines import tiers as T


def test_tier_order():
    assert ORDER == ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]
    assert RANK["F"] == 0 and RANK["SSS"] == 8


def test_distance_and_capping():
    assert tier_distance("A", "S") == 1
    assert tier_distance("S", "B") == -2
    assert capped("SS", "A") == "A"
    assert capped("C", "A") == "C"


def test_job_band_map_edges():
    m = T.TIERS["job"]["map"]
    assert tier_from_score(0, m) == "F"
    assert tier_from_score(19.9, m) == "F"
    assert tier_from_score(20, m) == "E"
    assert tier_from_score(75, m) == "A"
    assert tier_from_score(100, m) == "SSS"


def _conf(points, *, verified=True, assess=True, contracts=6, ident=True):
    return map_confidence(points, has_verified_evidence=verified,
                          has_assessment=assess, contracts_completed=contracts,
                          identity_plus=ident)


def test_confidence_ladder():
    assert _conf(0, verified=False, assess=False, contracts=0, ident=False) == "Provisional"
    assert _conf(15) == "Low"
    assert _conf(30, verified=False) == "Low"          # no verified evidence → Moderate blocked
    assert _conf(50) == "Moderate"
    assert _conf(80, contracts=2) == "High"
    assert _conf(200, contracts=1) == "Moderate"       # contract volume gates High
    assert _conf(200, ident=False) == "High"           # identity blocks Verified only
    assert _conf(200) == "Verified"


def test_confidence_requires_all_high_prereqs():
    assert _conf(90, assess=False) == "Moderate"
    assert _conf(300, contracts=5) == "High"           # Verified needs >=6 contracts
