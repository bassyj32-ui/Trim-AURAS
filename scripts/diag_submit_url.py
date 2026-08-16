"""Submit a URL job via POST /api/jobs -> tmp/submitted_url_job.json"""
import json
import sys
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
OUT = Path(__file__).resolve().parent.parent / "tmp" / "submitted_url_job.json"

title = sys.argv[1]
url = sys.argv[2]
template_id = sys.argv[3] if len(sys.argv) > 3 else "auto"

c = httpx.Client(timeout=120, base_url=BASE)
try:
    r = c.post("/api/jobs", json={
        "title": title, "source_url": url,
        "template_id": template_id, "max_clips": 3,
    })
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:300]}
    OUT.write_text(json.dumps({"http": r.status_code, "body": body}, indent=1), encoding="utf-8")
    print(f"{r.status_code} {body}", flush=True)
except Exception as e:
    OUT.write_text(json.dumps({"http": "EXC", "body": str(e)[:300]}, indent=1), encoding="utf-8")
    print(f"EXC {str(e)[:200]}", flush=True)
