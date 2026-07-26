import json
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

PROMPT_PATH = Path("prompts") / "seo_generation.txt"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_seo(
    transcript_text: str,
    campaign_rules: str = "",
) -> dict[str, str]:
    """Generate 3 title variations, description, and hashtags via DeepSeek.

    Args:
        transcript_text: The clip transcript text.
        campaign_rules: Optional SEO rules/campaign guidelines.

    Returns dict with keys: title_curiosity, title_direct, title_question, description, hashtags.
    """
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    user_msg = f"TRANSCRIPT:\n{transcript_text[:2000]}\n\n"
    if campaign_rules:
        user_msg += f"CAMPAIGN RULES:\n{campaign_rules}\n\n"
    user_msg += "Return JSON."

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
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
    result = json.loads(raw)

    return {
        "title_curiosity": result.get("title_curiosity", ""),
        "title_direct": result.get("title_direct", ""),
        "title_question": result.get("title_question", ""),
        "description": result.get("description", ""),
        "hashtags": result.get("hashtags", ""),
    }
