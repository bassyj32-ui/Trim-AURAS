"""Quick probe: newest jobs + new diag rows -> tmp/probe.json"""
import json
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tmp" / "probe.json"

c = httpx.Client(timeout=30, base_url=BASE)
jobs = c.get("/api/jobs").json()
newest = [{"job_id": j["job_id"], "title": j["title"][:45], "status": j["status"]}
          for j in jobs[:8]]
rows = [json.loads(l) for l in (ROOT / "tmp" / "diag_results.jsonl").open(encoding="utf-8")]
newrows = [{"job_id": r["job_id"], "chars": r.get("chars"), "outcome": r["outcome"],
            "err": str(r.get("error"))[:100]} for r in rows if r.get("job_id", 0) >= 83]
OUT.write_text(json.dumps({"newest": newest, "newrows": newrows}, indent=1), encoding="utf-8")
print("probe ok")
