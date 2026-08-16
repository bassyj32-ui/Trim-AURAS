"""Detached uploader: uploads one file, writes job_id to tmp/uploaded_jobs.json.

Survives terminal flakiness. Usage: python scripts/diag_detached_upload.py <file> <label>
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
OUT = ROOT / "tmp" / "uploaded_jobs.json"

fpath = Path(sys.argv[1])
label = sys.argv[2]
template_id = sys.argv[3] if len(sys.argv) > 3 else "auto"
size_mb = round(fpath.stat().st_size / 1048576, 1)

rows = []
if OUT.exists():
    rows = json.loads(OUT.read_text(encoding="utf-8"))

try:
    with httpx.Client(timeout=1800) as c:
        with fpath.open("rb") as fh:
            r = c.post(
                f"{BASE}/api/jobs/upload",
                files={"file": (fpath.name, fh, "video/mp4")},
                data={"template_id": template_id, "max_clips": "3"},
            )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:200]}
    rows.append({"file": fpath.name, "label": label, "size_mb": size_mb,
                 "status": r.status_code, "body": body})
except Exception as e:
    rows.append({"file": fpath.name, "label": label, "size_mb": size_mb,
                 "status": "EXC", "body": str(e)[:300]})

OUT.write_text(json.dumps(rows, ensure_ascii=True, indent=1), encoding="utf-8")
print("done", fpath.name, rows[-1]["status"])
