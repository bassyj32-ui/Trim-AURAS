"""Per-user quotas + burst throttling for expensive endpoints.

DB-backed (Supabase Postgres), NOT in-memory: Modal scale-to-zero can run
several ASGI containers, so an in-memory counter would be per-container and
wrong. Every expensive endpoint (job create, upload, generate-more, trim,
refresh-seo) checks quotas BEFORE spawning a Modal worker, so abuse fails
fast without burning compute.

Quotas enforced here:
  - per-tier max concurrent non-terminal jobs per user
  - per-tier max jobs per rolling 24h per user
  - per-tier monthly CREDITS (= source minutes, the real cost driver) with
    top-up credits on top; deducted at job creation from the probed duration
  - per-tier max source minutes per job
  - max total clips per job (incl. generate-more)
  - max clips per generate-more call
  - burst cap on expensive writes per minute (QuotaUsage sliding window)
"""

import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import Job, JobStatus, MonthlyUsage, QuotaUsage, UserTier, VideoClip

_NON_TERMINAL = [
    JobStatus.PENDING,
    JobStatus.DOWNLOADING,
    JobStatus.TRANSCRIBING,
    JobStatus.ANALYZING,
    JobStatus.RENDERING,
]

# Expensive write actions we burst-throttle per minute.
_HEAVY_ACTIONS = ("job", "generate_more", "trim", "refresh_seo", "upload")

_FALLBACK_LIMITS = {"monthly_credits": 60, "monthly_clips": 10, "jobs_per_day": 2,
                    "concurrent": 1, "max_source_min": 15, "max_clips_per_job": 5}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month() -> str:
    return _now().strftime("%Y-%m")


def _retry_after_headers(retry_after_seconds: int) -> dict[str, str]:
    return {"Retry-After": str(max(retry_after_seconds, 1))}


def _raise_429(message: str, retry_after_seconds: int) -> None:
    raise HTTPException(
        429,
        message,
        headers=_retry_after_headers(retry_after_seconds),
    )


# --- Tier + monthly ledger --------------------------------------------------

def get_tier(user_id: str) -> str:
    """Current plan tier, defaulting to 'free' (row created lazily)."""
    with Session(engine) as session:
        row = session.get(UserTier, user_id)
        if row is None:
            session.add(UserTier(user_id=user_id, tier="free"))
            session.commit()
            return "free"
        return row.tier if row.tier in settings.tier_limits else "free"


def get_tier_limits(user_id: str) -> dict:
    tier = get_tier(user_id)
    return settings.tier_limits.get(tier, _FALLBACK_LIMITS)


def get_usage_summary(user_id: str) -> dict:
    """Public usage view: tier, monthly balance, caps, top-up price."""
    limits = get_tier_limits(user_id)
    month = _month()
    with Session(engine) as session:
        usage = session.get(MonthlyUsage, (user_id, month))
    used = usage.credits_used if usage else 0
    topups = usage.topup_credits if usage else 0
    jobs = usage.jobs_used if usage else 0
    return {
        "tier": get_tier(user_id),
        "month": month,
        "credits_used": used,
        "topup_credits": topups,
        "credits_balance": limits["monthly_credits"] + topups - used,
        "monthly_credits": limits["monthly_credits"],
        "jobs_used": jobs,
        "jobs_per_day": limits["jobs_per_day"],
        "concurrent": limits["concurrent"],
        "max_source_min": limits["max_source_min"],
        "topup_price_usd_per_credit": settings.topup_credit_price,
    }


def deduct_credits(user_id: str, source_seconds: int | None, session: Session) -> int:
    """Charge source minutes for a new job and bump the monthly job counter.

    Call inside the same session/commit as the Job insert so the charge is
    atomic with job creation. Unknown duration still costs a minimum of 1
    credit (the pipeline timeout bounds whatever slips through).
    """
    minutes = max(1, math.ceil((source_seconds or 0) / 60))
    usage = session.get(MonthlyUsage, (user_id, _month()))
    if usage is None:
        usage = MonthlyUsage(user_id=user_id, month=_month())
        session.add(usage)
    usage.credits_used += minutes
    usage.jobs_used += 1
    return minutes


# --- Job creation quotas ---------------------------------------------------

def check_create_job_quota(user_id: str, source_seconds: int | None = None) -> None:
    """Enforce per-tier concurrent, daily, monthly-credit and clip caps. 429 on hit."""
    limits = get_tier_limits(user_id)
    minutes = max(1, math.ceil((source_seconds or 0) / 60))
    month = _month()

    with Session(engine) as session:
        # Concurrent in-flight jobs (the Modal compute burn).
        in_flight = session.exec(
            select(Job).where(
                Job.user_id == user_id,
                Job.status.in_(_NON_TERMINAL),
            )
        ).all()
        if len(in_flight) >= limits["concurrent"]:
            _raise_429(
                f"Too many jobs in progress ({len(in_flight)}/"
                f"{limits['concurrent']}). Wait for one to finish before starting another.",
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
        if len(recent) >= limits["jobs_per_day"]:
            _raise_429(
                f"Daily job limit reached ({len(recent)}/"
                f"{limits['jobs_per_day']}). Try again tomorrow.",
                3600,
            )

        # Monthly credits (source minutes — the real cost driver).
        usage = session.get(MonthlyUsage, (user_id, month))
        used = usage.credits_used if usage else 0
        topups = usage.topup_credits if usage else 0
        balance = limits["monthly_credits"] + topups - used

        # Per-tier max source length per job (free 15 / starter 60 / pro 120).
        # Separate from the global 90-min probe ceiling — this is the tier gate.
        max_min = limits["max_source_min"]
        if minutes > max_min:
            _raise_429(
                f"Source is {minutes} min — the {get_tier(user_id)} plan allows "
                f"up to {max_min} min per job. Trim it or upgrade.",
                3600,
            )

        if minutes > balance:
            price = math.ceil(minutes * settings.topup_credit_price * 100)
            _raise_429(
                f"Not enough credits this month — this job needs {minutes} min, "
                f"{balance} left. Buy a top-up (${price / 100:.2f}) or wait for the reset.",
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