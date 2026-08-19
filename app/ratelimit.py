"""Per-IP DB-backed rate limiting (defense-in-depth for open signup).

Shares the QuotaUsage table with per-user burst throttling — IP rows use
``user_id = "ip:<addr>"`` so they never collide with real user UUIDs.
DB-backed (not in-memory) because Modal scale-to-zero can run several ASGI
containers, so an in-memory counter would be per-container and wrong.

This bounds scraping / hammering on the public API surface. The expensive
compute path (job creation) is additionally gated by per-user quotas in
app/quotas.py.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import QuotaUsage

_RATE_ACTIONS = ("api",)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def client_ip(request: Request) -> str:
    """Real client IP behind Modal's proxy (X-Forwarded-For, first hop)."""
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_ip_rate(request: Request) -> None:
    """Enforce a per-IP requests/minute cap on API routes. 429 when exceeded."""
    limit = settings.ip_rate_per_minute
    ip = client_ip(request)
    with Session(engine) as session:
        window = _now().replace(second=0, microsecond=0)
        key = f"ip:{ip}"
        row = session.exec(
            select(QuotaUsage).where(
                QuotaUsage.user_id == key,
                QuotaUsage.action == "api",
                QuotaUsage.window_start == window,
            )
        ).first()

        if row is None:
            # Prune stale rows for this IP so the table stays tiny.
            session.exec(
                QuotaUsage.__table__.delete().where(
                    QuotaUsage.user_id == key,
                    QuotaUsage.window_start < window - timedelta(hours=24),
                )
            )
            session.add(
                QuotaUsage(user_id=key, action="api", window_start=window, count=1)
            )
            session.commit()
            return

        if row.count >= limit:
            raise HTTPException(
                429,
                f"Too many requests from this IP ({limit}/min). Slow down.",
                headers={"Retry-After": "30"},
            )
        row.count += 1
        session.add(row)
        session.commit()
