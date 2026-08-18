"""Faithful local repro of the pipeline on the Frame.io source.

Runs the EXACT same steps as orchestrator.execute_pipeline on
VAL_Agent_30_Launch.mov (the source of hung jobs 79/80) and times each
stage. Uses real Groq + DeepSeek calls. Then renders with the real clips,
segments, and face track.
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, ".")

from app.pipeline.face_track import detect_face_track
from app.pipeline.intelligence import (
    classify_content,
    execute_analyze,
    extract_video_signals,
    recommend_template,
    snap_clips_to_signals,
)
from app.pipeline.transcriber import execute_transcribe
from app.pipeline.video_editor import execute_render

VID = r"tmp\downloads\VAL_Agent_30_Launch.mov"


async def timeit(name, coro):
    t0 = time.monotonic()
    r = await coro
    print(f"[{name}] {time.monotonic()-t0:.1f}s", flush=True)
    return r


async def main():
    signals = await timeit("signals", asyncio.to_thread(extract_video_signals, VID))
    face = await timeit("face_track", asyncio.to_thread(detect_face_track, VID))
    print("  face samples:", len(face), flush=True)

    segments = await timeit("transcribe", execute_transcribe(VID))
    text = " ".join(s.get("text", "") for s in segments).strip()
    has_speech = len(text) >= 10
    content_type = classify_content(segments, signals)
    print(f"  speech: {has_speech} ({len(text)} chars) content_type={content_type}", flush=True)

    if has_speech:
        clips = await timeit("analyze", execute_analyze(
            segments, max_clips=3, campaign_rules="", video_signals=signals,
        ))
    else:
        from app.pipeline.intelligence import select_signal_clips
        clips = select_signal_clips(max_clips=3, video_signals=signals)
    clips = snap_clips_to_signals(clips, signals)
    print("  clips:", json.dumps(clips, default=str)[:800], flush=True)

    template = recommend_template(content_type, title="frameio_link", transcript_text=text)
    print("  template:", template, flush=True)

    t0 = time.monotonic()
    outs = await execute_render(
        VID, clips, segments, template,
        burn_text=False, trim_silence=False, face_track=face,
    )
    print(f"[render] {time.monotonic()-t0:.1f}s -> {outs}", flush=True)
    json.dump({"clips": clips, "template": template, "face_samples": len(face),
               "segments": len(segments)},
              open(r"tmp\repro_result.json", "w", encoding="utf-8"), default=str, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
