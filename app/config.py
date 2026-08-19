import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AI APIs
    groq_api_key: str
    deepseek_api_key: str

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "trimaura-clips"
    r2_public_domain: str = ""
    r2_verify_ssl: bool = True      # set False behind corporate proxies

    # Supabase (PostgreSQL)
    supabase_url: str = ""           # e.g. https://xxxx.supabase.co
    supabase_anon_key: str = ""      # anon/public key (frontend-safe)

    # Sentry
    sentry_dsn: str = ""

    # Web Push (VAPID) — PWA push notifications
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:trimaura@solo.app"

    # App
    database_url: str = "postgresql://postgres:@localhost:5432/postgres"
    app_env: str = "development"
    port: int = 8000

    # CORS — explicit origins only (auth uses Bearer tokens, not cookies, so
    # allow_credentials stays False and wildcard origins are never allowed).
    cors_origins: str = (
        "https://bassyj32--trimaura-fastapi-app.modal.run,"
        "http://localhost:8100,http://127.0.0.1:8100"
    )

    # Per-user quotas — DB-backed (Supabase), enforced BEFORE a Modal worker
    # is spawned so abuse fails fast without burning compute. Tune via env.
    quota_max_concurrent_jobs: int = 3   # non-terminal jobs in flight at once
    quota_max_daily_jobs: int = 20       # jobs created per rolling 24h
    quota_max_clips_per_job: int = 15    # total clips per job (incl. generate-more)
    quota_generate_more_max: int = 3     # clips per generate-more call
    quota_max_upload_mb: int = 500       # hard cap on local uploads
    quota_heavy_per_minute: int = 10     # burst cap on expensive writes/min

    # Cost-caps (P0 smart protection) — bound the COST per job, not just the
    # count. Enforced pre-flight in the ASGI container (app/probe.py) BEFORE a
    # Modal worker is spawned, so over-cap sources fail fast without burning
    # compute. Cost scales with source duration (Groq transcribe is per
    # audio-hour + download/render time) and resolution (encode cost ~4x per
    # doubling of height).
    quota_max_source_minutes: int = 90   # reject longer sources
    quota_max_source_height: int = 2160  # reject taller sources (8K decode burn)
    quota_max_render_height: int = 1080  # clamp encode height (no 4K/8K encodes)
    quota_max_clip_seconds: int = 90     # clamp AI clip length (render scales with it)
    quota_probe_timeout: int = 45        # per-attempt pre-flight probe timeout (s)

    # Plan tiers — monthly allowances per user. 1 credit = 1 minute of source
    # video (the actual cost driver: transcription is per audio-hour). Caps are
    # tuned so every tier stays profitable even at 100% use; top-ups convert
    # overage into revenue instead of friction.
    tier_limits: dict = {
        "free": {
            "monthly_credits": 60, "monthly_clips": 10, "jobs_per_day": 2,
            "concurrent": 1, "max_source_min": 15, "max_clips_per_job": 5,
        },
        "starter": {
            "monthly_credits": 600, "monthly_clips": 100, "jobs_per_day": 5,
            "concurrent": 2, "max_source_min": 60, "max_clips_per_job": 15,
        },
        "pro": {
            "monthly_credits": 1500, "monthly_clips": 400, "jobs_per_day": 10,
            "concurrent": 4, "max_source_min": 120, "max_clips_per_job": 15,
        },
    }
    topup_credit_price: float = 0.0199   # USD per credit ($1.99 per 100 min)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# -- Auto-detect Modal environment -------------------------------------------
MODAL = os.environ.get("MODAL") == "1"

if MODAL:
    settings.app_env = "production"

# -- Cloudflare R2 toggle ---------------------------------------------------
# Cloudflare R2 S3 API TLS cert is not provisioned for this account yet,
# so uploads fail with SSLV3_ALERT_HANDSHAKE_FAILURE and only add latency
# before falling back to the Modal Volume. Keep R2 disabled until the cert
# is provisioned (https://www.cloudflarestatus.com/incidents/py46dmbg0t0t).
R2_ENABLED = False
