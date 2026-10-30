"""Generates application logo SVG, multi-size Windows .ico, and seeds default machine/pen JSON profiles."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PIL import Image, ImageDraw
from app.machine.profiles import ProfileManager


LOGO_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="12" y="12" width="232" height="232" rx="44" fill="#14171A" stroke="#2B313A" stroke-width="6"/>
  <!-- Build Plate Grid -->
  <rect x="44" y="44" width="168" height="168" rx="14" fill="#1B1F24" stroke="#22C55E" stroke-width="3" stroke-opacity="0.45"/>
  <line x1="100" y1="44" x2="100" y2="212" stroke="#262C34" stroke-width="2"/>
  <line x1="156" y1="44" x2="156" y2="212" stroke="#262C34" stroke-width="2"/>
  <line x1="44" y1="100" x2="212" y2="100" stroke="#262C34" stroke-width="2"/>
  <line x1="44" y1="156" x2="212" y2="156" stroke="#262C34" stroke-width="2"/>
  <!-- Plotted Trajectory Curve -->
  <path d="M 64 184 C 84 116, 128 192, 156 124" fill="none" stroke="#22C55E" stroke-width="8" stroke-linecap="round"/>
  <!-- Precision Pen Nib / Toolhead -->
  <polygon points="156,124 180,68 202,90" fill="#22C55E"/>
  <polygon points="180,68 194,54 216,76 202,90" fill="#E2E8F0"/>
  <circle cx="64" cy="184" r="7" fill="#38BDF8"/>
</svg>
"""


def build_icon_ico(output_ico: Path) -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded dark graphite badge
    draw.rounded_rectangle([12, 12, 244, 244], radius=44, fill=(20, 23, 26, 255), outline=(45, 52, 62, 255), width=6)
    # Build plate inner frame
    draw.rounded_rectangle([44, 44, 212, 212], radius=16, fill=(27, 31, 36, 255), outline=(34, 197, 94, 150), width=4)

    # Subtle grid lines
    for pos in (100, 156):
        draw.line([(pos, 48), (pos, 208)], fill=(40, 46, 54, 255), width=2)
        draw.line([(48, pos), (208, pos)], fill=(40, 46, 54, 255), width=2)

    # Plotted trajectory line
    pts = [(64, 184), (96, 148), (124, 162), (156, 124)]
    draw.line(pts, fill=(34, 197, 94, 255), width=10, joint="curve")

    # Pen body & nib
    draw.polygon([(156, 124), (182, 68), (204, 90)], fill=(34, 197, 94, 255))
    draw.polygon([(182, 68), (198, 52), (220, 74), (204, 90)], fill=(226, 232, 240, 255))

    # Origin dot
    draw.ellipse([55, 175, 73, 193], fill=(56, 189, 248, 255))

    output_ico.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        output_ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    img.save(output_ico.with_suffix(".png"), format="PNG")


def main() -> None:
    res_dir = ROOT_DIR / "app" / "resources"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "logo.svg").write_text(LOGO_SVG, encoding="utf-8")
    build_icon_ico(res_dir / "icon.ico")

    # Seed default profiles
    pm = ProfileManager(ROOT_DIR / "profiles")
    print(f"Assets generated. Seeded {len(pm.machines)} machine(s) and {len(pm.pens)} pen profile(s).")


if __name__ == "__main__":
    main()
