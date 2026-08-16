"""QA generate-more test (x1.md §20).

On a completed speech job (default: the m01 baseline job 109, overridable):
  1. snapshot clips before
  2. POST /api/jobs/{jid}/generate-more count=3
  3. poll to terminal (job-level diag status; generate-more runs async)
  4. snapshot clips after; verify: new clips exist, no duplicate windows,
     no corrupted clips (download + ffprobe), job still COMPLETED
Usage:
  python scripts/qa_generate_more.py [--job 109] [--count 3]
"""
import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
CLIPS = ROOT / "tmp" / "qa" / "clips"
POLL_S = 15
TIMEOUT_S = 2400


def probe(path: Path) -> dict:
    import subprocess
    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {"error": r.stderr[-200:]}
    d = json.loads(r.stdout or "{}")
    v = None
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            v = s
            break
    fmt = d.get("format", {})
    return {"duration": round(float(fmt.get("duration", 0)), 3),
            "size": int(fmt.get("size", 0)),
            "vcodec": (v or {}).get("codec_name"),
            "w": (v or {}).get("width"), "h": (v or {}).get("height")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=int, default=109)
    ap.add_argument("--count", type=int, default=3)
    args = ap.parse_args()
    CLIPS.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(timeout=600, base_url=BASE)

    def get_job(jid):
        return c.get(f"/api/jobs/{jid}").json()

    before = get_job(args.job)
    windows_before = {(cl["start_time"], cl["end_time"]) for cl in before.get("clips", [])}
    print(f"job {args.job} status={before.get('status')} clips_before={len(before.get('clips', []))}", flush=True)

    r = c.post(f"/api/jobs/{args.job}/generate-more", json={"count": args.count})
    print(f"generate-more POST {r.status_code} {r.text[:200]}", flush=True)

    t0 = time.time()
    while time.time() - t0 < TIMEOUT_S:
        time.sleep(POLL_S)
        j = get_job(args.job)
        new_windows = {(cl["start_time"], cl["end_time"]) for cl in j.get("clips", [])}
        added = new_windows - windows_before
        print(f"  t={time.time()-t0:.0f}s status={j.get('status')} clips={len(j.get('clips', []))} added={len(added)}", flush=True)
        if len(j.get("clips", [])) > len(before.get("clips", [])) and len(added) > 0:
            # wait one more cycle for the async render to finish publishing all
            time.sleep(POLL_S)
            j = get_job(args.job)
            break
        if time.time() - t0 > 60 and j.get("status") == "FAILED":
            break

    after = get_job(args.job)
    windows_after = {(cl["start_time"], cl["end_time"]) for cl in after.get("clips", [])}
    added = windows_after - windows_before
    removed = windows_before - windows_after
    dups = [cl for cl in after.get("clips", [])
            if sum(1 for x in after.get("clips", [])
                   if x["start_time"] == cl["start_time"] and x["end_time"] == cl["end_time"]) > 1]

    new_clips = [cl for cl in after.get("clips", [])
                 if (cl["start_time"], cl["end_time"]) in added]
    probes = {}
    for cl in new_clips:
        dest = CLIPS / f"gm_j{args.job}_c{cl['clip_id']}.mp4"
        dr = c.get(f"/api/clips/{cl['clip_id']}/download")
        if dr.status_code == 200 and dr.headers.get("content-type", "").startswith("video/"):
            dest.write_bytes(dr.content)
            probes[cl["clip_id"]] = probe(dest)
        else:
            probes[cl["clip_id"]] = {"download": f"http{dr.status_code}:{dr.text[:120]}"}

    result = {
        "job_id": args.job,
        "status_before": before.get("status"),
        "status_after": after.get("status"),
        "clips_before": len(before.get("clips", [])),
        "clips_after": len(after.get("clips", [])),
        "added_windows": sorted([[a, b] for a, b in added]),
        "removed_windows": sorted([[a, b] for a, b in removed]),
        "duplicate_windows_count": len(dups),
        "new_clip_probes": probes,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (ROOT / "tmp" / "qa" / "generate_more.json").write_text(
        json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, indent=1, default=str), flush=True)


if __name__ == "__main__":
    main()
