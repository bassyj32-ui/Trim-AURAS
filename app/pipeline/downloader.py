import base64
import os
import re
import shutil
import uuid
from pathlib import Path

import httpx
import yt_dlp

WORKSPACE = Path("tmp") / "downloads"

# Browser-like headers so Frame.io / GDrive don't block us
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".wmv", ".mts", ".m2ts"}


def _is_youtube(url: str) -> bool:
    """True for any youtube.com / youtu.be link (watch, shorts, live, embed)."""
    u = (url or "").strip().lower()
    return "youtube.com" in u or "youtu.be" in u

# Frame.io "next" share links are served through the GraphQL API. Anonymous
# viewers authenticate with `x-frameio-share-authentication: base64(share_id)`
# plus any client/session headers — no real account needed.
_FRAMEIO_GQL_URL = "https://api.frame.io/graphql"
_FRAMEIO_GQL_LIST = """query GetShareAssets($shareId: ID!) {
  share(shareId: $shareId) {
    collectionAssets(assetType: FILE, page: {first: 200}) {
      nodes { id }
    }
  }
}"""
_FRAMEIO_GQL_ASSETS = """query GetAssetsForViewer($assetIds: [ID!]!) @stewardship(stewards: [VIEWER]) {
  assets(assetIds: $assetIds) {
    id name assetType
    ... on VideoAsset {
      media {
        id duration filesize
        metadata { originalHeight originalWidth }
        original { downloadUrl filesizeInBytes }
        videoTranscodes { key downloadUrl filesizeInBytes height width codec }
      }
    }
  }
}"""


def _frameio_headers(share_id: str, op: str) -> dict:
    return {
        "User-Agent": _HEADERS["User-Agent"],
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://next.frame.io",
        "Referer": "https://next.frame.io/",
        "x-frameio-share-authentication": base64.b64encode(share_id.encode()).decode(),
        "x-frameio-session-id": str(uuid.uuid4()),
        "apollographql-client-name": "web-app",
        "apollographql-client-version": "@frameio/next-web-app@630.0",
        "x-gql-op": op,
    }


def _is_frameio(url: str) -> bool:
    return "frame.io" in url


def _is_direct_file(url: str) -> bool:
    """A plain link to a video/audio file we can stream straight down."""
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    path = re.split(r"[?#]", url)[0].lower()
    return path.endswith(tuple(_VIDEO_EXTS)) or path.endswith((".m4a", ".mp3", ".wav"))


def _is_local_path(value: str) -> bool:
    p = Path(value)
    return p.exists() and p.is_file()


