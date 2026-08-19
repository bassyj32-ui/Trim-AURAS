import time

import pytest
from sqlmodel import select

from app.auth import get_current_user
from app.main import app
from app.models import PushSubscription

pytest.importorskip("pywebpush")


class TestPushRls:
    @pytest.mark.asyncio
    async def test_subscribe_requires_auth(self, client):
        app.dependency_overrides.pop(get_current_user, None)
        res = await client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push/e1", "keys": {"p256dh": "x", "auth": "y"}},
        )
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_subscribe_scoped_by_user(self, client, mock_user, session):
        mock_user["id"] = "user-a"
        r1 = await client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push/a", "keys": {"p256dh": "a1", "auth": "a2"}},
        )
        assert r1.status_code == 201

        # A different user's device gets its own row, tagged with its owner.
        mock_user["id"] = "user-b"
        r2 = await client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push/b", "keys": {"p256dh": "b1", "auth": "b2"}},
        )
        assert r2.status_code == 201

        subs = session.exec(select(PushSubscription)).all()
        assert len(subs) == 2
        assert {s.user_id for s in subs} == {"user-a", "user-b"}

    @pytest.mark.asyncio
    async def test_unsubscribe_only_removes_owner(self, client, mock_user, session):
        mock_user["id"] = "user-a"
        await client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push/a", "keys": {"p256dh": "a1", "auth": "a2"}},
        )
        mock_user["id"] = "user-b"
        await client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push/b", "keys": {"p256dh": "b1", "auth": "b2"}},
        )

        # user-a tries to delete user-b's endpoint — must be a no-op.
        mock_user["id"] = "user-a"
        res = await client.request(
            "DELETE", "/api/push/subscribe", json={"endpoint": "https://push/b", "keys": {}}
        )
        assert res.status_code == 200

        # user-a deletes their own — only their row disappears.
        res = await client.request(
            "DELETE", "/api/push/subscribe", json={"endpoint": "https://push/a", "keys": {}}
        )
        assert res.status_code == 200

        remaining = session.exec(select(PushSubscription)).all()
        assert [s.user_id for s in remaining] == ["user-b"]

    def test_notify_user_sends_only_to_owner(self, monkeypatch, session, test_engine):
        from app.config import settings
        from app.push import notify_user

        for uid, ep in (("user-a", "https://push/a"), ("user-b", "https://push/b")):
            session.add(
                PushSubscription(user_id=uid, endpoint=ep, p256dh=f"k-{uid}", auth=f"a-{uid}")
            )
        session.commit()

        monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
        sent = []

        import pywebpush

        monkeypatch.setattr(pywebpush, "webpush", lambda **kw: sent.append(kw))

        notify_user("user-a", "Title", "Body")
        deadline = time.time() + 3
        while not sent and time.time() < deadline:
            time.sleep(0.05)

        assert len(sent) == 1
        assert sent[0]["subscription_info"]["endpoint"] == "https://push/a"
