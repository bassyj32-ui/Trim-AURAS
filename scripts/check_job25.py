import json
import urllib.request

r = urllib.request.urlopen('https://bassyj32--trimaura-fastapi-app.modal.run/api/jobs/25', timeout=15)
j = json.loads(r.read())
err = j.get('error', 'none')
print(f'Job 25 DB status: {j.get("status")}, progress: {j.get("progress")}, error: {err}')
