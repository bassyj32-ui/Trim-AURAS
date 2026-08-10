import json
import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
out = {}
r = httpx.get(f"{BASE}/api/jobs/105", timeout=30)
out["job"] = r.json()
# raw clip rows (incl. r2_url/keys) may be in a dedicated endpoint; try job body
clips = r.json().get("clips") or []
out["clips"] = clips
out["clips_count"] = len(clips)
r2 = httpx.get(f"{BASE}/api/clips?job_id=105", timeout=30)
if r2.status_code == 200:
    out["api_clips"] = r2.json()
open(r"d:\trae\TrimAURAs\TrimAuras\tmp\gm_check.json", "w", encoding="utf-8").write(
    json.dumps(out, indent=1, default=str))
print("WROTE tmp/gm_check.json")
