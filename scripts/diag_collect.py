"""TrimAURA diag collector — reliable poll + record against the live API.

The sandbox wrapper kills the long-running harness process, so this collector
is designed to be run as a SHORT blocking command per unit of work:

  python scripts/diag_collect.py record <job_id>          # poll to terminal, record row
  python scripts/diag_collect.py submit <url> <label>      # create URL job, poll, record
  python scripts/diag_collect.py report                    # table from diag_results.jsonl

Rows match diag_run_tests.py format and append to tmp/diag_results.jsonl.
"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "tmp" / "diag_results.jsonl"


def record(row: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(f"  >> recorded job {row.get('job_id')} -> {row['outcome']} "
          f"({row.get('failure_stage') or 'n/a'})", flush=True)


def failure_stage(res: dict) -> str | None:
    for ev in res.get("diag", {}).get("events", []):
        if ev.get("event") == "FAILED":
            return ev.get("stage") or "UNKNOWN"
    return None


def stage_summary(res: dict) -> dict:
    diag = res.get("diag") or {}
    return {k: {kk: vv for kk, vv in v.items() if kk != "entered_at"}
            for k, v in (diag.get("stages") or {}).items()}


def poll_until_terminal(client: httpx.Client, job_id: int, timeout_s: int = 45 * 60) -> dict:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        try:
            r = client.get(f"{BASE}/api/jobs/{job_id}/poll", timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    poll error (retrying): {e}", flush=True)
            time.sleep(10)
            continue
        key = f"{data['status']} {data.get('progress')}%"
        if key != last:
            print(f"    [{time.strftime('%H:%M:%S')}] {key}", flush=True)
            last = key
        if data["status"] in ("COMPLETED", "FAILED"):
            try:
                diag = client.get(f"{BASE}/api/jobs/{job_id}/diag", timeout=30).json()
            except Exception:
                diag = {}
            return {"status": data["status"], "error": data.get("error"), "diag": diag}
        time.sleep(15)
    return {"status": "STUCK", "error": "poll timeout 45min", "diag": {}}


def record_job(job_id: int, extra: dict | None = None) -> None:
    with httpx.Client() as client:
        res = poll_until_terminal(client, job_id)
        row = {"job_id": job_id, "outcome": res["status"].lower(),
               "failure_stage": failure_stage(res),
               "error": (res.get("error") or "")[:500],
               "stages": stage_summary(res), "total_s": None}
        if extra:
            row.update(extra)
        record(row)


def submit_url(url: str, label: str) -> None:
    with httpx.Client() as client:
        t0 = time.time()
        r = client.post(f"{BASE}/api/jobs", json={
            "title": label, "source_url": url, "template_id": "auto",
            "max_clips": 3, "preferred_height": 720, "burn_captions": False,
            "trim_silence": False,
        }, timeout=60)
        print(f"  POST /api/jobs {label} -> HTTP {r.status_code}", flush=True)
        if r.status_code >= 400:
            record({"job_id": None, "source_type": "url", "video": None, "url": url,
                    "chars": label, "size_mb": None, "network": "ide_wifi",
                    "backgrounded": False, "outcome": "submit_failed",
                    "failure_stage": "JOB_CREATE", "error": r.text[:300],
                    "stages": {}, "total_s": None})
            return
        job_id = r.json().get("job_id")
        print(f"  job {job_id} submitted", flush=True)
        res = poll_until_terminal(client, job_id)
        record({"job_id": job_id, "source_type": "url", "video": None, "url": url,
                "chars": label, "size_mb": None, "network": "ide_wifi",
                "backgrounded": False, "outcome": res["status"].lower(),
                "failure_stage": failure_stage(res),
                "error": (res.get("error") or "")[:500],
                "stages": stage_summary(res), "total_s": None})


def report() -> None:
    if not RESULTS.exists():
        print("no results yet")
        return
    rows = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{'job':>5} {'type':<7} {'video/url':<36} {'outcome':<14} {'stage':<16} error")
    print("-" * 120)
    for r in rows:
        j = r.get("job_id") or "-"
        vid = (r.get("video") or r.get("url") or "")[:36]
        st = r.get("failure_stage") or "-"
        err = (r.get("error") or "")[:50].replace("\n", " ")
        print(f"{j!s:>5} {r.get('source_type',''):<7} {vid:<36} {r.get('outcome',''):<14} {st:<16} {err}")
    print("-" * 120)
    print(f"total rows: {len(rows)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "record":
        record_job(int(sys.argv[2]))
    elif cmd == "submit":
        submit_url(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2])
    elif cmd == "report":
        report()
    else:
        print(__doc__)
