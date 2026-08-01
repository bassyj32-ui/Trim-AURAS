"""
TrimAURA — Modal Serverless Deployment
========================================

Wraps the existing FastAPI backend into a Modal cloud app with:
  - Modal Volume for SQLite + rendered clips
  - ASGI web endpoint (min-containers=1 for fast polling)
  - Background pipeline (1200s timeout, R2/Volume fallback)
  - Status JSON files for lightweight frontend polling

Deploy:
  modal deploy modal_app.py
"""

from pathlib import Path

import modal

# ---------------------------------------------------------------------------
# Persistent Volume — SQLite, clips, status files
# ---------------------------------------------------------------------------
DATA_DIR = "/mnt/data"
STATUS_DIR = f"{DATA_DIR}/status"
CLIPS_DIR = f"{DATA_DIR}/clips"
SOURCES_DIR = f"{DATA_DIR}/sources"

data_volume = modal.Volume.from_name("trimaura-data", create_if_missing=True)


# ---------------------------------------------------------------------------
# Custom Modal Image — ffmpeg + Python deps + local code baked in
# ---------------------------------------------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.30.0",
        "sqlmodel>=0.0.22",
        "boto3>=1.35.0",
        "groq>=0.9.0",
        "openai>=1.0.0",
        "yt-dlp>=2024.12.0",
        "psycopg2-binary>=2.9.0",
        "python-multipart>=0.0.12",
        "pydantic-settings>=2.4.0",
        "tenacity>=9.0.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "sentry-sdk>=2.0.0",
        "pywebpush>=1.14.0",
    )
    .env({"MODAL": "1"})
    .add_local_dir("./app", remote_path="/root/app", copy=True)
    .add_local_dir("./assets", remote_path="/root/assets", copy=True)
    .add_local_dir("./prompts", remote_path="/root/prompts", copy=True)
    .add_local_dir("./public", remote_path="/root/public", copy=True)
)


# ---------------------------------------------------------------------------
# Modal App
# ---------------------------------------------------------------------------
app = modal.App("trimaura")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_status(job_id: int, status: str, progress: int, error: str | None = None):
    """Write a lightweight JSON status file on the Volume for frontend polling."""
    Path(STATUS_DIR).mkdir(parents=True, exist_ok=True)
    payload = {"status": status, "progress": progress}
    if error:
        payload["error"] = error
    Path(f"{STATUS_DIR}/job_{job_id}.json").write_text(
        __import__("json").dumps(payload)
    )
    # Commit so the web container sees the new status file immediately
    # (without this, polls may read a stale file for a long time).
    try:
        data_volume.commit()
    except Exception as e:
        print(f"[status] volume commit failed (non-fatal): {e}")


def _ensure_path():
    """Make sure /root is on sys.path so `from app.xxx` imports resolve."""
    import os, sys

    cwd = os.getcwd()  # typically /root in Modal containers
    for p in (cwd, os.path.join(cwd, "app")):
        if p not in sys.path:
            sys.path.insert(0, p)


# ===========================================================================
# 1. ASGI Web Endpoint
# ===========================================================================
@app.function(
    image=image,
    volumes={DATA_DIR: data_volume},
    secrets=[
        modal.Secret.from_name("trimaura-secrets-v2"),
        modal.Secret.from_name("trimaura-supabase-keys"),
        modal.Secret.from_name("trimaura-db-url"),
    ],
    scaledown_window=120,
)
@modal.asgi_app()
def fastapi_app():
    _ensure_path()

    for d in (STATUS_DIR, CLIPS_DIR, SOURCES_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)

    # Auto-cleanup old failed/pending jobs on startup
    try:
        from app.database import engine, init_db
        from app.models import Job, JobStatus
        from sqlmodel import Session, select
        from datetime import datetime, timedelta

        init_db()
        cutoff = datetime.utcnow() - timedelta(hours=24)
        # Anything not COMPLETED that's been alive >24h is stuck (pipeline max is 1h).
        stale_statuses = [
            JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.TRANSCRIBING,
            JobStatus.ANALYZING, JobStatus.RENDERING, JobStatus.FAILED,
        ]
        with Session(engine) as session:
            old_jobs = session.exec(
                select(Job).where(Job.created_at < cutoff).where(
                    Job.status.in_(stale_statuses)
                )
            ).all()
            for j in old_jobs:
                for c in j.clips:
                    c.deleted = True
                    session.add(c)
                session.delete(j)
            session.commit()
            if old_jobs:
                print(f"[Startup] Cleaned up {len(old_jobs)} old failed/pending jobs")
    except Exception as e:
        print(f"[Startup] Cleanup error (non-fatal): {e}")

    from app.main import app as _fastapi_app

    return _fastapi_app


# ===========================================================================
# 2. Background Pipeline Functions
# ===========================================================================
# Shared kwargs for pipeline functions
_PIPELINE_KWARGS = dict(
    image=image,
    volumes={DATA_DIR: data_volume},
    secrets=[
        modal.Secret.from_name("trimaura-secrets-v2"),
        modal.Secret.from_name("trimaura-supabase-keys"),
        modal.Secret.from_name("trimaura-db-url"),
    ],
    # 2 CPU per pipeline container: render is CPU-bound (libx264), so this
    # roughly halves per-clip render wall-clock under back-to-back load.
    cpu=2.0,
    scaledown_window=300,
    retries=0,
)


