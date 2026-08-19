import pytest
from sqlmodel import Session

from app.config import settings
from app.models import Job, JobStatus


class TestQuotas:
    @pytest.mark.asyncio
    async def test_ok_within_limits(self, client, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg, mock_user):
        res = await client.post("/api/jobs", json={
            "source_url": "https://example.com/video.mp4",
            "template_id": "blurpad_v1",
            "max_clips": 3,
        })
        assert res.status_code == 202

    @pytest.mark.asyncio
    async def test_concurrent_job_limit_429(self, client, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg, mock_user, test_engine):
        # Fill up the concurrent quota with in-flight jobs (no workers touch DB).
        with Session(test_engine) as session:
            for i in range(settings.quota_max_concurrent_jobs):
                session.add(Job(
                    user_id="test-user",
                    title=f"inflight-{i}",
                    source_url="https://example.com/video.mp4",
                    status=JobStatus.RENDERING,
                ))
            session.commit()

        res = await client.post("/api/jobs", json={
            "source_url": "https://example.com/video.mp4",
            "template_id": "blurpad_v1",
        })
        assert res.status_code == 429
        assert "Retry-After" in res.headers

    @pytest.mark.asyncio
    async def test_daily_job_limit_429(self, client, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg, mock_user, test_engine):
        with Session(test_engine) as session:
            for i in range(settings.quota_max_daily_jobs):
                session.add(Job(
                    user_id="test-user",
                    title=f"done-{i}",
                    source_url="https://example.com/video.mp4",
                    status=JobStatus.COMPLETED,
                ))
            session.commit()

        res = await client.post("/api/jobs", json={
            "source_url": "https://example.com/video.mp4",
            "template_id": "blurpad_v1",
        })
        assert res.status_code == 429

    @pytest.mark.asyncio
    async def test_max_clips_clamped(self, client, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg, mock_user, test_engine):
        res = await client.post("/api/jobs", json={
            "source_url": "https://example.com/video.mp4",
            "template_id": "blurpad_v1",
            "max_clips": 999,
        })
        assert res.status_code == 202
        job_id = res.json()["job_id"]
        with Session(test_engine) as session:
            job = session.get(Job, job_id)
            assert job.max_clips <= settings.quota_max_clips_per_job

    @pytest.mark.asyncio
    async def test_burst_throttle_429(self, client, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg, mock_user, test_engine):
        # Tight limit for the test by spamming the same endpoint faster than
        # the per-minute window allows.
        statuses = []
        for _ in range(settings.quota_heavy_per_minute + 2):
            res = await client.post("/api/jobs", json={
                "source_url": "https://example.com/video.mp4",
                "template_id": "blurpad_v1",
            })
            statuses.append(res.status_code)
            if res.status_code == 429:
                break
        assert statuses[-1] == 429
        assert any(s == 429 for s in statuses)