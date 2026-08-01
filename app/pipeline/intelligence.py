import json
import math
import re
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

PROMPT_PATH = Path("prompts") / "clip_analysis.txt"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_analyze(
    segments: list[dict[str, Any]],
    max_clips: int = 5,
    existing_clips: list[dict[str, Any]] | None = None,
    campaign_rules: str = "",
    video_signals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Use DeepSeek to pick viral clip timestamps from transcript segments.

    Args:
        segments: Full transcript segments.
        max_clips: Maximum number of clips to suggest.
        existing_clips: Previously selected clips so DeepSeek avoids repeats.
        campaign_rules: Optional campaign/SEO rules that should guide clip
            selection (topics to include or avoid, hook style, tone, etc.).
        video_signals: Optional cheap audio/video signals (scene boundaries,
            loud windows, black ranges) to guide where clips start/end.

    Returns a list of {'start': float, 'end': float, 'reason': str}.
    """
    transcript_text = _segments_to_text(segments)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = system_prompt.replace("{max_clips}", str(max_clips))

    user_msg = f"TRANSCRIPT:\n{transcript_text}\n\n"
    if campaign_rules:
        user_msg += (
            f"CAMPAIGN RULES (follow these when choosing segments):\n"
            f"{campaign_rules}\n\n"
        )
    if video_signals:
        user_msg += _signals_text(video_signals)
    if existing_clips:
        existing_desc = "\n".join(
            f"  - Already used: [{c['start']}-{c['end']}] ({c.get('reason', '')})"
            for c in existing_clips
        )
        user_msg += f"Previously selected clips (DO NOT repeat these):\n{existing_desc}\n\n"
    user_msg += "Return JSON array of clips."

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.4,
    }

    async with AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    clips = json.loads(raw)

    # Normalize "score" (0-100) so downstream code always sees a clean int or
    # None, then rank best-first so the frontend can trust clip order.
    for c in clips:
        score = c.get("score")
        if score is None:
            c["score"] = None
        else:
            try:
                score = int(round(float(score)))
            except (TypeError, ValueError):
                c["score"] = None
            else:
                c["score"] = max(0, min(100, score))
    clips.sort(
        key=lambda c: c["score"] if c["score"] is not None else -1,
        reverse=True,
    )

    return clips


def _signals_text(video_signals: dict[str, Any]) -> str:
    """Format the extracted video signals into instructions for DeepSeek."""
    parts = []
    loud = video_signals.get("loud_windows") or []
    if loud:
        parts.append(
            "HIGH-ENERGY WINDOWS (loud/excited speech — PREFER these): "
            + ", ".join(f"{a:.1f}-{b:.1f}" for a, b in loud)
        )
    scenes = video_signals.get("scene_times") or []
    if scenes:
        parts.append(
            "SCENE BOUNDARIES (visual cuts — start/end clips here): "
            + ", ".join(f"{t:.1f}" for t in scenes[:200])
        )
    blacks = video_signals.get("black_ranges") or []
    if blacks:
        parts.append(
            "BLACK/DEAD-AIR RANGES (NEVER include these): "
            + ", ".join(f"{a:.1f}-{b:.1f}" for a, b in blacks)
        )
    if not parts:
        return ""
    return (
        "VIDEO SIGNALS:\n" + "\n".join(parts) + "\n\n"
        "RULES: Prefer clips that overlap HIGH-ENERGY WINDOWS. "
        "Start and end clips at SCENE BOUNDARIES whenever possible. "
        "Never start a clip inside or include a BLACK range.\n\n"
    )


# --- Cheap audio/video signal extraction (no vision model needed) ---
#
# These three FFmpeg passes are cheap "sight" proxies that let DeepSeek cut
# smarter without an expensive vision API:
#   1. Scene changes  -> natural cut points (no awkward mid-scene jumps)
#   2. Loudness       -> high-energy speech moments (the viral parts)
#   3. Black frames   -> dead air to keep clips away from

def _run_ffmpeg_probe(cmd: list[str], timeout: int = 600) -> str:
    """Run a non-destructive ffmpeg pass; return stderr ("" on any failure)."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stderr if res.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _detect_scene_times(video_path: str) -> list[float]:
    """Visual cuts via FFmpeg's scene filter, on a downscaled decode pass."""
    stderr = _run_ffmpeg_probe(
        [
            "ffmpeg", "-hide_banner", "-i", video_path,
            "-vf", "scale=-1:360,select=gt(scene\\,0.3),showinfo",
            "-an", "-f", "null", "-",
        ]
    )
    return [float(t) for t in re.findall(r"pts_time:([0-9.]+)", stderr)]


def _detect_black_ranges(video_path: str) -> list[tuple[float, float]]:
    """Dead-air intervals (black frames >= 0.5s), on a downscaled decode pass."""
    stderr = _run_ffmpeg_probe(
        [
            "ffmpeg", "-hide_banner", "-i", video_path,
            "-vf", "scale=-1:360,blackdetect=d=0.5:pix_th=0.1",
            "-an", "-f", "null", "-",
        ]
    )
    return [
        (float(s), float(e))
        for s, e in re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", stderr)
    ]


def _detect_loud_windows(
    video_path: str,
    window_s: float = 0.5,
    percentile: float = 85.0,
) -> list[tuple[float, float]]:
    """Find high-energy speech windows.

    Decodes audio to 8kHz mono PCM (fast, audio-only) and computes RMS per
    0.5s window, then groups windows above the 85th percentile of loudness.
    """
    win = int(8000 * window_s)
    try:
        proc = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-i", video_path,
                "-ac", "1", "-ar", "8000", "-f", "f32le", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return []

    rms_vals: list[float] = []
    times: list[float] = []
    buf = bytearray()
    n_win = 0
    deadline = time.monotonic() + 600
    try:
        while time.monotonic() < deadline:
            raw = proc.stdout.read(65536)
            if not raw:
                break
            buf.extend(raw)
            while len(buf) >= win * 4:
                chunk = bytes(buf[: win * 4])
                del buf[: win * 4]
                samples = struct.unpack(f"{win}f", chunk)
                rms = math.sqrt(sum(x * x for x in samples) / win)
                rms_vals.append(rms)
                times.append(n_win * window_s)
                n_win += 1
    finally:
        proc.kill()

    if len(rms_vals) < 5:
        return []

    threshold = sorted(rms_vals)[int(len(rms_vals) * percentile / 100.0)]
    if threshold <= 1e-6:
        return []

    windows: list[tuple[float, float]] = []
    w_start: float | None = None
    for t, r in zip(times, rms_vals):
        if r >= threshold:
            if w_start is None:
                w_start = t
        elif w_start is not None:
            if t - w_start >= window_s:
                windows.append((w_start, t))
            w_start = None
    if w_start is not None and times[-1] + window_s - w_start >= window_s:
        windows.append((w_start, times[-1] + window_s))
    return windows


def extract_video_signals(video_path: str) -> dict[str, Any]:
    """Extract cheap audio/video signals to guide smarter clip cutting.

    Returns {"scene_times": [...], "black_ranges": [...], "loud_windows": [...]}.
    Every probe fails silently, so a missing file or a video without audio
    simply yields empty signals and the pipeline falls back to transcript-only
    selection.
    """
    return {
        "scene_times": _detect_scene_times(video_path),
        "black_ranges": _detect_black_ranges(video_path),
        "loud_windows": _detect_loud_windows(video_path),
    }


def snap_clips_to_signals(
    clips: list[dict[str, Any]],
    video_signals: dict[str, Any] | None,
    tolerance: float = 2.0,
    min_clip_s: float = 15.0,
) -> list[dict[str, Any]]:
    """Force clip boundaries onto scene cuts and away from black ranges.

    A hard post-pass so the rules hold even if DeepSeek ignores them:
    - Snaps each clip start/end to the nearest scene boundary (within 2s).
    - Pushes starts out of black ranges and pulls ends back before them.
    - Drops clips that sit entirely inside dead air; never returns empty.
    """
    if not video_signals:
        return clips
    scene_times = sorted(video_signals.get("scene_times") or [])
    black_ranges = video_signals.get("black_ranges") or []
    if not scene_times and not black_ranges:
        return clips

    def nearest_scene(t: float) -> float | None:
        if not scene_times:
            return None
        best = min(scene_times, key=lambda s: abs(s - t))
        return best if abs(best - t) <= tolerance else None

    out: list[dict[str, Any]] = []
    for c in clips:
        start = float(c.get("start", 0.0))
        end = float(c.get("end", 0.0))
        s = nearest_scene(start)
        if s is not None:
            start = max(0.0, s)
        e = nearest_scene(end)
        if e is not None and e > start:
            end = e
        dropped = False
        for bs, be in black_ranges:
            if start >= bs and end <= be:
                dropped = True  # clip sits entirely inside dead air
                break
            if bs < start < be:
                start = be      # clip starts inside black -> push past it
            if bs < end < be:
                end = bs        # clip ends inside black -> pull back
        if dropped or end - start < min_clip_s:
            continue
        c["start"], c["end"] = round(start, 2), round(end, 2)
        out.append(c)
    return out or clips


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "")
        lines.append(f"[{start:.1f}-{end:.1f}] {text}")
    return "\n".join(lines)
