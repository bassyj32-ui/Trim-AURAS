"""Append rows for jobs 91/92/93 to diag_results.jsonl (same format as 77-90)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "tmp" / "diag_results.jsonl"
rows = [json.loads(l) for l in J.read_text(encoding="utf-8").splitlines() if l.strip()]
existing = {r["job_id"] for r in rows}

poll91 = json.loads((ROOT / "tmp" / "poll_job91.txt").read_text(encoding="utf-8"))["diag"]
d9293 = json.loads((ROOT / "tmp" / "diag_92_93.json").read_text(encoding="utf-8"))

FRAMEIO_URL = "https://next.frame.io/share/a969e3a9-c761-442a-8bfb-17a06b38174c/"


def mk(job_id, source_type, video, url, chars, size_mb, stages, total_s):
    return {
        "job_id": job_id,
        "source_type": source_type,
        "video": video,
        "url": url,
        "chars": chars,
        "size_mb": size_mb,
        "network": "ide_wifi",
        "backgrounded": False,
        "outcome": "completed",
        "failure_stage": None,
        "error": "",
        "stages": stages,
        "total_s": total_s,
    }


new_rows = []
if 91 not in existing:
    s91 = poll91["stages"]
    new_rows.append(mk(91, "upload", "VAL_Agent_30_Launch.mov", None,
                       "val_mrbeast_16x9_isolated", 28.8, s91, 132.55))
if 92 not in existing:
    s92 = d9293["92"]["stages"]
    new_rows.append(mk(92, "url", None, FRAMEIO_URL,
                       "frameio_concurrent_mrbeast", None, s92, 139.57))
if 93 not in existing:
    s93 = d9293["93"]["stages"]
    new_rows.append(mk(93, "upload", "v04_mov_h264_916_60s.mov", None,
                       "v04_916_regression", 42.5, s93, 63.18))

if not new_rows:
    print("no new rows to append (already present)")
else:
    with J.open("a", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r) + "\n")
    print(f"appended {len(new_rows)} rows; total={len(rows) + len(new_rows)}")
