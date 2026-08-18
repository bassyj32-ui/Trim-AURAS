"""Repro: does rendering the Frame.io source (VAL_Agent_30_Launch.mov) hang?

Renders one clip with the mrbeast_energy_v1 template (the auto pick for the
hung jobs 79/80) using a synthetic face track, timing each variant so we can
bisect which filter (face crop / ken burns / overlay) is the culprit.
"""
import asyncio
import sys
import time

sys.path.insert(0, ".")

from app.pipeline.video_editor import execute_render

VID = r"tmp\downloads\VAL_Agent_30_Launch.mov"

# Synthetic face track: a person near center moving slightly, 0..95s every 1s
FACE = [{"t": i, "cx": 0.45 + 0.05 * ((i // 10) % 2), "cy": 0.40 + 0.02 * (i % 5)}
        for i in range(96)]


def render(clip, face, tag):
    t0 = time.monotonic()
    try:
        outs = asyncio.run(execute_render(
            VID, [clip], [], "mrbeast_energy_v1",
            burn_text=False, apply_overlay=True, trim_silence=False,
            face_track=face,
        ))
        dt = time.monotonic() - t0
        print(f"[{tag}] OK {dt:.1f}s -> {outs}", flush=True)
    except Exception as e:
        dt = time.monotonic() - t0
        print(f"[{tag}] FAILED after {dt:.1f}s: {str(e)[:300]}", flush=True)


if __name__ == "__main__":
    clip = {"start": float(sys.argv[1]), "end": float(sys.argv[2])}
    tag = sys.argv[3] if len(sys.argv) > 3 else "full"
    face = FACE if tag != "nocrop" else None
    render(clip, face, tag)
