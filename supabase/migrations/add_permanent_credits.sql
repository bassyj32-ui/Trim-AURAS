-- Purchased top-up minutes become a permanent per-user wallet that never
-- expires (instead of sitting in the current month's monthly_usage row and
-- vanishing at month rollover). Backfill any minutes already sitting in the
-- monthly ledger so existing balances are preserved.

ALTER TABLE user_tiers ADD COLUMN IF NOT EXISTS permanent_credits INTEGER NOT NULL DEFAULT 0;

INSERT INTO user_tiers (user_id, tier, permanent_credits, updated_at)
SELECT u.user_id, 'free', SUM(u.topup_credits), now()
FROM monthly_usage u
WHERE u.topup_credits > 0
GROUP BY u.user_id
ON CONFLICT (user_id) DO UPDATE SET
  permanent_credits = user_tiers.permanent_credits + EXCLUDED.permanent_credits;
