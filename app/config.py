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

    # Sentry
    sentry_dsn: str = ""

    # App
    database_url: str = "sqlite:///./trimaura.db"
    app_env: str = "development"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# -- Auto-detect Modal environment -------------------------------------------
# When deployed on Modal, database_url should point to the persistent Volume.
# Override it here so the rest of the code (models, database, pipeline) works
# without any changes.
MODAL = os.environ.get("MODAL") == "1"

if MODAL:
    settings.database_url = "sqlite:////mnt/data/trimaura.db"
    settings.app_env = "production"

# -- Cloudflare R2 toggle ---------------------------------------------------
# Cloudflare R2 S3 API TLS cert is not provisioned for this account yet.
# Set True once resolved (https://www.cloudflarestatus.com/incidents/py46dmbg0t0t)
R2_ENABLED = False
