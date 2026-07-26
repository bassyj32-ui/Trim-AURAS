import asyncio
import json
from pathlib import Path
from typing import Optional

import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import MODAL
from app.database import engine
from app.models import Job, JobStatus, VideoClip, clip_vault_cutoff
from app.api.sse import event_stream
from app.pipeline.orchestrator import execute_pipeline, generate_more_clips, refresh_clip_seo
from app.storage import generate_presigned_url

router = APIRouter(prefix="/api", tags=["api"])

TEMPLATES_DIR = Path("assets") / "templates"

# ---------------------------------------------------------------------------
# Modal-aware dispatch — on Modal we spawn a cloud function;
# locally we use asyncio.create_task
# ---------------------------------------------------------------------------
if MODAL:
    import modal as _modal

    async def _dispatch_pipeline(job_id: int):
        await _modal.Function.from_name("trimaura", "process_pipeline").spawn.aio(
            job_id
        )

    async def _dispatch_generate_more(job_id: int, count: int = 3):
        await _modal.Function.from_name(
            "trimaura", "process_generate_more"
        ).spawn.aio(job_id, count)

else:

    async def _dispatch_pipeline(job_id: int):
        asyncio.create_task(execute_pipeline(job_id))

    async def _dispatch_generate_more(job_id: int, count: int = 3):
        asyncio.create_task(generate_more_clips(job_id, count=count))


# --- Schemas ---

class CreateJobRequest(BaseModel):
    title: str = "Untitled Job"
    source_url: str
    template_id: str = "blurpad_v1"
    campaign_rules: Optional[str] = None
    max_clips: int = 5


class CreateJobResponse(BaseModel):
    job_id: int
    status: str
    message: str


class GenerateMoreRequest(BaseModel):
    count: int = 3


# --- Job Endpoints ---

@router.post("/jobs", status_code=202)
async def create_job(body: CreateJobRequest):
    with Session(engine) as session:
        job = Job(
            title=body.title,
            source_url=body.source_url,
            template_id=body.template_id,
            campaign_rules=body.campaign_rules,
            max_clips=body.max_clips,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    await _dispatch_pipeline(job_id)

    return CreateJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Job dispatched.",
    )


