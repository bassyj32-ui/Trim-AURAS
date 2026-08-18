"""TEST 1 + TEST 2 combined-fix verification (local, deterministic).

Renders the SAME v01 window (0.1..30.3) with face_track=None (static crop ->
pixel-identical framing) in three configurations:

  A. burn_text=True  + trim_silence=True  -> combined_burn_trim.mp4
  B. burn_text=False + trim_silence=True  -> combined_ctrl_trim.mp4
  C. burn_text=False + trim_silence=False -> default_clean.mp4   (TEST 2)

Segments have a real 4s pause (6.0->10.0) + trailing dead air (13.0->30.3),
so trim_silence must cut 21.3s -> expected rendered duration ~8.9s.

Checks:
  - Resolution of A/B/C (expect 1080x1920 canvas — preferred_height only caps
    the DOWNLOAD, render output is always the template canvas).
  - Duration of A/B vs expected cut math (21.3s cut, 8.9s out).
  - PSNR(A,B) at caption times (expect ~25dB, caption-only difference).
  - Row profile A vs B at t=2.0 (expect ONE band at the bottom,
    y~1708-1737 = margin_v 180 from bottom, NOT the 3-band top-of-frame bug).
  - TEST 2 regression: PSNR(C, pre-fix baseline no_burn.mp4) ~ inf (bit-identical).
  - Filter-graph audit from stderr logs: A contains `subtitles=` + `[condv]`
    + `[conda]`; C contains NEITHER (default path untouched by the fixes).
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
OUT = ROOT / "tmp" / "combined_fix"
OUT.mkdir(parents=True, exist_ok=True)
BASELINE = ROOT / "tmp" / "parity_burn_local" / "no_burn.mp4"  # pre-fix render (8/6)
TEMPLATE = "mrbeast_energy_v1"

# Two word-bearing segments with a 4s pause + trailing dead air.
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
    {"text": "second phrase spoken after a pause",
     "start": 10.0, "end": 13.0, "words": [
        {"start": 10.0, "end": 10.5, "word": "second"},
        {"start": 10.6, "end": 11.1, "word": "phrase"},
        {"start": 11.2, "end": 11.7, "word": "spoken"},
        {"start": 11.8, "end": 12.3, "word": "after"},
        {"start": 12.4, "end": 13.0, "word": "pause"},
    ]},
]
CLIPS = [{"start": 0.1, "end": 30.3}]
WINDOW = 30.3 - 0.1  # 30.2s source window
EXPECTED_CUTS = [(6.0, 10.0), (13.0, 30.3)]
EXPECTED_CUT_S = sum(ce - cs for cs, ce in EXPECTED_CUTS)  # 21.3s
EXPECTED_DUR = WINDOW - EXPECTED_CUT_S  # 8.9s


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kw)


def probe(path: Path) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(r.stdout)
    v = j["streams"][0]
    return {"w": v["width"], "h": v["height"],
            "duration": round(float(j["format"]["duration"]), 3)}


def frame(path: Path, t: float, dst: Path) -> None:
    # Frame-accurate: -ss AFTER -i
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
          "-frames:v", "1", str(dst)], check=True)


def psnr(a: Path, b: Path, t: float) -> str:
    fa, fb = OUT / "psnr_a.png", OUT / "psnr_b.png"
    frame(a, t, fa)
    frame(b, t, fb)
    r = _run(["ffmpeg", "-y", "-v", "info", "-i", str(fa), "-i", str(fb),
              "-filter_complex", "psnr=stats_file=-", "-f", "null", "-"])
    lines = [l for l in r.stderr.splitlines() if "PSNR" in l]
    return lines[-1].strip() if lines else "no-psnr"


def row_profile(a: Path, b: Path, t: float, scale_h: int = 1920) -> dict:
    """Per-row gray diff profile between two frames (scaled to 1xH)."""
    ra, rb = OUT / "row_a.raw", OUT / "row_b.raw"
    for src, dst in ((a, ra), (b, rb)):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
              "-frames:v", "1", "-vf", f"scale=1:{scale_h}",
              "-f", "rawvideo", "-pix_fmt", "gray", str(dst)], check=True)
    da, db = ra.read_bytes(), rb.read_bytes()
    if len(da) != len(db):
        return {"err": f"size mismatch {len(da)} vs {len(db)}"}
    n = scale_h
    diff_rows = [i for i in range(n)
                 if abs(int(da[i]) - int(db[i])) > 12]
    bands: list[list[int]] = []
    for i in diff_rows:
        if bands and i - bands[-1][-1] == 1:
            bands[-1].append(i)
        else:
            bands.append([i])
    out_bands = [(b[0], b[-1]) for b in bands]
    return {"diff_rows": len(diff_rows), "bands": out_bands,
            "first_pct": (out_bands[0][0] / n if out_bands else None),
            "last_pct": (out_bands[-1][1] / n if out_bands else None)}


def band_diff(a: Path, b: Path, t: float) -> dict:
    ba, bb = OUT / "bd_a.rgb", OUT / "bd_b.rgb"
    for src, dst in ((a, ba), (b, bb)):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
              "-frames:v", "1", "-vf", "crop=iw:ih*0.35:0:ih*0.65,scale=270:120",
              "-f", "rawvideo", "-pix_fmt", "gray", str(dst)], check=True)
    da, db = ba.read_bytes(), bb.read_bytes()
    n = len(da)
    d = sum(1 for x, y in zip(da, db) if abs(x - y) > 12)
    return {"band_pixels": n, "diff_pixels": d,
            "diff_ratio": round(d / n, 5)}


def read_last_filter() -> str:
    """Read the filter_complex from the newest per-render stderr log."""
    logs = sorted((ROOT / "tmp" / "render").glob("clip_*.stderr.log"),
                  key=lambda p: p.stat().st_mtime)
    if not logs:
        return ""
    txt = logs[-1].read_text(encoding="utf-8", errors="replace")
    # The log's first two lines are "# <ffmpeg version>" and "# <filter_complex>".
    hash_lines = [l[2:].strip() for l in txt.splitlines() if l.startswith("# ")]
    return hash_lines[1] if len(hash_lines) > 1 else ""


async def render(label: str, burn: bool, trim: bool) -> tuple[Path, str]:
    print(f"rendering {label} (burn={burn} trim={trim}) ...", flush=True)
    await execute_render(str(VIDEO), CLIPS, SEGMENTS, TEMPLATE,
                         burn_text=burn, apply_overlay=True,
                         trim_silence=trim, face_track=None)
    src = ROOT / "tmp" / "render" / "clip_0.mp4"
    dst = OUT / f"{label}.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), str(dst)], check=True)
    return dst, read_last_filter()


def audit(txt: str) -> dict:
    return {
        "has_subtitles": "subtitles=" in txt,
        "has_condv": "[condv]" in txt,
        "has_conda": "[conda]" in txt,
    }


async def main() -> None:
    a, fa = await render("combined_burn_trim", burn=True, trim=True)
    b, _ = await render("combined_ctrl_trim", burn=False, trim=True)
    c, fc = await render("default_clean", burn=False, trim=False)

    res: dict = {
        "segments": {"window_s": WINDOW, "cuts": EXPECTED_CUTS,
                     "expected_cut_s": EXPECTED_CUT_S,
                     "expected_dur_s": EXPECTED_DUR},
        "probe": {
            "burn_trim": probe(a),
            "ctrl_trim": probe(b),
            "default_clean": probe(c),
        },
        "test1_caption": {
            "psnr_t2_caption1": psnr(a, b, 2.0),
            "psnr_t75_caption2": psnr(a, b, 7.5),
            "row_profile_t2": row_profile(a, b, 2.0),
            "bottom_band_diff_t2": band_diff(a, b, 2.0),
        },
        "test2_regression": {
            "baseline_exists": BASELINE.exists(),
            "baseline": probe(BASELINE) if BASELINE.exists() else None,
            "psnr_default_vs_baseline": (
                psnr(c, BASELINE, 2.0) if BASELINE.exists() else "NO_BASELINE"),
        },
        "filter_audit": {
            "burn_trim": audit(fa),
            "default_clean": audit(fc),
        },
    }
    out = OUT / "result.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
