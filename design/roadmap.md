# TrimAURA Roadmap — pending parts

Current state: desktop shell + mobile/PWA polish + full offline shell ported to the real app (public/index.html + styles.css + service-worker.js + manifest.json), verified at 360px + 1366px. Mocks that define the spec: `public/desktop-mock.html`, `public/mobile-mock.html`.

## Next parts (chosen in order, rest deferred by user for later sessions)

1. **Real-flow polish** — ✅ DONE (2026-08-10): empty-state cards (results / vault / styles), error-variant toast on 7 failure paths, aria-labels on all 11 form fields, closed drawers hidden from the AX tree. Verified at 390px + 1366px via snapshots/evaluate_script. Remaining: live upload → generate → clip-drawer test once the sandbox has network to the dev server / Modal backend.
2. **Auth + payments integration** — **Auth part ✅ DONE — deployed LIVE (2026-08-11)**. Supabase Auth (Google OAuth only) is running on https://bassyj32--trimaura-fastapi-app.modal.run.
   - **Backend**: `app/auth.py` JWT verification gate (`Depends(get_current_user)`) on every protected `/api` route; `job.user_id` stamped + filtered per user; ownership helpers (`_owned_job`/`_owned_clip`, 404 on foreign rows); legacy claim `POST /api/claim-legacy`.
   - **DB/RLS**: migration `supabase/migrations/add_auth_rls.sql` — RLS enabled on `job`/`videoclip`/`pushsubscription` with `auth.uid()` policies (clips follow the parent job). **Verified live**: anon-key REST query on `job` and `videoclip` returns `[]` (zero rows visible without a token); signed-in users only see their own rows.
   - **Frontend**: `public/auth.js` — sign-in modal, account chip with real name/avatar, fetch+XHR `Authorization` injection, guest write-block, sync token read at boot + silent refresh/retry on 401; vault shows a "Sign in to see your clips" CTA for guests instead of a false server-offline error; SW v11 precaches `auth.js`.
   - **Google OAuth**: client ID/secret configured in Google Console + Supabase dashboard; Site URL + redirect allow list = modal.run; provider verified live (authorize URL → Google login page).
   - **Deployment**: `modal deploy modal_app.py` (CLI available via `python -m modal`); live `/api/jobs` → **401** without a token (was returning full list on the stale deploy).
   - **Ownership**: legacy `user_id='default'` rows (88 jobs / 182 clips) claimed and re-assigned to the owner account **bassyjmin@gmail.com** (admin). A friend account (mintesnotamare@gmail.com) that grabbed the initial claim was emptied via SQL transfer. Zero `default` rows remain; all data belongs to the admin account.
   - UX bugfixes (Phase 7.5a, commit `5f0637d`): fixed "session expired" modal (silent refresh + retry) and false "server offline / try again" (401-aware vault).
   - **Payments part pending** (Stripe checkout on the Upgrade/plans shells) — needs a backend / external-service decision (breaks the zero-backend rule).
3. **PWA depth** — ✅ DONE (2026-08-10, SW now v11): SW offline shell (precache `/`, `index.html`, `clip.html`, `auth.js`, styles, icons; network-first navigation with cached fallback; stale-while-revalidate assets), upgraded manifest (id/scope/categories/display_override + purpose icons), offline banner + online/offline JS, SW update loop (30-min + on-focus, `updateViaCache:none`), appinstalled toast, error-variant toast + graceful backend-offline states on all API failure paths, iOS install hints (apple-touch metas, PWA install sheet with share-sheet instructions, one-time hint toast), splash-*.png assets generated. Verified at 360px + 1366px via a11y snapshots + evaluate_script — incl. CDP Offline emulation (banner appears; reload serves the cached shell). Remaining: live push subscription once `/api/push/*` + a push service are reachable from the sandbox.
4. **Content features** — more template styles, SEO caption editor, posting flows (auto-open YouTube Shorts / TikTok / IG with caption copied).

## Constraints
- Frontend-only polish must NOT change `app/main.py` (static server) or the Modal backend.
- Browser verification must use a11y snapshots + evaluate_script only — no screenshots.
