"""Collect evidence for job 108's generate-more clip (direct audit + trim + caption position)."""
import json
import subprocess
from pathlib import Path

import httpx
import modal

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
WORK = ROOT / "tmp"
JID = 108
ENV = dict(__import__("os").environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

SPEECH = [(0.0, 4.05), (8.11, 12.39), (16.41, 20.93)]
SILENCE = [(4.05, 8.11), (12.39, 16.41)]

OUT: dict = {}


def modal_volume_get(src, dst):
    r = subprocess.run(["python", "-m", "modal", "volume", "get", "trimaura-data",
                        src, str(dst), "--force"], capture_output=True, text=True,
                       env=ENV, timeout=600)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError(r.stderr[:300])


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, timeout=120)
    j = json.loads(r.stdout)
    v = j["streams"][0]
    return {"w": v["width"], "h": v["height"],
            "duration": round(float(j["format"]["duration"]), 3)}


def audit_filter(log_path):
    if not log_path.exists():
        return {"err": "no stderr log"}
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    hash_lines = [l[2:].strip() for l in txt.splitlines() if l.startswith("# ")]
    filt = hash_lines[1] if len(hash_lines) > 1 else ""
    import re
    atrims = re.findall(r"atrim=([0-9.]+:[0-9.]+)", filt)
    sub_i = filt.find("subtitles=")
    return {
        "has_subtitles": "subtitles=" in filt,
        "has_condv": "[condv]" in filt,
        "has_conda": "[conda]" in filt,
        "atrim_count": len(atrims),
        "atrims": atrims[:10],
        "subtitles_snippet": filt[sub_i:sub_i + 90] if sub_i >= 0 else None,
        "filter_len": len(filt),
    }


def band_diff_same_clip(path, t_on, t_off, band):
    ra, rb = WORK / "ev_a.rgb", WORK / "ev_b.rgb"
    expr = {"top": "crop=iw:ih*0.35:0:0",
            "mid": "crop=iw:ih*0.35:0:ih*0.325",
            "bottom": "crop=iw:ih*0.35:0:ih*0.65"}.get(band, "crop=iw:ih*0.35:0:ih*0.65")
    for t, dst in ((t_on, ra), (t_off, rb)):
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
                            "-frames:v", "1", "-vf", f"{expr},scale=270:120",
                            "-f", "rawvideo", "-pix_fmt", "gray", str(dst)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    a, b = ra.read_bytes(), rb.read_bytes()
    n = min(len(a), len(b))
    d = sum(1 for x, y in zip(a, b) if abs(x - y) > 12)
    return {"band": band, "band_pixels": n, "diff_pixels": d, "diff_ratio": round(d / n, 5)}


def row_profile_same_clip(path, t_on, t_off, scale_h=1920):
    ra, rb = WORK / "ev_r_a.raw", WORK / "ev_r_b.raw"
    for t, dst in ((t_on, ra), (t_off, rb)):
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
                            "-frames:v", "1", "-vf", f"scale=1:{scale_h}",
                            "-f", "rawvideo", "-pix_fmt", "gray", str(dst)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    da, db = ra.read_bytes(), rb.read_bytes()
    if len(da) != len(db):
        return {"err": f"size mismatch {len(da)} vs {len(db)}"}
    diff_rows = [i for i in range(scale_h) if abs(int(da[i]) - int(db[i])) > 12]
    bands = []
    for i in diff_rows:
        if bands and i - bands[-1][-1] == 1:
            bands[-1].append(i)
        else:
            bands.append([i])
    ob = [(b[0], b[-1]) for b in bands]
    return {"diff_rows": len(diff_rows), "bands": ob,
            "first_pct": round(ob[0][0] / scale_h, 4) if ob else None,
            "last_pct": round(ob[-1][1] / scale_h, 4) if ob else None}


def caption_times(ws, we):
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


# 1) clip info
job = httpx.get(f"{BASE}/api/jobs/{JID}", timeout=30).json()
clips = job.get("clips") or []
OUT["clips"] = [{"clip_id": c.get("clip_id"), "window": [c.get("start_time"), c.get("end_time")],
                 "db_duration": c.get("duration"), "created_at": c.get("created_at")} for c in clips]

# 2) both stderr logs (initial + generate-more) — per-run unique names
v = modal.Volume.from_name("trimaura-data")
logs = sorted([e.path.split("/")[-1] for e in v.listdir("/diag")
               if e.path.endswith(".stderr.log") and "clip_0_" in e.path])
for log in logs:
    dst = WORK / f"ev_{log}"
    try:
        modal_volume_get(f"diag/{log}", dst)
        OUT.setdefault("stderr_logs", []).append({"log": log, "audit": audit_filter(dst)})
    except Exception as e:
        OUT.setdefault("stderr_logs", []).append({"log": log, "err": str(e)[:150]})

# 3) generate-more clip = newest clip_id (141)
gen = max(clips, key=lambda c: c.get("clip_id") or 0)
cid = gen["clip_id"]
dst = WORK / "ev_gm_clip.mp4"
modal_volume_get(f"clips/{JID}_{cid}.mp4", dst)
p = probe(dst)
OUT["generated_clip"] = {"clip_id": cid, "probe": p}

ws, we = float(gen["start_time"]), float(gen["end_time"])
window = round(we - ws, 3)
sil_overlap = round(sum(max(0.0, min(we, e) - max(ws, s)) for s, e in SILENCE), 3)
OUT["generated_clip"]["window_s"] = window
OUT["generated_clip"]["silence_overlap_s"] = sil_overlap
OUT["generated_clip"]["cut_observed_s"] = round(window - p["duration"], 3)
tt = caption_times(ws, we)
OUT["caption"] = dict(tt)
if tt["t_on"] is not None and tt["t_off"] is not None:
    OUT["caption"]["band_top"] = band_diff_same_clip(dst, tt["t_on"], tt["t_off"], "top")
    OUT["caption"]["band_mid"] = band_diff_same_clip(dst, tt["t_on"], tt["t_off"], "mid")
    OUT["caption"]["band_bottom"] = band_diff_same_clip(dst, tt["t_on"], tt["t_off"], "bottom")
    OUT["caption"]["row_profile"] = row_profile_same_clip(dst, tt["t_on"], tt["t_off"])
    # cleaner caption read: two caption frames inside the SAME speech block
    # (different words -> caption pixels change, video content ~same)
    t2_on, t2_off = tt["t_on"], tt["t_on"] + 1.6
    if t2_off <= we:
        OUT["caption"]["within_speech_band_bottom"] = band_diff_same_clip(
            dst, t2_on, t2_off, "bottom")
        OUT["caption"]["within_speech_row_profile"] = row_profile_same_clip(
            dst, t2_on, t2_off)
        fa, fb = WORK / "ev_pa.png", WORK / "ev_pb.png"
        for t, dd in ((t2_on, fa), (t2_off, fb)):
            r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dst), "-ss", str(t),
                                "-frames:v", "1", "-vf", "crop=iw:ih*0.3:0:ih*0.7", str(dd)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-300:])
        r = subprocess.run(["ffmpeg", "-y", "-v", "info", "-i", str(fa), "-i", str(fb),
                            "-filter_complex", "psnr=stats_file=-", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=120)
        pl = [l for l in r.stderr.splitlines() if "PSNR" in l]
        OUT["caption"]["within_speech_band_psnr"] = pl[-1].strip() if pl else "no-psnr"

save = ROOT / "tmp" / "gm_evidence.json"
save.write_text(json.dumps(OUT, indent=1, default=str), encoding="utf-8")
print(json.dumps(OUT, indent=1, default=str), flush=True)
