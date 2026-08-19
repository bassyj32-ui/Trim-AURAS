-- Corrective migration: the app's SQLModel tables use lowercase class
-- names (usertier / monthlyusage), created by create_all. The earlier
-- tiers/Dodo migrations created user_tiers / monthly_usage (with
-- underscores) which the app never reads — so subscription columns and
-- permanent_credits were added to the wrong tables, leaving the live
-- usertier table without them (every tier/usage query would fail).

ALTER TABLE usertier
    ADD COLUMN IF NOT EXISTS subscription_id TEXT,
    ADD COLUMN IF NOT EXISTS subscription_status TEXT,
    ADD COLUMN IF NOT EXISTS period_end TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS permanent_credits INTEGER NOT NULL DEFAULT 0;

-- Move purchased minutes already sitting in the legacy monthly ledger
-- into the permanent wallet, then clear the legacy field.
INSERT INTO usertier (user_id, tier, permanent_credits, updated_at)
SELECT user_id, 'free', SUM(topup_credits), now()
FROM monthlyusage
WHERE topup_credits > 0
GROUP BY user_id
ON CONFLICT (user_id) DO UPDATE SET
    permanent_credits = usertier.permanent_credits + EXCLUDED.permanent_credits,
    updated_at = now();

UPDATE monthlyusage SET topup_credits = 0 WHERE topup_credits > 0;

-- Drop the unused underscore tables the app never uses.
DROP TABLE IF EXISTS user_tiers;
DROP TABLE IF EXISTS monthly_usage;
