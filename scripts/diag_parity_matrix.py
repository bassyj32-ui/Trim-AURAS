"""Route-parity confirmation matrix.

Uploads the SAME source video 4x with the new upload Form fields:
  control   -> no new fields (old-style client; must still get 202 not 422)
  burn_on   -> burn_captions=true
  trim_on   -> trim_silence=true
  prefh_480 -> preferred_height=480

Each row is polled to a terminal state, then per-job evidence is captured:
  - POST status + returned job_id (202 required; 422 = param regression)
  - full /api/jobs/{id}/diag (PIPELINE_START shows what the worker read from
    the DB: burn_captions + preferred_height persisted end-to-end)
  - /api/jobs/{id} clip rows (clip ids, declared durations)
  - clip_*.stderr.log from the Modal Volume (header line = full filter_complex
    -> proves subtitles=/[condv] chains reached the real ffmpeg invocation)

Rows run SEQUENTIALLY so each job's stderr logs can be captured before the
next job's render overwrites diag/clip_0..2.stderr.log.

Writes tmp/parity_matrix.json
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos" / "v01_small_h264_720p_40s.mp4"
OUT = ROOT / "tmp" / "parity_matrix.json"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

ROWS = [
    {"label": "control", "data": {"max_clips": "3"}},
    {"label": "burn_on", "data": {"max_clips": "3", "burn_captions": "true"}},
    {"label": "trim_on", "data": {"max_clips": "3", "trim_silence": "true"}},
    {"label": "prefh_480", "data": {"max_clips": "3", "preferred_height": "480"}},
]


def modal_volume_cat(path: str) -> str:
    r = subprocess.run(
        ["python", "-m", "modal", "volume", "cat", "trimaura-data", path],
        capture_output=True, text=True, env=ENV, timeout=180,
    )
    return r.stdout


def poll(jid: int, timeout_s: int = 1800) -> dict:
    c = httpx.Client(timeout=30, base_url=BASE)
    t0 = time.time()
    last = ""
    d = {}
    while time.time() - t0 < timeout_s:
        try:
            d = c.get(f"/api/jobs/{jid}/diag").json()
            st = d.get("status")
        except Exception as e:
            st = f"ERR:{str(e)[:60]}"
        if st != last:
            print(f"  [{jid}] t={time.time()-t0:.0f}s status={st}", flush=True)
            last = st
            if st in ("COMPLETED", "FAILED"):
                return d
        time.sleep(10)
    return {"status": "TIMEOUT", "last_diag": d}


def main() -> None:
    if not VID.exists():
        print(f"MISSING {VID}")
        sys.exit(1)
    results = []
    for row in ROWS:
        print(f"== row: {row['label']} data={row['data']} ==", flush=True)
        with httpx.Client(timeout=1800) as c:
            with VID.open("rb") as fh:
                r = c.post(
                    f"{BASE}/api/jobs/upload",
                    files={"file": (VID.name, fh, "video/mp4")},
                    data={"template_id": "auto", **row["data"]},
                )
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:300]}
        print(f"  POST status={r.status_code} body={body}", flush=True)
        entry = {**row, "post_status": r.status_code, "body": body}
        if r.status_code != 202 or "job_id" not in body:
            results.append(entry)
            OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
            continue
        jid = body["job_id"]
        diag = poll(jid)
        try:
            job = httpx.get(f"{BASE}/api/jobs/{jid}", timeout=30).json()
        except Exception as e:
            job = {"err": str(e)}
        # Capture stderr logs BEFORE the next row's render overwrites them.
        stderr = {}
        for idx in range(0, 5):
            try:
                txt = modal_volume_cat(f"diag/clip_{idx}.stderr.log")
                if txt.strip():
                    stderr[f"clip_{idx}"] = txt[:6000]
            except Exception as e:
                stderr[f"clip_{idx}"] = f"ERR {str(e)[:120]}"
        entry.update({"job_id": jid, "status": diag.get("status"),
                      "diag": diag, "job": job, "stderr": stderr})
        results.append(entry)
        OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
        print(f"  recorded {jid} -> {OUT}", flush=True)
    print("ALL DONE")


if __name__ == "__main__":
    main()
