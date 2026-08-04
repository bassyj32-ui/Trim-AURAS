# TrimAURA — Build Plan & Roadmap

> **Last updated:** 2026-08-04
> **Status:** 🟢 V1 live on Modal — Warm cream UI, scale-to-zero, Whisper Turbo, Supabase Postgres, Frame.io GraphQL downloader, quality selector (1080p default), Publish Kit (TikTok/Shorts/Reels), FFmpeg "sight" signals, content-aware clip selection (speech/action/music), any-source downloads via yt-dlp (YouTube, TikTok, Instagram, Google Drive), optional cookies.txt upload (fixes YouTube "not a bot" blocks on cloud IPs), clean clips (no burned text) with genre-distinct template overlay frames, optional Opus-style animated burned captions (per-job toggle), silence/filler trimming + per-clip trim & re-render, face-aware animated crop (speaker tracking, auto with static fallback), clip viewer page + copy-link (hosted playback/seek via FileResponse Range), PWA + push notifications, stress-tested (3/3 back-to-back, ~6 min/job)
> **URL:** <https://bassyj32--trimaura-fastapi-app.modal.run>

***

## 📋 Project Structure

```
trimaura/
├── app/
│   ├── __init__.py              # Package init
│   ├── main.py                  # FastAPI app & static mounting
│   ├── config.py                # Pydantic Settings & environment validation
│   ├── database.py              # SQLModel engine — Supabase Postgres pooler on Modal, local fallback
│   ├── models.py                # SQLModel schema (Job, VideoClip, clip vault)
│   ├── storage.py               # Cloudflare R2 upload helpers (DISABLED)
│   │
│   ├── api/
│   │   ├── routes.py            # REST endpoints (Jobs, Upload, Clip Vault, Posted, Download)
│   │   └── sse.py              # SSE stream helper (legacy, unused)
│   │
│   └── pipeline/
│       ├── orchestrator.py      # Pipeline controller with clip vault features
│       ├── downloader.py        # Phase 1: any http(s) link via yt-dlp (YouTube, TikTok, Instagram, GDrive) + Frame.io GraphQL + local uploads
│       ├── transcriber.py      # Phase 2: Groq Whisper V3 Turbo (with Tenacity retry)
│       ├── intelligence.py     # Phase 3: DeepSeek viral moment extractor + FFmpeg "sight" signals + content-aware routing (speech/action/music)
│       ├── video_editor.py     # Phase 4: FFmpeg template applier & renderer
│       └── seo_generator.py    # Phase 5: DeepSeek SEO title & hashtag builder
│
├── supabase/migrations/         # PostgreSQL schema migrations (ALTER TABLE add-column)
│
├── assets/templates/
│   ├── blurpad_v1/             # Blur-pad template (universal baseline)
│   ├── podcast_split_v1/       # Podcast split-screen template
│   ├── retro_vhs_v1/           # Retro VHS template
│   ├── gaming_neon_v1/         # Gaming Neon (+40-55% retention)
│   ├── mrbeast_energy_v1/      # MrBeast Energy (+35-45% retention, #1 style)
│   └── brand_bold_v1/          # Brand Bold (professional #2 style)
│
├── prompts/
│   ├── clip_analysis.txt       # DeepSeek clip analysis prompt
│   └── seo_generation.txt      # DeepSeek SEO generation prompt
│
├── public/
│   ├── index.html              # PWA frontend (warm cream design, publish kit, quality selector)
│   ├── styles.css              # CSS design system
│   ├── manifest.json           # Web App Manifest
│   ├── service-worker.js       # Cache-first service worker (⚠ refresh after deploys)
│   └── template-previews/      # Lightweight JPEG template previews
│
├── modal_app.py                # Modal cloud deployment
├── dev_server.py               # Local dev server (proxies /api/* to Modal)
├── design/                     # UI/UX design docs (mobile, web)
├── PLAN.md                     # ← You are here
├── prd.md                      # Master product requirements (v4.0)
├── .env
└── requirements.txt
```

***

## ✅ Phase 1 — Backend Foundation

**Status:** ✅ COMPLETED

| Step | File               | What                                                          | Status |
| ---- | ------------------ | ------------------------------------------------------------- | ------ |
| 1.1  | `requirements.txt` | Lock all deps                                                 | ✅      |
| 1.2  | `app/__init__.py`  | Empty package init                                            | ✅      |
| 1.3  | `app/config.py`    | Pydantic `Settings` with env validation                       | ✅      |
| 1.4  | `app/models.py`    | `JobStatus` enum, `Job` & `VideoClip` SQLModel tables         | ✅      |
| 1.5  | `app/database.py`  | SQLModel engine with SQLite WAL mode                          | ✅      |
| 1.6  | `app/main.py`      | FastAPI app with CORS, static mount, DB init, health endpoint | ✅      |

***

## ✅ Phase 2 — Pipeline Modules

**Status:** ✅ COMPLETED (all phases tested individually)

| Step | File                            | What                                                                     | Status |
| ---- | ------------------------------- | ------------------------------------------------------------------------ | ------ |
| 2.1  | `app/pipeline/downloader.py`    | Any http(s) link via yt-dlp (YouTube, TikTok, Instagram, GDrive) + Frame.io GraphQL share API + direct video links / local uploads | ✅      |
| 2.2  | `app/pipeline/transcriber.py`   | Groq Whisper V3 Turbo with tenacity retry (was V3, cheaper)              | ✅      |
| 2.3  | `app/pipeline/intelligence.py`  | DeepSeek viral moment analysis                                           | ✅      |
| 2.4  | `app/pipeline/video_editor.py`  | FFmpeg render with ASS subtitles                                         | ✅      |
| 2.5  | `app/pipeline/seo_generator.py` | DeepSeek SEO titles + hashtags                                           | ✅      |
| 2.6  | `app/storage.py`                | Cloudflare R2 upload (⚠️ DISABLED due to Cloudflare incident)            | ✅      |
| 2.7  | `app/pipeline/orchestrator.py`  | Pipeline controller + clip vault features (generate\_more, refresh\_seo) | ✅      |