def _ensure_pot_server() -> bool:
    """Start the bgutil PO-token provider (single Rust binary) on localhost:4416.

    yt-dlp's `bgutil-ytdlp-pot-provider` plugin auto-connects to this server to
    mint proof-of-origin tokens, which help bypass YouTube's "Sign in to
    confirm you're not a bot" challenge on datacenter IPs (Modal). No-op when
    the binary isn't installed (local dev) or the server is already up.
    """
    import shutil
    import subprocess
    import time

    if not shutil.which("bgutil-pot"):
        return False
    try:
        httpx.get("http://127.0.0.1:4416/ping", timeout=2.0)
        return True  # already running
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["bgutil-pot", "server", "--host", "127.0.0.1", "--port", "4416"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return False
    for _ in range(40):  # wait up to ~20s for the server to come up
        try:
            httpx.get("http://127.0.0.1:4416/ping", timeout=2.0)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _get_ydl_opts(output_path: str, preferred_height: int = 1080) -> dict:
    """Return yt-dlp options that try several clients to bypass bot checks."""
    fmt = f"best[height<={preferred_height}]/best" if preferred_height > 0 else "best"
    opts = {
        "outtmpl": output_path,
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        # "default" lets yt-dlp auto-pick the player client that passes
        # YouTube's bot check (tv_embedded works as of 2026; tv#embed no
        # longer does).
        "extractor_args": {
            "youtube": {
                "player_client": ["default"],
            }
        },
        # Mimic a real browser so we don't get blocked before extraction
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    # TLS impersonation (Chrome fingerprint via curl_cffi) helps against
    # YouTube's anti-bot; silently skipped when curl_cffi isn't installed.
    # yt-dlp 2025+ requires an ImpersonateTarget OBJECT here — a raw string
    # like "chrome" crashes YoutubeDL.__init__ with a silent AssertionError.
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget

        opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except ImportError:
        pass
    return opts


def execute_download(source: str, cookies_file: str | None = None, preferred_height: int = 1080) -> str:
    """Resolve a video source to a local file path.

    Supports:
      - Local file paths (just copies to workspace)
      - Frame.io share links (downloads via Frame.io GraphQL share API)
      - Direct video file URLs (streams straight down)
      - Any other http(s) link — YouTube, TikTok, Instagram, Google Drive,
        etc. — downloaded via yt-dlp

    `preferred_height` caps the downloaded resolution (default 1080p).
    """
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Local file — just copy to workspace so pipeline can work with it
    if _is_local_path(source):
        src = Path(source)
        dest = str(WORKSPACE / src.name)
        shutil.copy2(str(src), dest)
        return os.path.abspath(dest)

    # Frame.io share link → use the share API
    if _is_frameio(source):
        return _download_frameio(source, preferred_height=preferred_height)

    # Direct file link → stream it down
    if _is_direct_file(source):
        return _download_direct(source)

    # YouTube is disabled at this stage — Modal datacenter IPs get bot-flagged
    # ("Sign in to confirm you're not a bot") even with cookies/impersonation,
    # so a YouTube job would just fail. Fail fast with a clear message.
    if _is_youtube(source):
        raise ValueError(
            "YouTube is disabled at this stage — use a direct video link "
            "(mp4/mov), Google Drive, Frame.io, or upload the file instead"
        )

    # Everything else (TikTok, Instagram, Google Drive, ...) is handled by
    # yt-dlp. Reject non-http(s) values with a clear message.
    if not (source.startswith("http://") or source.startswith("https://")):
        raise ValueError(
            "Supported sources: YouTube, TikTok, Instagram, Google Drive, "
            "Frame.io share links, direct video file links, or local file "
            f"uploads. Got: {source[:80]}"
        )

    # Download via yt-dlp
    output_path = str(WORKSPACE / "%(title)s_%(id)s.%(ext)s")
    opts = _get_ydl_opts(output_path, preferred_height=preferred_height)
    if cookies_file and Path(cookies_file).exists():
        opts["cookiefile"] = cookies_file

    # Start the PO-token provider so yt-dlp can mint proof-of-origin tokens
    # (helps against YouTube's bot challenge on datacenter IPs).
    _ensure_pot_server()

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([source])

    files = list(WORKSPACE.iterdir())
    if not files:
        raise RuntimeError("Download completed but no file found in workspace")
    latest = max(files, key=os.path.getctime)
    return os.path.abspath(latest)


def _extract_share_id(url: str) -> str:
    """Pull the Frame.io share id out of common link shapes."""
    # https://share.frame.io/{token}
    m = re.search(r"share\.frame\.io/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    # https://frame.io/s/{token}
    m = re.search(r"frame\.io/s/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    # https://next.frame.io/share/{uuid} or .../share/{uuid}/view/{asset}
    m = re.search(r"(?:next\.)?frame\.io/share/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    # fallback: last non-empty path segment
    parts = [p for p in url.rstrip("/").split("/") if p]
    if parts:
        return parts[-1].split("?")[0]
    raise ValueError(f"Could not find a Frame.io share id in: {url[:120]}")


def _extract_asset_id(url: str) -> str | None:
    """Pull the asset id out of a next.frame.io /share/{id}/view/{asset} URL."""
    m = re.search(r"/share/[A-Za-z0-9_-]+/view/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def _gql(client: httpx.Client, share_id: str, op: str, variables: dict, query: str) -> dict:
    """Run one Frame.io GraphQL call and return the JSON data (or raise)."""
    resp = client.post(
        _FRAMEIO_GQL_URL,
        headers=_frameio_headers(share_id, op),
        json={"operationName": op, "variables": variables, "query": query},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Frame.io API error ({resp.status_code}). Is the share link valid? "
            f"Share: {share_id[:12]}…"
        )
    payload = resp.json()
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
        raise RuntimeError(f"Frame.io share access denied: {msgs[:200]}")
    return payload.get("data") or {}


def _pick_transcode(video_transcodes: list, preferred_height: int) -> dict | None:
    """Pick the proxy that is closest to (and not above) the preferred height."""
    picks = [t for t in video_transcodes if t.get("key") and t.get("height") and t.get("downloadUrl")]
    if not picks:
        return None
    # Prefer the transcode with the smallest height that is >= preferred_height.
    for want in range(preferred_height, 0, -1):
        exact = [t for t in picks if t["height"] <= want]
        if exact:
            return max(exact, key=lambda t: t["height"])
    return max(picks, key=lambda t: t["height"])


def _download_frameio(url: str, preferred_height: int = 720) -> str:
    """Download the best matching video from a Frame.io share link.

    Works with both new links (next.frame.io/share/{id}/view/{asset}) and
    classic ones (share.frame.io/{token}). Uses the public GraphQL share API
    so no Frame.io account is required.
    """
    share_id = _extract_share_id(url)
    asset_id = _extract_asset_id(url)

    with httpx.Client(headers=_HEADERS, timeout=60.0, follow_redirects=True) as client:
        # Resolve the list of asset ids in the share (unless the URL already
        # points at a specific asset).
        if asset_id:
            asset_ids = [asset_id]
        else:
            data = _gql(client, share_id, "GetShareAssets",
                        {"shareId": share_id}, _FRAMEIO_GQL_LIST)
            nodes = (data.get("share") or {}).get("collectionAssets") or {}
            asset_ids = [n["id"] for n in nodes.get("nodes") or []]
            if not asset_ids:
                raise RuntimeError(f"No downloadable assets found in Frame.io share '{share_id}'.")

        data = _gql(client, share_id, "GetAssetsForViewer",
                    {"assetIds": asset_ids}, _FRAMEIO_GQL_ASSETS)
        assets = data.get("assets") or []

        videos = []
        for a in assets:
            if a.get("assetType") == "FILE" and a.get("media"):
                m = a["media"]
                videos.append({
                    "id": a["id"],
                    "name": a.get("name") or f"{a['id']}.mp4",
                    "size": m.get("filesize") or 0,
                    "transcodes": m.get("videoTranscodes") or [],
                    "original": m.get("original") or {},
                })
        if not videos:
            raise RuntimeError(
                f"No video assets found in Frame.io share '{share_id}'."
            )
        # Pick the largest video (most likely the main source) when the URL
        # didn't specify one.
        videos.sort(key=lambda v: v["size"], reverse=True)
        video = videos[0]

        if preferred_height == 0:
            # 0 = "Original" — full-resolution source file, no proxy
            dl_url = (video["original"] or {}).get("downloadUrl")
            label = "original"
        else:
            tc = _pick_transcode(video["transcodes"], preferred_height)
            if tc:
                dl_url = tc["downloadUrl"]
                label = f"{tc.get('key')} ({tc.get('width')}x{tc.get('height')})"
            else:
                dl_url = (video["original"] or {}).get("downloadUrl")
                label = "original"
        if not dl_url:
            raise RuntimeError(f"No downloadable link available for '{video['name']}'.")
        print(f"[frameio] source={video['name']} quality={label}")

        # Stream it down into the workspace
        dest = WORKSPACE / (re.sub(r"[^\w.\-]+", "_", video["name"]) or f"{share_id}.mp4")
        with client.stream("GET", dl_url) as stream:
            stream.raise_for_status()
            with open(dest, "wb") as fh:
                fh.writelines(stream.iter_bytes(chunk_size=1024 * 1024))

    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"Frame.io download produced an empty file: {dest.name}")
    return os.path.abspath(dest)


def _download_direct(url: str) -> str:
    """Stream a direct video file URL down to the workspace."""
    dest = WORKSPACE / (Path(url.split("?")[0]).name or "source_video")
    with httpx.Client(headers=_HEADERS, timeout=60.0, follow_redirects=True) as client:
        with client.stream("GET", url) as stream:
            stream.raise_for_status()
            with open(dest, "wb") as fh:
                fh.writelines(stream.iter_bytes(chunk_size=1024 * 1024))
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"Direct download produced an empty file: {dest.name}")
    return os.path.abspath(dest)
