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


def execute_download(source: str) -> str:
    """Resolve a video source to a local file path.

    Supports:
      - Local file paths (just returns the path)
      - Google Drive URLs (downloads via yt-dlp)
    """
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Local file — just copy to workspace so pipeline can work with it
    if _is_local_path(source):
        src = Path(source)
        dest = str(WORKSPACE / src.name)
        shutil.copy2(str(src), dest)
        return os.path.abspath(dest)

    # Google Drive — let yt-dlp handle auth & confirmation natively
    if _is_google_drive(source):
        output_path = str(WORKSPACE / "gdrive_%(id)s.%(ext)s")
        with yt_dlp.YoutubeDL({"outtmpl": output_path, "quiet": True, "no_warnings": True}) as ydl:
            ydl.download([source])
        files = list(WORKSPACE.iterdir())
        if not files:
            raise RuntimeError("Download completed but no file found in workspace")
        latest = max(files, key=os.path.getctime)
        return os.path.abspath(latest)

    raise ValueError(
        "Unsupported source. Provide a local file path or a Google Drive URL."
    )