@router.post("/jobs/upload", status_code=202)
async def upload_job(
    file: UploadFile = File(...),
    template_id: str = "blurpad_v1",
    campaign_rules: Optional[str] = Form(None),
    max_clips: int = Form(5),
):
    suffix = Path(file.filename).suffix if file.filename else ".mp4"
    tmp_path = tempfile.mktemp(suffix=suffix)
    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    with Session(engine) as session:
        job = Job(
            title=file.filename or "Untitled Upload",
            source_url=tmp_path,
            template_id=template_id,
            campaign_rules=campaign_rules,
            max_clips=max_clips,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    await _dispatch_pipeline(job_id)

    return CreateJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Upload received, job dispatched.",
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        clips_data = [
            {
                "clip_id": c.id,
                "r2_url": c.r2_url,
                "duration": c.duration,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "titles": {
                    "curiosity": c.title_curiosity,
                    "direct": c.title_direct,
                    "question": c.title_question,
                },
                "description": c.description,
                "hashtags": c.hashtags,
                "created_at": c.created_at.isoformat(),
            }
            for c in job.clips
            if not c.deleted
        ]
        return {
            "job_id": job.id,
            "title": job.title,
            "template_id": job.template_id,
            "status": job.status,
            "progress": job.progress_percentage,
            "error": job.error_message,
            "campaign_rules": job.campaign_rules,
            "max_clips": job.max_clips,
            "created_at": job.created_at.isoformat(),
            "clips": clips_data,
        }


@router.get("/jobs/{job_id}/poll")
def poll_job_status(job_id: int):
    """Lightweight polling endpoint used by the frontend on Modal.

    Reads a JSON status file (written by the background pipeline function)
    so the frontend doesn't hit SQLite on every poll cycle.
    Falls back to the DB query if the file hasn't been written yet.
    """
    if MODAL:
        status_path = Path("/mnt/data/status") / f"job_{job_id}.json"
        if status_path.exists():
            return json.loads(status_path.read_text())

    # Fallback: read directly from SQLite
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return {
            "status": job.status,
            "progress": job.progress_percentage,
            "error": job.error_message,
        }


@router.get("/jobs/{job_id}/stream")
def stream_job(job_id: int):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

    return StreamingResponse(
        event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs")
def list_jobs():
    with Session(engine) as session:
        jobs = session.exec(
            select(Job).order_by(Job.created_at.desc())
        ).all()
        return [
            {
                "job_id": j.id,
                "title": j.title,
                "template_id": j.template_id,
                "status": j.status,
                "created_at": j.created_at.isoformat(),
                "clips_count": len([c for c in j.clips if not c.deleted]),
            }
            for j in jobs
        ]


# --- Generate More Clips ---

@router.post("/jobs/{job_id}/generate-more", status_code=202)
async def api_generate_more(job_id: int, body: GenerateMoreRequest = GenerateMoreRequest()):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if not job.source_r2_key or not job.transcript_json:
            raise HTTPException(
                400,
                "Job has no saved source or transcript. Run the initial pipeline first.",
            )

    await _dispatch_generate_more(job_id, count=body.count)

    return {
        "job_id": job_id,
        "status": JobStatus.ANALYZING,
        "message": f"Generating {body.count} more clips.",
    }


# --- Clip Vault Endpoints ---

@router.get("/clips")
def list_clips():
    cutoff = clip_vault_cutoff()
    with Session(engine) as session:
        clips = session.exec(
            select(VideoClip)
            .where(VideoClip.deleted == False)
            .where(VideoClip.created_at >= cutoff)
            .order_by(VideoClip.created_at.desc())
        ).all()

        return [
            {
                "clip_id": c.id,
                "job_id": c.job_id,
                "r2_url": c.r2_url,
                "duration": c.duration,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "titles": {
                    "curiosity": c.title_curiosity,
                    "direct": c.title_direct,
                    "question": c.title_question,
                },
                "description": c.description,
                "hashtags": c.hashtags,
                "created_at": c.created_at.isoformat(),
            }
            for c in clips
        ]


@router.post("/clips/{clip_id}/refresh-seo")
async def api_refresh_seo(clip_id: int):
    try:
        seo_data = await refresh_clip_seo(clip_id)
        return {
            "clip_id": clip_id,
            "status": "ok",
            "titles": {
                "curiosity": seo_data.get("title_curiosity", ""),
                "direct": seo_data.get("title_direct", ""),
                "question": seo_data.get("title_question", ""),
            },
            "description": seo_data.get("description", ""),
            "hashtags": seo_data.get("hashtags", ""),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: int):
    with Session(engine) as session:
        clip = session.get(VideoClip, clip_id)
        if not clip:
            raise HTTPException(404, "Clip not found")
        clip.deleted = True
        session.add(clip)
        session.commit()
    return {"status": "deleted"}


@router.get("/clips/{clip_id}/download")
async def download_clip(clip_id: int):
    with Session(engine) as session:
        clip = session.get(VideoClip, clip_id)
        if not clip or clip.deleted:
            raise HTTPException(404, "Clip not found")

    # On Modal, try to serve directly from the Volume first
    if MODAL:
        vol_path = Path(f"/mnt/data/clips/{clip.job_id}_{clip.id}.mp4")
        if vol_path.exists():
            return FileResponse(
                vol_path,
                media_type="video/mp4",
                filename=f"trimaura_clip_{clip.id}.mp4",
            )

    # Fallback: presigned R2 URL or direct public URL
    if clip.r2_key:
        url = generate_presigned_url(clip.r2_key)
        if url:
            return {"download_url": url}

    # Last resort: the raw stored URL (local path or R2 public)
    return {"download_url": clip.r2_url}


# --- Templates ---

@router.get("/templates")
def list_templates():
    if not TEMPLATES_DIR.exists():
        return []
    results = []
    for folder in sorted(TEMPLATES_DIR.iterdir()):
        if folder.is_dir():
            config_path = folder / "template.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                results.append({
                    "id": config.get("id", folder.name),
                    "name": config.get("name", folder.name),
                    "description": config.get("description", ""),
                })
    return results
