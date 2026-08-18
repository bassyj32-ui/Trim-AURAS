"""TEST 1 (deployed) + TEST 3 deployed verification — one toggled job.

Uploads v01 ONCE with burn_captions=true + trim_silence=true +
preferred_height=480 (all on the same job), polls to COMPLETED, then:

  * probes the rendered clip: resolution + duration (vs the 30.3s source
    window — trim must make it meaningfully shorter)
  * top/bottom 35% band diffs of the SAME clip at caption-on vs caption-off
    times (bottom-band diff > 0 => captions burned at the bottom = PlayRes
    fix working in the real pipeline; the old bug would put text at TOP)
  * audits the deployed render stderr filter for `subtitles=` + `[condv]` +
    `[conda]` (proves burn + trim were active in the filter graph)

TEST 3: then calls generate-more (count=1) on the SAME job and clip-trim on
one clip — both must re-render with the SAME toggles (correct caption
position + trimmed duration), proving the job-row settings are reused.

Writes tmp/combined_deploy.json
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos" / "v01_small_h264_720p_40s.mp4"
OUT = ROOT / "tmp" / "combined_deploy.json"
WORK = ROOT / "tmp"
ENV = dict(__import__("os").environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
RESULTS: dict = {}


def upload(data: dict) -> tuple[int, dict]:
    with httpx.Client(timeout=1800) as c, VID.open("rb") as fh:
        r = c.post(f"{BASE}/api/jobs/upload",
                   files={"file": (VID.name, fh, "video/mp4")},
                   data={"template_id": "auto", "max_clips": "1", **data})
    ct = r.headers.get("content-type", "")
    body = r.json() if "json" in ct else {"raw": r.text[:300]}
    return r.status_code, body


def poll(jid: int, label: str, timeout_s: int = 2400) -> dict:
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
        time.sleep(20)
    return {"status": "TIMEOUT", "last": d}


def get_job(jid: int) -> dict:
    r = httpx.get(f"{BASE}/api/jobs/{jid}", timeout=30)
    return r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:300]}


def modal_volume_get(src: str, dst: Path) -> None:
    r = subprocess.run(["python", "-m", "modal", "volume", "get",
                        "trimaura-data", src, str(dst), "--force"],
                       capture_output=True, text=True, env=ENV, timeout=600)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"volume get failed: {r.stdout[:200]} {r.stderr[:300]}")


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, timeout=120)
    j = json.loads(r.stdout)
    v = j["streams"][0]
    return {"w": v["width"], "h": v["height"],
            "duration": round(float(j["format"]["duration"]), 3)}


def band_diff_same_clip(path: Path, t_on: float, t_off: float,
                        band: str) -> dict:
    """Diff one 35% band of the same clip at two times.
    band='bottom' -> crop y=0.65h..h ; band='top' -> crop y=0..0.35h"""
    ra, rb = WORK / "cb_a.rgb", WORK / "cb_b.rgb"
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


def audit_filter(log_path: Path) -> dict:
    if not log_path.exists():
        return {"err": "no stderr log"}
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    hash_lines = [l[2:].strip() for l in txt.splitlines() if l.startswith("# ")]
    filt = hash_lines[1] if len(hash_lines) > 1 else ""
    sub_i = filt.find("subtitles=")
    return {
        "has_subtitles": "subtitles=" in filt,
        "has_condv": "[condv]" in filt,
        "has_conda": "[conda]" in filt,
        "subtitles_snippet": filt[sub_i:sub_i + 90] if sub_i >= 0 else None,
    }


def download_first_clip(job: dict, label: str) -> dict:
    clips = job.get("clips") or []
    out = {"clips": len(clips)}
    if not clips:
        return out
    cid = clips[0].get("clip_id") or clips[0].get("id")
    rel = (clips[0].get("r2_url") or "").replace("/mnt/data/", "")
    src = rel if rel and not rel.startswith("http") else f"clips/{job.get('id')}_{cid}.mp4"
    dst = WORK / f"dep_{label}.mp4"
    modal_volume_get(src, dst)
    out["clip_id"] = cid
    out["src"] = src
    out["probe"] = probe(dst)
    out["band_top_t2_vs_t8"] = band_diff_same_clip(dst, 2.0, 8.0, "top")
    out["band_bottom_t2_vs_t8"] = band_diff_same_clip(dst, 2.0, 8.0, "bottom")
    out["band_bottom_t4_vs_t8"] = band_diff_same_clip(dst, 4.0, 8.0, "bottom")
    stderr = WORK / f"dep_{label}.stderr.log"
    try:
        modal_volume_get("diag/clip_0.stderr.log", stderr)
        out["filter_audit"] = audit_filter(stderr)
    except Exception as e:
        out["filter_audit"] = {"err": str(e)[:200]}
    return out


def save() -> None:
    OUT.write_text(json.dumps(RESULTS, indent=1, default=str), encoding="utf-8")


def main() -> None:
    # Optional argv[1] = existing completed job id (skip upload, reuse it).
    reuse = len(sys.argv) > 1 and sys.argv[1].isdigit()
    if reuse:
        jid = int(sys.argv[1])
        RESULTS["test1"] = {"job_id": jid, "reused": True, "post_status": "REUSED"}
        diag = poll(jid, "test1")
        RESULTS["test1"]["status"] = diag.get("status")
        save()
    else:
        # ---------- TEST 1: one toggled job ----------
        st, body = upload({"burn_captions": "true", "trim_silence": "true",
                           "preferred_height": "480"})
        print(f"== TEST1 upload: POST {st} {body}", flush=True)
        RESULTS["test1"] = {"post_status": st, "post_body": body}
        save()
        if st != 202 or "job_id" not in body:
            print("ABORT: upload failed", flush=True)
            return
        jid = body["job_id"]
        RESULTS["test1"]["job_id"] = jid
        diag = poll(jid, "test1")
        RESULTS["test1"]["status"] = diag.get("status")
        save()
    if diag.get("status") == "COMPLETED":
        job = get_job(jid)
        RESULTS["test1"]["clip"] = download_first_clip(job, "t1")
        # Pull the deployed diag JSONL: confirm the toggles reached the worker.
        dj = WORK / "dep_t1_diag.jsonl"
        try:
            modal_volume_get(f"diag/job_{jid}_diag.jsonl", dj)
            flag_lines = [l for l in dj.read_text(encoding="utf-8", errors="replace")
                          .splitlines() if "burn_captions" in l or
                          "trim_silence" in l or "preferred_height" in l]
            RESULTS["test1"]["diag_flag_lines"] = flag_lines[-6:]
        except Exception as e:
            RESULTS["test1"]["diag_flag_err"] = str(e)[:200]
        save()

    # ---------- TEST 3: generate-more on the SAME job ----------
    print(f"== TEST3 generate-more on job {jid}", flush=True)
    try:
        r = httpx.post(f"{BASE}/api/jobs/{jid}/generate-more",
                       json={"count": 1}, timeout=30)
        gm_body = r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:200]}
        print(f"  generate-more: POST {r.status_code} {gm_body}", flush=True)
        RESULTS["test3"] = {"generate_more": {"post_status": r.status_code,
                                              "body": gm_body}}
        save()
        d2 = poll(jid, "generate_more")
        RESULTS["test3"]["generate_more"]["status"] = d2.get("status")
        job = get_job(jid)
        extra = [c for c in (job.get("clips") or []) if "extra" in str(c.get("r2_url", ""))]
        RESULTS["test3"]["generate_more"]["clips_total"] = len(job.get("clips") or [])
        if extra:
            cid = extra[-1].get("clip_id") or extra[-1].get("id")
            src = f"clips/{jid}_{cid}.mp4"
            dst = WORK / "dep_gm.mp4"
            try:
                modal_volume_get(src, dst)
                RESULTS["test3"]["generate_more"]["clip_id"] = cid
                RESULTS["test3"]["generate_more"]["probe"] = probe(dst)
                RESULTS["test3"]["generate_more"]["band_bottom_t2_vs_t8"] = \
                    band_diff_same_clip(dst, 2.0, 8.0, "bottom")
                stderr = WORK / "dep_gm.stderr.log"
                modal_volume_get("diag/clip_0.stderr.log", stderr)
                RESULTS["test3"]["generate_more"]["filter_audit"] = audit_filter(stderr)
            except Exception as e:
                RESULTS["test3"]["generate_more"]["clip_err"] = str(e)[:300]
        save()
    except Exception as e:
        RESULTS["test3"] = {"generate_more": {"err": str(e)[:300]}}
        save()

    # ---------- TEST 3: clip-trim on an existing clip ----------
    print("== TEST3 clip-trim", flush=True)
    try:
        job = get_job(jid)
        clips = job.get("clips") or []
        if clips:
            first = clips[0]
            cid = first.get("clip_id") or first.get("id")
            s = float(first.get("start_time") or first.get("start") or 0)
            e = float(first.get("end_time") or first.get("end") or s + 3)
            if e - s > 3:
                ns, ne = s + 1.0, e - 1.0
            else:
                ns, ne = s + 0.3, e - 0.3
            r = httpx.post(f"{BASE}/api/clips/{cid}/trim",
                           json={"start": ns, "end": ne}, timeout=30)
            tb = r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:200]}
            print(f"  trim: POST {r.status_code} {tb}", flush=True)
            RESULTS["test3"]["trim"] = {"post_status": r.status_code, "body": tb,
                                        "cid": cid, "new_bounds": [ns, ne]}
            save()
            d3 = poll(jid, "trim")
            RESULTS["test3"]["trim"]["status"] = d3.get("status")
            dst = WORK / "dep_trim.mp4"
            try:
                modal_volume_get(f"clips/{jid}_{cid}.mp4", dst)
                RESULTS["test3"]["trim"]["probe"] = probe(dst)
                stderr = WORK / "dep_trim.stderr.log"
                modal_volume_get("diag/clip_0.stderr.log", stderr)
                RESULTS["test3"]["trim"]["filter_audit"] = audit_filter(stderr)
            except Exception as e:
                RESULTS["test3"]["trim"]["clip_err"] = str(e)[:300]
            save()
    except Exception as e:
        RESULTS.setdefault("test3", {})["trim"] = {"err": str(e)[:300]}
        save()

    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
