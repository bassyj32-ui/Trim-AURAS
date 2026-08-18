"""Generate PWA icon PNGs for TrimAURA."""
from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path("public")
ICON_BG = (0, 229, 255)  # accent cyan
ICON_FG = (7, 11, 14)    # dark text


def _generate(size: int, path: Path):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded rect background
    radius = size // 6
    d.rounded_rectangle([0, 0, size, size], radius, fill=ICON_BG)

    # Play triangle ◀
    # Center at roughly 40% of the icon, triangle pointing right
    cx, cy = size * 0.42, size * 0.5
    tri_size = size * 0.28
    pts = [
        (cx - tri_size * 0.4, cy - tri_size * 0.55),
        (cx - tri_size * 0.4, cy + tri_size * 0.55),
        (cx + tri_size * 0.5, cy),
    ]
    d.polygon(pts, fill=ICON_FG)

    # Small sparkle dot top-right
    dot_r = size * 0.06
    dx, dy = size * 0.72, size * 0.28
    d.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=ICON_FG)

    img.save(path, "PNG")
    print(f"  {path.name} ({size}x{size})")


def main():
    print("Generating PWA icons...")
    _generate(192, PUBLIC / "icon-192.png")
    _generate(512, PUBLIC / "icon-512.png")
    print("Done!")


if __name__ == "__main__":
    main()
