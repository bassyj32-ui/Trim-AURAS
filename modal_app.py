"""
TrimAURA — Modal Serverless Deployment
========================================

Wraps the existing FastAPI backend into a Modal cloud app with:
  - Modal Volume for SQLite + rendered clips
  - ASGI web endpoint (min-containers=1 for fast polling)
  - Background pipeline (1200s timeout, R2/Volume fallback)
  - Status JSON files for lightweight frontend polling

Deploy:
  modal deploy modal_app.py
"""

from pathlib import Path

import modal
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Persistent Volume — SQLite, clips, status files
# ---------------------------------------------------------------------------
DATA_DIR = "/mnt/data"
STATUS_DIR = f"{DATA_DIR}/status"
CLIPS_DIR = f"{DATA_DIR}/clips"
SOURCES_DIR = f"{DATA_DIR}/sources"

data_volume = modal.Volume.from_name("trimaura-data", create_if_missing=True)


# ---------------------------------------------------------------------------
# Custom Modal Image — ffmpeg + Python deps + local code baked in
# ---------------------------------------------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.13")
    # NOTE: ffmpeg is intentionally NOT apt-installed. Debian bookworm's apt
    # ffmpeg resolves to 5.1.9, which HANGS on the face-aware piecewise crop
    # filter chain (crop=1080:1920:x='lt(t,...)*...+...') for 16:9 sources —
    # job 86 froze at frame 248 while the same chain renders fine locally on
    # gyan.dev 8.1.2 (38.6s) and on Modal for 9:16 simple-crop chains. We pin
    # an immutable BtbN static 8.1.2 build (release branch, dated autobuild)
    # with its SHA256 so an image rebuild can never silently drift back to a
    # broken apt version (same discipline as the yt-dlp/groq/opencv pins below).
    .apt_install("curl", "unzip", "xz-utils", "ca-certificates")
    .run_commands(
        # ffmpeg PIN: 8.1.2 (BtbN static, linux64-gpl) — matches local gyan.dev
        # 8.1.2 that renders the piecewise face-crop chain in 38.6s.
        # Asset: ffmpeg-n8.1.2-21-gce3c09c101-linux64-gpl-8.1.tar.xz
        # SHA256 pinned from the autobuild-2026-06-30-13-34 checksums file.
        "curl -fsSL -o /tmp/ffmpeg.tar.xz https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-06-30-13-34/ffmpeg-n8.1.2-21-gce3c09c101-linux64-gpl-8.1.tar.xz",
        "echo '0ba73bbd93472c7622f6dec26d334c5e62e64d858d072490b2844320970456cd  /tmp/ffmpeg.tar.xz' | sha256sum -c -",
        "mkdir -p /tmp/ffmpeg && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg --strip-components=1",
        "mv /tmp/ffmpeg/bin/ffmpeg /usr/local/bin/ffmpeg",
        "mv /tmp/ffmpeg/bin/ffprobe /usr/local/bin/ffprobe",
        "rm -rf /tmp/ffmpeg /tmp/ffmpeg.tar.xz",
        "ffmpeg -version | head -n 1",
        # yt-dlp 2026+ requires a JS runtime for YouTube extraction; deno is the
        # only runtime enabled by default and is auto-detected from PATH.
        "curl -fsSL -o /usr/local/bin/deno.zip https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip",
        "unzip -o /usr/local/bin/deno.zip -d /usr/local/bin/ && rm -f /usr/local/bin/deno.zip",
        # PO-token (proof-of-origin) provider — single Rust binary, no deps.
        # yt-dlp uses it to bypass YouTube's "Sign in to confirm you're not a
        # bot" challenge that Modal's datacenter IPs trigger even with cookies.
        "curl -fsSL -o /usr/local/bin/bgutil-pot https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest/download/bgutil-pot-linux-x86_64",
        "chmod +x /usr/local/bin/bgutil-pot",
    )
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.30.0",
        "sqlmodel>=0.0.22",
        "boto3>=1.35.0",
        # Pinned to exact versions verified against this codebase: loose pins
        # silently resolved to breaking majors at image rebuild (yt-dlp 2026
        # changed ImpersonateTarget, groq 1.6 changed segments to null, and
        # opencv 5.0 dropped CascadeClassifier + bundled Haar cascades).
        "groq==1.6.0",
        "openai>=1.0.0",
        "yt-dlp==2026.7.4",
        "curl_cffi>=0.14.0,<0.16",
        # yt-dlp POT provider plugin (auto-registers bgutil:http provider)
        "bgutil-ytdlp-pot-provider>=1.3.0",
        # Dodo Payments (merchant-of-record; USDT payouts) + webhook signing
        "dodopayments[webhooks]==1.113.0",
        "psycopg2-binary>=2.9.0",
        "python-multipart>=0.0.12",
        "pydantic-settings>=2.4.0",
        "tenacity>=9.0.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "sentry-sdk>=2.0.0",
        "pywebpush>=1.14.0",
        # Supabase Auth — server-side JWT verification (app/auth.py)
        "supabase>=2.10.0",
        # Face-aware crop: OpenCV Haar cascades (bundled with the wheel) — no
        # model downloads, no fragile mediapipe build on Python 3.13. The
        # mediapipe path in face_track.py only activates if it's importable.
        "opencv-python-headless==4.13.0.92",
    )
    .env({"MODAL": "1"})
    .add_local_dir("./app", remote_path="/root/app", copy=True)
    .add_local_dir("./assets", remote_path="/root/assets", copy=True)
    .add_local_dir("./prompts", remote_path="/root/prompts", copy=True)
    .add_local_dir("./public", remote_path="/root/public", copy=True)
)