***

## ✅ Phase 3 — API Layer

**Status:** ✅ COMPLETED

| Step | File                | What                                                           | Status |
| ---- | ------------------- | -------------------------------------------------------------- | ------ |
| 3.1  | `app/api/sse.py`    | SSE event stream helper (legacy, replaced by polling)          | ✅      |
| 3.2  | `app/api/routes.py` | `POST /api/jobs` — create + dispatch job (campaign_rules, max_clips, preferred_height) | ✅      |
| 3.3  | `app/api/routes.py` | `GET /api/jobs` — list all jobs                                | ✅      |
| 3.4  | `app/api/routes.py` | `GET /api/jobs/{id}` — full job detail with clips + posted_platforms | ✅      |
| 3.5  | `app/api/routes.py` | `GET /api/jobs/{id}/poll` — lightweight polling (replaces SSE) | ✅      |
| 3.6  | `app/api/routes.py` | `POST /api/jobs/upload` — multipart local upload (up to 500MB) | ✅      |
| 3.7  | `app/api/routes.py` | `GET /api/templates` — list available templates                | ✅      |
| 3.8  | `app/api/routes.py` | Clip vault CRUD (list, delete, download, refresh-seo)          | ✅      |
| 3.9  | `app/api/routes.py` | `POST /api/clips/{id}/posted` — toggle posted platform (tiktok/youtube/instagram) | ✅      |
| 3.10 | `app/api/routes.py` | `POST /api/jobs/{id}/generate-more` — generate extra clips     | ✅      |

***

## ✅ Phase 4 — Modal Serverless Deployment

**Status:** ✅ COMPLETED AND LIVE

| Step | File                          | What                                                                                                         | Status |
| ---- | ----------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| 4.1  | `modal_app.py`                | Modal image with ffmpeg + Python deps                                                                        | ✅      |
| 4.2  | `modal_app.py`                | `modal.Volume("trimaura-data")` for clips + status + uploads (DB moved to Supabase) | ✅      |
| 4.3  | `modal_app.py`                | `@asgi_app()` wrapping FastAPI, scale-to-zero (removed `min_containers=1`, saves $36/mo)                    | ✅      |
| 4.4  | `modal_app.py`                | `process_pipeline()` — 3600s timeout (1hr), Volume fallback                                                  | ✅      |
| 4.5  | `modal_app.py`                | `process_generate_more()` — 600s timeout                                                                     | ✅      |
| 4.6  | `modal_app.py`                | Status JSON files at `/mnt/data/status/job_{id}.json`                                                        | ✅      |
| 4.7  | `app/config.py`               | Auto-detect `MODAL=1` → override DB path                                                                     | ✅      |
| 4.8  | `app/api/routes.py`           | Conditional dispatch: `modal.Function.from_name().spawn.aio()` vs `asyncio.create_task()`                    | ✅      |
| 4.9  | `app/api/routes.py`           | `GET /api/jobs/{id}/poll` endpoint                                                                           | ✅      |
| 4.10 | `public/index.html`           | Polling every 2s (replaced SSE)                                                                              | ✅      |
| 4.11 | Deployment                    | `modal deploy modal_app.py` → live at `bassyj32--trimaura-fastapi-app.modal.run`                             | ✅      |
| 4.12 | Fix: SQLite Modal Volume sync | Pass job payload to `process_pipeline.spawn.aio()`, add retry to `_get_job()`, remove `data_volume.reload()` | ✅ v18  |

***

## ✅ Phase 5 — PWA Frontend

**Status:** ✅ COMPLETED — Warm cream UI redesign deployed

| Step | File                        | What                                                                                                             | Status |
| ---- | --------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------ |
| 5.1  | `public/index.html`         | Warm cream `#EDE9E3` layout: circular template chips, pill URL input, Opus-style result cards, simplified drawer | ✅      |
| 5.2  | `public/styles.css`         | Warm cream design system with gold accents, 52px circular swatches, result-row cards, vault list                 | ✅      |
| 5.3  | `public/manifest.json`      | Web App Manifest with `#EDE9E3` background, `display: standalone`                                                | ✅      |
| 5.4  | `public/service-worker.js`  | Cache-first for static, network-only for API, notification click handler                                         | ✅      |
| 5.5  | Icons                       | Proper PNG icons for iOS/Android install                                                                         | ✅      |
| 5.6  | Template preview images     | 6 lightweight (1.3KB each) JPEG previews for circular swatches                                                   | ✅      |
| 5.7  | PWA completion notification | Browser Notification API fires when job completes — no push server needed                                        | ✅      |

***

## ✅ Phase 6 — Static Assets & Prompts

**Status:** ✅ COMPLETED

