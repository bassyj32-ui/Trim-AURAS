from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlmodel import Field, Relationship, SQLModel


class JobStatus:
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default="default")
    title: str = Field(default="Untitled Job")
    source_url: str
    template_id: str = Field(default="blurpad_v1")

    # Clip Vault: keep source video + transcript for re-generation
    source_r2_key: Optional[str] = None          # R2 key of the uploaded source video
    transcript_json: Optional[str] = None         # Full transcript JSON (segments)
    campaign_rules: Optional[str] = None          # SEO campaign rules per job
    max_clips: int = Field(default=5)             # Max clips to generate
    preferred_height: Optional[int] = Field(default=720)  # Frame.io proxy height (0 = original)

    status: str = Field(default=JobStatus.PENDING)
    progress_percentage: int = Field(default=0)
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    clips: list["VideoClip"] = Relationship(back_populates="job")


class VideoClip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")

    start_time: float
    end_time: float
    duration: float
    r2_url: str
    r2_key: str = ""                              # R2 key for direct download

    title_curiosity: str = ""
    title_direct: str = ""
    title_question: str = ""
    description: str = ""
    hashtags: str = ""
    viral_score: Optional[int] = None              # 0-100 viral prediction from DeepSeek
    posted_platforms: Optional[str] = Field(default="[]")  # JSON list: ["tiktok","youtube","instagram"]

    deleted: bool = Field(default=False)          # Soft delete
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    job: Optional[Job] = Relationship(back_populates="clips")


class PushSubscription(SQLModel, table=True):
    """A browser PWA push subscription (endpoint + ECDH keys)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    endpoint: str = Field(unique=True, index=True)
    p256dh: str = ""
    auth: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def clip_vault_cutoff() -> datetime:
    """Clips older than 14 days from now are considered expired."""
    return datetime.now(timezone.utc) - timedelta(days=14)
