import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

os.environ.setdefault("MODAL", "0")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

import app.database as db_module
import app.api.routes as routes_module
import app.pipeline.orchestrator as orch_module
import app.pipeline.transcriber as tr_module
import app.pipeline.intelligence as int_module
import app.pipeline.video_editor as ve_module
import app.pipeline.seo_generator as seo_module
import app.pipeline.face_track as ft_module
import app.storage as storage_module
import app.push as push_module
import app.quotas as quotas_module

from app.main import app
from app.models import Job, JobStatus, VideoClip


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture(scope="function", autouse=True)
def patch_engine(test_engine, monkeypatch):
    for mod in (db_module, orch_module, tr_module, int_module, ve_module, seo_module, ft_module, storage_module, push_module, quotas_module):
        if hasattr(mod, "engine"):
            monkeypatch.setattr(mod, "engine", test_engine)
    # Also patch the routes module which imports engine directly
    monkeypatch.setattr(routes_module, "engine", test_engine)


@pytest.fixture
def mock_user():
    return {"id": "test-user", "email": "test@example.com", "metadata": {}}


@pytest.fixture(autouse=True)
def override_auth(mock_user, monkeypatch):
    from app.auth import get_current_user

    def mock_get_current_user():
        return mock_user

    # FastAPI resolves Depends() by the original function object captured at
    # import time, so monkeypatching module attributes is not enough — use
    # dependency_overrides, the canonical mechanism.
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_modal(monkeypatch):
    mock_fn = AsyncMock()
    # Patch the dispatch functions directly since they're used in routes
    async def mock_dispatch_pipeline(job_id, job_data=None):
        await mock_fn(job_id, job_data)
    
    async def mock_dispatch_generate_more(job_id, count=3):
        await mock_fn(job_id, count)
    
    async def mock_dispatch_trim_clip(clip_id, new_start, new_end):
        await mock_fn(clip_id, new_start, new_end)
    
    monkeypatch.setattr("app.api.routes._dispatch_pipeline", mock_dispatch_pipeline)
    monkeypatch.setattr("app.api.routes._dispatch_generate_more", mock_dispatch_generate_more)
    monkeypatch.setattr("app.api.routes._dispatch_trim_clip", mock_dispatch_trim_clip)
    return mock_fn


@pytest.fixture
def mock_groq(monkeypatch):
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.segments = [
        MagicMock(start=0.0, end=5.0, text="Hello world", words=[
            MagicMock(word="Hello", start=0.0, end=0.5),
            MagicMock(word="world", start=0.5, end=1.0),
        ]),
    ]
    mock_response.words = [
        MagicMock(word="Hello", start=0.0, end=0.5),
        MagicMock(word="world", start=0.5, end=1.0),
    ]
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("app.pipeline.transcriber.AsyncGroq", lambda api_key: mock_client)
    return mock_client


@pytest.fixture
def mock_deepseek(monkeypatch):
    # Mock execute_seo directly since it's used by refresh_clip_seo
    async def mock_execute_seo(transcript_text: str, campaign_rules: str = "") -> dict[str, str]:
        return {
            "title_curiosity": "Why This Works",
            "title_direct": "This Works Because",
            "title_question": "Does This Work?",
            "description": "Test description",
            "hashtags": "#test #viral",
        }
    
    # Mock execute_analyze for clip analysis
    async def mock_execute_analyze(segments, max_clips=5, existing_clips=None, campaign_rules="", video_signals=None):
        return [{"start": 1.0, "end": 10.0, "reason": "viral hook", "score": 85}]
    
    monkeypatch.setattr("app.pipeline.seo_generator.execute_seo", mock_execute_seo)
    monkeypatch.setattr("app.pipeline.intelligence.execute_analyze", mock_execute_analyze)
    return None


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    def mock_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        return mock_result

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("subprocess.Popen", MagicMock())


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def sample_job(test_engine) -> Job:
    with Session(test_engine) as session:
        job = Job(
            user_id="test-user",
            title="Test Video",
            source_url="https://example.com/video.mp4",
            template_id="blurpad_v1",
            status=JobStatus.COMPLETED,
            progress_percentage=100,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
    return job


@pytest.fixture
def sample_clip(test_engine, sample_job: Job) -> VideoClip:
    with Session(test_engine) as session:
        clip = VideoClip(
            job_id=sample_job.id,
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            r2_url="/mnt/data/clips/test.mp4",
            r2_key="clips/test.mp4",
            title_curiosity="Why This Works",
            title_direct="This Works Because",
            title_question="Does This Work?",
            description="Test description",
            hashtags="#test #viral",
            viral_score=85,
        )
        session.add(clip)
        session.commit()
        session.refresh(clip)
    return clip