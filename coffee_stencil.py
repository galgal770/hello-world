"""
Image -> laser-cut coffee stencil (SVG) — paddle shape.

The stencil has two parts:
  - a circular body that holds the halftone dot pattern, and
  - a handle protruding to the left for gripping/aligning the stencil.

Defaults match the user-supplied chart: 95 mm body, 146 mm total width
(51 mm of handle), 12 mm rounded tip on the handle.

The outer path is a single closed curve: handle-tip arc (left semicircle),
two cubic Bezier curves joining the tip to the body tangentially, and the
body's major arc closing the loop. Dots only appear inside the body
circle, never in the handle.

Usage:
    python coffee_stencil.py input.png output.svg
    python coffee_stencil.py heart.png heart.svg --diameter 95 --handle-length 51
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageOps


SVG_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="{w}mm" height="{h}mm" '
    'viewBox="0 0 {w} {h}" '
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
    half = cell_px / 2.0
    left = max(0, int(cx - half))
    top = max(0, int(cy - half))
    right = min(img.width, int(cx + half) + 1)
    bottom = min(img.height, int(cy + half) + 1)
    if right <= left or bottom <= top:
        return 0.0
    region = img.crop((left, top, right, bottom))
    pixels = list(region.tobytes())
    mean = sum(pixels) / len(pixels)
    return 1.0 - mean / 255.0


def generate_dots(
    img: Image.Image,
    body_cx: float,
    body_cy: float,
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
        y_local = offset + row * grid_mm
        y_mm = body_cy - radius_mm + y_local
        x_shift = (grid_mm / 2.0) if row % 2 else 0.0
        for col in range(n):
            x_local = offset + col * grid_mm + x_shift
            x_mm = body_cx - radius_mm + x_local
            dx = x_mm - body_cx
            dy = y_mm - body_cy
            if dx * dx + dy * dy > usable_radius * usable_radius:
                continue
            img_x = x_local * px_per_mm
            img_y = y_local * px_per_mm
            darkness = sample_darkness(img, img_x, img_y, grid_mm * px_per_mm)
            if darkness <= 0.08:
                continue
            r = min_r + (max_r - min_r) * darkness
            dots.append((x_mm, y_mm, r))
    return dots


def make_paddle_outline_path(
    diameter_mm: float,
    handle_length_mm: float,
    handle_tip_r_mm: float = 12.0,
    join_angle_deg: float = 30.0,
    k_tip: float = 12.0,
    k_body: float = 20.0,
) -> str:
    """SVG path 'd' string for the paddle outline.

    Geometry: body circle on the right, handle protruding to the left.
    Handle tip is a small circle that connects to the body via two cubic
    Beziers that are tangent to both circles. Body is closed with its own
    major arc (>180°).
    """
    R = diameter_mm / 2.0
    total_w = diameter_mm + handle_length_mm
    cy = R
    body_cx = total_w - R
    tip_cx = handle_tip_r_mm

    tip_top = (tip_cx, cy - handle_tip_r_mm)
    tip_bot = (tip_cx, cy + handle_tip_r_mm)

    phi = math.radians(join_angle_deg)
    sin_p, cos_p = math.sin(phi), math.cos(phi)
    body_join_top = (body_cx - R * cos_p, cy - R * sin_p)
    body_join_bot = (body_cx - R * cos_p, cy + R * sin_p)

    # Top edge bezier: tip_top -> body_join_top, going clockwise around outline.
    # Tangent at tip_top going right: (1, 0)
    # Tangent at body_join_top approaching the body arc: (sin_p, -cos_p)
    cp1_top = (tip_top[0] + k_tip, tip_top[1])
    cp2_top = (body_join_top[0] - k_body * sin_p,
               body_join_top[1] + k_body * cos_p)

    # Bottom edge bezier: body_join_bot -> tip_bot, going clockwise.
    # Tangent leaving body at body_join_bot: (-sin_p, -cos_p)
    # Tangent at tip_bot going left: (-1, 0)
    cp1_bot = (body_join_bot[0] - k_body * sin_p,
               body_join_bot[1] - k_body * cos_p)
    cp2_bot = (tip_bot[0] + k_tip, tip_bot[1])

    parts: list[str] = []
    parts.append(f"M {tip_top[0]:.3f} {tip_top[1]:.3f}")
    parts.append(
        f"C {cp1_top[0]:.3f} {cp1_top[1]:.3f} "
        f"{cp2_top[0]:.3f} {cp2_top[1]:.3f} "
        f"{body_join_top[0]:.3f} {body_join_top[1]:.3f}"
    )
    # Body major arc (sweep=1 clockwise, large=1 since >180°)
    parts.append(
        f"A {R:.3f} {R:.3f} 0 1 1 "
        f"{body_join_bot[0]:.3f} {body_join_bot[1]:.3f}"
    )
    parts.append(
        f"C {cp1_bot[0]:.3f} {cp1_bot[1]:.3f} "
        f"{cp2_bot[0]:.3f} {cp2_bot[1]:.3f} "
        f"{tip_bot[0]:.3f} {tip_bot[1]:.3f}"
    )
    # Tip semicircle on the left (sweep=1 clockwise = goes around the left)
    parts.append(
        f"A {handle_tip_r_mm:.3f} {handle_tip_r_mm:.3f} 0 0 1 "
        f"{tip_top[0]:.3f} {tip_top[1]:.3f}"
    )
    parts.append("Z")
    return " ".join(parts)


def write_svg(
    path: Path,
    diameter_mm: float,
    handle_length_mm: float,
    dots: list[tuple[float, float, float]],
    handle_tip_r_mm: float,
    join_angle_deg: float,
) -> None:
    total_w = diameter_mm + handle_length_mm
    parts = [SVG_HEADER.format(w=f"{total_w:.3f}", h=f"{diameter_mm:.3f}")]
    outline = make_paddle_outline_path(
        diameter_mm, handle_length_mm, handle_tip_r_mm, join_angle_deg
    )
    parts.append(f'  <path d="{outline}" />\n')
    for x, y, r in dots:
        parts.append(f'  <circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}" />\n')
    parts.append(SVG_FOOTER)
    path.write_text("".join(parts))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--diameter", type=float, default=95.0,
                   help="Body circle Ø mm (chart: 95).")
    p.add_argument("--handle-length", type=float, default=51.0,
                   help="Handle protrusion mm beyond body (chart: 51, total 146).")
    p.add_argument("--handle-tip-r", type=float, default=12.0,
                   help="Handle tip semicircle radius mm.")
    p.add_argument("--join-angle", type=float, default=30.0,
                   help="Angle (deg) from body-leftmost where handle joins body.")
    p.add_argument("--grid", type=float, default=1.6, help="Halftone cell size mm.")
    p.add_argument("--min-hole", type=float, default=0.4, help="Smallest hole Ø mm.")
    p.add_argument("--max-hole", type=float, default=0.7, help="Largest hole Ø mm.")
    p.add_argument("--margin", type=float, default=3.0,
                   help="Blank margin between dots and body edge mm.")
    p.add_argument("--sample-px", type=int, default=1200,
                   help="Internal raster size for the input image.")
    args = p.parse_args()

    R = args.diameter / 2.0
    total_w = args.diameter + args.handle_length
    body_cx = total_w - R
    body_cy = R

    img = load_grayscale(args.input, args.sample_px)
    dots = generate_dots(
        img, body_cx, body_cy,
        args.diameter, args.grid, args.min_hole, args.max_hole, args.margin,
    )
    write_svg(
        args.output, args.diameter, args.handle_length, dots,
        args.handle_tip_r, args.join_angle,
    )
    print(f"Wrote {len(dots)} holes to {args.output}")


if __name__ == "__main__":
    main()
