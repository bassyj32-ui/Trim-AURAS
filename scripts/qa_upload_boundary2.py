"""Confirmatory pass:
1. Verify jobs 145-149 (incl. the '303 but created' jobs) reached COMPLETED.
2. POST 45MB with follow_redirects=True  -> does the Modal attempt-token retry
   succeed for a redirect-following client, and does it duplicate the job?
3. POST 60MB and 70MB follow_redirects=False -> 202 / 303 / reset?
"""
import json
import time
from pathlib import Path
import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "tmp" / "qa"
SRC = ROOT / "tmp" / "diag" / "videos" / "v08_large_400mb_40s.mp4"
OUT = QA / "upload_boundary2.jsonl"
OUT.unlink(missing_ok=True)


def job_ids(c: httpx.Client) -> set:
    r = c.get(f"{BASE}/api/jobs", timeout=30)
    data = r.json()
    items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
    return {j.get("job_id") or j.get("id") for j in items}


def job_status(c: httpx.Client, jid: int) -> str:
    try:
        r = c.get(f"{BASE}/api/jobs/{jid}", timeout=30)
        return f"{r.status_code}:{r.json().get('status', '?')}"
    except Exception as e:
        return f"ERR {e}"


def truncate(mb: int) -> Path:
    dst = QA / f"bnd2_{mb}mb.mp4"
    with SRC.open("rb") as f:
        dst.write_bytes(f.read(mb * 1024 * 1024))
    return dst


def rec(row: dict):
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


def main():
    with httpx.Client(timeout=(30, 900)) as c:
        # 1. status of the boundary-sweep jobs (145-149)
        for jid in (145, 146, 147, 148, 149):
            rec({"check": f"job_status_{jid}", "value": job_status(c, jid)})
        rec({"check": "sleep_for_workers", "value": "start"})
        time.sleep(60)
        for jid in (146, 147):
            rec({"check": f"job_status_{jid}_late", "value": job_status(c, jid)})

        # 2. 45MB with redirect-follow (browser-like)
        dst = truncate(45)
        before = job_ids(c)
        t0 = time.time()
        try:
            with dst.open("rb") as fh:
                r = c.post(f"{BASE}/api/jobs/upload",
                           files={"file": (dst.name, fh, "application/octet-stream")},
                           data={"template_id": "auto", "max_clips": "1"},
                           follow_redirects=True)
            after = job_ids(c)
            rec({"test": "45MB follow=True", "status": r.status_code,
                 "body": r.text[:200], "elapsed_s": round(time.time() - t0, 1),
                 "jobs_created": sorted(after - before)})
        except Exception as e:
            rec({"test": "45MB follow=True", "exc": f"{type(e).__name__}: {e}",
                 "elapsed_s": round(time.time() - t0, 1)})

        # 3. 60MB, no follow (70MB skipped: 68MB conn-reset already evidenced)
        for mb in (60,):
            dst = truncate(mb)
            before = job_ids(c)
            t0 = time.time()
            try:
                with dst.open("rb") as fh:
                    r = c.post(f"{BASE}/api/jobs/upload",
                               files={"file": (dst.name, fh, "application/octet-stream")},
                               data={"template_id": "auto", "max_clips": "1"},
                               follow_redirects=False)
                after = job_ids(c)
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                rec({"test": f"{mb}MB follow=False", "status": r.status_code,
                     "location": (hdrs.get("location") or "")[:120],
                     "body": r.text[:120], "elapsed_s": round(time.time() - t0, 1),
                     "jobs_created": sorted(after - before)})
            except Exception as e:
                rec({"test": f"{mb}MB follow=False", "exc": f"{type(e).__name__}: {e}",
                     "elapsed_s": round(time.time() - t0, 1)})


if __name__ == "__main__":
    main()
