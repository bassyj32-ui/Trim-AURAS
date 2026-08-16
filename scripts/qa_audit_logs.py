"""Re-audit per-job stderr logs via the Modal SDK (volume cat not in CLI).

Reads each recorded row's new_stderr_logs, extracts the header/# filter lines,
and writes tmp/qa/log_audit.txt.
"""
import json
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
out = open(ROOT / "tmp" / "qa" / "log_audit.txt", "w", encoding="utf-8")

v = modal.Volume.from_name("trimaura-data")
rows = {}
for line in (ROOT / "tmp" / "qa" / "results.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    rows[r["label"]] = r

for lbl in ["m01", "m02", "m03", "m04", "m05", "m06", "m07", "m08", "m09", "m10",
            "m13", "m18", "m19", "u1", "u2", "u3"]:
    r = rows.get(lbl)
    if not r:
        continue
    for lg in (r.get("new_stderr_logs") or []):
        if "stderr.log" not in lg:
            continue
        try:
            data = b"".join(v.read_file("/" + lg)).decode("utf-8", errors="replace")
        except Exception as e:
            out.write(f"{lbl} {lg}: READ-ERR {e}\n")
            continue
        hash_lines = [l[2:].strip() for l in data.splitlines() if l.startswith("# ")]
        fc = hash_lines[1] if len(hash_lines) > 1 else (hash_lines[0] if hash_lines else "")
        has_sub = "subtitles=" in fc
        atrims = [t for t in fc.split(";") if "atrim" in t]
        out.write(f"{lbl:5s} {lg[-30:]} subtitles={has_sub} atrims={atrims[:4]}\n")
        out.write(f"        header0={hash_lines[0][:80] if hash_lines else 'NONE'}\n")
        out.write(f"        fc_len={len(fc)}\n")

out.close()
print("done")
