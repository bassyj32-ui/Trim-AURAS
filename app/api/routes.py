import asyncio
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.sse import event_stream
from app.auth import get_current_user
from app.config import MODAL, settings
from app.database import engine
from app.models import (
    Job,
    JobStatus,
    MonthlyUsage,
    PushSubscription,
    VideoClip,
    clip_vault_cutoff,
)
from app.pipeline.downloader import _is_youtube
from app.pipeline.orchestrator import (
    execute_pipeline,
    generate_more_clips,
    refresh_clip_seo,
    save_job_cookies,
    trim_clip,
)
from app.probe import clamp_render_height, probe_and_check
from app.quotas import (
    check_burst,
    check_clip_quota,
    check_create_job_quota,
    deduct_credits,
    get_usage_summary,
)
from app.ssrf import validate_source_url
from app.storage import generate_presigned_url

router = APIRouter(prefix="/api", tags=["api"])

TEMPLATES_DIR = Path("assets") / "templates"

# ---------------------------------------------------------------------------
# Modal-aware dispatch — on Modal we spawn a cloud function;
# locally we use asyncio.create_task
# ---------------------------------------------------------------------------
if MODAL:
    import modal as _modal

    async def _dispatch_pipeline(job_id: int, job_data: dict | None = None):
        await _modal.Function.from_name("trimaura", "process_pipeline").spawn.aio(
            job_id, job_data
        )

    async def _dispatch_generate_more(job_id: int, count: int = 3):
        await _modal.Function.from_name(
            "trimaura", "process_generate_more"
        ).spawn.aio(job_id, count)

    async def _dispatch_trim_clip(clip_id: int, new_start: float, new_end: float):
        await _modal.Function.from_name("trimaura", "process_trim_clip").spawn.aio(
            clip_id, new_start, new_end
        )

else:

    async def _dispatch_pipeline(job_id: int, job_data: dict | None = None):
        asyncio.create_task(execute_pipeline(job_id))

    async def _dispatch_generate_more(job_id: int, count: int = 3):
        asyncio.create_task(generate_more_clips(job_id, count=count))

    async def _dispatch_trim_clip(clip_id: int, new_start: float, new_end: float):
        asyncio.create_task(trim_clip(clip_id, new_start, new_end))


# --- Schemas ---

class CreateJobRequest(BaseModel):
    title: str = "Untitled Job"
    source_url: str
    template_id: str = "auto"  # "auto" = best-fit template by genre; or a specific id like "gaming_neon_v1"
    campaign_rules: str | None = None
    max_clips: int = 5
    preferred_height: int | None = 1080  # Caps download/Frame.io proxy height; 0 = original file
    cookies: str | None = None  # Netscape cookies.txt content (for login-walled / bot-blocked sources)
    burn_captions: bool = False  # Burn animated word-level captions (karaoke, Opus-style)
    trim_silence: bool = False  # Cut inter-word pauses >0.5s for punchier clips


class TrimClipRequest(BaseModel):
    start: float  # New clip boundary in source-video seconds (tightened only)
    end: float


class CreateJobResponse(BaseModel):
    job_id: int
    status: str
    message: str


class GenerateMoreRequest(BaseModel):
    count: int = 3


class TogglePostedRequest(BaseModel):
    platform: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict = {}


_PLATFORM_KEYS = ("tiktok", "youtube", "instagram")


def _clip_posted(clip: VideoClip) -> list[str]:
    """Parse a clip's posted_platforms JSON text into a list."""
    try:
        raw = json.loads(clip.posted_platforms or "[]")
        return [p for p in raw if p in _PLATFORM_KEYS]
    except Exception:
        return []


# --- Job Endpoints ---

# Any http(s) link is accepted — yt-dlp resolves YouTube, TikTok, Instagram,
# Google Drive, Frame.io, etc. Direct video file URLs also work.
_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".wmv", ".mts", ".m2ts")


