"""Compress template preview images to be lightweight for 52px circular swatches."""
import os
from PIL import Image

INPUT_DIR = os.path.join("public", "template-previews")
OUTPUT_DIR = INPUT_DIR

TEMPLATES = [
    "blurpad_v1",
    "brand_bold_v1",
    "gaming_neon_v1",
    "mrbeast_energy_v1",
    "podcast_split_v1",
    "retro_vhs_v1",
]

for tid in TEMPLATES:
    input_path = os.path.join(INPUT_DIR, f"{tid}.jpg")
    if not os.path.exists(input_path):
        print(f"  ✗ {tid}.jpg not found")
        continue
    
    img = Image.open(input_path)
    # Resize to very small — only used as 52px circle background
    img = img.resize((120, 120), Image.LANCZOS)
    
    output_path = os.path.join(OUTPUT_DIR, f"{tid}.jpg")
    # Save with low quality (60) for small file size
    img.save(output_path, "JPEG", quality=60, optimize=True)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f"  ✓ Compressed {tid}.jpg ({size_kb:.1f} KB)")

print("\nDone! All previews compressed.")
