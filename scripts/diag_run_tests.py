"""TrimAURA diag suite — submit + poll + record jobs through the live API.

Usage:
  python scripts/diag_run_tests.py upload          # upload-path rows (IDE, wifi)
  python scripts/diag_run_tests.py url             # URL-path rows (GDrive / Frame.io)
  python scripts/diag_run_tests.py rerun <job_id>  # re-submit the SAME source as job <id>
  python scripts/diag_run_tests.py report          # aggregate tmp/diag_results.jsonl

Every result row captures: source_type, video/url, characteristics, network,
backgrounded, outcome, failure_stage (from /api/jobs/{id}/diag), stage
durations, and the error. Rows append to tmp/diag_results.jsonl.
"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "tmp" / "diag" / "videos"
RESULTS = ROOT / "tmp" / "diag_results.jsonl"

UPLOAD_ROWS = [  # order matters: small->large so the big uploads run last
    {"video": "v01_small_h264_720p_40s.mp4"},
    {"video": "v02_medium_h264_1080p_6min.mp4"},
    {"video": "v03_hevc_4k_20s.mp4"},
    {"video": "v04_mov_h264_916_60s.mov"},
    {"video": "v05_webm_vp9_720p_30s_silent.webm"},
    {"video": "v06_music_720p_30s.mp4"},
    {"video": "v07_long_30min_360p_silent.mp4"},
    {"video": "v08_large_400mb_40s.mp4"},
]

URL_ROWS = [
    {"url": "https://drive.google.com/file/d/1C0ewiFev8kfwFcXjd9kdux5bF5nFsHu_/view?usp=drivesdk",
     "label": "gdrive_link"},
    {"url": "https://next.frame.io/share/a969e3a9-c761-442a-8bfb-17a06b38174c/",
     "label": "frameio_link"},
]


def manifest() -> dict:
    p = ROOT / "tmp" / "diag_matrix.json"
    if p.exists():
        return {m["video"]: m for m in json.loads(p.read_text(encoding="utf-8"))}
    return {}


def record(row: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(f"  >> recorded job {row.get('job_id')} -> {row['outcome']} "
          f"({row.get('failure_stage') or 'n/a'})")


def poll_until_terminal(client: httpx.Client, job_id: int, timeout_s: int = 45 * 60) -> dict:
    """Poll /poll then pull /diag. Returns merged result dict (no network on failure)."""
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        r = client.get(f"{BASE}/api/jobs/{job_id}/poll", timeout=30)
        r.raise_for_status()
        data = r.json()
        key = f"{data['status']} {data.get('progress')}%"
        if key != last:
            print(f"    [{time.strftime('%H:%M:%S')}] {key}")
            last = key
        if data["status"] in ("COMPLETED", "FAILED"):
            try:
                diag = client.get(f"{BASE}/api/jobs/{job_id}/diag", timeout=30).json()
            except Exception:
                diag = {}
            return {"status": data["status"], "error": data.get("error"), "diag": diag}
        time.sleep(15)
    return {"status": "STUCK", "error": "poll timeout 45min", "diag": {}}


def submit_upload(client: httpx.Client, path: Path) -> httpx.Response:
    size_mb = round(path.stat().st_size / 1_048_576, 1)
    t0 = time.time()
    with path.open("rb") as f:
        r = client.post(
            f"{BASE}/api/jobs/upload",
            files={"file": (path.name, f)},
            data={"template_id": "auto", "max_clips": "3", "campaign_rules": ""},
            timeout=httpx.Timeout(3600.0, connect=30.0),
        )
    dur = round(time.time() - t0, 1)
    print(f"  upload {path.name} ({size_mb}MB) -> HTTP {r.status_code} in {dur}s")
    return r


def run_upload_row(client: httpx.Client, video: str, man: dict) -> None:
    path = VID / video
    if not path.exists():
        print(f"  SKIP {video} (missing)")
        return
    meta = man.get(video, {})
    r = submit_upload(client, path)
    if r.status_code != 200 and r.status_code != 202:
        record({
            "job_id": None, "source_type": "upload", "video": video,
            "url": None, "chars": meta.get("chars", ""), "size_mb": meta.get("size_mb"),
            "network": "ide_wifi", "backgrounded": False, "outcome": "submit_failed",
            "failure_stage": "UPLOAD_SUBMIT", "error": r.text[:300], "stages": {}, "total_s": None,
        })
        return
    data = r.json()
    job_id = data.get("job_id")
    if not job_id:
        record({"job_id": None, "source_type": "upload", "video": video, "url": None,
                "chars": meta.get("chars", ""), "size_mb": meta.get("size_mb"),
                "network": "ide_wifi", "backgrounded": False, "outcome": "submit_failed",
                "failure_stage": "UPLOAD_SUBMIT", "error": f"no job_id in {data}", "stages": {}, "total_s": None})
        return
    print(f"  job {job_id} submitted for {video}")
    res = poll_until_terminal(client, job_id)
    record({
        "job_id": job_id, "source_type": "upload", "video": video, "url": None,
        "chars": meta.get("chars", ""), "size_mb": meta.get("size_mb"),
        "network": "ide_wifi", "backgrounded": False,
        "outcome": res["status"].lower(), "failure_stage": failure_stage(res),
        "error": (res.get("error") or "")[:500], "stages": stage_summary(res), "total_s": None,
    })


def run_url_row(client: httpx.Client, url: str, label: str) -> None:
    t0 = time.time()
    r = client.post(f"{BASE}/api/jobs", json={
        "title": label, "source_url": url, "template_id": "auto",
        "max_clips": 3, "preferred_height": 720, "burn_captions": False, "trim_silence": False,
    }, timeout=60)
    print(f"  POST /api/jobs {label} -> HTTP {r.status_code}")
    if r.status_code >= 400:
        record({"job_id": None, "source_type": "url", "video": None, "url": url,
                "chars": label, "size_mb": None, "network": "ide_wifi", "backgrounded": False,
                "outcome": "submit_failed", "failure_stage": "JOB_CREATE",
                "error": r.text[:300], "stages": {}, "total_s": None})
        return
    job_id = r.json().get("job_id")
    res = poll_until_terminal(client, job_id)
    record({
        "job_id": job_id, "source_type": "url", "video": None, "url": url,
        "chars": label, "size_mb": None, "network": "ide_wifi", "backgrounded": False,
        "outcome": res["status"].lower(), "failure_stage": failure_stage(res),
        "error": (res.get("error") or "")[:500], "stages": stage_summary(res), "total_s": None,
    })


def failure_stage(res: dict) -> str | None:
    diag = res.get("diag") or {}
    for ev in diag.get("events", []):
        if ev.get("event") == "FAILED":
            return ev.get("stage") or "UNKNOWN"
    return None


def stage_summary(res: dict) -> dict:
    diag = res.get("diag") or {}
    return {k: {kk: vv for kk, vv in v.items() if kk != "entered_at"}
            for k, v in (diag.get("stages") or {}).items()}


def rerun(job_id: int) -> None:
    """Re-submit the same source as an existing job (IDE comparison column)."""
    prev = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    row = next((r for r in prev if r.get("job_id") == job_id), None)
    if not row:
        print(f"job {job_id} not found in results")
        return
    with httpx.Client() as client:
        if row.get("source_type") == "upload" and row.get("video"):
            run_upload_row(client, row["video"], manifest())
        elif row.get("url"):
            run_url_row(client, row["url"], row.get("chars") or "rerun")
        else:
            print("cannot determine source for", job_id)


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
    total = len(rows)
    by_outcome: dict[str, int] = {}
    for r in rows:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
    print(f"total rows: {total} | {by_outcome}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    man = manifest()
    if cmd == "upload":
        with httpx.Client() as client:
            for v in UPLOAD_ROWS:
                run_upload_row(client, v["video"], man)
    elif cmd == "url":
        with httpx.Client() as client:
            for u in URL_ROWS:
                run_url_row(client, u["url"], u["label"])
    elif cmd == "rerun":
        rerun(int(sys.argv[2]))
    elif cmd == "report":
        report()
    else:
        print(__doc__)
