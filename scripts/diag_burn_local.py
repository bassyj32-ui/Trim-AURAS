"""Controlled burn_captions output test (local, deterministic).

Renders the SAME v01 clip window twice with face_track=None (static center
crop -> pixel-identical framing) and burn_text ON vs OFF, then frame-diffs
at t=2.0:
  - near-identical PSNR (>= 40dB)  -> burn drew NOTHING visible (bug)
  - clearly lower PSNR + non-zero caption-band diff -> captions actually
    rendered into the pixels (fix verified)

This isolates the burn effect from the face-track crop-plan differences that
confounded the deployed burn2-vs-control comparison (different clip spans ->
different crop paths).
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"d:\trae\TrimAURAs\TrimAuras")

from app.pipeline.video_editor import execute_render

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
VIDEO = ROOT / "tmp" / "diag" / "videos" / "v01_small_h264_720p_40s.mp4"
OUT_DIR = ROOT / "tmp" / "parity_burn_local"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Matches the deployed clips: window 0.1..30.3 with word-bearing speech.
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
CLIPS = [{"start": 0.1, "end": 30.3}]


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    v = json.loads(r.stdout).get("streams", [{}])[0]
    return {"w": v.get("width"), "h": v.get("height")}


def psnr(path_a: Path, path_b: Path, t: float) -> str:
    fa = OUT_DIR / "f_a.png"
    fb = OUT_DIR / "f_b.png"
    for src, dst in ((path_a, fa), (path_b, fb)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src),
             "-frames:v", "1", str(dst)],
            capture_output=True, text=True, timeout=120, check=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "info", "-i", str(fa), "-i", str(fb),
         "-filter_complex", "psnr=stats_file=-", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    lines = [l for l in r.stderr.splitlines() if "PSNR" in l]
    return lines[-1] if lines else "no-psnr"


def band_diff(path_a: Path, path_b: Path, t: float) -> dict:
    ba = OUT_DIR / "b_a.rgb"
    bb = OUT_DIR / "b_b.rgb"
    for src, dst in ((path_a, ba), (path_b, bb)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src),
             "-frames:v", "1", "-vf", "crop=iw:ih*0.35:0:ih*0.65,scale=270:120",
             "-f", "rawvideo", "-pix_fmt", "gray", str(dst)],
            capture_output=True, text=True, timeout=120, check=True)
    da, db = ba.read_bytes(), bb.read_bytes()
    if len(da) != len(db):
        return {"err": "size mismatch"}
    n = len(da)
    d = sum(1 for x, y in zip(da, db) if abs(x - y) > 12)
    return {"band_pixels": n, "diff_pixels": d, "diff_ratio": round(d / n, 5)}


async def main():
    print("rendering burn OFF (control) ...", flush=True)
    await execute_render(str(VIDEO), CLIPS, SEGMENTS, "mrbeast_energy_v1",
                         burn_text=False, apply_overlay=True,
                         trim_silence=False, face_track=None)
    ctrl = OUT_DIR / "no_burn.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                    str(ROOT / "tmp" / "render" / "clip_0.mp4"), str(ctrl)],
                   check=True, capture_output=True, timeout=120)

    print("rendering burn ON ...", flush=True)
    await execute_render(str(VIDEO), CLIPS, SEGMENTS, "mrbeast_energy_v1",
                         burn_text=True, apply_overlay=True,
                         trim_silence=False, face_track=None)
    burn = OUT_DIR / "burn.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                    str(ROOT / "tmp" / "render" / "clip_0.mp4"), str(burn)],
                   check=True, capture_output=True, timeout=120)

    print("probing ...", flush=True)
    res = {
        "no_burn": probe(ctrl),
        "burn": probe(burn),
        "psnr_t2": psnr(burn, ctrl, 2.0),
        "band_diff_t2": band_diff(burn, ctrl, 2.0),
    }
    out = OUT_DIR / "result.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
