import os
import shutil
from pathlib import Path

import yt_dlp

WORKSPACE = Path("tmp") / "downloads"


def _is_google_drive(url: str) -> bool:
    return "drive.google.com" in url


def _is_local_path(value: str) -> bool:
    p = Path(value)
    return p.exists() and p.is_file()


def _get_ydl_opts(output_path: str) -> dict:
    """Return yt-dlp options that try several clients to bypass bot checks."""
    return {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        # tv#embed is a combined client that avoids YouTube's sign-in wall.
        # Also skip webpage/JS parsing to avoid bot-detection triggers.
        "extractor_args": {
            "youtube": {
                "player_client": ["tv#embed"],
                "player_skip": ["webpage", "js"],
            }
        },
        # Mimic a real browser so we don't get blocked before extraction
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }


def execute_download(source: str, cookies_file: str | None = None) -> str:
    """Resolve a video source to a local file path.

    V1 supports:
      - Local file paths (just copies to workspace)
      - Google Drive URLs (downloads via yt-dlp)
    """
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Local file — just copy to workspace so pipeline can work with it
    if _is_local_path(source):
        src = Path(source)
        dest = str(WORKSPACE / src.name)
        shutil.copy2(str(src), dest)
        return os.path.abspath(dest)

    # V1: only Google Drive URLs allowed from here
    if not _is_google_drive(source):
        raise ValueError(
            "V1 only supports Google Drive URLs and local file uploads. "
            f"Got: {source[:80]}"
        )

    # Google Drive download via yt-dlp
    output_path = str(WORKSPACE / "%(title)s_%(id)s.%(ext)s")
    opts = _get_ydl_opts(output_path)
    if cookies_file and Path(cookies_file).exists():
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([source])

    files = list(WORKSPACE.iterdir())
    if not files:
        raise RuntimeError("Download completed but no file found in workspace")
    latest = max(files, key=os.path.getctime)
    return os.path.abspath(latest)
