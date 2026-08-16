import json
import subprocess
from pathlib import Path

ROOT = Path(r"d:\trae\TrimAURAs\TrimAuras")
ENV = dict(__import__("os").environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
out = {}
r = subprocess.run(["python", "-m", "modal", "volume", "get", "trimaura-data",
                    "clips/105_139.mp4", str(ROOT / "tmp" / "dep_gm.mp4"), "--force"],
                   capture_output=True, text=True, env=ENV, timeout=600)
out["get_rc"] = r.returncode
dst = ROOT / "tmp" / "dep_gm.mp4"
if dst.exists():
    rp = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                         "stream=width,height:format=duration", "-of", "json",
                         str(dst)], capture_output=True, text=True, timeout=120)
    out["probe"] = json.loads(rp.stdout)
(ROOT / "tmp" / "gm139_probe.json").write_text(json.dumps(out, indent=1, default=str),
                                               encoding="utf-8")
print("WROTE tmp/gm139_probe.json")
