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

def _build_subtitle_file(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    sub_style: dict[str, Any],
    name: str = "subs",
) -> str:
    """Create an ASS subtitle file in the render workspace."""
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    ass_path = str(RENDER_DIR / f"{name}.ass")

    font_name = sub_style.get("font_name", "Arial")
    font_size = sub_style.get("font_size", 28)
    primary = sub_style.get("primary_color", "&H00FFFFFF")
    outline_color = sub_style.get("outline_color", "&H00000000")
    outline_w = sub_style.get("outline_width", 3)
    alignment = sub_style.get("alignment", 2)
    margin_v = sub_style.get("margin_v", 180)

    style_line = (
        f"Style: Default,{font_name},{font_size},{primary},&H000000FF,"
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

        rel_start = max(seg_start - clip_start, 0)
        rel_end = min(seg_end - clip_start, clip_end - clip_start)

        if rel_end - rel_start < 0.5:
            continue

        # Inject emojis into subtitle text
        text = _enrich_with_emojis(text)

        # Escape ASS special chars: {} are override tags
        safe_text = text.replace("{", "\\{").replace("}", "\\}")
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
) -> list[str]:
    """Render each clip from source video using the template.

    Supports:
      - ASS subtitle overlay with emoji injection
      - Ken Burns subtle zoom on the main video slot
      - Color grading (brightness, contrast, saturation, gamma)
      - Optional PNG overlay image per template
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
        sub_file = _build_subtitle_file(
            segments, clip["start"], clip["end"], sub_style, f"subs_{i}"
        )

        width, height = canvas["width"], canvas["height"]
        sw, sh = slot["width"], slot["height"]
        sx, sy = slot["x_offset"], slot["y_offset"]
        trim_start = clip["start"]
        trim_end = clip["end"]
        duration = trim_end - trim_start

        sub_escaped = _ffmpeg_escape_path(sub_file)

        # --- Build filter complex ---
        fit_mode = slot.get("fit_mode", "cover")

        # 1. Main video chain (with optional Ken Burns zoom)
        if fit_mode == "cover":
            # Full-screen 9:16 reframe: scale the source to COVER the canvas,
            # then center-crop. Works for any source aspect — a 9:16 source
            # fills the screen exactly, a 16:9 source is cropped to fill.
            main_chain = (
                f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        else:
            # Legacy "contain": centered video on a blurred background
            main_chain = (
                f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS,"
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
        chains = [main_chain]
        post_label = "main"
        if fit_mode == "contain":
            bg_chain = (
                f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=2,"
                f"boxblur=5:2,"
                f"crop=trunc(iw/2)*2:trunc(ih/2)*2[bg]"
            )
            chains.append(bg_chain)
            chains.append(f"[bg][main]overlay={sx}:{sy}[withvid]")
            post_label = "withvid"

        # 3. Optional PNG overlay (composited on top)
        if overlay_path:
            ov_escaped = _ffmpeg_escape_path(overlay_path)
            chains.append(
                f"[1:v]format=rgba[overlay];[{post_label}]overlay=0:0[withovl]"
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

        # 5. Subtitles on top
        chains.append(f"[{post_label}]subtitles={sub_escaped}:charenc=utf-8[out]")

        # Assemble full filter complex
        filter_complex = ";".join(chains)

        # --- FFmpeg command ---
        cmd = ["ffmpeg", "-i", video_path]
        next_input = 1
        audio_map = "0:a?"
        if overlay_path:
            cmd += ["-i", overlay_path]
            next_input += 1
        # YouTube rejects files with no audio track — add a silent track if needed
        if not _has_audio_stream(video_path):
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

        os.unlink(sub_file)
        output_paths.append(out_path)

    return output_paths
