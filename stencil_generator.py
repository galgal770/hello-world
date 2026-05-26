#!/usr/bin/env python3
"""
Coffee Stencil Generator
========================
Generates an SVG file with a hole pattern sized to fit a round wooden disk
placed on top of a coffee cup.  Sprinkle cinnamon (or cocoa) through the
holes to transfer the image onto the coffee surface.

Usage
-----
  python stencil_generator.py --pattern heart
  python stencil_generator.py --pattern star   --diameter 80 --grid 50
  python stencil_generator.py --pattern flower --hole-diameter 1.0 -o flower.svg
  python stencil_generator.py --image  logo.png --invert --diameter 90

Output
------
A single .svg file.  Send it to a laser cutter or CNC router:
  • Red stroke  (#ff0000) – outer disk outline  → cut / score this line
  • Blue fill   (#0000ff) – holes               → cut / drill through here

Recommended settings for a 3 mm thin-ply or 2 mm cardboard disk:
  --diameter 88   (matches a standard espresso / cappuccino cup rim)
  --grid     40   (2.2 mm cell spacing, good balance of detail and strength)
  --hole-diameter 1.5
"""

import math
import argparse
import sys
import os

# ── Built-in pattern functions ────────────────────────────────────────────────
# Each receives (nx, ny) in normalised [-1, 1] space where the disk has r = 1.
# Return True  → drill a hole here.
# Return False → leave solid.

def pattern_heart(nx, ny):
    """Classic algebraic heart, tip pointing up."""
    x, y = nx, -ny          # flip y so tip faces upward
    return (x**2 + y**2 - 1)**3 - x**2 * y**3 < 0


def pattern_star(nx, ny, points=5, inner_r=0.38, outer_r=0.85):
    """N-point star, first tip pointing up."""
    r = math.hypot(nx, ny)
    if r > outer_r:
        return False
    # atan2(x, -y) gives 0 at the top, increasing clockwise
    angle  = math.atan2(nx, -ny)
    sector = math.pi / points           # half-sector angle (tip↔valley)
    local  = abs(angle % (2 * sector) - sector)   # 0 = valley, sector = tip
    r_edge = inner_r + (outer_r - inner_r) * (local / sector)
    return r <= r_edge


def pattern_spiral(nx, ny, turns=3, arm_width=0.14):
    """Archimedean spiral (3 arms by default)."""
    r = math.hypot(nx, ny)
    if r < 0.08 or r > 0.90:
        return False
    theta       = math.atan2(ny, nx) % (2 * math.pi)
    expected    = (r * turns * 2 * math.pi) % (2 * math.pi)
    delta       = abs(theta - expected)
    delta       = min(delta, 2 * math.pi - delta)
    arc_dist    = r * delta             # approximate arc-length distance
    return arc_dist < arm_width


def pattern_wave(nx, ny, freq=3, amp=0.35, band=0.22):
    """Sine wave band running across the disk."""
    if math.hypot(nx, ny) > 0.92:
        return False
    centre_y = amp * math.sin(nx * math.pi * freq)
    return abs(ny - centre_y) < band


def pattern_diamond(nx, ny, size=0.80):
    """Solid rotated-square (diamond) shape."""
    return abs(nx) + abs(ny) < size


def pattern_flower(nx, ny, petals=6, core=0.12, petal_r=0.45, fringe=0.12):
    """Flower with N petals and a filled centre."""
    r     = math.hypot(nx, ny)
    if r > petal_r + fringe:
        return False
    if r < core:
        return True
    angle = math.atan2(ny, nx)
    petal = petal_r * abs(math.cos(petals / 2 * angle))
    return r < petal + fringe


def pattern_circle(nx, ny, r=0.72):
    """Filled circle (simplest stencil; great for a border ring if inverted)."""
    return math.hypot(nx, ny) < r


def pattern_snowflake(nx, ny, arms=6, spoke_w=0.10, branch_l=0.28,
                      branch_w=0.07):
    """Six-armed snowflake."""
    r     = math.hypot(nx, ny)
    if r > 0.90:
        return False
    angle = math.atan2(ny, nx)
    # Angular distance to the nearest arm
    sector   = math.pi / arms
    local_a  = angle % sector
    arm_dist = r * min(local_a, sector - local_a)  # arc-length to arm axis
    if arm_dist < spoke_w * r and r < 0.88:
        return True
    # Branches: appear at multiples of branch_l from centre
    if r > branch_l * 0.5:
        branch_n  = round(r / branch_l)
        branch_r  = branch_n * branch_l
        along_arm = abs(r - branch_r)
        if along_arm < branch_w and arm_dist < branch_w * 2:
            return True
    return False


PATTERNS = {
    "heart":      pattern_heart,
    "star":       pattern_star,
    "spiral":     pattern_spiral,
    "wave":       pattern_wave,
    "diamond":    pattern_diamond,
    "flower":     pattern_flower,
    "circle":     pattern_circle,
    "snowflake":  pattern_snowflake,
}


