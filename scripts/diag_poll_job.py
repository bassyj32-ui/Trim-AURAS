"""Poll a job until terminal state, write status history -> tmp/poll_job91.txt"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
jid = int(sys.argv[1])
timeout_s = int(sys.argv[2]) if len(sys.argv) > 2 else 3600
OUT = Path(__file__).resolve().parent.parent / "tmp" / f"poll_job{jid}.txt"

c = httpx.Client(timeout=30, base_url=BASE)
t0 = time.time()
history = []
last = ""
while time.time() - t0 < timeout_s:
    try:
        d = c.get(f"/api/jobs/{jid}/diag").json()
        st = d.get("status")
    except Exception as e:
        st = f"ERR:{str(e)[:60]}"
    if st != last:
        history.append(f"t={time.time()-t0:.0f}s status={st}")
        last = st
        OUT.write_text(json.dumps({"history": history, "last_diag": d if st != last else None}, indent=1, default=str), encoding="utf-8")
        print(f"t={time.time()-t0:.0f}s status={st}", flush=True)
        if st in ("COMPLETED", "FAILED"):
            OUT.write_text(json.dumps({"history": history, "diag": d}, indent=1, default=str), encoding="utf-8")
            print("TERMINAL", flush=True)
            break
    time.sleep(10)
else:
    OUT.write_text(json.dumps({"history": history, "diag": d}, indent=1, default=str), encoding="utf-8")
    print("TIMEOUT", flush=True)
