import json
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

PROMPT_PATH = Path("prompts") / "clip_analysis.txt"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_analyze(
    segments: list[dict[str, Any]],
    max_clips: int = 5,
    existing_clips: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Use DeepSeek to pick viral clip timestamps from transcript segments.

    Args:
        segments: Full transcript segments.
        max_clips: Maximum number of clips to suggest.
        existing_clips: Previously selected clips so DeepSeek avoids repeats.

    Returns a list of {'start': float, 'end': float, 'reason': str}.
    """
    transcript_text = _segments_to_text(segments)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = system_prompt.replace("{max_clips}", str(max_clips))

    user_msg = f"TRANSCRIPT:\n{transcript_text}\n\n"
    if existing_clips:
        existing_desc = "\n".join(
            f"  - Already used: [{c['start']}-{c['end']}] ({c.get('reason', '')})"
            for c in existing_clips
        )
        user_msg += f"Previously selected clips (DO NOT repeat these):\n{existing_desc}\n\n"
    user_msg += "Return JSON array of clips."

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.4,
    }

    async with AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    clips = json.loads(raw)

    return clips


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "")
        lines.append(f"[{start:.1f}-{end:.1f}] {text}")
    return "\n".join(lines)
