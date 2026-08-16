"""ASCII-render the top region of burn vs no_burn frames at t=2.0.

No images needed — downscale the top 45% of each 1080x1920 frame to a
~106x22 grid of luminance chars so the actual differing content is visible
as text. Also prints a diff map (D where pixels differ).
"""
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BURN = ROOT / "tmp" / "parity_burn_local" / "burn.mp4"
NOBURN = ROOT / "tmp" / "parity_burn_local" / "no_burn.mp4"

CHARS = " .:-=+*#%@"
W, H = 106, 22
TOP_H = 0.45  # top 45% of frame


def extract_top_gray(src: Path, t: float, dst: Path) -> None:
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", str(t),
        "-frames:v", "1", "-vf", f"crop=iw:ih*{TOP_H}:0:0,scale={W}:{H}",
        "-f", "rawvideo", "-pix_fmt", "gray", str(dst),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    if not dst.exists() or dst.stat().st_size != W * H:
        raise RuntimeError(f"bad size: {dst.stat().st_size}")


def render(px: bytes) -> str:
    out = []
    for y in range(H):
        row = "".join(CHARS[min(px[y * W + x] * len(CHARS) // 256, len(CHARS) - 1)]
                      for x in range(W))
        out.append(row)
    return "\n".join(out)


def main() -> None:
    lines: list[str] = []
    for name, src in (("BURN", BURN), ("NOBURN", NOBURN)):
        dst = ROOT / "tmp" / f"top_{name.lower()}.raw"
        extract_top_gray(src, 2.0, dst)
        lines.append(f"===== {name} top 45% @ t=2.0 =====")
        lines.append(render(dst.read_bytes()))
        lines.append("")
    # diff map
    a = (ROOT / "tmp" / "top_burn.raw").read_bytes()
    b = (ROOT / "tmp" / "top_noburn.raw").read_bytes()
    lines.append("===== DIFF MAP (D = |burn-noburn|>12) =====")
    for y in range(H):
        lines.append("".join("D" if abs(a[y * W + x] - b[y * W + x]) > 12 else " "
                             for x in range(W)))
    out_path = ROOT / "tmp" / "ascii_top.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path} ({len(lines)} lines)", flush=True)


if __name__ == "__main__":
    main()
