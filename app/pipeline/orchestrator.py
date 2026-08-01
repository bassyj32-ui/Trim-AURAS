import json
import os
from pathlib import Path
from sqlmodel import Session, select

from app.database import engine
from app.models import Job, JobStatus, VideoClip
from app.pipeline.downloader import execute_download
from app.pipeline.transcriber import execute_transcribe
from app.pipeline.intelligence import (
    execute_analyze,
    extract_video_signals,
    snap_clips_to_signals,
)
from app.pipeline.video_editor import execute_render
from app.pipeline.seo_generator import execute_seo
from app.storage import upload_to_r2

# Persistent Volume paths (match modal_app.py)
SOURCE_CACHE_DIR = Path("/mnt/data/sources")
CLIPS_DIR = Path("/mnt/data/clips")


async def _volume_commit():
    """Commit the Modal Volume so the web container can serve a clip as soon
    as it's written (progressive publishing). Uses the async .aio() interface
    so the commit does not block the pipeline event loop."""
    try:
        import modal

        await modal.Volume.from_name("trimaura-data").commit.aio()
    except Exception as e:
        print(f"[volume] commit failed (non-fatal): {e}")


def _update_job(job_id: int, **kwargs):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)
            session.add(job)
            session.commit()
    # Fire push notifications for terminal states (fire-and-forget)
    status = kwargs.get("status")
    if status in (JobStatus.COMPLETED, JobStatus.FAILED):
        _notify_terminal(status, kwargs.get("error_message"))


def _notify_terminal(status: str, error: str | None = None):
    """Push a notification when a job finishes or fails, so the user can
    deploy the clips from their phone without watching the page."""
    try:
        from app.push import notify_all

        if status == JobStatus.COMPLETED:
            notify_all(
                "TrimAURA — Ready ✅",
                "Your shorts are done. Open the app to review & deploy.",
                data={"jobDone": True},
            )
        elif status == JobStatus.FAILED:
            notify_all(
                "TrimAURA — Failed ❌",
                f"Processing error: {(error or 'Unknown error')[:140]}",
                data={"jobDone": True},
            )
    except Exception as exc:
        print(f"[push] notification dispatch failed (non-fatal): {exc}")


def _get_transcript_text(segments: list[dict]) -> str:
    return " ".join(s.get("text", "") for s in segments)


def _cleanup_temp(*paths: str):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except Exception:
            pass


def _cache_source(job_id: int, video_path: str) -> str:
    """Copy the source video onto the Volume so `generate-more` works even
    when R2 is unavailable. Returns the cached path (or ``video_path`` on
    non-Modal setups where the volume dir doesn't exist)."""
    try:
        SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest = SOURCE_CACHE_DIR / f"{job_id}_source.mp4"
        import shutil
        shutil.copy2(video_path, str(dest))
        return str(dest)
    except Exception as e:
        print(f"[generate-more] source cache failed (non-fatal): {e}")
        return video_path


async def _resolve_source(job_id: int, job) -> str:
    """Locate the job's source video, trying, in order:

    1. R2 (``source_r2_key``) — used when the pipeline upload succeeded.
    2. The Volume cache at /mnt/data/sources/{job_id}_source.mp4.
    3. Re-download from the original ``source_url``.

    The resolved file is cached on the Volume for future calls.
    """
    import asyncio
    import tempfile

    from app.config import settings

    # 1) R2
    if job.source_r2_key:
        try:
            import boto3
            from botocore.config import Config as BotoConfig

            client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                config=BotoConfig(
                    signature_version="s3v4",
                    region_name="us-east-1",
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
                verify=settings.r2_verify_ssl,
            )
            tmp_video = tempfile.mktemp(suffix=".mp4")
            client.download_file(settings.r2_bucket_name, job.source_r2_key, tmp_video)
            if os.path.exists(tmp_video) and os.path.getsize(tmp_video) > 0:
                print(f"[generate-more] source from R2: {job.source_r2_key}")
                _cache_source(job_id, tmp_video)
                return tmp_video
        except Exception as e:
            print(f"[generate-more] R2 source download failed (non-fatal): {e}")

    # 2) Volume cache
    cached = SOURCE_CACHE_DIR / f"{job_id}_source.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        print(f"[generate-more] source from Volume: {cached}")
        return str(cached)

    # 3) Re-download from the original URL
    if job.source_url:
        print(f"[generate-more] re-downloading source from: {job.source_url[:80]}")
        path = await asyncio.to_thread(
            execute_download,
            job.source_url,
            preferred_height=job.preferred_height if job.preferred_height is not None else 720,
        )
        _cache_source(job_id, path)
        return path

    raise RuntimeError(
        "Job has no source video (no R2 key, volume cache, or source URL). "
        "Cannot generate more clips."
    )


