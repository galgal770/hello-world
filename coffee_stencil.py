"""
Image -> laser-cut coffee stencil (SVG).

Converts a raster image into a halftone dot pattern sized for a circular
stencil that sits on top of a coffee cup. Output is an SVG in real-world
millimetres, ready for LightBurn / xTool / Glowforge / RDWorks.

Usage:
    python coffee_stencil.py input.png output.svg \
        --diameter 80 --grid 1.6 --min-hole 0.4 --max-hole 0.7

Design notes:
- Dots (round holes) are used instead of arbitrary shapes so every feature
  is self-supporting: there are no enclosed islands that fall out when cut.
- Cinnamon/cocoa flows reliably through holes >= ~0.35 mm; below that the
  powder bridges and the dot prints as blank. Keep --min-hole >= 0.35.
- Max hole radius is capped below grid/2 so neighbouring holes never merge
  into slots (which would also drop out of the stencil).
- Outer ring is drawn as the cut boundary; add registration notches if your
  shaker cap needs keyed alignment.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


SVG_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="{size}mm" height="{size}mm" '
    'viewBox="0 0 {size} {size}" '
    'stroke="#FF0000" fill="none" stroke-width="0.05">\n'
)
SVG_FOOTER = "</svg>\n"


def load_grayscale(path: Path, box_px: int) -> Image.Image:
    img = Image.open(path).convert("L")
    img = ImageOps.exif_transpose(img)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageOps.fit(img, (box_px, box_px), method=Image.LANCZOS)
    return img


def sample_darkness(img: Image.Image, cx: float, cy: float, cell_px: float) -> float:
    """Average darkness (0..1) in a square cell centred at (cx, cy)."""
    half = cell_px / 2.0
    left = max(0, int(cx - half))
    top = max(0, int(cy - half))
    right = min(img.width, int(cx + half) + 1)
    bottom = min(img.height, int(cy + half) + 1)
    if right <= left or bottom <= top:
        return 0.0
    region = img.crop((left, top, right, bottom))
    mean = sum(region.getdata()) / (region.width * region.height)
    return 1.0 - mean / 255.0


def generate_dots(
    img: Image.Image,
    diameter_mm: float,
    grid_mm: float,
    min_hole_mm: float,
    max_hole_mm: float,
    margin_mm: float,
) -> list[tuple[float, float, float]]:
    radius_mm = diameter_mm / 2.0
    usable_radius = radius_mm - margin_mm
    px_per_mm = img.width / diameter_mm

    min_r = min_hole_mm / 2.0
    max_r = min(max_hole_mm / 2.0, grid_mm / 2.0 - 0.1)
    if max_r <= min_r:
        raise ValueError("max-hole must exceed min-hole and fit within grid.")

    dots: list[tuple[float, float, float]] = []
    n = int(diameter_mm / grid_mm)
    offset = (diameter_mm - n * grid_mm) / 2.0 + grid_mm / 2.0

    for row in range(n):
        y_mm = offset + row * grid_mm
        # Hex packing: every other row shifted half a cell for denser, nicer dots.
        x_shift = (grid_mm / 2.0) if row % 2 else 0.0
        for col in range(n):
            x_mm = offset + col * grid_mm + x_shift
            dx = x_mm - radius_mm
            dy = y_mm - radius_mm
            if dx * dx + dy * dy > usable_radius * usable_radius:
                continue
            darkness = sample_darkness(
                img, x_mm * px_per_mm, y_mm * px_per_mm, grid_mm * px_per_mm
            )
            if darkness <= 0.08:
                continue
            r = min_r + (max_r - min_r) * darkness
            dots.append((x_mm, y_mm, r))
    return dots


def write_svg(
    path: Path,
    diameter_mm: float,
    dots: list[tuple[float, float, float]],
    registration_notch: bool,
) -> None:
    r = diameter_mm / 2.0
    parts = [SVG_HEADER.format(size=f"{diameter_mm:.3f}")]
    parts.append(f'  <circle cx="{r}" cy="{r}" r="{r - 0.1:.3f}" />\n')
    if registration_notch:
        # Two small V-notches at 12 and 6 o'clock so the shaker cap keys in.
        notch = 1.5
        parts.append(
            f'  <path d="M {r - notch} 0 L {r} {notch} L {r + notch} 0 Z" />\n'
        )
        parts.append(
            f'  <path d="M {r - notch} {diameter_mm} '
            f'L {r} {diameter_mm - notch} L {r + notch} {diameter_mm} Z" />\n'
        )
    for x, y, radius in dots:
        parts.append(f'  <circle cx="{x:.3f}" cy="{y:.3f}" r="{radius:.3f}" />\n')
    parts.append(SVG_FOOTER)
    path.write_text("".join(parts))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--diameter", type=float, default=80.0, help="Stencil OD in mm.")
    p.add_argument("--grid", type=float, default=1.6, help="Halftone cell size in mm.")
    p.add_argument("--min-hole", type=float, default=0.4, help="Smallest hole Ø mm.")
    p.add_argument("--max-hole", type=float, default=0.7, help="Largest hole Ø mm.")
    p.add_argument("--margin", type=float, default=3.0, help="Blank ring near edge mm.")
    p.add_argument("--no-notch", action="store_true", help="Disable keying notches.")
    p.add_argument("--sample-px", type=int, default=1200, help="Internal raster size.")
    args = p.parse_args()

    img = load_grayscale(args.input, args.sample_px)
    dots = generate_dots(
        img,
        args.diameter,
        args.grid,
        args.min_hole,
        args.max_hole,
        args.margin,
    )
    write_svg(args.output, args.diameter, dots, not args.no_notch)
    print(f"Wrote {len(dots)} holes to {args.output}")


if __name__ == "__main__":
    main()
