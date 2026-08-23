-- Ladder MVP schema (subset of blueprint S.2)
CREATE TABLE IF NOT EXISTS applicants (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  headline TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  tz_offset INTEGER NOT NULL DEFAULT 0,
  skills TEXT NOT NULL DEFAULT '[]',            -- [{skill, level}]
  domains TEXT NOT NULL DEFAULT '[]',           -- industry experience tags
  availability_hours INTEGER NOT NULL DEFAULT 40,
  min_comp INTEGER NOT NULL DEFAULT 0,          -- monthly USD expectation floor
  contract_types TEXT NOT NULL DEFAULT '["contract"]',
  credentials TEXT NOT NULL DEFAULT '[]',       -- held certifications
  experience_level TEXT NOT NULL DEFAULT 'mid', -- junior|mid|senior|lead|principal
  leadership_claims TEXT NOT NULL DEFAULT '[]',
  identity_verified INTEGER NOT NULL DEFAULT 0,
  trust_level TEXT NOT NULL DEFAULT 'Unverified',
  fraud_state TEXT NOT NULL DEFAULT 'Clear',
  preferred_min_tier TEXT NOT NULL DEFAULT 'B', -- preference band soft only
  preferred_max_tier TEXT NOT NULL DEFAULT 'S',
  avg_rating REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evidences (
  id INTEGER PRIMARY KEY,
  applicant_id INTEGER NOT NULL REFERENCES applicants(id),
  type TEXT NOT NULL,          -- see rank-applicant-v1 evidence_type_weights
  verified INTEGER NOT NULL DEFAULT 0,
  points INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assessments (
  id INTEGER PRIMARY KEY,
  applicant_id INTEGER NOT NULL REFERENCES applicants(id),
  domain TEXT NOT NULL,
  band TEXT NOT NULL,          -- novice|competent|advanced|expert
  percentile REAL NOT NULL DEFAULT 50
);

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  industry TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  payment_on_time_pct REAL NOT NULL DEFAULT 90,
  satisfaction_avg REAL NOT NULL DEFAULT 4.0,
  completion_rate REAL NOT NULL DEFAULT 90,
  dispute_rate REAL NOT NULL DEFAULT 0.03,
  clarity_score REAL NOT NULL DEFAULT 70,
  response_hours REAL NOT NULL DEFAULT 24,
  comp_fairness REAL NOT NULL DEFAULT 80,
  contracts_completed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'published',   -- draft|published|closed
  authority TEXT NOT NULL,
  scope TEXT NOT NULL,
  complexity_points INTEGER NOT NULL DEFAULT 10,
  skills_required TEXT NOT NULL DEFAULT '[]', -- [{skill, min_level}]
  credentials_required TEXT NOT NULL DEFAULT '[]',
  commitment_hours INTEGER NOT NULL DEFAULT 40,
  duration_months INTEGER NOT NULL DEFAULT 6,
  contract_type TEXT NOT NULL DEFAULT 'contract',
  comp_min INTEGER NOT NULL DEFAULT 0,
  comp_max INTEGER NOT NULL DEFAULT 0,
  benchmark_ratio REAL NOT NULL DEFAULT 1.0,  -- comp midpoint vs local benchmark
  domain TEXT NOT NULL DEFAULT 'software',
  location_rule TEXT NOT NULL DEFAULT 'any',  -- any|same_country
  country TEXT NOT NULL DEFAULT '',
  views_qualified INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  published_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rankings (
  id INTEGER PRIMARY KEY,
  subject_type TEXT NOT NULL,   -- applicant|job|company
  subject_id INTEGER NOT NULL,
  dimension TEXT NOT NULL DEFAULT 'core',
  rank_tier TEXT NOT NULL,
  confidence_tier TEXT NOT NULL DEFAULT 'Provisional',
  internal_score REAL NOT NULL DEFAULT 0,
  percentile REAL,
  evidence_points INTEGER NOT NULL DEFAULT 0,
  model_version TEXT NOT NULL,
  inputs_hash TEXT NOT NULL DEFAULT '',
  previous_tier TEXT,
  status TEXT NOT NULL DEFAULT 'active',      -- active|shadow
  calculated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_rankings_subject ON rankings(subject_type, subject_id, dimension, status);

CREATE TABLE IF NOT EXISTS rank_events (
  id INTEGER PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id INTEGER NOT NULL,
  dimension TEXT NOT NULL DEFAULT 'core',
  previous_tier TEXT,
  new_tier TEXT NOT NULL,
  trigger_type TEXT NOT NULL,   -- INITIAL|EVIDENCE_ADDED|RECALC|CALIBRATION|OVERRIDE
  trigger_ref TEXT NOT NULL DEFAULT '',
  reason_codes TEXT NOT NULL DEFAULT '[]',
  actor TEXT NOT NULL DEFAULT 'system',
  model_version TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  applicant_id INTEGER NOT NULL REFERENCES applicants(id),
  status TEXT NOT NULL DEFAULT 'submitted',   -- submitted|accepted|rejected|interview|offer|withdrawn
  stretch INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(job_id, applicant_id)
);

CREATE TABLE IF NOT EXISTS matches (
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  applicant_id INTEGER NOT NULL REFERENCES applicants(id),
  match_class TEXT NOT NULL,
  match_score REAL NOT NULL,
  reasons TEXT NOT NULL DEFAULT '[]',
  stale INTEGER NOT NULL DEFAULT 0,
  calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (job_id, applicant_id)
);

CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id),
  applicant_id INTEGER NOT NULL REFERENCES applicants(id),
  state TEXT NOT NULL DEFAULT 'active',       -- active|completed|cancelled|disputed
  value_usd INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
