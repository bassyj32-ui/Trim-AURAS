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

    # DeepSeek on a full multi-minute transcript routinely takes 30-90s under
    # Modal load; 60s caused ReadTimeouts that failed jobs at the ANALYZING
    # stage. 300s gives ~5x headroom (tenacity retries add ~70s on top).
    async with AsyncClient(timeout=300) as client:
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

    Returns {"duration": float|None, "scene_times": [...],
    "black_ranges": [...], "loud_windows": [...]}.
    Every probe fails silently, so a missing file or a video without audio
    simply yields empty signals and the pipeline falls back to transcript-only
    selection.
    """
    return {
        "duration": _detect_duration(video_path),
        "scene_times": _detect_scene_times(video_path),
        "black_ranges": _detect_black_ranges(video_path),
        "loud_windows": _detect_loud_windows(video_path),
    }


def _detect_duration(video_path: str) -> float | None:
    """Video duration in seconds via ffprobe; None on any failure."""
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0", video_path,
            ],
            capture_output=True, text=True, timeout=60,
        )
        return float(res.stdout.strip()) if res.returncode == 0 else None
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# --- Content-aware routing (no vision model needed) ---
#
# Different content types want different clip-selection strategies. These two
# helpers classify the video from signals we already compute and, for videos
# with no usable speech, pick clips directly from those signals so the job no
# longer fails with "No speech detected".

def classify_content(
    segments: list[dict[str, Any]],
    video_signals: dict[str, Any] | None,
) -> str:
    """Classify the video's content type from cheap signals.

    - "speech": transcript covers >= 15% of the video (podcast, talking head,
      commentary-heavy gaming) — transcript/DeepSeek selection works best.
    - "action": little speech but frequent scene cuts (gameplay without
      commentary, visual demo) — cut on scene boundaries + loud windows.
    - "music": little speech and few cuts (music video, no-speech content) —
      loudness/energy windows drive selection.
    """
    signals = video_signals or {}
    duration = float(signals.get("duration") or 0)
    if duration <= 0:
        return "speech" if segments else "visual"

    speech_s = sum(
        max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
        for s in segments
    )
    speech_ratio = speech_s / duration
    cuts_per_min = len(signals.get("scene_times") or []) / (duration / 60.0)

    if speech_ratio >= 0.15:
        return "speech"
    if cuts_per_min >= 6:
        return "action"
    return "music"


# --- Auto template recommendation (content → template) ---
#
# Each template.json declares a `genres` keyword list. `recommend_template`
# scores every template against the job's title + transcript (title hits are
# worth 3x) plus a per-content-type affinity, and returns the best fit. With
# no signals it falls back to blurpad_v1 (universal baseline).

TEMPLATES_DIR = Path("assets") / "templates"

# Content type → template boost so speech/action/music videos lean toward the
# styles that research says perform best for them even with zero keyword hits.
_CONTENT_AFFINITY: dict[str, dict[str, int]] = {
    "speech": {"podcast_split_v1": 2, "brand_bold_v1": 1},
    "action": {"gaming_neon_v1": 2, "mrbeast_energy_v1": 1},
    "music": {"mrbeast_energy_v1": 2, "retro_vhs_v1": 1, "gaming_neon_v1": 1},
}


def _template_genres() -> dict[str, list[str]]:
    """Load each template's genre keywords: {template_id: [lowercased kws]}."""
    out: dict[str, list[str]] = {}
    if not TEMPLATES_DIR.exists():
        return out
    for folder in sorted(TEMPLATES_DIR.iterdir()):
        cfg = folder / "template.json"
        if not folder.is_dir() or not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            kws = [str(k).lower() for k in (data.get("genres") or [])]
            out[data.get("id", folder.name)] = kws
        except Exception:
            continue
    return out


