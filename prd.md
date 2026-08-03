Here is your final, complete, and production-ready **Master Product Requirement Document (PRD v4.0)**.

It incorporates the **Modal serverless architecture**, **template-driven layouts with folder versioning**, **API retry resiliency**, **3 catchy title options per clip**, a **Mobile Job History view**, **Supabase PostgreSQL**, **Frame.io GraphQL source download with quality selection**, and a **Publish Kit** (one-tap captions + upload links for TikTok / YouTube Shorts / Instagram Reels with posted tracking).

***

# PRODUCT REQUIREMENT DOCUMENT (PRD) - v4.0

## PROJECT NAME: TrimAURA

**Tagline:** High-speed, template-driven $16:9 \rightarrow 9:16$ short-form video re-framing, captioning & publishing engine.

**Target Platform:** Mobile-First PWA (iOS/Android) & Web

**Primary Architecture:** FastAPI + SQLModel (Supabase PostgreSQL) + Modal.com (Serverless FFmpeg Execution) + Groq Whisper V3 Turbo + DeepSeek Chat + Modal Volume (fallback) + Cloudflare R2 (CDN, currently disabled).

***

## 1. VISION & ARCHITECTURE OVERVIEW

TrimAURA converts long-form horizontal videos (Google Drive, Frame.io share links, local uploads) into viral $9:16$ vertical shorts (TikToks, Reels, Shorts).

It is designed to be operated from a **mobile phone PWA** while all heavy compute tasks (downloading, transcribing, AI hook selection, FFmpeg rendering) are offloaded to **Modal.com cloud containers**. Finished clips can be published directly from the PWA: per-platform captions are copied, the MP4 is downloaded, and the platform upload screen opens in one tap.

```text
┌────────────────────────┐
│  Mobile PWA (Phone/PC) │
│  Submit Link & History │
└───────────┬────────────┘
            │ 1. POST /api/jobs (URL + Template ID)
            ▼
┌────────────────────────┐      ┌──────────────────────────────┐
│   FastAPI Web App      │ ────►│   SQLModel / Supabase Pg    │
│  (Modal / Cloud Host)  │      │  (Jobs & Video Clips)       │
└───────────┬────────────┘      └──────────────────────────────┘
            │ 2. Dispatches Modal Background Worker
            ▼
┌────────────────────────────────────────────────────────┐
│               Modal.com Serverless Worker              │
│  1. yt-dlp / GDrive / Frame.io Download to Ephemeral Workspace │
│  2. Groq Whisper V3 Turbo (API + Tenacity Auto-Retry)  │
│  3. DeepSeek Chat (API + Tenacity Auto-Retry)          │
│  4. FFmpeg Engine (Loads Versioned Template + Subtitles)│
│  5. Copy HD 1080x1920 MP4 Clips to Modal Volume (+R2)  │
│  6. Auto-Purge Raw Source & Terminate Container        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│         Cloudflare R2 Bucket (S3 Compatible)           │
│   Stores finished 1080x1920 MP4 clips & previews       │
└────────────────────────────────────────────────────────┘

```

***

## 2. ENGINEERING STANDARDS & GUARDRAILS

1. **Python Standards:** Python 3.11+. Strict type hints required (`from typing import Optional, List, Dict`).
2. **Single Entry Point Pattern:** Pipeline modules expose **one public entry function** (`async def execute_...()`).
3. **No Business Logic in API Routes:** Endpoints in `app/api/` only handle HTTP validation and dispatch Modal background tasks.
4. **Resiliency Rule (Mandatory Retries):** All external AI API calls (Groq, DeepSeek) MUST be wrapped with exponential backoff retries (`tenacity`) to recover automatically from timeouts or 429 rate limits.
5. **No Thumbnails:** Static image thumbnails are omitted to maximize pipeline speed and minimize storage bloat.
6. **No AI Layout Guessing:** FFmpeg layout coordinates, bounding boxes, fonts, and borders are strictly loaded from hardcoded JSON template configs.

***

## 3. PROJECT DIRECTORY STRUCTURE

