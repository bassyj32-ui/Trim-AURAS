"""Stuck-job auto-recovery.

The pipeline has a 3600s timeout; if a Modal worker is OOM-killed or the
container is lost, a job can sit in a non-terminal state forever with the
frontend polling it indefinitely. This background sweep marks such jobs
FAILED with a clear message so the UI unblocks and the user can retry.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import Job, JobStatus

logger = logging.getLogger("trimaura.recovery")

# Pipeline max is 1h (3600s in modal_app.py); give generous slack so a slow
# but legitimately-running job is never killed by the sweep.
STUCK_AFTER_MINUTES = int(getattr(settings, "recovery_stuck_minutes", 150))

_NON_TERMINAL = [
    JobStatus.PENDING,
    JobStatus.DOWNLOADING,
    JobStatus.TRANSCRIBING,
    JobStatus.ANALYZING,
    JobStatus.RENDERING,
]


def _recover_once() -> int:
    """Mark jobs stuck > STUCK_AFTER_MINUTES as FAILED. Returns count."""
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_AFTER_MINUTES)
    recovered = 0
    with Session(engine) as session:
        jobs = session.exec(select(Job)).all()
        for job in jobs:
            if job.status in _NON_TERMINAL and job.created_at < cutoff:
                job.status = JobStatus.FAILED
                job.error_message = (
                    "Job was stuck in a non-terminal state and was "
                    "auto-marked failed by the recovery sweep. Please retry."
                )
                session.add(job)
                recovered += 1
                logger.warning(
                    "recovery: job %s stuck in %s since %s -> FAILED",
                    job.id, job.status, job.created_at,
                )
        session.commit()
    return recovered


async def recovery_loop() -> None:
    """Run every 10 minutes until the process stops."""
    while True:
        try:
            recovered = _recover_once()
            if recovered:
                logger.warning("recovery: marked %s stuck job(s) FAILED", recovered)
        except Exception as exc:  # never let the loop die
            logger.exception("recovery sweep failed: %s", exc)
        await asyncio.sleep(10 * 60)


def start_recovery() -> asyncio.Task:
    """Start the background recovery loop (idempotent-ish, call once)."""
    return asyncio.create_task(recovery_loop())