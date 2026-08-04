import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_transcribe(video_path: str) -> list[dict[str, Any]]:
    """Extract audio from video and transcribe with Groq Whisper V3.

    Returns a list of segments with 'start', 'end', and 'text' keys.
    """
    client = AsyncGroq(api_key=settings.groq_api_key)

    audio_path = _extract_audio(video_path)

    with open(audio_path, "rb") as f:
        response = await client.audio.transcriptions.create(
            file=(Path(audio_path).name, f),
            model="whisper-large-v3-turbo",
            response_format="verbose_json",
            language="en",
            timestamp_granularities=["word"],
        )

    os.unlink(audio_path)

    segments = []
    for seg in response.segments or []:
        segments.append({
            "start": round(seg.get("start", 0), 1),
            "end": round(seg.get("end", 0), 1),
            "text": seg.get("text", "").strip(),
            "words": _words_for_segment(seg, response),
        })

    if not segments:
        # Groq's whisper-large-v3-turbo now returns "segments": null while
        # still returning flat word timestamps — rebuild segments from the
        # words so clip selection + caption rendering keep working.
        words = [_normalize_word(w) for w in (response.words or [])]
        segments = _segments_from_words(words)

    return segments


def _segments_from_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group flat word timestamps into segments (sentence-ish chunks).

    Splits on a >2.5s pause or a 20-word cap, and honors sentence-ending
    punctuation so each segment reads like a line.
    """
    segments = []
    cur: list[dict[str, Any]] = []

    def flush() -> None:
        if not cur:
            return
        text = " ".join(w["word"] for w in cur).strip()
        segments.append({
            "start": round(cur[0]["start"], 1),
            "end": round(cur[-1]["end"], 1),
            "text": text,
            "words": list(cur),
        })
        cur.clear()

    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > 2.5 or len(cur) >= 20):
            flush()
        cur.append(w)
    flush()

    return segments


def _normalize_word(w) -> dict[str, Any]:
    if isinstance(w, dict):
        return {
            "word": str(w.get("word", "")),
            "start": float(w.get("start", 0) or 0),
            "end": float(w.get("end", 0) or 0),
        }
    return {
        "word": str(getattr(w, "word", "")),
        "start": float(getattr(w, "start", 0) or 0),
        "end": float(getattr(w, "end", 0) or 0),
    }


def _words_for_segment(seg: dict[str, Any], response: Any) -> list[dict[str, Any]]:
    """Attach word-level timestamps that fall inside this segment.

    Groq (like OpenAI) returns a flat ``response.words`` array when
    ``timestamp_granularities=["word"]`` is requested; some builds also nest
    them inside each segment as ``seg["words"]``. Both shapes are handled so
    the karaoke renderer always has per-word timing when available.
    """
    seg_start = seg.get("start", 0)
    seg_end = seg.get("end", 0)

    nested = seg.get("words")
    if isinstance(nested, list) and nested:
        return [w for w in (_normalize_word(w) for w in nested) if w["word"]]

    flat = getattr(response, "words", None) or []
    if isinstance(flat, list) and flat:
        return [
            w
            for w in (_normalize_word(w) for w in flat)
            if w["word"] and seg_start <= w["start"] < seg_end
        ]

    return []


def _extract_audio(video_path: str) -> str:
    audio_path = tempfile.mktemp(suffix=".mp3")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame",
         "-ar", "16000", "-ac", "1", "-y", audio_path],
        check=True, capture_output=True, text=True,
    )
    return audio_path
