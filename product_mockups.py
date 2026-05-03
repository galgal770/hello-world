"""Stylized 3D-look product renders for the coffee-stencil cap.

Three outputs:
    stencil_render.png  - the laser-cut stencil disc with silicone grip ring
    shaker_render.png   - the refillable shaker dome with mesh floor + piston
    assembly_render.png - both parts seated on the user's wooden mug

Pillow primitives only. Not photoreal; aimed at design-review clarity.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
OUT_DIR = Path("/home/user/hello-world")
MUG_PATH = Path("/root/.claude/uploads/40f7e828-d046-4e41-9079-3fded5919702/69a53316-1000669511.jpg")


# ---------- helpers ----------

def studio_backdrop(size: int = SIZE) -> Image.Image:
    """Soft warm-white studio gradient with horizon shading and a floor band."""
    bg = Image.new("RGB", (size, size))
    px = bg.load()
    for y in range(size):
        t = y / (size - 1)
        # slightly warm white at top, cool gray at bottom
        r = int(248 - 35 * t * t)
        g = int(247 - 38 * t * t)
        b = int(245 - 30 * t * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    # subtle floor shading band well below the subject
    horizon = int(size * 0.86)
    floor = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(floor)
    for y in range(horizon, size):
        t = (y - horizon) / max(1, size - horizon)
        a = int(60 * t)
        fd.line((0, y, size, y), fill=(80, 75, 70, a))
    bg = bg.convert("RGBA")
    bg.alpha_composite(floor)
    return bg


def soft_shadow(surface: Image.Image, bbox, dx: int = 12, dy: int = 22,
                blur: int = 24, alpha: int = 110) -> None:
    """Drop a blurred elliptical shadow beneath a shape."""
    shadow = Image.new("RGBA", surface.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        (bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy),
        fill=(0, 0, 0, alpha),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    surface.alpha_composite(shadow)


def linear_gradient_ellipse(surface: Image.Image, bbox, top_color, bot_color) -> None:
    """Fill an ellipse with a vertical linear gradient."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    grad = Image.new("RGB", (1, h))
    gpx = grad.load()
    for i in range(h):
        t = i / max(1, h - 1)
        gpx[0, i] = tuple(
            int(top_color[k] + (bot_color[k] - top_color[k]) * t) for k in range(3)
        )
    grad = grad.resize((w, h))
    mask = Image.new("L", surface.size, 0)
    ImageDraw.Draw(mask).ellipse(bbox, fill=255)
    canvas = Image.new("RGB", surface.size, (0, 0, 0))
    canvas.paste(grad, (x0, y0))
    surface.paste(canvas, (0, 0), mask)


def make_heart_mask(size: int) -> Image.Image:
    """Return a grayscale heart silhouette (255 inside, 0 outside)."""
    img = Image.new("L", (size, size), 0)
    pts = []
    cx = cy = size / 2
    scale = size * 0.42
    for i in range(360):
        t = i / 360 * math.tau
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
              - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x / 17 * scale, cy + y / 17 * scale))
    ImageDraw.Draw(img).polygon(pts, fill=255)
    return img.filter(ImageFilter.GaussianBlur(size * 0.01))


# ---------- 1. stencil disc ----------

