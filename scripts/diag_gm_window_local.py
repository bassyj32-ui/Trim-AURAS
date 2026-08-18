"""TEST 3 caption proof — local deterministic burn-on vs burn-off of the
generate-more window (1.5..21.5) on gm_sil2_src.mp4 with mrbeast_energy_v1.

Segments are constructed so _compute_silence_cuts reproduces the EXACT keep
intervals observed in the deployed generate-more render's filter audit:
atrim=[1.5:4.18, 7.94:12.64, 16.38:21.5] -> rendered duration 12.5s.

PSNR(burn_on, burn_off) + row-profile at caption times must show caption-only
diffs confined to the bottom caption band (~y1700-1740 = margin_v 180), NOT
the 4x-oversized top-of-frame bug.
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"d:\trae\TrimAURAs\TrimAuras")

from app.pipeline.video_editor import execute_render

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
VIDEO = ROOT / "tmp" / "diag" / "videos" / "gm_sil2_src.mp4"
OUT = ROOT / "tmp" / "gm_window_local"
OUT.mkdir(parents=True, exist_ok=True)
TEMPLATE = "mrbeast_energy_v1"
CLIPS = [{"start": 1.5, "end": 21.5}]
KEEP = [(1.5, 4.18), (7.94, 12.64), (16.38, 21.5)]
EXPECTED_DUR = round(sum(e - s for s, e in KEEP), 3)  # 12.5


def dense_words(interval) -> list[dict]:
    """Evenly spaced words inside the interval; gaps < 0.5 so no inter-word
    cut; first word starts at interval start, last ends at interval end
    (reproduces the exact deployed keep intervals as atrim ranges)."""
    s, e = interval
    dur = e - s
    n = max(2, int(dur // 0.8))
    words = []
    for i in range(n):
        ws = s + i * (dur / n)
        we = min(ws + 0.5, e)
        words.append({"start": round(ws, 3), "end": round(we, 3), "word": f"w{i}"})
    words[0]["start"] = s
    words[-1]["end"] = e
    return words


SEGMENTS = [
    {"text": f"segment {i}", "start": s, "end": e, "words": dense_words((s, e))}
    for i, (s, e) in enumerate(KEEP)
]


def _run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kw)


def probe(path: Path) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(r.stdout)
    v = j["streams"][0]
    return {"w": v["width"], "h": v["height"],
            "duration": round(float(j["format"]["duration"]), 3)}


def psnr(a: Path, b: Path, t: float) -> str:
    fa, fb = OUT / "psnr_a.png", OUT / "psnr_b.png"
    for src, dst in ((a, fa), (b, fb)):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
              "-frames:v", "1", str(dst)], check=True)
    r = _run(["ffmpeg", "-y", "-v", "info", "-i", str(fa), "-i", str(fb),
              "-filter_complex", "psnr=stats_file=-", "-f", "null", "-"])
    lines = [l for l in r.stderr.splitlines() if "PSNR" in l]
    return lines[-1].strip() if lines else "no-psnr"


def row_profile(a: Path, b: Path, t: float, scale_h: int = 1920) -> dict:
    ra, rb = OUT / "row_a.raw", OUT / "row_b.raw"
    for src, dst in ((a, ra), (b, rb)):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
              "-frames:v", "1", "-vf", f"scale=1:{scale_h}",
              "-f", "rawvideo", "-pix_fmt", "gray", str(dst)], check=True)
    da, db = ra.read_bytes(), rb.read_bytes()
    n = scale_h
    diff_rows = [i for i in range(n) if abs(int(da[i]) - int(db[i])) > 12]
    bands = []
    for i in diff_rows:
        if bands and i - bands[-1][-1] == 1:
            bands[-1].append(i)
        else:
            bands.append([i])
    ob = [(b[0], b[-1]) for b in bands]
    return {"diff_rows": len(diff_rows), "bands": ob,
            "first_pct": round(ob[0][0] / n, 4) if ob else None,
            "last_pct": round(ob[-1][1] / n, 4) if ob else None}


def band_diff(a: Path, b: Path, t: float, band: str) -> dict:
    ba, bb = OUT / "bd_a.rgb", OUT / "bd_b.rgb"
    expr = {"top": "crop=iw:ih*0.35:0:0",
            "mid": "crop=iw:ih*0.35:0:ih*0.325",
            "bottom": "crop=iw:ih*0.35:0:ih*0.65"}.get(band, "crop=iw:ih*0.35:0:ih*0.65")
    for src, dst in ((a, ba), (b, bb)):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
              "-frames:v", "1", "-vf", f"{expr},scale=270:120",
              "-f", "rawvideo", "-pix_fmt", "gray", str(dst)], check=True)
    da, db = ba.read_bytes(), bb.read_bytes()
    n = len(da)
    d = sum(1 for x, y in zip(da, db) if abs(x - y) > 12)
    return {"band_pixels": n, "diff_pixels": d, "diff_ratio": round(d / n, 5)}


async def render(label: str, burn: bool) -> Path:
    print(f"rendering {label} (burn={burn}) ...", flush=True)
    await execute_render(str(VIDEO), CLIPS, SEGMENTS, TEMPLATE,
                         burn_text=burn, apply_overlay=True,
                         trim_silence=True, face_track=None)
    src = ROOT / "tmp" / "render" / "clip_0.mp4"
    dst = OUT / f"{label}.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), str(dst)], check=True)
    return dst


async def main() -> None:
    on = await render("burn_on", burn=True)
    off = await render("burn_off", burn=False)

    res = {
        "window": {"clip": CLIPS[0], "keep_intervals": KEEP,
                   "expected_dur_s": EXPECTED_DUR},
        "probe": {"burn_on": probe(on), "burn_off": probe(off)},
        "caption": {
            # t=1.0 -> inside first keep interval (1.5..4.18 mapped to clip 0..2.68)
            "psnr_t1": psnr(on, off, 1.0),
            "row_profile_t1": row_profile(on, off, 1.0),
            "band_top_t1": band_diff(on, off, 1.0, "top"),
            "band_mid_t1": band_diff(on, off, 1.0, "mid"),
            "band_bottom_t1": band_diff(on, off, 1.0, "bottom"),
            # t=2.0 -> still first caption block
            "psnr_t2": psnr(on, off, 2.0),
            "row_profile_t2": row_profile(on, off, 2.0),
            # t=9.0 -> inside middle caption block (7.94..12.64 -> clip 2.68..7.38)
            "psnr_t9": psnr(on, off, 9.0),
            "row_profile_t9": row_profile(on, off, 9.0),
        },
    }
    (OUT / "result.json").write_text(json.dumps(res, indent=1, default=str),
                                     encoding="utf-8")
    print(json.dumps(res, indent=1, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