# ---------------------------------------------------------------------------
# Modal App
# ---------------------------------------------------------------------------
app = modal.App("trimaura")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_status(job_id: int, status: str, progress: int, error: str | None = None):
    """Write a lightweight JSON status file on the Volume for frontend polling."""
    Path(STATUS_DIR).mkdir(parents=True, exist_ok=True)
    payload = {"status": status, "progress": progress}
    if error:
        payload["error"] = error
    Path(f"{STATUS_DIR}/job_{job_id}.json").write_text(
        __import__("json").dumps(payload)
    )
    # Commit so the web container sees the new status file immediately
    # (without this, polls may read a stale file for a long time).
    try:
        data_volume.commit()
    except Exception as e:
        print(f"[status] volume commit failed (non-fatal): {e}")


def _ensure_path():
    """Make sure /root is on sys.path so `from app.xxx` imports resolve."""
    import os
    import sys

    cwd = os.getcwd()  # typically /root in Modal containers
    for p in (cwd, os.path.join(cwd, "app")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _bootstrap():
    """sys.path + structured JSON logging + Sentry for any worker container.

    Sentry is per-process: pipeline workers never import app.main (which owns
    the web container's init), so without this, worker failures would never
    leave stderr. Safe to call everywhere — no-ops when Sentry is unset."""
    _ensure_path()
    from app.logging_conf import setup_logging
    from app.observability import init_sentry

    setup_logging()
    init_sentry()


# ---------------------------------------------------------------------------
# Retry classification
# ---------------------------------------------------------------------------
# Modal's `retries=N` retries the function on ANY exception (no
# non-retryable marker in Modal 1.5.3). The pipeline raises ValueError /
# RuntimeError for permanent problems (bad source URL, "Couldn't pick any
# watchable clips", invalid trim bounds) where a re-run just burns compute
# and paid AI calls. So workers classify via app.failures.is_transient:
# permanent errors are written as FAILED and swallowed (Modal then won't
# retry); transient errors re-raise so Modal's retries=1 respawns a fresh
# container. OOM/container loss kills the container before our except runs —
# Modal's retries=1 is what revives those jobs. The orchestrator also uses
# is_transient so transient failures never even write FAILED to the DB.
def _reset_to_retrying(job_id: int | None, exc: BaseException):
    """Undo the terminal FAILED that the pipeline wrote so the frontend never
    sees a FAILED flash (or a spurious 'Failed' push) before we retry."""
    if job_id is None:
        return
    try:
        from sqlmodel import Session

        from app.database import engine
        from app.models import Job, JobStatus

        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job and job.status != JobStatus.COMPLETED:
                # The pipeline already wrote FAILED; revert to a non-terminal
                # state. Keep progress where it was so the bar doesn't reset.
                job.status = JobStatus.PENDING
                job.error_message = f"Transient failure — retrying automatically: {str(exc)[:200]}"
                session.add(job)
                session.commit()
    except Exception as e:
        print(f"[retry] status reset failed (non-fatal): {e}")


# ===========================================================================
# 1. ASGI Web Endpoint
# ===========================================================================
@app.function(
    image=image,
    volumes={DATA_DIR: data_volume},
    secrets=[
        modal.Secret.from_name("trimaura-secrets-v2"),
        modal.Secret.from_name("trimaura-supabase-keys"),
        modal.Secret.from_name("trimaura-db-url"),
        modal.Secret.from_name("trimaura-share-secret"),
    ],
    scaledown_window=120,
)
@modal.asgi_app()
def fastapi_app():
    _ensure_path()

    for d in (STATUS_DIR, CLIPS_DIR, SOURCES_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)

    # Auto-cleanup old failed/pending jobs on startup
    try:
        from datetime import datetime, timedelta

        from sqlmodel import Session, select

        from app.database import engine, init_db
        from app.models import Job, JobStatus

        init_db()
        cutoff = datetime.utcnow() - timedelta(hours=24)
        # Anything not COMPLETED that's been alive >24h is stuck (pipeline max is 1h).
        stale_statuses = [
            JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.TRANSCRIBING,
            JobStatus.ANALYZING, JobStatus.RENDERING, JobStatus.FAILED,
        ]
        with Session(engine) as session:
            old_jobs = session.exec(
                select(Job).where(Job.created_at < cutoff).where(
                    Job.status.in_(stale_statuses)
                )
            ).all()
            for j in old_jobs:
                for c in j.clips:
                    c.deleted = True
                    session.add(c)
                session.delete(j)
            session.commit()
            if old_jobs:
                print(f"[Startup] Cleaned up {len(old_jobs)} old failed/pending jobs")
    except Exception as e:
        print(f"[Startup] Cleanup error (non-fatal): {e}")

    from app.main import app as _fastapi_app

    return _fastapi_app


# ===========================================================================
# 2. Background Pipeline Functions
# ===========================================================================
# Shared kwargs for pipeline functions
_PIPELINE_KWARGS = dict(
    image=image,
    volumes={DATA_DIR: data_volume},
    secrets=[
        modal.Secret.from_name("trimaura-secrets-v2"),
        modal.Secret.from_name("trimaura-supabase-keys"),
        modal.Secret.from_name("trimaura-db-url"),
    ],
    # 2 CPU per pipeline container: render is CPU-bound (libx264), so this
    # roughly halves per-clip render wall-clock under back-to-back load.
    cpu=2.0,
    scaledown_window=300,
    # One automatic re-run on infra-level failure (OOM kill, container loss,
    # network blip). Workers classify permanent errors themselves so a bad
    # source URL never triggers a wasteful re-run (see _is_transient).
    retries=1,
)

# Lighter ops don't need 2 vCPU — trim re-renders one short clip and
# generate-more reuses the saved source + transcript, so halving their
# container cost is invisible to users.
_LIGHT_PIPELINE_KWARGS = dict(_PIPELINE_KWARGS, cpu=1.0)


@app.function(timeout=3600, **_PIPELINE_KWARGS)
def process_pipeline(job_id: int, job_data: dict | None = None):
    _write_status(job_id, "DOWNLOADING", 10)
    try:
        _bootstrap()

        from app.database import engine, init_db

        init_db()

        # Persist the job's cookies.txt from the payload so the download phase
        # can authorize YouTube/TikTok/Instagram even if the ASGI container's
        # Volume write hasn't propagated yet.
        if job_data and job_data.get("cookies"):
            from app.pipeline.orchestrator import save_job_cookies

            save_job_cookies(job_id, job_data.get("cookies"))

        # If the job record written by the ASGI container isn't visible yet
        # (Modal Volume propagation delay), create it locally from the payload
        # that was passed alongside job_id.
        if job_data is not None:
            from sqlmodel import Session

            from app.models import Job

            with Session(engine) as session:
                existing = session.get(Job, job_id)
                if existing is None:
                    job = Job(**{k: v for k, v in job_data.items() if k not in ("id", "cookies")})
                    job.id = job_id
                    session.add(job)
                    session.commit()

        import asyncio

        # Wait for the uploaded source file to appear on the Volume (it was
        # written by the ASGI container and may not have synced yet). Reload
        # each iteration with a FRESH handle — Modal volumes don't auto-
        # propagate between containers; only a reload() sees another
        # container's commit, and a fresh from_name() handle is required to
        # pick up the latest volume state.
        import os
        import time

        from app.pipeline.orchestrator import execute_pipeline
        if job_data and "source_url" in job_data and job_data["source_url"].startswith("/mnt/data/"):
            waited = 0
            found = False
            for _ in range(120):  # up to ~120 seconds
                try:
                    modal.Volume.from_name("trimaura-data").reload()
                except Exception as e:
                    print(f"[pipeline] volume reload failed (non-fatal): {e}")
                if os.path.exists(job_data["source_url"]):
                    print(f"Source file found after ~{waited}s: {job_data['source_url']}")
                    found = True
                    break
                time.sleep(1)
                waited += 1
            if not found:
                # Bulletproof fallback: read the file server-side from the
                # volume API, bypassing the local mount (which may never
                # refresh even after reload()).
                try:
                    rel = job_data["source_url"].replace("/mnt/data/", "", 1)
                    data = modal.Volume.from_name("trimaura-data").read_file(rel)
                    Path(job_data["source_url"]).parent.mkdir(parents=True, exist_ok=True)
                    with open(job_data["source_url"], "wb") as fh:
                        fh.write(data)
                    print(f"[pipeline] source recovered via read_file: {job_data['source_url']} ({len(data)} bytes)")
                except Exception as e:
                    print(f"Source file NOT found after {waited}s: {job_data['source_url']} "
                          f"(read_file fallback failed: {e})")

        asyncio.run(execute_pipeline(job_id))
        _sync_clips_to_volume(job_id)
        _write_status(job_id, "COMPLETED", 100)
    except Exception as exc:
        from app.failures import is_transient

        if is_transient(exc):
            # Transient failure — Modal's retries=1 will respawn this function.
            # Undo the FAILED the pipeline wrote so the UI keeps waiting.
            _reset_to_retrying(job_id, exc)
            _write_status(job_id, "RETRYING", 0, str(exc))
            raise
        # Permanent failure — publish whatever clips already rendered, mark
        # FAILED, and swallow so Modal does NOT re-run the paid pipeline.
        try:
            _sync_clips_to_volume(job_id)
        except Exception as sync_exc:
            print(f"[pipeline] failed-path clip sync error (non-fatal): {sync_exc}")
        _write_status(job_id, "FAILED", 0, str(exc))
        return


@app.function(timeout=600, **_LIGHT_PIPELINE_KWARGS)
def process_generate_more(job_id: int, count: int = 3):
    _write_status(job_id, "ANALYZING", 40)
    try:
        _bootstrap()

        import asyncio

        from app.pipeline.orchestrator import generate_more_clips

        asyncio.run(generate_more_clips(job_id, count=count))
        _sync_clips_to_volume(job_id)
        _write_status(job_id, "COMPLETED", 100)
    except Exception as exc:
        from app.failures import is_transient

        if is_transient(exc):
            _reset_to_retrying(job_id, exc)
            _write_status(job_id, "RETRYING", 0, str(exc))
            raise
        _write_status(job_id, "FAILED", 0, str(exc))
        return


@app.function(timeout=600, **_LIGHT_PIPELINE_KWARGS)
def process_trim_clip(clip_id: int, new_start: float, new_end: float):
    """Re-render a single clip with tightened boundaries (worker).

    Runs ``trim_clip`` (source + transcript reuse, no re-analysis) and
    commits the Volume so the web container can serve the updated file.
    """
    job_id = None
    try:
        _bootstrap()

        from app.database import engine, init_db

        init_db()

        # Resolve job_id from the clip so status files stay consistent.
        from sqlmodel import Session

        from app.models import VideoClip

        with Session(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip:
                job_id = clip.job_id
        if job_id is not None:
            _write_status(job_id, "RENDERING", 60)

        import asyncio

        from app.pipeline.orchestrator import trim_clip

        asyncio.run(trim_clip(clip_id, new_start, new_end))
        if job_id is not None:
            _sync_clips_to_volume(job_id)
            _write_status(job_id, "COMPLETED", 100)
    except Exception as exc:
        from app.failures import is_transient

        if is_transient(exc):
            _reset_to_retrying(job_id, exc)
            if job_id is not None:
                _write_status(job_id, "RETRYING", 0, str(exc))
            raise
        if job_id is not None:
            _write_status(job_id, "FAILED", 0, str(exc))
        return


def _sync_clips_to_volume(job_id: int):
    """Copy locally-rendered clips to the Volume so they can be served
    by the `/api/clips/{id}/download` endpoint."""
    import shutil

    from sqlmodel import Session

    from app.database import engine
    from app.models import VideoClip

    with Session(engine) as session:
        clips = (
            session.query(VideoClip)
            .filter(VideoClip.job_id == job_id, VideoClip.deleted == False)
            .all()
        )
        for clip in clips:
            local_path = clip.r2_url
            if local_path and Path(local_path).exists():
                dest = Path(CLIPS_DIR) / f"{job_id}_{clip.id}.mp4"
                if Path(local_path) == dest:
                    continue  # already in place on the Volume
                shutil.copy2(local_path, str(dest))
                clip.r2_url = str(dest)  # Volume path, readable by download endpoint
                session.add(clip)
        session.commit()
        # Force Volume commit so the web container can see the new files immediately
        data_volume.commit()


# ===========================================================================
# 3. Debug probe — verify deno + cookies work inside the DEPLOYED image
# ===========================================================================
@app.function(timeout=60, image=image, volumes={DATA_DIR: data_volume})
def ffmpeg_probe() -> str:
    """Print the exact ffmpeg version baked into the deployed image (pin check).

    Also writes it to the Volume as ffmpeg_probe.txt so it survives terminal
    output-swallowing. Run via:  modal run modal_app.py::ffmpeg_probe
    """
    import subprocess

    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    lines = out.stdout.splitlines()
    result = f"{lines[0]} | {lines[1] if len(lines) > 1 else ''}" if lines else f"ffmpeg MISSING: {out.stderr[:300]}"
    try:
        Path(f"{DATA_DIR}/ffmpeg_probe.txt").write_text(result)
        data_volume.commit()
    except Exception as e:
        result += f" (volume write failed: {e})"
    return result


@app.function(timeout=600, image=image, volumes={DATA_DIR: data_volume}, secrets=[
    modal.Secret.from_name("trimaura-secrets-v2"),
    modal.Secret.from_name("trimaura-supabase-keys"),
    modal.Secret.from_name("trimaura-db-url"),
])
def yt_probe(url: str, cookies_text: str = "", impersonate: bool = False) -> str:
    """Probe the deployed image: does deno exist? does yt-dlp extract formats
    with the given cookies? Run via:  modal run modal_app.py::yt_probe ..."""
    import os
    import subprocess
    from pathlib import Path

    lines = []
    lines.append(f"python: {os.sys.version.split()[0]}")
    # 1. deno presence
    deno = subprocess.run(["sh", "-lc", "command -v deno"], capture_output=True, text=True)
    lines.append(f"deno on PATH: {deno.stdout.strip() or 'MISSING'}")
    if deno.returncode == 0:
        ver = subprocess.run(["deno", "--version"], capture_output=True, text=True)
        lines.append(f"deno version: {ver.stdout.splitlines()[0] if ver.stdout else '?'}")
    # 2. package versions
    pkgs = subprocess.run(
        ["sh", "-lc", "python -c \"import yt_dlp, curl_cffi; print('yt-dlp', yt_dlp.version.__version__); print('curl_cffi', curl_cffi.__version__)\""],
        capture_output=True, text=True)
    lines.append(pkgs.stdout.strip() or pkgs.stderr.strip())
    # 3. cookies — from the argument, or fall back to a probe file on the
    #    Volume (uploaded via: modal volume put trimaura-data cookies/probe.txt cookies.txt)
    cookie_path = None
    if cookies_text.strip():
        cookie_path = "/tmp/probe_cookies.txt"
        Path(cookie_path).write_text(cookies_text.replace("\r\n", "\n"))
        lines.append(f"cookies: from arg ({len(cookies_text)} chars)")
    elif Path(f"{DATA_DIR}/cookies/probe.txt").exists():
        cookie_path = f"{DATA_DIR}/cookies/probe.txt"
        lines.append(f"cookies: from volume ({Path(cookie_path).stat().st_size} bytes)")
    else:
        lines.append("cookies: none")
    # 3.5 impersonate targets available
    ip = subprocess.run(["yt-dlp", "--list-impersonate-targets"], capture_output=True, text=True, timeout=60)
    targets_out = (ip.stdout or ip.stderr or "").strip()
    lines.append("impersonate targets list:")
    lines += ["  " + l for l in targets_out.splitlines()[:20]]
    # 3.6 curl_cffi direct check
    cc = subprocess.run(
        ["sh", "-lc", "python -c \"import curl_cffi, sys; print('ok', curl_cffi.__version__, sys.modules.get('curl_cffi._wrapper'))\""],
        capture_output=True, text=True)
    lines.append("curl_cffi check: " + (cc.stdout.strip() or cc.stderr.strip()[:200]))
    # 4. start POT server (bgutil-pot) — required by the yt-dlp plugin
    _pot_proc = subprocess.Popen(
        ["bgutil-pot", "server", "--host", "127.0.0.1", "--port", "4416"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import time
    pot_ok = False
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=2)
            pot_ok = True
            break
        except Exception:
            time.sleep(0.5)
    lines.append(f"pot server: {'UP on 4416' if pot_ok else 'FAILED to start'}")
    # plugin registration check
    vv = subprocess.run(
        ["yt-dlp", "-v", "--skip-download", url],
        capture_output=True, text=True, timeout=180)
    vv_out = (vv.stdout or "") + (vv.stderr or "")
    pot_line = next((l for l in vv_out.splitlines() if "PO Token Providers" in l), "not found")
    lines.append("pot providers: " + pot_line.strip())
    # 4.5 detailed verbose run with cookies+impersonate to see if the POT is attached
    if cookie_path:
        vv2 = subprocess.run(
            ["yt-dlp", "-v", "--skip-download", "--cookies", cookie_path,
             "--impersonate", "chrome", url],
            capture_output=True, text=True, timeout=240)
        v2 = ((vv2.stdout or "") + (vv2.stderr or ""))
        for key in ("pot", "visitor", "token", "Bot", "bot", "403", "confirm", "player_client", "player client", "nsig", "n-sig"):
            hit = next((l for l in v2.splitlines() if key.lower() in l.lower()), None)
            if hit:
                lines.append(f"v-{key}: {hit.strip()[:220]}")
        if vv2.returncode != 0:
            tail = [l for l in v2.splitlines() if l.strip()][-4:]
            lines += ["  v-tail: " + t.strip()[:220] for t in tail]
    # 5. extraction — try several player clients & impersonation combos
    clients = ["default", "tv", "web_embedded", "android", "android_vr", "ios"]
    base_cmd = ["yt-dlp", "--skip-download", "--no-warnings", url]
    if cookie_path:
        base_cmd += ["--cookies", cookie_path]
    results = []
    for client in clients:
        for imp in (["chrome"] if impersonate else [None]):
            cmd = base_cmd + ["--extractor-args", f"youtube:player_client={client}"]
            if imp:
                cmd += ["--impersonate", imp]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            if proc.returncode == 0:
                results.append(f"OK    client={client} impersonate={imp or 'off'} formats={len(out.splitlines())}")
            else:
                tail = " | ".join(err.strip().splitlines()[-2:]) if err else "?"
                results.append(f"FAIL  client={client} impersonate={imp or 'off'} :: {tail[-180:]}")
    lines += results
    result = "\n".join(lines)
    # Write result to the Volume so it can be read back locally even when
    # `modal run` console output isn't captured.
    try:
        Path(f"{DATA_DIR}/cookies/probe_result.txt").write_text(result)
        data_volume.commit()
    except Exception as e:
        result += f"\n(write result to volume failed: {e})"
    return result


@app.function(timeout=120, image=image, volumes={DATA_DIR: data_volume})
def ass_burn_probe() -> str:
    """Verify the PlayResX/PlayResY burn-caption fix INSIDE the deployed image.

    Renders the same karaoke ASS onto a black 1080x1920 canvas at t=2.0 twice
    — once WITHOUT PlayRes, once WITH PlayResX=1080/PlayResY=1920 — and reports
    the text bounding box for each:
      * no PlayRes  -> libass defaults to a 384x288 canvas, so the text burns
                       ~4x oversized at the TOP (expected y0~60, y1~680)
      * PlayRes     -> text at bottom center, margin_v=180 (expected y~1700-1740)

    Run via:  modal run modal_app.py::ass_burn_probe
    """
    import subprocess
    from pathlib import Path

    W, H = 1080, 1920
    work = Path("/tmp/assprobe")
    work.mkdir(parents=True, exist_ok=True)

    ffv = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    ffv = (ffv.stdout or ffv.stderr).splitlines()[0] if ffv.stdout else "MISSING"

    style_line = ("Style: Default,Arial Black,36,&H00FFFFFF,&H00FF3333,&H00000000,"
                  "&H00000000,0,0,0,0,100,100,0,0,1,6,0,2,20,20,180,1")
    kara_text = (r"{\k50}this {\k40}is {\k60}a {\k60}test {\k60}phrase "
                 r"{\k60}with {\k60}several {\k60}words {\k60}aloud")
    header_noplayres = "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes"
    header_playres = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
                      "WrapStyle: 0\nScaledBorderAndShadow: yes")
    body_tmpl = (
        "{header}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "{style}\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:05.90,Default,,0,0,0,,{text}\n"
    )

    def bbox(png: Path) -> str:
        raw = work / (png.stem + ".raw")
        r = subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(png),
            "-vf", "scale=54:96", "-f", "rawvideo", "-pix_fmt", "gray", str(raw),
        ], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return f"SCALE_FAILED: {r.stderr[-200:]}"
        data = raw.read_bytes()
        xs, ys = [], []
        for y in range(96):
            for x in range(54):
                if data[y * 54 + x] > 24:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return "NO_TEXT (empty frame)"
        cnt = len(xs)
        x0, y0, x1, y1 = min(xs) * 20, min(ys) * 20, max(xs) * 20 + 20, max(ys) * 20 + 20
        return f"bbox x={x0}-{x1} y={y0}-{y1} area={cnt} (y0={y0/H:.1%} y1={y1/H:.1%})"

    results = [f"ffmpeg: {ffv}", f"canvas: {W}x{H}"]
    for name, header in (("no_playres", header_noplayres), ("with_playres", header_playres)):
        ass = work / f"{name}.ass"
        ass.write_text(body_tmpl.format(header=header, style=style_line, text=kara_text), encoding="utf-8")
        png = work / f"{name}.png"
        r = subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=black:s=1080x1920:d=10:r=30",
            "-ss", "2.0", "-frames:v", "1",
            "-vf", f"subtitles={ass.name}:charenc=utf-8", png.name,
        ], cwd=str(work), capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            results.append(f"{name}: BURN_FAILED: {r.stderr[-300:]}")
        else:
            results.append(f"{name}: {bbox(png)}")

    result = "\n".join(results)
    try:
        Path(f"{DATA_DIR}/diag").mkdir(parents=True, exist_ok=True)
        Path(f"{DATA_DIR}/diag/ass_burn_probe.txt").write_text(result)
        data_volume.commit()
    except Exception as e:
        result += f"\n(volume write failed: {e})"
    return result


