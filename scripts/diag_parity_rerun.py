"""Re-run burn/trim rows with deterministic stderr-log capture.

Job 96 (trim_on) FAILED pre-fix (audio [conda] chains appended after the
filter_complex join); job 95's stderr logs were overwritten before capture.
This re-runs:
  burn2 -> burn_captions=true   (capture filter evidence: subtitles=)
  trim2 -> trim_silence=true    (capture filter evidence: [condv]/[conda])

Each row: upload -> poll to terminal -> IMMEDIATELY pull diag/clip_*.stderr.log
from the Volume via `modal volume get` (the correct CLI; `volume cat` does
not exist) so the next job's render can't overwrite it.

Writes tmp/parity_rerun.json (same schema as parity_matrix.json rows).
"""
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos" / "v01_small_h264_720p_40s.mp4"
OUT = ROOT / "tmp" / "parity_rerun.json"
STDERR_DIR = ROOT / "tmp" / "parity_stderr"
STDERR_DIR.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

ROWS = [
    {"label": "burn2", "data": {"max_clips": "3", "burn_captions": "true"}},
    {"label": "trim2", "data": {"max_clips": "3", "trim_silence": "true"}},
]


def volume_get(remote: str, local: Path) -> str:
    r = subprocess.run(
        ["python", "-m", "modal", "volume", "get", "trimaura-data", remote, str(local)],
        capture_output=True, text=True, env=ENV, timeout=240,
    )
    if local.exists():
        txt = local.read_text(encoding="utf-8", errors="replace")
        return txt[:6000]
    return f"ERR rc={r.returncode} {r.stderr[:200]}"


def capture_stderr(jid: int, label: str) -> dict:
    """Pull diag/clip_0..2.stderr.log into tmp/parity_stderr immediately."""
    out = {}
    for idx in range(3):
        local = STDERR_DIR / f"{label}_clip{idx}.stderr.log"
        txt = volume_get(f"diag/clip_{idx}.stderr.log", local)
        if txt.strip():
            out[f"clip_{idx}"] = txt
    return out


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
    results = []
    for row in ROWS:
        print(f"== row: {row['label']} {row['data']} ==", flush=True)
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
        stderr = capture_stderr(jid, row["label"])
        entry.update({"job_id": jid, "status": diag.get("status"),
                      "diag": diag, "job": job, "stderr": stderr})
        results.append(entry)
        OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
        print(f"  recorded {jid} stderr_files={list(stderr.keys())}", flush=True)
    print("ALL DONE")


if __name__ == "__main__":
    main()
