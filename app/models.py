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
    source_seconds: int | None = None             # Probed source duration (credits = minutes)

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
    """A browser PWA push subscription (endpoint + ECDH keys), owned by a user.

    ``user_id`` scopes rows per account (RLS + API both key off it) so a
    job's terminal push reaches only the job's owner.
    """
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(default="", index=True)
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


class UserTier(SQLModel, table=True):
    """Per-user plan tier (free/starter/pro). Row created lazily on first use."""
    user_id: str = Field(primary_key=True)
    email: str = Field(default="")   # auto-filled from auth.users (DB trigger + first-request stamp)
    tier: str = Field(default="free")
    permanent_credits: int = Field(default=0)  # purchased minutes, never expire
    subscription_id: str | None = None     # Dodo subscription id (recurring plans)
    subscription_status: str | None = None  # active | cancelled | expired | on_hold | paused
    period_end: datetime | None = None     # next billing date / expiry
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Payment(SQLModel, table=True):
    """One checkout session (top-up or subscription start) + payment outcome.

    ``session_id`` is unique so retried webhooks can't double-grant credits.
    Rows are created when the checkout is issued and updated on webhook.
    """
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    payment_id: str | None = None      # Dodo payment id (set on payment.succeeded; refunds match on it)
    user_id: str = Field(index=True)
    kind: str = Field(default="topup")   # "topup" | "subscription"
    plan: str | None = None              # "starter" | "pro" for subscriptions
    credits: int = Field(default=0)      # credits granted for top-ups
    amount_cents: int = Field(default=0)
    currency: str = Field(default="USD")
    status: str = Field(default="pending")  # pending | succeeded | refunded | failed
    event_id: str | None = None          # Dodo event id (dedupe)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MonthlyUsage(SQLModel, table=True):
    """Monthly allowance ledger per user: credits (source minutes) used.

    Row per (user_id, 'YYYY-MM'). credits_used counts source minutes of jobs
    started this month; jobs_used/clips_used track the other caps. Purchased
    minutes live in UserTier.permanent_credits (never expire) — topup_credits
    here is legacy and no longer written.
    """
    user_id: str = Field(primary_key=True)
    month: str = Field(primary_key=True)      # 'YYYY-MM'
    credits_used: int = Field(default=0)
    jobs_used: int = Field(default=0)
    clips_used: int = Field(default=0)
    topup_credits: int = Field(default=0)


def clip_vault_cutoff() -> datetime:
    """Clips older than 14 days from now are considered expired."""
    return datetime.now(UTC) - timedelta(days=14)