# ===========================================================================
# 3.5 Uptime monitor — every 5 min verify the app + DB are alive
# ===========================================================================
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("trimaura-secrets-v2"),
        modal.Secret.from_name("trimaura-supabase-keys"),
        modal.Secret.from_name("trimaura-db-url"),
    ],
    schedule=modal.Cron("*/5 * * * *"),
)
def health_check() -> str:
    """Probe the deployed app's /health AND the database every 5 minutes.

    On any failure it explicitly sends a Sentry event (alert rules can page
    you) and raises so Modal logs the error. Pair with an external uptime
    monitor (UptimeRobot etc.) for independence from Modal itself.
    """
    _bootstrap()
    import httpx

    from app.database import engine

    problems = []
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        problems.append(f"db: {exc}")

    try:
        try:
            url = fastapi_app.get_web_url()
        except Exception:
            url = "https://bassyj32--trimaura-fastapi-app.modal.run"
        resp = httpx.get(url + "/health", timeout=15)
        if resp.status_code != 200:
            problems.append(f"web: HTTP {resp.status_code}")
    except Exception as exc:
        problems.append(f"web: {exc}")

    if problems:
        try:
            import sentry_sdk

            sentry_sdk.capture_message(
                "Uptime check failed: " + "; ".join(problems), level="error"
            )
        except Exception:
            pass
        raise RuntimeError("health_check failed: " + "; ".join(problems))
    return "ok"


# ===========================================================================
# 4. Entrypoint — verify image builds
# ===========================================================================
@app.local_entrypoint()
def build_check():
    import subprocess

    subprocess.run(["ffmpeg", "-version"], check=True)
    print("✅ Image build verified — ffmpeg + deps ready.")
    print('Run  » modal deploy modal_app.py  «  to deploy.')
