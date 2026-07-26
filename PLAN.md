# TrimAURA — Build Plan & Roadmap

> **Last updated:** 2026-07-26
> **Status:** 🟢 MVP deployed on Modal cloud
> **URL:** https://bassyj32--trimaura-fastapi-app.modal.run

---

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
│       ├── downloader.py       # Phase 1: yt-dlp & GDrive parser
│       ├── transcriber.py      # Phase 2: Groq Whisper V3 (with Tenacity retry)
│       ├── intelligence.py     # Phase 3: DeepSeek viral moment extractor & titles
│       ├── video_editor.py     # Phase 4: FFmpeg template applier & renderer
│       └── seo_generator.py    # Phase 5: DeepSeek SEO title & hashtag builder
│
├── assets/templates/
│   ├── blurpad_v1/             # Blur-pad template
│   ├── podcast_split_v1/       # Podcast split-screen template
│   └── retro_vhs_v1/           # Retro VHS template
│
├── prompts/
│   ├── clip_analysis.txt       # DeepSeek clip analysis prompt
│   └── seo_generation.txt      # DeepSeek SEO generation prompt
│
├── public/
│   ├── index.html              # PWA frontend (SaaS dark theme)
│   ├── styles.css              # CSS design system
│   ├── manifest.json           # Web App Manifest
│   └── service-worker.js       # Cache-first service worker
│
├── modal_app.py                # Modal cloud deployment
├── PLAN.md                     # ← You are here
├── .env
└── requirements.txt
```

---

## ✅ Phase 1 — Backend Foundation

**Status:** ✅ COMPLETED

| Step | File | What | Status |
|------|------|------|--------|
| 1.1 | `requirements.txt` | Lock all deps | ✅ |
| 1.2 | `app/__init__.py` | Empty package init | ✅ |
| 1.3 | `app/config.py` | Pydantic `Settings` with env validation | ✅ |
| 1.4 | `app/models.py` | `JobStatus` enum, `Job` & `VideoClip` SQLModel tables | ✅ |
| 1.5 | `app/database.py` | SQLModel engine with SQLite WAL mode | ✅ |
| 1.6 | `app/main.py` | FastAPI app with CORS, static mount, DB init, health endpoint | ✅ |

---

## ✅ Phase 2 — Pipeline Modules

**Status:** ✅ COMPLETED (all phases tested individually)

| Step | File | What | Status |
|------|------|------|--------|
| 2.1 | `app/pipeline/downloader.py` | yt-dlp download + GDrive regex | ✅ |
| 2.2 | `app/pipeline/transcriber.py` | Groq Whisper V3 with tenacity retry | ✅ |
| 2.3 | `app/pipeline/intelligence.py` | DeepSeek viral moment analysis | ✅ |
| 2.4 | `app/pipeline/video_editor.py` | FFmpeg render with ASS subtitles | ✅ |
| 2.5 | `app/pipeline/seo_generator.py` | DeepSeek SEO titles + hashtags | ✅ |
| 2.6 | `app/storage.py` | Cloudflare R2 upload (⚠️ DISABLED due to Cloudflare incident) | ✅ |
| 2.7 | `app/pipeline/orchestrator.py` | Pipeline controller + clip vault features (generate_more, refresh_seo) | ✅ |

---

## ✅ Phase 3 — API Layer

**Status:** ✅ COMPLETED

| Step | File | What | Status |
|------|------|------|--------|
| 3.1 | `app/api/sse.py` | SSE event stream helper (legacy, replaced by polling) | ✅ |
| 3.2 | `app/api/routes.py` | `POST /api/jobs` — create and dispatch job | ✅ |
| 3.3 | `app/api/routes.py` | `GET /api/jobs` — list all jobs | ✅ |
| 3.4 | `app/api/routes.py` | `GET /api/jobs/{id}` — full job detail with clips | ✅ |
| 3.5 | `app/api/routes.py` | `GET /api/jobs/{id}/poll` — lightweight polling (replaces SSE) | ✅ |
| 3.6 | `app/api/routes.py` | `GET /api/templates` — list available templates | ✅ |
| 3.7 | `app/api/routes.py` | Clip vault CRUD (list, delete, download, refresh-seo) | ✅ |
| 3.8 | `app/api/routes.py` | `POST /api/jobs/{id}/generate-more` — generate extra clips | ✅ |

---

## ✅ Phase 4 — Modal Serverless Deployment

**Status:** ✅ COMPLETED AND LIVE

| Step | File | What | Status |
|------|------|------|--------|
| 4.1 | `modal_app.py` | Modal image with ffmpeg + Python deps | ✅ |
| 4.2 | `modal_app.py` | `modal.Volume("trimaura-data")` for SQLite + clips + status | ✅ |
| 4.3 | `modal_app.py` | `@asgi_app()` wrapping FastAPI, `min_containers=1` | ✅ |
| 4.4 | `modal_app.py` | `process_pipeline()` — 1200s timeout, Volume fallback | ✅ |
| 4.5 | `modal_app.py` | `process_generate_more()` — 600s timeout | ✅ |
| 4.6 | `modal_app.py` | Status JSON files at `/mnt/data/status/job_{id}.json` | ✅ |
| 4.7 | `app/config.py` | Auto-detect `MODAL=1` → override DB path | ✅ |
| 4.8 | `app/api/routes.py` | Conditional dispatch: `modal.Function.from_name().spawn.aio()` vs `asyncio.create_task()` | ✅ |
| 4.9 | `app/api/routes.py` | `GET /api/jobs/{id}/poll` endpoint | ✅ |
| 4.10 | `public/index.html` | Polling every 2s (replaced SSE) | ✅ |
| 4.11 | Deployment | `modal deploy modal_app.py` → live at `bassyj32--trimaura-fastapi-app.modal.run` | ✅ |

---

## ✅ Phase 5 — PWA Frontend

**Status:** ✅ COMPLETED (needs proper PNG icons for full PWA)

| Step | File | What | Status |
|------|------|------|--------|
| 5.1 | `public/index.html` | Dark SaaS layout: URL input, template picker, Generate button, progress bar, history, clip drawer, settings modal | ✅ |
| 5.2 | `public/styles.css` | #070B0E dark theme with #00E5FF accent, glassmorphism, neon glow | ✅ |
| 5.3 | `public/manifest.json` | Web App Manifest with theme colors, `display: standalone` | ✅ |
| 5.4 | `public/service-worker.js` | Cache-first for static, network-only for API | ✅ |
| 5.5 | Icons | Proper PNG icons for iOS/Android install | ⏳ NEEDED |

---

## ✅ Phase 6 — Static Assets & Prompts

**Status:** ✅ COMPLETED

| Step | File | What | Status |
|------|------|------|--------|
| 6.1 | `prompts/clip_analysis.txt` | DeepSeek clip analysis prompt | ✅ |
| 6.2 | `prompts/seo_generation.txt` | DeepSeek SEO prompt | ✅ |
| 6.3 | `assets/templates/blurpad_v1/` | Blur-pad template config | ✅ |
| 6.4 | `assets/templates/podcast_split_v1/` | Podcast split template config + overlay | ✅ |
| 6.5 | `assets/templates/retro_vhs_v1/` | Retro VHS template config + overlay | ✅ |

---

## ⏳ Phase 7 — Integration & Polish

**Status:** 🔄 IN PROGRESS

| Step | What | Status | Notes |
|------|------|--------|-------|
| 7.1 | API keys configured in `.env` and Modal secrets | ✅ | Groq, DeepSeek, R2 all set |
| 7.2 | End-to-end test with real video | ⏳ | Need to test with real GDrive link |
| 7.3 | Mobile testing from phone | ⏳ | App live, needs real-world test |
| 7.4 | PWA install + offline test | ⏳ | Needs PNG icons first |
| 7.5 | Cloudflare R2 SSL incident | 🐌 BLOCKED | Incident `py46dmbg0t0t`, using Modal Volume fallback |

---

## 🚀 Phase 8 — Scaling for Thousands of Users

**Status:** 📋 PLANNED

This phase is what turns TrimAURA from a personal tool into a SaaS product serving 1000s of creators.

### Auth & Multi-Tenancy

| Priority | Feature | Why |
|----------|---------|-----|
| 🔴 P0 | User auth (Google OAuth or email+password) | Each user needs isolated jobs, clips, settings |
| 🔴 P0 | User ↔ Job relationship in models | `Job.user_id` foreign key |
| 🔴 P0 | Per-user clip vault | Users see only their own clips |
| 🟡 P1 | Team / workspace support | Agencies managing multiple clients |

### Database — SQLite → PostgreSQL

| Why | Migration Path |
|-----|----------------|
| SQLite can't handle concurrent writes from 100s of users | Use **Supabase** (PostgreSQL) — free tier handles 1000s |
| SQLite WAL on Modal Volume has latency | Supabase gives managed DB with connection pooling |
| SQLite doesn't scale horizontally | Alembic migrations for zero-downtime schema changes |

### Job Queue — Polling → Proper Queue

| Current | Future |
|---------|--------|
| Frontend polls every 2s | **Redis + Celery** or **Modal Task Queue** for real-time updates |
| No retry on failure | Automatic retry with exponential backoff |
| No priority | Priority queue for paying users |

### Billing

| Feature | Implementation |
|---------|---------------|
| Usage-based pricing (per clip) | **Stripe** metered billing |
| Free tier: 10 clips/month | Track usage in `User.clips_generated` counter |
| Paid tiers: unlimited | Webhook on payment success → update user tier |
| Cost control | `max_clips` slider already implemented in frontend |

### CDN & Storage

| Current | Future |
|---------|--------|
| Modal Volume (single region) | **Cloudflare R2** CDN — global edge, fast downloads |
| R2 disabled (SSL incident) | Flip `R2_ENABLED = True` once resolved |
| Local file serving | R2 presigned URLs + CDN caching |

### Monitoring & Observability

| Tool | What it tracks |
|------|---------------|
| **Modal logs** | Pipeline execution, errors, timing |
| **Sentry** | Error tracking across all users |
| **Datadog / Grafana** | CPU, memory, API latency, queue depth |
| **Uptime monitoring** | Cron job pings `/health` every 5 min |

### Estimated Infrastructure Cost (1000 users, 5000 clips/month)

| Service | Cost/month | Notes |
|---------|-----------|-------|
| Modal compute | ~$50-100 | FFmpeg renders are the main cost |
| Supabase (PostgreSQL) | $25 | Free tier works for MVP |
| Cloudflare R2 | $5-10 | Egress + storage, very cheap |
| Stripe | 2.9% + $0.30/txn | Transaction fees |
| Sentry | Free (developer tier) | Error monitoring |
| **Total** | **~$100-150/mo** | Before revenue |

---

## 🐛 Known Issues

| Issue | Status | Workaround |
|-------|--------|-----------|
| Cloudflare R2 TLS cert not provisioned | 🔴 BLOCKED | Clips stored on Modal Volume, served via API download |
| `generate_more` requires R2 source key | 🟡 Needs R2 fix | Feature unavailable until R2 is back |
| PWA icons are SVG data URIs (blank on iOS) | 🟡 Low priority | Add proper PNG icon files |
| No user auth (single-user) | 🟡 OK for MVP | Add auth before onboarding others |

---

## 📦 Deploy Commands

```bash
# Deploy to Modal cloud
modal deploy modal_app.py

# View app logs
modal app logs trimaura --since=30m

# Check secret
modal secret list

# Run locally
cd d:\trae\TrimAURAs\TrimAuras
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
