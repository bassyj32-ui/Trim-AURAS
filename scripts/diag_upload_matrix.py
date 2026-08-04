"""Upload-path test runner for the PART 2 matrix.

Uploads a local file via POST /api/jobs/upload, polls to terminal, pulls the
diag breakdown, and appends one row to tmp/diag_results.jsonl in the same
format as the URL-submitted jobs 77-82.

Usage:
  python scripts/diag_upload_matrix.py <file> <label> [--template T] [--max-clips N]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
RESULTS = ROOT / "tmp" / "diag_results.jsonl"
POLL_SECS = 20
TIMEOUT_S = 5400  # 90 min cap per row (render hangs are the point)


def record(row: dict):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
    print(f"[record] job {row['job_id']} -> {RESULTS}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("label")
    ap.add_argument("--template", default="auto")
    ap.add_argument("--max-clips", type=int, default=3)
    args = ap.parse_args()

    fpath = Path(args.file)
    size_mb = round(fpath.stat().st_size / 1048576, 1)

    t0 = time.monotonic()
    log = ROOT / "tmp" / "diag_upload_progress.txt"
    with httpx.Client(timeout=1200) as c:
        # 1) Upload (retry on connection drops — sandbox network is flaky)
        for attempt in range(1, 4):
            try:
                with fpath.open("rb") as fh:
                    resp = c.post(
                        f"{BASE}/api/jobs/upload",
                        files={"file": (fpath.name, fh, "video/mp4")},
                        data={"template_id": args.template, "max_clips": str(args.max_clips)},
                    )
                break
            except httpx.HTTPError as e:
                log.write_text(f"upload attempt {attempt} failed: {e}\n", encoding="utf-8")
                print(f"[upload] attempt {attempt} failed: {e}")
                if attempt == 3:
                    record({"job_id": None, "source_type": "upload", "video": fpath.name,
                            "chars": args.label, "size_mb": size_mb, "network": "ide_wifi",
                            "backgrounded": False, "outcome": "upload_transport_error",
                            "failure_stage": "UPLOAD", "error": str(e)[:300], "stages": {},
                            "total_s": round(time.monotonic() - t0, 1)})
                    return 1

        print(f"[upload] HTTP {resp.status_code} | {resp.text[:200]}")
        if resp.status_code >= 400:
            record({"job_id": None, "source_type": "upload", "video": fpath.name,
                    "chars": args.label, "size_mb": size_mb, "network": "ide_wifi",
                    "backgrounded": False, "outcome": "upload_failed",
                    "failure_stage": "UPLOAD", "error": resp.text[:300], "stages": {},
                    "total_s": round(time.monotonic() - t0, 1)})
            return 1
        job_id = resp.json().get("job_id")

        # 2) Poll
        status, error = "PENDING", ""
        elapsed = 0.0
        while elapsed < TIMEOUT_S:
            time.sleep(POLL_SECS)
            elapsed = time.monotonic() - t0
            try:
                p = c.get(f"{BASE}/api/jobs/{job_id}/poll").json()
            except httpx.HTTPError as e:
                print(f"[poll] error at {elapsed:.0f}s: {e}")
                continue
            status = p.get("status", "?")
            error = p.get("error") or ""
            print(f"[poll] t={elapsed:.0f}s job={job_id} {status} {('err=' + error[:120]) if error else ''}")
            if status in ("COMPLETED", "FAILED"):
                break
        else:
            status = "STUCK"

        # 3) Diag breakdown
        stages = {}
        try:
            d = c.get(f"{BASE}/api/jobs/{job_id}/diag").json()
            stages = d.get("stages", {})
            if not stages:
                evs = d.get("events", [])
                enters = [(e.get("stage"), e.get("event")) for e in evs
                          if e.get("event") in ("STAGE_ENTER", "STAGE_EXIT")]
        except Exception as e:
            print(f"[diag] error: {e}")

        # 4) Failure stage: first stage entered but never exited, else from error
        failure_stage = None
        if status == "FAILED":
            for name, s in stages.items():
                if not s.get("ok"):
                    failure_stage = name
                    break
            if not failure_stage:
                # last STAGE_ENTER without exit
                for ev in reversed(d.get("events", []) if 'd' in dir() else []):
                    if ev.get("event") == "STAGE_ENTER":
                        failure_stage = ev.get("stage")
                        break
                failure_stage = failure_stage or "UNKNOWN"

        row = {
            "job_id": job_id,
            "source_type": "upload",
            "video": fpath.name,
            "chars": args.label,
            "size_mb": size_mb,
            "network": "ide_wifi",
            "backgrounded": False,
            "outcome": "completed" if status == "COMPLETED" else
                       ("failed" if status == "FAILED" else "stuck"),
            "failure_stage": failure_stage,
            "error": error[:300],
            "stages": stages,
            "total_s": round(time.monotonic() - t0, 1),
        }
        record(row)
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0 if status == "COMPLETED" else 2


if __name__ == "__main__":
    sys.exit(main())
