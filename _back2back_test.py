"""Back-to-back stress test against the live Modal backend.

Fires N jobs with the same source link back-to-back, polls them all
concurrently, and reports each job's stage timeline + final result.

Usage:
    python _back2back_test.py [N] [global_timeout_s] [source_url] [height] [max_clips] [cookies_file]
"""
import asyncio
import sys
import time

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
SOURCE = sys.argv[3] if len(sys.argv) > 3 else "https://next.frame.io/share/a969e3a9-c761-442a-8bfb-17a06b38174c/"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
GLOBAL_TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
TEMPLATE = "blurpad_v1"
MAX_CLIPS = int(sys.argv[5]) if len(sys.argv) > 5 else 3
HEIGHT = int(sys.argv[4]) if len(sys.argv) > 4 else 540  # 0 = original, 1080 = full HD
COOKIES_FILE = sys.argv[6] if len(sys.argv) > 6 else ""

COOKIES_TEXT = ""
if COOKIES_FILE:
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        COOKIES_TEXT = f.read()

TERMINAL = ("COMPLETED", "FAILED", "TIMEOUT")


async def create_job(client: httpx.AsyncClient, i: int) -> int:
    payload = {
        "title": f"Stress-{i}",
        "source_url": SOURCE,
        "template_id": TEMPLATE,
        "max_clips": MAX_CLIPS,
        "preferred_height": HEIGHT,
    }
    if COOKIES_TEXT:
        payload["cookies"] = COOKIES_TEXT
    r = await client.post(f"{BASE}/api/jobs", json=payload, timeout=60)
    data = r.json()
    if r.status_code != 202 or not data.get("job_id"):
        raise RuntimeError(f"create failed [{r.status_code}]: {data}")
    return data["job_id"]


async def watch(client: httpx.AsyncClient, job_id: int, results: dict, t0: float):
    last = None
    timeline = []
    while True:
        now = time.time() - t0
        try:
            r = await client.get(f"{BASE}/api/jobs/{job_id}/poll", timeout=30)
            d = r.json()
            status, prog, err = d.get("status"), d.get("progress", 0), d.get("error")
        except Exception as e:
            status, prog, err = f"POLL-ERR", 0, f"{type(e).__name__}: {str(e)[:80]}"
        if status != last:
            last = status
            timeline.append(f"[{now:6.0f}s] {status} {prog}%")
            suffix = f"  err={err[:140]}" if err else ""
            print(f"  job {job_id}: {status} progress={prog}%{suffix}", flush=True)
        if status in ("COMPLETED", "FAILED"):
            try:
                jr = await client.get(f"{BASE}/api/jobs/{job_id}", timeout=30)
                jd = jr.json()
                clips = len(jd.get("clips") or [])
                err = jd.get("error") or err
            except Exception as e:
                clips = -1
            results[job_id] = {
                "final": status, "elapsed": time.time() - t0, "clips": clips,
                "error": err, "timeline": timeline,
            }
            return
        if now > GLOBAL_TIMEOUT:
            results[job_id] = {
                "final": "TIMEOUT", "elapsed": now, "clips": -1,
                "error": err, "timeline": timeline,
            }
            return
        await asyncio.sleep(5)


async def main():
    print(f"=== Back-to-back stress: {N} jobs, {MAX_CLIPS} clips each, {HEIGHT}p quality ===")
    print(f"Source: {SOURCE}")
    print(f"Cookies: {'loaded (' + COOKIES_FILE + ')' if COOKIES_TEXT else 'none'}")
    async with httpx.AsyncClient(timeout=60) as c:
        ids = []
        t0 = time.time()
        for i in range(1, N + 1):
            jid = await create_job(c, i)
            ids.append(jid)
            print(f"[{time.time()-t0:5.0f}s] created job {jid}", flush=True)

        results: dict = {}
        await asyncio.gather(*[watch(c, jid, results, t0) for jid in ids])

        print("\n================= SUMMARY =================")
        all_ok = True
        for jid in ids:
            res = results.get(jid, {})
            ok = res.get("final") == "COMPLETED"
            all_ok = all_ok and ok
            print(f"job {jid}: {'OK ' if ok else 'FAIL'} final={res.get('final')} "
                  f"elapsed={res.get('elapsed', 0):.0f}s clips={res.get('clips')} "
                  f"err={str(res.get('error'))[:120]}")
            for line in res.get("timeline", []):
                print("    " + line)
        print("============================================")
        print("RESULT:", "ALL PASSED" if all_ok else "ISSUES FOUND")


asyncio.run(main())
