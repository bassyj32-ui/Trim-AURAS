"""Live test against Modal deployment with real GDrive URL."""
import urllib.request, json, time, sys

URL = "https://bassyj32--trimaura-fastapi-app.modal.run"
GDRIVE_URL = "https://drive.google.com/file/d/1C0ewiFev8kfwFcXjd9kdux5bF5nFsHu_/view"

def fetch(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=data, method=method, 
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:500]}
    except Exception as e:
        return 0, {"error": str(e)}

# 1. Health check
print("=== 1. Health Check ===")
s, html = fetch(URL + "/")
if s == 200 and isinstance(html, dict) == False:
    print(f"  Status: {s} - OK")
    html_str = html if isinstance(html, bytes) else str(html)
    if isinstance(html, bytes):
        html_decoded = html.decode()
        print(f"  Has new UI: result-row={'result-row' in html_decoded}, style-chip={'style-chip' in html_decoded}")
else:
    print(f"  Status: {s}")
    if isinstance(html, dict) and "error" in html:
        print(f"  Error: {html['error'][:200]}")
print()

# 2. Submit job
print("=== 2. Submit GDrive Job ===")
payload = json.dumps({
    "title": "Test GDrive 15min",
    "source_url": GDRIVE_URL,
    "template_id": "blurpad_v1",
    "max_clips": 3
}).encode()
s, resp = fetch(URL + "/api/jobs", data=payload, method="POST")
print(f"  Status: {s}")
print(f"  Response: {json.dumps(resp, indent=2)[:300]}")

if "job_id" not in resp:
    print("\n  FAILED: No job_id returned")
    sys.exit(1)

job_id = resp["job_id"]
print(f"\n  Job ID: {job_id}")
print()

# 3. Poll job status
print("=== 3. Polling Job (every 10s, up to 10 min) ===")
for i in range(60):
    time.sleep(10)
    s, status = fetch(URL + f"/api/jobs/{job_id}/poll")
    pct = status.get("progress", 0)
    st = status.get("status", "UNKNOWN")
    err = status.get("error", "")
    print(f"  [{i*10}s] {st} - {pct}%", end="")
    if err:
        print(f"  ERROR: {err[:200]}", end="")
    print()
    
    if st == "COMPLETED":
        print(f"\n  ✅ SUCCESS! Job {job_id} completed!")
        s, job = fetch(URL + f"/api/jobs/{job_id}")
        clips = job.get("clips", [])
        print(f"  Clips generated: {len(clips)}")
        for c in clips[:3]:
            print(f"    - {c.get('clip_id')}: {c.get('titles',{}).get('curiosity','no title')[:60]}")
        break
    if st == "FAILED":
        print(f"\n  ❌ FAILED: {err[:300]}")
        break
else:
    print("\n  ⏰ Timeout after 10 minutes")
