import asyncio
import json
from collections.abc import AsyncGenerator

from sqlmodel import Session

from app.database import engine
from app.models import Job


async def event_stream(job_id: int) -> AsyncGenerator[str]:
    """Yield SSE events for a job, polling DB for status changes every 2s."""
    last_status = None
    last_progress = -1

    while True:
        with Session(engine) as session:
            job = session.get(Job, job_id)

        if job is None:
            yield f"event: error\ndata: {json.dumps({'message': 'Job not found'})}\n\n"
            return

        status = job.status
        progress = job.progress_percentage
        error = job.error_message

        if status != last_status or progress != last_progress:
            payload = {"status": status, "progress": progress}
            if error:
                payload["error"] = error
            yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
            last_status = status
            last_progress = progress

            if status in ("COMPLETED", "FAILED"):
                return

        await asyncio.sleep(2)