async def execute_pipeline(job_id: int):
    """Run the full pipeline for a given job. Updates job status at each step."""
    video_path = None
    rendered_paths = []

    try:
        # --- Phase 1: Download ---
        _update_job(job_id, status=JobStatus.DOWNLOADING, progress_percentage=10)
        job = _get_job(job_id)
        import asyncio
        video_path = await asyncio.to_thread(
            execute_download,
            job.source_url,
            preferred_height=job.preferred_height if job.preferred_height is not None else 720,
        )

        # Upload source video to R2 for re-generation (non-fatal)
        source_key = f"sources/{job_id}_source.mp4"
        r2_url = upload_to_r2(video_path, source_key)
        if r2_url:
            _update_job(job_id, source_r2_key=source_key)

        # Cache source on the Volume too, so "generate more" works even when
        # R2 is unavailable (R2 TLS cert incident, see app/config.py).
        _cache_source(job_id, video_path)

        # --- Phase 2: Transcribe ---
        _update_job(job_id, status=JobStatus.TRANSCRIBING, progress_percentage=25)
        segments = await execute_transcribe(video_path)

        # Guard: a video with no usable speech can't produce clips. Fail with
        # a clear message instead of a confusing downstream error.
        if not segments or len(_get_transcript_text(segments).strip()) < 10:
            raise RuntimeError(
                "No speech detected in this video (transcript is empty). "
                "Please use a video with clear spoken audio."
            )

        # Save full transcript to job for later re-generation
        _update_job(job_id, transcript_json=json.dumps(segments))

        # --- Phase 3: Analyze ---
        _update_job(job_id, status=JobStatus.ANALYZING, progress_percentage=40)
        # Cheap FFmpeg "sight" probes: scene cuts, loud moments, dead air
        video_signals = await asyncio.to_thread(extract_video_signals, video_path)
        clips = await execute_analyze(
            segments,
            max_clips=job.max_clips,
            campaign_rules=job.campaign_rules or "",
            video_signals=video_signals,
        )
        clips = snap_clips_to_signals(clips, video_signals)

        if not clips:
            raise RuntimeError("DeepSeek returned no clip suggestions")

        # --- Phase 4: Render ---
        _update_job(job_id, status=JobStatus.RENDERING, progress_percentage=60)
        rendered_paths = await execute_render(video_path, clips, segments, job.template_id)

        # --- Phase 5: SEO & Upload (per clip) ---
        transcript_text = _get_transcript_text(segments)
        seo_data = await execute_seo(transcript_text, campaign_rules=job.campaign_rules or "")

        CLIPS_DIR.mkdir(parents=True, exist_ok=True)

        with Session(engine) as session:
            db_job = session.get(Job, job_id)

            for i, rendered_path in enumerate(rendered_paths):
                clip_info = clips[i]
                key = f"clips/{job_id}_{i}.mp4"
                r2_url = upload_to_r2(rendered_path, key)
                is_offline = r2_url is None

                db_clip = VideoClip(
                    job_id=job_id,
                    start_time=clip_info["start"],
                    end_time=clip_info["end"],
                    duration=clip_info["end"] - clip_info["start"],
                    r2_url=rendered_path,       # will update below
                    r2_key=key if not is_offline else "",
                    title_curiosity=seo_data.get("title_curiosity", ""),
                    title_direct=seo_data.get("title_direct", ""),
                    title_question=seo_data.get("title_question", ""),
                    description=seo_data.get("description", ""),
                    hashtags=seo_data.get("hashtags", ""),
                    viral_score=clip_info.get("score"),
                )
                session.add(db_clip)
                session.flush()  # get db_clip.id before commit

                # Copy to predictable path that the download endpoint can serve
                clip_serve_path = CLIPS_DIR / f"{job_id}_{db_clip.id}.mp4"
                import shutil
                shutil.copy2(rendered_path, str(clip_serve_path))
                db_clip.r2_url = str(clip_serve_path)

                # Publish this clip NOW: commit to the DB and the Volume so it
                # is visible/downloadable while later clips are still rendering,
                # and survives a mid-render failure instead of being rolled
                # back with the whole job.
                session.commit()
                await _volume_commit()

            db_job.status = JobStatus.COMPLETED
            db_job.progress_percentage = 100
            session.add(db_job)
            session.commit()
            _notify_terminal(JobStatus.COMPLETED)

    except Exception as e:
        _update_job(job_id, status=JobStatus.FAILED, error_message=str(e))
        raise

    finally:
        _cleanup_temp(video_path)
        for p in rendered_paths:
            _cleanup_temp(p)


