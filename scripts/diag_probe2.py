"""Probe diag for jobs 86/88 -> tmp/probe2.json"""
import json
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
OUT = Path(__file__).resolve().parent.parent / "tmp" / "probe2.json"

c = httpx.Client(timeout=30, base_url=BASE)
out = {}
for jid in (86, 88):
    r = c.get(f"/api/jobs/{jid}/diag")
    if r.status_code != 200:
        out[str(jid)] = {"http": r.status_code}
        continue
    d = r.json()
    out[str(jid)] = {
        "status": d.get("status"),
        "stages": d.get("stages"),
        "error": d.get("error"),
        "clip_stderr_logs": d.get("clip_stderr_logs"),
    }
OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("probe2 ok")
