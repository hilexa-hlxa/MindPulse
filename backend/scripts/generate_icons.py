"""
One-off script that generates the PWA app icons referenced in
frontend/manifest.json (spec 7.3): icon-192.png and icon-512.png.

Draws a simple rounded-square "pulse" mark using brand colors instead
of shipping a placeholder image or an external download.

Usage:
    python backend/scripts/generate_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = "#15120F"  # matches manifest.json background_color
ACCENT = "#FF6B4A"      # matches manifest.json theme_color
LINE = "#F3EADB"

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "icons"


def draw_icon(size: int) -> Image.Image:
    scale = 4  # supersample then downscale for smoother edges
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square background.
    radius = int(big * 0.22)
    draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=BACKGROUND)

    # Concentric "pulse" rings (a simple, recognizable, license-free glyph).
    center = big // 2
    for i, ring_ratio in enumerate((0.34, 0.24, 0.14)):
        r = int(big * ring_ratio)
        width = max(int(big * 0.035), 2)
        color = ACCENT if i % 2 == 0 else LINE
        draw.ellipse(
            [center - r, center - r, center + r, center + r],
            outline=color,
            width=width,
        )

    # Solid core dot.
    dot_r = int(big * 0.07)
    draw.ellipse(
        [center - dot_r, center - dot_r, center + dot_r, center + dot_r],
        fill=LINE,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        icon = draw_icon(size)
        path = OUT_DIR / f"icon-{size}.png"
        icon.save(path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
