import pytest
from httpx import AsyncClient
from sqlmodel import Session
from app.models import Job


class TestJobsAPI:
    @pytest.mark.asyncio
    async def test_create_job_url_success(self, client: AsyncClient, mock_modal, mock_groq, mock_deepseek, mock_ffmpeg):
        res = await client.post("/api/jobs", json={
            "source_url": "https://example.com/video.mp4",
            "template_id": "blurpad_v1",
            "max_clips": 3,
        })
        assert res.status_code == 202
        data = res.json()
        assert "job_id" in data
        assert data["status"] == "PENDING"
        assert mock_modal.called

    @pytest.mark.asyncio
    async def test_create_job_missing_url_fails(self, client: AsyncClient):
        res = await client.post("/api/jobs", json={"template_id": "blurpad_v1"})
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_youtube_rejected(self, client: AsyncClient):
        res = await client.post("/api/jobs", json={
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "template_id": "blurpad_v1",
        })
        assert res.status_code == 400
        assert "YouTube is disabled" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_job_invalid_url_fails(self, client: AsyncClient):
        res = await client.post("/api/jobs", json={
            "source_url": "not-a-url",
            "template_id": "blurpad_v1",
        })
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        res = await client.get("/api/jobs")
        assert res.status_code == 200
        assert res.json() == []

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        res = await client.get("/api/jobs/999")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_job_not_found(self, client: AsyncClient):
        res = await client.get("/api/jobs/999/poll")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_more_no_transcript_fails(self, client: AsyncClient, sample_job):
        res = await client.post(f"/api/jobs/{sample_job.id}/generate-more", json={"count": 2})
        assert res.status_code == 400
        assert "no saved transcript" in res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_generate_more_success(self, client: AsyncClient, test_engine, sample_job, mock_modal):
        with Session(test_engine) as session:
            job = session.get(Job, sample_job.id)
            job.transcript_json = '[{"start": 0, "end": 5, "text": "hello"}]'
            session.add(job)
            session.commit()
        
        res = await client.post(f"/api/jobs/{sample_job.id}/generate-more", json={"count": 2})
        assert res.status_code == 202
        assert mock_modal.called


class TestJobsPolling:
    @pytest.mark.asyncio
    async def test_poll_returns_status(self, client: AsyncClient, sample_job):
        res = await client.get(f"/api/jobs/{sample_job.id}/poll")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["progress"] == 100