```text
trimaura/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app & static mounting
│   ├── config.py                # Pydantic Settings & environment validation
│   ├── database.py              # SQLModel engine — Supabase Postgres pooler (local SQLite fallback)
│   ├── models.py                # SQLModel schema (Job, VideoClip, Enums)
│   ├── storage.py               # Cloudflare R2 upload helpers (DISABLED)
│   │
│   ├── api/
│   │   ├── routes.py            # REST endpoints (Jobs, Upload, Clip Vault, Posted, Download, Generate More)
│   │   └── sse.py              # Real-time progress SSE stream (legacy, replaced by polling)
│   │
│   └── pipeline/
│       ├── orchestrator.py      # Modal worker execution controller
│       ├── downloader.py       # Any http(s) link via yt-dlp (YouTube, TikTok, Instagram, GDrive; optional cookies.txt), Frame.io GraphQL, local uploads
│       ├── transcriber.py      # Phase 2: Groq Whisper V3 Turbo (with Tenacity retry)
│       ├── intelligence.py     # Phase 3: DeepSeek viral moment extractor & titles + content-aware routing (speech/action/music)
│       ├── video_editor.py     # Phase 4: FFmpeg template applier & renderer
│       └── seo_generator.py    # Phase 5: DeepSeek SEO title & hashtag builder
│
├── supabase/migrations/         # PostgreSQL schema migrations (ALTER TABLE add-column)
│
├── assets/
│   └── templates/               # VERSIONED STATIC TEMPLATE STORAGE
│       ├── blurpad_v1/
│       │   ├── template.json
│       │   └── preview.jpg
│       ├── podcast_split_v1/
│       │   ├── template.json
│       │   ├── overlay.png
│       │   └── preview.jpg
│       └── retro_vhs_v1/
│           ├── template.json
│           ├── overlay.png
│           └── preview.jpg
│
├── prompts/
│   ├── clip_analysis.txt       # System prompt for viral clips
│   └── seo_generation.txt      # System prompt for 3 headline options
│
├── public/                     # Mobile PWA Static Files
│   ├── index.html              # Single-Canvas PWA Interface (publish kit, quality selector, settings)
│   ├── styles.css              # CSS design system (warm cream)
│   ├── manifest.json            # Web App Manifest
│   └── service-worker.js        # Offline PWA service worker
│
├── modal_app.py                 # Modal container environment configuration
├── dev_server.py                # Local dev server (proxies /api/* to Modal)
├── design/                      # UI/UX design docs (mobile, web)
├── .env                        # Environment secrets
├── requirements.txt            # Dependencies
└── prd.md                      # Master PRD Document

```

***

## 4. VERSIONED TEMPLATE CONFIGURATION (`assets/templates/*_v1/template.json`)

All visual presentation layers are controlled by explicit JSON schemas. Templates are versioned (e.g., `podcast_split_v1`) to guarantee past jobs remain reproducible even if layout styles change in future releases.

```json
{
  "id": "podcast_split_v1",
  "name": "Podcast Split Screen v1",
  "description": "Square 1080x1080 video centered with PNG overlay frame and bottom animated subtitles.",
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  },
  "video_slot": {
    "width": 1080,
    "height": 1080,
    "x_offset": 0,
    "y_offset": 420,
    "fit_mode": "contain"
  },
  "overlay_image": "overlay.png",
  "subtitles": {
    "alignment": 2,
    "margin_v": 180,
    "font_name": "Montserrat ExtraBold",
    "font_size": 24,
    "primary_color": "&H00FFFFFF",
    "highlight_color": "&H0000FFFF",
    "outline_color": "&H00000000",
    "outline_width": 3
  }
}

```

***

## 5. DATABASE SCHEMA (SQLModel → Supabase PostgreSQL)

