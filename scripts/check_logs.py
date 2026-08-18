"""Get Modal logs and check for errors."""
import os
import subprocess
import sys

# Save logs to file
with open("modal_logs.txt", "w", encoding="utf-8") as f:
    result = subprocess.run(
        [sys.executable, "-m", "modal", "app", "logs", "trimaura", "--since=15m"],
        capture_output=True, text=True, timeout=30
    )
    f.write(result.stdout)
    f.write(result.stderr)

# Read back and analyze
with open("modal_logs.txt", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")
print(f"Total log lines: {len(lines)}")

# Find interesting lines
keywords = ["error", "exception", "traceback", "fail", "crash", "timeout",
            "RENDERING", "DOWNLOADING", "ANALYZING", "TRANSCRIBING",
            "pipeline", "process_", "job 24", "clip", "database", "sql"]
            
print("\n=== Relevant Log Lines ===")
for i, line in enumerate(lines):
    if any(k.lower() in line.lower() for k in keywords):
        print(f"  L{i}: {line[:300]}")

print(f"\nFile size: {os.path.getsize('modal_logs.txt')} bytes")
