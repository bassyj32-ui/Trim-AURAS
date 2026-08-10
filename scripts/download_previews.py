"""Download lightweight template preview images for TrimAURA circular swatches."""
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join("public", "template-previews")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SIZE = "square_hd"

TEMPLATES = [
    {
        "id": "blurpad_v1",
        "prompt": "Beautiful minimalist video template with soft blurred gradient background in warm beige tones, clean modern style, soft bokeh effect, professional video editing thumbnail",
    },
    {
        "id": "brand_bold_v1",
        "prompt": "Professional corporate video template with elegant gold accents on dark background, serif typography, premium business style, clean sophisticated design",
    },
    {
        "id": "gaming_neon_v1",
        "prompt": "Vibrant gaming video template with cyan and neon magenta glow effects on dark background, cyberpunk aesthetic, esports style thumbnail",
    },
    {
        "id": "mrbeast_energy_v1",
        "prompt": "High energy viral video template with bold yellow and red colors, thick text, dramatic contrast, youtube style thumbnail with explosive energy",
    },
    {
        "id": "podcast_split_v1",
        "prompt": "Clean podcast video template with elegant frame border, warm professional lighting, microphone silhouette, talking heads format",
    },
    {
        "id": "retro_vhs_v1",
        "prompt": "Vintage retro VHS video template with scanline overlay, static noise effect, nostalgic 80s aesthetic, warm desaturated colors with yellow text",
    },
]

BASE_URL = "https://coresg-normal.trae.ai/api/ide/v1/text_to_image"

for t in TEMPLATES:
    params = urllib.parse.urlencode({
        "prompt": t["prompt"],
        "image_size": SIZE,
    })
    url = f"{BASE_URL}?{params}"
    output_path = os.path.join(OUTPUT_DIR, f"{t['id']}.jpg")
    
    print(f"Downloading {t['id']}...")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "image/webp,image/jpeg,image/*,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            with open(output_path, "wb") as f:
                f.write(data)
            size_kb = len(data) / 1024
            print(f"  ✓ Saved {t['id']}.jpg ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"  ✗ Failed for {t['id']}: {e}")

print("\nDone! All previews downloaded.")