```python
from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel


class JobStatus(str, Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default="default")
    title: str = Field(default="Untitled Job")
    source_url: str
    template_id: str = Field(default="blurpad_v1")
    source_r2_key: Optional[str] = None       # R2 path if source was uploaded
    transcript_json: Optional[str] = None     # raw transcript for Generate More

    # SEO campaign / batch controls
    campaign_rules: Optional[str] = None
    max_clips: int = Field(default=5)
    preferred_height: Optional[int] = Field(default=720)  # Frame.io proxy height (0 = original)

    status: JobStatus = Field(default=JobStatus.PENDING)
    progress_percentage: int = Field(default=0)
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    clips: List["VideoClip"] = Relationship(back_populates="job")


class VideoClip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")

    start_time: float
    end_time: float
    duration: float
    r2_url: str                              # storage path under /mnt/data/clips

    # 3 Distinct Catchy Headline Variations
    title_curiosity: str
    title_direct: str
    title_question: str

    description: str
    hashtags: str
    deleted: bool = Field(default=False)     # soft delete
    posted_platforms: Optional[str] = Field(default="[]")  # JSON: ["tiktok","youtube","instagram"]

    created_at: datetime = Field(default_factory=datetime.utcnow)
    job: Optional[Job] = Relationship(back_populates="clips")

```

> **Migrations:** Schema changes are applied to the existing Supabase database via `supabase/migrations/*.sql` (e.g. `add_job_preferred_height.sql`, `add_clip_posted_platforms.sql`) and executed through the Supabase MCP/CLI. `create_all` only creates missing tables — it does not alter existing ones.

***

## 6. PROMPT & RESILIENCY RULES

### 6.1 Groq & DeepSeek API Auto-Retry Rule

All API interactions must incorporate exponential backoff retries via `tenacity` to handle transient network limits (e.g., HTTP 429 or timeouts):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def call_deepseek_with_retry(prompt: str) -> dict:
    # Calls DeepSeek Chat API
    ...

```

### 6.2 SEO & Catchy Title Generation (`prompts/seo_generation.txt`)

DeepSeek is instructed to output 3 distinct headline formats per clip:

```text
You are a viral social media headline writer. For the provided short clip transcript, generate exactly 3 title variations and metadata in valid JSON.

SCHEMA:
{
  "title_curiosity": "Curiosity hook under 60 chars (e.g., 'Why 90% of Coders Fail This Test...')",
  "title_direct": "Bold, punchy statement (e.g., 'Stop Using This Framework in 2026.')",
  "title_question": "Engaging question (e.g., 'Is This the End of Traditional Coding?')",
  "description": "Engaging 2-sentence summary with call to action.",
  "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5"
}

