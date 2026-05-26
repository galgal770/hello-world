#!/usr/bin/env python3
"""
Generate coffee_input.png – a dense circular B&W coffee composition
(pot · 'Coffee' lettering · cup · big beans · leaves · swirls)
then dilate all dark areas so thin strokes register on the stencil grid.

Usage:
    python scripts/make_coffee_image.py
Outputs:
    samples/coffee_input.png  (900×900 grayscale, ready for stencil_generator.py)
"""

import math
import os
import cairosvg
from PIL import Image, ImageFilter

SIZE = 900
CX = CY = SIZE / 2.0
CLIP_R = 420


# ── SVG helpers ───────────────────────────────────────────────────────────────

parts = []


def add(s):
    parts.append(s)


def leaf(x, y, angle_deg, length=28, width=16):
    """Filled leaf shape along given direction."""
    a = math.radians(angle_deg)
    pa = a + math.pi / 2
    tx = x + length * math.cos(a)
    ty = y + length * math.sin(a)
    mx = x + length / 2 * math.cos(a)
    my = y + length / 2 * math.sin(a)
    b1x = mx + width / 2 * math.cos(pa)
    b1y = my + width / 2 * math.sin(pa)
    b2x = mx - width / 2 * math.cos(pa)
    b2y = my - width / 2 * math.sin(pa)
    add(f'<path fill="black" d="M {x:.1f},{y:.1f} '
        f'Q {b1x:.1f},{b1y:.1f} {tx:.1f},{ty:.1f} '
        f'Q {b2x:.1f},{b2y:.1f} {x:.1f},{y:.1f} Z"/>')


def branch(cx, cy, stem_angle_deg, n=6, stem=80, llen=26, lwid=16):
    sa = math.radians(stem_angle_deg)
    ex = cx + stem * math.cos(sa)
    ey = cy + stem * math.sin(sa)
    add(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
        f'stroke="black" stroke-width="5" stroke-linecap="round"/>')
    for i in range(n):
        t = (i + 0.5) / n
        lx = cx + t * stem * math.cos(sa)
        ly = cy + t * stem * math.sin(sa)
        side = 1 if i % 2 == 0 else -1
        leaf(lx, ly, stem_angle_deg + side * 55, llen, lwid)


def coffee_bean(cx, cy, rx, ry, angle_deg):
    """Filled coffee-bean ellipse with white centre groove."""
    add(f'<g transform="rotate({angle_deg:.1f},{cx:.1f},{cy:.1f})">'
        f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx}" ry="{ry}" fill="black"/>'
        f'<line x1="{cx:.1f}" y1="{cy-ry+4:.1f}" '
        f'      x2="{cx:.1f}" y2="{cy+ry-4:.1f}" '
        f'stroke="white" stroke-width="4.5"/>'
        f'</g>')


# ── Build SVG ─────────────────────────────────────────────────────────────────

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}">')
add('<rect width="100%" height="100%" fill="white"/>')
add(f'<defs>'
    f'<clipPath id="c">'
    f'<circle cx="{CX}" cy="{CY}" r="{CLIP_R}"/>'
    f'</clipPath>'
    f'</defs>')
add('<g clip-path="url(#c)">')


# ─── COFFEE POT (top-centre, large) ──────────────────────────────────────────
px, py = CX, CY - 168

# base plate
add(f'<rect x="{px-58:.0f}" y="{py+66:.0f}" width="116" height="16" rx="8" fill="black"/>')
# body
add(f'<rect x="{px-48:.0f}" y="{py-56:.0f}" width="96" height="124" rx="20" fill="black"/>')
# lid rim
add(f'<rect x="{px-30:.0f}" y="{py-72:.0f}" width="60" height="20" rx="9" fill="black"/>')
# knob
add(f'<circle cx="{px:.0f}" cy="{py-86:.0f}" r="10" fill="black"/>')

# spout (fat filled shape)
add(f'<path fill="black" d="'
    f'M {px-48:.0f} {py-18:.0f} '
    f'C {px-92:.0f} {py-18:.0f} {px-118:.0f} {py+14:.0f} {px-104:.0f} {py+44:.0f} '
    f'L {px-86:.0f} {py+34:.0f} '
    f'C {px-97:.0f} {py+12:.0f} {px-75:.0f} {py-4:.0f} {px-48:.0f} {py-4:.0f} Z"/>')

