"""QA master matrix runner (x1.md §4-§9, §16-§20, §23).

Runs backend jobs through the REAL deployed Modal API:
  - upload rows (matrix of source codec/resolution/aspect/duration/size +
    template/captions/trim/height settings)
  - URL-source rows (direct MP4 / direct WebM / Vimeo via yt-dlp)
Sequential by default so per-render stderr evidence can be attributed per job.
Records one JSONL row per job in tmp/qa/results.jsonl (resume-safe: rows whose
label is already recorded are skipped). Downloads every produced clip, probes
it with ffprobe, and captures the per-job diag stage breakdown.

Usage:
  python scripts/qa_matrix_run.py [--rows m01,m02,...] [--max-clips N]
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos"
RESULTS = ROOT / "tmp" / "qa" / "results.jsonl"
CLIPS = ROOT / "tmp" / "qa" / "clips"
POLL_S = 10
TIMEOUT_S = 3600
# Steering rules so LLM clip selection is deterministic for silence/height rows.
STEER = ("This video has three distinct spoken sections separated by pauses. "
         "Pick highlight clips from the spoken sections. Prefer windows of 10-16 seconds "
         "that span a spoken section plus the natural pause after it. Always return at least one clip.")

ROWS = [
    # --- Backend matrix: codec / resolution / aspect / duration / size ---
    {"label": "m01", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4", "data": {}},
    {"label": "m02", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"burn_captions": "true"}},
    {"label": "m03", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"trim_silence": "true"}},
    {"label": "m04", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "blurpad_v1", "burn_captions": "true"}},
    {"label": "m05", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "mrbeast_energy_v1"}},
    {"label": "m06", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "podcast_split_v1", "trim_silence": "true"}},
    {"label": "m07", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "retro_vhs_v1"}},
    {"label": "m08", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "gaming_neon_v1"}},
    {"label": "m09", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"template_id": "brand_bold_v1"}},
    {"label": "m10", "mode": "upload", "file": "v01_small_h264_720p_40s.mp4",
     "data": {"preferred_height": "480"}},
    {"label": "m11", "mode": "upload", "file": "v02_medium_h264_1080p_6min.mp4", "data": {}},
    {"label": "m12", "mode": "upload", "file": "v03_hevc_4k_20s.mp4", "data": {}},
    {"label": "m13", "mode": "upload", "file": "v04_mov_h264_916_60s.mov", "data": {}},
    {"label": "m14", "mode": "upload", "file": "v05_webm_vp9_720p_30s_silent.webm", "data": {}},
    {"label": "m15", "mode": "upload", "file": "v06_music_720p_30s.mp4", "data": {}},
    {"label": "m15b", "mode": "upload", "file": "v06_music_720p_30s.mp4", "data": {}},
    {"label": "m16", "mode": "upload", "file": "v07_long_30min_360p_silent.mp4", "data": {}},
    {"label": "m17", "mode": "upload", "file": "v08_large_400mb_40s.mp4", "data": {}},
    # --- Silence-cut direct verification (steering = deterministic windows) ---
    {"label": "m18", "mode": "upload", "file": "gm_sil2_src.mp4",
     "data": {"burn_captions": "true", "trim_silence": "true", "campaign_rules": STEER}},
    {"label": "m19", "mode": "upload", "file": "gm_sil2_src.mp4",
     "data": {"burn_captions": "true", "campaign_rules": STEER}},
    # --- URL sources (non-YouTube) ---
    {"label": "u1", "mode": "url", "url": "https://media.w3.org/2010/05/sintel/trailer.mp4", "data": {}},
    {"label": "u2", "mode": "url", "url": "https://media.w3.org/2010/05/video/movie_300.webm", "data": {}},
    {"label": "u3", "mode": "url", "url": "https://download.samplelib.com/mp4/sample-10s.mp4", "data": {}},
    {"label": "u4", "mode": "url", "url": "https://vimeo.com/76979871", "data": {}},
]

def _env():
    import os
    return dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def volume_entries(path: str) -> dict:
    """Return {path: mtime} for a Modal Volume directory via the SDK."""
    try:
        import modal
        v = modal.Volume.from_name("trimaura-data")
        out = {}
        for e in v.listdir(path):
            p = e.path.lstrip("/")
            out[p] = e.mtime
        return out
    except Exception as e:
        print(f"  [volume ls] FAILED: {e}", flush=True)
        return {}


def volume_cat(path: str) -> str:
    r = subprocess.run(
        ["python", "-m", "modal", "volume", "cat", "trimaura-data", path],
        capture_output=True, text=True, env=_env(), timeout=180,
    )
    return r.stdout or r.stderr


def probe(path: Path) -> dict:
    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,format_name",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {"error": r.stderr[-300:]}
    d = json.loads(r.stdout or "{}")
    v = a = None
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s
        if s.get("codec_type") == "audio" and a is None:
            a = s
    fmt = d.get("format", {})
    return {
        "container": fmt.get("format_name"),
        "duration": round(float(fmt.get("duration", 0)), 3),
        "size": int(fmt.get("size", 0)),
        "vcodec": (v or {}).get("codec_name"),
        "w": (v or {}).get("width"),
        "h": (v or {}).get("height"),
        "fps": (v or {}).get("r_frame_rate"),
        "acodec": (a or {}).get("codec_name") if a else None,
        "asample": (a or {}).get("sample_rate") if a else None,
    }


def poll(jid: int, label: str) -> dict:
    c = httpx.Client(timeout=30, base_url=BASE)
    t0 = time.time()
    last = ""
    d = {}
    while time.time() - t0 < TIMEOUT_S:
        time.sleep(POLL_S)
        try:
            d = c.get(f"/api/jobs/{jid}/poll").json()
            st = d.get("status")
        except Exception as e:
            st = f"ERR:{str(e)[:60]}"
        if st != last:
            print(f"  [{label}/{jid}] t={time.time()-t0:.0f}s status={st} {('err='+(d.get('error') or '')[:100]) if d.get('error') else ''}", flush=True)
            last = st
            if st in ("COMPLETED", "FAILED"):
                try:
                    d2 = c.get(f"/api/jobs/{jid}/diag").json()
                except Exception:
                    d2 = {}
                return {"poll": d, "diag": d2, "elapsed_s": round(time.time() - t0, 1)}
        if time.time() - t0 > 120 and last == "PENDING":
            # Pipeline spawn usually visible within 2 min; keep polling regardless.
            pass
    return {"poll": {"status": "STUCK"}, "diag": {}, "elapsed_s": round(time.time() - t0, 1)}


def download_clip(cid: int, dest: Path) -> str:
    with httpx.Client(timeout=600, base_url=BASE, follow_redirects=True) as c:
        r = c.get(f"/api/clips/{cid}/download")
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("video/"):
            dest.write_bytes(r.content)
            return f"bytes:{len(r.content)}"
        if r.headers.get("content-type", "").startswith("application/json"):
            try:
                j = r.json()
            except Exception:
                j = {}
            u = j.get("download_url")
            if u and u.startswith("http"):
                rr = c.get(u)
                if rr.status_code == 200:
                    dest.write_bytes(rr.content)
                    return f"presigned:{len(rr.content)}"
            return f"json:{json.dumps(j)[:200]}"
        return f"http{r.status_code}:{r.text[:120]}"


def post_row(c: httpx.Client, row: dict, max_clips: int, attempts: int = 3):
    data = {"template_id": "auto", "max_clips": str(max_clips), **row.get("data", {})}
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            if row["mode"] == "upload":
                fpath = VID / row["file"]
                with fpath.open("rb") as fh:
                    r = c.post(f"{BASE}/api/jobs/upload",
                               files={"file": (fpath.name, fh, "application/octet-stream")},
                               data=data)
                src = row["file"]
            else:
                payload = {"title": row.get("url").split("/")[-1] or "qa-url",
                           "source_url": row["url"], **data}
                r = c.post(f"{BASE}/api/jobs", json=payload)
                src = row["url"]
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:300]}
            return r.status_code, body, src
        except Exception as e:
            last_exc = e
            print(f"  [post] attempt {attempt} failed: {e}", flush=True)
            if attempt < attempts:
                time.sleep(20)
    return 0, {"exc": str(last_exc)[:300]}, row.get("file") or row.get("url", "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=None, help="comma-separated labels to run")
    ap.add_argument("--max-clips", type=int, default=3)
    args = ap.parse_args()

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    seen = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["label"])
            except Exception:
                pass

    rows = ROWS
    if args.rows:
        want = set(args.rows.split(","))
        rows = [r for r in rows if r["label"] in want]

    for row in rows:
        label = row["label"]
        if label in seen:
            print(f"[skip] {label} already recorded", flush=True)
            continue
        print(f"=== {label} mode={row['mode']} {row.get('file') or row.get('url')} data={row.get('data')} ===", flush=True)

        logs_before = volume_entries("/diag")
        t0 = time.time()
        try:
            with httpx.Client(timeout=3600) as c:
                status, body, src = post_row(c, row, args.max_clips)
        except Exception as e:
            RESULTS.open("a", encoding="utf-8").write(json.dumps({
                "label": label, "mode": row["mode"],
                "source": row.get("file") or row.get("url"),
                "settings": row.get("data", {}), "outcome": "runner_error",
                "error": f"{type(e).__name__}: {e}"[:300], "posted_at": time.time(),
            }, default=str) + "\n")
            print(f"  [row-error] {label}: {e}", flush=True)
            continue
        print(f"  POST {status} {body}", flush=True)
        entry = {
            "label": label, "mode": row["mode"], "source": src,
            "settings": row.get("data", {}), "post_status": status,
            "post_body": body, "posted_at": time.time(),
        }
        if status != 202 or "job_id" not in body:
            entry.update({"outcome": "submit_failed", "error": json.dumps(body)[:300]})
            RESULTS.open("a", encoding="utf-8").write(json.dumps(entry) + "\n")
            continue

        jid = body["job_id"]
        entry["job_id"] = jid
        term = poll(jid, label)
        entry["terminal"] = term["poll"].get("status")
        entry["error"] = term["poll"].get("error")
        entry["elapsed_s"] = round(time.time() - t0, 1)
        d = term.get("diag", {})
        entry["stages"] = d.get("stages", {})
        entry["events"] = d.get("events", [])

        # Job + clips
        try:
            job = httpx.get(f"{BASE}/api/jobs/{jid}", timeout=30).json()
            entry["job"] = job
        except Exception as e:
            job = {"err": str(e)}
            entry["job"] = job

        # Download + probe every clip
        clips = []
        for clip in job.get("clips", []):
            cid = clip["clip_id"]
            dest = CLIPS / f"j{jid}_c{cid}.mp4"
            try:
                dl = download_clip(cid, dest)
            except Exception as e:
                dl = f"EXC:{type(e).__name__}:{e}"[:120]
                dest = Path(str(dest) + ".missing")
            p = probe(dest) if dest.exists() and dest.stat().st_size > 0 else {"error": "no file"}
            clips.append({**clip, "download": dl, "probe": p})
        entry["clips_probed"] = clips

        # Per-render stderr evidence created by THIS job (delta of unique names)
        logs_after = volume_entries("/diag")
        new_logs = sorted(set(logs_after) - set(logs_before))
        entry["new_stderr_logs"] = new_logs
        entry["stderr_audit"] = {}
        for lg in new_logs:
            if "stderr.log" in lg:
                txt = volume_cat(lg)
                hash_lines = [l[2:].strip() for l in txt.splitlines() if l.startswith("# ")]
                entry["stderr_audit"][lg] = {
                    "header": hash_lines[0] if len(hash_lines) > 0 else "",
                    "filter_complex": hash_lines[1] if len(hash_lines) > 1 else "",
                    "len": len(txt),
                }

        RESULTS.open("a", encoding="utf-8").write(json.dumps(entry, default=str) + "\n")
        print(f"  [done] {label} jid={jid} outcome={entry['terminal']} elapsed={entry['elapsed_s']}s", flush=True)

    print("ALL ROWS DONE", flush=True)


if __name__ == "__main__":
    main()
