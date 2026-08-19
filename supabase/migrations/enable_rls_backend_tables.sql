-- Enable RLS (no policies) on backend-managed tables.
--
-- These tables are written/read ONLY by the FastAPI backend, which connects
-- as the postgres role (RLS does not apply to it), so zero policies here =
-- deny-all for the anon/authenticated roles. The frontend never queries them
-- via Supabase REST (no .from() calls), so nothing breaks — this closes the
-- hole where anyone holding the anon key could read/write them directly.

ALTER TABLE public.quotausage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usertier ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monthlyusage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment ENABLE ROW LEVEL SECURITY;
