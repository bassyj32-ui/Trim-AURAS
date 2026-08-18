"""Final validation: 60MB and 70MB WITH follow_redirects=True (the retry a
fixed frontend would do). Records status + job created + elapsed."""
import json
import time
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "tmp" / "qa"
SRC = ROOT / "tmp" / "diag" / "videos" / "v08_large_400mb_40s.mp4"
OUT = QA / "upload_boundary3.jsonl"
OUT.unlink(missing_ok=True)


def job_ids(c: httpx.Client) -> set:
    r = c.get(f"{BASE}/api/jobs", timeout=30)
    data = r.json()
    items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
    return {j.get("job_id") or j.get("id") for j in items}


def main():
    with httpx.Client(timeout=(30, 900)) as c:
        for mb in (60, 70):
            dst = QA / f"bnd3_{mb}mb.mp4"
            with SRC.open("rb") as f:
                dst.write_bytes(f.read(mb * 1024 * 1024))
            before = job_ids(c)
            t0 = time.time()
            row = {"test": f"{mb}MB follow=True"}
            try:
                with dst.open("rb") as fh:
                    r = c.post(f"{BASE}/api/jobs/upload",
                               files={"file": (dst.name, fh, "application/octet-stream")},
                               data={"template_id": "auto", "max_clips": "1"},
                               follow_redirects=True)
                after = job_ids(c)
                row.update({"status": r.status_code, "body": r.text[:160],
                            "elapsed_s": round(time.time() - t0, 1),
                            "jobs_created": sorted(after - before)})
            except Exception as e:
                row.update({"exc": f"{type(e).__name__}: {e}",
                            "elapsed_s": round(time.time() - t0, 1)})
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
