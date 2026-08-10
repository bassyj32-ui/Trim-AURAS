import urllib.request, json

# Check all clips to see their r2_url values
r = urllib.request.urlopen("https://bassyj32--trimaura-fastapi-app.modal.run/api/clips", timeout=15)
clips = json.loads(r.read())
print(f"Total clips in DB: {len(clips)}")
for c in clips[-5:]:
    print(f"  id={c.get('clip_id')}, job={c.get('job_id')}, r2_url={c.get('r2_url','none')[:80]}, status=ok")

# Try downloading each clip from job 24
print("\n--- Download test ---")
for c in clips:
    if c.get('job_id') == 24:
        rid = c['clip_id']
        r2 = urllib.request.urlopen(f"https://bassyj32--trimaura-fastapi-app.modal.run/api/clips/{rid}/download", timeout=15)
        body = r2.read()
        ct = r2.headers.get('content-type','')
        print(f"Clip {rid}: status={r2.status}, content-type={ct[:40]}, body={body.decode()[:100]}")
