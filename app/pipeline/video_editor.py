"""Video rendering pipeline — subtitles, color grading, and Ken Burns zoom."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import settings

TEMPLATES_DIR = Path("assets") / "templates"
RENDER_DIR = Path("tmp") / "render"

# Per-process render counter so every execute_render invocation gets a
# distinct diagnostic stderr log (time_ns disambiguates across processes,
# the counter across sequential renders inside the same process). Without
# this, generate-more / clip-trim re-renders on the same job all write to
# the same clip_0.stderr.log and clobber each other's evidence.
_RENDER_RUN_ID = [0]


def _next_render_run_id() -> str:
    _RENDER_RUN_ID[0] += 1
    return f"{time.time_ns()}_{_RENDER_RUN_ID[0]}"

def _load_template(template_id: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / template_id / "template.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Emoji injection — keyword → emoji mapping for more engaging captions
# ---------------------------------------------------------------------------
_EMOJI_MAP: dict[str, str] = {
    # Positive reactions
    "amazing": "🤯",
    "incredible": "🔥",
    "unbelievable": "🤯",
    "wow": "😮",
    "crazy": "🤯",
    "insane": "🔥",
    "mind blown": "🤯",
    "mindblowing": "🤯",
    "genius": "🧠",
    "brilliant": "💡",
    "perfect": "✨",
    "love": "❤️",
    "beautiful": "✨",
    "gorgeous": "🔥",
    "phenomenal": "🔥",
    "legendary": "🏆",
    "epic": "🔥",
    "huge": "📈",
    "massive": "📈",
    # Money / success
    "money": "💰",
    "billion": "💰",
    "million": "💰",
    "rich": "💸",
    "wealthy": "💸",
    "cash": "💵",
    "profit": "📈",
    "revenue": "📊",
    "growth": "📈",
    "success": "🏆",
    "successful": "🏆",
    "winning": "🏆",
    "deal": "🤝",
    "investment": "📊",
    # Agreement / truth
    "exactly": "💯",
    "truth": "💯",
    "facts": "💯",
    "absolutely": "✅",
    "correct": "✅",
    # Disagreement / controversy
    "wrong": "❌",
    "mistake": "❌",
    "lie": "🤥",
    "controversial": "⚡",
    "hot take": "🌶️",
    # Intelligence
    "smart": "🧠",
    "intelligent": "🧠",
    "wise": "🧠",
    "strategy": "♟️",
    "strategic": "♟️",
    "calculated": "🎯",
    # Emotions
    "scared": "😨",
    "terrified": "😱",
    "afraid": "😨",
    "excited": "🎉",
    "hyped": "🚀",
    "pumped": "🔥",
    "funny": "😂",
    "hilarious": "😂",
    "sad": "😢",
    "depressing": "😢",
    "tragic": "😢",
    "angry": "😡",
    "furious": "😡",
    "surprising": "😲",
    "surprise": "😲",
    "shocked": "😱",
    "shocking": "⚡",
    # Emphasis
    "key": "🔑",
    "secret": "🔑",
    "important": "❗",
    "critical": "❕",
    "essential": "❕",
    "crucial": "❗",
    "dangerous": "☠️",
    "risky": "🎲",
    "bet": "🎲",
    "game changer": "⚡",
    "revolutionary": "🔄",
    "breakthrough": "💥",
    "discovery": "🔬",
    # Business / tech
    "business": "💼",
    "startup": "🚀",
    "company": "🏢",
    "ceo": "👔",
    "founder": "🚀",
    "investor": "💼",
    "ai": "🤖",
    "technology": "💻",
    "data": "📊",
    "code": "💻",
    "app": "📱",
    "internet": "🌐",
    # Social media
    "viral": "📈",
    "trending": "🔥",
    "followers": "👥",
    "audience": "👥",
    "subscribe": "🔔",
    "community": "🌍",
    # Common
    "think about it": "🤔",
    "imagine": "🌌",
    "listen": "👂",
    "look": "👀",
    "watch": "👀",
    "stop": "🛑",
    "win": "🏆",
    "lose": "💀",
    "fail": "💀",
    "goal": "🎯",
    "dream": "💭",
    "focus": "🎯",
    "never": "🚫",
    "always": "♾️",
    "everyone": "👥",
    "nobody": "🙅",
    "people": "👥",
    "best": "🏆",
    "worst": "💀",
    "biggest": "📈",
    "top": "🏆",
    "number": "🔢",
    "percent": "📊",
    "100%": "💯",
}


def _enrich_with_emojis(text: str) -> str:
    """Append relevant emojis after sentences based on keyword matching."""
    # Check multi-word phrases first (longer = more specific)
    text_lower = text.lower()
    matched: set[str] = set()
    for phrase, emoji in sorted(_EMOJI_MAP.items(), key=lambda x: -len(x[0])):
        if phrase in text_lower:
            matched.add(emoji)

    if not matched:
        return text

    # Append up to 2 unique emojis at the end
    suffix = " " + "".join(list(matched)[:2])
    return text.rstrip() + suffix


# ---------------------------------------------------------------------------
# ASS subtitle builder
# ---------------------------------------------------------------------------

def _compute_silence_cuts(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    threshold: float = 0.5,
) -> list[tuple[float, float]]:
    """Find silence ranges (absolute source time) to cut out of a clip.

    Uses Whisper word timestamps: gaps >= ``threshold`` between consecutive
    words are cut, plus leading/trailing dead air beyond the threshold.
    Cuts only ever land BETWEEN words, so burned karaoke captions stay
    frame-accurate once subtitle times are remapped (word ``\\k`` durations
    are unchanged; only the timeline between words is shortened).

    Returns [] when there's no word data or when cutting would leave the
    clip shorter than ~1.2s (safety — don't shred the clip).
    """
    words: list[tuple[float, float]] = []
    for seg in segments:
        for w in seg.get("words") or []:
            ws = float(w.get("start", 0) or 0)
            we = float(w.get("end", 0) or ws)
            if we > clip_start and ws < clip_end:
                words.append((ws, we))
    words.sort()
    if len(words) < 2:
        return []

    cuts: list[tuple[float, float]] = []
    first_s, first_e = words[0]
    last_s, last_e = words[-1]

    if first_s - clip_start >= threshold:
        cuts.append((clip_start, first_s))
    prev_e = first_e
    for ws, we in words[1:]:
        if ws - prev_e >= threshold:
            cuts.append((prev_e, ws))
        prev_e = we
    if clip_end - last_e >= threshold:
        cuts.append((last_e, clip_end))

    keep = (clip_end - clip_start) - sum(ce - cs for cs, ce in cuts)
    if keep < 1.2:
        return []
    return cuts


def _keep_intervals(
    clip_start: float, clip_end: float, cuts: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Invert the cut ranges into the keep intervals (absolute source time)."""
    intervals: list[tuple[float, float]] = []
    cursor = clip_start
    for cs, ce in cuts:
        if cs > cursor:
            intervals.append((cursor, cs))
        cursor = ce
    if cursor < clip_end:
        intervals.append((cursor, clip_end))
    return intervals


def _shift_time(t: float, cuts: list[tuple[float, float]]) -> float:
    """Map a clip-relative time into the silence-condensed timeline."""
    out = t
    for cs, ce in cuts:
        if t >= ce:
            out -= ce - cs
        elif t > cs + 1e-9:
            out = cs
    return out


def _build_karaoke_line(
    seg: dict[str, Any], clip_start: float, clip_end: float
) -> tuple[str | None, float, float]:
    """Build one ASS karaoke dialogue line from a segment's word timestamps.

    Each word becomes a ``\\k`` syllable (duration in centiseconds) so the
    template's highlight colour fills in word-by-word as it is spoken — the
    classic Opus-style animated caption. Times are relative to ``clip_start``.
    Returns ``(text, rel_start, rel_end)`` or ``(None, 0, 0)`` when the
    segment has no usable words inside the clip window.
    """
    words = seg.get("words") or []
    parts: list[str] = []
    rel_start: float | None = None
    rel_end = 0.0

    for w in words:
        ws = float(w.get("start", 0) or 0)
        we = float(w.get("end", 0) or ws)
        if we <= clip_start or ws >= clip_end:
            continue
        word = str(w.get("word", "")).strip()
        if not word:
            continue
        r_s = max(ws - clip_start, 0.0)
        r_e = min(we - clip_start, clip_end - clip_start)
        if r_e - r_s < 0.05:
            continue
        if rel_start is None:
            rel_start = r_s
        rel_end = max(rel_end, r_e)
        dur_cs = max(int(round((r_e - r_s) * 100)), 1)
        # Escape ASS special chars per-word; the \k tags themselves must stay
        # raw (the caller does NOT run the whole-line escape in karaoke mode).
        safe = word.replace("{", "\\{").replace("}", "\\}")
        parts.append(f"{{\\k{dur_cs}}}{safe}")

    if not parts or rel_start is None:
        return None, 0.0, 0.0
    return " ".join(parts), rel_start, rel_end


def _build_subtitle_file(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    sub_style: dict[str, Any],
    name: str = "subs",
    karaoke: bool = False,
    cuts: list[tuple[float, float]] | None = None,
    canvas_w: int = 0,
    canvas_h: int = 0,
) -> str:
    """Create an ASS subtitle file in the render workspace.

    When ``karaoke=True`` each word is emitted with a ``\\k`` timing tag so
    words highlight in the template's ``highlight_color`` as they're spoken
    (Opus-style). Words come from each segment's ``words`` list (populated by
    the transcriber when Whisper returns word timestamps); segments without
    words fall back to plain text.

    ``cuts`` is a list of clip-relative silence ranges that were removed from
    the timeline (silence trimming); Dialogue times are remapped so captions
    stay synced to the condensed clip. Karaoke ``\\k`` durations are left
    untouched — cuts only land between words.

    ``canvas_w``/``canvas_h`` are the final video dimensions. They are written
    as PlayResX/PlayResY — REQUIRED: when the header lacks them, ffmpeg's
    libass falls back to a tiny default canvas (384x288) and burns the text
    into the video frame without scaling, so captions render ~4x oversized at
    the top of the frame instead of at margin_v from the bottom.
    """
    cuts = cuts or []
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    ass_path = str(RENDER_DIR / f"{name}.ass")

    font_name = sub_style.get("font_name", "Arial")
    font_size = sub_style.get("font_size", 28)
    # Karaoke: upcoming words render white and flip to the template's accent
    # colour as they're spoken (secondary = already-spoken colour).
    primary = "&H00FFFFFF" if karaoke else sub_style.get("primary_color", "&H00FFFFFF")
    secondary = (
        sub_style.get("highlight_color", "&H0000FFFF") if karaoke else "&H000000FF"
    )
    outline_color = sub_style.get("outline_color", "&H00000000")
    outline_w = sub_style.get("outline_width", 3)
    alignment = sub_style.get("alignment", 2)
    margin_v = sub_style.get("margin_v", 180)

    style_line = (
        f"Style: Default,{font_name},{font_size},{primary},{secondary},"
        f"{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline_w},0,"
        f"{alignment},20,20,{margin_v},1"
    )

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if canvas_w > 0 and canvas_h > 0:
        # PlayRes is mandatory (see docstring): without it libass uses a tiny
        # default canvas and the burned text lands oversized at the top.
        lines[1:1] = [f"PlayResX: {canvas_w}", f"PlayResY: {canvas_h}"]

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        text = seg.get("text", "")

        if seg_end <= clip_start or seg_start >= clip_end:
            continue

        if karaoke:
            kara_text, k_start, k_end = _build_karaoke_line(seg, clip_start, clip_end)
            if kara_text is not None:
                rel_start = k_start
                rel_end = k_end
                safe_text = _enrich_with_emojis(kara_text)
            else:
                # No word timestamps for this segment — fall back to plain text
                rel_start = max(seg_start - clip_start, 0)
                rel_end = min(seg_end - clip_start, clip_end - clip_start)
                safe_text = _enrich_with_emojis(text).replace("{", "\\{").replace("}", "\\}")
        else:
            rel_start = max(seg_start - clip_start, 0)
            rel_end = min(seg_end - clip_start, clip_end - clip_start)
            if rel_end - rel_start < 0.5:
                continue
            # Inject emojis into subtitle text
            safe_text = _enrich_with_emojis(text).replace("{", "\\{").replace("}", "\\}")

        # Remap into the silence-condensed timeline (cuts only land between
        # words, so karaoke \k durations stay intact).
        rel_start = _shift_time(rel_start, cuts)
        rel_end = _shift_time(rel_end, cuts)

        if rel_end - rel_start < 0.05:
            continue

        lines.append(
            f"Dialogue: 0,{_fmt_ass_time(rel_start)},{_fmt_ass_time(rel_end)},Default,,0,0,0,,{safe_text}"
        )

    Path(ass_path).write_text("\n".join(lines), encoding="utf-8")
    return ass_path


def _fmt_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ffmpeg_escape_path(p: str) -> str:
    """Convert a Windows path to FFmpeg filter-safe format."""
    return p.replace("\\", "/").replace(":", "\\:")


def _has_audio_stream(video_path: str) -> bool:
    """Return True if the source video has at least one audio stream.

    Used to add a silent audio track when absent — YouTube rejects files
    that have no audio stream at all.
    """
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    return bool(probe.stdout.strip())


def _probe_dimensions(video_path: str) -> tuple[int, int] | None:
    """Return (width, height) of the source video's first video stream."""
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    line = probe.stdout.strip()
    if "x" in line:
        w, h = line.split("x", 1)
        try:
            return int(w), int(h)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Face-aware crop — animated cover crop that follows the speaker
# ---------------------------------------------------------------------------

_MAX_CROP_SAMPLES = 180  # keeps each axis expression < ~15KB (Windows cmd limit)


def _lerp_expr(pts: list[tuple[float, float, float]], axis: int) -> str:
    """Piecewise-linear FFmpeg expression from (t, x, y) samples.

    ``axis`` selects x (1) or y (2). The timeline is partitioned half-open
    (``[t_i, t_{i+1})``) so each sample point is counted exactly once —
    ``between()`` alone is inclusive on BOTH ends and would double-count the
    value at shared sample instants. For ``t`` before the first sample the
    value is held at the first point; after the last it is held at the last
    point. A pure, testable function.
    """
    if len(pts) == 1:
        return f"{pts[0][axis]:.3f}"
    terms: list[str] = []
    t0, v0 = pts[0][0], pts[0][axis]
    terms.append(f"lt(t,{t0:.3f})*{v0:.3f}")
    for i in range(len(pts) - 1):
        t1, v1 = pts[i][0], pts[i][axis]
        t2, v2 = pts[i + 1][0], pts[i + 1][axis]
        dt = t2 - t1
        if dt <= 0:
            continue
        slope = (v2 - v1) / dt
        terms.append(
            f"gte(t,{t1:.3f})*lt(t,{t2:.3f})*({v1:.3f}+{slope:.4f}*(t-{t1:.3f}))"
        )
    tn, vn = pts[-1][0], pts[-1][axis]
    terms.append(f"gte(t,{tn:.3f})*{vn:.3f}")
    return "+".join(terms)


def _build_animated_crop(
    face_track: list[dict],
    trim_start: float,
    trim_end: float,
    cuts_rel: list[tuple[float, float]],
    src_w: int,
    src_h: int,
    canvas_w: int,
    canvas_h: int,
    slack: float = 1.15,
) -> tuple[int, int, str, str] | None:
    """Plan a face-following cover crop for one clip.

    Returns ``(scale_w, scale_h, x_expr, y_expr)`` or ``None`` when the
    track has fewer than 2 usable samples inside the clip window (the caller
    then falls back to the static center crop).

    The source is scaled to cover the canvas with ``slack`` extra on each
    side (15% by default) so the crop has room to pan; the crop window is
    then centered on the smoothed face path. Face sample times are remapped
    through the silence-condensed timeline (``cuts_rel``) so panning stays in
    sync with the speech.
    """
    samples: list[tuple[float, float, float]] = []
    for s in face_track:
        t = s.get("t", 0.0)
        if trim_start - 0.5 <= t <= trim_end + 0.5:
            rel = _shift_time(t - trim_start, cuts_rel)
            if rel < 0.0:
                rel = 0.0
            samples.append((rel, float(s.get("cx", 0.5)), float(s.get("cy", 0.5))))
    if len(samples) < 2:
        return None
    samples.sort(key=lambda p: p[0])

    # Cap sample count to keep the filter expression a manageable size.
    if len(samples) > _MAX_CROP_SAMPLES:
        stride = len(samples) / _MAX_CROP_SAMPLES
        picked = [
            samples[min(int(i * stride), len(samples) - 1)] for i in range(_MAX_CROP_SAMPLES)
        ]
        if picked[-1][0] < samples[-1][0]:
            picked.append(samples[-1])
        samples = picked

    # Scale the source to cover the canvas plus slack; round to even dims.
    f = max((canvas_w * slack) / src_w, (canvas_h * slack) / src_h)
    scale_w = int(src_w * f / 2) * 2
    scale_h = int(src_h * f / 2) * 2
    max_x = max(scale_w - canvas_w, 0)
    max_y = max(scale_h - canvas_h, 0)

    # Crop position = face center in the scaled frame, clamped to the window.
    pts: list[tuple[float, float, float]] = []
    for rel, cx, cy in samples:
        x = max(0.0, min(float(max_x), cx * scale_w - canvas_w / 2.0))
        y = max(0.0, min(float(max_y), cy * scale_h - canvas_h / 2.0))
        pts.append((rel, x, y))

    return scale_w, scale_h, _lerp_expr(pts, 1), _lerp_expr(pts, 2)


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

async def execute_render(
    video_path: str,
    clips: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    template_id: str,
    burn_text: bool = False,
    apply_overlay: bool = True,
    trim_silence: bool = False,
    face_track: list[dict] | None = None,
) -> list[str]:
    """Render each clip from source video using the template.

    The template's PNG overlay frame (corner glow, scanlines, corner blocks,
    bottom bar, etc.) is composited by default (apply_overlay=True) so every
    template renders with a distinct look — this is what makes "Auto"
    template picks visually different from each other. burn_text only
    controls whether ASS subtitles are burned on; when False (the default)
    the clip stays text-free so any on-screen captions can be added by the
    user afterwards. When burn_text=True the template's ASS subtitles are
    applied on top of the overlay.

    When trim_silence=True, inter-word pauses >= 0.5s (and leading/trailing
    dead air) are cut out of each clip using Whisper word timestamps. Cuts
    only ever land BETWEEN words, so burned karaoke captions stay
    frame-accurate after the subtitle times are remapped.

    When face_track is a non-empty normalized face track (list of
    {"t", "cx", "cy"}, see face_track.detect_face_track), cover-mode clips
    get an ANIMATED crop that pans to keep the speaker centered (Opus-style
    auto face tracking); the crop falls back to the static center crop when
    there's no track or no faces inside a clip's window.

    Template features:
      - Ken Burns subtle zoom on the main video slot
      - Color grading (brightness, contrast, saturation, gamma)
      - PNG overlay image per template (apply_overlay)
      - ASS subtitle overlay with emoji injection (burn_text only)
      - Face-aware animated cover crop (cover-mode templates, face_track set)
    """
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    template = _load_template(template_id)
    canvas = template["canvas"]
    slot = template["video_slot"]
    sub_style = template.get("subtitles", {})
    overlay_rel = template.get("overlay_image")
    color_grade = template.get("color_grade", {})
    ken_burns = template.get("ken_burns", {})

    fps = canvas.get("fps", 30)

    # Resolve overlay path relative to template directory
    overlay_path = None
    if overlay_rel:
        candidate = TEMPLATES_DIR / template_id / overlay_rel
        if candidate.exists():
            overlay_path = str(candidate.resolve())

    output_paths = []

    for i, clip in enumerate(clips):
        out_path = str(RENDER_DIR / f"clip_{i}.mp4")
        sub_file = None
        trim_start = clip["start"]
        trim_end = clip["end"]
        cuts = _compute_silence_cuts(segments, trim_start, trim_end) if trim_silence else []
        cuts_rel = [(cs - trim_start, ce - trim_start) for cs, ce in cuts]
        duration = (trim_end - trim_start) - sum(ce - cs for cs, ce in cuts)
        width, height = canvas["width"], canvas["height"]
        if burn_text:
            sub_file = _build_subtitle_file(
                segments, trim_start, trim_end, sub_style, f"subs_{i}",
                karaoke=burn_text, cuts=cuts_rel,
                canvas_w=width, canvas_h=height,
            )

        sw, sh = slot["width"], slot["height"]
        sx, sy = slot["x_offset"], slot["y_offset"]

        sub_escaped = _ffmpeg_escape_path(sub_file) if sub_file else None

        # --- Build filter complex ---
        fit_mode = slot.get("fit_mode", "cover")

        # Face-aware cover crop: animate x/y so the speaker stays centered.
        # Falls back to None (static center crop) when there's no track or no
        # faces inside this clip's window.
        crop_plan = None
        if fit_mode == "cover" and face_track:
            src_dims = _probe_dimensions(video_path)
            if src_dims:
                crop_plan = _build_animated_crop(
                    face_track, trim_start, trim_end, cuts_rel,
                    src_dims[0], src_dims[1], width, height,
                )

        # 0. Silence trimming: condense the timeline by cutting inter-word
        #    pauses. Builds [condv] via trimmed concat; the main chain then
        #    starts from [condv]. Audio is condensed the same way later.
        #    NOTE: when video_src is a bare label ("[condv]") the next filter
        #    must GLUE to it ("[condv]scale=...") — a comma after a label is
        #    parsed as an empty filter ("No such filter: ''").
        chains: list[str] = []
        video_src = f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS"
        vs_sep = ","
        keeps: list[tuple[float, float]] = []
        if cuts:
            keeps = _keep_intervals(trim_start, trim_end, cuts)
            v_labels = []
            for j, (ks, ke) in enumerate(keeps):
                v_labels.append(f"kv{j}")
                chains.append(f"[0:v]trim={ks}:{ke},setpts=PTS-STARTPTS[kv{j}]")
            chains.append(
                f"[{']['.join(v_labels)}]concat=n={len(v_labels)}:v=1:a=0[condv]"
            )
            video_src = "[condv]"
            vs_sep = ""

        # 1. Main video chain (with optional Ken Burns zoom)
        if fit_mode == "cover":
            if crop_plan:
                # Face-aware: scale with slack, then pan a WxH window so the
                # speaker stays centered. x/y are piecewise-linear expressions
                # in clip time, single-quoted so the commas are literal.
                scale_w, scale_h, x_expr, y_expr = crop_plan
                main_chain = (
                    f"{video_src}{vs_sep}"
                    f"scale={scale_w}:{scale_h},"
                    f"crop={width}:{height}:x='{x_expr}':y='{y_expr}'"
                )
            else:
                # Full-screen 9:16 reframe: scale the source to COVER the
                # canvas, then center-crop. Works for any source aspect — a
                # 9:16 source fills the screen exactly, a 16:9 source is
                # cropped to fill.
                main_chain = (
                    f"{video_src}{vs_sep}"
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height}"
                )
        else:
            # Legacy "contain": centered video on a blurred background
            main_chain = (
                f"{video_src}{vs_sep}"
                f"scale={sw}:{sh}:force_original_aspect_ratio=1,"
                f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2"
            )

        kb_enabled = ken_burns.get("enabled", False)
        if kb_enabled:
            zs = ken_burns.get("zoom_start", 1.0)
            ze = ken_burns.get("zoom_end", 1.05)
            # Per-frame increment so it reaches ze by the last frame
            frame_count = max(int(duration * fps), 1)
            inc = (ze - zs) / frame_count
            main_chain += (
                f",zoompan=z='if(eq(on,1),{zs},min(zoom+{inc},{ze}))'"
                f":d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={sw}x{sh}"
                f",fps={fps},setpts=PTS-STARTPTS"
            )
        else:
            # Force a constant frame rate so YouTube always accepts the file
            main_chain += f",fps={fps}"

        main_chain += "[main]"

        # 2. Background blur chain (contain mode only)
        chains.append(main_chain)
        post_label = "main"
        if fit_mode == "contain":
            bg_chain = (
                f"{video_src}{vs_sep}"
                f"scale={width}:{height}:force_original_aspect_ratio=2,"
                f"boxblur=5:2,"
                f"crop=trunc(iw/2)*2:trunc(ih/2)*2[bg]"
            )
            chains.append(bg_chain)
            chains.append(f"[bg][main]overlay={sx}:{sy}[withvid]")
            post_label = "withvid"

        # 3. Optional PNG overlay (composited on top) — template frame/branding
        if apply_overlay and overlay_path:
            ov_escaped = _ffmpeg_escape_path(overlay_path)
            chains.append(
                f"[1:v]format=rgba[overlay];[{post_label}][overlay]overlay=0:0[withovl]"
            )
            post_label = "withovl"

        # 4. Color grading (eq filter)
        has_cg = bool(color_grade)
        if has_cg:
            b = color_grade.get("brightness", 0.0)
            c_val = color_grade.get("contrast", 1.0)
            s_val = color_grade.get("saturation", 1.0)
            g = color_grade.get("gamma", 1.0)
            chains.append(
                f"[{post_label}]eq="
                f"brightness={b}:contrast={c_val}:saturation={s_val}:gamma={g}[graded]"
            )
            post_label = "graded"

        # 5. Subtitles on top — or plain passthrough when text is not burned
        if burn_text and sub_file:
            chains.append(f"[{post_label}]subtitles={sub_escaped}:charenc=utf-8[out]")
        else:
            chains.append(f"[{post_label}]null[out]")

        # Audio condense chains MUST be appended before the join below —
        # `-map [conda]` references a label, so it has to exist in the graph
        # that `filter_complex` is built from (previously appended after the
        # join, so trim_silence renders failed with "Error opening output
        # file: Invalid argument" — [conda] matched no stream).
        has_audio = _has_audio_stream(video_path)
        if cuts and has_audio:
            a_labels = []
            for j, (ks, ke) in enumerate(keeps):
                a_labels.append(f"ka{j}")
                chains.append(f"[0:a]atrim={ks}:{ke},asetpts=PTS-STARTPTS[ka{j}]")
            chains.append(
                f"[{']['.join(a_labels)}]concat=n={len(a_labels)}:v=0:a=1[conda]"
            )

        # Assemble full filter complex
        filter_complex = ";".join(chains)

        # --- FFmpeg command ---
        cmd = ["ffmpeg", "-i", video_path]
        next_input = 1
        audio_map = "[conda]" if (cuts and has_audio) else "0:a?"
        if apply_overlay and overlay_path:
            cmd += ["-i", overlay_path]
            next_input += 1
        # YouTube rejects files with no audio track — add a silent track if needed
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            audio_map = f"{next_input}:a"
        cmd += [
            "-filter_complex",
            filter_complex,
            "-map", "[out]",
            "-map", audio_map,
            "-t", str(duration),
            "-r", str(fps),
            "-c:v", "libx264",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-y",
            out_path,
        ]

        import asyncio

        # --- Diag instrumentation (evidence only — no behavior change) ---
        # Log the exact ffmpeg version + full filter string so Modal (5.1)
        # can be diffed against local (8.x) directly.
        try:
            ver = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
            ).stdout.splitlines()[0]
        except Exception:
            ver = "ffmpeg version: unknown"
        print(f"[render] ffmpeg: {ver}", flush=True)
        print(f"[render] filter_complex[{len(filter_complex)} chars]: {filter_complex}", flush=True)
        print(f"[render] cmd: {' '.join(cmd)}", flush=True)

        # Stream ffmpeg stderr live to a persisted log file (survives on the
        # /mnt/data Volume on Modal) + console, so a stalled render shows
        # partial output instead of nothing until it finishes or times out.
        diag_dir = (
            Path("/mnt/data/diag")
            if (os.name == "posix" and os.path.isdir("/mnt/data"))
            else RENDER_DIR
        )
        diag_dir.mkdir(parents=True, exist_ok=True)
        # Unique per render invocation (run-id suffix) — sequential/concurrent
        # renders of the same job no longer overwrite each other's log.
        stderr_log = diag_dir / f"{Path(out_path).stem}_{_next_render_run_id()}.stderr.log"

        def _run_streamed() -> tuple[int, list[str]]:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
            seen: list[str] = []
            with stderr_log.open("w", encoding="utf-8") as lf:
                lf.write(f"# {ver}\n# {filter_complex}\n")
                lf.flush()
                assert proc.stderr is not None
                for line in proc.stderr:
                    line = line.rstrip()
                    if not line:
                        continue
                    lf.write(line + "\n")
                    lf.flush()
                    seen.append(line)
                    print(f"[render-stderr] {line}", flush=True)
            proc.wait()
            return proc.returncode, seen

        returncode, stderr_lines = await asyncio.to_thread(_run_streamed)
        if returncode != 0:
            error_lines = [
                l for l in stderr_lines if "error" in l.lower() or "Error" in l
            ]
            detail = "; ".join(error_lines[-5:]) if error_lines else "".join(stderr_lines)[-1000:]
            raise RuntimeError(
                f"FFmpeg failed (exit {returncode}): {detail}"
            )

        if sub_file and os.path.exists(sub_file):
            os.unlink(sub_file)
        output_paths.append(out_path)

    return output_paths
