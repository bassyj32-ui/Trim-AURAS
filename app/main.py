import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.api.routes import router as api_router

from app.config import settings

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    send_default_pii=True,
    traces_sample_rate=0.1,
)

app = FastAPI(title="TrimAURA", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    import os
    from app.config import settings, MODAL
    from app.database import engine
    url = str(engine.url)
    # Redact password
    if "@" in url:
        prefix, rest = url.split("@", 1)
        if ":" in prefix:
            prefix = prefix.rsplit(":", 1)[0] + ":****"
        url = f"{prefix}@{rest}"
    settings_url = str(settings.database_url)
    if "@" in settings_url:
        prefix, rest = settings_url.split("@", 1)
        if ":" in prefix:
            prefix = prefix.rsplit(":", 1)[0] + ":****"
        settings_url = f"{prefix}@{rest}"
    return {
        "status": "ok",
        "modal_flag": MODAL,
        "modal_env": os.environ.get("MODAL", "0"),
        "engine_url": url,
        "settings_url": settings_url,
        "env_db_url_set": bool(os.environ.get("DATABASE_URL")),
    }


@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0


app.mount("/", StaticFiles(directory="public", html=True), name="public")
