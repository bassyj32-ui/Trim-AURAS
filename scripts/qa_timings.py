"""Extract per-stage timings + failure stages from results.jsonl and concurrency.jsonl."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = open(ROOT / "tmp" / "qa" / "timings.txt", "w", encoding="utf-8")


def pr(*a):
    print(*a, file=out, flush=True)


rows = {}
for line in (ROOT / "tmp" / "qa" / "results.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        r = json.loads(line)
        rows[r["label"]] = r

pr("=== STAGE DURATIONS (completed) ===")
for lbl in ["m01", "m02", "m13", "m18", "m19", "m05"]:
    r = rows.get(lbl)
    if not r:
        continue
    st = r.get("stages", {})
    pr(f"{lbl} jid={r.get('job_id')} elapsed={r.get('elapsed_s')} stages={st}")

pr("")
pr("=== FAILURE STAGES (events tail) ===")
for lbl in ["m12", "m14", "m15", "m15b", "u1", "u3", "u4"]:
    r = rows.get(lbl)
    if not r:
        continue
    evs = r.get("events", []) or []
    tail = evs[-6:] if evs else []
    pr(f"{lbl} jid={r.get('job_id')} err={str(r.get('error'))[:90]}")
    for e in tail:
        pr(f"      {e}")

pr("")
pr("=== CONCURRENCY ===")
for line in (ROOT / "tmp" / "qa" / "concurrency.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    pr(f"batch={r.get('batch')} {r.get('file')} jid={r.get('job_id')} "
       f"post={r.get('post_status')} terminal={r.get('terminal')} "
       f"elapsed={r.get('elapsed_s')} err={str(r.get('error'))[:80]} clips={r.get('clips_count')} "
       f"stages={r.get('stages')}")

out.close()
print("ok")
