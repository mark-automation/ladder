import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines import matching as m


def test_match_weights_sum_to_one():
    assert abs(sum(m.W.values()) - 1.0) < 1e-9


APP = dict(skills=[{"skill": "Python", "level": "expert"},
                   {"skill": "PostgreSQL", "level": "proficient"},
                   {"skill": "AWS", "level": "working"}],
           domains=["software"], availability_hours=40, min_comp=6000,
           tz_offset=0, preferred_min_tier="B", preferred_max_tier="S")
JOB = dict(skills_required=[{"skill": "Python", "min_level": "proficient"},
                            {"skill": "PostgreSQL", "min_level": "working"},
                            {"skill": "AWS", "min_level": "familiar"}],
           domain="software", commitment_hours=40, comp_min=7000, comp_max=10000,
           tz_offset=0)
CO = {"id": 1}


def test_perfect_alignment_is_strong_or_better():
    r = m.score_match(APP, JOB, CO, "B", "B", "A")
    assert r["match_class"] in ("Strong", "Exceptional")
    assert any("3/3" in x for x in r["reasons"])


def test_skill_gaps_lower_class():
    weak = {**APP, "skills": [{"skill": "CSS", "level": "familiar"}]}
    r = m.score_match(weak, JOB, CO, "B", "B", "C")
    assert r["match_score"] < 0.55
    assert r["match_class"] in ("Poor", "Possible")


def test_overqualification_penalized_but_less_than_under():
    over = m.score_match(APP, JOB, CO, "S", "B", "C")
    under = m.score_match({**APP, "confidence_tier": "Moderate"}, JOB, CO, "D", "SS", "C")
    assert over["match_score"] > under["match_score"]


def test_comp_below_minimum_zeroes_alignment():
    poor_pay = {**JOB, "comp_max": 3000}
    r = m.score_match(APP, poor_pay, CO, "B", "B", "A")
    assert r["match_score"] < 0.85


def test_timezone_modifier():
    far = m.score_match({**APP, "tz_offset": 11}, {**JOB, "tz_offset": -8}, CO, "B", "B", "A")
    near = m.score_match(APP, JOB, CO, "B", "B", "A")
    assert far["match_score"] < near["match_score"]


def test_class_thresholds_monotonic():
    scores = [0.0, 0.45, 0.6, 0.75, 0.9]
    classes = [m.class_for(s) for s in scores]
    order_idx = [m.TIERS["match_classes"].index(next(
        c for c in m.TIERS["match_classes"] if c["label"] == cl)) for cl in classes]
    assert order_idx == sorted(order_idx, reverse=True)  # list is best-first
