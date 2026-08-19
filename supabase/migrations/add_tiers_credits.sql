-- Per-user plan tier + monthly allowance ledger for cost-safe pricing.
-- 1 credit = 1 minute of source video (the actual cost driver).

CREATE TABLE IF NOT EXISTS user_tiers (
    user_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL DEFAULT 'free',           -- free | starter | pro
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS monthly_usage (
    user_id TEXT NOT NULL,
    month TEXT NOT NULL,                         -- 'YYYY-MM'
    credits_used INT NOT NULL DEFAULT 0,         -- source minutes of jobs started
    jobs_used INT NOT NULL DEFAULT 0,
    clips_used INT NOT NULL DEFAULT 0,
    topup_credits INT NOT NULL DEFAULT 0,        -- purchased minutes on top of tier allowance
    PRIMARY KEY (user_id, month)
);

-- Probed source duration (drives credit deduction + future cost accounting).
ALTER TABLE job ADD COLUMN IF NOT EXISTS source_seconds integer;
