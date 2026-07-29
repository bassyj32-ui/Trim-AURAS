import json
import os
from sqlmodel import Session

from app.database import engine
from app.models import Job, JobStatus, VideoClip
from app.pipeline.downloader import execute_download
from app.pipeline.transcriber import execute_transcribe
from app.pipeline.intelligence import execute_analyze
from app.pipeline.video_editor import execute_render
from app.pipeline.seo_generator import execute_seo
from app.storage import upload_to_r2


def _update_job(job_id: int, **kwargs):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)
            session.add(job)
            session.commit()
            from app.database import force_db_sync
            force_db_sync()


def _get_transcript_text(segments: list[dict]) -> str:
    return " ".join(s.get("text", "") for s in segments)


def _cleanup_temp(*paths: str):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except Exception:
            pass


async def execute_pipeline(job_id: int):
    """Run the full pipeline for a given job. Updates job status at each step."""
    video_path = None
    rendered_paths = []

    try:
        # --- Phase 1: Download ---
        _update_job(job_id, status=JobStatus.DOWNLOADING, progress_percentage=10)
        job = _get_job(job_id)
        import asyncio
        video_path = await asyncio.to_thread(execute_download, job.source_url)

        # Upload source video to R2 for re-generation (non-fatal)
        source_key = f"sources/{job_id}_source.mp4"
        r2_url = upload_to_r2(video_path, source_key)
        if r2_url:
            _update_job(job_id, source_r2_key=source_key)

        # --- Phase 2: Transcribe ---
        _update_job(job_id, status=JobStatus.TRANSCRIBING, progress_percentage=25)
        segments = await execute_transcribe(video_path)

        # Save full transcript to job for later re-generation
        _update_job(job_id, transcript_json=json.dumps(segments))

        # --- Phase 3: Analyze ---
        _update_job(job_id, status=JobStatus.ANALYZING, progress_percentage=40)
        clips = await execute_analyze(segments, max_clips=job.max_clips)

        if not clips:
            raise RuntimeError("DeepSeek returned no clip suggestions")

        # --- Phase 4: Render ---
        _update_job(job_id, status=JobStatus.RENDERING, progress_percentage=60)
        rendered_paths = await execute_render(video_path, clips, segments, job.template_id)

        # --- Phase 5: SEO & Upload (per clip) ---
        transcript_text = _get_transcript_text(segments)
        seo_data = await execute_seo(transcript_text, campaign_rules=job.campaign_rules or "")

        with Session(engine) as session:
            db_job = session.get(Job, job_id)

            for i, rendered_path in enumerate(rendered_paths):
                clip_info = clips[i]
                key = f"clips/{job_id}_{i}.mp4"
                r2_url = upload_to_r2(rendered_path, key)
                is_offline = r2_url is None
                if is_offline:
                    r2_url = rendered_path  # fall back to local path

                db_clip = VideoClip(
                    job_id=job_id,
                    start_time=clip_info["start"],
                    end_time=clip_info["end"],
                    duration=clip_info["end"] - clip_info["start"],
                    r2_url=r2_url,
                    r2_key=key if not is_offline else "",
                    title_curiosity=seo_data.get("title_curiosity", ""),
                    title_direct=seo_data.get("title_direct", ""),
                    title_question=seo_data.get("title_question", ""),
                    description=seo_data.get("description", ""),
                    hashtags=seo_data.get("hashtags", ""),
                )
                session.add(db_clip)

            db_job.status = JobStatus.COMPLETED
            db_job.progress_percentage = 100
            session.add(db_job)
            session.commit()

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

    try:
        _update_job(job_id, status=JobStatus.ANALYZING, progress_percentage=40)
        job = _get_job(job_id)

        if not job.source_r2_key or not job.transcript_json:
            raise RuntimeError("Job has no saved source video or transcript. Cannot generate more clips.")

        # Load saved segments from DB
        segments = json.loads(job.transcript_json)

        # Find existing clip timestamps so DeepSeek avoids repeats
        existing_clips = [
            {"start": c.start_time, "end": c.end_time, "reason": ""}
            for c in job.clips if not c.deleted
        ]

        # Analyze with existing clips as exclusions
        max_to_generate = min(count, job.max_clips)
        clips = await execute_analyze(
            segments,
            max_clips=max_to_generate,
            existing_clips=existing_clips,
        )

        if not clips:
            raise RuntimeError("DeepSeek returned no new clip suggestions")

        # Download source video from R2
        import tempfile
        import boto3
        from botocore.config import Config as BotoConfig
        from app.config import settings

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                region_name="us-east-1",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        tmp_video = tempfile.mktemp(suffix=".mp4")
        client.download_file(settings.r2_bucket_name, job.source_r2_key, tmp_video)

        # Render new clips
        _update_job(job_id, status=JobStatus.RENDERING, progress_percentage=60)
        rendered_paths = await execute_render(tmp_video, clips, segments, job.template_id)

        # SEO + upload
        transcript_text = _get_transcript_text(segments)

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

                db_clip = VideoClip(
                    job_id=job_id,
                    start_time=clip_info["start"],
                    end_time=clip_info["end"],
                    duration=clip_info["end"] - clip_info["start"],
                    r2_url=r2_url,
                    r2_key=key,
                    title_curiosity=seo_data.get("title_curiosity", ""),
                    title_direct=seo_data.get("title_direct", ""),
                    title_question=seo_data.get("title_question", ""),
                    description=seo_data.get("description", ""),
                    hashtags=seo_data.get("hashtags", ""),
                )
                session.add(db_clip)
                session.commit()

        _update_job(job_id, status=JobStatus.COMPLETED, progress_percentage=100)

    except Exception as e:
        _update_job(job_id, status=JobStatus.FAILED, error_message=str(e))
        raise

    finally:
        for p in rendered_paths:
            _cleanup_temp(p)


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