def recommend_template(
    content_type: str = "speech",
    title: str = "",
    transcript_text: str = "",
) -> str:
    """Pick the template that best matches the video's genre.

    Scores each template by keyword hits in the title (×3) and transcript
    (×1). The keyword winner wins; ties are broken by the content-type
    affinity. When there's no keyword signal at all, non-speech content
    (action/music) falls back to its affinity pick, and speech falls back to
    ``blurpad_v1`` (the universal talking-head baseline).
    """
    genres = _template_genres()
    if not genres:
        return "blurpad_v1"
    title_l = (title or "").lower()
    transcript_l = (transcript_text or "").lower()
    affinity = _CONTENT_AFFINITY.get(content_type, {})

    scores = {}
    for tid, kws in genres.items():
        score = 0
        for kw in kws:
            if kw in title_l:
                score += 3
            if kw in transcript_l:
                score += 1
        scores[tid] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        # No keyword signal — content-type affinity for speechless genres,
        # otherwise the universal baseline.
        if content_type in ("action", "music") and affinity:
            best = max(affinity, key=affinity.get)
        else:
            best = "blurpad_v1"
    else:
        # Keyword winner(s); break ties with content affinity.
        tied = [t for t, s in scores.items() if s == scores[best]]
        if len(tied) > 1:
            best = max(tied, key=lambda t: (scores[t], affinity.get(t, 0)))
    return best


def select_signal_clips(
    max_clips: int,
    video_signals: dict[str, Any] | None,
    existing_clips: list[dict[str, Any]] | None = None,
    min_clip_s: float = 15.0,
) -> list[dict[str, Any]]:
    """Pick clips for videos with no usable speech (music, action, visual).

    Uses loudness windows first (energy peaks), then the longest uninterrupted
    scene chunks, then evenly spaced windows as a last resort. Returns the same
    shape as DeepSeek's clips so downstream code is unchanged:
    {'start', 'end', 'reason', 'score'}.
    """
    signals = video_signals or {}
    duration = float(signals.get("duration") or 0)
    existing = existing_clips or []

    def overlaps(s: float, e: float) -> bool:
        if any(s < x.get("end", 0) and e > x.get("start", 0) for x in existing):
            return True
        return any(s < c["end"] and e > c["start"] for c in clips)

    def trim(s: float, e: float) -> tuple[float, float]:
        if duration > 0:
            s, e = max(0.0, s), min(duration, e)
        if e - s < min_clip_s:
            e = min(s + min_clip_s, duration) if duration else s + min_clip_s
        return s, e

    clips: list[dict[str, Any]] = []

    # 1) Energy peaks: longest loud windows first (music + action)
    loud = sorted(
        signals.get("loud_windows") or [],
        key=lambda w: w[1] - w[0],
        reverse=True,
    )
    for ws, we in loud:
        if len(clips) >= max_clips:
            break
        s, e = trim(ws, we)
        if e - s < min_clip_s or overlaps(s, e):
            continue
        clips.append(
            {
                "start": round(s, 2),
                "end": round(e, 2),
                "reason": "High-energy moment (no speech detected)",
                "score": 85,
            }
        )

    # 2) Scene pacing: longest uninterrupted shots between cuts (action/visual)
    if len(clips) < max_clips and duration > 0 and signals.get("scene_times"):
        scenes = sorted(signals["scene_times"])
        bounds = [0.0, *scenes, duration]
        chunks = sorted(
            ((a, b) for a, b in zip(bounds, bounds[1:]) if b - a >= min_clip_s),
            key=lambda c: c[1] - c[0],
            reverse=True,
        )
        for s, e in chunks:
            if len(clips) >= max_clips:
                break
            if overlaps(s, e):
                continue
            clips.append(
                {
                    "start": round(s, 2),
                    "end": round(e, 2),
                    "reason": "Long uninterrupted shot (no speech detected)",
                    "score": 75,
                }
            )

    # 3) Last resort: evenly spaced windows across the whole video
    if len(clips) < max_clips and duration > min_clip_s:
        step = duration / max(max_clips, 1)
        for i in range(max_clips):
            if len(clips) >= max_clips:
                break
            s = i * step
            e = min(s + min_clip_s, duration)
            if e - s < min_clip_s or overlaps(s, e):
                continue
            clips.append(
                {
                    "start": round(s, 2),
                    "end": round(e, 2),
                    "reason": "Evenly spaced window (no speech detected)",
                    "score": 70,
                }
            )

    return clips


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