```

***

## 7. API SPECIFICATION

### `POST /api/jobs`

Initializes a video rendering job from a source URL.

- **Request (JSON):**

```json
{
  "title": "My Long Video",
  "source_url": "https://www.youtube.com/watch?v=...",
  "template_id": "blurpad_v1",
  "campaign_rules": "SEI, crypto affiliate channel",
  "max_clips": 5,
  "preferred_height": 1080,
  "cookies": "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t...\t..."
}
```

| Field              | Type | Default          | Notes                                                              |
| ------------------ | ---- | ---------------- | ------------------------------------------------------------------ |
| `title`            | str  | `"Untitled Job"` | Job display name                                                   |
| `source_url`       | str  | required         | Any http(s) video link (YouTube, TikTok, Instagram, Google Drive, Frame.io, direct file) — resolved via yt-dlp |
| `template_id`      | str  | `"blurpad_v1"`   | Template used for rendering                                        |
| `campaign_rules`   | str  | `""`             | SEO campaign instructions for the clip analyzer                    |
| `max_clips`        | int  | `5`              | Maximum clips to generate                                          |
| `preferred_height` | int  | `1080`           | Caps download/Frame.io proxy height; `0` = original full file (360/540/720/1080) |
| `cookies`          | str  | `null`           | Optional Netscape-format cookies.txt content (export via "Get cookies.txt LOCALLY" extension). Authorizes login-walled / bot-blocked sources (YouTube on cloud IPs, TikTok, Instagram). Persisted per job on the Volume and passed to yt-dlp as `--cookies`. Never returned by any endpoint. |

- **Response** **`202 Accepted`:**

```json
{
  "job_id": 42,
  "status": "PENDING",
  "message": "Job dispatched to Modal."
}
```

### `POST /api/jobs/upload`

Initializes a job from a local file upload (multipart form-data).

- **Request:** `multipart/form-data` with `file` (up to 500 MB), `template_id`, `campaign_rules`, `max_clips`.
- **Response:** `202 Accepted` with `job_id` + `status: "PENDING"`.

### `GET /api/jobs`

Fetches a list of all past jobs and their associated clips for the Mobile PWA History screen.

- **Response** **`200 OK`:**

```json
[
  {
    "job_id": 42,
    "title": "My Long Video",
    "template_id": "blurpad_v1",
    "status": "COMPLETED",
    "created_at": "2026-03-31T10:00:00Z",
    "clips_count": 4,
    "clips": [
      {
        "clip_id": 101,
        "r2_url": "/mnt/data/clips/42_101.mp4",
        "duration": 45.0,
        "titles": {
          "curiosity": "Why 90% of Coders Fail This Test...",
          "direct": "Stop Using This Framework in 2026.",
          "question": "Is This the End of Traditional Coding?"
        },
        "description": "A deep dive into software engineering trends.",
        "hashtags": "#coding #tech #software #2026",
        "posted_platforms": ["tiktok"]
      }
    ]
  }
]
```

### `GET /api/jobs/{job_id}`

Full job detail with clips (used when opening a job drawer).

### `GET /api/jobs/{job_id}/poll`

- **Protocol:** HTTP GET polling (every 2s from frontend)
- **Response:** Lightweight status JSON from Modal Volume status file
- **Emits:** `{"status": "RENDERING", "progress": 80}` until job reaches `COMPLETED` or `FAILED`.

### `POST /api/jobs/{job_id}/generate-more`

Generates additional clips for an existing job. Body: `{"count": 3}`.

### Clip Vault endpoints

| Endpoint                           | Method | Purpose                                                                                 |
| ---------------------------------- | ------ | --------------------------------------------------------------------------------------- |
| `GET /api/clips`                   | GET    | List all clips with SEO metadata + `posted_platforms`                                   |
| `GET /api/clips/{id}/download`     | GET    | Stream MP4 file (serves from Modal Volume)                                              |
| `POST /api/clips/{id}/refresh-seo` | POST   | Regenerate titles/description/hashtags via DeepSeek                                     |
| `POST /api/clips/{id}/posted`      | POST   | Toggle posted platform. Body: `{"platform": "tiktok"}` (tiktok \| youtube \| instagram) |
| `DELETE /api/clips/{id}`           | DELETE | Soft-delete a clip                                                                      |

### `GET /api/templates`

Lists available templates (id, name, description, preview URL).

***

## 8. MOBILE PWA INTERFACE REQUIREMENTS

1. **Dashboard View:**

- URL input field + horizontal template picker (`blurpad_v1`, `podcast_split_v1`).
- Primary action button: **"Generate 9:16 Shorts"** (or local file upload).
- Job progress via HTTP polling every 2s (SSE retired).

1. **Campaign Settings Drawer:**

- **Campaign rules** textarea (e.g. "SEI, crypto affiliate channel").
- **Max clips** slider (1–10).
- **Source Quality** selector — Frame.io only: 360p / 540p / 720p (default) / 1080p / Original.
- **Your Link** field (Vyro profile / affiliate link) appended to publish captions. Stored in `localStorage`.

1. **Job History View:**

- History cards grouped with job title, status, and clip count.
- One-tap access to re-download video clips anytime without re-processing.

1. **Clip Action Drawer:**

- Vertical $9:16$ HTML5 video preview player.
- **Copy Title**, **Copy Hashtags**, **Refresh SEO**, and **Download MP4** buttons.
- **Publish section:** one button per platform (**TikTok / YouTube Shorts / IG Reels**) that copies a platform-formatted caption (title + hashtags + link), downloads the MP4, and opens the platform's upload page. A **Mark / ✓ Posted** toggle per platform persists to `posted_platforms` so clips are never double-posted.