# ── Image-based pattern ───────────────────────────────────────────────────────

def load_image_pattern(image_path, invert=False):
    """Return a pattern function derived from a greyscale image file.

    Requires Pillow:  pip install Pillow
    Dark pixels in the source image become holes (pass-through areas).
    Use --invert to swap light/dark.
    """
    try:
        from PIL import Image
    except ImportError:
        sys.exit(
            "ERROR: Pillow is required for --image mode.\n"
            "       Install it with:  pip install Pillow"
        )

    img = Image.open(image_path).convert("L")   # convert to greyscale
    w, h = img.size

    def fn(nx, ny):
        # Map normalised [-1, 1] → pixel coordinates
        px = int((nx + 1) / 2 * w)
        py = int((ny + 1) / 2 * h)
        px = max(0, min(w - 1, px))
        py = max(0, min(h - 1, py))
        brightness = img.getpixel((px, py))
        # Dark pixel (<128) → hole, unless inverted
        return (brightness < 128) != invert

    return fn


# ── SVG generation ────────────────────────────────────────────────────────────

def generate_svg(pattern_fn, diameter_mm=90.0, grid_n=40, hole_d_mm=1.5,
                 max_fill=0.20):
    """Build SVG text for the stencil.

    Parameters
    ----------
    pattern_fn   : callable(nx, ny) -> bool
    diameter_mm  : outer diameter of the wooden disk in mm
    grid_n       : number of grid cells across the full diameter
    hole_d_mm    : requested hole diameter in mm; auto-scaled down if needed
    max_fill     : maximum fraction of disk area that may be holes (default 0.20).
                   Keeps cinnamon throughput to a light, photogenic dusting.
                   Set to None to disable the cap.

    Returns
    -------
    svg_text      : str
    n_holes       : int
    fill_ratio    : float   – actual fraction of disk area occupied by holes
    actual_hole_d : float   – hole diameter used (may be < hole_d_mm if capped)
    """
    radius_mm = diameter_mm / 2.0
    disk_area = math.pi * radius_mm ** 2
    cell      = diameter_mm / grid_n
    hole_r    = hole_d_mm / 2.0

    pad    = 6.0
    canvas = diameter_mm + 2 * pad
    cx = cy = canvas / 2.0

    # Collect hole centres using the requested hole_r for the margin check.
    hole_centres = []
    for row in range(grid_n):
        for col in range(grid_n):
            mx = (col + 0.5) * cell - radius_mm
            my = (row + 0.5) * cell - radius_mm
            if math.hypot(mx, my) + hole_r > radius_mm - 0.5:
                continue
            nx = mx / radius_mm
            ny = my / radius_mm
            if pattern_fn(nx, ny):
                hole_centres.append((cx + mx, cy + my))

    n_holes = len(hole_centres)

    # ── Fill-ratio cap ────────────────────────────────────────────────────────
    # If the requested holes would push too much cinnamon through, shrink the
    # hole radius until the fill ratio hits the cap exactly.
    fill_ratio = n_holes * math.pi * hole_r ** 2 / disk_area if n_holes else 0.0
    if max_fill and n_holes and fill_ratio > max_fill:
        hole_r     = math.sqrt(max_fill * disk_area / (n_holes * math.pi))
        fill_ratio = max_fill

    actual_hole_d = hole_r * 2

    # ── SVG assembly ──────────────────────────────────────────────────────────
    cinnamon_g = fill_ratio * 3.0   # fraction of ~1 tsp (3 g) that falls through

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!-- Coffee Stencil  |  ⌀{diameter_mm} mm  |  {n_holes} holes'
        f'  |  fill {fill_ratio*100:.1f}%  |  ~{cinnamon_g:.1f} g cinnamon -->',
        f'<!-- Generated by stencil_generator.py -->',
        '<svg xmlns="http://www.w3.org/2000/svg"',
        f'     width="{canvas}mm" height="{canvas}mm"',
        f'     viewBox="0 0 {canvas} {canvas}">',
        f'  <title>Coffee Stencil – {diameter_mm} mm disk</title>',
        '',
        '  <!-- Plate outline: RED = cut/score the disk perimeter -->',
        f'  <circle cx="{cx}" cy="{cy}" r="{radius_mm}"',
        '          fill="none" stroke="#ff0000" stroke-width="0.3"/>',
        '',
        '  <!-- Holes: BLUE = cut/drill through -->',
        f'  <g fill="#0000ff" stroke="none">',
    ]

    for (hx, hy) in hole_centres:
        lines.append(f'    <circle cx="{hx:.4f}" cy="{hy:.4f}" r="{hole_r:.4f}"/>')

    lines += [
        '  </g>',
        '',
        f'  <text x="{cx}" y="{canvas - 1.5}"',
        '        text-anchor="middle" font-family="sans-serif"',
        '        font-size="2.5" fill="#999999">',
        f'    ⌀{diameter_mm} mm · {n_holes} holes · hole ⌀{actual_hole_d:.2f} mm'
        f' · fill {fill_ratio*100:.1f}% · ~{cinnamon_g:.1f} g cinnamon',
        '  </text>',
        '</svg>',
    ]

    return '\n'.join(lines), n_holes, fill_ratio, actual_hole_d


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="stencil_generator.py",
        description="Generate a laser-cut / CNC coffee stencil SVG.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap_dedent("""
            Built-in patterns:  heart, star, spiral, wave,
                                diamond, flower, circle, snowflake

            Examples
            --------
              # Heart at default 90 mm, saved to heart_stencil.svg
              python stencil_generator.py --pattern heart

              # Fine 5-point star at 80 mm, higher grid resolution
              python stencil_generator.py --pattern star --diameter 80 --grid 55

              # Flower with tiny holes, custom output filename
              python stencil_generator.py --pattern flower --hole-diameter 1.0 -o flower.svg

              # Custom image (requires Pillow)
              python stencil_generator.py --image logo.png --invert --diameter 90

              # List all built-in patterns
              python stencil_generator.py --list-patterns
        """),
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pattern", choices=sorted(PATTERNS),
        help="Built-in pattern to use",
    )
    group.add_argument(
        "--image", metavar="FILE",
        help="Path to an image file (requires Pillow).  Dark areas become holes.",
    )
    group.add_argument(
        "--list-patterns", action="store_true",
        help="Print all available built-in pattern names and exit.",
    )

    parser.add_argument(
        "--diameter", type=float, default=90.0, metavar="MM",
        help="Outer disk diameter in mm (default: 90)",
    )
    parser.add_argument(
        "--grid", type=int, default=40, metavar="N",
        help="Grid resolution – cells across the diameter (default: 40).  "
             "Higher = finer detail, more holes.",
    )
    parser.add_argument(
        "--hole-diameter", dest="hole_d", type=float, default=1.5, metavar="MM",
        help="Diameter of each hole in mm (default: 1.5)",
    )
    parser.add_argument(
        "--invert", action="store_true",
        help="Invert the pattern (swap hole and solid areas)",
    )
    parser.add_argument(
        "--max-fill", dest="max_fill", type=float, default=0.20, metavar="RATIO",
        help="Max fraction of disk area that may be holes (default: 0.20). "
             "Hole diameter is auto-scaled down to meet this cap, keeping "
             "cinnamon throughput to a light, photogenic dusting (~0.6 g at 20%%).",
    )
    parser.add_argument(
        "--output", "-o", metavar="FILE",
        help="Output SVG filename (default: <pattern>_stencil.svg)",
    )

    args = parser.parse_args()

    # --list-patterns
    if args.list_patterns:
        print("Available built-in patterns:")
        for name in sorted(PATTERNS):
            print(f"  {name}")
        return

    # Require --pattern or --image
    if args.pattern is None and args.image is None:
        parser.error("Specify --pattern <name> or --image <file> (or --list-patterns).")

    # Build the pattern function
    if args.image:
        pattern_fn  = load_image_pattern(args.image, invert=args.invert)
        default_out = os.path.splitext(os.path.basename(args.image))[0] + "_stencil.svg"
        label       = os.path.basename(args.image)
    else:
        base_fn = PATTERNS[args.pattern]
        if args.invert:
            pattern_fn = lambda nx, ny, _f=base_fn: not _f(nx, ny)
        else:
            pattern_fn = base_fn
        default_out = f"{args.pattern}_stencil.svg"
        label       = args.pattern

    out_path = args.output or default_out

    # Generate
    svg_text, n_holes, fill_ratio, actual_hole_d = generate_svg(
        pattern_fn,
        diameter_mm=args.diameter,
        grid_n=args.grid,
        hole_d_mm=args.hole_d,
        max_fill=args.max_fill,
    )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(svg_text)

    cell_mm      = args.diameter / args.grid
    cinnamon_g   = fill_ratio * 3.0
    scaled_note  = (f"  (auto-scaled from ⌀{args.hole_d} mm to stay within "
                    f"{args.max_fill*100:.0f}% fill cap)"
                    if actual_hole_d < args.hole_d - 0.01 else "")
    print(
        f"Saved:  {out_path}\n"
        f"  Pattern    : {label}\n"
        f"  Disk       : ⌀{args.diameter} mm\n"
        f"  Grid       : {args.grid}×{args.grid}  ({cell_mm:.1f} mm/cell)\n"
        f"  Holes      : {n_holes}  (⌀{actual_hole_d:.2f} mm each){scaled_note}\n"
        f"  Fill ratio : {fill_ratio*100:.1f}%  →  ~{cinnamon_g:.1f} g cinnamon per dusting\n"
    )


def textwrap_dedent(s):
    """Lightweight dedent so we don't need to import textwrap."""
    lines  = s.splitlines()
    indent = min(
        (len(l) - len(l.lstrip()) for l in lines if l.strip()),
        default=0,
    )
    return "\n".join(l[indent:] for l in lines)


if __name__ == "__main__":
    main()
