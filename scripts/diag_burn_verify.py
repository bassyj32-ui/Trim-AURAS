"""Numeric-only burn verification (no images needed).

Answers two questions with pure numbers:
1. Does the burn render actually differ from the no_burn render?
   -> whole-video frame-aligned PSNR (already measured 21.8dB, min 14.2, max inf)
2. Is the difference confined to the caption band (bottom ~18%)?
   -> frame-accurate extraction at t in {2.0 (caption on), 7.0 (caption off)},
      then per-band pixel-diff: bottom band (where margin_v=180 puts the text)
      vs top+middle bands.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BURN = ROOT / "tmp" / "parity_burn_local" / "burn.mp4"
NOBURN = ROOT / "tmp" / "parity_burn_local" / "no_burn.mp4"
OUT = ROOT / "tmp" / "parity_burn_verify.json"

FRAME_W, FRAME_H = 1080, 1920
BAND_H = int(FRAME_H * 0.18)          # caption sits at margin_v=180 from bottom
TOP = int(FRAME_H * 0.45)             # top band (no captions expected)
MID = FRAME_H - BAND_H - TOP          # middle band (no captions expected)


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def extract_frame(src: Path, t: float, dst: Path) -> None:
    # Frame-accurate: -ss AFTER -i.
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
             "-frames:v", "1", str(dst)])
    if r.returncode != 0:
        raise RuntimeError(f"extract failed: {r.stderr[-500:]}")


def psnr(a: Path, b: Path) -> float | None:
    r = run(["ffmpeg", "-i", str(a), "-i", str(b), "-filter_complex", "psnr",
             "-f", "null", "-"])
    for line in r.stderr.splitlines():
        if "PSNR" in line and "average" in line:
            m = [p for p in line.split() if p.startswith("average:")]
            if m:
                try:
                    return round(float(m[0].split(":")[1]), 3)
                except ValueError:
                    return None
    return None


def band_diff(a: Path, b: Path, t: float, y_frac: float, h_frac: float) -> int:
    """Diff pixels in a horizontal band [y_frac, y_frac+h_frac) of the frame."""
    ra, rb = OUT.parent / "band_a.rgb", OUT.parent / "band_b.rgb"
    for src, dst in ((a, ra), (b, rb)):
        r = run([
            "ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
            "-frames:v", "1",
            "-vf", (f"crop=iw:{int(h_frac*FRAME_H)}:0:{int(y_frac*FRAME_H)},"
                    f"scale=270:{int(270*h_frac*FRAME_H/FRAME_W)}"),
            "-f", "rawvideo", "-pix_fmt", "gray", str(dst),
        ])
        if r.returncode != 0:
            raise RuntimeError(f"band extract failed: {r.stderr[-500:]}")
    da, db = ra.read_bytes(), rb.read_bytes()
    if len(da) != len(db):
        raise RuntimeError("band size mismatch")
    return sum(1 for x, y in zip(da, db) if abs(x - y) > 12)


def main() -> None:
    results = {}
    for t, label in ((2.0, "caption_on"), (7.0, "caption_off")):
        fa = OUT.parent / f"verify_{label}_burn.png"
        fb = OUT.parent / f"verify_{label}_noburn.png"
        extract_frame(BURN, t, fa)
        extract_frame(NOBURN, t, fb)
        results[label] = {
            "psnr": psnr(fa, fb),
            "diff_top_px": band_diff(fa, fb, t, 0.0, TOP / FRAME_H),
            "diff_mid_px": band_diff(fa, fb, t, TOP / FRAME_H, MID / FRAME_H),
            "diff_bottom_px": band_diff(fa, fb, t, (TOP + MID) / FRAME_H,
                                        BAND_H / FRAME_H),
        }
        print(f"{label}: {results[label]}", flush=True)

    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
