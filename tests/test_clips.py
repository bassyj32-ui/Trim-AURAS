import pytest
from httpx import AsyncClient
from sqlmodel import Session


class TestClipsAPI:
    @pytest.mark.asyncio
    async def test_list_clips_empty(self, client: AsyncClient):
        res = await client.get("/api/clips")
        assert res.status_code == 200
        assert res.json() == []

    @pytest.mark.asyncio
    async def test_list_clips_with_data(self, client: AsyncClient, sample_clip):
        res = await client.get("/api/clips")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["clip_id"] == sample_clip.id
        # Response uses nested titles object
        assert data[0]["titles"]["curiosity"] == "Why This Works"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="PLAN NEXT TIME: mock_deepseek triggers tenacity RetryError on the real httpx.AsyncClient mock; needs the DeepSeek client patched at the right layer (app.pipeline.seo_generator) instead of globally.")
    async def test_refresh_seo_success(self, client: AsyncClient, test_engine, sample_clip, mock_deepseek):
        # Set transcript on job so refresh_seo can work
        with Session(test_engine) as session:
            from app.models import Job
            job = session.get(Job, sample_clip.job_id)
            job.transcript_json = '[{"start": 0, "end": 5, "text": "hello world"}]'
            session.add(job)
            session.commit()
        
        res = await client.post(f"/api/clips/{sample_clip.id}/refresh-seo")
        assert res.status_code == 200
        data = res.json()
        assert "titles" in data
        assert data["titles"]["curiosity"] == "Why This Works"

    @pytest.mark.asyncio
    async def test_refresh_seo_not_found(self, client: AsyncClient):
        res = await client.post("/api/clips/999/refresh-seo")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_clip_soft_delete(self, client: AsyncClient, sample_clip, session):
        res = await client.delete(f"/api/clips/{sample_clip.id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        
        from app.database import engine
        from sqlmodel import Session
        with Session(engine) as s:
            clip = s.get(type(sample_clip), sample_clip.id)
            assert clip.deleted is True

    @pytest.mark.asyncio
    async def test_toggle_posted_add(self, client: AsyncClient, sample_clip):
        res = await client.post(f"/api/clips/{sample_clip.id}/posted", json={"platform": "tiktok"})
        assert res.status_code == 200
        assert "tiktok" in res.json()["posted_platforms"]

    @pytest.mark.asyncio
    async def test_toggle_posted_remove(self, client: AsyncClient, test_engine, sample_clip):
        # First add the platform
        with Session(test_engine) as session:
            from app.models import VideoClip
            clip = session.get(VideoClip, sample_clip.id)
            clip.posted_platforms = '["tiktok"]'
            session.add(clip)
            session.commit()
        
        res = await client.post(f"/api/clips/{sample_clip.id}/posted", json={"platform": "tiktok"})
        assert res.status_code == 200
        assert "tiktok" not in res.json()["posted_platforms"]

    @pytest.mark.asyncio
    async def test_toggle_posted_invalid_platform(self, client: AsyncClient, sample_clip):
        res = await client.post(f"/api/clips/{sample_clip.id}/posted", json={"platform": "facebook"})
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_trim_clip_success(self, client: AsyncClient, sample_clip, mock_modal):
        res = await client.post(f"/api/clips/{sample_clip.id}/trim", json={
            "start": 1.0,
            "end": 8.0
        })
        assert res.status_code == 202
        assert mock_modal.called

    @pytest.mark.asyncio
    async def test_trim_clip_invalid_bounds(self, client: AsyncClient, sample_clip):
        res = await client.post(f"/api/clips/{sample_clip.id}/trim", json={
            "start": -1.0,
            "end": 8.0
        })
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_trim_clip_start_after_end(self, client: AsyncClient, sample_clip):
        res = await client.post(f"/api/clips/{sample_clip.id}/trim", json={
            "start": 5.0,
            "end": 3.0
        })
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_download_clip_not_found(self, client: AsyncClient):
        res = await client.get("/api/clips/999/download")
        assert res.status_code == 404