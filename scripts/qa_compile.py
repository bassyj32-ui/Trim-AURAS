"""Compile QA evidence from tmp/qa/results.jsonl into tmp/qa/compile.txt."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = open(ROOT / "tmp" / "qa" / "compile.txt", "w", encoding="utf-8")


def pr(*a):
    print(*a, file=out, flush=True)


rows = {}
for line in (ROOT / "tmp" / "qa" / "results.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    rows[r["label"]] = r

pr("=== MASTER TABLE ===")
order = ["m01", "m02", "m03", "m04", "m05", "m06", "m07", "m08", "m09", "m10",
         "m11", "m12", "m13", "m14", "m15", "m15b", "m16", "m17", "m18", "m19",
         "u1", "u2", "u3", "u4"]
for lbl in order:
    r = rows.get(lbl)
    if not r:
        pr(f"{lbl}: NOT RECORDED")
        continue
    out_ = r.get("outcome") or r.get("terminal")
    err = (r.get("error") or "")[:70]
    jid = r.get("job_id")
    pr(f"{lbl:5s} jid={jid} post={r.get('post_status')} outcome={out_} err={err}")

pr("")
pr("=== CLIP OUTPUT INTEGRITY (completed jobs) ===")
for lbl in order:
    r = rows.get(lbl)
    if not r or r.get("terminal") != "COMPLETED":
        continue
    for cl in r.get("clips_probed", []):
        p = cl.get("probe", {})
        pr(f"{lbl:5s} c{cl.get('clip_id')} w={cl.get('start_time')}-{cl.get('end_time')} "
           f"probe={p.get('w')}x{p.get('h')} dur={p.get('duration')} v={p.get('vcodec')} a={p.get('acodec')} "
           f"size={p.get('size')} dl={cl.get('download')}")

pr("")
pr("=== STDERR FILTER-GRAPH AUDIT (captions/trim evidence) ===")
for lbl in ["m01", "m02", "m03", "m04", "m18", "m19", "m10"]:
    r = rows.get(lbl)
    if not r:
        continue
    for lg, audit in (r.get("stderr_audit") or {}).items():
        fc = audit.get("filter_complex") or ""
        has_sub = "subtitles=" in fc
        atrims = [t for t in fc.split(";") if "atrim" in t]
        pr(f"{lbl:5s} {lg[-28:]} subtitles={has_sub} atrim_present={len(atrims)>0}")
        if atrims:
            pr(f"        atrims: {atrims[:4]}")

pr("")
pr("=== SETTING VERIFICATION (m10 height cap vs m01 baseline) ===")
for lbl in ["m01", "m10"]:
    r = rows.get(lbl)
    if not r or r.get("terminal") != "COMPLETED":
        pr(f"{lbl}: n/a")
        continue
    for cl in r.get("clips_probed", []):
        p = cl.get("probe", {})
        bps = (p.get("size") or 0) * 8 / max(p.get("duration") or 1, 0.1)
        pr(f"{lbl}: c{cl.get('clip_id')} {p.get('w')}x{p.get('h')} dur={p.get('duration')} "
           f"bytes={p.get('size')} ~{bps/1000:.0f}kbps")

out.close()
print("written")
