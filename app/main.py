import logging
import time
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.api.routes import router as api_router
from app.config import settings
from app.database import engine, init_db
from app.models import VideoClip
from app.observability import bootstrap
from app.ratelimit import check_ip_rate
from app.recovery import start_recovery
from app.share import verify_share_token

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
async def ip_rate_limit(request: Request, call_next):
    """DB-backed per-IP cap on /api/* (stops scraping/hammering)."""
    if request.url.path.startswith("/api/"):
        try:
            check_ip_rate(request)
        except HTTPException as exc:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
    return await call_next(request)


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


# ---------------------------------------------------------------------------
# Public share page — server-rendered so social crawlers (WhatsApp/Discord/X)
# read real og: tags from the HTML (a JS-only page renders a blank card).
# Gated by the same unguessable HMAC token as /api/public/clips/*.
# ---------------------------------------------------------------------------
def _clip_share_html(
    clip: VideoClip,
    token: str,
    base_url: str,
) -> str:
    title = clip.title_curiosity or clip.title_direct or f"Clip {clip.id}"
    description = clip.description or ""
    poster = f"{base_url}/api/public/clips/{clip.id}/poster?t={quote(token)}"
    video = f"{base_url}/api/public/clips/{clip.id}/download?t={quote(token)}"
    score = clip.viral_score if clip.viral_score is not None else "—"

    og_title = f"“{title}”"
    og_desc = description[:300] or "A TrimAURA clip."

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0f0f10">
<title>{esc(og_title)} — TrimAURA</title>
<meta property="og:type" content="video.other">
<meta property="og:title" content="{esc(og_title)}">
<meta property="og:description" content="{esc(og_desc)}">
<meta property="og:image" content="{esc(poster)}">
<meta property="og:video" content="{esc(video)}">
<meta property="og:video:type" content="video/mp4">
<meta property="og:video:width" content="1080">
<meta property="og:video:height" content="1920">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(og_title)}">
<meta name="twitter:description" content="{esc(og_desc)}">
<meta name="twitter:image" content="{esc(poster)}">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ height:100%; background:#0f0f10; color:#f4f1ea; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  body {{ display:flex; flex-direction:column; align-items:center; overflow-x:hidden; }}
  .topbar {{ width:100%; max-width:560px; display:flex; align-items:center; justify-content:space-between; padding:14px 16px; }}
  .brand {{ font-size:14px; font-weight:800; letter-spacing:0.5px; color:#f4f1ea; }}
  .brand span {{ color:#d8a24a; }}
  .player-wrap {{ width:100%; max-width:480px; padding:0 12px; }}
  video {{ width:100%; aspect-ratio:9/16; background:#000; border-radius:16px; object-fit:cover; }}
  .meta {{ width:100%; max-width:480px; padding:14px 16px 8px; }}
  .title {{ font-size:17px; font-weight:700; line-height:1.35; }}
  .sub {{ font-size:12px; color:#9a968f; margin-top:6px; }}
  .actions {{ width:100%; max-width:480px; display:flex; gap:10px; padding:8px 16px 28px; }}
  .actions a, .actions button {{
    flex:1; text-align:center; text-decoration:none; border:none; cursor:pointer;
    padding:12px 10px; border-radius:12px; font-size:14px; font-weight:700; font-family:inherit;
    background:#d8a24a; color:#17130d;
  }}
  .actions .ghost {{ background:#26262a; color:#f4f1ea; }}
  .toast {{ position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
    background:#26262a; color:#f4f1ea; padding:10px 18px; border-radius:999px; font-size:13px;
    opacity:0; transition:opacity .2s; pointer-events:none; white-space:nowrap; }}
  .toast.show {{ opacity:1; }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">TRIM<span>AURA</span></div>
    <div style="font-size:12px;color:#9a968f;">clip viewer</div>
  </div>
  <div class="player-wrap">
    <video src="{esc(video)}" controls playsinline preload="metadata" poster="{esc(poster)}"></video>
  </div>
  <div class="meta">
    <div class="title">{esc(title)}</div>
    <div class="sub">Viral score {esc(str(score))}/100 · {clip.duration:.1f}s · {esc(clip.hashtags or "")}</div>
  </div>
  <div class="actions">
    <button id="copyLinkBtn">Copy Link</button>
    <a id="downloadLink" class="ghost" href="{esc(video)}" download>Download MP4</a>
  </div>
  <div class="toast" id="toast"></div>
<script>
  const shareUrl = window.location.href.split('#')[0];
  const toastEl = document.getElementById('toast');
  document.getElementById('copyLinkBtn').onclick = () => {{
    navigator.clipboard.writeText(shareUrl).then(
      () => {{ toastEl.textContent = 'Clip link copied'; toastEl.classList.add('show'); setTimeout(() => toastEl.classList.remove('show'), 1800); }},
      () => {{ toastEl.textContent = 'Copy failed — long-press the link instead'; toastEl.classList.add('show'); setTimeout(() => toastEl.classList.remove('show'), 1800); }}
    );
  }};
</script>
</body>
</html>"""


@app.get("/clip/{clip_id}")
def clip_share_page(clip_id: int, request: Request, t: str = ""):
    """Server-rendered share page: real OG meta for crawlers + working player."""
    if not verify_share_token(clip_id, t):
        raise HTTPException(404, "Clip not found")
    with Session(engine) as session:
        clip = session.get(VideoClip, clip_id)
        if not clip or clip.deleted:
            raise HTTPException(404, "Clip not found")
    base_url = str(request.base_url).rstrip("/")
    return HTMLResponse(_clip_share_html(clip, t, base_url))


app.mount("/", StaticFiles(directory="public", html=True), name="public")
