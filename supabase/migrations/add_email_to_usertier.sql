-- Email on usertier for admin visibility (see who each user is at a glance).
-- NOTE: the live table is `usertier` (SQLModel lowercase class name) — the
-- old hand-written `user_tiers` was dropped in fix_credit_tables.sql.

ALTER TABLE public.usertier ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';

-- Backfill existing rows from Supabase auth.users.
UPDATE public.usertier u
SET email = au.email
FROM auth.users au
WHERE au.id::text = u.user_id
  AND u.email = '';

-- Auto-fill email for NEW rows (webhook, checkout, or admin topup all create
-- UserTier rows with only user_id — the trigger fills in the email).
CREATE OR REPLACE FUNCTION public.usertier_set_email()
RETURNS TRIGGER AS $$
BEGIN
  NEW.email := COALESCE(
    (SELECT email FROM auth.users WHERE id::text = NEW.user_id),
    NEW.email
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usertier_set_email ON public.usertier;
CREATE TRIGGER trg_usertier_set_email
BEFORE INSERT ON public.usertier
FOR EACH ROW EXECUTE FUNCTION public.usertier_set_email();