@app.function(timeout=3600, **_PIPELINE_KWARGS)
def process_pipeline(job_id: int, job_data: dict | None = None):
    _write_status(job_id, "DOWNLOADING", 10)
    try:
        _ensure_path()

        from app.database import engine, init_db

        init_db()

        # If the job record written by the ASGI container isn't visible yet
        # (Modal Volume propagation delay), create it locally from the payload
        # that was passed alongside job_id.
        if job_data is not None:
            from sqlmodel import Session
            from app.models import Job

            with Session(engine) as session:
                existing = session.get(Job, job_id)
                if existing is None:
                    job = Job(**{k: v for k, v in job_data.items() if k != "id"})
                    job.id = job_id
                    session.add(job)
                    session.commit()

        import asyncio
        from app.pipeline.orchestrator import execute_pipeline

        # Wait for the uploaded source file to appear on the Volume (it was
        # written by the ASGI container and may not have synced yet). Reload
        # each iteration with a FRESH handle — Modal volumes don't auto-
        # propagate between containers; only a reload() sees another
        # container's commit, and a fresh from_name() handle is required to
        # pick up the latest volume state.
        import os, time
        if job_data and "source_url" in job_data and job_data["source_url"].startswith("/mnt/data/"):
            waited = 0
            found = False
            for _ in range(120):  # up to ~120 seconds
                try:
                    modal.Volume.from_name("trimaura-data").reload()
                except Exception as e:
                    print(f"[pipeline] volume reload failed (non-fatal): {e}")
                if os.path.exists(job_data["source_url"]):
                    print(f"Source file found after ~{waited}s: {job_data['source_url']}")
                    found = True
                    break
                time.sleep(1)
                waited += 1
            if not found:
                # Bulletproof fallback: read the file server-side from the
                # volume API, bypassing the local mount (which may never
                # refresh even after reload()).
                try:
                    rel = job_data["source_url"].replace("/mnt/data/", "", 1)
                    data = modal.Volume.from_name("trimaura-data").read_file(rel)
                    Path(job_data["source_url"]).parent.mkdir(parents=True, exist_ok=True)
                    with open(job_data["source_url"], "wb") as fh:
                        fh.write(data)
                    print(f"[pipeline] source recovered via read_file: {job_data['source_url']} ({len(data)} bytes)")
                except Exception as e:
                    print(f"Source file NOT found after {waited}s: {job_data['source_url']} "
                          f"(read_file fallback failed: {e})")

        asyncio.run(execute_pipeline(job_id))
        _sync_clips_to_volume(job_id)
        _write_status(job_id, "COMPLETED", 100)
    except Exception as exc:
        # Best-effort: publish whatever clips were already rendered+committed
        # so a mid-render failure doesn't lose the work that succeeded.
        try:
            _sync_clips_to_volume(job_id)
        except Exception as sync_exc:
            print(f"[pipeline] failed-path clip sync error (non-fatal): {sync_exc}")
        _write_status(job_id, "FAILED", 0, str(exc))
        raise


@app.function(timeout=600, **_PIPELINE_KWARGS)
def process_generate_more(job_id: int, count: int = 3):
    _write_status(job_id, "ANALYZING", 40)
    try:
        _ensure_path()

        import asyncio
        from app.pipeline.orchestrator import generate_more_clips

        asyncio.run(generate_more_clips(job_id, count=count))
        _sync_clips_to_volume(job_id)
        _write_status(job_id, "COMPLETED", 100)
    except Exception as exc:
        _write_status(job_id, "FAILED", 0, str(exc))
        raise


def _sync_clips_to_volume(job_id: int):
    """Copy locally-rendered clips to the Volume so they can be served
    by the `/api/clips/{id}/download` endpoint."""
    import shutil
    from sqlmodel import Session
    from app.database import engine
    from app.models import VideoClip

    with Session(engine) as session:
        clips = (
            session.query(VideoClip)
            .filter(VideoClip.job_id == job_id, VideoClip.deleted == False)
            .all()
        )
        for clip in clips:
            local_path = clip.r2_url
            if local_path and Path(local_path).exists():
                dest = Path(CLIPS_DIR) / f"{job_id}_{clip.id}.mp4"
                if Path(local_path) == dest:
                    continue  # already in place on the Volume
                shutil.copy2(local_path, str(dest))
                clip.r2_url = str(dest)  # Volume path, readable by download endpoint
                session.add(clip)
        session.commit()
        # Force Volume commit so the web container can see the new files immediately
        data_volume.commit()


# ===========================================================================
# 3. Entrypoint — verify image builds
# ===========================================================================
@app.local_entrypoint()
def build_check():
    import subprocess

    subprocess.run(["ffmpeg", "-version"], check=True)
    print("✅ Image build verified — ffmpeg + deps ready.")
    print('Run  » modal deploy modal_app.py  «  to deploy.')
