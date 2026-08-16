"""Capture local ffmpeg version + full filter_complex for the diff report."""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
ROOT = Path(__file__).resolve().parent.parent

from app.pipeline.video_editor import execute_render

VID = r"tmp\downloads\VAL_Agent_30_Launch.mov"
FACE = [{"t": i, "cx": 0.45 + 0.05 * ((i // 10) % 2), "cy": 0.40 + 0.02 * (i % 5)}
        for i in range(0, 96)]
lines: list[str] = []


def hook(line):
    lines.append(line)


async def main():
    clip = {"start": 10.0, "end": 30.0}
    t0 = time.monotonic()
    # Patch print to also capture [render] lines (instrumentation output).
    import builtins
    orig_print = builtins.print
    def spy(*a, **k):
        s = " ".join(str(x) for x in a)
        if s.startswith("[render]"):
            lines.append(s)
        orig_print(*a, **k)
    builtins.print = spy
    try:
        outs = await execute_render(
            VID, [clip], [], "mrbeast_energy_v1",
            burn_text=False, apply_overlay=True, trim_silence=False,
            face_track=FACE,
        )
        dt = time.monotonic() - t0
        print(f"[local-render] OK {dt:.1f}s -> {outs}")
    finally:
        builtins.print = orig_print
    return time.monotonic() - t0


if __name__ == "__main__":
    dt = asyncio.run(main())
    fc = next((l.split("filter_complex", 1)[1] for l in lines if "filter_complex" in l), "")
    ver = next((l.replace("[render] ffmpeg: ", "") for l in lines if "ffmpeg version" in l), "")
    ev = {
        "env": "local",
        "ffmpeg_version": ver,
        "filter_complex": fc.strip(),
        "render_seconds": round(dt, 1),
        "ok": True,
    }
    (ROOT / "tmp" / "render_evidence_local.json").write_text(
        json.dumps(ev, indent=2), encoding="utf-8")
    print("wrote tmp/render_evidence_local.json | filter_complex chars:", len(fc))
