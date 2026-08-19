"""Observability bootstrap shared by the web container and pipeline workers.

Modal runs the pipeline stages in separate containers from the ASGI app, so
Sentry must be initialized in each process or worker errors never leave
stderr. Everything here is a no-op when Sentry is not configured, so imports
can never crash a cold start.
"""

_initialized = False


def init_sentry() -> None:
    """Initialize the Sentry SDK once per process (no-op without a DSN)."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        from app.config import settings

        if not settings.sentry_dsn:
            return
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            send_default_pii=True,
            traces_sample_rate=0.1,
        )
    except Exception:
        pass


def bootstrap() -> None:
    """One-call setup for any process (workers, cron): JSON logging + Sentry."""
    from app.logging_conf import setup_logging

    setup_logging()
    init_sentry()


def capture_job_failure(job_id: int, stage: str, error: str) -> None:
    """Emit an alertable Sentry event for a terminal job failure.

    Alert rules in the Sentry dashboard can key off the ``job_id``/``stage``
    tags (e.g. "notify when a new issue arrives") so a dead pipeline surfaces
    without anyone watching the dashboard.
    """
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("job_id", job_id)
            scope.set_tag("stage", stage)
            sentry_sdk.capture_message(
                f"Job {job_id} FAILED at {stage or 'unknown'} stage: {error[:300]}",
                level="error",
            )
    except Exception:
        pass