async def generate_more_clips(job_id: int, count: int = 3):
    """Generate extra clips from an existing job's saved source + transcript.

    Bypasses download + transcribe. Only runs analyze → render → SEO → upload.
    """
    rendered_paths = []
    tmp_video = None

    try:
        _update_job(job_id, status=JobStatus.ANALYZING, progress_percentage=40)
        job = _get_job(job_id)

        if not job.transcript_json:
            raise RuntimeError("Job has no saved transcript. Cannot generate more clips.")

        # Load saved segments from DB
        segments = json.loads(job.transcript_json)

        # Find existing clip timestamps so DeepSeek avoids repeats.
        # `job.clips` is a lazy relationship on a detached instance — query
        # inside a fresh session instead.
        existing_clips = []
        with Session(engine) as session:
            rows = session.exec(
                select(VideoClip).where(
                    VideoClip.job_id == job_id, VideoClip.deleted == False
                )
            ).all()
            existing_clips = [
                {"start": c.start_time, "end": c.end_time, "reason": ""}
                for c in rows
            ]

        # Locate the source video: R2 → Volume cache → re-download
        tmp_video = await _resolve_source(job_id, job)

        # Cheap FFmpeg "sight" probes: scene cuts, loud moments, dead air
        import asyncio
        video_signals = await asyncio.to_thread(extract_video_signals, tmp_video)

        # Analyze with existing clips as exclusions
        max_to_generate = min(count, job.max_clips)
        clips = await execute_analyze(
            segments,
            max_clips=max_to_generate,
            existing_clips=existing_clips,
            campaign_rules=job.campaign_rules or "",
            video_signals=video_signals,
        )
        if not clips:
            # DeepSeek refused to suggest anything new (existing clips cover
            # the highlights). Retry once without exclusions so "generate
            # more" can still produce additional crops of the same video.
            print(
                "[generate-more] no new suggestions with exclusions; "
                "retrying without exclusions"
            )
            clips = await execute_analyze(
                segments,
                max_clips=max_to_generate,
                campaign_rules=job.campaign_rules or "",
                video_signals=video_signals,
            )

        if not clips:
            raise RuntimeError("DeepSeek returned no clip suggestions")

        clips = snap_clips_to_signals(clips, video_signals)

        # Render new clips
        _update_job(job_id, status=JobStatus.RENDERING, progress_percentage=60)
        rendered_paths = await execute_render(tmp_video, clips, segments, job.template_id)

        # SEO + upload
        transcript_text = _get_transcript_text(segments)

        CLIPS_DIR.mkdir(parents=True, exist_ok=True)

        with Session(engine) as session:
            db_job = session.get(Job, job_id)

            for i, rendered_path in enumerate(rendered_paths):
                clip_info = clips[i]

                # Generate SEO per clip transcript snippet
                clip_transcript = _get_clip_transcript_text(segments, clip_info["start"], clip_info["end"])
                seo_data = await execute_seo(clip_transcript, campaign_rules=job.campaign_rules or "")

                clip_idx = len([c for c in db_job.clips if not c.deleted]) + i
                key = f"clips/{job_id}_extra_{clip_idx}.mp4"
                r2_url = upload_to_r2(rendered_path, key)
                is_offline = r2_url is None

                db_clip = VideoClip(
                    job_id=job_id,
                    start_time=clip_info["start"],
                    end_time=clip_info["end"],
                    duration=clip_info["end"] - clip_info["start"],
                    r2_url=rendered_path,       # will update below
                    r2_key=key if not is_offline else "",
                    title_curiosity=seo_data.get("title_curiosity", ""),
                    title_direct=seo_data.get("title_direct", ""),
                    title_question=seo_data.get("title_question", ""),
                    description=seo_data.get("description", ""),
                    hashtags=seo_data.get("hashtags", ""),
                    viral_score=clip_info.get("score"),
                )
                session.add(db_clip)
                session.flush()  # get db_clip.id before commit

                # Copy to predictable path that the download endpoint can serve
                clip_serve_path = CLIPS_DIR / f"{job_id}_{db_clip.id}.mp4"
                import shutil
                shutil.copy2(rendered_path, str(clip_serve_path))
                db_clip.r2_url = str(clip_serve_path)

                session.commit()
                await _volume_commit()

        _update_job(job_id, status=JobStatus.COMPLETED, progress_percentage=100)

    except Exception as e:
        _update_job(job_id, status=JobStatus.FAILED, error_message=str(e))
        raise

    finally:
        for p in rendered_paths:
            _cleanup_temp(p)
        # Clean up temp source downloads, but keep the Volume cache file.
        if tmp_video and not str(tmp_video).startswith(str(SOURCE_CACHE_DIR)):
            _cleanup_temp(tmp_video)


