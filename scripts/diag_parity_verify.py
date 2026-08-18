"""Verify route-parity confirmation matrix results in the RENDERED OUTPUT.

Reads tmp/parity_matrix.json (written by diag_parity_matrix.py) and:
  1. Extracts filter_complex evidence from captured clip stderr logs:
       burn_on  -> 'subtitles=' filter present
       trim_on  -> '[condv]' concat chain present
  2. Downloads rendered clips via /api/clips/{id}/download and ffprobes
     ACTUAL media duration + resolution (not the declared DB values).
  3. trim_silence check: rendered duration < declared start/end span
     (pauses cut from media).
  4. burn_captions check: PSNR frame-diff between the burn clip and the
     control clip at the same timestamp + a bottom-band diff ratio.
  5. preferred_height check: value persisted (PIPELINE_START diag event) and
     documents the expected local-upload semantics (download cap, not an
     output-resize).

Writes tmp/parity_verify.json
"""
import json
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
OUT = ROOT / "tmp" / "parity_verify.json"
DLDIR = ROOT / "tmp" / "parity"
DLDIR.mkdir(parents=True, exist_ok=True)


def ffprobe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    out = {}
    try:
        j = json.loads(r.stdout)
        v = next(s for s in j.get("streams", []) if s.get("codec_type") == "video")
        out["width"] = v.get("width")
        out["height"] = v.get("height")
        out["duration"] = round(float(j.get("format", {}).get("duration", 0)), 3)
    except Exception as e:
        out["err"] = str(e)[:200]
    return out


def download_clip(clip_id: int, label: str) -> dict:
    out_path = DLDIR / f"{label}_clip{clip_id}.mp4"
    if out_path.exists():
        return {"cached": True, **probe_ok(out_path), "path": str(out_path)}
    r = httpx.get(f"{BASE}/api/clips/{clip_id}/download", timeout=600)
    if r.headers.get("content-type", "").startswith("application/json"):
        body = r.json()
        if "download_url" in body:
            r2 = httpx.get(body["download_url"], timeout=600, follow_redirects=True)
            if r2.status_code == 200:
                out_path.write_bytes(r2.content)
                return {**probe_ok(out_path), "path": str(out_path)}
        return {"err": f"download_url path: {body}"}
    if r.status_code == 200:
        out_path.write_bytes(r.content)
        return {**probe_ok(out_path), "path": str(out_path)}
    return {"err": f"HTTP {r.status_code} {r.text[:200]}"}


def probe_ok(out_path: Path) -> dict:
    p = ffprobe(out_path)
    return {"duration_s": p.get("duration"), "width": p.get("width"), "height": p.get("height")}


def psnr_diff(path_a: Path, path_b: Path, t: float = 2.0) -> dict:
    """PSNR + mean absolute pixel diff between one frame at t from two clips.

    Uses ffmpeg's psnr filter on single extracted frames; returns global PSNR
    and the per-frame mse. A burned-caption clip vs control at the same
    timestamp shows a large pixel diff in the caption band and a lower PSNR.
    """
    tmp_a = DLDIR / "frame_a.png"
    tmp_b = DLDIR / "frame_b.png"
    for src, dst in ((path_a, tmp_a), (path_b, tmp_b)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src),
             "-frames:v", "1", str(dst)],
            capture_output=True, text=True, timeout=120, check=True,
        )
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "info", "-i", str(tmp_a), "-i", str(tmp_b),
         "-filter_complex", "psnr=stats_file=-", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    last = [l for l in r.stderr.splitlines() if "PSNR" in l]
    line = last[-1] if last else ""
    return {"t": t, "psnr_line": line[:300]}


