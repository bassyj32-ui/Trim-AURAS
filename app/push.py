"""Web Push (VAPID) notifications for installed PWA clients.

Sends a push message to a user's subscriptions whenever one of their jobs
reaches a terminal state (COMPLETED / FAILED) so they get pinged even when
the tab is closed. Dead subscriptions (404/410 — app uninstalled or endpoint
expired) are pruned automatically.
"""
import json
import threading

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import PushSubscription


def _send_one(sub: PushSubscription, title: str, body: str, data: dict | None = None) -> None:
    from pywebpush import WebPushException, webpush

    payload = {"title": title, "body": body, "data": data or {}}
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject or "mailto:trimaura@solo.app"},
        )
    except WebPushException as exc:
        # 404/410 means the endpoint is gone — let the caller prune it.
        if exc.response is not None and exc.response.status_code in (404, 410):
            raise
        print(f"[push] send failed (non-fatal): {exc}")
    except Exception as exc:  # network timeouts, bad endpoint, etc.
        print(f"[push] send failed (non-fatal): {exc}")


def _send_all(subs: list[PushSubscription], title: str, body: str, data: dict | None) -> None:
    dead: list[int] = []
    for sub in subs:
        try:
            _send_one(sub, title, body, data)
        except Exception:
            dead.append(sub.id)

    if dead:
        try:
            with Session(engine) as session:
                for sid in dead:
                    sub = session.get(PushSubscription, sid)
                    if sub:
                        session.delete(sub)
                session.commit()
                print(f"[push] pruned {len(dead)} expired subscription(s)")
        except Exception as exc:
            print(f"[push] prune failed (non-fatal): {exc}")


def _spawn(subs_loader, title: str, body: str, data: dict | None) -> None:
    """Run the send loop in a daemon thread so the caller (pipeline worker)
    never blocks on browser push service latency."""

    def _run():
        try:
            with Session(engine) as session:
                subs = subs_loader(session)
        except Exception as exc:
            print(f"[push] db read failed (non-fatal): {exc}")
            return
        _send_all(subs, title, body, data)

    threading.Thread(target=_run, daemon=True).start()


def notify_user(user_id: str, title: str, body: str, data: dict | None = None) -> None:
    """Send *title/body* to one user's subscriptions (fire-and-forget).

    Rows are scoped by owner (``user_id``), so a completed/failed job pings
    only the job's owner instead of broadcasting to every device on the
    platform.
    """
    if not settings.vapid_private_key:
        print("[push] VAPID private key not configured — skipping push")
        return

    def _load(session):
        return list(
            session.exec(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            ).all()
        )

    _spawn(_load, title, body, data)


def notify_all(title: str, body: str, data: dict | None = None) -> None:
    """Broadcast to every registered subscription (ops/admin use only)."""
    if not settings.vapid_private_key:
        print("[push] VAPID private key not configured — skipping push")
        return

    def _load(session):
        return list(session.exec(select(PushSubscription)).all())

    _spawn(_load, title, body, data)
