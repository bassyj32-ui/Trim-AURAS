"""TrimAURA diag suite — generate the characteristic test-video matrix.

Requires: ffmpeg on PATH and tmp/diag/speech.wav (run scripts/diag_speech.ps1
first). Outputs go to tmp/diag/videos/. Each file targets one dimension of the
failure-isolation matrix (codec/container, resolution, duration, audio type,
file size). Rows are also written to tmp/diag_matrix.json for the runner.
"""
import json
import subprocess
import sys
from pathlib import Path

VID = Path("tmp") / "diag" / "videos"
SPEECH = Path("tmp") / "diag" / "speech.wav"
VID.mkdir(parents=True, exist_ok=True)

BASE = [
    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
]


def run(cmd: list[str]) -> None:
    print("  $", " ".join(cmd[:10]), "...")
    subprocess.run(cmd, check=True)


def speech_video(out: str, size: str, dur_s: int, codec: str, extra: list[str] | None = None,
                 crf: str = "23") -> None:
    """testsrc2 video + looped speech track."""
    cmd = BASE + [
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={dur_s}",
        "-stream_loop", "-1", "-i", str(SPEECH),
        "-t", str(dur_s),
        "-c:v", codec, "-preset", "veryfast", "-crf", crf, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart",
    ]
    if extra:
        cmd += extra
    cmd.append(str(VID / out))
    run(cmd)


def build_matrix() -> list[dict]:
    if not SPEECH.exists():
        print("MISSING speech.wav — run scripts/diag_speech.ps1 first")
        sys.exit(1)

    rows = []

    # v01 baseline: small h264 mp4, 720p, 40s speech
    speech_video("v01_small_h264_720p_40s.mp4", "1280x720", 40, "libx264")
    rows.append({"video": "v01_small_h264_720p_40s.mp4", "chars": "h264/mp4 720p 40s speech",
                 "size_class": "small (<50MB)", "note": "baseline"})

    # v02 medium: 1080p 6-min speech (h264)
    speech_video("v02_medium_h264_1080p_6min.mp4", "1920x1080", 360, "libx264")
    rows.append({"video": "v02_medium_h264_1080p_6min.mp4", "chars": "h264/mp4 1080p 6min speech",
                 "size_class": "medium (~60MB)", "note": ""})

    # v03 hevc 4K 20s (iPhone default codec/res combo)
    speech_video("v03_hevc_4k_20s.mp4", "3840x2160", 20, "libx265", crf="28")
    rows.append({"video": "v03_hevc_4k_20s.mp4", "chars": "hevc/mp4 4K 20s speech",
                 "size_class": "medium (~30MB)", "note": "iPhone default codec"})

    # v04 mov 9:16 60s (iPhone native container + vertical phone-shot res)
    speech_video("v04_mov_h264_916_60s.mov", "1080x1920", 60, "libx264")
    rows.append({"video": "v04_mov_h264_916_60s.mov", "chars": "h264/mov 1080x1920 60s speech",
                 "size_class": "small", "note": "iPhone-native container/vertical"})

    # v05 webm vp9 30s, NO audio (no-speech path)
    run(BASE + ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=30",
                "-c:v", "libvpx-vp9", "-b:v", "800k", "-deadline", "realtime", "-cpu-used", "5",
                "-row-mt", "1", str(VID / "v05_webm_vp9_720p_30s_silent.webm")])
    rows.append({"video": "v05_webm_vp9_720p_30s_silent.webm", "chars": "webm/vp9 720p 30s NO-audio",
                 "size_class": "small", "note": "7.30 no-speech fallback path"})

    # v06 music-only 30s (tone audio, no speech)
    run(BASE + ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=30",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                str(VID / "v06_music_720p_30s.mp4")])
    rows.append({"video": "v06_music_720p_30s.mp4", "chars": "h264/mp4 720p 30s music-only",
                 "size_class": "small", "note": "7.30 no-speech fallback path"})

    # v07 long 30-min 360p NO audio (duration near practical upper range, cheap encode)
    run(BASE + ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=1800",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
                str(VID / "v07_long_30min_360p_silent.mp4")])
    rows.append({"video": "v07_long_30min_360p_silent.mp4", "chars": "h264/mp4 360p 30min NO-audio",
                 "size_class": "medium (~40MB)", "note": "long duration"})

    # v08 large ~400MB: re-encode v01 at 80Mbps (40s -> ~400MB, under 500MB cap)
    src = VID / "v01_small_h264_720p_40s.mp4"
    dst = VID / "v08_large_400mb_40s.mp4"
    if dst.exists():
        dst.unlink()
    run(BASE + ["-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", "80M", "-maxrate", "90M", "-bufsize", "160M",
                "-c:a", "copy", "-movflags", "+faststart", str(dst)])
    rows.append({"video": "v08_large_400mb_40s.mp4", "chars": "h264/mp4 720p 40s speech (80Mbps)",
                 "size_class": "large (~400MB)", "note": "near 500MB upload cap"})

    # report sizes
    print("\nGenerated matrix:")
    manifest = []
    for r in rows:
        p = VID / r["video"]
        mb = round(p.stat().st_size / 1_048_576, 1) if p.exists() else -1
        r["size_mb"] = mb
        manifest.append(r)
        print(f"  {r['video']:<38} {mb:>9.1f} MB   {r['chars']}")
    (Path("tmp") / "diag_matrix.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest -> tmp/diag_matrix.json  (total {sum(r['size_mb'] for r in manifest):.0f} MB)")


if __name__ == "__main__":
    build_matrix()
