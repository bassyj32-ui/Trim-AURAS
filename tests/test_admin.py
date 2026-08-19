import pytest
from sqlmodel import Session

from app.auth import get_current_user
from app.main import app
from app.models import Job, JobStatus, UserTier


def _set_current_user(app, user: dict):
    app.dependency_overrides[get_current_user] = lambda: user


def _restore_current_user(app):
    app.dependency_overrides.pop(get_current_user, None)


ADMIN = {"id": "admin-1", "email": "vitamerina@gmail.com", "metadata": {}}
NON_ADMIN = {"id": "user-9", "email": "someone@example.com", "metadata": {}}


class TestAdminGate:
    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client):
        _set_current_user(app, NON_ADMIN)
        try:
            res = await client.get("/api/admin/overview")
            assert res.status_code == 403
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_no_token_401(self, client, monkeypatch):
        # No dependency override -> the real gate runs and rejects missing token.
        _restore_current_user(app)
        res = await client.get("/api/admin/overview")
        assert res.status_code == 401


class TestAdminOverview:
    @pytest.mark.asyncio
    async def test_overview_counts(self, client, test_engine):
        _set_current_user(app, ADMIN)
        try:
            with Session(test_engine) as session:
                session.add(Job(user_id="u1", title="a", source_url="https://x/1.mp4", status=JobStatus.COMPLETED))
                session.add(Job(user_id="u1", title="b", source_url="https://x/2.mp4", status=JobStatus.FAILED))
                session.add(Job(user_id="u2", title="c", source_url="https://x/3.mp4", status=JobStatus.COMPLETED))
                session.commit()

            res = await client.get("/api/admin/overview")
            assert res.status_code == 200
            data = res.json()
            assert data["total_jobs"] == 3
            assert data["jobs_by_status"]["COMPLETED"] == 2
            assert data["jobs_by_status"]["FAILED"] == 1
        finally:
            _restore_current_user(app)


class TestAdminUsers:
    @pytest.mark.asyncio
    async def test_users_lists_email_and_tier(self, client, test_engine):
        _set_current_user(app, ADMIN)
        try:
            with Session(test_engine) as session:
                session.add(UserTier(user_id="u1", email="one@example.com", tier="pro", permanent_credits=500))
                session.commit()

            res = await client.get("/api/admin/users")
            assert res.status_code == 200
            users = res.json()["users"]
            assert any(u["user_id"] == "u1" and u["email"] == "one@example.com"
                       and u["tier"] == "pro" and u["permanent_credits"] == 500 for u in users)
        finally:
            _restore_current_user(app)


class TestAdminActions:
    @pytest.mark.asyncio
    async def test_grant_credits(self, client, test_engine):
        _set_current_user(app, ADMIN)
        try:
            res = await client.post("/api/admin/users/u1/credits", json={"credits": 250})
            assert res.status_code == 200
            assert res.json()["permanent_credits"] == 250
            res2 = await client.post("/api/admin/users/u1/credits", json={"credits": -100})
            assert res2.json()["permanent_credits"] == 150
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_set_tier(self, client, test_engine):
        _set_current_user(app, ADMIN)
        try:
            res = await client.post("/api/admin/users/u1/tier", json={"tier": "starter"})
            assert res.status_code == 200
            assert res.json()["tier"] == "starter"
            bad = await client.post("/api/admin/users/u1/tier", json={"tier": "platinum"})
            assert bad.status_code == 400
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_retry_failed_job(self, client, mock_modal, test_engine):
        _set_current_user(app, ADMIN)
        try:
            with Session(test_engine) as session:
                job = Job(user_id="u1", title="t", source_url="https://x/1.mp4",
                          status=JobStatus.FAILED, error_message="boom")
                session.add(job)
                session.commit()
                job_id = job.id

            res = await client.post(f"/api/admin/jobs/{job_id}/retry")
            assert res.status_code == 200
            assert res.json()["status"] == "PENDING"
            with Session(test_engine) as session:
                row = session.get(Job, job_id)
                assert row.status == JobStatus.PENDING
                assert row.error_message is None
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_retry_rejects_completed(self, client, mock_modal, test_engine):
        _set_current_user(app, ADMIN)
        try:
            with Session(test_engine) as session:
                job = Job(user_id="u1", title="t", source_url="https://x/1.mp4",
                          status=JobStatus.COMPLETED)
                session.add(job)
                session.commit()
                job_id = job.id

            res = await client.post(f"/api/admin/jobs/{job_id}/retry")
            assert res.status_code == 400
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_cleanup_gated(self, client):
        _set_current_user(app, NON_ADMIN)
        try:
            res = await client.post("/api/admin/cleanup")
            assert res.status_code == 403
        finally:
            _restore_current_user(app)

    @pytest.mark.asyncio
    async def test_topup_gated_by_admin(self, client):
        _set_current_user(app, NON_ADMIN)
        try:
            res = await client.post("/api/credits/topup", json={"credits": 100})
            assert res.status_code == 403
        finally:
            _restore_current_user(app)