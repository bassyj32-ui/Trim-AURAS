"""Video rendering pipeline — subtitles, color grading, and Ken Burns zoom."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.config import settings

TEMPLATES_DIR = Path("assets") / "templates"
RENDER_DIR = Path("tmp") / "render"

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

    Template features:
      - Ken Burns subtle zoom on the main video slot
      - Color grading (brightness, contrast, saturation, gamma)
      - PNG overlay image per template (apply_overlay)
      - ASS subtitle overlay with emoji injection (burn_text only)
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
        if burn_text:
            sub_file = _build_subtitle_file(
                segments, trim_start, trim_end, sub_style, f"subs_{i}",
                karaoke=burn_text, cuts=cuts_rel,
            )

        width, height = canvas["width"], canvas["height"]
        sw, sh = slot["width"], slot["height"]
        sx, sy = slot["x_offset"], slot["y_offset"]

        sub_escaped = _ffmpeg_escape_path(sub_file) if sub_file else None

        # --- Build filter complex ---
        fit_mode = slot.get("fit_mode", "cover")

        # 0. Silence trimming: condense the timeline by cutting inter-word
        #    pauses. Builds [condv] via trimmed concat; the main chain then
        #    starts from [condv]. Audio is condensed the same way later.
        chains: list[str] = []
        video_src = f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS"
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

        # 1. Main video chain (with optional Ken Burns zoom)
        if fit_mode == "cover":
            # Full-screen 9:16 reframe: scale the source to COVER the canvas,
            # then center-crop. Works for any source aspect — a 9:16 source
            # fills the screen exactly, a 16:9 source is cropped to fill.
            main_chain = (
                f"{video_src},"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        else:
            # Legacy "contain": centered video on a blurred background
            main_chain = (
                f"{video_src},"
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
                f"{video_src},"
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

        # Assemble full filter complex
        filter_complex = ";".join(chains)

        # --- FFmpeg command ---
        cmd = ["ffmpeg", "-i", video_path]
        next_input = 1
        audio_map = "0:a?"
        has_audio = _has_audio_stream(video_path)
        # Silence trimming: condense audio with the same keep intervals so
        # audio and video stay in sync (no drift).
        if cuts and has_audio:
            a_labels = []
            for j, (ks, ke) in enumerate(keeps):
                a_labels.append(f"ka{j}")
                chains.append(f"[0:a]atrim={ks}:{ke},asetpts=PTS-STARTPTS[ka{j}]")
            chains.append(
                f"[{']['.join(a_labels)}]concat=n={len(a_labels)}:v=0:a=1[conda]"
            )
            audio_map = "[conda]"
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

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )
        if result.returncode != 0:
            error_lines = [
                l for l in result.stderr.split("\n") if "error" in l.lower() or "Error" in l
            ]
            detail = "; ".join(error_lines[-5:]) if error_lines else result.stderr[-1000:]
            raise RuntimeError(
                f"FFmpeg failed (exit {result.returncode}): {detail}"
            )

        if sub_file and os.path.exists(sub_file):
            os.unlink(sub_file)
        output_paths.append(out_path)

    return output_paths