# handle (fat C-shape)
add(f'<path fill="black" d="'
    f'M {px+48:.0f} {py-42:.0f} '
    f'C {px+90:.0f} {py-42:.0f} {px+90:.0f} {py+32:.0f} {px+48:.0f} {py+32:.0f} '
    f'L {px+48:.0f} {py+16:.0f} '
    f'C {px+70:.0f} {py+16:.0f} {px+70:.0f} {py-26:.0f} {px+48:.0f} {py-26:.0f} Z"/>')

# steam wisps
for ox, sx in [(-20, 1), (0, -1), (20, 1)]:
    spx = px + ox
    spy = py - 90
    add(f'<path stroke="black" stroke-width="6" fill="none" stroke-linecap="round" d="'
        f'M {spx:.0f} {spy:.0f} '
        f'Q {spx+sx*16:.0f} {spy-20:.0f} {spx:.0f} {spy-40:.0f} '
        f'Q {spx-sx*16:.0f} {spy-60:.0f} {spx:.0f} {spy-80:.0f}"/>')


# ─── "Coffee" LETTERING ───────────────────────────────────────────────────────
# Two lines: decorative "Coffee" + a tagline
add(f'<text x="{CX:.0f}" y="{CY+32:.0f}" '
    f'font-family="DejaVu Serif" font-size="108" font-weight="bold" '
    f'font-style="italic" text-anchor="middle" fill="black" letter-spacing="-1">'
    f'Coffee</text>')

# swash underline
add(f'<path stroke="black" stroke-width="5" fill="none" stroke-linecap="round" d="'
    f'M {CX-140:.0f} {CY+52:.0f} '
    f'Q {CX-60:.0f} {CY+72:.0f} {CX:.0f} {CY+68:.0f} '
    f'Q {CX+60:.0f} {CY+64:.0f} {CX+140:.0f} {CY+52:.0f}"/>')

# decorative swash above (top of C letter region)
add(f'<path stroke="black" stroke-width="5" fill="none" stroke-linecap="round" d="'
    f'M {CX-130:.0f} {CY-68:.0f} '
    f'Q {CX-50:.0f} {CY-90:.0f} {CX:.0f} {CY-86:.0f} '
    f'Q {CX+50:.0f} {CY-82:.0f} {CX+130:.0f} {CY-68:.0f}"/>')


# ─── COFFEE CUP (bottom-centre, larger) ──────────────────────────────────────
cpx, cpy = CX, CY + 215

# cup body
add(f'<path fill="black" d="'
    f'M {cpx-50:.0f} {cpy-48:.0f} '
    f'L {cpx+50:.0f} {cpy-48:.0f} '
    f'L {cpx+37:.0f} {cpy+42:.0f} '
    f'Q {cpx+34:.0f} {cpy+47:.0f} {cpx+30:.0f} {cpy+47:.0f} '
    f'L {cpx-30:.0f} {cpy+47:.0f} '
    f'Q {cpx-34:.0f} {cpy+47:.0f} {cpx-37:.0f} {cpy+42:.0f} Z"/>')
# rim outer
add(f'<ellipse cx="{cpx:.0f}" cy="{cpy-48:.0f}" rx="50" ry="13" fill="black"/>')
# rim inner (hollow top — white)
add(f'<ellipse cx="{cpx:.0f}" cy="{cpy-50:.0f}" rx="42" ry="8" fill="white"/>')
# handle
add(f'<path fill="black" d="'
    f'M {cpx+50:.0f} {cpy-32:.0f} '
    f'C {cpx+84:.0f} {cpy-32:.0f} {cpx+84:.0f} {cpy+22:.0f} {cpx+50:.0f} {cpy+22:.0f} '
    f'L {cpx+50:.0f} {cpy+7:.0f} '
    f'C {cpx+66:.0f} {cpy+7:.0f} {cpx+66:.0f} {cpy-17:.0f} {cpx+50:.0f} {cpy-17:.0f} Z"/>')
