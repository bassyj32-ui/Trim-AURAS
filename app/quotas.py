"""Per-user quotas + burst throttling for expensive endpoints.

DB-backed (Supabase Postgres), NOT in-memory: Modal scale-to-zero can run
several ASGI containers, so an in-memory counter would be per-container and
wrong. Every expensive endpoint (job create, upload, generate-more, trim,
refresh-seo) checks quotas BEFORE spawning a Modal worker, so abuse fails
fast without burning compute.

Quotas enforced here:
  - max concurrent non-terminal jobs per user
  - max jobs per rolling 24h per user
  - max total clips per job (incl. generate-more)
  - max clips per generate-more call
  - burst cap on expensive writes per minute (QuotaUsage sliding window)
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import Job, JobStatus, QuotaUsage, VideoClip

_NON_TERMINAL = [
    JobStatus.PENDING,
    JobStatus.DOWNLOADING,
    JobStatus.TRANSCRIBING,
    JobStatus.ANALYZING,
    JobStatus.RENDERING,
]

# Expensive write actions we burst-throttle per minute.
_HEAVY_ACTIONS = ("job", "generate_more", "trim", "refresh_seo", "upload")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _retry_after_headers(retry_after_seconds: int) -> dict[str, str]:
    return {"Retry-After": str(max(retry_after_seconds, 1))}


def _raise_429(message: str, retry_after_seconds: int) -> None:
    raise HTTPException(
        429,
        message,
        headers=_retry_after_headers(retry_after_seconds),
    )


# --- Job creation quotas ---------------------------------------------------

def check_create_job_quota(user_id: str) -> None:
    """Enforce concurrent + daily job limits for a user. Raise 429 on hit."""
    with Session(engine) as session:
        # Concurrent in-flight jobs (the Modal compute burn).
        in_flight = session.exec(
            select(Job).where(
                Job.user_id == user_id,
                Job.status.in_(_NON_TERMINAL),
            )
        ).all()
        if len(in_flight) >= settings.quota_max_concurrent_jobs:
            _raise_429(
                f"Too many jobs in progress ({len(in_flight)}/"
                f"{settings.quota_max_concurrent_jobs}). "
                "Wait for one to finish before starting another.",
                # Worst case a job runs ~15 min — suggest a reasonable wait.
                60,
            )

        # Jobs created in the last 24h (rolling window).
        cutoff = _now() - timedelta(hours=24)
        recent = session.exec(
            select(Job).where(
                Job.user_id == user_id,
                Job.created_at >= cutoff,
            )
        ).all()
        if len(recent) >= settings.quota_max_daily_jobs:
            _raise_429(
                f"Daily job limit reached ({len(recent)}/"
                f"{settings.quota_max_daily_jobs}). Try again tomorrow.",
                3600,
            )


def check_clip_quota(job: Job, extra: int = 0) -> None:
    """Ensure adding `extra` clips to a job stays under the per-job cap."""
    with Session(engine) as session:
        count = len(
            session.exec(
                select(VideoClip).where(
                    VideoClip.job_id == job.id,
                    VideoClip.deleted == False,  # noqa: E712
                )
            ).all()
        )
        if count + extra > settings.quota_max_clips_per_job:
            _raise_429(
                f"Clip limit reached for this job ({count}/"
                f"{settings.quota_max_clips_per_job}). "
                "Generate more clips in a new job.",
                60,
            )


# --- Burst throttling (sliding per-minute window) --------------------------

def check_burst(user_id: str, action: str) -> None:
    """Throttle expensive writes to N per minute per user (DB-backed)."""
    if action not in _HEAVY_ACTIONS:
        return

    limit = settings.quota_heavy_per_minute
    with Session(engine) as session:
        window = _now().replace(second=0, microsecond=0)

        row = session.exec(
            select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.action == action,
                QuotaUsage.window_start == window,
            )
        ).first()

        if row is None:
            # Prune old rows (same user+action) so the table stays tiny.
            session.exec(
                QuotaUsage.__table__.delete().where(
                    QuotaUsage.user_id == user_id,
                    QuotaUsage.action == action,
                    QuotaUsage.window_start < window - timedelta(hours=24),
                )
            )
            session.add(
                QuotaUsage(
                    user_id=user_id,
                    action=action,
                    window_start=window,
                    count=1,
                )
            )
            session.commit()
            return

        if row.count >= limit:
            _raise_429(
                f"Too many requests ({row.count}/{limit} per minute). Slow down.",
                30,
            )
        row.count += 1
        session.add(row)
        session.commit()