def render_stencil(path: Path) -> None:
    img = studio_backdrop()
    cx, cy = SIZE // 2, int(SIZE * 0.58)
    rx, ry = 360, 110          # tilted disc → strong perspective
    edge_h = 18                # visible side thickness

    # ground shadow
    soft_shadow(img, (cx - rx, cy - ry, cx + rx, cy + ry), dy=36, blur=30, alpha=130)

    # silicone grip ring (a slightly larger, warm matte ring underneath)
    grip_pad = 22
    grip_bbox = (cx - rx - grip_pad, cy - ry - 4, cx + rx + grip_pad, cy + ry + edge_h + 14)
    grip = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grip)
    gd.ellipse(grip_bbox, fill=(168, 130, 95, 255))
    # darker side of the silicone ring (the visible vertical edge)
    gd.chord(grip_bbox, 0, 180, fill=(112, 80, 55, 255))
    grip = grip.filter(ImageFilter.GaussianBlur(0.8))
    img.alpha_composite(grip)

    # disc side (the metal edge, between top face and silicone)
    side_bbox = (cx - rx, cy - ry + edge_h, cx + rx, cy + ry + edge_h)
    sd_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sd_layer).chord(side_bbox, 0, 180, fill=(120, 122, 128, 255))
    img.alpha_composite(sd_layer)

    # disc top face: brushed stainless gradient
    top_bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
    linear_gradient_ellipse(img, top_bbox, (228, 230, 235), (170, 172, 178))

    # brushed-metal radial lines (already constrained inside the ellipse)
    brush = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(brush)
    rng = random.Random(2)
    for _ in range(900):
        a = rng.uniform(0, math.tau)
        r0 = rng.uniform(0.05, 0.97)
        r1 = r0 + rng.uniform(0.005, 0.03)
        shade = rng.randint(140, 220)
        alpha = rng.randint(25, 70)
        x0 = cx + r0 * rx * math.cos(a)
        y0 = cy + r0 * ry * math.sin(a)
        x1 = cx + r1 * rx * math.cos(a)
        y1 = cy + r1 * ry * math.sin(a)
        bd.line((x0, y0, x1, y1), fill=(shade, shade, shade + 4, alpha), width=1)
    img.alpha_composite(brush)

    # specular highlight crescent on top face
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        (cx - rx * 0.7, cy - ry + 2, cx + rx * 0.7, cy - ry + 26),
        fill=(255, 255, 255, 110),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(hl)

    # heart hole pattern
    mask = make_heart_mask(420)
    mpx = mask.load()
    msz = 420
    pat_radius_disc = 0.62          # heart fills 62% of disc radius
    grid_x = 14                     # ~14 px between dots horizontally
    squash = ry / rx
    holes = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(holes)
    rng2 = random.Random(5)
    n = int(rx * pat_radius_disc / grid_x) + 1
    for row in range(-n, n + 1):
        y_off = row * grid_x * squash
        x_shift = grid_x / 2 if row % 2 else 0
        for col in range(-n, n + 1):
            x_off = col * grid_x + x_shift
            u = x_off / (rx * pat_radius_disc)
            v = y_off / (ry * pat_radius_disc)
            if u * u + v * v > 1.0:
                continue
            mx = int((u * 0.5 + 0.5) * (msz - 1))
            my = int((v * 0.5 + 0.5) * (msz - 1))
            d = mpx[mx, my] / 255.0
            if d <= 0.1:
                continue
            r_h = 2.0 + 3.0 * d + rng2.uniform(-0.3, 0.3)
            x = cx + x_off
            y = cy + y_off
            hd.ellipse((x - r_h, y - r_h * squash, x + r_h, y + r_h * squash),
                       fill=(28, 24, 22, 255))
            # tiny inner highlight on each hole rim
            hd.ellipse((x - r_h, y - r_h * squash, x + r_h * 0.3, y - r_h * squash * 0.3),
                       fill=(255, 255, 255, 50))
    img.alpha_composite(holes)

    # registration V-notches at front and back
    nd = ImageDraw.Draw(img)
    notch = 16
    nd.polygon([(cx - notch, cy - ry), (cx + notch, cy - ry),
                (cx, cy - ry + notch * 0.7)], fill=(168, 130, 95, 255))
    nd.polygon([(cx - notch, cy + ry + edge_h), (cx + notch, cy + ry + edge_h),
                (cx, cy + ry + edge_h - notch * 0.7)], fill=(112, 80, 55, 255))

    # caption
    cap = ImageDraw.Draw(img)
    cap.text((36, SIZE - 60), "Stencil disc  -  laser-cut stainless + silicone grip ring",
             fill=(60, 60, 60, 255))

    img.convert("RGB").save(path, "PNG", optimize=True)


# ---------- 2. shaker dome ----------

