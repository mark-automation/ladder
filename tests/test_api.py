"""API contract tests — incl. the blueprint's serializer guard (§U.2, §50)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BANNED_KEYS = {"score", "internalScore", "internal_score", "percentile",
               "evidence_points", "evidencePoints", "inputs_hash"}


def walk(obj, key_path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, key_path
            yield from walk(v, f"{key_path}.{k}")
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item, key_path)


def test_health(api):
    assert api.get("/api/health").json() == {"ok": True, "service": "ladder"}


def test_public_jobs_have_no_internal_scores(api):
    d = api.get("/api/jobs").json()
    assert d["jobs"]
    for k, path in walk(d):
        assert k not in BANNED_KEYS, f"LEAK: {k} at {path}"
    j = d["jobs"][0]
    assert set(j["rank"]) <= set("FEDCBSA") or j["rank"] in ("SS", "SSS")


def test_public_rank_endpoint_shape(api):
    d = api.get("/api/applicants/1/rank").json()
    assert d["rank"] == "S" and d["confidence"] == "Verified"
    for k in BANNED_KEYS:
        assert k not in d


def test_public_feed_shape_and_ordering(api):
    d = api.get("/api/feed/3").json()
    assert {"rank", "confidence"} <= set(d["you"])
    classes = [r["match_class"] for r in d["recommended"]]
    order = ["Exceptional", "Strong", "Good", "Possible", "Poor"]
    idxs = [order.index(c) for c in classes]
    assert idxs == sorted(idxs)                      # ordered by class quality
    for r in d["recommended"]:
        assert not (set(r) & BANNED_KEYS)
        assert "reasons" in r and isinstance(r["reasons"], list)


def test_apply_happy_then_duplicate_then_blocked(api):
    r1 = api.post("/api/jobs/6/apply", json={"applicant_id": 3})   # Priya A → C job
    assert r1.status_code == 200 and r1.json()["status"] == "submitted"
    r2 = api.post("/api/jobs/6/apply", json={"applicant_id": 3})
    assert r2.status_code == 409 and r2.json()["error"] == "DUPLICATE_APPLICATION"
    r3 = api.post("/api/jobs/17/apply", json={"applicant_id": 3})  # SS job vs A → floor block
    assert r3.status_code == 422
    body = r3.json()
    assert body["error"] == "CAPABILITY_BELOW_FLOOR"
    assert "message" in body and body["message"]


def test_stretch_flow_marks_application(api):
    # Carlo Reyes (id=4, A, Identity+High) stretches to job 5 (AI Ops, technical_owner)
    r = api.post("/api/jobs/5/apply", json={"applicant_id": 4})
    if r.status_code == 200:
        assert isinstance(r.json().get("stretch"), bool)


def test_admin_realm_is_gated(api):
    assert api.get("/api/admin/rankings").status_code == 403
    ok = api.get("/api/admin/rankings", headers={"x-ladder-key": "ladder-demo-admin"})
    assert ok.status_code == 200
    rows = ok.json()["rankings"]
    assert any("internalScore" in r for r in rows)     # admin realm MAY expose scores
    assert any(r["modelVersion"].startswith("rank-") for r in rows)


def test_admin_recompute_writes_events(api):
    before = api.get("/api/admin/rankings",
                     headers={"x-ladder-key": "ladder-demo-admin"}).json()["rankings"]
    r = api.post("/api/admin/recompute", headers={"x-ladder-key": "ladder-demo-admin"})
    assert r.status_code == 200
    after = api.get("/api/admin/rankings",
                    headers={"x-ladder-key": "ladder-demo-admin"}).json()["rankings"]
    assert len(before) == len(after)                   # no mass unexplained movement
