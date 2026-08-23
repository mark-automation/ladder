"""Ranking audit trail + model versioning invariants (blueprint §R, §50)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_every_ranking_has_model_version(api_client=None):
    import db as dbm, main
    rows = dbm.q(main.conn, "SELECT * FROM rankings")
    assert rows
    for r in rows:
        assert r["model_version"].startswith(("rank-applicant", "rank-job", "rank-company"))


def test_initial_seed_writes_rank_events(api):
    import db as dbm, main
    n = dbm.q1(main.conn, "SELECT COUNT(*) n FROM rank_events")["n"]
    assert n >= 49                      # one INITIAL event per ranked subject


def test_events_are_append_only_shape(api):
    import db as dbm, main
    ev = dbm.q1(main.conn, """SELECT previous_tier, new_tier, trigger_type, actor,
                              model_version FROM rank_events LIMIT 1""")
    assert ev is not None
    for col in ("new_tier", "trigger_type", "actor", "model_version"):
        assert ev[col]


def test_recompute_is_stable_no_mass_movement(api):
    import db as dbm, main, seed as S
    before = {r["subject_type"] + str(r["subject_id"]): r["rank_tier"]
              for r in dbm.q(main.conn, "SELECT * FROM rankings WHERE status='active'")}
    S.compute_all_rankings(main.conn, actor="test", trigger="RECALC")
    after = {r["subject_type"] + str(r["subject_id"]): r["rank_tier"]
             for r in dbm.q(main.conn, "SELECT * FROM rankings WHERE status='active'")}
    diff = [k for k in before if before[k] != after.get(k)]
    assert not diff, f"deterministic recompute moved tiers: {diff}"


def test_sss_population_is_rare_or_empty(api):
    import db as dbm, main
    sss = dbm.q1(main.conn, """SELECT COUNT(*) n FROM rankings WHERE status='active'
                               AND rank_tier='SSS'""")["n"]
    total = dbm.q1(main.conn, "SELECT COUNT(*) n FROM rankings WHERE status='active'")["n"]
    assert sss / total <= 0.003         # blueprint invariant: SSS must stay rare