def render_shaker(path: Path) -> None:
    img = studio_backdrop()
    cx = SIZE // 2
    base_y = int(SIZE * 0.78)
    rx, ry = 230, 60                  # base ellipse
    body_h = 360                      # cylindrical body height
    dome_h = 130                      # rounded top
    top_y = base_y - body_h

    # ground shadow under the whole shaker
    soft_shadow(img, (cx - rx - 8, base_y - ry, cx + rx + 8, base_y + ry),
                dy=28, blur=28, alpha=130)

    # bayonet ring: thin dark metallic band at the very bottom
    bd = ImageDraw.Draw(img)
    bd.rectangle((cx - rx - 4, base_y - 8, cx + rx + 4, base_y + 4),
                 fill=(70, 70, 75, 255))
    bd.line((cx - rx - 4, base_y - 4, cx + rx + 4, base_y - 4),
            fill=(160, 160, 165, 220), width=1)
    # rounded ends of the band
    bd.chord((cx - rx - 6, base_y - 8, cx - rx + 6, base_y + 4), 90, 270,
             fill=(70, 70, 75, 255))
    bd.chord((cx + rx - 6, base_y - 8, cx + rx + 6, base_y + 4), 270, 90,
             fill=(70, 70, 75, 255))

    # === translucent body: rectangle sides + dome top ===
    # Side wall, with slight left-light gradient.
    body = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(body)
    # Make the side a clipped rectangle.
    side_rect = (cx - rx, top_y, cx + rx, base_y)
    # Build a gradient strip
    grad = Image.new("RGBA", (rx * 2, body_h))
    gpx = grad.load()
    for x in range(rx * 2):
        t = x / (rx * 2 - 1)
        # left side brighter, right darker
        v = int(245 - 75 * (t ** 1.4))
        a = 215
        for y in range(body_h):
            yy = y / (body_h - 1)
            tint_r = v
            tint_g = v - 4
            tint_b = v - 10
            gpx[x, y] = (tint_r, tint_g, tint_b, a)
    body.paste(grad, (cx - rx, top_y))

    # cinnamon level inside (visible through translucent body) - lower 35%
    cin_top_y = base_y - int(body_h * 0.34)
    cin = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(cin)
    # filled side region of cinnamon
    cd.rectangle((cx - rx, cin_top_y, cx + rx, base_y), fill=(150, 85, 45, 255))
    # speckle the cinnamon for a granular texture
    rng = random.Random(13)
    for _ in range(6000):
        x = rng.randint(cx - rx, cx + rx - 1)
        y = rng.randint(cin_top_y, base_y - 1)
        v = rng.randint(110, 200)
        cd.point((x, y), fill=(v, int(v * 0.55), int(v * 0.3), 255))
    # cinnamon meniscus highlight (top edge ellipse inside the body)
    cd.ellipse((cx - rx + 4, cin_top_y - 8, cx + rx - 4, cin_top_y + 8),
               fill=(180, 110, 65, 255))

    body.alpha_composite(cin)

    # mesh floor visible at the bottom inside (horizontal lines)
    mesh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    md = ImageDraw.Draw(mesh)
    for i in range(8):
        yy = base_y - 18 + i * 3
        md.line((cx - rx + 6, yy, cx + rx - 6, yy), fill=(40, 40, 40, 200), width=1)
    body.alpha_composite(mesh)

    # outer shine band on the body left side
    shine = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh = ImageDraw.Draw(shine)
    sh.rectangle((cx - rx + 8, top_y + 10, cx - rx + 38, base_y - 12),
                 fill=(255, 255, 255, 90))
    shine = shine.filter(ImageFilter.GaussianBlur(6))
    body.alpha_composite(shine)

    img.alpha_composite(body)


    # === dome top: single half-ellipse with side shading ===
    dome_bbox = (cx - rx, top_y - dome_h, cx + rx, top_y + dome_h)
    dome_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(dome_layer).chord(dome_bbox, 180, 360,
                                      fill=(248, 248, 246, 235))
    # very soft right-side shading on the dome
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse(
        (cx + rx * 0.3, top_y - dome_h * 0.4, cx + rx, top_y + 8),
        fill=(40, 38, 35, 70),
    )
    shade = shade.filter(ImageFilter.GaussianBlur(28))
    dome_layer.alpha_composite(shade)
    img.alpha_composite(dome_layer)

    # soft specular sliver on the dome's upper-left
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        (cx - rx * 0.6, top_y - dome_h + 22, cx - rx * 0.2, top_y - dome_h * 0.55),
        fill=(255, 255, 255, 110),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(20))
    img.alpha_composite(hl)

    # red piston button (no extra UFO-shadow)
    pb_w, pb_h = 70, 22
    pb_x = cx - pb_w // 2
    pb_y = top_y - dome_h + 6
    pd = ImageDraw.Draw(img)
    # tight contact shadow ring
    sh2 = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh2).ellipse(
        (pb_x - 2, pb_y + pb_h - 4, pb_x + pb_w + 2, pb_y + pb_h + 6),
        fill=(0, 0, 0, 110))
    sh2 = sh2.filter(ImageFilter.GaussianBlur(3))
    img.alpha_composite(sh2)
    # button body
    pd.ellipse((pb_x, pb_y, pb_x + pb_w, pb_y + pb_h), fill=(180, 45, 45, 255))
    pd.ellipse((pb_x + 5, pb_y + 2, pb_x + pb_w - 5, pb_y + pb_h - 3),
               fill=(215, 70, 70, 255))
    pd.ellipse((pb_x + 14, pb_y + 3, pb_x + pb_w - 30, pb_y + 7),
               fill=(255, 210, 210, 230))

    # caption
    ImageDraw.Draw(img).text(
        (36, SIZE - 60),
        "Shaker dome  -  refillable, mesh floor, tap-piston dosing",
        fill=(60, 60, 60, 255),
    )
    img.convert("RGB").save(path, "PNG", optimize=True)


