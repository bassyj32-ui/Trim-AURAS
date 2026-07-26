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
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 0", "ScaledBorderAndShadow: yes",
        "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
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

        # Escape ASS special chars: {} are override tags, escape them
        safe_text = text.replace("{", "\\{").replace("}", "\\}")
        lines.append(f"Dialogue: 0,{_fmt_ass_time(rel_start)},{_fmt_ass_time(rel_end)},Default,,0,0,0,,{safe_text}")

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


def execute_render(
    video_path: str,
    clips: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    template_id: str,
) -> list[str]:
    """Render each clip from source video using the template.

    Returns a list of rendered file paths.
    """
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    template = _load_template(template_id)
    canvas = template["canvas"]
    slot = template["video_slot"]
    sub_style = template.get("subtitles", {})
    overlay_rel = template.get("overlay_image")

    # Resolve overlay path relative to template directory
    overlay_path = None
    if overlay_rel:
        candidate = TEMPLATES_DIR / template_id / overlay_rel
        if candidate.exists():
            overlay_path = str(candidate.resolve())

    output_paths = []

    for i, clip in enumerate(clips):
        out_path = str(RENDER_DIR / f"clip_{i}.mp4")
        sub_file = _build_subtitle_file(segments, clip["start"], clip["end"], sub_style, f"subs_{i}")

        width, height = canvas["width"], canvas["height"]
        sw, sh = slot["width"], slot["height"]
        sx, sy = slot["x_offset"], slot["y_offset"]
        trim_start = clip["start"]
        trim_end = clip["end"]
        duration = trim_end - trim_start

        sub_escaped = _ffmpeg_escape_path(sub_file)

        filter_complex = (
            f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS,"
            f"scale={sw}:{sh}:force_original_aspect_ratio=1,"
            f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2[main];"
            f"[0:v]trim={trim_start}:{trim_end},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=2,"
            f"boxblur=20:5,"
            f"crop=trunc(iw/2)*2:trunc(ih/2)*2[bg];"
            f"[bg][main]overlay={sx}:{sy}[withvid];"
        )

        # Append overlay PNG if available
        if overlay_path:
            ov_escaped = _ffmpeg_escape_path(overlay_path)
            filter_complex += (
                f"[1:v]format=rgba[overlay];"
                f"[withvid][overlay]overlay=0:0[withovl];"
                f"[withovl]subtitles={sub_escaped}:charenc=utf-8[out]"
            )
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-i", overlay_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-y",
                out_path,
            ]
        else:
            filter_complex += f"[withvid]subtitles={sub_escaped}:charenc=utf-8[out]"
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-y",
                out_path,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            error_lines = [l for l in result.stderr.split("\n") if "error" in l.lower() or "Error" in l]
            detail = "; ".join(error_lines[-5:]) if error_lines else result.stderr[-1000:]
            raise RuntimeError(
                f"FFmpeg failed (exit {result.returncode}): {detail}"
            )

        os.unlink(sub_file)
        output_paths.append(out_path)

    return output_paths
