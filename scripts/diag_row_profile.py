"""Per-row diff profile between burn and no_burn at t=2.0 (full res).

Extracts full-res t=2.0 frames, downscales each row of the 1080x1920 frame
to 1px, then reports the vertical profile of |burn-noburn| so the exact
y-extent of the caption region is visible as a numeric row histogram.
"""
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BURN = ROOT / "tmp" / "parity_burn_local" / "burn.mp4"
NOBURN = ROOT / "tmp" / "parity_burn_local" / "no_burn.mp4"

H = 1920


def extract(src: Path, t: float, dst: Path) -> None:
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
        "-frames:v", "1", "-vf", "scale=1:1920", "-f", "rawvideo",
        "-pix_fmt", "gray", str(dst),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or dst.stat().st_size != H:
        raise RuntimeError(r.stderr[-300:])


def main() -> None:
    da_p = ROOT / "tmp" / "rowprof_burn.raw"
    db_p = ROOT / "tmp" / "rowprof_noburn.raw"
    extract(BURN, 2.0, da_p)
    extract(NOBURN, 2.0, db_p)
    a, b = da_p.read_bytes(), db_p.read_bytes()
    rows = []
    for y in range(H):
        d = abs(a[y] - b[y])
        if d > 12:
            rows.append(y)
    # Group into contiguous bands
    bands = []
    start = prev = None
    for y in rows:
        if start is None:
            start = prev = y
        elif y == prev + 1:
            prev = y
        else:
            bands.append((start, prev))
            start = prev = y
    if start is not None:
        bands.append((start, prev))
    lines = []
    lines.append(f"diff rows: {len(rows)}/{H}")
    for s, e in bands:
        lines.append(f"  band y={s}-{e} (h={e-s+1})  [{s/1920:.1%}..{e/1920:.1%} of frame]")
    lines.append("row histogram (40px buckets, width=diff-col count):")
    for by in range(0, H, 40):
        cnt = sum(1 for y in rows if by <= y < by + 40)
        bar = "#" * min(cnt, 80)
        lines.append(f"  y={by:4d}: {cnt:4d} {bar}")
    out = ROOT / "tmp" / "row_profile.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
