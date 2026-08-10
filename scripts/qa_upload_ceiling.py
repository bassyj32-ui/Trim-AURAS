"""Bracket the upload ceiling: 45MB vs 50MB truncated copies, print headers."""
import time
from pathlib import Path
import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "tmp" / "qa"
SRC = ROOT / "tmp" / "diag" / "videos" / "v08_large_400mb_40s.mp4"

for mb in (45, 50):
    dst = QA / f"trunc_{mb}mb.mp4"
    with SRC.open("rb") as f:
        dst.write_bytes(f.read(mb * 1024 * 1024))
    t0 = time.time()
    try:
        with httpx.Client(timeout=600, follow_redirects=False) as c:
            with dst.open("rb") as fh:
                r = c.post(f"{BASE}/api/jobs/upload",
                           files={"file": (dst.name, fh, "application/octet-stream")},
                           data={"template_id": "auto", "max_clips": "1"})
        print(f"{mb}MB status={r.status_code} loc={r.headers.get('location')} "
              f"ct={r.headers.get('content-type')} body={r.text[:150]} elapsed={time.time()-t0:.1f}s")
    except Exception as e:
        print(f"{mb}MB EXC {type(e).__name__}: {e} elapsed={time.time()-t0:.1f}s")
