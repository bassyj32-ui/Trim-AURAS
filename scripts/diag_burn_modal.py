"""Deployed-caption verification (no images).

Deploy the PlayRes fix, then upload the same v01 video twice:
  control -> burn_captions absent
  burn_on -> burn_captions=true
Poll to COMPLETED, download the first rendered clip of each job from the
Modal Volume, then verify caption POSITION with a self-contained check:

  bottom-band (bottom 35%) of the clip at t=caption_off vs t=caption_on:
    burn clip : diff > 0  -> text IS burned in the bottom band (fix works)
    control   : diff ~ 0  -> no caption anywhere (methodology sanity check)

The mrbeast_energy_v1 overlay has an opaque bottom bar, so the bottom band
is static EXCEPT where captions are drawn — no cross-job matching needed.

Writes tmp/parity_burn_modal.json
"""
import json
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
BASE = "https://bassyj32--trimaura-fastapi-app.modal.run"
VID = ROOT / "tmp" / "diag" / "videos" / "v01_small_h264_720p_40s.mp4"
OUT = ROOT / "tmp" / "parity_burn_modal.json"
ENV = dict(__import__("os").environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def upload(data: dict) -> tuple[int, dict]:
    with httpx.Client(timeout=1800) as c, VID.open("rb") as fh:
        r = c.post(f"{BASE}/api/jobs/upload",
                   files={"file": (VID.name, fh, "video/mp4")},
                   data={"template_id": "auto", "max_clips": "3", **data})
    body = r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:300]}
    return r.status_code, body


def poll(jid: int, timeout_s: int = 2400) -> dict:
    c = httpx.Client(timeout=30, base_url=BASE)
    t0 = time.time()
    d = {}
    while time.time() - t0 < timeout_s:
        try:
            d = c.get(f"/api/jobs/{jid}/diag").json()
            st = d.get("status")
        except Exception as e:
            st = f"ERR:{str(e)[:60]}"
        print(f"  [{jid}] t={time.time()-t0:.0f}s status={st}", flush=True)
        if st in ("COMPLETED", "FAILED"):
            return d
        time.sleep(20)
    return {"status": "TIMEOUT", "last": d}


def modal_volume_get(src: str, dst: Path) -> None:
    r = subprocess.run(["python", "-m", "modal", "volume", "get",
                        "trimaura-data", src, str(dst)],
                       capture_output=True, text=True, env=ENV, timeout=600)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"volume get failed: {r.stdout[:300]} {r.stderr[:300]}")


def band_diff_same_clip(path: Path, t_on: float, t_off: float) -> dict:
    """Diff bottom 35% band of one clip at two different times."""
    ra, rb = OUT.parent / "mb_a.rgb", OUT.parent / "mb_b.rgb"
    for t, dst in ((t_on, ra), (t_off, rb)):
        r = subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(t),
            "-frames:v", "1", "-vf", "crop=iw:ih*0.35:0:ih*0.65,scale=270:120",
            "-f", "rawvideo", "-pix_fmt", "gray", str(dst),
        ], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    a, b = ra.read_bytes(), rb.read_bytes()
    n = min(len(a), len(b))
    d = sum(1 for x, y in zip(a, b) if abs(x - y) > 12)
    return {"band_pixels": n, "diff_pixels": d, "diff_ratio": round(d / n, 5)}


def full_row_profile(path: Path, t: float) -> list[int]:
    """Per-40px-bucket diff counts vs a fixed reference time of the SAME clip."""
    ref_t = 7.0 if t < 6.0 else 2.0
    rows_a = OUT.parent / "mrp_a.raw"
    rows_b = OUT.parent / "mrp_b.raw"
    for tt, dst in ((t, rows_a), (ref_t, rows_b)):
        r = subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", str(tt),
            "-frames:v", "1", "-vf", "scale=1:1920", "-f", "rawvideo",
            "-pix_fmt", "gray", str(dst),
        ], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
    a, b = rows_a.read_bytes(), rows_b.read_bytes()
    buckets = []
    for by in range(0, 1920, 40):
        buckets.append(sum(1 for y in range(by, min(by + 40, 1920))
                           if abs(a[y] - b[y]) > 12))
    return buckets


def main() -> None:
    results = {}
    for label, data in (("control", {}), ("burn_on", {"burn_captions": "true"})):
        st, body = upload(data)
        print(f"== {label}: POST {st} {body}", flush=True)
        entry = {"post_status": st, "post_body": body}
        if st != 202 or "job_id" not in body:
            results[label] = entry
            OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
            continue
        jid = body["job_id"]
        entry["job_id"] = jid
        diag = poll(jid)
        entry["status"] = diag.get("status")
        if diag.get("status") == "COMPLETED":
            try:
                job = httpx.get(f"{BASE}/api/jobs/{jid}", timeout=30).json()
            except Exception as e:
                job = {"err": str(e)}
            entry["job"] = job
            clips = job.get("clips") or []
            if clips:
                cid = clips[0].get("clip_id") or clips[0].get("id")
                rel = (clips[0].get("r2_url") or "").replace("/mnt/data/", "")
                src = rel if rel and not rel.startswith("http") else f"clips/{jid}_{cid}.mp4"
                dst = OUT.parent / f"modal_{label}.mp4"
                try:
                    modal_volume_get(src, dst)
                    entry["clip_download"] = src
                    entry["band_t2_vs_t7"] = band_diff_same_clip(dst, 2.0, 7.0)
                    entry["row_profile_t2_vs_t7"] = full_row_profile(dst, 2.0)
                    entry["row_profile_t4_vs_t7"] = full_row_profile(dst, 4.0)
                except Exception as e:
                    entry["clip_analysis_err"] = str(e)[:300]
        results[label] = entry
        OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
