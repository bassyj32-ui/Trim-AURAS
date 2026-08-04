"""Run diag_record_rows and capture result + errors to a file."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
r = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "diag_record_rows.py")],
    capture_output=True, text=True, timeout=600,
)
(ROOT / "tmp" / "record_rows_result.txt").write_text(
    f"exit={r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr[:2000]}",
    encoding="utf-8")