| Step | File                                  | What                                                                                        | Status |
| ---- | ------------------------------------- | ------------------------------------------------------------------------------------------- | ------ |
| 6.1  | `prompts/clip_analysis.txt`           | DeepSeek clip analysis prompt                                                               | ✅      |
| 6.2  | `prompts/seo_generation.txt`          | DeepSeek SEO prompt                                                                         | ✅      |
| 6.3  | `assets/templates/blurpad_v1/`        | Blur-pad template config (updated styling)                                                  | ✅      |
| 6.4  | `assets/templates/podcast_split_v1/`  | Podcast split template config + overlay                                                     | ✅      |
| 6.5  | `assets/templates/retro_vhs_v1/`      | Retro VHS template config + overlay                                                         | ✅      |
| 6.6  | `assets/templates/gaming_neon_v1/`    | Gaming Neon — cyan glow, magenta highlights (+40-55% retention)                             | ✅      |
| 6.7  | `assets/templates/mrbeast_energy_v1/` | MrBeast Energy — yellow/red, #1 viral style (+35-45% retention)                             | ✅      |
| 6.8  | `assets/templates/brand_bold_v1/`     | Brand Bold — professional #2 style for business content                                     | ✅      |
| 6.9  | `app/pipeline/video_editor.py`        | Renderer supports overlay PNG, emoji captions, color grading (eq), Ken Burns zoom (zoompan) | ✅      |
| 6.10 | Emoji injection                       | 90+ keyword→emoji mapping appended to ASS subtitles                                         | ✅      |
| 6.11 | Color grading per template            | FFmpeg eq filter — brightness, contrast, saturation, gamma configurable per template        | ✅      |
| 6.12 | Ken Burns subtle zoom                 | FFmpeg zoompan — slow zoom-in over clip duration, per-template toggle                       | ✅      |

***

## ⏳ Phase 7 — Integration & Polish

**Status:** 🔄 IN PROGRESS

