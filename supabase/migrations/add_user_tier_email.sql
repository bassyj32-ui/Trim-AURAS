-- Stamp the sign-in email on the UserTier row so the admin dashboard can
-- show real emails (the DB has no separate auth table). Populated lazily by
-- app.quotas.touch_user() on every authenticated request; backfill from the
-- legacy user_id -> email mapping if the admin set it (manual, optional).

ALTER TABLE user_tiers ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';