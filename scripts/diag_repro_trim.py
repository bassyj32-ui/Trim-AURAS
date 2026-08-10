"""Local repro: execute_render with trim_silence=True (the failing path).

Replicates the /api/jobs/upload trim_silence=true failure (job 96:
"FFmpeg failed (exit 234): Error opening output file ...") using local
ffmpeg 8.1.2 + the same mrbeast_energy_v1 template the matrix jobs used.

Synthetic segments with word gaps >= 0.5s so _compute_silence_cuts returns
cuts and the [condv] concat chain actually builds.
"""
import asyncio
import json
import sys

sys.path.insert(0, r"d:\trae\TrimAURAs\TrimAuras")

from app.pipeline.video_editor import execute_render  # noqa: E402

VIDEO = r"d:\trae\TrimAURAs\TrimAuras\tmp\diag\videos\v01_small_h264_720p_40s.mp4"

# Words with a 2.0s gap between them -> silence cut in [2.0, 4.0].
SEGMENTS = [
    {"text": "word one", "start": 0.0, "end": 2.0, "words": [
        {"start": 0.0, "end": 0.5, "word": "word"},
        {"start": 0.7, "end": 2.0, "word": "one"},
    ]},
    {"text": "word two", "start": 4.0, "end": 6.0, "words": [
        {"start": 4.0, "end": 4.6, "word": "word"},
        {"start": 4.8, "end": 6.0, "word": "two"},
    ]},
    {"text": "word three", "start": 8.0, "end": 10.0, "words": [
        {"start": 8.0, "end": 8.7, "word": "word"},
        {"start": 8.9, "end": 10.0, "word": "three"},
    ]},
]

CLIPS = [{"start": 0.0, "end": 10.0}]


async def main():
    print("=== trim_silence=True (repro of job 96 failure) ===", flush=True)
    try:
        out = await execute_render(
            VIDEO, CLIPS, SEGMENTS, "mrbeast_energy_v1",
            burn_text=False, apply_overlay=True, trim_silence=True, face_track=None,
        )
        print("RENDER OK ->", out, flush=True)
    except Exception as e:
        print(f"RENDER FAILED: {type(e).__name__}: {str(e)[:800]}", flush=True)
    # Dump the filter_complex header of the (now failed) render log
    log = r"d:\trae\TrimAURAs\TrimAuras\tmp\render\clip_0.stderr.log"
    try:
        head = open(log, encoding="utf-8", errors="replace").read().splitlines()
        print("\n--- FILTER (line 2 of stderr log) ---", flush=True)
        print(head[1] if len(head) > 1 else "(no header)", flush=True)
    except Exception as e:
        print("log read failed:", e, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
