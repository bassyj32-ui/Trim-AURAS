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
            model="whisper-large-v3",
            response_format="verbose_json",
            language="en",
        )

    os.unlink(audio_path)

    segments = []
    for seg in response.segments:
        segments.append({
            "start": round(seg.get("start", 0), 1),
            "end": round(seg.get("end", 0), 1),
            "text": seg.get("text", "").strip(),
        })

    return segments


def _extract_audio(video_path: str) -> str:
    audio_path = tempfile.mktemp(suffix=".mp3")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame",
         "-ar", "16000", "-ac", "1", "-y", audio_path],
        check=True, capture_output=True, text=True,
    )
    return audio_path
