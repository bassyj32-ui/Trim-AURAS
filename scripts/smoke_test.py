"""Backend smoke test — verifies API, templates, static files, and DB work."""
import sys
import os
import time
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1
        print(f"  ✗ {name}: {e}")

def fetch(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()

# ---------- Static Files ----------
def test_static_css():
    status, data = fetch("/styles.css")
    assert status == 200, f"Expected 200, got {status}"
    assert b"--bg:#EDE9E3" in data, "Missing warm cream CSS variable"

def test_static_html():
    status, data = fetch("/")
    assert status == 200, f"Expected 200, got {status}"
    assert b"TrimAURA" in data, "Missing title"
    assert b"template-previews" in data, "Missing template preview references"
    assert b"style-chip" in data, "Missing circular chip classes"

def test_template_preview():
    status, data = fetch("/template-previews/blurpad_v1.jpg")
    assert status == 200, f"Blur Pad preview missing: {status}"

def test_template_preview_brand():
    status, data = fetch("/template-previews/brand_bold_v1.jpg")
    assert status == 200, f"Brand preview missing: {status}"

def test_template_preview_gaming():
    status, data = fetch("/template-previews/gaming_neon_v1.jpg")
    assert status == 200, f"Gaming preview missing: {status}"

def test_manifest():
    status, data = fetch("/manifest.json")
    assert status == 200
    assert b"#EDE9E3" in data, "Manifest background not updated"

# ---------- API Endpoints ----------
def test_api_templates():
    status, data = fetch("/api/templates")
    assert status == 200
    templates = json.loads(data)
    assert len(templates) >= 4, f"Expected 4+ templates, got {len(templates)}"

def test_api_jobs_list():
    status, data = fetch("/api/jobs")
    assert status == 200
    jobs = json.loads(data)
    assert isinstance(jobs, list)

def test_api_clips_list():
    status, data = fetch("/api/clips")
    assert status == 200
    clips = json.loads(data)
    assert isinstance(clips, list)

# ---------- Run Tests ----------
print("=== TrimAURA Backend Smoke Test ===\n")

test("styles.css serves with warm cream palette", test_static_css)
test("index.html serves with new classes", test_static_html)
test("Blur Pad preview image (1.3KB)", test_template_preview)
test("Brand Bold preview image", test_template_preview_brand)
test("Gaming Neon preview image", test_template_preview_gaming)
test("manifest.json has updated background", test_manifest)
test("GET /api/templates returns templates", test_api_templates)
test("GET /api/jobs returns list", test_api_jobs_list)
test("GET /api/clips returns list", test_api_clips_list)

print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
sys.exit(0 if FAIL == 0 else 1)
