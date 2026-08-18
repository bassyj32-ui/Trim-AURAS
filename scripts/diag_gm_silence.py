"""TEST 3 (direct evidence) — generate-more filter-graph audit + trim + caption position.

Uses a synthetic source (gm_sil2_src.mp4) with KNOWN speech/silence layout
(speech 0-4, silence 4-8, speech 8-12.4, silence 12.4-16.4, speech 16.4-20.9),
so ANY generate-more window overlaps real silence and trim_silence has
something to cut. Silence blocks use gray (not black) frames so the video
signals extractor doesn't flag them as "black ranges to never include".

Flow:
  1. Upload with burn_captions=true + trim_silence=true  ->  job N
  2. Poll COMPLETED; snapshot the volume diag dir (set A) — the initial
     render's per-run stderr log (unique name after the clobber fix)
  3. generate-more count=1 -> poll COMPLETED
  4. Snapshot diag dir again (set B). B - A = the generate-more render's own
     stderr log, captured DIRECTLY (not inferred) -> audit subtitles=/[condv]/
     [conda]/atrim
  5. Probe the generate-more clip: duration vs its window (must be shorter ->
     trim_silence actually cut) + resolution
  6. Caption sizing/position: same-clip band-diff (bottom vs top) + row-profile
     at a caption-on time (inside a speech block) vs caption-off time (inside
     a silence block)

Writes tmp/gm_silence.json
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import modal

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos" / "gm_sil2_src.mp4"
OUT = ROOT / "tmp" / "gm_silence.json"
WORK = ROOT / "tmp"
ENV = dict(__import__("os").environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

# Known source layout (seconds). Speech blocks are different real v01 audio
# chunks; silences are 4s digital-zero (Whisper-transcribable speech around
# them gives trim_silence real inter-word gaps to cut).
SPEECH = [(0.0, 4.05), (8.11, 12.39), (16.41, 20.93)]
SILENCE = [(4.05, 8.11), (12.39, 16.41)]

CAMPAIGN_RULES = (
    "This video has three distinct spoken sections separated by pauses. "
    "Pick highlight clips from the spoken sections. Prefer windows of "
    "10-16 seconds that span a spoken section plus the natural pause after "
    "it. Always return at least one clip."
)

RESULTS: dict = {}
_VOLUME = None


def volume() -> modal.Volume:
    global _VOLUME
    if _VOLUME is None:
        _VOLUME = modal.Volume.from_name("trimaura-data")
    return _VOLUME


def list_diag_logs() -> dict[str, int]:
    """path -> mtime for every clip_*.stderr.log on the volume diag dir."""
    try:
        entries = volume().listdir("/diag")
    except Exception as e:
        print(f"  [volume listdir failed: {e}]", flush=True)
        return {}
    return {e.path.split("/")[-1]: e.mtime for e in entries
            if e.path.endswith(".stderr.log")}


def modal_volume_get(src: str, dst: Path) -> None:
    r = subprocess.run(["python", "-m", "modal", "volume", "get",
                        "trimaura-data", src, str(dst), "--force"],
                       capture_output=True, text=True, env=ENV, timeout=600)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"volume get failed: {r.stdout[:200]} {r.stderr[:300]}")


def upload(data: dict) -> tuple[int, dict]:
    with httpx.Client(timeout=1800) as c, VID.open("rb") as fh:
        r = c.post(f"{BASE}/api/jobs/upload",
                   files={"file": (VID.name, fh, "video/mp4")},
                   data={"template_id": "auto", "max_clips": "1", **data})
    ct = r.headers.get("content-type", "")
    body = r.json() if "json" in ct else {"raw": r.text[:300]}
    return r.status_code, body


def poll(jid: int, label: str, timeout_s: int = 1800) -> dict:
    c = httpx.Client(timeout=30, base_url=BASE)
    t0 = time.time()
    d = {}
    while time.time() - t0 < timeout_s:
        try:
            d = c.get(f"/api/jobs/{jid}/diag").json()
            st = d.get("status")
        except Exception as e:
            st = f"ERR:{str(e)[:60]}"
        print(f"  [{jid}|{label}] t={time.time()-t0:.0f}s status={st}", flush=True)
        if st in ("COMPLETED", "FAILED"):
            return d
        time.sleep(15)
    return {"status": "TIMEOUT", "last": d}


def get_job(jid: int) -> dict:
    r = httpx.get(f"{BASE}/api/jobs/{jid}", timeout=30)
    return r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:300]}


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, timeout=120)
    j = json.loads(r.stdout)
    v = j["streams"][0]
    return {"w": v["width"], "h": v["height"],
            "duration": round(float(j["format"]["duration"]), 3)}


def audit_filter(log_path: Path) -> dict:
    if not log_path.exists():
        return {"err": "no stderr log"}
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    hash_lines = [l[2:].strip() for l in txt.splitlines() if l.startswith("# ")]
    filt = hash_lines[1] if len(hash_lines) > 1 else ""
    atrims = [m for m in __import__("re").findall(r"atrim=([0-9.]+:[0-9.]+)", filt)]
    sub_i = filt.find("subtitles=")
    return {
        "has_subtitles": "subtitles=" in filt,
        "has_condv": "[condv]" in filt,
        "has_conda": "[conda]" in filt,
        "atrim_count": len(atrims),
        "atrims": atrims[:8],
        "subtitles_snippet": filt[sub_i:sub_i + 90] if sub_i >= 0 else None,
    }


def frame(path: Path, t: float, dst: Path) -> None:
    # Frame-accurate: -ss AFTER -i
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
                        "-frames:v", "1", str(dst)], capture_output=True, text=True,
                       timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])


def band_diff_same_clip(path: Path, t_on: float, t_off: float, band: str) -> dict:
    ra, rb = WORK / "gm_b_a.rgb", WORK / "gm_b_b.rgb"
    expr = ("crop=iw:ih*0.35:0:0" if band == "top"
            else "crop=iw:ih*0.35:0:ih*0.65")
    for t, dst in ((t_on, ra), (t_off, rb)):
        r = subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
            "-frames:v", "1", "-vf", f"{expr},scale=270:120",
            "-f", "rawvideo", "-pix_fmt", "gray", str(dst),
        ], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    a, b = ra.read_bytes(), rb.read_bytes()
    n = min(len(a), len(b))
    d = sum(1 for x, y in zip(a, b) if abs(x - y) > 12)
    return {"band": band, "band_pixels": n, "diff_pixels": d,
            "diff_ratio": round(d / n, 5)}


def row_profile_same_clip(path: Path, t_on: float, t_off: float,
                          scale_h: int = 1920) -> dict:
    """Per-row gray diff between caption-on and caption-off frames."""
    ra, rb = WORK / "gm_r_a.raw", WORK / "gm_r_b.raw"
    for t, dst in ((t_on, ra), (t_off, rb)):
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path),
                            "-ss", str(t), "-frames:v", "1",
                            "-vf", f"scale=1:{scale_h}",
                            "-f", "rawvideo", "-pix_fmt", "gray", str(dst)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    da, db = ra.read_bytes(), rb.read_bytes()
    if len(da) != len(db):
        return {"err": f"size mismatch {len(da)} vs {len(db)}"}
    n = scale_h
    diff_rows = [i for i in range(n) if abs(int(da[i]) - int(db[i])) > 12]
    bands: list[list[int]] = []
    for i in diff_rows:
        if bands and i - bands[-1][-1] == 1:
            bands[-1].append(i)
        else:
            bands.append([i])
    out_bands = [(b[0], b[-1]) for b in bands]
    return {"diff_rows": len(diff_rows), "bands": out_bands,
            "first_pct": (out_bands[0][0] / n if out_bands else None),
            "last_pct": (out_bands[-1][1] / n if out_bands else None)}


def silence_overlap(ws: float, we: float) -> float:
    return sum(max(0.0, min(we, e) - max(ws, s)) for s, e in SILENCE)


def caption_times(ws: float, we: float) -> dict:
    """Pick a caption-on time (inside a speech block) and a caption-off time
    (inside a silence block), both within the clip window."""
    t_on = t_off = None
    for s, e in SPEECH:
        ov = (max(ws, s), min(we, e))
        if ov[1] - ov[0] >= 1.0:
            t_on = round(ov[0] + min(2.0, (ov[1] - ov[0]) / 2), 2)
            break
    for s, e in SILENCE:
        ov = (max(ws, s), min(we, e))
        if ov[1] - ov[0] >= 1.0:
            t_off = round(ov[0] + min(1.5, (ov[1] - ov[0]) / 2), 2)
            break
    return {"t_on": t_on, "t_off": t_off}


def save() -> None:
    OUT.write_text(json.dumps(RESULTS, indent=1, default=str), encoding="utf-8")
    print(json.dumps(RESULTS, indent=1, default=str), flush=True)


def main() -> None:
    reuse = len(sys.argv) > 1 and sys.argv[1].isdigit()
    if reuse:
        jid = int(sys.argv[1])
        RESULTS["job"] = {"job_id": jid, "reused": True}
    else:
        st, body = upload({"burn_captions": "true", "trim_silence": "true",
                           "campaign_rules": CAMPAIGN_RULES})
        print(f"== upload: POST {st} {body}", flush=True)
        RESULTS["job"] = {"post_status": st, "post_body": body}
        save()
        if st != 202 or "job_id" not in body:
            print("ABORT: upload failed", flush=True)
            return
        jid = body["job_id"]
        RESULTS["job"]["job_id"] = jid
        diag = poll(jid, "upload")
        RESULTS["job"]["status"] = diag.get("status")
        save()
        if diag.get("status") != "COMPLETED":
            print("ABORT: initial job failed", flush=True)
            return
        # Capture the INITIAL render's own stderr log (direct evidence the
        # main pipeline path also got a unique per-run log).
        logs0 = list_diag_logs()
        new0 = [k for k in logs0 if "stderr.log" in k]
        if new0:
            log = new0[-1]
            try:
                lf = WORK / "gm_initial.stderr.log"
                modal_volume_get(f"diag/{log}", lf)
                RESULTS["job"]["initial_stderr_log"] = log
                RESULTS["job"]["initial_filter_audit"] = audit_filter(lf)
            except Exception as e:
                RESULTS["job"]["initial_audit_err"] = str(e)[:200]

    # ---------- generate-more ----------
    print(f"== generate-more on job {jid}", flush=True)
    before = set(list_diag_logs().keys())
    try:
        r = httpx.post(f"{BASE}/api/jobs/{jid}/generate-more",
                       json={"count": 1}, timeout=30)
        gm_body = r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:200]}
        print(f"  POST {r.status_code} {gm_body}", flush=True)
        RESULTS["generate_more"] = {"post_status": r.status_code, "body": gm_body}
        save()
        if r.status_code == 202:
            d2 = poll(jid, "generate_more")
            RESULTS["generate_more"]["status"] = d2.get("status")
            save()
    except Exception as e:
        RESULTS["generate_more"] = {"err": str(e)[:300]}
        save()

    after = set(list_diag_logs().keys())
    new_logs = sorted(after - before)
    print(f"  new stderr logs after generate-more: {new_logs}", flush=True)
    RESULTS["generate_more"]["new_stderr_logs"] = new_logs
    for log in new_logs:
        try:
            lf = WORK / "gm_gm.stderr.log"
            modal_volume_get(f"diag/{log}", lf)
            RESULTS["generate_more"]["filter_audit"] = audit_filter(lf)
        except Exception as e:
            RESULTS["generate_more"]["audit_err"] = str(e)[:200]
        break  # first (only) new log is the generate-more render

    # ---------- identify + probe the generated clip ----------
    job = get_job(jid)
    clips = job.get("clips") or []
    RESULTS["generate_more"]["clips_total"] = len(clips)
    if len(clips) >= 2:
        gen = max(clips, key=lambda c: c.get("clip_id") or 0)
        RESULTS["generate_more"]["clip"] = {
            "clip_id": gen.get("clip_id"),
            "window": [gen.get("start_time"), gen.get("end_time")],
            "db_duration": gen.get("duration"),
            "created_at": gen.get("created_at"),
        }
        ws = float(gen.get("start_time"))
        we = float(gen.get("end_time"))
        cid = gen.get("clip_id")
        dst = WORK / "dep_gm_sil.mp4"
        try:
            modal_volume_get(f"clips/{jid}_{cid}.mp4", dst)
            p = probe(dst)
            RESULTS["generate_more"]["clip"]["probe"] = p
            RESULTS["generate_more"]["clip"]["window_s"] = round(we - ws, 3)
            RESULTS["generate_more"]["clip"]["silence_overlap_s"] = round(
                silence_overlap(ws, we), 3)
            RESULTS["generate_more"]["clip"]["cut_observed_s"] = round(
                (we - ws) - p["duration"], 3)
        except Exception as e:
            RESULTS["generate_more"]["clip"]["probe_err"] = str(e)[:300]
        # ---------- caption sizing/position on the generated clip ----------
        try:
            tt = caption_times(ws, we)
            RESULTS["generate_more"]["caption"] = dict(tt)
            if tt["t_on"] is not None and tt["t_off"] is not None:
                RESULTS["generate_more"]["caption"]["band_top"] = band_diff_same_clip(
                    dst, tt["t_on"], tt["t_off"], "top")
                RESULTS["generate_more"]["caption"]["band_bottom"] = band_diff_same_clip(
                    dst, tt["t_on"], tt["t_off"], "bottom")
                RESULTS["generate_more"]["caption"]["row_profile"] = row_profile_same_clip(
                    dst, tt["t_on"], tt["t_off"])
                # PSNR on the caption band crop (bottom 30%): isolates the
                # caption text vs the rest of the frame.
                fa, fb = WORK / "gm_p_a.png", WORK / "gm_p_b.png"
                for t, dd in ((tt["t_on"], fa), (tt["t_off"], fb)):
                    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dst),
                                        "-ss", str(t), "-frames:v", "1",
                                        "-vf", "crop=iw:ih*0.3:0:ih*0.7", str(dd)],
                                       capture_output=True, text=True, timeout=120)
                    if r.returncode != 0:
                        raise RuntimeError(r.stderr[-300:])
                r = subprocess.run(["ffmpeg", "-y", "-v", "info", "-i", str(fa),
                                    "-i", str(fb), "-filter_complex", "psnr=stats_file=-",
                                    "-f", "null", "-"], capture_output=True, text=True,
                                   timeout=120)
                pl = [l for l in r.stderr.splitlines() if "PSNR" in l]
                RESULTS["generate_more"]["caption"]["band_psnr"] = (
                    pl[-1].strip() if pl else "no-psnr")
        except Exception as e:
            RESULTS["generate_more"]["caption"] = {"err": str(e)[:300]}
    save()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