# ---------- 3. assembly on the user's mug ----------

def render_assembly(path: Path) -> None:
    img = Image.open(MUG_PATH).convert("RGBA")

    # Mug rim ellipse, measured earlier on this exact photo.
    rim_cx, rim_cy = 538, 222
    rim_rx, rim_ry = 318, 73

    # ---- 1. silicone grip ring + stencil disc seated on the rim ----
    # The stencil's silicone ring projects ~12 px past the wood rim and grips it.
    grip_pad = 12
    grip_h = 22  # visible vertical thickness of the silicone ring
    grip_bbox = (rim_cx - rim_rx - grip_pad, rim_cy - rim_ry - 6,
                 rim_cx + rim_rx + grip_pad, rim_cy + rim_ry + grip_h)

    # silicone-ring shadow on the wood rim
    soft_shadow(img, grip_bbox, dx=4, dy=18, blur=14, alpha=130)

    grip = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grip)
    # bottom (front) curved face of the silicone ring
    gd.chord(grip_bbox, 0, 180, fill=(100, 72, 50, 255))
    # top face of silicone ring
    gd.ellipse((grip_bbox[0], grip_bbox[1], grip_bbox[2],
                grip_bbox[1] + (grip_bbox[3] - grip_bbox[1]) - grip_h),
               fill=(168, 130, 95, 255))
    img.alpha_composite(grip)

    # stencil metal top face (slightly inset from the silicone ring)
    stencil_bbox = (rim_cx - rim_rx, rim_cy - rim_ry,
                    rim_cx + rim_rx, rim_cy + rim_ry)
    linear_gradient_ellipse(img, stencil_bbox, (222, 224, 230), (158, 162, 170))

    # heart of holes on the stencil (only the ring around the dome will be visible)
    mask = make_heart_mask(420)
    mpx = mask.load()
    msz = 420
    squash = rim_ry / rim_rx
    pat_r_x = rim_rx * 0.78
    pat_r_y = pat_r_x * squash
    grid = 9
    holes = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(holes)
    n = int(pat_r_x / grid) + 2
    for row in range(-n, n + 1):
        y_off = row * grid * squash
        x_shift = grid / 2 if row % 2 else 0
        for col in range(-n, n + 1):
            x_off = col * grid + x_shift
            u = x_off / pat_r_x
            v = y_off / pat_r_y
            if u * u + v * v > 1.0:
                continue
            mx = int((u * 0.5 + 0.5) * (msz - 1))
            my = int((v * 0.5 + 0.5) * (msz - 1))
            d = mpx[mx, my] / 255.0
            if d <= 0.1:
                continue
            r_h = 1.4 + 1.8 * d
            x = rim_cx + x_off
            y = rim_cy + y_off
            hd.ellipse((x - r_h, y - r_h * squash, x + r_h, y + r_h * squash),
                       fill=(28, 24, 22, 255))
    img.alpha_composite(holes)

    # ---- 2. shaker dome seated on top of the stencil ----
    cx = rim_cx
    base_y = rim_cy - 6        # bayonet ring sits on the stencil top
    rx = int(rim_rx * 0.55)
    ry = int(rim_ry * 0.55)
    body_h = 130
    dome_h = 55
    top_y = base_y - body_h

    # bayonet ring: thin dark band where the dome locks into the stencil
    bd = ImageDraw.Draw(img)
    bd.rectangle((cx - rx - 2, base_y - 3, cx + rx + 2, base_y + 5),
                 fill=(60, 60, 65, 255))
    bd.line((cx - rx - 2, base_y, cx + rx + 2, base_y),
            fill=(150, 150, 155, 200), width=1)

    # translucent body + cinnamon visible through it
    body = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bw = rx * 2
    grad = Image.new("RGBA", (bw, body_h))
    gpx = grad.load()
    for x in range(bw):
        t = x / max(1, bw - 1)
        v = int(245 - 80 * (t ** 1.4))
        for y in range(body_h):
            gpx[x, y] = (v, v - 3, v - 9, 210)
    body.paste(grad, (cx - rx, top_y))

    cin_top_y = base_y - int(body_h * 0.42)
    cdraw = ImageDraw.Draw(body)
    cdraw.rectangle((cx - rx, cin_top_y, cx + rx, base_y), fill=(150, 85, 45, 255))
    rng = random.Random(31)
    for _ in range(1800):
        x = rng.randint(cx - rx, cx + rx - 1)
        y = rng.randint(cin_top_y, base_y - 1)
        v = rng.randint(110, 200)
        cdraw.point((x, y), fill=(v, int(v * 0.55), int(v * 0.3), 255))
    # meniscus on the cinnamon top
    cdraw.ellipse((cx - rx + 3, cin_top_y - 4, cx + rx - 3, cin_top_y + 4),
                  fill=(180, 110, 65, 255))

    # subtle vertical shine on the body
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle(
        (cx - rx + 6, top_y + 8, cx - rx + 24, base_y - 8),
        fill=(255, 255, 255, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(5))
    body.alpha_composite(sh)

    img.alpha_composite(body)

    # dome: single half-ellipse with a vertical light-to-shadow gradient
    dome_bbox = (cx - rx, top_y - dome_h, cx + rx, top_y + dome_h)
    dome_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(dome_layer).chord(dome_bbox, 180, 360,
                                      fill=(248, 248, 246, 235))
    # subtle shadow on the lower-right side of the dome
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).chord(
        (cx - rx * 0.2, top_y - dome_h * 0.5, cx + rx + 6, top_y),
        200, 360, fill=(40, 38, 35, 90),
    )
    shade = shade.filter(ImageFilter.GaussianBlur(8))
    dome_layer.alpha_composite(shade)
    img.alpha_composite(dome_layer)

    # specular dome highlight (curved sliver on upper-left)
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hd2 = ImageDraw.Draw(hl)
    hd2.chord(
        (cx - rx + 14, top_y - dome_h + 6, cx + rx * 0.1, top_y + dome_h * 0.3),
        180, 270, fill=(255, 255, 255, 180),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(hl)

    # red piston button on top of the dome
    pb_rx, pb_ry = 26, 7
    pb_cy = top_y - dome_h + 4
    pd = ImageDraw.Draw(img)
    # button shadow ring on dome
    sh3 = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh3).ellipse(
        (cx - pb_rx - 2, pb_cy + pb_ry - 1, cx + pb_rx + 2, pb_cy + pb_ry + 6),
        fill=(0, 0, 0, 110))
    sh3 = sh3.filter(ImageFilter.GaussianBlur(3))
    img.alpha_composite(sh3)
    # button body
    pd.ellipse((cx - pb_rx, pb_cy - pb_ry, cx + pb_rx, pb_cy + pb_ry),
               fill=(180, 45, 45, 255))
    pd.ellipse((cx - pb_rx + 3, pb_cy - pb_ry + 1,
                cx + pb_rx - 3, pb_cy + pb_ry - 2),
               fill=(215, 70, 70, 255))
    # tiny top highlight on button
    pd.ellipse((cx - 12, pb_cy - pb_ry + 1, cx + 6, pb_cy - pb_ry + 3),
               fill=(255, 210, 210, 230))

    # caption
    label = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(label)
    ld.rectangle((24, img.height - 56, 560, img.height - 22), fill=(0, 0, 0, 170))
    ld.text((38, img.height - 50),
            "Cap assembled on mug  -  press button to dust pattern through stencil",
            fill=(245, 235, 215, 255))
    img.alpha_composite(label)

    img.convert("RGB").save(path, "PNG", optimize=True)


def main() -> None:
    render_stencil(OUT_DIR / "render_stencil.png")
    render_shaker(OUT_DIR / "render_shaker.png")
    render_assembly(OUT_DIR / "render_assembly.png")
    print("Wrote render_stencil.png, render_shaker.png, render_assembly.png")


if __name__ == "__main__":
    main()