async def refresh_clip_seo(clip_id: int) -> dict[str, str]:
    """Re-run SEO for a single clip using its job's transcript + campaign rules.

    Returns the updated SEO data dict.
    """
    with Session(engine) as session:
        clip = session.get(VideoClip, clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")
        job = session.get(Job, clip.job_id)
        if not job or not job.transcript_json:
            raise ValueError("Job has no saved transcript")

    segments = json.loads(job.transcript_json)
    clip_transcript = _get_clip_transcript_text(segments, clip.start_time, clip.end_time)
    seo_data = await execute_seo(clip_transcript, campaign_rules=job.campaign_rules or "")

    with Session(engine) as session:
        db_clip = session.get(VideoClip, clip_id)
        if db_clip:
            db_clip.title_curiosity = seo_data.get("title_curiosity", "")
            db_clip.title_direct = seo_data.get("title_direct", "")
            db_clip.title_question = seo_data.get("title_question", "")
            db_clip.description = seo_data.get("description", "")
            db_clip.hashtags = seo_data.get("hashtags", "")
            session.add(db_clip)
            session.commit()

    return seo_data


def _get_clip_transcript_text(segments: list[dict], clip_start: float, clip_end: float) -> str:
    """Extract transcript text that falls within a clip's time range."""
    texts = []
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        if seg_start >= clip_start and seg_end <= clip_end:
            texts.append(seg.get("text", ""))
        elif seg_start < clip_end and seg_end > clip_start:
            # Partial overlap — include it
            texts.append(seg.get("text", ""))
    return " ".join(texts)


def _get_job(job_id: int, retries: int = 5) -> Job:
    """Look up a job by id, retrying up to *retries* times with 2 s delays.

    The retry loop covers the case where the SQLite database was just written
    on one Modal container and needs to propagate to a newly spawned worker
    container via the shared Volume.
    """
    import time

    for attempt in range(retries):
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is not None:
                return job
        if attempt < retries - 1:
            time.sleep(2)
    raise ValueError(f"Job {job_id} not found after {retries} attempts")
