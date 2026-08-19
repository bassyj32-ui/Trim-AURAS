-- Scope push subscriptions to their owning user + per-user RLS policy.
--
-- Prior to auth (7.50) the table was intentionally policy-less and the API
-- endpoints were unauthenticated — safe only because RLS-on-zero-policies
-- denies everything. Now every row is owned by a user:
--   * user_id column (pre-auth rows can't be attributed and are pruned)
--   * RLS policy mirrors job/videoclip (auth.uid() scoping)
--   * subscribe/unsubscribe endpoints are auth-gated (app/api/routes.py)
--
-- Run this in the Supabase SQL editor (or psql) BEFORE deploying the app
-- change: SQLModel's create_all does NOT alter existing production tables.

ALTER TABLE public.pushsubscription
  ADD COLUMN IF NOT EXISTS user_id text NOT NULL DEFAULT '';

-- Legacy rows predate auth and can't be attributed — prune them so a stale
-- orphan never receives (or retains) push state.
DELETE FROM public.pushsubscription WHERE user_id = '';

-- Drop any pre-existing policies first so this migration is safe to re-run
-- (CREATE POLICY has no IF NOT EXISTS).
DROP POLICY IF EXISTS sub_select_own ON public.pushsubscription;
DROP POLICY IF EXISTS sub_insert_own ON public.pushsubscription;
DROP POLICY IF EXISTS sub_update_own ON public.pushsubscription;
DROP POLICY IF EXISTS sub_delete_own ON public.pushsubscription;

-- Per-user policies (deny-all for anything else, matching job/videoclip).
CREATE POLICY sub_select_own ON public.pushsubscription
  FOR SELECT USING (user_id = auth.uid()::text);
CREATE POLICY sub_insert_own ON public.pushsubscription
  FOR INSERT WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY sub_update_own ON public.pushsubscription
  FOR UPDATE USING (user_id = auth.uid()::text)
  WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY sub_delete_own ON public.pushsubscription
  FOR DELETE USING (user_id = auth.uid()::text);
