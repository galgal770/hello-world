"""4-panel step-by-step assembly diagram for the coffee-stencil cap MVP.

Aims for an IKEA-style line-art look: minimal color, clear arrows,
labelled parts.
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
STEEL = (232, 232, 236)
STEEL_DARK = (190, 190, 196)
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


# ---------- helpers ----------

def panel_origin(idx: int) -> tuple[int, int]:
    col = idx % 2
    row = idx // 2
    return (MARGIN + col * (PANEL_W + MARGIN), 100 + row * (PANEL_H + MARGIN))


def draw_panel_frame(d: ImageDraw.ImageDraw, ox: int, oy: int,
                     num: int, title: str, caption: str) -> None:
    d.rectangle((ox, oy, ox + PANEL_W, oy + PANEL_H), outline=OUTLINE, width=2, fill=BG)
    d.ellipse((ox + 18, oy + 18, ox + 78, oy + 78), fill=INK)
    d.text((ox + 32, oy + 24), str(num), fill=(255, 255, 255), font=FONT_NUM)
    d.text((ox + 96, oy + 30), title, fill=INK, font=FONT_TITLE)
    # bottom caption
    d.text((ox + 24, oy + PANEL_H - 40), caption, fill=INK, font=FONT_CAPTION)


def curved_arrow(d, cx, cy, rx, ry, start_deg, end_deg, color=ARROW, width=4):
    """Draw a curved arrow with a small head at the end."""
    d.arc((cx - rx, cy - ry, cx + rx, cy + ry), start_deg, end_deg,
          fill=color, width=width)
    a = math.radians(end_deg)
    ex = cx + rx * math.cos(a)
    ey = cy + ry * math.sin(a)
    # tangent direction
    tx = -rx * math.sin(a)
    ty = ry * math.cos(a)
    L = math.hypot(tx, ty)
    tx /= L; ty /= L
    nx, ny = -ty, tx
    head = 14
    p1 = (ex, ey)
    p2 = (ex - tx * head + nx * head * 0.5, ey - ty * head + ny * head * 0.5)
    p3 = (ex - tx * head - nx * head * 0.5, ey - ty * head - ny * head * 0.5)
    d.polygon([p1, p2, p3], fill=color)


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

def shaker_body(d, cx, base_y, w, h, fill_cinnamon=True, top_open=True, ry=14):
    """Vertical cylinder seen 3/4 from the front, open at top if top_open."""
    L = cx - w // 2
    R = cx + w // 2
    T = base_y - h
    # body rect
    d.rectangle((L, T, R, base_y), outline=OUTLINE, width=STROKE, fill=STEEL)
    # bottom front curve
    d.arc((L, base_y - ry, R, base_y + ry), 0, 180, fill=OUTLINE, width=STROKE)
    # top ellipse
    if top_open:
        d.ellipse((L, T - ry, R, T + ry), outline=OUTLINE, width=STROKE,
                  fill=STEEL_DARK)
    else:
        d.ellipse((L, T - ry, R, T + ry), outline=OUTLINE, width=STROKE, fill=STEEL)
    # cinnamon
    if fill_cinnamon:
        cin_top = base_y - int(h * 0.45)
        d.rectangle((L + 3, cin_top, R - 3, base_y - 1), fill=CINNAMON)
        d.line((L + 3, cin_top, R - 3, cin_top), fill=CINNAMON_DARK, width=2)
    return L, R, T


def lid_ring(d, cx, cy, w, h=28, mesh=True, ry=14):
    """A short ring (lid). If mesh=True, draw mesh dots in the opening."""
    L = cx - w // 2
    R = cx + w // 2
    T = cy - h // 2
    B = cy + h // 2
    d.rectangle((L, T, R, B), outline=OUTLINE, width=STROKE, fill=STEEL)
    d.arc((L, B - ry, R, B + ry), 0, 180, fill=OUTLINE, width=STROKE)
    d.ellipse((L, T - ry, R, T + ry), outline=OUTLINE, width=STROKE,
              fill=STEEL_DARK if mesh else STEEL)
    if mesh:
        # mesh pattern as small dots inside the top ellipse
        for i in range(L + 14, R - 14, 9):
            for j in range(T - ry + 4, T + ry - 4, 6):
                # only inside the ellipse
                u = (i - cx) / (w / 2 - 4)
                v = (j - T) / (ry - 2)
                if u * u + v * v <= 1.0:
                    d.ellipse((i, j, i + 2, j + 2), fill=OUTLINE)


def stencil_disc(d, cx, cy, w=240, ry=22, show_heart=True, with_grip=False):
    """Round disc, viewed nearly edge-on. Heart of dot holes optional."""
    L = cx - w // 2
    R = cx + w // 2
    if with_grip:
        gp = 14
        d.ellipse((L - gp, cy - ry - 4, R + gp, cy + ry + 14),
                  outline=OUTLINE, width=STROKE, fill=SILICONE)
        d.arc((L - gp, cy - ry - 4, R + gp, cy + ry + 14), 0, 180,
              fill=SILICONE_DARK, width=STROKE)
    d.ellipse((L, cy - ry, R, cy + ry), outline=OUTLINE, width=STROKE, fill=STEEL)
    if show_heart:
        # small heart of dots
        cx0, cy0 = cx, cy
        rxh = w * 0.22
        ryh = ry * 0.55
        # parametric heart silhouette mask via simple grid sampling
        for u_i in range(-12, 13):
            for v_i in range(-6, 7):
                u = u_i / 12
                v = v_i / 6
                # heart inequality (math y up)
                x, y = u, -v
                val = (x * x + y * y - 1) ** 3 - x * x * y * y * y
                if val <= 0 and u * u + v * v < 1.1:
                    px = cx0 + u * rxh
                    py = cy0 + v * ryh
                    d.ellipse((px - 1.5, py - 1.5, px + 1.5, py + 1.5), fill=INK)


def silicone_cap(d, cx, cy, w, h=70, ry=18):
    """Soft flexible mug-lid silhouette."""
    L = cx - w // 2
    R = cx + w // 2
    T = cy - h
    B = cy
    d.rectangle((L, T + 8, R, B - 8), outline=OUTLINE, width=STROKE, fill=SILICONE)
    d.arc((L, B - ry, R, B + ry), 0, 180, fill=OUTLINE, width=STROKE)
    d.ellipse((L, T - ry // 2, R, T + ry // 2), outline=OUTLINE, width=STROKE,
              fill=SILICONE)
    # rim ridge
    d.line((L + 2, T + 8, R - 2, T + 8), fill=SILICONE_DARK, width=2)
    d.line((L + 2, B - 8, R - 2, B - 8), fill=SILICONE_DARK, width=2)


def mug(d, cx, base_y, w=320, h=290):
    """Simple wooden mug silhouette."""
    L = cx - w // 2
    R = cx + w // 2
    T = base_y - h
    # body trapezoid (slightly flared at top)
    flare = 22
    d.polygon([(L - flare, T), (R + flare, T), (R, base_y), (L, base_y)],
              outline=OUTLINE, width=STROKE, fill=WOOD)
    # rim ellipse
    d.ellipse((L - flare, T - 22, R + flare, T + 22),
              outline=OUTLINE, width=STROKE, fill=WOOD_DARK)
    # handle
    d.ellipse((R + flare - 10, T + 50, R + flare + 90, T + 180),
              outline=OUTLINE, width=STROKE, fill=WOOD)
    d.ellipse((R + flare + 18, T + 80, R + flare + 62, T + 150),
              fill=BG, outline=OUTLINE, width=STROKE)


# ---------- panels ----------

def panel1(d, ox, oy):
    draw_panel_frame(d, ox, oy, 1, "Unscrew the mesh lid",
                     "Take a stainless cocoa shaker, twist the mesh lid off.")
    cx = ox + PANEL_W // 2
    body_base = oy + PANEL_H - 110
    # body (open at top, mesh lid removed)
    shaker_body(d, cx, body_base, w=200, h=260, top_open=True)
    # lid floating above
    lid_ring(d, cx + 100, oy + 200, w=210, h=34, mesh=True)
    # curved arrow showing unscrew rotation, going from above the body up and to the right
    curved_arrow(d, cx + 50, oy + 240, 90, 60, 200, 350)
    # labels
    draw_label(d, ox + 40, oy + 130, "mesh lid")
    d.line((ox + 110, oy + 152, cx + 100 - 40, oy + 200), fill=INK, width=1)
    draw_label(d, ox + PANEL_W - 220, oy + PANEL_H - 200, "shaker body\n(holds cinnamon)")


def panel2(d, ox, oy):
    draw_panel_frame(d, ox, oy, 2, "Stack stencil under the mesh",
                     "Drop in mesh disc, then stencil disc, then screw the ring back on.")
    cx = ox + PANEL_W // 2
    # exploded vertical view: body at bottom, then mesh, stencil, ring
    body_base = oy + PANEL_H - 110
    shaker_body(d, cx, body_base, w=200, h=180, top_open=True)
    # mesh disc above
    y_mesh = oy + 280
    stencil_disc(d, cx, y_mesh, w=210, ry=18, show_heart=False)
    # mesh dots on it
    for i in range(cx - 90, cx + 90, 9):
        for j in range(y_mesh - 12, y_mesh + 12, 5):
            u = (i - cx) / 100
            v = (j - y_mesh) / 14
            if u * u + v * v < 1.0:
                d.ellipse((i, j, i + 1.6, j + 1.6), fill=OUTLINE)
    # stencil above mesh
    y_st = oy + 220
    stencil_disc(d, cx, y_st, w=210, ry=18, show_heart=True)
    # ring above stencil
    y_ring = oy + 150
    lid_ring(d, cx, y_ring, w=210, h=24, mesh=False)
    # vertical down-arrows between layers
    straight_arrow(d, cx + 130, y_ring + 16, cx + 130, y_st - 24)
    straight_arrow(d, cx + 130, y_st + 22, cx + 130, y_mesh - 22)
    straight_arrow(d, cx + 130, y_mesh + 22, cx + 130, body_base - 200)
    # labels
    draw_label(d, ox + 30, y_ring - 6, "lid ring")
    draw_label(d, ox + 30, y_st - 6, "stencil disc (your laser-cut)")
    draw_label(d, ox + 30, y_mesh - 6, "mesh disc")
    draw_label(d, ox + 30, body_base - 130, "shaker body")


def panel3(d, ox, oy):
    draw_panel_frame(d, ox, oy, 3, "Snap silicone lid onto the rim",
                     "Flip the assembly over, push a silicone mug-lid onto the rim.")
    cx = ox + PANEL_W // 2
    base_y = oy + PANEL_H - 80
    w_body = 180
    h_body = 180
    sten_y = base_y - 30
    silicone_cap(d, cx, sten_y + 26, w=w_body + 90, h=58)
    stencil_disc(d, cx, sten_y - 4, w=w_body + 22, ry=16, show_heart=True)
    lid_ring(d, cx, sten_y - 32, w=w_body + 22, h=20, mesh=False)
    body_base = sten_y - 44
    body_top = body_base - h_body
    L = cx - w_body // 2; R = cx + w_body // 2
    d.rectangle((L, body_top, R, body_base), outline=OUTLINE, width=STROKE, fill=STEEL)
    d.arc((L, body_top - 12, R, body_top + 12), 180, 360, fill=OUTLINE, width=STROKE)
    d.ellipse((L, body_base - 12, R, body_base + 12), outline=OUTLINE, width=STROKE,
              fill=STEEL)
    cin_top = body_base - int(h_body * 0.45)
    d.rectangle((L + 3, cin_top, R - 3, body_base - 1), fill=CINNAMON)
    d.line((L + 3, cin_top, R - 3, cin_top), fill=CINNAMON_DARK, width=2)
    # silicone-snap arrows
    straight_arrow(d, cx - 230, sten_y + 30, cx - 145, sten_y + 30)
    straight_arrow(d, cx + 230, sten_y + 30, cx + 145, sten_y + 30)
    # labels (above the arrows, well clear of the bottom caption)
    draw_label(d, ox + 28, body_top + 20, "(now\ninverted)")
    draw_label(d, ox + 30, sten_y - 80, "silicone\nmug-lid")
    draw_label(d, ox + PANEL_W - 200, sten_y - 80, "stretches\nover rim")


def panel4(d, ox, oy):
    draw_panel_frame(d, ox, oy, 4, "Place on cup, tap, lift",
                     "Set on cup. Tap shaker top twice. Lift straight up. Done.")
    cx = ox + PANEL_W // 2
    mug_base = oy + PANEL_H - 70
    mug_h = 200
    mug(d, cx, mug_base, w=260, h=mug_h)
    rim_cy = mug_base - mug_h
    # silicone wraps mug rim
    silicone_cap(d, cx, rim_cy + 22, w=320, h=34, ry=14)
    # stencil disc
    stencil_disc(d, cx, rim_cy - 2, w=270, ry=16, show_heart=True)
    # inverted body (narrower than stencil)
    bw, bh = 160, 130
    body_base = rim_cy - 16
    body_top = body_base - bh
    L = cx - bw // 2; R = cx + bw // 2
    d.rectangle((L, body_top, R, body_base), outline=OUTLINE, width=STROKE, fill=STEEL)
    d.ellipse((L, body_top - 10, R, body_top + 10), outline=OUTLINE, width=STROKE,
              fill=STEEL_DARK)
    d.ellipse((L, body_base - 10, R, body_base + 10), outline=OUTLINE, width=STROKE,
              fill=STEEL)
    cin_top = body_base - int(bh * 0.5)
    d.rectangle((L + 3, cin_top, R - 3, body_base - 1), fill=CINNAMON)
    d.line((L + 3, cin_top, R - 3, cin_top), fill=CINNAMON_DARK, width=2)
    # tap arrows pointing down onto the top of the body (no finger)
    arrow_top = body_top - 50
    if arrow_top < oy + 90:
        arrow_top = oy + 90
    straight_arrow(d, cx - 30, arrow_top, cx - 30, body_top - 6, color=ARROW)
    straight_arrow(d, cx + 30, arrow_top, cx + 30, body_top - 6, color=ARROW)
    draw_label(d, cx + 50, arrow_top + 4, "tap x2")
    # coffee surface visible inside mug rim, with heart pattern in cinnamon
    coffee_bbox = (cx - 110, rim_cy - 6, cx + 110, rim_cy + 22)
    d.ellipse(coffee_bbox, fill=COFFEE, outline=OUTLINE, width=2)
    rxh, ryh = 42, 9
    for u_i in range(-14, 15):
        for v_i in range(-7, 8):
            u = u_i / 14; v = v_i / 7
            x, y = u, -v
            val = (x * x + y * y - 1) ** 3 - x * x * y * y * y
            if val <= 0 and u * u + v * v < 1.05:
                px = cx + u * rxh
                py = rim_cy + 8 + v * ryh
                d.ellipse((px - 1.3, py - 1.3, px + 1.3, py + 1.3), fill=CINNAMON)


# ---------- main ----------

def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # main title
    d.text((MARGIN, 30), "Coffee-Stencil MVP — Assembly", fill=INK,
           font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38))
    d.text((MARGIN, 72),
           "Off-the-shelf cocoa shaker + laser-cut stencil + silicone mug-lid.",
           fill=(80, 80, 85), font=FONT_CAPTION)

    for i, fn in enumerate([panel1, panel2, panel3, panel4]):
        ox, oy = panel_origin(i)
        fn(d, ox, oy)

    img.save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
