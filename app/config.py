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

    # App
    database_url: str = "postgresql://postgres:@localhost:5432/postgres"
    app_env: str = "development"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# -- Auto-detect Modal environment -------------------------------------------
MODAL = os.environ.get("MODAL") == "1"

if MODAL:
    settings.app_env = "production"

# -- Cloudflare R2 toggle ---------------------------------------------------
# Cloudflare R2 S3 API TLS cert is not provisioned for this account yet.
# Set True once resolved (https://www.cloudflarestatus.com/incidents/py46dmbg0t0t)
R2_ENABLED = True
