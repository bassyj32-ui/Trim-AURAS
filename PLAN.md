# TrimAURA — Build Plan & Roadmap

> **Last updated:** 2026-07-30
> **Status:** 🟢 V1 deployed on Modal — Warm cream UI redesign, circular template swatches, Opus-style results
> **URL:** <https://bassyj32--trimaura-fastapi-app.modal.run>

***

## 📋 Project Structure

```
trimaura/
├── app/
│   ├── __init__.py              # Package init
│   ├── main.py                  # FastAPI app & static mounting
│   ├── config.py                # Pydantic Settings & environment validation
│   ├── database.py              # SQLModel engine & SQLite WAL initialization
│   ├── models.py                # SQLModel schema (Job, VideoClip, Enums)
│   ├── storage.py               # Cloudflare R2 upload helpers (DISABLED)
│   │
│   ├── api/
│   │   ├── routes.py            # REST endpoints (Jobs, Templates, History, Polling)
│   │   └── sse.py              # SSE stream helper (legacy, unused)
│   │
│   └── pipeline/
│       ├── orchestrator.py      # Pipeline controller with clip vault features
│   │   ├── downloader.py       # Phase 1: GDrive-only downloader (YouTube disabled for V1)
│       ├── transcriber.py      # Phase 2: Groq Whisper V3 (with Tenacity retry)
│       ├── intelligence.py     # Phase 3: DeepSeek viral moment extractor & titles
│       ├── video_editor.py     # Phase 4: FFmpeg template applier & renderer
│       └── seo_generator.py    # Phase 5: DeepSeek SEO title & hashtag builder
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
│   ├── index.html              # PWA frontend (warm cream design)
│   ├── styles.css              # CSS design system
│   ├── manifest.json           # Web App Manifest
│   ├── service-worker.js       # Cache-first service worker
│   └── template-previews/      # Lightweight JPEG template previews
│
├── modal_app.py                # Modal cloud deployment
├── dev_server.py               # Local dev server (proxies /api/* to Modal)
├── design/                     # UI/UX design docs (mobile, web)
├── PLAN.md                     # ← You are here
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
| 2.1  | `app/pipeline/downloader.py`    | yt-dlp download + GDrive regex                                           | ✅      |
| 2.2  | `app/pipeline/transcriber.py`   | Groq Whisper V3 with tenacity retry                                      | ✅      |
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
| 3.2  | `app/api/routes.py` | `POST /api/jobs` — create and dispatch job                     | ✅      |
| 3.3  | `app/api/routes.py` | `GET /api/jobs` — list all jobs                                | ✅      |
| 3.4  | `app/api/routes.py` | `GET /api/jobs/{id}` — full job detail with clips              | ✅      |
| 3.5  | `app/api/routes.py` | `GET /api/jobs/{id}/poll` — lightweight polling (replaces SSE) | ✅      |
| 3.6  | `app/api/routes.py` | `GET /api/templates` — list available templates                | ✅      |
| 3.7  | `app/api/routes.py` | Clip vault CRUD (list, delete, download, refresh-seo)          | ✅      |
| 3.8  | `app/api/routes.py` | `POST /api/jobs/{id}/generate-more` — generate extra clips     | ✅      |

***

## ✅ Phase 4 — Modal Serverless Deployment

**Status:** ✅ COMPLETED AND LIVE

| Step | File                          | What                                                                                                         | Status |
| ---- | ----------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| 4.1  | `modal_app.py`                | Modal image with ffmpeg + Python deps                                                                        | ✅      |
| 4.2  | `modal_app.py`                | `modal.Volume("trimaura-data")` for SQLite + clips + status                                                  | ✅      |
| 4.3  | `modal_app.py`                | `@asgi_app()` wrapping FastAPI, `min_containers=1`                                                           | ✅      |
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
| 7.11 | YouTube disabled for V1 (GDrive + local uploads only)           | ✅          | 3-layer guard: frontend, API validation, downloader check       |
| 7.12 | boxblur=20:5 → 5:2 for faster rendering                         | ✅          | \~3-4x faster blurpad rendering on CPU                          |
| 7.13 | Fixed missing `Path` import in orchestrator                     | ✅          | Pipeline was crashing at RENDERING stage                        |
| 7.14 | Database migrated from SQLite → Supabase (PostgreSQL)           | ✅          | `database.py` uses Supabase pooler on Modal, local dev fallback |
| 7.15 | Mobile testing from phone                                       | ⏳          | App live at URL, needs real-world test                          |
| 7.16 | Cloudflare R2 SSL incident                                      | 🐌 BLOCKED | Incident `py46dmbg0t0t`, using Modal Volume fallback            |

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

### Current Personal Plan (Free)

> You're on **Modal Hobby** ($30/mo free credits) + **Groq Free Tier** + **DeepSeek pay-as-you-go** (\~$5 prepaid).

| Service               | What You Pay                                     | How It's Free                                   |
| --------------------- | ------------------------------------------------ | ----------------------------------------------- |
| **Modal compute**     | **$0/mo** (within free $30 credits)              | Modal gives $30/mo free to devs. You use \~$11  |
| **Groq Whisper V3**   | **$0/mo**                                        | Free tier: 3,000 calls/day, 1,000 min audio/day |
| **DeepSeek V4 Flash** | **\~$0.0001/video** ($5 prepaid ≈ 50,000 videos) | Extremely cheap API pricing                     |
| **Cloudflare R2**     | **$0/mo** (disabled)                             | Would be free tier anyway (10GB, 1M reads/mo)   |
| **Modal Volume**      | **Included**                                     | Storage within free tier                        |
| **Total**             | **\~$0-1/mo**                                    | $5 DeepSeek deposit lasts years                 |

#### Per-Video Cost Breakdown (40 videos/mo = 10/week)

| Step                       | Cost per Video | Annual Cost   |
| -------------------------- | -------------- | ------------- |
| Download (Modal CPU)       | \~$0.002       | \~$0.96       |
| Transcribe (Groq free)     | $0             | $0            |
| Analyze (DeepSeek)         | \~$0.00004     | \~$0.02       |
| Render 5 clips (Modal CPU) | \~$0.02        | \~$9.60       |
| SEO (DeepSeek)             | \~$0.00007     | \~$0.03       |
| **Pipeline total**         | **\~$0.025**   | **\~$12**     |
| Keep-warm container        | $9/mo flat     | \~$108        |
| **Grand total**            | **\~$11/mo**   | **\~$120/yr** |

> **Note:** You've set a $28/mo Modal spend cap. At 40 videos/month, you're at \~40% of that cap. Room to grow.

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
| Clip vault (14-day)        | ✅ Yes             | SQLite + clips on Modal Volume                        |
| Generate More clips        | ❌ No              | Requires R2 for saved source (blocked until R2 fixed) |
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
| Cloudflare R2 TLS cert not provisioned     | 🔴 BLOCKED      | Clips stored on Modal Volume, served via API download |
| `generate_more` requires R2 source key     | 🟡 Needs R2 fix | Feature unavailable until R2 is back                  |
| No user auth (single-user)                 | 🟡 OK for MVP   | Add auth before onboarding others                     |
| Supabase transaction pool may timeout      | 🟡 OK for MVP   | Modal process_pipeline has 3600s timeout              |
| Stale status file on Modal Volume          | 🟡 WORKAROUND   | Job payload passed to pipeline worker; read GET /jobs/{id} for real state |

***

## 📦 Deploy Commands

```bash
# Deploy to Modal cloud
modal deploy modal_app.py

# View app logs
modal app logs trimaura --since=30m

# Check secret
modal secret list

# Run locally (API only)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run dev server (static files + proxy to Modal)
python dev_server.py
```

