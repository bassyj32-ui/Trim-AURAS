"""Web Push (VAPID) notifications for installed PWA clients.

Sends a push message to every registered subscription whenever a job
reaches a terminal state (COMPLETED / FAILED) so the user gets pinged
even when the tab is closed. Dead subscriptions (404/410 — app
uninstalled or endpoint expired) are pruned automatically.
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


def notify_all(title: str, body: str, data: dict | None = None) -> None:
    """Send *title/body* to every registered subscription (fire-and-forget).

    Runs in a daemon thread so the caller (pipeline worker) never blocks
    on browser push service latency.
    """
    if not settings.vapid_private_key:
        print("[push] VAPID private key not configured — skipping push")
        return

    def _run():
        try:
            with Session(engine) as session:
                subs = list(session.exec(select(PushSubscription)).all())
        except Exception as exc:
            print(f"[push] db read failed (non-fatal): {exc}")
            return

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

    threading.Thread(target=_run, daemon=True).start()
