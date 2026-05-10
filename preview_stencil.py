"""Generate a heart test image, run coffee_stencil.py, then render a PIL
preview of the resulting paddle stencil so we can visually verify the
outline + dot pattern look right.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path("/home/user/hello-world")
HEART_PNG = ROOT / "test_heart.png"
STENCIL_SVG = ROOT / "stencil_paddle.svg"
PREVIEW_PNG = ROOT / "stencil_paddle_preview.png"


def make_heart_test_image(path: Path, size: int = 800) -> None:
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    pts = []
    cx = cy = size / 2
    scale = size * 0.40
    for i in range(360):
        t = i / 360 * math.tau
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
              - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x / 17 * scale, cy + y / 17 * scale))
    d.polygon(pts, fill=0)
    img = img.filter(ImageFilter.GaussianBlur(size * 0.008))
    img.save(path, "PNG")


# Re-implement the paddle outline geometry from coffee_stencil.py so we
# can rasterize it for the preview. (Kept in sync with that file.)

def paddle_outline_points(
    diameter_mm: float,
    handle_length_mm: float,
    handle_tip_r_mm: float = 12.0,
    join_angle_deg: float = 30.0,
    k_tip: float = 12.0,
    k_body: float = 20.0,
    samples_bezier: int = 60,
    samples_arc: int = 240,
) -> list[tuple[float, float]]:
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

    cp1_top = (tip_top[0] + k_tip, tip_top[1])
    cp2_top = (body_join_top[0] - k_body * sin_p,
               body_join_top[1] + k_body * cos_p)
    cp1_bot = (body_join_bot[0] - k_body * sin_p,
               body_join_bot[1] - k_body * cos_p)
    cp2_bot = (tip_bot[0] + k_tip, tip_bot[1])

    def cubic(p0, p1, p2, p3, n):
        out = []
        for i in range(n + 1):
            t = i / n
            x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0]
                 + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0])
            y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1]
                 + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1])
            out.append((x, y))
        return out

    points: list[tuple[float, float]] = []
    points.extend(cubic(tip_top, cp1_top, cp2_top, body_join_top, samples_bezier))
    # Body major arc clockwise from body_join_top to body_join_bot.
    start_angle = math.atan2(body_join_top[1] - cy, body_join_top[0] - body_cx)
    end_angle = math.atan2(body_join_bot[1] - cy, body_join_bot[0] - body_cx)
    # We want to sweep clockwise (increasing angle in SVG y-down).
    if end_angle <= start_angle:
        end_angle += 2 * math.pi
    for i in range(1, samples_arc + 1):
        t = i / samples_arc
        a = start_angle + (end_angle - start_angle) * t
        points.append((body_cx + R * math.cos(a), cy + R * math.sin(a)))
    points.extend(cubic(body_join_bot, cp1_bot, cp2_bot, tip_bot, samples_bezier)[1:])
    # Tip semicircle clockwise (left side) from tip_bot to tip_top.
    tip_center = (tip_cx, cy)
    start_a = math.atan2(tip_bot[1] - cy, tip_bot[0] - tip_cx)  # π/2
    end_a = math.atan2(tip_top[1] - cy, tip_top[0] - tip_cx)    # -π/2
    if end_a <= start_a:
        end_a += 2 * math.pi
    for i in range(1, samples_arc + 1):
        t = i / samples_arc
        a = start_a + (end_a - start_a) * t
        points.append((tip_center[0] + handle_tip_r_mm * math.cos(a),
                       tip_center[1] + handle_tip_r_mm * math.sin(a)))
    return points


def parse_circles_from_svg(svg_path: Path) -> list[tuple[float, float, float]]:
    """Pull every <circle cx=... cy=... r=... /> out of the file."""
    import re
    text = svg_path.read_text()
    pattern = re.compile(
        r'<circle\s+cx="([\d.\-]+)"\s+cy="([\d.\-]+)"\s+r="([\d.\-]+)"'
    )
    return [(float(a), float(b), float(c)) for a, b, c in pattern.findall(text)]


def render_preview(
    svg_path: Path,
    out_png: Path,
    diameter_mm: float = 95.0,
    handle_length_mm: float = 51.0,
    handle_tip_r_mm: float = 12.0,
    join_angle_deg: float = 30.0,
    px_per_mm: float = 8.0,
) -> None:
    total_w = diameter_mm + handle_length_mm
    total_h = diameter_mm
    pad = 30
    W = int(total_w * px_per_mm) + 2 * pad
    H = int(total_h * px_per_mm) + 2 * pad

    img = Image.new("RGB", (W, H), (252, 251, 248))
    d = ImageDraw.Draw(img)

    # outline
    pts = paddle_outline_points(diameter_mm, handle_length_mm,
                                 handle_tip_r_mm, join_angle_deg)
    px_pts = [(pad + x * px_per_mm, pad + y * px_per_mm) for x, y in pts]
    d.polygon(px_pts, outline=(40, 40, 45), fill=(225, 225, 230), width=2)

    # dot holes
    circles = parse_circles_from_svg(svg_path)
    for cx, cy, r in circles:
        x = pad + cx * px_per_mm
        y = pad + cy * px_per_mm
        rp = r * px_per_mm
        d.ellipse((x - rp, y - rp, x + rp, y + rp), fill=(30, 25, 22))

    # dimension annotations
    R = diameter_mm / 2.0
    body_cx = total_w - R
    # horizontal total width dim
    y_dim = pad - 14
    x0 = pad
    x1 = pad + int(total_w * px_per_mm)
    d.line((x0, y_dim, x1, y_dim), fill=(40, 80, 160), width=2)
    d.line((x0, y_dim - 6, x0, y_dim + 6), fill=(40, 80, 160), width=2)
    d.line((x1, y_dim - 6, x1, y_dim + 6), fill=(40, 80, 160), width=2)
    d.text(((x0 + x1) // 2 - 26, y_dim - 22),
           f"{total_w:.0f} mm", fill=(40, 80, 160))
    # vertical body height dim
    x_dim = pad + int(total_w * px_per_mm) + 14
    y0 = pad
    y1 = pad + int(total_h * px_per_mm)
    d.line((x_dim, y0, x_dim, y1), fill=(40, 80, 160), width=2)
    d.line((x_dim - 6, y0, x_dim + 6, y0), fill=(40, 80, 160), width=2)
    d.line((x_dim - 6, y1, x_dim + 6, y1), fill=(40, 80, 160), width=2)
    d.text((x_dim + 4, (y0 + y1) // 2 - 8),
           f"{diameter_mm:.0f} mm", fill=(40, 80, 160))

    img.save(out_png, "PNG", optimize=True)


def main() -> None:
    make_heart_test_image(HEART_PNG)
    subprocess.run(
        [sys.executable, str(ROOT / "coffee_stencil.py"),
         str(HEART_PNG), str(STENCIL_SVG),
         "--diameter", "95", "--handle-length", "51"],
        check=True,
    )
    render_preview(STENCIL_SVG, PREVIEW_PNG)
    print(f"Wrote {PREVIEW_PNG}")


if __name__ == "__main__":
    main()