# saucer
add(f'<ellipse cx="{cpx:.0f}" cy="{cpy+50:.0f}" rx="70" ry="17" fill="black"/>')
add(f'<ellipse cx="{cpx:.0f}" cy="{cpy+46:.0f}" rx="58" ry="10" fill="white"/>')
add(f'<ellipse cx="{cpx:.0f}" cy="{cpy+49:.0f}" rx="70" ry="8" fill="black"/>')


# ─── LARGE COFFEE BEANS (8 scattered, matching original's big beans) ──────────
# angle_from_top°, radial_dist, rx, ry, extra_rotation
big_beans = [
    (-68,  245, 44, 27,  12),
    ( 68,  245, 44, 27, -12),
    (-118, 282, 46, 28,  58),
    ( 118, 282, 46, 28, -58),
    (  0,  270, 38, 23,   0),   # above pot
    ( 180, 250, 38, 24,   0),   # below cup
    (-150, 258, 40, 25,  28),
    ( 150, 258, 40, 25, -28),
]
for ang, dist, rx, ry, rot in big_beans:
    a = math.radians(ang - 90)
    bx = CX + dist * math.cos(a)
    by = CY + dist * math.sin(a)
    coffee_bean(bx, by, rx, ry, ang + rot)


# ─── LEAF BRANCHES (8 branches, denser) ──────────────────────────────────────
for bx_, by_, ang_ in [
    (CX - 218, CY - 148, -52),
    (CX + 218, CY - 148, -128),
    (CX - 300, CY +  50, -12),
    (CX + 300, CY +  50, -168),
    (CX - 178, CY + 270,  44),
    (CX + 178, CY + 270,  136),
    (CX - 250, CY - 200, -30),
    (CX + 250, CY - 200, -150),
]:
    branch(bx_, by_, ang_)


# ─── DECORATIVE DOTS ──────────────────────────────────────────────────────────
for dx, dy, dr in [
    (CX - 355, CY -  58, 7), (CX - 360, CY +  58, 5), (CX - 334, CY + 145, 4),
    (CX + 355, CY -  58, 7), (CX + 360, CY +  58, 5), (CX + 334, CY + 145, 4),
    (CX -  60, CY - 312, 5), (CX +  60, CY - 312, 5), (CX,       CY - 328, 6),
    (CX -  60, CY + 360, 5), (CX +  60, CY + 360, 5),
    (CX - 140, CY - 298, 4), (CX + 140, CY - 298, 4),
]:
    add(f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="{dr}" fill="black"/>')


# ─── SMALL DECORATIVE CURL / SWIRL near cup bottom ───────────────────────────
# Swirling tail under cup handle (top-right of cup area)
sx, sy = cpx + 100, cpy + 5
add(f'<path stroke="black" stroke-width="7" fill="none" stroke-linecap="round" d="'
    f'M {sx:.0f} {sy:.0f} '
    f'Q {sx+30:.0f} {sy-20:.0f} {sx+20:.0f} {sy-44:.0f} '
    f'Q {sx+6:.0f} {sy-60:.0f} {sx-12:.0f} {sy-48:.0f}"/>')


add('</g>')
add('</svg>')

svg_text = '\n'.join(parts)

# ── Write outputs ─────────────────────────────────────────────────────────────
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'samples')
os.makedirs(out_dir, exist_ok=True)

svg_path = os.path.join(out_dir, 'coffee_input.svg')
raw_png  = os.path.join(out_dir, 'coffee_input_raw.png')
png_path = os.path.join(out_dir, 'coffee_input.png')

with open(svg_path, 'w', encoding='utf-8') as fh:
    fh.write(svg_text)
print(f"Intermediate SVG → {svg_path}")

cairosvg.svg2png(bytestring=svg_text.encode(), write_to=raw_png,
                 output_width=SIZE, output_height=SIZE)

# ── Dilation: thicken all dark areas by ~1 mm so thin strokes register ────────
# PIL MinFilter(n) replaces each pixel with the minimum in its n×n neighbourhood;
# since dark = 0 (small), this expands dark areas outward — exactly morphological dilation.
DILATION_PX = 9   # ≈0.95 mm at 900px/95mm; enough to catch thin stems/strokes
img = Image.open(raw_png).convert('L')
img = img.filter(ImageFilter.MinFilter(DILATION_PX))
img.save(png_path)
print(f"PNG (dilated ×{DILATION_PX}px) → {png_path}")
