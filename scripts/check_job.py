import json
import urllib.request

# Check job 24 status from database
r = urllib.request.urlopen("https://bassyj32--trimaura-fastapi-app.modal.run/api/jobs/24", timeout=15)
j = json.loads(r.read())
print("Job 24:")
print(f"  status: {j.get('status')}")
print(f"  progress: {j.get('progress')}")
print(f"  clips: {len(j.get('clips',[]))}")
print(f"  error: {j.get('error')}")
if j.get('clips'):
    for c in j['clips']:
        print(f"  clip: id={c.get('clip_id')}, title={c.get('titles',{}).get('curiosity','')[:50]}, duration={c.get('duration')}")
