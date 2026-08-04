"""Refresh diag_results.jsonl rows from live API data (jobs 77-90)."""
import json
from pathlib import Path

import httpx

BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "tmp" / "diag_results.jsonl"

META = {
    77: dict(source_type="url", chars="gdrive_link", size_mb=None),
    78: dict(source_type="url", chars="gdrive_link", size_mb=None),
    79: dict(source_type="url", chars="frameio_link", size_mb=None),
    80: dict(source_type="url", chars="frameio_link", size_mb=None),
    81: dict(source_type="url", chars="gdrive_mrbeast", size_mb=None),
    82: dict(source_type="url", chars="frameio_brandbold", size_mb=None),
    83: dict(source_type="upload", chars="v01_h264_720p_40s_smoke", video="v01_small_h264_720p_40s.mp4", size_mb=13.2),
    84: dict(source_type="upload", chars="v06_music_720p_30s", video="v06_music_720p_30s.mp4", size_mb=10.0),
    85: dict(source_type="upload", chars="v03_hevc_4k_20s", video="v03_hevc_4k_20s.mp4", size_mb=40.7),
    87: dict(source_type="upload", chars="v03_hevc_4k_20s_dup", video="v03_hevc_4k_20s.mp4", size_mb=40.7),
    89: dict(source_type="upload", chars="v05_webm_vp9_720p_30s_silent", video="v05_webm_vp9_720p_30s_silent.webm", size_mb=3.1),
    90: dict(source_type="upload", chars="v04_mov_h264_916_60s", video="v04_mov_h264_916_60s.mov", size_mb=42.5),
    86: dict(source_type="url", chars="frameio_isolated_mrbeast", url="https://next.frame.io/share/a969e3a9-c761-442a-8bfb-17a06b38174c/", size_mb=None),
    88: dict(source_type="url", chars="frameio_link2_untitled", url="https://next.frame.io/share/33cf6029-e532-4d3e-9c4f-134a9ae1b8c3/", size_mb=None),
}


def main():
    c = httpx.Client(timeout=60, base_url=BASE)
    rows = []
    for jid in sorted(META):
        meta = META[jid]
        d = c.get(f"/api/jobs/{jid}/diag").json()
        stages = d.get("stages", {})
        status = d.get("status")
        error = d.get("error") or ""
        failure = None
        if status == "FAILED":
            for name, s in stages.items():
                if not s.get("ok"):
                    failure = name
                    break
            if not failure:
                for ev in reversed(d.get("events", [])):
                    if ev.get("event") == "STAGE_ENTER":
                        failure = ev.get("stage")
                        break
        rows.append({
            "job_id": jid,
            "source_type": meta["source_type"],
            "video": meta.get("video"),
            "url": meta.get("url"),
            "chars": meta["chars"],
            "size_mb": meta.get("size_mb"),
            "network": "ide_wifi",
            "backgrounded": False,
            "outcome": "completed" if status == "COMPLETED" else ("failed" if status == "FAILED" else "stuck"),
            "failure_stage": failure,
            "error": error[:300],
            "stages": stages,
            "total_s": None,
        })
    RESULTS.write_text("\n".join(json.dumps(r, ensure_ascii=True) for r in rows) + "\n",
                       encoding="utf-8")
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main()