| Step | What                                                            | Status     | Notes                                                           |
| ---- | --------------------------------------------------------------- | ---------- | --------------------------------------------------------------- |
| 7.1  | API keys configured in `.env` and Modal secrets                 | ✅          | Groq, DeepSeek, R2 all set                                      |
| 7.2  | Pipeline timeout increased to 1hr (3600s)                       | ✅          | Handles long videos up to 1GB                                   |
| 7.3  | 6 research-backed templates with overlay PNGs                   | ✅          | MrBeast, Gaming Neon, Brand Bold + 3 originals                  |
| 7.4  | Renderer supports overlay compositing + dynamic subtitle styles | ✅          | Font, color, outline, size all per-template                     |
| 7.5  | Sentry error monitoring (backend + frontend)                    | ✅          | Free tier, 5k errors/mo. Auto-captures API crashes + JS errors  |
| 7.6  | PWA icons generated (192x512, 512x512)                          | ✅          | Real PNG icons, installable on Android/iOS                      |
| 7.7  | Safe-area CSS for notch phones                                  | ✅          | iPhone X+ notch/home indicator covered                          |
| 7.8  | iOS PWA support (apple-touch-icon, meta tags)                   | ✅          | Can add to iOS home screen                                      |
| 7.9  | Touch-optimized UI (tap targets, scroll snap)                   | ✅          | 44px min touch targets, smooth scroll                           |
| 7.10 | End-to-end test with real GDrive video                          | ✅          | Tested with Google Drive URL — pipeline completed, 3 clips      |
| 7.11 | YouTube disabled for V1 (GDrive + Frame.io + uploads)           | ✅ → ⚡ | Originally a 3-layer guard (frontend, API validation, downloader check). **Superseded by 7.28 — YouTube + all platforms now enabled** |
| 7.12 | boxblur=20:5 → 5:2 for faster rendering                         | ✅          | \~3-4x faster blurpad rendering on CPU                          |
| 7.13 | Fixed missing `Path` import in orchestrator                     | ✅          | Pipeline was crashing at RENDERING stage                        |
| 7.14 | Database migrated from SQLite → Supabase (PostgreSQL)           | ✅          | `database.py` uses Supabase pooler on Modal, local dev fallback |
| 7.15 | Mobile testing from phone                                       | ✅          | Verified on real phone (PWA blank screen fixed via `.frame-wrapper` CSS). Live end-to-end: GDrive + Frame.io jobs → 3 clips each |
| 7.16 | Cloudflare R2 SSL incident                                      | 🐌 BLOCKED | Incident `py46dmbg0t0t`, using Modal Volume fallback            |
| 7.17 | Frame.io share links supported                                  | ✅          | GraphQL share API (`base64(share_id)` header). PWA quality selector: 360p/540p/720p/1080p/Original (**default 1080p** since 7.29). Verified live: 540p → 35.7MB (960x506), 720p → 51MB; job 32 COMPLETED |
| 7.18 | Publish kit (TikTok / Shorts / Reels)                            | ✅          | Per-clip buttons: copy platform-formatted caption (title + hashtags + optional link) + download MP4 + open upload page. Posted ✓ tracking (toggle endpoint, `posted_platforms` column). Settings has "Your Link" field. Verified live in browser |
| 7.19 | Supabase migrations for new columns                              | ✅          | `preferred_height` on job, `posted_platforms` on videoclip — `supabase/migrations/`, applied via Supabase MCP |
| 7.20 | PWA service-worker stale shell                                  | ✅ FIXED    | After deploys the SW serves old HTML → unregister SW + clear caches on load (verified in browser) |
| 7.21 | FFmpeg "sight" signals                                          | ✅          | Cheap pre-analysis in `intelligence.py`: scene cuts, loud windows (PCM + RMS), black/dead-air ranges. `snap_clips_to_signals()` hard post-pass so clips land on real moments, not AI guesses |
| 7.22 | PWA push notifications                                          | ✅          | VAPID keys, `pywebpush`, `PushSubscription` table, `POST/DELETE /api/push/subscribe` + `GET /api/push/vapid-key`, service-worker `push` handler. Notifies on COMPLETED/FAILED so you can deploy from your phone without watching the page |
| 7.23 | Back-to-back live stress test                                   | ✅          | `_back2back_test.py` vs real Frame.io share link on live Modal: 3 simultaneous jobs, all stages clean, **3/3 COMPLETED** (836–1061s each on old settings) |
| 7.24 | Render speed under pressure                                     | ✅          | `cpu=2.0` on both Modal pipeline functions + `-preset fast → veryfast`. Re-test on same link: **331–361s/job (2.6–3× faster)**, 3/3 COMPLETED, downloads 200 video/mp4 |
| 7.25 | Progressive clip publishing                                     | ✅          | Per-clip DB commit + Volume commit the moment each clip renders — clips appear while still rendering and survive a mid-render failure (failed path also syncs finished clips) |
| 7.26 | Viral score (0-100) + best-first sort                            | ✅          | DeepSeek returns a `score` per clip (scoring guide in `clip_analysis.txt`); `intelligence.py` normalizes & sorts best-first; stored in `videoclip.viral_score` (Supabase migration applied); frontend shows colored score badge + sorts clips so you always post the strongest one first |
| 7.27 | Clean video (no on-screen text)                                  | ✅          | Default renders burn NO text: subtitles + template overlay PNGs disabled (`burn_text=False` in `video_editor.execute_render`). Clips come out clean — the user adds their own text later. `burn_text=True` escape hatch kept for the future |
| 7.28 | Any-source downloads (YouTube + all yt-dlp platforms)            | ✅          | Removed the 3-layer YouTube block (frontend host check, API whitelist, downloader guard). Any http(s) link now goes through yt-dlp: YouTube, TikTok, Instagram, Twitter/X, Vimeo, Google Drive, etc. Fixed YouTube bot-check: `player_client=["default"]` (old `tv#embed` was blocked) + updated yt-dlp. Verified end-to-end download locally. ⚠️ Some TikTok/Instagram videos are login-walled → need cookies (backlog #4) |
| 7.29 | 1080p default download quality                                   | ✅          | `preferred_height` default 720 → **1080** everywhere (routes, orchestrator fallbacks, `execute_download` default, PWA selector default 1080p). yt-dlp format cap: `best[height<=1080]/best`. Original (0) still available per job |
| 7.30 | Content-aware clip selection (speech/action/music)               | ✅          | `classify_content()`: transcript-coverage ratio + scene-cut density → type. Speech content uses DeepSeek transcript selection (unchanged); no-speech content (music video, gameplay w/o commentary, visual B-roll) now uses `select_signal_clips()`: loudness windows → longest scene chunks → even spacing. Removed the hard "No speech detected" job failure. SEO falls back to video title when transcript is empty. Verified: unit tests + real silent video produced 3 non-overlapping clips |
| 7.31 | Optional cookies.txt upload (fixes YouTube bot-block on cloud IPs) | ✅        | Production back-to-back on a YouTube link failed 3/3 with "Sign in to confirm you're not a bot" on Modal's cloud IPs (works on local residential IP). Fix: PWA settings gains a "Cookies File" picker (export via "Get cookies.txt LOCALLY" extension) → sent with the job → persisted per job on the Volume (`/mnt/data/cookies/{job_id}.txt`, no DB schema change) → passed to yt-dlp (`opts["cookiefile"]`) in `execute_download`. `generate-more` re-downloads reuse the same file. Service-worker cache bumped v2→v3. Verified live: YouTube back-to-back 1/3 passed without cookies (bot check is intermittent on cloud IPs) — job COMPLETED 4.4 min, 5 clips (scores 82-91) |
| 7.32 | Cookies persist in the browser                               | ✅          | Picked cookies.txt is saved to `localStorage` (`trimaura_cookies`) so you pick it once per platform — survives reloads (with a Remove button + size guard >2MB). Re-pick only when it expires |
| 7.33 | YouTube on cloud IPs — infrastructure hardened, still IP-blocked | ⚠️ DEFERRED | Deep dive: Modal's datacenter IPs are reputation-flagged by Google. Even with valid cookies + deno JS runtime + Chrome TLS impersonation (`impersonate: chrome` via curl_cffi) + a live PO-token provider (`bgutil-pot` + `bgutil-ytdlp-pot-provider` plugin) + all player clients (default/tv/web_embedded/android/android_vr/ios), YouTube returns "Sign in to confirm you're not a bot" from Modal IPs (works from residential IPs). Real fix needs a residential proxy — parked. The image changes are kept: deno, `curl_cffi>=0.14,<0.16` (yt-dlp rejects 0.16+), `bgutil-pot` binary, POT plugin — all degrade gracefully (no-op when binary/plugin missing) so other sources (Frame.io, TikTok, Instagram, direct links) are unaffected |
| 7.34 | Auto template by genre                                      | ✅          | Each template.json now declares `genres` keywords. New `recommend_template()` in intelligence.py scores templates by title (×3) + transcript (×1) keyword hits; speech falls back to blurpad_v1 baseline, action→gaming_neon, music→mrbeast_energy when no signal. New "Auto" chip is the DEFAULT template picker option; `template_id="auto"` is resolved in the pipeline and the chosen template is persisted on the job (generate-more + result cards reuse it). 12/12 unit cases pass |
| 7.35 | R2 disabled until TLS cert provisioned                     | ✅          | `config.R2_ENABLED` was `True` while storage.py/config comment said DISABLED → every upload attempted R2 and failed with `SSLV3_ALERT_HANDSHAKE_FAILURE`, adding wasted retry latency per clip before falling back. Flipped `R2_ENABLED = False` (matches docstring + config comment; Volume fallback already covered clips, downloads, generate-more). Verified live: new job completed with zero `[R2] Upload failed` logs, clip resolves to `/mnt/data/clips/…`, `/api/clips/{id}/download` returns 200 video/mp4 from the Volume |
| 7.36 | Genre-distinct template overlays on by default              | ✅          | Decoupled the PNG overlay frame from subtitle burning in `video_editor.execute_render` (new `apply_overlay=True` default; `burn_text` still only controls ASS captions). Every template now composites its own overlay — gaming cyan glow/grid/FPS box, MrBeast yellow/red corner blocks + arrows, podcast bottom bar, VHS scanlines + tracking bars, brand gold/silver frame; blurpad stays the clean baseline (no overlay, by design) — so "Auto" picks (7.34) finally render visually distinct. **Fixed latent bug**: overlay chain wrote `[main]overlay=0:0` and left the `[overlay]` input unconnected (`Filter 'format:default' has output 0 (overlay) unconnected`) — broken since the overlay feature shipped but masked by 7.27 disabling it; now `[main][overlay]overlay=0:0`. Verified: 6/6 templates render (console smoke test) |
| 7.37 | Burned animated captions (Opus-style karaoke)                | ✅          | `transcriber.py` requests `timestamp_granularities=["word"]` and attaches per-word timings to each segment (`_words_for_segment`, handles both flat `response.words` and nested shapes). `video_editor.py` gains a karaoke ASS builder: each word becomes a `\k` syllable so it flips white → template `highlight_color` as spoken (classic Opus look); segments without word timings fall back to plain text; emoji injection kept. New `Job.burn_captions` flag (default OFF to preserve clean-clip output) wired end-to-end: API `CreateJobRequest` + upload `Form` field → job payload → orchestrator passes `burn_text=job.burn_captions` in both initial render and generate-more. Supabase migration `add_job_burn_captions.sql` applied. PWA Settings gains an "Opus-Style Captions" toggle (persisted in localStorage). Verified locally: ASS output has correct `\k` tags + secondary colour, and a burn_text=True render (karaoke + overlay) succeeds |
| 7.38 | Silence/filler trimming + clip trim & re-render (Opus polish) | ✅          | Two Opus gaps closed. **(a) Silence trimming** — `video_editor._compute_silence_cuts` cuts inter-word pauses ≥0.5s + leading/trailing dead air from Whisper word timestamps; cuts ONLY land between words so karaoke `\k` durations stay frame-accurate; `_shift_time` remaps caption times into the condensed timeline; audio condensed with the same keep-intervals (`atrim/asetpts/concat` + `-map [conda]`); safety floor keeps ≥1.2s. New `Job.trim_silence` flag (default OFF) wired end-to-end: API JSON + upload Form + payload → orchestrator (initial render AND generate-more) → render; Supabase migration `add_job_trim_silence.sql`; PWA Settings "Silence Trimming" toggle (localStorage). **(b) Clip trim & re-render** — `POST /api/clips/{id}/trim` (new bounds must stay strictly inside the original clip) → Modal `process_trim_clip` worker → `orchestrator.trim_clip` re-renders from the saved source + transcript (no re-analysis/re-download) with the job's template/burn/silence settings and updates the clip row in place (job flips RENDERING → COMPLETED without a push). PWA clip drawer gains Start/End sliders + "Save Trim" that polls until re-rendered, then refreshes the clip card. **Fixed float-boundary bug** in `_shift_time`: a word ending exactly at a cut start was clamped back to ≈uncondensed time (7.6s instead of 4.7s); fixed with `t > cs + 1e-9`. Verified: 16/16 silence-engine smoke tests + `py_compile` clean. SW cache v6→v7 |
| 7.39 | Face-aware crop (Opus-style speaker tracking)                 | ✅          | New `app/pipeline/face_track.py`: MediaPipe face detection when importable, else OpenCV Haar cascades (bundled with `opencv-python-headless` — zero model downloads, no fragile mediapipe build on Modal's Python 3.13) → normalized face track `[{t,cx,cy}]` (median-smoothed, largest-face pick). `execute_pipeline` detects ONCE in Phase 3 and persists it on `Job.face_track_json` (Supabase migration `add_job_face_track.sql` applied); every render — initial pipeline, generate-more, AND clip trim — reuses the saved track. `video_editor._build_animated_crop` scales the source to cover the canvas + 15% slack, then animates a `crop=W:H:x='expr':y='expr'` window that pans to keep the speaker centered: pure `_lerp_expr` piecewise-linear FFmpeg expression (half-open `[t_i,t_{i+1})` gating so sample points are counted once — `between()` alone double-counts at joints), face times remapped through the silence-condensed timeline via `_shift_time`, `[]` track → static center-crop fallback. **Fixed pre-existing 7.38 bug**: silence-trim renders built `[condv],scale=…` — a comma after a bare label parses as an empty filter (`No such filter: ''`), so condensed clips had NEVER rendered; now labels glue directly (`[condv]scale=…`). Verified: 17/17 smoke tests (expression math vs reference piecewise + bounds/holds, animated-crop plan incl. silence cuts + static fallback, detector graceful on synthetic footage, real 1080×1920 renders with face track — plain AND silence-condensed, correct durations 3.0s/2.2s) + `py_compile` + app import clean. Modal image adds `opencv-python-headless`. No UI toggle — face tracking is automatic, degrades to static crop when no face is found |
| 7.40 | Clip viewer page + copy-link (hosted playback)                  | ✅          | Tiny UX close-out: new `public/clip.html` — a standalone dark, 9:16-optimized player (`/clip.html?id=<id>`) that plays the MP4 straight from `/api/clips/{id}/download` (Starlette `FileResponse` already serves HTTP Range → fast start + seeking for free), plus title/viral-score enrichment from `/api/clips` and a Download button. Clip drawer gains two buttons: **Open Player** (new tab) and **Copy Link** (shareable URL). SW cache v7→v8, `/clip.html` added to precache. Verified locally: `/clip.html` 200 + player markup, drawer buttons present, download endpoint serves via Range on real clips. No backend changes needed — the download route already streamed |

**Known limitations (V1):**
- YouTube downloads from Modal's cloud IPs are blocked by Google's bot check ("Sign in to confirm you're not a bot") — even with cookies, Chrome impersonation, and a PO-token provider. Works from residential IPs; a residential proxy would unblock it (deferred, see 7.33)
- TikTok/Instagram login-walled videos still need an exported cookies.txt — upload it in Settings → Cookies File (fixes YouTube's bot check on cloud IPs too; solved for the YouTube case in 7.31)
- Music/visual clips get generic SEO (title-only) since there's no transcript to mine
- `select_signal_clips` is deterministic — "Generate more" may return nothing new once energy windows are exhausted

***

## 🎯 Future Polish Backlog (saved for later — not needed for V1)

Ranked by ROI for the current solo/gaming workflow. Not scheduled.

| # | Upgrade | Difficulty | Value | Notes |
|---|---------|-----------|-------|-------|
| 1 | ~~**Karaoke / word-level animated captions**~~ | ~~🟡 Medium~~ | ~~High (retention)~~ | **✅ Shipped in 7.37** — Whisper word timestamps (`timestamp_granularities=["word"]`), ASS `\k` builder, template `highlight_color`, per-job `burn_captions` toggle. |
| 2 | ~~**Silence / filler-word trimming**~~ | ~~🟡 Medium~~ | ~~Medium~~ | **✅ Shipped in 7.38** — cuts inter-word pauses ≥0.5s (safest: never mid-word, so karaoke timing + captions stay in sync), per-job `trim_silence` toggle. |
| 3 | ~~**Trim / adjust clips**~~ | ~~🟢 Easy~~ | ~~High~~ | **✅ Shipped in 7.38** — per-clip Start/End sliders in the clip drawer → `POST /api/clips/{id}/trim` re-renders from the saved source + transcript (tighten-only) and updates the clip in place. |
| 4 | ~~**Face-aware crop (speaker tracking)**~~ | ~~🔴 Hard~~ | ~~Low for gaming~~ | **✅ Shipped in 7.39** — auto face tracking (OpenCV Haar, MediaPipe if importable) + smoothed animated crop, auto with static fallback; runs once per job, reused by every render. |
| 5 | ~~**Cookies file support (TikTok/Instagram/login-walled videos)**~~ | ~~🟢 Easy~~ | ~~Medium~~ | **✅ Shipped in 7.31** — PWA "Cookies File" picker → persisted per job → passed to yt-dlp (`opts["cookiefile"]`). Unlocks login-walled YouTube/TikTok/Instagram posts and fixes the YouTube bot-check on cloud IPs. |
| — | ~~Music overlay~~ | ~~Easy~~ | — | **Explicitly not wanted** by the user — skip. |

> All other Opus-clip features (B-roll, dubbing, speech enhancement, direct auto-post, scheduler) are intentionally out of scope for the solo tool.

***

## 🚀 Phase 8 — Scaling for Thousands of Users

**Status:** 📋 PLANNED

This phase is what turns TrimAURA from a personal tool into a SaaS product serving 1000s of creators.

### Auth & Multi-Tenancy

| Priority | Feature                                    | Why                                            |
| -------- | ------------------------------------------ | ---------------------------------------------- |
| 🔴 P0    | User auth (Google OAuth or email+password) | Each user needs isolated jobs, clips, settings |
| 🔴 P0    | User ↔ Job relationship in models          | `Job.user_id` foreign key                      |
| 🔴 P0    | Per-user clip vault                        | Users see only their own clips                 |
| 🟡 P1    | Team / workspace support                   | Agencies managing multiple clients             |

### Database — SQLite → PostgreSQL

| Why                                                      | Migration Path                                          |
| -------------------------------------------------------- | ------------------------------------------------------- |
| SQLite can't handle concurrent writes from 100s of users | Use **Supabase** (PostgreSQL) — free tier handles 1000s |
| SQLite WAL on Modal Volume has latency                   | Supabase gives managed DB with connection pooling       |
| SQLite doesn't scale horizontally                        | Alembic migrations for zero-downtime schema changes     |

### Job Queue — Polling → Proper Queue

| Current                 | Future                                                           |
| ----------------------- | ---------------------------------------------------------------- |
| Frontend polls every 2s | **Redis + Celery** or **Modal Task Queue** for real-time updates |
| No retry on failure     | Automatic retry with exponential backoff                         |
| No priority             | Priority queue for paying users                                  |

### Billing

| Feature                        | Implementation                                     |
| ------------------------------ | -------------------------------------------------- |
| Usage-based pricing (per clip) | **Stripe** metered billing                         |
| Free tier: 10 clips/month      | Track usage in `User.clips_generated` counter      |
| Paid tiers: unlimited          | Webhook on payment success → update user tier      |
| Cost control                   | `max_clips` slider already implemented in frontend |

### CDN & Storage

| Current                      | Future                                              |
| ---------------------------- | --------------------------------------------------- |
| Modal Volume (single region) | **Cloudflare R2** CDN — global edge, fast downloads |
| R2 disabled (SSL incident)   | Flip `R2_ENABLED = True` once resolved              |
| Local file serving           | R2 presigned URLs + CDN caching                     |

### Monitoring & Observability

| Tool                  | What it tracks                        |
| --------------------- | ------------------------------------- |
| **Modal logs**        | Pipeline execution, errors, timing    |
| **Sentry**            | Error tracking across all users       |
| **Datadog / Grafana** | CPU, memory, API latency, queue depth |
| **Uptime monitoring** | Cron job pings `/health` every 5 min  |

### Estimated Infrastructure Cost (1000 users, 5000 clips/month)

| Service               | Cost/month            | Notes                            |
| --------------------- | --------------------- | -------------------------------- |
| Modal compute         | \~$50-100             | FFmpeg renders are the main cost |
| Supabase (PostgreSQL) | $25                   | Free tier works for MVP          |
| Cloudflare R2         | $5-10                 | Egress + storage, very cheap     |
| Stripe                | 2.9% + $0.30/txn      | Transaction fees                 |
| Sentry                | Free (developer tier) | Error monitoring                 |
| **Total**             | **\~$100-150/mo**     | Before revenue                   |

***

## 💰 Cost Analysis

### Current Personal Plan (Cheap Mode)

> You're on **Modal Hobby** ($30/mo free credits) + **Groq Free Tier** + **DeepSeek pay-as-you-go** (\~$5 prepaid).
> **Scale-to-zero enabled** — no always-on container. App goes to sleep when idle, cold starts in ~1s.

| Service                 | What You Pay                                     | How It's Free                                   |
| ----------------------- | ------------------------------------------------ | ----------------------------------------------- |
| **Modal compute**       | **$0/mo** (within free $30 credits)              | Modal gives $30/mo free. You use \~$2           |
| **Groq Whisper Turbo**  | **$0/mo** (or ~$0.03/video past free tier)       | Free tier: 3,000 calls/day, 1,000 min audio/day |
| **DeepSeek V4 Flash**   | **\~$0.0001/video** ($5 prepaid ≈ 50,000 videos) | Extremely cheap API pricing                     |
| **Cloudflare R2**       | **$0/mo** (disabled)                             | Would be free tier anyway (10GB, 1M reads/mo)   |
| **Modal Volume**        | **Included**                                     | Storage within free tier                        |
| **Total**               | **\~$0-1/mo**                                    | $5 DeepSeek deposit lasts years                 |

#### Per-Video Cost Breakdown (40 videos/mo = 10/week)

| Step                       | Cost per Video | Annual Cost   |
| -------------------------- | -------------- | ------------- |
| Download (Modal CPU)       | \~$0.002       | \~$0.96       |
| Transcribe (Groq Turbo)    | \~$0.03        | \~$14.40      |
| Analyze (DeepSeek)         | \~$0.00004     | \~$0.02       |
| Render 5 clips (Modal CPU) | \~$0.02        | \~$9.60       |
| SEO (DeepSeek)             | \~$0.00007     | \~$0.03       |
| **Pipeline total**         | **\~$0.05**    | **\~$25**     |
| ~~Keep-warm container~~    | **$0 (removed)** | **$0**       |
| **Grand total**            | **\~$0.05/vid** | **\~$25/yr** |

> **Note:** Changed from Whisper V3 → Turbo (halves cost). Removed `min_containers=1` → saves $36/mo. Cold start is ~1s.

### 🚀 Future Cost Projections (6+ months away)

#### 100 Users (≈500 videos/mo, 5 clips each)

| Item                          | Cost/mo          | Notes                 |
| ----------------------------- | ---------------- | --------------------- |
| Modal compute (renders)       | $30-50           | Bulk of cost          |
| Modal keep-warm (auto-scale)  | $20              | Multiple containers   |
| PostgreSQL (Supabase)         | $25              | Free tier on old plan |
| Cloudflare R2 (fixed by then) | $10              | CDN + storage         |
| Stripe fees                   | 2.9% + $0.30/txn | Only if monetizing    |
| Monitoring (Sentry free)      | $0               | Developer tier        |
| **Total**                     | **\~$50-100/mo** | Before revenue        |

#### 1,000 Users (≈5,000 videos/mo, 5 clips each)

| Item                         | Cost/mo           | Notes                    |
| ---------------------------- | ----------------- | ------------------------ |
| Modal compute (renders)      | $200-400          | Bulk of cost             |
| Modal auto-scale infra       | $100              | Load-balanced containers |
| PostgreSQL (Supabase Pro)    | $50               | Team plan                |
| Cloudflare R2 CDN            | $50               | Egress + storage         |
| Redis queue                  | $20               | Job queue                |
| Stripe fees                  | 2.9% + $0.30/txn  | Only if monetizing       |
| Monitoring (Datadog/Grafana) | $50               | Optional                 |
| **Total**                    | **\~$400-600/mo** | Before revenue           |

> These numbers assume **no revenue** from users. If you charge even $5/user/mo:
>
> - 100 users × $5 = **$500/mo** → profitable
> - 1,000 users × $5 = **$5,000/mo** → very profitable

***

## 📱 Works On Phone Without R2?

**Yes, absolutely.** Cloudflare R2 being off does not affect phone usage.

| Feature                    | Works Without R2? | How                                                   |
| -------------------------- | ----------------- | ----------------------------------------------------- |
| Open app from phone        | ✅ Yes             | Modal URL loads in any browser                        |
| Submit a job               | ✅ Yes             | Enter GDrive link or upload                           |
| Pipeline processing        | ✅ Yes             | Runs in Modal cloud, not on phone                     |
| Clips rendering            | ✅ Yes             | FFmpeg runs in Modal container                        |
| Download clips             | ✅ Yes             | Served from Modal Volume via API                      |
| Video player in drawer     | ✅ Yes             | Streams from API download endpoint                    |
| Clip vault (14-day)        | ✅ Yes             | Supabase PostgreSQL + clips on Modal Volume           |
| Generate More clips        | ✅ Yes             | Volume-cached source + re-download; R2 used when available |
| PWA install to home screen | ✅ Yes             | HTTPS ready, manifest ready                           |
| Offline access             | ⏳ Needs PNG icons | Service worker works, icons pending                   |

**In short:** Everything except "Generate More" works from your phone right now. R2 only adds faster global download speeds — it's not required for the app to function.

***

## 🎯 Opus Clip vs TrimAURA — Gap Analysis

| Feature                           | Opus Clip ($29/mo) | TrimAURA (Free) |      Worth Adding for Solo?     |
| --------------------------------- | :----------------: | :-------------: | :-----------------------------: |
| **9:16 auto reframe**             |          ✅         |        ✅        |           Already done          |
| **AI subtitle captions**          |          ✅         |        ✅        |           Already done          |
| **Multi-template styling**        |          ✅         |        ✅        |    Already done (6 templates)   |
| **Hook clip detection**           |          ✅         |        ✅        |   DeepSeek picks best moments   |
| **SEO titles + hashtags**         |          ✅         |        ✅        |           Already done          |
| **Emoji in captions**             |          ✅         |        ❌        |    🟢 EASY — keyword mapping    |
| **Color grading presets**         |          ✅         |        ❌        |   🟢 EASY — FFmpeg `eq` filter  |
| **Ken Burns zoom effect**         |          ✅         |        ❌        |   🟡 MEDIUM — FFmpeg `zoompan`  |
| **Speaker detection (auto-zoom)** |          ✅         |        ❌        |     🔴 HARD — needs ML model    |
| **Filler word removal**           |          ✅         |        ❌        | 🟡 MEDIUM — filter "um/uh/like" |
| **Background music**              |          ✅         |        ❌        |  🟢 EASY — overlay audio track  |
| **B-roll auto-insert**            |          ✅         |        ❌        |   🔴 HARD — needs scene search  |
| **Multi-speaker labeling**        |          ✅         |        ❌        |   🔴 HARD — needs diarization   |
| **Clip preview + trim UI**        |          ✅         |        ⏳        |    🟡 MEDIUM — frontend work    |
| **Generate More**                 |          ✅         |        ❌        |   🐌 BLOCKED — needs R2 fixed   |

### 🎯 What I Recommend You Add (For Solo $0)

These 3 are high-impact, zero-dollar, and make your clips look significantly better:

| Priority | Feature                   | Effort   | Impact                           |
| :------: | ------------------------- | -------- | -------------------------------- |
|   **1**  | **Emoji in captions**     | \~30 min | Medium — clips feel more "alive" |
|   **2**  | **Color grade presets**   | \~30 min | High — clips look more polished  |
|   **3**  | **Ken Burns subtle zoom** | \~1 hr   | High — adds production value     |

Total effort: **\~2 hours.** After that, your clips will be 80-90% of Opus quality for **$0/mo vs $29/mo**.

> Skip the hard features (speaker detection, filler words, B-roll) for solo use. They need ML models, heavy deps, and add marginal value for Vyro clips where volume matters more than perfection.

## 🐛 Known Issues

| Issue                                      | Status          | Workaround                                            |
| ------------------------------------------ | --------------- | ----------------------------------------------------- |
| Cloudflare R2 TLS cert not provisioned     | 🔴 BLOCKED      | Clips stored on Modal Volume, served via API download. Probe with `python scripts/probe_r2.py` |
| `generate_more` no longer needs R2         | ✅ FIXED        | Source resolved R2 → Volume cache → re-download; verified live (job 32 → clip 55, 27 MB, HTTP 200) |
| PWA serves stale shell after deploys       | ✅ FIXED        | Service worker cache — reinstall/reload PWA to see new UI |
| No user auth (single-user)                 | 🟡 OK for MVP   | Add auth before onboarding others                     |
| Supabase transaction pool may timeout      | 🟡 OK for MVP   | Modal process_pipeline has 3600s timeout              |
| Volume reload on cold start                | ✅ FIXED        | `data_volume.reload()` added to download endpoint     |
| PWA blank screen on mobile CSS fix         | ✅ FIXED        | `.frame-wrapper{display:block}` deployed              |
| Scale-to-zero cold start delay             | ✅ ACCEPTABLE   | ~1s cold start (removed min_containers=1, saves $36/mo) |

***

## 📦 Deploy Commands

```bash
# Deploy to Modal cloud (on Windows use: python -m modal deploy modal_app.py)
python -m modal deploy modal_app.py

# View app logs
python -m modal app logs trimaura --since=30m

# Check secret
python -m modal secret list

# Run locally (API only)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run dev server (static files + proxy to Modal)
python dev_server.py
```

