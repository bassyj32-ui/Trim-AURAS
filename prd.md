Here is your final, complete, and production-ready **Master Product Requirement Document (PRD v3.2)**.

It incorporates the **Modal serverless architecture**, **template-driven layouts with folder versioning**, **API retry resiliency**, **3 catchy title options per clip**, and a **Mobile Job History view**.

***

# PRODUCT REQUIREMENT DOCUMENT (PRD) - v3.2

## PROJECT NAME: TrimAURA

**Tagline:** High-speed, template-driven $16:9 \rightarrow 9:16$ short-form video re-framing & caption engine.

**Target Platform:** Mobile-First PWA (iOS/Android) & Web

**Primary Architecture:** FastAPI + SQLModel (Supabase PostgreSQL) + Modal.com (Serverless FFmpeg Execution) + Groq Whisper V3 Turbo + DeepSeek Chat + Modal Volume (fallback) + Cloudflare R2 (CDN).

***

## 1. VISION & ARCHITECTURE OVERVIEW

TrimAURA converts long-form horizontal videos (YouTube links, Google Drive files) into viral $9:16$ vertical shorts (TikToks, Reels, Shorts).

It is designed to be operated from a **mobile phone PWA** while all heavy compute tasks (downloading, transcribing, AI hook selection, FFmpeg rendering) are offloaded to **Modal.com cloud containers**.

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
│  1. yt-dlp / GDrive Download to Ephemeral Workspace    │
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
│   ├── database.py              # SQLModel engine & SQLite WAL initialization
│   ├── models.py                # SQLModel schema (Job, VideoClip, Enums)
│   ├── storage.py               # Cloudflare R2 upload helpers
│   │
│   ├── api/
│   │   ├── routes.py            # REST endpoints (Jobs, Templates, History)
│   │   └── sse.py              # Real-time progress SSE stream
│   │
│   └── pipeline/
│       ├── orchestrator.py      # Modal worker execution controller
│       ├── downloader.py       # Phase 1: yt-dlp & GDrive parser
│       ├── transcriber.py      # Phase 2: Groq Whisper V3 (with Tenacity retry)
│       ├── intelligence.py     # Phase 3: DeepSeek viral moment extractor & titles
│       ├── video_editor.py     # Phase 4: FFmpeg template applier & renderer
│       └── seo_generator.py    # Phase 5: DeepSeek SEO title & hashtag builder
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
│   ├── index.html              # Single-Canvas PWA Interface
│   ├── manifest.json            # Web App Manifest
│   └── service-worker.js        # Offline PWA service worker
│
├── modal_app.py                 # Modal container environment configuration
├── .env                        # Environment secrets
├── requirements.txt            # Dependencies
└── TRIMAURA_PRD.md             # Master PRD Document

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

## 5. DATABASE SCHEMA (SQLModel)

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
    title: str = Field(default="Untitled Job")
    source_url: str
    template_id: str = Field(default="blurpad_v1")
    
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
    r2_url: str
    
    # 3 Distinct Catchy Headline Variations
    title_curiosity: str
    title_direct: str
    title_question: str
    
    description: str
    hashtags: str
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    job: Optional[Job] = Relationship(back_populates="clips")

```

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

Initializes a video rendering job.

- **Request (JSON):**

```json
{
  "title": "Lex Fridman Podcast #410",
  "source_url": "https://www.youtube.com/watch?v=example",
  "template_id": "podcast_split_v1"
}

```

- **Response** **`202 Accepted`:**

```json
{
  "job_id": 42,
  "status": "PENDING",
  "message": "Job dispatched to Modal."
}

```

### `GET /api/jobs/history`

Fetches a list of all past jobs and their associated clips for the Mobile PWA History screen.

- **Response** **`200 OK`:**

```json
[
  {
    "job_id": 42,
    "title": "Lex Fridman Podcast #410",
    "template_id": "podcast_split_v1",
    "status": "COMPLETED",
    "created_at": "2026-03-31T10:00:00Z",
    "clips_count": 4,
    "clips": [
      {
        "clip_id": 101,
        "r2_url": "https://r2.trimaura.com/clips/clip_42_1.mp4",
        "duration": 45.0,
        "titles": {
          "curiosity": "Why 90% of Coders Fail This Test...",
          "direct": "Stop Using This Framework in 2026.",
          "question": "Is This the End of Traditional Coding?"
        },
        "description": "A deep dive into software engineering trends.",
        "hashtags": "#coding #tech #software #2026"
      }
    ]
  }
]

```

### `GET /api/jobs/{job_id}/poll` (Replaces SSE)

- **Protocol:** HTTP GET polling (every 2s from frontend)
- **Response:** Lightweight status JSON from Modal Volume status file
- **Emits:** `{"status": "RENDERING", "progress": 80}` until job reaches `COMPLETED` or `FAILED`.

***

## 8. MOBILE PWA INTERFACE REQUIREMENTS

1. **Dashboard View:**

- URL input field + horizontal template picker (`blurpad_v1`, `podcast_split_v1`).
- Primary action button: **"Generate 9:16 Shorts"**.
- Real-time progress bar powered by SSE connection.

1. **Job History View:**

- Grouped history cards (*"Yesterday — Lex Fridman Podcast (4 Clips)"*).
- One-tap access to re-download video clips anytime without re-processing.

1. **Clip Action Drawer:**

- Vertical $9:16$ HTML5 video preview player.
- Tabbed Title Selector: Choose between **Curiosity**, **Direct**, or **Question** headline, with a single **"Copy Title"** button.
- **"Copy Hashtags"** button and **"Download HD MP4"** button.

