"""Pre-flight source probing — reject cost-heavy sources BEFORE a worker spawns.

Cost per job is driven by source duration (Groq transcription bills per
audio-hour, and download/render time scale with it) and resolution (encode
cost roughly quadruples per doubling of height). This module probes the
source cheaply in the ASGI container and rejects over-cap inputs fail-fast,
so abuse never reaches the expensive Modal pipeline.

- Local uploads: ffprobe the file directly (fast, reliable).
- Remote URLs: best-effort — try ffprobe's HTTP range probe first (direct
  video files), then yt-dlp metadata extraction (Drive/Frame.io/TikTok/IG).
  If every probe fails or times out we ALLOW the job — never block a legit
  user because probing is flaky. The pipeline's own timeouts still bound it.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings

# Browser-ish UA so ffprobe's HTTP range probe isn't 403'd by video hosts.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _ffprobe(target: str, timeout: float) -> dict[str, Any] | None:
    """ffprobe a local file or remote URL. Returns {duration_s, height} or None."""
    cmd = [
        "ffprobe", "-v", "error",
        "-user_agent", _UA,
        "-rw_timeout", "15000000",          # 15s network I/O timeout (microseconds)
        "-timeout", "15000000",             # 15s TCP connect timeout
        "-select_streams", "v:0",
        "-show_entries", "format=duration:stream=width,height",
        "-of", "json", target,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    fmt = data.get("format") or {}
    stream = (data.get("streams") or [{}])[0] or {}
    dur = fmt.get("duration")
    height = stream.get("height")
    try:
        duration_s = float(dur) if dur is not None else None
    except (TypeError, ValueError):
        duration_s = None
    try:
        height_v = int(height) if height is not None else None
    except (TypeError, ValueError):
        height_v = None
    if duration_s is None and height_v is None:
        return None
    return {"duration_s": duration_s, "height": height_v}


def _ytdlp_metadata(url: str, cookies: str, timeout: float) -> dict[str, Any] | None:
    """yt-dlp --skip-download metadata extraction. Returns {duration_s, height} or None."""
    cmd = ["yt-dlp", "--skip-download", "--no-warnings", "-J", url]
    cookie_path: str | None = None
    try:
        if cookies.strip():
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(cookies.replace("\r\n", "\n"))
                cookie_path = fh.name
            cmd += ["--cookies", cookie_path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None
    finally:
        if cookie_path:
            try:
                Path(cookie_path).unlink(missing_ok=True)
            except OSError:
                pass
    dur = data.get("duration")
    height = data.get("height")
    try:
        duration_s = float(dur) if dur is not None else None
    except (TypeError, ValueError):
        duration_s = None
    try:
        height_v = int(height) if height is not None else None
    except (TypeError, ValueError):
        height_v = None
    if duration_s is None and height_v is None:
        return None
    return {"duration_s": duration_s, "height": height_v}


def probe_source(
    path_or_url: str, *, is_local: bool, cookies: str = ""
) -> dict[str, Any] | None:
    """Best-effort probe of a source. Never raises. Returns None on failure."""
    if not is_local and path_or_url.startswith(("http://", "https://")):
        # Remote probing must not stall the API response — each attempt gets a
        # shorter cap (a valid direct-file range probe takes 1-3s anyway).
        remote_timeout = min(20.0, float(settings.quota_probe_timeout))
        info = _ffprobe(path_or_url, timeout=remote_timeout)
        if info:
            return info
        return _ytdlp_metadata(path_or_url, cookies, timeout=remote_timeout)
    return _ffprobe(path_or_url, timeout=settings.quota_probe_timeout)


def probe_and_check(
    path_or_url: str,
    *,
    is_local: bool,
    cookies: str = "",
) -> tuple[str | None, int | None]:
    """Probe a source and return (error_message, source_seconds).

    error_message is None when the source is within caps (or probing failed —
    a failed probe never blocks, the pipeline's own timeouts still bound it).
    source_seconds is the probed duration (None when unknown) and drives the
    monthly credit deduction.
    """
    info = probe_source(path_or_url, is_local=is_local, cookies=cookies)
    if info is None:
        return None, None
    duration_s = info.get("duration_s")
    try:
        seconds = int(duration_s) if duration_s else None
    except (TypeError, ValueError):
        seconds = None
    if seconds and seconds > settings.quota_max_source_minutes * 60:
        return (
            f"Source video is {seconds / 60:.0f} min long — the max is "
            f"{settings.quota_max_source_minutes} min. Trim it and retry.",
            seconds,
        )
    height = info.get("height")
    if height and height > settings.quota_max_source_height:
        return (
            f"Source video is {height}p — the max is "
            f"{settings.quota_max_source_height}p. Use a lower-resolution copy.",
            seconds,
        )
    return None, seconds


def check_source_limits(
    path_or_url: str,
    *,
    is_local: bool,
    cookies: str = "",
) -> str | None:
    """Return an error message if the source exceeds cost caps, else None.

    Thin wrapper over probe_and_check for callers that only need the verdict.
    """
    return probe_and_check(path_or_url, is_local=is_local, cookies=cookies)[0]


def clamp_render_height(preferred_height: int | None) -> int:
    """Cap the encode height so no client can request a 4K/8K render.

    0 means "original file" — clamp it too, since a 4K encode costs ~4x a
    1080p one for near-zero virality benefit.
    """
    wanted = preferred_height if preferred_height else settings.quota_max_render_height
    return min(wanted, settings.quota_max_render_height)
