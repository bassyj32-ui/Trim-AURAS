import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import settings
from app.database import init_db
from app.observability import bootstrap
from app.recovery import start_recovery

bootstrap()

_access_log = logging.getLogger("trimaura.access")

app = FastAPI(title="TrimAURA", version="0.1.0")

# Explicit allow-list, never "*". Auth uses Bearer tokens, so credentials
# (cookies) are not needed — keeping allow_credentials=False avoids the
# browser's wildcard+credentials restriction and CSRF surface.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in settings.cors_origins.split(",") if o.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Content-Security-Policy — inline scripts force 'unsafe-inline', but this still
# blocks most injected payloads and restricts where the page can connect.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://browser.sentry-cdn.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https://*.supabase.co wss://*.supabase.co "
    "https://*.ingest.us.sentry.io https://*.modal.run wss://*.modal.run; "
    "worker-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'self'; "
    "base-uri 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if (response.headers.get("content-type") or "").startswith("text/html"):
        response.headers["Content-Security-Policy"] = _CSP
    return response


@app.middleware("http")
async def access_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:8]
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    _access_log.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - start) * 1000, 1),
        },
    )
    return response


@app.on_event("startup")
def on_startup():
    init_db()
    # Background sweep that fails jobs stuck in non-terminal states, so the
    # frontend stops polling jobs whose worker died (OOM, lost container).
    try:
        start_recovery()
    except RuntimeError:
        # No running event loop (e.g. import-time contexts) — skip gracefully.
        pass


@app.get("/health")
def health():
    import os

    from app.config import MODAL, settings
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
    1 / 0


app.mount("/", StaticFiles(directory="public", html=True), name="public")
