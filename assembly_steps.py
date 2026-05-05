"""4-panel step-by-step assembly diagram for the mason-jar MVP.

Mason jar lids are guaranteed to be two separate pieces (ring + insert),
so this approach has no parts-uncertainty: every standard jar in the world
lets you stack your own discs under the ring.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/home/user/hello-world/assembly_steps.png")

W, H = 1600, 1280
PANEL_W, PANEL_H = 720, 580
MARGIN = 40

OUTLINE = (55, 55, 60)
INK = (35, 35, 40)
GLASS = (252, 254, 255)        # mason jar body (clear glass, near white)
GLASS_DARK = (210, 218, 224)
STEEL = (232, 232, 236)
STEEL_DARK = (185, 185, 190)
CINNAMON = (170, 100, 55)
CINNAMON_DARK = (135, 75, 40)
SILICONE = (190, 150, 110)
SILICONE_DARK = (140, 100, 70)
COFFEE = (35, 22, 14)
WOOD = (160, 95, 55)
WOOD_DARK = (115, 65, 35)
ARROW = (210, 70, 70)
BG = (252, 251, 248)

STROKE = 3
FONT_NUM = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
FONT_CAPTION = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
FONT_LABEL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
FONT_TITLE_BIG = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)


# ---------- helpers ----------

def panel_origin(idx: int) -> tuple[int, int]:
    col = idx % 2
    row = idx // 2
    return (MARGIN + col * (PANEL_W + MARGIN), 100 + row * (PANEL_H + MARGIN))


def draw_panel_frame(d, ox, oy, num, title, caption):
    d.rectangle((ox, oy, ox + PANEL_W, oy + PANEL_H),
                outline=OUTLINE, width=2, fill=BG)
    d.ellipse((ox + 18, oy + 18, ox + 78, oy + 78), fill=INK)
    d.text((ox + 32, oy + 24), str(num), fill=(255, 255, 255), font=FONT_NUM)
    d.text((ox + 96, oy + 30), title, fill=INK, font=FONT_TITLE)
    d.text((ox + 24, oy + PANEL_H - 40), caption, fill=INK, font=FONT_CAPTION)


def straight_arrow(d, x0, y0, x1, y1, color=ARROW, width=4, head=14):
    d.line((x0, y0, x1, y1), fill=color, width=width)
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1:
        return
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    p1 = (x1, y1)
    p2 = (x1 - ux * head + nx * head * 0.5, y1 - uy * head + ny * head * 0.5)
    p3 = (x1 - ux * head - nx * head * 0.5, y1 - uy * head - ny * head * 0.5)
    d.polygon([p1, p2, p3], fill=color)


def draw_label(d, x, y, text):
    d.multiline_text((x, y), text, fill=INK, font=FONT_LABEL, spacing=2)


# ---------- part primitives ----------

def mason_jar(d, cx, base_y, body_w=180, body_h=260, with_cinnamon=True,
              cin_frac=0.35, with_lid=False, ring_h=22):
    """Draw a mason jar with body, shoulder, threaded neck, mouth ellipse."""
    L = cx - body_w // 2
    R = cx + body_w // 2
    T = base_y - body_h
    neck_w = body_w - 38
    Ln = cx - neck_w // 2
    Rn = cx + neck_w // 2
    neck_h = 32
    shoulder_h = 18
    straight_top = base_y - body_h + neck_h + shoulder_h
    neck_bot = straight_top - shoulder_h
    neck_top = neck_bot - neck_h
    ry = 14
    ry_neck = max(8, int(ry * neck_w / body_w))

    # straight body section
    d.rectangle((L, straight_top, R, base_y), outline=OUTLINE, width=STROKE,
                fill=GLASS)
    d.arc((L, base_y - ry, R, base_y + ry), 0, 180, fill=OUTLINE, width=STROKE)

    # shoulder taper
    d.polygon([(L, straight_top), (Ln, neck_bot),
               (Rn, neck_bot), (R, straight_top)], fill=GLASS)
    d.line((L, straight_top, Ln, neck_bot), fill=OUTLINE, width=STROKE)
    d.line((R, straight_top, Rn, neck_bot), fill=OUTLINE, width=STROKE)

    # neck (vertical sides)
    d.rectangle((Ln, neck_top, Rn, neck_bot), fill=GLASS)
    d.line((Ln, neck_top, Ln, neck_bot), fill=OUTLINE, width=STROKE)
    d.line((Rn, neck_top, Rn, neck_bot), fill=OUTLINE, width=STROKE)

    # thread lines on neck
    for y in (neck_top + 8, neck_top + 16, neck_top + 24):
        d.line((Ln + 3, y, Rn - 3, y), fill=OUTLINE, width=1)

    # mouth ellipse (open top)
    if not with_lid:
        d.ellipse((Ln, neck_top - ry_neck, Rn, neck_top + ry_neck),
                  outline=OUTLINE, width=STROKE, fill=GLASS_DARK)
    else:
        # ring sits on top
        d.ellipse((Ln - 6, neck_top - ry_neck - ring_h,
                   Rn + 6, neck_top - ry_neck - ring_h + 12),
                  outline=OUTLINE, width=STROKE, fill=STEEL_DARK)
        d.rectangle((Ln - 6, neck_top - ry_neck - ring_h + 6,
                     Rn + 6, neck_top - ry_neck + 6),
                    outline=OUTLINE, width=STROKE, fill=STEEL)
        d.arc((Ln - 6, neck_top - ry_neck, Rn + 6, neck_top - ry_neck + 12),
              0, 180, fill=OUTLINE, width=STROKE)

    # cinnamon level
    if with_cinnamon:
        cin_top_y = base_y - int(body_h * cin_frac)
        d.rectangle((L + 3, cin_top_y, R - 3, base_y - 1), fill=CINNAMON)
        d.line((L + 3, cin_top_y, R - 3, cin_top_y),
               fill=CINNAMON_DARK, width=2)

    return cx, neck_top, neck_w, ry_neck


def mason_ring(d, cx, cy, w=210, h=22, ry=12):
    """Standalone metal ring (the screw-on band) seen 3/4 from the front."""
    L = cx - w // 2
    R = cx + w // 2
    T = cy - h // 2
    B = cy + h // 2
    d.rectangle((L, T, R, B), outline=OUTLINE, width=STROKE, fill=STEEL)
    d.ellipse((L, T - ry, R, T + ry), outline=OUTLINE, width=STROKE,
              fill=STEEL_DARK)
    d.arc((L, B - ry, R, B + ry), 0, 180, fill=OUTLINE, width=STROKE)
    # rolled lip
    d.line((L + 1, T + 5, R - 1, T + 5), fill=OUTLINE, width=1)


def mesh_disc(d, cx, cy, w=200, ry=14):
    """A flat disc viewed 3/4 with mesh dots covering it."""
    L = cx - w // 2
    R = cx + w // 2
    d.ellipse((L, cy - ry, R, cy + ry), outline=OUTLINE, width=STROKE,
              fill=STEEL_DARK)
    # mesh dots
    for i in range(L + 6, R - 6, 7):
        for j in range(cy - ry + 3, cy + ry - 3, 5):
            u = (i - cx) / (w / 2 - 4)
            v = (j - cy) / (ry - 2)
            if u * u + v * v <= 1.0:
                d.ellipse((i, j, i + 1.6, j + 1.6), fill=OUTLINE)


def stencil_disc(d, cx, cy, w=200, ry=14, show_heart=True):
    """A flat stencil disc with heart-pattern dot holes."""
    L = cx - w // 2
    R = cx + w // 2
    d.ellipse((L, cy - ry, R, cy + ry), outline=OUTLINE, width=STROKE, fill=STEEL)
    if not show_heart:
        return
    rxh = w * 0.22
    ryh = ry * 0.55
    for u_i in range(-12, 13):
        for v_i in range(-6, 7):
            u = u_i / 12
            v = v_i / 6
            x, y = u, -v
            val = (x * x + y * y - 1) ** 3 - x * x * y * y * y
            if val <= 0 and u * u + v * v < 1.1:
                px = cx + u * rxh
                py = cy + v * ryh
                d.ellipse((px - 1.5, py - 1.5, px + 1.5, py + 1.5), fill=INK)


def silicone_band(d, cx, cy, w=230, h=20, ry=10):
    """A flexible O-ring style band, seen 3/4."""
    L = cx - w // 2
    R = cx + w // 2
    T = cy - h // 2
    B = cy + h // 2
    d.rectangle((L, T, R, B), fill=SILICONE)
    d.ellipse((L, T - ry, R, T + ry), outline=OUTLINE, width=STROKE,
              fill=SILICONE)
    d.arc((L, B - ry, R, B + ry), 0, 180, fill=OUTLINE, width=STROKE)
    d.line((L, T, L, B), fill=OUTLINE, width=STROKE)
    d.line((R, T, R, B), fill=OUTLINE, width=STROKE)


def mug(d, cx, base_y, w=260, h=210):
    """Wooden mug silhouette."""
    L = cx - w // 2
    R = cx + w // 2
    T = base_y - h
    flare = 18
    d.polygon([(L - flare, T), (R + flare, T), (R, base_y), (L, base_y)],
              outline=OUTLINE, width=STROKE, fill=WOOD)
    d.ellipse((L - flare, T - 18, R + flare, T + 18),
              outline=OUTLINE, width=STROKE, fill=WOOD_DARK)
    # handle
    d.ellipse((R + flare - 8, T + 36, R + flare + 70, T + 140),
              outline=OUTLINE, width=STROKE, fill=WOOD)
    d.ellipse((R + flare + 14, T + 60, R + flare + 50, T + 116),
              fill=BG, outline=OUTLINE, width=STROKE)


# ---------- panels ----------

def panel1(d, ox, oy):
    draw_panel_frame(d, ox, oy, 1, "Fill the jar with cinnamon",
                     "Use a regular-mouth mason jar. Fill ~1/3 full.")
    cx = ox + PANEL_W // 2 + 30
    base_y = oy + PANEL_H - 90
    mason_jar(d, cx, base_y, body_w=180, body_h=300, with_cinnamon=True,
              cin_frac=0.35)
    # downward arrow into the mouth
    straight_arrow(d, cx, oy + 130, cx, base_y - 300 + 4)
    # cinnamon dust particles falling near the arrow
    rng_pts = [(cx - 14, oy + 200), (cx + 8, oy + 220), (cx - 4, oy + 180),
               (cx + 18, oy + 240), (cx - 22, oy + 240)]
    for px, py in rng_pts:
        d.ellipse((px, py, px + 3, py + 3), fill=CINNAMON_DARK)
    # labels
    draw_label(d, ox + 50, oy + 160,
               "any standard\nregular-mouth\nmason jar\n(70 mm opening)")
    draw_label(d, ox + 50, oy + PANEL_H - 200, "cinnamon\ninside")


def panel2(d, ox, oy):
    draw_panel_frame(d, ox, oy, 2, "Stack mesh + stencil, screw ring on",
                     "Mesh disc first (touches cinnamon), stencil on top, then ring.")
    cx = ox + PANEL_W // 2 + 40
    base_y = oy + PANEL_H - 90
    # jar (with cinnamon, no lid yet)
    mason_jar(d, cx, base_y, body_w=170, body_h=210, with_cinnamon=True,
              cin_frac=0.45)
    # exploded vertical stack above the jar mouth
    mouth_y = base_y - 210 + 32 - 14  # neck top from mason_jar params
    # mesh disc just above mouth
    y_mesh = mouth_y - 50
    mesh_disc(d, cx, y_mesh, w=150, ry=12)
    # stencil disc above mesh
    y_st = mouth_y - 100
    stencil_disc(d, cx, y_st, w=150, ry=12, show_heart=True)
    # ring above stencil
    y_ring = mouth_y - 158
    mason_ring(d, cx, y_ring, w=160, h=22, ry=10)
    # vertical down-arrows on the right side
    ax = cx + 110
    straight_arrow(d, ax, y_ring + 18, ax, y_st - 18)
    straight_arrow(d, ax, y_st + 16, ax, y_mesh - 18)
    straight_arrow(d, ax, y_mesh + 16, ax, mouth_y - 8)
    # labels on the left
    draw_label(d, ox + 40, y_ring - 8, "screw ring")
    draw_label(d, ox + 40, y_st - 8, "stencil disc\n(your laser-cut)")
    draw_label(d, ox + 40, y_mesh - 8, "mesh disc")
    draw_label(d, ox + 40, mouth_y + 30, "jar with cinnamon")


def panel3(d, ox, oy):
    draw_panel_frame(d, ox, oy, 3, "Snap silicone band onto the ring",
                     "Adds friction so the cap grips the cup rim.")
    cx = ox + PANEL_W // 2
    base_y = oy + PANEL_H - 90
    mason_jar(d, cx, base_y, body_w=180, body_h=270, with_cinnamon=True,
              cin_frac=0.4, with_lid=True, ring_h=22)
    # silicone band, drawn around / just below the metal ring
    band_cy = base_y - 270 + 32 - 14 - 10  # near the ring
    silicone_band(d, cx, band_cy + 4, w=240, h=22, ry=10)
    # arrows showing the band snapping in from the sides
    straight_arrow(d, cx - 220, band_cy + 4, cx - 130, band_cy + 4)
    straight_arrow(d, cx + 220, band_cy + 4, cx + 130, band_cy + 4)
    # labels
    draw_label(d, ox + 40, band_cy - 30, "silicone band\n(food-safe O-ring\n or mug-lid cover)")
    draw_label(d, ox + PANEL_W - 200, band_cy - 30,
               "stretches over\nthe metal ring")


def panel4(d, ox, oy):
    draw_panel_frame(d, ox, oy, 4, "Invert onto cup, tap, lift",
                     "Cinnamon sifts through mesh, dot pattern lands on coffee.")
    cx = ox + PANEL_W // 2
    mug_base = oy + PANEL_H - 70
    mug_h = 180
    mug(d, cx, mug_base, w=240, h=mug_h)
    rim_cy = mug_base - mug_h
    # inverted jar: lid (silicone + ring + stencil) is now on the bottom touching cup
    # silicone band straddles the cup rim
    silicone_band(d, cx, rim_cy + 12, w=300, h=22, ry=12)
    # stencil disc just under it, sitting between silicone and coffee
    stencil_disc(d, cx, rim_cy - 6, w=270, ry=14, show_heart=True)
    # mesh just above stencil (but visually we draw inverted jar over both)
    # Inverted jar body — narrow neck at bottom (touching ring/stencil), wide body up
    bw = 160
    bh = 170
    body_top = rim_cy - 24 - bh  # top of the (inverted) jar
    body_bot = rim_cy - 24      # bottom of straight body
    # straight body section (now occupying upper area of cap)
    L = cx - bw // 2; R = cx + bw // 2
    d.rectangle((L, body_top, R, body_bot), outline=OUTLINE, width=STROKE, fill=GLASS)
    # bottom of jar (now top — flat) showed as ellipse
    d.ellipse((L, body_top - 12, R, body_top + 12), outline=OUTLINE,
              width=STROKE, fill=GLASS_DARK)
    # inverted shoulder + neck below body_bot
    nw = bw - 32
    Ln = cx - nw // 2; Rn = cx + nw // 2
    neck_bot = body_bot + 18
    d.polygon([(L, body_bot), (Ln, neck_bot), (Rn, neck_bot), (R, body_bot)],
              fill=GLASS)
    d.line((L, body_bot, Ln, neck_bot), fill=OUTLINE, width=STROKE)
    d.line((R, body_bot, Rn, neck_bot), fill=OUTLINE, width=STROKE)
    d.rectangle((Ln, neck_bot, Rn, rim_cy - 6), fill=GLASS)
    d.line((Ln, neck_bot, Ln, rim_cy - 6), fill=OUTLINE, width=STROKE)
    d.line((Rn, neck_bot, Rn, rim_cy - 6), fill=OUTLINE, width=STROKE)
    # cinnamon settled at the bottom of the inverted jar — meaning at body_bot region
    cin_top = body_bot - int(bh * 0.35)
    d.rectangle((L + 3, cin_top, R - 3, body_bot - 1), fill=CINNAMON)
    d.line((L + 3, cin_top, R - 3, cin_top), fill=CINNAMON_DARK, width=2)
    # tap arrows on top (now-up) jar bottom
    arrow_top = body_top - 60
    straight_arrow(d, cx - 30, arrow_top, cx - 30, body_top - 8)
    straight_arrow(d, cx + 30, arrow_top, cx + 30, body_top - 8)
    draw_label(d, cx + 50, arrow_top + 4, "tap x2")
    # coffee surface inside mug rim with cinnamon-heart pattern
    coffee_bbox = (cx - 100, rim_cy - 4, cx + 100, rim_cy + 22)
    d.ellipse(coffee_bbox, fill=COFFEE, outline=OUTLINE, width=2)
    rxh, ryh = 38, 8
    for u_i in range(-14, 15):
        for v_i in range(-7, 8):
            u = u_i / 14; v = v_i / 7
            x, y = u, -v
            val = (x * x + y * y - 1) ** 3 - x * x * y * y * y
            if val <= 0 and u * u + v * v < 1.05:
                px = cx + u * rxh
                py = rim_cy + 9 + v * ryh
                d.ellipse((px - 1.3, py - 1.3, px + 1.3, py + 1.3), fill=CINNAMON)


# ---------- main ----------

def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((MARGIN, 30), "Coffee-Stencil MVP — Mason-Jar Assembly",
           fill=INK, font=FONT_TITLE_BIG)
    d.text((MARGIN, 72),
           "Standard mason jar lids are two separate pieces by design — "
           "ring + insert. We just supply two custom inserts.",
           fill=(80, 80, 85), font=FONT_CAPTION)

    for i, fn in enumerate([panel1, panel2, panel3, panel4]):
        ox, oy = panel_origin(i)
        fn(d, ox, oy)

    img.save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
