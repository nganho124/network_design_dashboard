"""
Generates the warehouse marker icons used by components/map_view.py.

Run once (already run — output is committed to assets/): python3 assets/generate_icons.py

Using locally-generated icons instead of a hotlinked public icon URL avoids
another external-network dependency on top of the map tiles — worth avoiding
given we already hit one network-related issue with the tile provider.
"""

from pathlib import Path
from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).parent


def make_warehouse_icon(path: Path, color: str, outline: str = "#1a1a1a"):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    body = [(6, 30), (58, 30), (58, 56), (6, 56)]
    roof = [(2, 30), (32, 8), (62, 30)]
    door = [(27, 40), (37, 56)]  # top-left, bottom-right
    d.polygon(body, fill=color, outline=outline)
    d.polygon(roof, fill=color, outline=outline)
    d.rectangle(door, fill=outline)
    img.save(path)


if __name__ == "__main__":
    make_warehouse_icon(ASSETS_DIR / "warehouse_open.png", "#2e8b3d")   # green = open
    make_warehouse_icon(ASSETS_DIR / "warehouse_closed.png", "#888888")  # gray = closed
    print(f"Icons written to {ASSETS_DIR}")