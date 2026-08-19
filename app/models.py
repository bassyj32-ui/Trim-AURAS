from datetime import UTC, datetime, timedelta

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
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(default="default")
    title: str = Field(default="Untitled Job")
    source_url: str
    template_id: str = Field(default="blurpad_v1")

    # Clip Vault: keep source video + transcript for re-generation
    source_r2_key: str | None = None          # R2 key of the uploaded source video
    transcript_json: str | None = None         # Full transcript JSON (segments)
    face_track_json: str | None = None         # Normalized face track [{t,cx,cy}] for animated crop
    campaign_rules: str | None = None          # SEO campaign rules per job
    max_clips: int = Field(default=5)             # Max clips to generate
    preferred_height: int | None = Field(default=720)  # Frame.io proxy height (0 = original)
    burn_captions: bool = Field(default=False)    # Burn animated word-level captions (karaoke, Opus-style)
    trim_silence: bool = Field(default=False)     # Cut inter-word pauses >0.5s (punchier clips)

    status: str = Field(default=JobStatus.PENDING)
    progress_percentage: int = Field(default=0)
    error_message: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    clips: list["VideoClip"] = Relationship(back_populates="job")


class VideoClip(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
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
    viral_score: int | None = None              # 0-100 viral prediction from DeepSeek
    posted_platforms: str | None = Field(default="[]")  # JSON list: ["tiktok","youtube","instagram"]

    deleted: bool = Field(default=False)          # Soft delete
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    job: Job | None = Relationship(back_populates="clips")


class PushSubscription(SQLModel, table=True):
    """A browser PWA push subscription (endpoint + ECDH keys)."""
    id: int | None = Field(default=None, primary_key=True)
    endpoint: str = Field(unique=True, index=True)
    p256dh: str = ""
    auth: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QuotaUsage(SQLModel, table=True):
    """Sliding-window burst counter for expensive endpoints (DB-backed).

    Modal scale-to-zero can run several ASGI containers, so in-memory rate
    counters are wrong; a Postgres row per (user, action, window) is correct.
    Rows are pruned when older than the window, keeping the table tiny.
    """
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    action: str = Field(index=True)          # e.g. "job", "generate_more", "trim", "refresh_seo"
    window_start: datetime = Field(index=True)  # minute bucket start
    count: int = Field(default=0)


def clip_vault_cutoff() -> datetime:
    """Clips older than 14 days from now are considered expired."""
    return datetime.now(UTC) - timedelta(days=14)
