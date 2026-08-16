"""Dump current diag state for the test jobs to tmp/diag_summary.json."""
import json
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
JOBS = [77, 78, 79, 80, 81, 82]
OUT = ROOT / "tmp" / "diag_summary.json"


def main():
    summary = {}
    with httpx.Client(timeout=30) as c:
        lst = c.get(f"{BASE}/api/jobs").json()
        for j in lst[:10]:
            if j["job_id"] in JOBS:
                summary[str(j["job_id"])] = {
                    "title": j["title"], "status": j["status"],
                    "template": j.get("template_id"), "clips": j.get("clips_count"),
                }
        for jid in JOBS:
            try:
                d = c.get(f"{BASE}/api/jobs/{jid}/diag").json()
                evs = d.get("events", [])
                summary[str(jid)]["events"] = [
                    {k: e[k] for k in ("event", "stage", "duration_s",
                                       "clip_candidates", "face_track_samples",
                                       "rendered", "text_len", "error")
                     if k in e} for e in evs
                ]
                summary[str(jid)]["stages"] = d.get("stages", {})
            except Exception as e:
                summary[str(jid)]["diag_error"] = str(e)[:200]
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
