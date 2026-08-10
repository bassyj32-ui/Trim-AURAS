"""Follow the Modal 303 retry-redirect for a >50MB upload to see if it lands."""
import time
from pathlib import Path
import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
OUT = Path("tmp") / "qa" / "follow_redirect.txt"
fpath = Path(r"tmp\diag\videos\v08_large_400mb_40s.mp4")
t0 = time.time()
lines = []
try:
    with httpx.Client(timeout=900, follow_redirects=True) as c:
        with fpath.open("rb") as f:
            r = c.post(BASE + "/api/jobs/upload",
                       files={"file": ("v08.mp4", f, "application/octet-stream")},
                       data={"template_id": "auto", "max_clips": "1"})
    lines.append(f"status {r.status_code} url {str(r.url)[:120]} body {r.text[:200]} elapsed {round(time.time()-t0,1)}")
except Exception as e:
    lines.append(f"EXC {type(e).__name__} {str(e)[:200]} elapsed {round(time.time()-t0,1)}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