def band_diff_ratio(path_a: Path, path_b: Path, t: float = 2.0) -> dict:
    """Fraction of differing pixels in the caption band (bottom 35% of frame)."""
    tmp_a = DLDIR / "band_a.rgb"
    tmp_b = DLDIR / "band_b.rgb"
    for src, dst in ((path_a, tmp_a), (path_b, tmp_b)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src),
             "-frames:v", "1", "-vf", "crop=iw:ih*0.35:0:ih*0.65,scale=270:120",
             "-f", "rawvideo", "-pix_fmt", "gray", str(dst)],
            capture_output=True, text=True, timeout=120, check=True,
        )
    da = tmp_a.read_bytes()
    db = tmp_b.read_bytes()
    if len(da) != len(db):
        return {"err": f"size mismatch {len(da)} vs {len(db)}"}
    n = len(da)
    diff = sum(1 for x, y in zip(da, db) if abs(x - y) > 12)
    return {"band_pixels": n, "diff_pixels": diff, "diff_ratio": round(diff / n, 5)}


def extract_evidence(stderr: dict) -> dict:
    """Filter-complex evidence: subtitles= filter (burn) and [condv]/[conda]
    (trim). Only clip_0 is examined — these matrix jobs render a single clip,
    and diag/clip_1..2.stderr.log are stale leftovers from older jobs that
    would otherwise false-positive the checks."""
    src = stderr.get("clip_0", "\n".join(stderr.values()))
    lines = src.splitlines()
    filt = lines[1] if len(lines) > 1 else ""
    return {
        "has_subtitles_filter": "subtitles=" in filt,
        "has_condv_concat": "[condv]" in filt,
        "has_conda_concat": "[conda]" in filt,
        "filter_head": filt[:400],
    }


def main() -> None:
    mtx = json.loads((ROOT / "tmp" / "parity_matrix.json").read_text(encoding="utf-8"))
    rerun_path = ROOT / "tmp" / "parity_rerun.json"
    if rerun_path.exists():
        mtx += json.loads(rerun_path.read_text(encoding="utf-8"))
    by_label = {r["label"]: r for r in mtx}
    report = {"rows": {}, "summary": {}}

    for label, row in by_label.items():
        e = {"post_status": row.get("post_status"), "status": row.get("status"),
             "job_id": row.get("job_id")}
        if row.get("post_status") != 202 or not row.get("job_id"):
            report["rows"][label] = e
            continue
        # persistence evidence from PIPELINE_START diag event
        ev = [x for x in row.get("diag", {}).get("events", []) if x.get("event") == "PIPELINE_START"]
        e["pipeline_start"] = ev[0] if ev else None
        e["filter_evidence"] = extract_evidence(row.get("stderr", {}))
        # clip-level output evidence
        clips = row.get("job", {}).get("clips", [])
        e["clips"] = []
        for c in clips[:3]:
            cid = c["clip_id"]
            dl = download_clip(cid, label)
            span = round(float(c.get("end_time", 0)) - float(c.get("start_time", 0)), 3)
            e["clips"].append({
                "clip_id": cid,
                "declared_start": c.get("start_time"),
                "declared_end": c.get("end_time"),
                "declared_span_s": span,
                "media": dl,
                "media_shorter_than_span": bool(dl.get("duration_s") and dl["duration_s"] < span - 0.05),
            })
        report["rows"][label] = e

    # burn vs control frame-diff (prefer the fresh burn2 row when present)
    burn_label = "burn2" if "burn2" in report["rows"] else "burn_on"
    if burn_label in report["rows"] and "control" in report["rows"]:
        burn_clips = report["rows"][burn_label].get("clips", [])
        ctrl_clips = report["rows"]["control"].get("clips", [])
        paired = []
        for b, c in zip(burn_clips, ctrl_clips):
            bp = Path(b.get("media", {}).get("path", ""))
            cp = Path(c.get("media", {}).get("path", ""))
            if bp.exists() and cp.exists():
                paired.append({
                    "burn_clip_id": b["clip_id"], "control_clip_id": c["clip_id"],
                    "burn_row": burn_label,
                    "psnr": psnr_diff(bp, cp),
                    "band_diff": band_diff_ratio(bp, cp),
                })
        report["burn_vs_control"] = {"paired": paired, "burn_row": burn_label, "note": (
            "low PSNR / high band diff = captions actually burned; "
            "near-identical = burn silently dropped")}

    OUT.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:6000])
    print(f"\nWROTE {OUT}")


if __name__ == "__main__":
    main()
