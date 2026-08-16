"""QA concurrency test (x1.md §17).

Batch 1: 3 simultaneous uploads of DIFFERENT sources (v01 speech H264 MP4,
         v06 music MP4, v04 portrait MOV).
Batch 2: 5 simultaneous mixed uploads (v01, v02, v03, v04, v06).

All are POSTed back-to-back BEFORE polling, then polled to terminal in
parallel. Records outcome, stage durations, failure stage, and whether
resources contended (Modal errors / long stage times).

Usage:
  python scripts/qa_concurrency.py --batch 1
"""
import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos"
OUT = ROOT / "tmp" / "qa" / "concurrency.jsonl"
POLL_S = 10
TIMEOUT_S = 5400

BATCHES = {
    1: ["v01_small_h264_720p_40s.mp4", "v06_music_720p_30s.mp4", "v04_mov_h264_916_60s.mov"],
    2: ["v01_small_h264_720p_40s.mp4", "v03_hevc_4k_20s.mp4", "v04_mov_h264_916_60s.mov",
        "v05_webm_vp9_720p_30s_silent.webm", "gm_sil2_src.mp4"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1)
    args = ap.parse_args()
    files = BATCHES[args.batch]
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"== concurrency batch {args.batch}: {files} ==", flush=True)
    with httpx.Client(timeout=3600) as c:
        # 1) Submit ALL jobs back-to-back
        jobs = []
        t_submit = time.time()
        for fname in files:
            fpath = VID / fname
            with fpath.open("rb") as fh:
                r = c.post(f"{BASE}/api/jobs/upload",
                           files={"file": (fname, fh, "application/octet-stream")},
                           data={"template_id": "auto", "max_clips": "3"})
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:200]}
            jobs.append({"file": fname, "post_status": r.status_code, "body": body})
            print(f"  POST {fname} -> {r.status_code} {body}", flush=True)
        submit_s = round(time.time() - t_submit, 1)
        print(f"  all {len(jobs)} submitted in {submit_s}s", flush=True)

        # 2) Poll all in parallel (round-robin)
        t0 = time.time()
        done = {i: False for i in range(len(jobs))}
        last_st = {i: "" for i in range(len(jobs))}
        while not all(done.values()) and time.time() - t0 < TIMEOUT_S:
            time.sleep(POLL_S)
            for i, j in enumerate(jobs):
                if done[i]:
                    continue
                jid = j["body"].get("job_id")
                if not jid:
                    done[i] = True
                    continue
                try:
                    p = c.get(f"{BASE}/api/jobs/{jid}/poll").json()
                    st = p.get("status")
                except Exception as e:
                    st = f"ERR:{str(e)[:60]}"
                if st != last_st[i]:
                    print(f"  [{j['file']}/{jid}] t={time.time()-t0:.0f}s {st}", flush=True)
                    last_st[i] = st
                if st in ("COMPLETED", "FAILED"):
                    d = {}
                    try:
                        d = c.get(f"{BASE}/api/jobs/{jid}/diag").json()
                    except Exception:
                        pass
                    job = {}
                    try:
                        job = c.get(f"{BASE}/api/jobs/{jid}").json()
                    except Exception:
                        pass
                    row = {
                        "batch": args.batch, "file": j["file"], "job_id": jid,
                        "post_status": j["post_status"], "terminal": st,
                        "error": p.get("error"),
                        "elapsed_s": round(time.time() - t0, 1),
                        "stages": d.get("stages", {}),
                        "events": d.get("events", []),
                        "clips_count": len(job.get("clips", [])),
                    }
                    with OUT.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, default=str) + "\n")
                    print(f"  [done] {j['file']} jid={jid} {st}", flush=True)
                    done[i] = True

    print("CONCURRENCY DONE", flush=True)


if __name__ == "__main__":
    main()