def _form_bool(value: str | None) -> bool:
    """Coerce a multipart Form boolean to a real Python bool.

    SQLModel table models do NOT validate/coerce on construction (verified:
    Job(burn_captions='true') stores the raw string), so a raw Form string
    would be written straight into a Postgres BOOLEAN column and fail at
    commit. Normalize 'true'/'false'/'1'/'0'/'yes'/'no'/'on'/'off' here.
    """
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _owned_job(session: Session, job_id: int, user_id: str) -> Job:
    """Fetch a job and 404 unless it belongs to the caller (no existence leak)."""
    job = session.get(Job, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(404, "Job not found")
    return job


def _owned_clip(session: Session, clip_id: int, user_id: str) -> VideoClip:
    """Fetch a non-deleted clip and 404 unless its job belongs to the caller."""
    clip = session.get(VideoClip, clip_id)
    if not clip or clip.deleted:
        raise HTTPException(404, "Clip not found")
    job = session.get(Job, clip.job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(404, "Clip not found")
    return clip


@router.post("/jobs", status_code=202)
async def create_job(body: CreateJobRequest, user: dict = Depends(get_current_user)):
    # Quotas first — fail fast before any Modal worker is spawned.
    check_burst(user["id"], "job")

    # Server-side clamp so a client can't ask for 99 clips and burn compute.
    max_clips = max(1, min(body.max_clips or 1, settings.quota_max_clips_per_job))

    url = (body.source_url or "").strip().lower()
    if url and not url.startswith(("http://", "https://")) and not url.endswith(_VIDEO_EXTS):
        raise HTTPException(
            400,
            "Source must be an http(s) video link (TikTok, Instagram, "
            "Google Drive, Frame.io, ...) or a direct video file URL",
        )

    # SSRF guard — block private/localhost/metadata destinations before the
    # pipeline hands the URL to yt-dlp/ffmpeg (which follow redirects).
    if url.startswith(("http://", "https://")):
        ssrf_error = validate_source_url(body.source_url)
        if ssrf_error:
            raise HTTPException(400, f"Source URL rejected: {ssrf_error}")

    # YouTube is disabled at this stage — reject it up-front so the user gets
    # a clear message instead of a job that dies in the download phase.
    if _is_youtube(body.source_url):
        raise HTTPException(
            400,
            "YouTube is disabled at this stage — use a direct video link "
            "(mp4/mov), Google Drive, Frame.io, or upload the file instead",
        )

    # Cost pre-flight: probe duration/resolution and reject over-cap sources
    # BEFORE a Modal worker is spawned (best-effort — a failed probe passes).
    # The probed duration also drives the monthly credit charge below.
    src_seconds: int | None = None
    if url.startswith(("http://", "https://")):
        probe_error, src_seconds = probe_and_check(
            body.source_url, is_local=False, cookies=body.cookies or ""
        )
        if probe_error:
            raise HTTPException(422, probe_error)

    # Tier quotas (jobs/day, concurrent, monthly credits) — now that we know
    # how many source minutes this job costs.
    check_create_job_quota(user["id"], src_seconds)

    # Cost cap: never render higher than quota_max_render_height (no 4K/8K encodes).
    pref_h = clamp_render_height(body.preferred_height)

    with Session(engine) as session:
        job = Job(
            user_id=user["id"],
            title=body.title,
            source_url=body.source_url,
            template_id=body.template_id,
            campaign_rules=body.campaign_rules,
            max_clips=max_clips,
            preferred_height=pref_h,
            burn_captions=body.burn_captions,
            trim_silence=body.trim_silence,
            source_seconds=src_seconds,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
        # Charge credits atomically with job creation (same session/commit).
        deduct_credits(user["id"], src_seconds, session)
        session.commit()

    # Persist optional cookies.txt so the pipeline worker (and later
    # generate-more re-downloads) can authorize YouTube/TikTok/Instagram.
    if body.cookies and body.cookies.strip():
        save_job_cookies(job_id, body.cookies)
        if MODAL:
            try:
                import modal as _modal
                _modal.Volume.from_name("trimaura-data").commit()
            except Exception as e:
                print(f"[jobs] cookies volume commit failed (non-fatal): {e}")

    # Send a payload so the Modal worker can recreate the job record locally
    # if the Volume hasn't synced yet. This bypasses SQLite staleness on Modal
    # shared Volumes.
    job_payload = {
        "id": job_id,
        "user_id": user["id"],
        "title": body.title,
        "source_url": body.source_url,
        "template_id": body.template_id,
        "campaign_rules": body.campaign_rules or "",
        "max_clips": max_clips,
        "preferred_height": pref_h,
        "cookies": body.cookies or "",
        "burn_captions": body.burn_captions,
        "trim_silence": body.trim_silence,
        "source_seconds": src_seconds,
        "status": JobStatus.PENDING,
    }
    await _dispatch_pipeline(job_id, job_payload)

    return CreateJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Job dispatched.",
    )


@router.post("/jobs/upload", status_code=202)
async def upload_job(
    file: UploadFile = File(...),
    template_id: str = "auto",
    campaign_rules: str | None = Form(None),
    max_clips: int = Form(5),
    preferred_height: int | None = Form(1080),  # match JSON route default; 0 = original
    burn_captions: str | None = Form(None),
    trim_silence: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    # Quotas first — fail fast before accepting the body / spawning work.
    check_burst(user["id"], "upload")

    # Server-side clamp for the multipart path too.
    max_clips = max(1, min(max_clips or 1, settings.quota_max_clips_per_job))

    suffix = Path(file.filename).suffix if file.filename else ".mp4"
    upload_dir = Path("/mnt/data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    local_path = str(upload_dir / f"{uuid.uuid4()}{suffix}")

    # Hard size cap so a client can't dump a multi-GB file into the Volume.
    max_bytes = settings.quota_max_upload_mb * 1024 * 1024
    written = 0
    with open(local_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            written += len(chunk)
            if written > max_bytes:
                f.close()
                Path(local_path).unlink(missing_ok=True)
                raise HTTPException(
                    413,
                    f"File too large — max {settings.quota_max_upload_mb}MB",
                )
            f.write(chunk)

    # Cost pre-flight: probe the saved file and reject over-cap sources BEFORE
    # a Modal worker is spawned. The file is local here, so ffprobe is fast
    # and reliable — this is the hard enforcement path. The probed duration
    # also drives the monthly credit charge below.
    probe_error, src_seconds = probe_and_check(local_path, is_local=True)
    if probe_error:
        Path(local_path).unlink(missing_ok=True)  # don't leave junk on the Volume
        raise HTTPException(422, probe_error)

    # Tier quotas (jobs/day, concurrent, monthly credits) now that we know the
    # source duration.
    check_create_job_quota(user["id"], src_seconds)

    # Coerce Form strings to real types BEFORE Job()/payload — SQLModel table
    # models don't validate or coerce, so a raw 'true' string would hit the
    # Postgres BOOLEAN column as-is and fail at commit (see _form_bool).
    burn_on = _form_bool(burn_captions)
    trim_on = _form_bool(trim_silence)
    # Cost cap: never render higher than quota_max_render_height (no 4K/8K encodes).
    pref_h = clamp_render_height(preferred_height)

    # Commit the Volume so the spawned pipeline worker can see the file
    # immediately (Modal only flushes volume writes when this container exits).
    if MODAL:
        try:
            import modal as _modal
            _modal.Volume.from_name("trimaura-data").commit()
        except Exception as e:
            print(f"[upload] volume commit failed (non-fatal): {e}")

    with Session(engine) as session:
        job = Job(
            user_id=user["id"],
            title=file.filename or "Untitled Upload",
            source_url=local_path,
            template_id=template_id,
            campaign_rules=campaign_rules,
            max_clips=max_clips,
            preferred_height=pref_h,
            burn_captions=burn_on,
            trim_silence=trim_on,
            source_seconds=src_seconds,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
        # Charge credits atomically with job creation (same session/commit).
        deduct_credits(user["id"], src_seconds, session)
        session.commit()

    # Send a payload so the Modal worker can recreate the job record locally
    # if the Volume hasn't synced yet. This bypasses SQLite staleness on Modal
    # shared Volumes.
    job_payload = {
        "id": job_id,
        "user_id": user["id"],
        "title": file.filename or "Untitled Upload",
        "source_url": local_path,
        "template_id": template_id,
        "campaign_rules": campaign_rules or "",
        "max_clips": max_clips,
        "preferred_height": pref_h,
        "burn_captions": burn_on,
        "trim_silence": trim_on,
        "source_seconds": src_seconds,
        "status": JobStatus.PENDING,
    }
    await _dispatch_pipeline(job_id, job_payload)

    return CreateJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Upload received, job dispatched.",
    )


# --- Tier + credits ---------------------------------------------------------

@router.get("/tiers")
def get_my_tier(user: dict = Depends(get_current_user)):
    """Current tier, monthly credit balance and caps (drives the quota UI)."""
    return get_usage_summary(user["id"])


class TopupRequest(BaseModel):
    credits: int = Field(ge=1, le=10000)


@router.post("/credits/topup")
def topup_credits(body: TopupRequest, user: dict = Depends(get_current_user)):
    """Admin-gated credit grant for testing — replaced by Stripe checkout when
    billing goes live. Credits are added on top of the tier's monthly allowance
    and are the hook the checkout/webhook will call.
    """
    admins = {e.strip() for e in (settings.admin_emails or "").split(",") if e.strip()}
    if (user.get("email") or "") not in admins:
        raise HTTPException(
            403,
            "Payments aren't wired yet — top-ups are admin-only for now.",
        )
    month = datetime.now(UTC).strftime("%Y-%m")
    with Session(engine) as session:
        usage = session.get(MonthlyUsage, (user["id"], month))
        if usage is None:
            usage = MonthlyUsage(user_id=user["id"], month=month)
            session.add(usage)
        usage.topup_credits += body.credits
        session.commit()
    return get_usage_summary(user["id"])


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: dict = Depends(get_current_user)):
    with Session(engine) as session:
        job = _owned_job(session, job_id, user["id"])
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
                "viral_score": c.viral_score,
                "posted_platforms": _clip_posted(c),
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
def poll_job_status(job_id: int, user: dict = Depends(get_current_user)):
    """Lightweight polling endpoint used by the frontend.

    Reads job status directly from the DB (Supabase is shared between the
    web container and pipeline workers, so it's always consistent). We
    deliberately avoid the legacy status-file fast path — volume files can
    be stale/absent on this container and caused flickering statuses.
    """
    with Session(engine) as session:
        job = _owned_job(session, job_id, user["id"])
        return {
            "status": job.status,
            "progress": job.progress_percentage,
            "error": job.error_message,
        }


@router.get("/jobs/{job_id}/diag")
def job_diag(job_id: int, user: dict = Depends(get_current_user)):
    """Stage-level diagnostics for a job (diagnostic suite).

    Returns the timestamped event log written by the pipeline orchestrator
    (see app/pipeline/orchestrator.py `_diag`) plus a per-stage breakdown
    (entered/exited timestamps, ok, duration_s, error). On Modal the log
    lives on the shared Volume; on local dev it's tmp/diag/job_{id}_diag.jsonl.
    """
    with Session(engine) as session:
        job = _owned_job(session, job_id, user["id"])
        base = {
            "job_id": job.id,
            "status": job.status,
            "error": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "source_url": (job.source_url or "")[:160],
        }

    if MODAL:
        try:
            import modal as _m

            _m.Volume.from_name("trimaura-data").reload()
        except Exception:
            pass
        path = Path("/mnt/data/diag") / f"job_{job_id}_diag.jsonl"
    else:
        path = Path("tmp") / "diag" / f"job_{job_id}_diag.jsonl"

    events = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    stages: dict[str, dict] = {}
    for ev in events:
        name = ev.get("stage")
        if not name:
            continue
        s = stages.setdefault(name, {})
        if ev.get("event") == "STAGE_ENTER":
            s["entered_at"] = ev["ts"]
        elif ev.get("event") == "STAGE_EXIT":
            s["exited_at"] = ev["ts"]
            s["ok"] = ev.get("ok")
            s["duration_s"] = ev.get("duration_s")
            s["error"] = ev.get("error")

    return {**base, "events": events, "stages": stages}


@router.get("/jobs/{job_id}/stream")
def stream_job(job_id: int, user: dict = Depends(get_current_user)):
    with Session(engine) as session:
        _owned_job(session, job_id, user["id"])

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
def list_jobs(user: dict = Depends(get_current_user)):
    with Session(engine) as session:
        jobs = session.exec(
            select(Job)
            .where(Job.user_id == user["id"])
            .order_by(Job.created_at.desc())
        ).all()
        # Avoid the N+1: count all non-deleted clips in ONE query instead of
        # touching j.clips (lazy load) for every job.
        clip_counts = {}
        if jobs:
            rows = session.exec(
                select(VideoClip.job_id).where(
                    VideoClip.deleted == False,
                    VideoClip.job_id.in_([j.id for j in jobs]),
                )
            ).all()
            clip_counts = dict(Counter(rows))
        return [
            {
                "job_id": j.id,
                "title": j.title,
                "template_id": j.template_id,
                "status": j.status,
                "created_at": j.created_at.isoformat(),
                "clips_count": clip_counts.get(j.id, 0),
            }
            for j in jobs
        ]


# --- Claim legacy data (pre-auth rows) ---

@router.post("/claim-legacy", status_code=200)
def claim_legacy(user: dict = Depends(get_current_user)):
    """Attach rows created before auth (user_id='default') to the caller.

    The first signed-in user gets the pre-existing jobs/clips (they are
    theirs). Idempotent — rows already owned by a user are never touched.
    """
    with Session(engine) as session:
        legacy = session.exec(
            select(Job).where(Job.user_id == "default")
        ).all()
        for j in legacy:
            j.user_id = user["id"]
            session.add(j)
        session.commit()
        return {"claimed": len(legacy)}


# --- Generate More Clips ---

@router.post("/jobs/{job_id}/generate-more", status_code=202)
async def api_generate_more(
    job_id: int,
    body: GenerateMoreRequest = GenerateMoreRequest(),
    user: dict = Depends(get_current_user),
):
    with Session(engine) as session:
        job = _owned_job(session, job_id, user["id"])
        if not job.transcript_json:
            raise HTTPException(
                400,
                "Job has no saved transcript. Run the initial pipeline first.",
            )
        job_ref = job

    # Quotas — burst throttle + per-job clip cap (clamp count server-side).
    check_burst(user["id"], "generate_more")
    check_clip_quota(job_ref, extra=body.count)
    count = max(1, min(body.count or 1, settings.quota_generate_more_max))

    await _dispatch_generate_more(job_id, count=count)

    return {
        "job_id": job_id,
        "status": JobStatus.ANALYZING,
        "message": f"Generating {count} more clips.",
    }


# --- Clip Vault Endpoints ---

@router.get("/clips")
def list_clips(user: dict = Depends(get_current_user)):
    cutoff = clip_vault_cutoff()
    with Session(engine) as session:
        clips = session.exec(
            select(VideoClip)
            .join(Job, VideoClip.job_id == Job.id)
            .where(Job.user_id == user["id"])
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
                "viral_score": c.viral_score,
                "posted_platforms": _clip_posted(c),
                "created_at": c.created_at.isoformat(),
            }
            for c in clips
        ]


@router.post("/clips/{clip_id}/refresh-seo")
async def api_refresh_seo(clip_id: int, user: dict = Depends(get_current_user)):
    check_burst(user["id"], "refresh_seo")
    with Session(engine) as session:
        _owned_clip(session, clip_id, user["id"])
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
def delete_clip(clip_id: int, user: dict = Depends(get_current_user)):
    with Session(engine) as session:
        clip = _owned_clip(session, clip_id, user["id"])
        clip.deleted = True
        session.add(clip)
        session.commit()
    return {"status": "deleted"}


@router.post("/clips/{clip_id}/posted")
def toggle_posted(
    clip_id: int,
    body: TogglePostedRequest,
    user: dict = Depends(get_current_user),
):
    """Mark/unmark a clip as posted to a platform (tiktok | youtube | instagram)."""
    platform = (body.platform or "").strip().lower()
    if platform not in _PLATFORM_KEYS:
        raise HTTPException(400, "Unsupported platform — use tiktok, youtube, or instagram")

    with Session(engine) as session:
        clip = _owned_clip(session, clip_id, user["id"])
        posted = _clip_posted(clip)
        if platform in posted:
            posted.remove(platform)
        else:
            posted.append(platform)
        clip.posted_platforms = json.dumps(posted)
        session.add(clip)
        session.commit()
        return {"clip_id": clip_id, "platform": platform, "posted_platforms": posted}


@router.post("/clips/{clip_id}/trim", status_code=202)
async def api_trim_clip(
    clip_id: int,
    body: TrimClipRequest,
    user: dict = Depends(get_current_user),
):
    """Tighten a rendered clip's boundaries and re-render from the source.

    New bounds must be strictly inside the clip's original start/end (the
    clip can only get shorter, never longer). The worker re-renders with the
    job's saved source + transcript and updates the clip row in place.
    """
    if body.start >= body.end:
        raise HTTPException(400, "start must be < end")
    check_burst(user["id"], "trim")
    with Session(engine) as session:
        clip = _owned_clip(session, clip_id, user["id"])
        if body.start < clip.start_time or body.end > clip.end_time:
            raise HTTPException(
                400,
                f"New boundaries must be inside the original clip "
                f"({clip.start_time:.2f}s–{clip.end_time:.2f}s)",
            )
        original_start, original_end = clip.start_time, clip.end_time

    await _dispatch_trim_clip(clip_id, body.start, body.end)

    return {
        "clip_id": clip_id,
        "status": "processing",
        "message": (
            f"Re-rendering clip from {body.start:.2f}s to {body.end:.2f}s "
            f"(original {original_start:.2f}s–{original_end:.2f}s)."
        ),
    }


@router.get("/clips/{clip_id}/download")
async def download_clip(clip_id: int, user: dict = Depends(get_current_user)):
    with Session(engine) as session:
        clip = _owned_clip(session, clip_id, user["id"])

    # On Modal, try to serve directly from the Volume first
    if MODAL:
        vol_path = Path(f"/mnt/data/clips/{clip.job_id}_{clip.id}.mp4")
        # Reload the Volume so we can see files committed by the pipeline
        # after this web container started.
        try:
            import modal as _modal
            _modal.Volume.from_name("trimaura-data").reload()
        except Exception:
            pass
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


# --- Push Notifications ---

@router.get("/push/vapid-key")
def get_vapid_public_key():
    """Public VAPID key the browser needs to subscribe for push messages."""
    return {"public_key": settings.vapid_public_key}


@router.post("/push/subscribe", status_code=201)
def subscribe_push(body: PushSubscribeRequest):
    """Save a browser push subscription so terminal job states can notify it."""
    keys = body.keys or {}
    with Session(engine) as session:
        existing = session.exec(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        ).first()
        if existing:
            existing.p256dh = keys.get("p256dh", "")
            existing.auth = keys.get("auth", "")
            session.add(existing)
            session.commit()
            return {"status": "updated"}
        sub = PushSubscription(
            endpoint=body.endpoint,
            p256dh=keys.get("p256dh", ""),
            auth=keys.get("auth", ""),
        )
        session.add(sub)
        session.commit()
    return {"status": "subscribed"}


@router.delete("/push/subscribe")
def unsubscribe_push(body: PushSubscribeRequest):
    with Session(engine) as session:
        sub = session.exec(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        ).first()
        if sub:
            session.delete(sub)
            session.commit()
    return {"status": "unsubscribed"}


# --- Admin / Cleanup ---

@router.post("/admin/cleanup", status_code=200)
def admin_cleanup():
    """Delete stale jobs stuck in any non-terminal state. Keeps completed jobs."""
    from datetime import datetime, timedelta
    # Anything not COMPLETED that's been alive >24h is stuck (pipeline max is 1h).
    stale_statuses = [
        JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.TRANSCRIBING,
        JobStatus.ANALYZING, JobStatus.RENDERING, JobStatus.FAILED,
    ]
    with Session(engine) as session:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        jobs = session.exec(select(Job)).all()
        deleted = 0
        for j in jobs:
            if j.status in stale_statuses and j.created_at < cutoff:
                # Soft-delete all clips too
                for c in j.clips:
                    c.deleted = True
                    session.add(c)
                session.delete(j)
                deleted += 1
        session.commit()
    return {"deleted_jobs": deleted, "message": f"Cleaned up {deleted} old failed/pending jobs."}

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
