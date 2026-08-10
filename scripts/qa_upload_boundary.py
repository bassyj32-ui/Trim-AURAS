"""Upload boundary sweep: 40/45/47/49/50/60 MB against the deployed API.

For each size records: exact size, HTTP status, response headers (attempt
token / location), body, upload duration, and whether a Job row was created
(FastAPI route completes only AFTER the full body is received and written).

Pass --follow to also retry 303s with follow_redirects=True (what a
redirect-aware client would do).
"""
import argparse
import json
import time
from pathlib import Path
import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "tmp" / "qa"
SRC = ROOT / "tmp" / "diag" / "videos" / "v08_large_400mb_40s.mp4"
OUT = QA / "upload_boundary.jsonl"

p = argparse.ArgumentParser()
p.add_argument("--follow", action="store_true")
p.add_argument("--sizes", default="40,45,47,49,50,60")
args = p.parse_args()

sizes = [int(s) for s in args.sizes.split(",") if s.strip()]


def job_ids(c: httpx.Client) -> set:
    try:
        r = c.get(f"{BASE}/api/jobs", timeout=30)
        data = r.json()
        items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
        return {j.get("job_id") or j.get("id") for j in items}
    except Exception:
        return set()


def truncate(mb: int) -> Path:
    dst = QA / f"bnd_{mb}mb.mp4"
    with SRC.open("rb") as f:
        dst.write_bytes(f.read(mb * 1024 * 1024))
    return dst


def main():
    with httpx.Client(timeout=(30, 600)) as c:
        before = job_ids(c)
        for mb in sizes:
            dst = truncate(mb)
            size_bytes = dst.stat().st_size
            row = {"size_mb": mb, "size_bytes": size_bytes, "follow": args.follow}
            t0 = time.time()
            try:
                with dst.open("rb") as fh:
                    r = c.post(
                        f"{BASE}/api/jobs/upload",
                        files={"file": (dst.name, fh, "application/octet-stream")},
                        data={"template_id": "auto", "max_clips": "1"},
                        follow_redirects=args.follow,
                    )
                elapsed = time.time() - t0
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                row.update({
                    "status": r.status_code,
                    "attempt_token": hdrs.get("__modal_attempt_token", None),
                    "location": hdrs.get("location", None),
                    "body": r.text[:200],
                    "elapsed_s": round(elapsed, 1),
                })
            except httpx.ReadError as e:
                row.update({"status": "CONN_RESET", "err": f"{type(e).__name__}: {e}",
                            "elapsed_s": round(time.time() - t0, 1)})
            except Exception as e:
                row.update({"status": "EXC", "err": f"{type(e).__name__}: {e}",
                            "elapsed_s": round(time.time() - t0, 1)})
            # Job created? route completes only after full body received+written.
            after = job_ids(c)
            row["job_created"] = sorted(after - before) if after != before else []
            before = after
            line = json.dumps(row)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            print(line, flush=True)


if __name__ == "__main__":
    main()
