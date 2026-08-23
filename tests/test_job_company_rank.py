import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines import job_rank as jr
from engines import company_rank as cr


def test_job_rubric_anchors():
    low = jr.rank_job(dict(authority="individual_contributor", scope="single_feature",
                           complexity_points=3, benchmark_ratio=1.0, views_qualified=99))
    assert low["rank_tier"] == "F"
    high = jr.rank_job(dict(authority="executive", scope="company_wide",
                            complexity_points=25, benchmark_ratio=1.1, views_qualified=99))
    assert high["internal_score"] == 100.0
    assert high["rank_tier"] == "SSS"


def test_sss_held_without_real_demand():
    j = dict(authority="executive", scope="company_wide", complexity_points=25,
             benchmark_ratio=1.2, views_qualified=8)
    rec = jr.rank_job(j)
    assert rec["rank_tier"] == "SS"                       # anti-inflation hold
    assert any("sss_held" in c for c in rec["reason_codes"])
    j["views_qualified"] = 60
    assert jr.rank_job(j)["rank_tier"] == "SSS"


def test_comp_mismatch_flag_and_penalty():
    ok = jr.rank_job(dict(authority="team_lead", scope="department", complexity_points=15,
                          benchmark_ratio=0.9, views_qualified=10))
    bad = jr.rank_job(dict(authority="team_lead", scope="department", complexity_points=15,
                           benchmark_ratio=0.5, views_qualified=10))
    assert ok["internal_score"] > bad["internal_score"]
    assert not any("comp_below" in c for c in ok["reason_codes"])
    assert any("comp_significantly_below" == c for c in bad["reason_codes"])


def _co(**kw):
    base = dict(payment_on_time_pct=98, satisfaction_avg=4.6, completion_rate=95,
                dispute_rate=0.02, clarity_score=90, response_hours=4,
                comp_fairness=90, contracts_completed=100)
    base.update(kw)
    return base


def test_excellent_veteran_reaches_S():
    rec = cr.rank_company(_co())
    assert rec["rank_tier"] == "S"


def test_provisional_cap_B_for_new_companies():
    rec = cr.rank_company(_co(contracts_completed=5))
    assert rec["confidence_tier"] == "Provisional"
    from engines.tiers import RANK
    assert RANK[rec["rank_tier"]] <= RANK["B"]


def test_big_terrible_company_capped_low():
    rec = cr.rank_company(_co(payment_on_time_pct=65, satisfaction_avg=2.6,
                              completion_rate=60, dispute_rate=0.20,
                              clarity_score=35, response_hours=70,
                              comp_fairness=30, contracts_completed=500))
    from engines.tiers import RANK
    assert RANK[rec["rank_tier"]] <= RANK["D"]


def test_volume_gates_bind_even_with_perfect_scores():
    perfect_new = _co(payment_on_time_pct=100, satisfaction_avg=5, completion_rate=100,
                      dispute_rate=0, clarity_score=100, response_hours=0,
                      comp_fairness=100, contracts_completed=10)
    rec = cr.rank_company(perfect_new)
    from engines.tiers import RANK
    assert RANK[rec["rank_tier"]] <= RANK["B"]   # needs n>=75 for S regardless of quality
