"""Deterministic seed: a believable marketplace spanning F..S.

SS/SSS intentionally empty — rarity is the product (blueprint D/Q).
All ranking rows are COMPUTED by the engines, never hand-assigned.
"""
import json
from db import init_db, ex, q, q1
from engines import applicant_rank as ar
from engines import job_rank as jr
from engines import company_rank as cr
from engines.eligibility import check
from engines import matching as m

CONTRACT_W = ar.RULES["evidence_type_weights"]


def _skills(*pairs):
    return json.dumps([{"skill": s, "level": l} for s, l in pairs])


def _j(v):
    return json.dumps(v)


def seed(conn) -> None:
    if q1(conn, "SELECT id FROM applicants LIMIT 1"):
        return  # idempotent

    companies = [
        # slug name industry country on_time sat compl dispute clarity resp_h comp_fair ncontracts
        ("northwind-labs", "Northwind Labs", "software", "US", 99.2, 4.8, 97.5, 0.01, 95, 3, 92, 120),
        ("halcyon-ai", "Halcyon AI", "ai", "US", 98.0, 4.7, 95.0, 0.02, 90, 5, 88, 34),
        ("datatide", "Datatide Analytics", "software", "UK", 96.0, 4.4, 93.0, 0.04, 82, 10, 80, 62),
        ("verdant", "Verdant Systems", "software", "AU", 94.0, 4.3, 91.0, 0.05, 78, 12, 76, 25),
        ("cobre", "Cobre Digital", "fintech", "PH", 90.0, 4.1, 85.0, 0.07, 70, 20, 72, 8),
        ("gigantorp", "Gigantorp Enterprise", "enterprise", "DE", 71.0, 2.9, 68.0, 0.16, 45, 60, 40, 200),
    ]
    for row in companies:
        ex(conn, """INSERT INTO companies(slug,name,industry,country,payment_on_time_pct,
             satisfaction_avg,completion_rate,dispute_rate,clarity_score,response_hours,
             comp_fairness,contracts_completed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", row)

    jobs = [
        # co title authority scope cx skills creds hrs months ctype cmin cmax ratio domain loc views
        ("northwind-labs", "Senior Backend Engineer", "technical_owner", "product", 18,
         [("Python", "expert"), ("PostgreSQL", "proficient"), ("AWS", "working")], [],
         40, 6, "contract", 8000, 11000, 1.05, "software", "any", 61),
        ("northwind-labs", "Staff Platform Architect", "department_lead", "company_wide", 22,
         [("Go", "proficient"), ("Kubernetes", "proficient"), ("Distributed Systems", "expert")], [],
         40, 12, "contract", 13000, 17000, 1.10, "software", "any", 44),
        ("northwind-labs", "Junior QA Analyst", "individual_contributor", "single_feature", 4,
         [("QA", "working")], [], 20, 3, "contract", 1800, 2600, 0.95, "software", "any", 30),
        ("halcyon-ai", "ML Engineer — LLM Platform", "team_lead", "department", 24,
         [("Python", "expert"), ("PyTorch", "proficient"), ("LLMOps", "proficient"), ("Kubernetes", "working")], [],
         40, 9, "contract", 12000, 16000, 1.08, "ai", "any", 58),
        ("halcyon-ai", "AI Ops Engineer", "technical_owner", "product", 17,
         [("Python", "proficient"), ("Docker", "proficient"), ("LLMOps", "working")], [],
         40, 6, "contract", 8500, 11500, 1.00, "ai", "any", 39),
        ("datatide", "Data Pipeline Engineer", "technical_owner", "product", 15,
         [("Python", "proficient"), ("Airflow", "working"), ("SQL", "proficient")], [],
         40, 6, "contract", 7000, 9500, 0.98, "software", "any", 27),
        ("datatide", "Frontend Developer (React)", "individual_contributor", "single_feature", 9,
         [("React", "proficient"), ("TypeScript", "working")], [],
         30, 4, "contract", 4500, 6500, 0.92, "software", "any", 33),
        ("datatide", "Analytics Team Lead", "team_lead", "department", 19,
         [("SQL", "expert"), ("Leadership", "proficient"), ("Python", "working")], [],
         40, 8, "contract", 9000, 12000, 1.00, "software", "any", 21),
        ("verdant", "Full-Stack Developer", "technical_owner", "product", 13,
         [("TypeScript", "proficient"), ("React", "working"), ("Node.js", "working")], [],
         40, 5, "contract", 5500, 7500, 0.96, "software", "any", 26),
        ("verdant", "DevOps Engineer", "technical_owner", "product", 14,
         [("Docker", "proficient"), ("Terraform", "working"), ("AWS", "proficient")], [],
         35, 5, "contract", 6500, 9000, 1.02, "software", "any", 24),
        ("cobre", "Backend Developer (GCash rails)", "individual_contributor", "single_feature", 11,
         [("Node.js", "proficient"), ("PostgreSQL", "working")], [],
         40, 4, "contract", 3200, 4800, 1.15, "fintech", "same_country", 19),
        ("cobre", "Mobile Developer (React Native)", "individual_contributor", "single_feature", 10,
         [("React Native", "proficient")], [], 30, 4, "part-time", 2400, 3600, 1.05, "fintech", "same_country", 15),
        ("cobre", "Compliance Lead (scope ⚠ underpaid)", "department_lead", "department", 16,
         [("Compliance", "expert"), ("Leadership", "proficient")], ["CAMS"],
         40, 6, "contract", 2200, 3000, 0.52, "fintech", "same_country", 12),
        ("gigantorp", "Enterprise Integration Dev", "individual_contributor", "single_feature", 12,
         [("Java", "proficient"), ("SAP", "working")], [],
         40, 6, "full-time", 5000, 7000, 0.88, "enterprise", "same_country", 28),
        ("gigantorp", "Legacy Migration Lead", "team_lead", "department", 20,
         [("COBOL", "proficient"), ("Leadership", "working"), ("Java", "working")], [],
         40, 12, "full-time", 6000, 8000, 0.70, "enterprise", "same_country", 17),
        ("gigantorp", "Support Engineer", "individual_contributor", "single_feature", 3,
         [("Troubleshooting", "working")], [],
         40, 3, "full-time", 2500, 3500, 1.00, "enterprise", "same_country", 22),
        ("northwind-labs", "Principal Distributed Systems Fellow", "executive", "company_wide", 25,
         [("Distributed Systems", "expert"), ("Go", "expert"), ("Leadership", "expert")], [],
         40, 12, "contract", 20000, 28000, 1.12, "software", "any", 8),
        ("halcyon-ai", "Research Engineer — Alignment", "department_lead", "company_wide", 23,
         [("PyTorch", "expert"), ("RLHF", "proficient"), ("Python", "expert")], [],
         40, 9, "contract", 15000, 22000, 1.06, "ai", "any", 6),
    ]
    for i, j in enumerate(jobs, start=1):
        (slug, title, auth, scope, cx, skills, creds, hrs, months, ctype,
         cmin, cmax, ratio, domain, loc, views) = j
        co = q1(conn, "SELECT id, country FROM companies WHERE slug=?", (slug,))
        ex(conn, """INSERT INTO jobs(id,company_id,title,status,authority,scope,complexity_points,
             skills_required,credentials_required,commitment_hours,duration_months,contract_type,
             comp_min,comp_max,benchmark_ratio,domain,location_rule,country,views_qualified)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           (i, co["id"], title, "published", auth, scope, cx, _skills(*skills), _j(creds),
            hrs, months, ctype, cmin, cmax, ratio, domain, loc, co["country"], views))
    # one draft job for gating tests
    ex(conn, """INSERT INTO jobs(id,company_id,title,status,authority,scope,complexity_points,
         skills_required,credentials_required,commitment_hours,duration_months,contract_type,
         comp_min,comp_max,benchmark_ratio,domain,location_rule,country,views_qualified)
         VALUES (19,1,'Unpublished Secret Role','draft','technical_owner','product',10,'[]','[]',
                 40,6,'contract',5000,8000,1.0,'software','any','US',0)""")

    # ---------------- applicants ----------------
    A = []

    def app(name, headline, country, tz, skills, domains, avail, min_comp, ctypes, creds,
            exp, lead, idver, trust, pref_lo, pref_hi, contracts, rating, evs, assess):
        A.append(dict(name=name, headline=headline, country=country, tz=tz, skills=skills,
                      domains=domains, avail=avail, min_comp=min_comp, ctypes=ctypes,
                      creds=creds, exp=exp, lead=lead, idver=idver, trust=trust,
                      pref=(pref_lo, pref_hi), contracts=contracts, rating=rating,
                      evs=evs, assess=assess))

    E = lambda *items: list(items)  # noqa: E731
    RC = lambda n: [("contract_completed_reviewed", 1)] * n  # noqa: E731

    # S tier (2) — deep evidence, many reviewed completions + repeat success
    app("Maya Santos", "Distributed-systems staff engineer; payments scale",
        "PH", 8, _skills(("Go", "expert"), ("Distributed Systems", "expert"),
                         ("PostgreSQL", "proficient"), ("Kubernetes", "proficient")),
        ["software"], 40, 9000, '["contract"]', [], "principal",
        ["Owned production billing platform", "Led 8-engineer team"],
        True, "Highly Verified", "A", "SSS", 16, 4.8,
        RC(16) + [("repeat_success", 1), ("repeat_success", 1),
                  ("verified_employment", 1), ("assessment", 1), ("portfolio", 1)],
        [("software", "expert", 99)])
    app("Jonas Weber", "Platform architect; migrations & reliability",
        "DE", 1, _skills(("Kubernetes", "expert"), ("Terraform", "proficient"),
                         ("Go", "proficient"), ("AWS", "expert")),
        ["software", "enterprise"], 40, 9500, '["contract"]', [], "lead",
        ["Ran company-wide migration"], True, "Professional", "B", "SS", 15, 4.7,
        RC(15) + [("assessment", 1), ("verified_employment", 1)],
        [("software", "advanced", 98)])

    # A tier (4)
    app("Priya Nair", "Senior backend engineer; fintech APIs", "IN", 5.5,
        _skills(("Python", "expert"), ("PostgreSQL", "proficient"), ("AWS", "proficient")),
        ["fintech", "software"], 40, 6500, '["contract"]', [], "senior",
        ["Owned payments API"], True, "Professional", "B", "S", 9, 4.6,
        RC(9) + [("repeat_success", 1), ("assessment", 1), ("verified_employment", 1)],
        [("software", "advanced", 95)])
    app("Carlo Reyes", "Full-stack lead; PH startups", "PH", 8,
        _skills(("TypeScript", "proficient"), ("React", "proficient"), ("Node.js", "proficient")),
        ["software", "fintech"], 40, 5000, '["contract","part-time"]', [], "senior",
        ["Tech lead, 4-person squad"], True, "Identity", "B", "S", 8, 4.5,
        RC(10) + [("assessment", 1), ("portfolio", 1), ("verified_employment", 1)],
        [("software", "advanced", 93)])
    app("Amara Okafor", "DevOps / SRE; audit-heavy environments", "NG", 1,
        _skills(("Docker", "expert"), ("Terraform", "proficient"), ("AWS", "proficient")),
        ["software"], 35, 6800, '["contract"]', [], "senior",
        ["Production ownership, 99.95% SLO"], True, "Professional", "B", "S", 7, 4.6,
        RC(10) + [("repeat_success", 1), ("assessment", 1)],
        [("software", "advanced", 94)])
    app("Elena Petrova", "ML engineer; recsys & NLP in prod", "RS", 2,
        _skills(("Python", "expert"), ("PyTorch", "proficient"), ("LLMOps", "working")),
        ["ai"], 40, 7200, '["contract"]', [], "senior",
        ["Shipped prod ML to 2M users"], True, "Identity", "B", "SS", 6, 4.5,
        RC(11) + [("assessment", 1), ("portfolio", 1)],
        [("ai", "advanced", 96)])

    # B tier (6) — the backbone
    b_batch = [
        ("Tomás Alvarez", "Product-minded full-stack dev", "MX", -6,
         [("TypeScript", "working"), ("React", "working"), ("Node.js", "working")],
         ["software"], 3800, "mid", [], False, "Identity", 5, 4.4, []),
        ("Grace Kim", "React specialist; design systems", "KR", 9,
         [("React", "proficient"), ("TypeScript", "working")],
         ["software"], 4200, "mid", [], True, "Identity", 5, 4.3, [("portfolio", 1)]),
        ("Ahmed Hassan", "Backend dev; Python/Django", "EG", 2,
         [("Python", "proficient"), ("PostgreSQL", "working")],
         ["software"], 3000, "mid", [], False, "Email", 4, 4.2, []),
        ("Bianca Rossi", "QA automation engineer", "IT", 1,
         [("QA", "proficient"), ("Python", "working")],
         ["software"], 4000, "mid", [], False, "Identity", 4, 4.4, []),
        ("Diego Ferreira", "Mobile dev; React Native focus", "BR", -3,
         [("React Native", "proficient"), ("TypeScript", "working")],
         ["software"], 3400, "mid", [], False, "Email", 3, 4.3, []),
        ("Linh Tran", "Data engineer; pipelines & SQL", "VN", 7,
         [("SQL", "proficient"), ("Python", "working"), ("Airflow", "familiar")],
         ["software"], 3100, "mid", [], True, "Identity", 3, 4.2, []),
    ]
    for nm, hl, ct, tz, skpairs, dm, mc, xp, ld, idv, tr, nc, rt, extra in b_batch:
        nc = max(nc, 6)
        ev = RC(nc) + [("assessment", 1)] \
           + ([("verified_employment", 1)] if tr == "Identity" else [("portfolio", 1)])
        app(nm, hl, ct, tz, _skills(*skpairs), dm, 40, mc,
            '["contract","part-time"]', [], xp, ld, idv, tr, "B", "A", nc, rt,
            ev, [("software", "competent", 78)])

    # C tier (5)
    app("Sam O'Neill", "Junior-mid backend developer", "IE", 0,
        _skills(("Node.js", "working"), ("PostgreSQL", "familiar")), ["software"],
        30, 2200, '["contract","part-time"]', [], "junior", [], False, "Identity",
        "C", "B", 2, 4.1,
        RC(4) + [("assessment", 1), ("portfolio", 1)], [("software", "competent", 72)])
    app("Yuki Tanaka", "Frontend developer; clean UI implementer", "JP", 9,
        _skills(("React", "working"), ("TypeScript", "familiar")), ["software"],
        40, 2400, '["contract","part-time"]', [], "junior", [], True, "Email",
        "C", "B", 2, 4.0,
        RC(4) + [("contract_executed", 1), ("portfolio", 1)], [])
    app("Fatima Al-Sayed", "WordPress→product transition dev", "MA", 1,
        _skills(("JavaScript", "working"), ("React", "familiar")), ["marketing"],
        20, 1600, '["contract","part-time"]', [], "junior", [], False, "Identity",
        "C", "B", 1, 4.2,
        RC(5) + [("portfolio", 1)], [])
    app("Piotr Nowak", "Python automation dev", "PL", 1,
        _skills(("Python", "working")), ["software"], 25, 1900,
        '["contract","part-time"]', [], "junior", [], False, "Unverified",
        "C", "B", 2, 4.0,
        RC(4) + [("contract_executed", 1), ("claim", 1)], [])
    app("Ana García", "Support→backend bootcamp grad", "ES", 1,
        _skills(("Troubleshooting", "proficient"), ("Node.js", "familiar")), [],
        40, 1400, '["contract","part-time","full-time"]', [], "junior", [], False,
        "Email", "C", "B", 1, 4.3,
        RC(5) + [("claim", 1)], [])

    # D/E tier (5)
    app("Omar Farouk", "Self-taught dev; first contracts", "EG", 2,
        _skills(("JavaScript", "familiar")), [], 20, 900,
        '["contract","part-time"]', [], "junior", [], False, "Email",
        "D", "C", 1, 3.9, RC(2) + [("contract_executed", 1)], [])
    app("Nadia Popescu", "CS student; freelance starter", "RO", 2,
        _skills(("Python", "familiar")), [], 15, 700,
        '["contract","part-time"]', [], "junior", [], False, "Email",
        "D", "C", 1, 4.0, RC(3) + [("portfolio", 1)], [])
    app("Kenji Sato", "Career switcher; QA basics", "JP", 9,
        _skills(("QA", "familiar")), [], 20, 1000,
        '["contract","part-time"]', [], "junior", [], False, "Unverified",
        "E", "D", 0, 0.0, RC(1) + [("claim", 1), ("claim", 1)], [])
    app("Lucia Mendez", "Junior designer-developer", "AR", -3,
        _skills(("CSS", "working"), ("React", "familiar")), ["design"], 20, 1100,
        '["contract","part-time"]', [], "junior", [], True, "Email",
        "E", "D", 0, 0.0, RC(1) + [("portfolio", 1)], [])
    app("Ivan Petrov", "Newcomer; strong fundamentals claim", "BG", 2,
        _skills(("Java", "familiar")), [], 30, 1200,
        '["contract","part-time","full-time"]', [], "junior", [], False, "Unverified",
        "E", "D", 0, 0.0, RC(1) + [("claim", 1), ("claim", 1)], [])

    # F tier (2) — assessed but bottom
    app("Copy-Paste Pete", "Aspiring dev", "XX", 0, _skills(("HTML", "familiar")), [],
        40, 400, '["contract"]', [], "junior", [], False, "Unverified",
        "F", "E", 0, 0.0, [("claim", 1)], [("software", "novice", 12)])
    app("Bot Account", "Suspicious profile", "XX", 0,
        _skills(("Everything", "expert")), [], 168, 100, '["contract"]', [],
        "principal", ["CEO of everything"], False, "Unverified",
        "F", "E", 0, 0.0, [("claim", 1)], [("software", "novice", 8)])

    for i, a in enumerate(A, start=1):
        ex(conn, """INSERT INTO applicants(id,name,headline,country,tz_offset,skills,domains,
             availability_hours,min_comp,contract_types,credentials,experience_level,
             leadership_claims,identity_verified,trust_level,fraud_state,
             preferred_min_tier,preferred_max_tier,avg_rating)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           (i, a["name"], a["headline"], a["country"], a["tz"], a["skills"], _j(a["domains"]),
            a["avail"], a["min_comp"], a["ctypes"], _j(a["creds"]), a["exp"], _j(a["lead"]),
            int(a["idver"]), a["trust"], "Clear", a["pref"][0], a["pref"][1], a["rating"]))
        for t, v in a["evs"]:
            w = CONTRACT_W[t]
            ex(conn, "INSERT INTO evidences(applicant_id,type,verified,points,note) VALUES (?,?,?,?,?)",
               (i, t, v, w, ""))
        for d, b, p in a["assess"]:
            ex(conn, "INSERT INTO assessments(applicant_id,domain,band,percentile) VALUES (?,?,?,?)",
               (i, d, b, p))
        if a["contracts"]:
            for _ in range(a["contracts"]):
                ex(conn, """INSERT INTO contracts(job_id,applicant_id,state,value_usd,completed_at)
                     VALUES (3,?,'completed',2500,datetime('now'))""", (i,))

    compute_all_rankings(conn)
    refresh_matches(conn)


# ---------------------------------------------------------------- rankings ---

def jloads_(s, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def applicant_context(row) -> dict:
    d = dict(row)
    d["skills"] = jloads_(d.get("skills", "[]"), [])
    d["domains"] = jloads_(d.get("domains", "[]"), [])
    d["contract_types"] = jloads_(d.get("contract_types", "[]"), [])
    d["credentials"] = jloads_(d.get("credentials", "[]"), [])
    d["leadership_claims"] = jloads_(d.get("leadership_claims", "[]"), [])
    return d


def job_context(row) -> dict:
    d = dict(row)
    d["skills_required"] = jloads_(d.get("skills_required", "[]"), [])
    d["credentials_required"] = jloads_(d.get("credentials_required", "[]"), [])
    return d


def current_tier(conn, stype, sid):
    r = q1(conn, """SELECT rank_tier FROM rankings WHERE subject_type=? AND subject_id=?
                    AND dimension='core' AND status='active'""", (stype, sid))
    return r["rank_tier"] if r else None


def current_ranking(conn, stype, sid):
    r = q1(conn, """SELECT * FROM rankings WHERE subject_type=? AND subject_id=?
                    AND dimension='core' AND status='active'""", (stype, sid))
    return dict(r) if r else None


def save_ranking(conn, stype, sid, rec, actor, trigger, inputs: dict) -> bool:
    """Upsert active ranking; emit immutable rank_event iff the tier changed."""
    import hashlib
    prev = current_tier(conn, stype, sid)
    ih = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    existing = q1(conn, """SELECT id FROM rankings WHERE subject_type=? AND subject_id=?
                           AND dimension='core' AND status='active'""", (stype, sid))
    conf = rec.get("confidence_tier", "Moderate")
    if existing:
        ex(conn, """UPDATE rankings SET rank_tier=?, confidence_tier=?, internal_score=?,
             percentile=?, evidence_points=?, model_version=?, inputs_hash=?, previous_tier=?,
             calculated_at=datetime('now') WHERE id=?""",
           (rec["rank_tier"], conf, rec["internal_score"], rec.get("percentile"),
            rec.get("evidence_points", 0), rec["model_version"], ih, prev or rec["rank_tier"],
            existing["id"]))
    else:
        ex(conn, """INSERT INTO rankings(subject_type,subject_id,dimension,rank_tier,
             confidence_tier,internal_score,percentile,evidence_points,model_version,
             inputs_hash,previous_tier,status)
             VALUES (?,?,'core',?,?,?,?,?,?,?,?,'active')""",
           (stype, sid, rec["rank_tier"], conf, rec["internal_score"], rec.get("percentile"),
            rec.get("evidence_points", 0), rec["model_version"], ih, prev or rec["rank_tier"]))
    changed = prev != rec["rank_tier"]
    if changed:
        ex(conn, """INSERT INTO rank_events(subject_type,subject_id,previous_tier,new_tier,
             trigger_type,trigger_ref,reason_codes,actor,model_version)
             VALUES (?,?,?,?,?,?,?,?,?)""",
           (stype, sid, prev, rec["rank_tier"], trigger, f"recalc:{stype}:{sid}",
            json.dumps(rec.get("reason_codes", [])), actor, rec["model_version"]))
    return changed


def compute_all_rankings(conn, actor: str = "system", trigger: str = "INITIAL") -> dict:
    changes = {"applicants": 0, "jobs": 0, "companies": 0}

    apps = [applicant_context(r) for r in q(conn, "SELECT * FROM applicants")]
    # pass 1: raw scores → cohort distribution for percentile caps
    prepared = []
    for a in apps:
        evs = [dict(e) for e in q(conn, "SELECT * FROM evidences WHERE applicant_id=?", (a["id"],))]
        ass = [dict(x) for x in q(conn, "SELECT * FROM assessments WHERE applicant_id=?", (a["id"],))]
        nc = q1(conn, "SELECT COUNT(*) n FROM contracts WHERE applicant_id=? AND state='completed'",
                (a["id"],))["n"]
        rec = ar.rank_applicant(a, evs, ass, contracts_completed=nc,
                                avg_rating=a.get("avg_rating", 0.0))
        prepared.append((a, evs, ass, nc, rec))
    cohort = [p[4]["internal_score"] for p in prepared]
    # pass 2: final rec with cohort percentiles applied
    for a, evs, ass, nc, _ in prepared:
        rec = ar.rank_applicant(a, evs, ass, contracts_completed=nc,
                                avg_rating=a.get("avg_rating", 0.0),
                                cohort_scores=cohort,
                                previous_tier=current_tier(conn, "applicant", a["id"]))
        if save_ranking(conn, "applicant", a["id"], rec, actor, trigger, a):
            changes["applicants"] += 1

    for j in q(conn, "SELECT * FROM jobs"):
        rec = jr.rank_job(dict(j))
        if save_ranking(conn, "job", j["id"], rec, actor, trigger, dict(j)):
            changes["jobs"] += 1

    for c in q(conn, "SELECT * FROM companies"):
        rec = cr.rank_company(dict(c))
        if save_ranking(conn, "company", c["id"], rec, actor, trigger, dict(c)):
            changes["companies"] += 1

    refresh_matches(conn)
    return changes


# ----------------------------------------------------------------- matches ---

def refresh_matches(conn) -> int:
    ex(conn, "DELETE FROM matches")
    apps = {r["id"]: applicant_context(r) for r in q(conn, "SELECT * FROM applicants")}
    ranks = {}
    for sid, a in apps.items():
        r = current_ranking(conn, "applicant", sid)
        if r:
            ranks[sid] = r
            a["confidence_tier"] = r["confidence_tier"]
    cos = {r["id"]: dict(r) | {"tier": current_tier(conn, "company", r["id"]) or "F"}
           for r in q(conn, "SELECT * FROM companies")}
    count = 0
    stretch_open: dict[int, int] = {}
    for j in q(conn, "SELECT * FROM jobs WHERE status='published' ORDER BY id"):
        jd = job_context(j)
        job_rank = current_tier(conn, "job", jd["id"]) or "C"
        co = cos[jd["company_id"]]
        for sid, a in apps.items():
            if sid not in ranks:
                continue
            ok, code, stretch = check(a, jd, ranks[sid]["rank_tier"], job_rank,
                                      stretch_open=stretch_open.get(sid, 0))
            if not ok:
                continue
            mm = m.score_match(a, jd, co, ranks[sid]["rank_tier"], job_rank, co["tier"])
            if stretch:
                stretch_open[sid] = stretch_open.get(sid, 0) + 1
            ex(conn, """INSERT OR REPLACE INTO matches(job_id,applicant_id,match_class,
                 match_score,reasons) VALUES (?,?,?,?,?)""",
               (jd["id"], sid, mm["match_class"], mm["match_score"],
                json.dumps(mm["reasons"])))
            count += 1
    return count


if __name__ == "__main__":
    conn_ = __import__("db").connect()
    init_db(conn_)
    seed(conn_)
    print("seeded:", q1(conn_, "SELECT COUNT(*) n FROM applicants")["n"], "applicants,",
          q1(conn_, "SELECT COUNT(*) n FROM jobs")["n"], "jobs,",
          q1(conn_, "SELECT COUNT(*) n FROM matches")["n"], "match rows")
