"""Render real template previews through the actual pipeline renderer.

For each template in assets/templates/, a short synthetic "content" clip is
rendered with execute_render (color grade + overlay + burned karaoke captions
all included) so the preview shows exactly what a real output looks like —
not a 1.3KB gradient placeholder.

Outputs (written to public/template-previews/):
  - <template_id>.jpg     poster frame at t=1s (the static picker thumbnail)
  - <template_id>.loop.mp4 4s 360x640 hover-loop for desktop template cards

Run:  python scripts/generate_template_previews.py
"""

import asyncio
import glob
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.video_editor import TEMPLATES_DIR, execute_render

OUT_DIR = Path("public") / "template-previews"
WORK = Path("tmp") / "preview_src"
SRC = WORK / "source.mp4"
CLIP_START, CLIP_END = 0.0, 4.5

# Synthetic caption track (talking-head style) so karaoke burn renders.
WORDS = [
    ("This", 0.2, 0.6),
    ("is", 0.6, 0.9),
    ("your", 0.9, 1.3),
    ("new", 1.3, 1.6),
    ("short", 1.6, 2.1),
    ("in", 2.1, 2.4),
    ("seconds", 2.4, 2.9),
    ("Flat", 3.2, 3.6),
    ("cuts", 3.6, 4.1),
    ("auto.", 4.1, 4.5),
]

LINE1 = "This is your new short"
LINE2 = "Flat cuts auto."


def build_segments() -> list[dict]:
    segs = []
    line1_words = [w for w in WORDS if w[1] < 3.0]
    line2_words = [w for w in WORDS if w[1] >= 3.0]
    if line1_words:
        segs.append({
            "start": line1_words[0][1],
            "end": line1_words[-1][2],
            "text": LINE1,
            "words": [
                {"word": w, "start": s, "end": e} for w, s, e in line1_words
            ],
        })
    if line2_words:
        segs.append({
            "start": line2_words[0][1],
            "end": line2_words[-1][2],
            "text": LINE2,
            "words": [
                {"word": w, "start": s, "end": e} for w, s, e in line2_words
            ],
        })
    return segs


def make_source() -> None:
    """Synthetic 1080x1920 'content' — moving gradient + centered talking block."""
    WORK.mkdir(parents=True, exist_ok=True)
    if SRC.exists():
        return
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        "color=c=0x1E1E26:s=1080x1920:r=30:d=6",
        "-f", "lavfi", "-i",
        "testsrc2=size=700x1100:rate=30:duration=6",
        "-filter_complex",
        "[1:v]scale=700:1100[bg];"
        "[0:v][bg]overlay=(W-w)/2:(H-h)/2:shortest=1[out]",
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        SRC,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def make_loop(full: str, out: str) -> None:
    """Downscale the rendered 1080x1920 clip to a 360x640 hover-loop MP4."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", full,
            "-vf", "scale=360:640",
            "-t", "4", "-r", "15",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-an", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out,
        ],
        check=True, capture_output=True,
    )


def make_poster(full: str, out: str) -> None:
    """Extract the t=1s poster frame, scaled for card thumbnails."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", full,
            "-ss", "1", "-frames:v", "1",
            "-vf", "scale=540:960",
            "-q:v", "5", out,
        ],
        check=True, capture_output=True,
    )


async def main() -> None:
    make_source()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = build_segments()
    template_ids = sorted(
        Path(p).parent.name
        for p in glob.glob(str(TEMPLATES_DIR / "*/template.json"))
    )
    if not template_ids:
        print("No templates found under", TEMPLATES_DIR)
        return

    for template_id in template_ids:
        print(f"Rendering {template_id} ...", flush=True)
        try:
            outputs = await execute_render(
                video_path=str(SRC),
                clips=[{"start": CLIP_START, "end": CLIP_END}],
                segments=segments,
                template_id=template_id,
                burn_text=True,
                apply_overlay=True,
                trim_silence=False,
            )
        except Exception as e:
            print(f"  FAILED {template_id}: {e}", flush=True)
            continue
        full = outputs[0]
        make_loop(full, str(OUT_DIR / f"{template_id}.loop.mp4"))
        make_poster(full, str(OUT_DIR / f"{template_id}.jpg"))
        print(f"  ok -> {OUT_DIR / template_id}", flush=True)

    print("\nDone. Sizes:")
    for p in sorted(OUT_DIR.glob("*.jpg")) + sorted(OUT_DIR.glob("*.loop.mp4")):
        print(f"  {p.name:32s} {p.stat().st_size/1024:7.1f} KB")


if __name__ == "__main__":
    asyncio.run(main())
