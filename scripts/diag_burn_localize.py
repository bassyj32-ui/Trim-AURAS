"""Localize burn-vs-no_burn pixel differences numerically (no images).

For a set of timestamps inside (2.0) and outside (7.0) the caption window:
  1. frame-accurately extract the frame from the VIDEO files
  2. compute a 5x5 grid of mean-abs-RGB-diff per cell
  3. compute the bounding box of differing pixels (threshold 16)
The caption is expected at the bottom center (margin_v=180, alignment=2).
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BURN = ROOT / "tmp" / "parity_burn_local" / "burn.mp4"
NOBURN = ROOT / "tmp" / "parity_burn_local" / "no_burn.mp4"
OUT = ROOT / "tmp" / "parity_burn_localize.json"

GRID = 5


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def extract_frame(src: Path, t: float, dst: Path) -> None:
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
             "-frames:v", "1", str(dst)])
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"extract failed t={t}: {r.stderr[-300:]}")


def localize(a: Path, b: Path) -> dict:
    """Per-cell mean-abs-diff (RGB) over a GRIDxGRID grid + diff bbox."""
    # Downscale both frames to 108x192 (grid of ~21.6x38.4 px cells) as RGB.
    ra, rb = OUT.parent / "loc_a.rgb", OUT.parent / "loc_b.rgb"
    for src, dst in ((a, ra), (b, rb)):
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                 "-vf", "scale=108:192", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 str(dst)])
        if r.returncode != 0:
            raise RuntimeError(f"scale failed: {r.stderr[-300:]}")
    da, db = ra.read_bytes(), rb.read_bytes()
    assert len(da) == len(db) and len(da) == 108 * 192 * 3, len(da)
    W, H = 108, 192
    cw, ch = W // GRID, H // GRID
    cells: dict[str, int] = {}
    diff_px = []
    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 3
            md = max(abs(da[i] - db[i]), abs(da[i + 1] - db[i + 1]),
                     abs(da[i + 2] - db[i + 2]))
            if md > 16:
                diff_px.append((x, y))
                gx, gy = min(x // cw, GRID - 1), min(y // ch, GRID - 1)
                cells[f"r{gy}c{gx}"] = cells.get(f"r{gy}c{gx}", 0) + 1
    # Per-cell mean abs diff (fill every cell)
    means = {}
    for gy in range(GRID):
        for gx in range(GRID):
            tot = n = 0
            for y in range(gy * ch, min((gy + 1) * ch, H)):
                for x in range(gx * cw, min((gx + 1) * cw, W)):
                    i = (y * W + x) * 3
                    tot += (abs(da[i] - db[i]) + abs(da[i + 1] - db[i + 1])
                            + abs(da[i + 2] - db[i + 2])) // 3
                    n += 1
            means[f"r{gy}c{gx}"] = round(tot / n, 1)
    bbox = None
    if diff_px:
        xs = [p[0] for p in diff_px]
        ys = [p[1] for p in diff_px]
        bbox = {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                "count": len(diff_px), "area_pct": round(len(diff_px) / (W * H) * 100, 2)}
    return {"diff_bbox": bbox, "cells": cells, "cell_means": means}


def main() -> None:
    results = {}
    for t, label in ((2.0, "caption_on"), (7.0, "caption_off")):
        fa = OUT.parent / f"loc_{label}_burn.png"
        fb = OUT.parent / f"loc_{label}_noburn.png"
        extract_frame(BURN, t, fa)
        extract_frame(NOBURN, t, fb)
        results[label] = localize(fa, fb)
        print(f"{label}: {json.dumps(results[label])}", flush=True)
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
