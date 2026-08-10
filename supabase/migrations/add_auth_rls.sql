-- Enable Row Level Security + auth.uid() policies for per-user isolation.
--
-- The Modal backend connects with the postgres superuser role (via the
-- Supavisor pooler), which bypasses RLS — these policies are defense-in-
-- depth so that direct client access (anyone holding the anon/publishable
-- key) can only see rows owned by the signed-in user.

ALTER TABLE public.job ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.videoclip ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pushsubscription ENABLE ROW LEVEL SECURITY;

-- job: users see/touch only their own rows
CREATE POLICY job_select_own ON public.job
  FOR SELECT USING (user_id = auth.uid()::text);
CREATE POLICY job_insert_own ON public.job
  FOR INSERT WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY job_update_own ON public.job
  FOR UPDATE USING (user_id = auth.uid()::text)
  WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY job_delete_own ON public.job
  FOR DELETE USING (user_id = auth.uid()::text);

-- videoclip: ownership follows its parent job
CREATE POLICY clip_select_own ON public.videoclip
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.job
            WHERE job.id = videoclip.job_id AND job.user_id = auth.uid()::text)
  );
CREATE POLICY clip_insert_own ON public.videoclip
  FOR INSERT WITH CHECK (
    EXISTS (SELECT 1 FROM public.job
            WHERE job.id = videoclip.job_id AND job.user_id = auth.uid()::text)
  );
CREATE POLICY clip_update_own ON public.videoclip
  FOR UPDATE USING (
    EXISTS (SELECT 1 FROM public.job
            WHERE job.id = videoclip.job_id AND job.user_id = auth.uid()::text)
  )
  WITH CHECK (
    EXISTS (SELECT 1 FROM public.job
            WHERE job.id = videoclip.job_id AND job.user_id = auth.uid()::text)
  );
CREATE POLICY clip_delete_own ON public.videoclip
  FOR DELETE USING (
    EXISTS (SELECT 1 FROM public.job
            WHERE job.id = videoclip.job_id AND job.user_id = auth.uid()::text)
  );

-- pushsubscription: no user column — backend-managed only. RLS enabled with
-- zero policies means clients cannot read/write it; the backend's superuser
-- connection is unaffected.
