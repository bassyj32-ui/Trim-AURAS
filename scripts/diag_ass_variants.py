"""Isolate why karaoke captions render oversized at the TOP.

Renders several ASS variants onto a black 1080x1920 canvas at t=2.0 and
reports the text bounding box for each:
  A. baseline (current generator output: karaoke \\k, no PlayRes)
  B. plain text, no \\k, no PlayRes
  C. baseline + explicit PlayResX=1080, PlayResY=1920
  D. baseline, Alignment=5 (middle)
  E. baseline, Alignment=8 (top)
  F. baseline + \\an2 override in Dialogue text
  G. short text "hello" alignment 2, no PlayRes
"""
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
RENDER = ROOT / "tmp" / "render"
W, H = 1080, 1920

BASE_STYLE = ("Style: Default,Arial Black,36,&H00FFFFFF,&H00FF3333,&H00000000,"
              "&H00000000,0,0,0,0,100,100,0,0,1,6,0,2,20,20,180,1")
KARAOKE_TEXT = (r"{\k50}this {\k40}is {\k60}a {\k60}test {\k60}phrase "
                r"{\k60}with {\k60}several {\k60}words {\k60}aloud")

VARIANTS = {
    "A_karaoke_noplayres": (BASE_STYLE, KARAOKE_TEXT, None),
    "B_plain_noplayres": (BASE_STYLE, "this is a test phrase with several words aloud", None),
    "C_karaoke_playres": (BASE_STYLE, KARAOKE_TEXT, "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\nScaledBorderAndShadow: yes"),
    "D_karaoke_mid_align": (BASE_STYLE.replace(",0,2,20,20,180,1", ",0,5,20,20,180,1"), KARAOKE_TEXT, None),
    "E_karaoke_top_align": (BASE_STYLE.replace(",0,2,20,20,180,1", ",0,8,20,20,180,1"), KARAOKE_TEXT, None),
    "F_karaoke_an2_override": (BASE_STYLE, r"{\an2}" + KARAOKE_TEXT, None),
    "G_short_hello": (BASE_STYLE, "hello", None),
}


def ass_for(name: str, style: str, text: str, script_extra: str | None) -> Path:
    info = script_extra or ("[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\n"
                            "ScaledBorderAndShadow: yes")
    body = (
        f"{info}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.90,Default,,0,0,0,,{text}\n"
    )
    p = RENDER / f"var_{name}.ass"
    p.write_text(body, encoding="utf-8")
    return p


def text_bbox(png: Path) -> tuple[int, int, int, int, int]:
    raw = RENDER / f"bbox_{png.stem}.raw"
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(png),
        "-vf", "scale=54:96", "-f", "rawvideo", "-pix_fmt", "gray", str(raw),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    data = raw.read_bytes()
    xs, ys = [], []
    for y in range(96):
        for x in range(54):
            if data[y * 54 + x] > 24:
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0, 0, 0, 0, 0)
    count = len(xs)
    # scale back to 1080x1920
    x0, x1 = min(xs) * 20, max(xs) * 20 + 20
    y0, y1 = min(ys) * 20, max(ys) * 20 + 20
    return (x0, y0, x1, y1, count)


def render(ass: Path, png: Path) -> None:
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "color=black:s=1080x1920:d=10:r=30",
        "-ss", "2.0", "-frames:v", "1",
        "-vf", f"subtitles={ass.name}:charenc=utf-8",
        png.name,
    ], cwd=str(ass.parent), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])


def main() -> None:
    lines = []
    for name, (style, text, extra) in VARIANTS.items():
        p = ass_for(name, style, text, extra)
        png = RENDER / f"var_{name}.png"
        render(p, png)
        x0, y0, x1, y1, cnt = text_bbox(png)
        lines.append(
            f"{name}: bbox x={x0}-{x1} y={y0}-{y1} area={cnt} "
            f"(y0={y0/1920:.1%} y1={y1/1920:.1%})")
    out = ROOT / "tmp" / "ass_variants.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
