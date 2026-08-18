"""Test download fix: submit GDrive job, wait for completion, verify download."""
import json
import sys
import time
import urllib.request

URL = "https://bassyj32--trimaura-fastapi-app.modal.run"
GDRIVE_URL = "https://drive.google.com/file/d/1C0ewiFev8kfwFcXjd9kdux5bF5nFsHu_/view"

def fetch(path, data=None, method="GET"):
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method,
        headers={"Content-Type":"application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if body:
                try: return r.status, json.loads(body)
                except: return r.status, body
            return r.status, {}
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}
    except Exception as e:
        return 0, {"error": str(e)}

# 1. Submit job
print("=== 1. Submitting GDrive job ===")
s, resp = fetch("/api/jobs", json.dumps({
    "title": "Download fix test",
    "source_url": GDRIVE_URL,
    "template_id": "blurpad_v1",
    "max_clips": 2
}).encode(), "POST")
print(f"  Status: {s}, job_id: {resp.get('job_id')}")
if "job_id" not in resp:
    print(f"  Error: {resp.get('error')}")
    sys.exit(1)

job_id = resp["job_id"]
print()

# 2. Poll until done
print("=== 2. Waiting for completion ===")
for i in range(180):
    time.sleep(10)
    s, status = fetch(f"/api/jobs/{job_id}/poll")
    st = status.get("status", "UNKNOWN")
    pct = status.get("progress", 0)
    print(f"  [{i*10}s] {st} - {pct}%", end="")
    err = status.get("error", "")
    if err: print(f"  ERROR: {err[:150]}", end="")
    print()
    if st in ("COMPLETED", "FAILED"):
        if st == "FAILED":
            print(f"\n  ❌ FAILED: {err}")
            sys.exit(1)
        break
else:
    print("\n  ⏰ Timeout")
    sys.exit(1)

# 3. Get clips and test download
print("\n=== 3. Testing download ===")
s, job = fetch(f"/api/jobs/{job_id}")
clips = job.get("clips", [])
print(f"  Clips: {len(clips)}")

for c in clips:
    cid = c["clip_id"]
    s, body = fetch(f"/api/clips/{cid}/download")
    ct = ""
    if isinstance(body, bytes):
        ct = "video/mp4 (binary)"
        sz = len(body)
    elif isinstance(body, dict):
        ct = body.get("download_url", "unknown")
    print(f"  Clip {cid}: status={s}, type={ct[:60]}")

print("\n✅ Done!")
