"""Where does the karaoke caption actually render?

Regenerates the exact ASS file the burn render used (same segments/clip/
template) and burns it onto a solid black 1080x1920 canvas at t=2.0, then
reports the bounding box of non-black pixels — proving the on-screen
position of the caption (expected: bottom center, margin_v=180).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"d:\trae\TrimAURAs\TrimAuras")

from app.pipeline.video_editor import RENDER_DIR, _build_subtitle_file

SEGMENTS = [
    {"text": "this is a test phrase with several words spoken aloud",
     "start": 0.0, "end": 6.0, "words": [
        {"start": 0.0, "end": 0.6, "word": "this"},
        {"start": 0.7, "end": 1.1, "word": "is"},
        {"start": 1.2, "end": 1.8, "word": "a"},
        {"start": 1.9, "end": 2.5, "word": "test"},
        {"start": 2.6, "end": 3.2, "word": "phrase"},
        {"start": 3.3, "end": 3.9, "word": "with"},
        {"start": 4.0, "end": 4.6, "word": "several"},
        {"start": 4.7, "end": 5.3, "word": "words"},
        {"start": 5.4, "end": 6.0, "word": "aloud"},
    ]},
]
CLIP_START, CLIP_END = 0.1, 30.3

STYLE = {"alignment": 2, "margin_v": 180, "font_name": "Arial Black",
         "font_size": 36, "primary_color": "&H00FFE600",
         "highlight_color": "&H00FF3333", "outline_color": "&H00000000",
         "outline_width": 6}


def main() -> None:
    ass = _build_subtitle_file(SEGMENTS, CLIP_START, CLIP_END, STYLE,
                               name="subs_probe", karaoke=True, cuts=[],
                               canvas_w=1080, canvas_h=1920)
    print(f"ASS: {ass}", flush=True)
    print(Path(ass).read_text(encoding="utf-8"), flush=True)

    out = RENDER_DIR / "subs_probe_frame.png"
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "color=black:s=1080x1920:d=10:r=30",
        "-ss", "2.0", "-frames:v", "1",
        "-vf", f"subtitles={str(ass).replace(chr(92), '/').replace(':', chr(92) + ':')}:charenc=utf-8",
        str(out),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print("FFMPEG FAILED:", r.stderr[-1000:], flush=True)
        return

    # Find bbox of non-black pixels
    raw = RENDER_DIR / "subs_probe.raw"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out),
                    "-vf", "scale=108:192", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    str(raw)], check=True, capture_output=True, timeout=120)
    data = raw.read_bytes()
    W, H = 108, 192
    xs, ys = [], []
    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 3
            if max(data[i], data[i + 1], data[i + 2]) > 24:
                xs.append(x)
                ys.append(y)
    if xs:
        print(f"TEXT_BBOX scaled108x192: x0={min(xs)} x1={max(xs)} "
              f"y0={min(ys)} y1={max(ys)} count={len(xs)}", flush=True)
        print(f"  -> full-res approx: x {min(xs)*10}-{max(xs)*10}, "
              f"y {min(ys)*10}-{max(ys)*10} of 1080x1920", flush=True)
    else:
        print("NO TEXT FOUND", flush=True)

    # ASCII render
    CHARS = " .:-=+*#%@"
    lines = []
    for y in range(H):
        lines.append("".join(CHARS[min(data[(y * W + x) * 3] * len(CHARS) // 256, 9)]
                             for x in range(W)))
    (RENDER_DIR / "subs_probe_ascii.txt").write_text("\n".join(lines), encoding="utf-8")
    print("ascii ->", RENDER_DIR / "subs_probe_ascii.txt", flush=True)


if __name__ == "__main__":
    main()
