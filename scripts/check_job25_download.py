import urllib.request, json

# Get job 25 clips
r = urllib.request.urlopen("https://bassyj32--trimaura-fastapi-app.modal.run/api/jobs/25", timeout=15)
j = json.loads(r.read())
clips = j.get("clips", [])
print(f"Job 25: {len(clips)} clips")

for c in clips:
    cid = c["clip_id"]
    r2 = urllib.request.urlopen(f"https://bassyj32--trimaura-fastapi-app.modal.run/api/clips/{cid}/download", timeout=30)
    ct = r2.headers.get("Content-Type", "")
    sz = r2.headers.get("Content-Length", "unknown")
    body = r2.read(20)
    print(f"  Clip {cid}: status={r2.status}, type={ct}, size={sz}, first_bytes={body[:8].hex()}")
