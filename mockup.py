"""Render a mockup of the coffee-stencil result onto the user's wooden mug."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

MUG = Path("/root/.claude/uploads/40f7e828-d046-4e41-9079-3fded5919702/69a53316-1000669511.jpg")
OUT = Path("/home/user/hello-world/mockup.png")

# Rim ellipse measured on the source photo (1078x1074 px).
RIM_CX, RIM_CY = 538, 222
RIM_RX, RIM_RY = 318, 73
INNER_SHRINK = 6  # coffee sits inside the wood wall
PATTERN_BITMAP = 400  # internal resolution for the pattern silhouette


def draw_coffee(base: Image.Image) -> None:
    """Paint a near-black espresso surface inside the rim cavity."""
    cx, cy = RIM_CX, RIM_CY
    rx, ry = RIM_RX - INNER_SHRINK, RIM_RY - INNER_SHRINK

    coffee = Image.new("RGBA", base.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(coffee)
    cd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(28, 16, 9, 255))

    # Specular highlight crescent near the back rim only.
    hl = Image.new("RGBA", base.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse(
        (cx - rx * 0.6, cy - ry + 3, cx + rx * 0.6, cy - ry + 22),
        fill=(150, 100, 65, 95),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(8))
    coffee.alpha_composite(hl)

    base.alpha_composite(coffee)


def make_heart_mask(size: int) -> Image.Image:
    """Return a grayscale heart silhouette: 255 inside, 0 outside, soft edges."""
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    scale = size * 0.42
    pts = []
    steps = 240
    for i in range(steps):
        t = i / steps * math.tau
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
              - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x / 17 * scale, cy + y / 17 * scale))
    d.polygon(pts, fill=255)
    return img.filter(ImageFilter.GaussianBlur(size * 0.012))


def draw_pattern(base: Image.Image) -> None:
    """Halftone-dust a heart into the coffee, perspective-matched to the rim."""
    cx, cy = RIM_CX, RIM_CY
    rx, ry = RIM_RX - INNER_SHRINK - 8, RIM_RY - INNER_SHRINK - 6
    squash = ry / rx

    pattern_radius_mm = 30.0
    grid_mm = 1.6
    px_per_mm = rx / 38.0  # rim ~76 mm wide

    mask = make_heart_mask(PATTERN_BITMAP)
    mpx = mask.load()
    msz = PATTERN_BITMAP

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    rng = random.Random(11)
    n = int(pattern_radius_mm / grid_mm) + 1
    for row in range(-n, n + 1):
        y_mm = row * grid_mm
        x_shift = grid_mm / 2.0 if row % 2 else 0.0
        for col in range(-n, n + 1):
            x_mm = col * grid_mm + x_shift
            u = x_mm / pattern_radius_mm
            v = y_mm / pattern_radius_mm
            if u * u + v * v > 1.0:
                continue
            mx = int((u * 0.5 + 0.5) * (msz - 1))
            my = int((v * 0.5 + 0.5) * (msz - 1))
            darkness = mpx[mx, my] / 255.0
            if darkness <= 0.08:
                continue

            px = cx + x_mm * px_per_mm + rng.uniform(-0.5, 0.5)
            py = cy + y_mm * px_per_mm * squash + rng.uniform(-0.4, 0.4)

            r_mm = 0.35 + 0.55 * darkness
            r_px = max(1.4, r_mm * px_per_mm)
            shade = int(160 + rng.uniform(-18, 18))
            color = (shade, int(shade * 0.55), int(shade * 0.28), 245)
            od.ellipse(
                (px - r_px, py - r_px * squash, px + r_px, py + r_px * squash),
                fill=color,
            )

    overlay = overlay.filter(ImageFilter.GaussianBlur(0.7))
    base.alpha_composite(overlay)


def draw_label(base: Image.Image) -> None:
    """Tiny corner caption."""
    d = ImageDraw.Draw(base)
    d.rectangle((20, base.height - 60, 360, base.height - 20), fill=(0, 0, 0, 160))
    d.text((34, base.height - 52), "Coffee Stencil — cinnamon halftone heart",
           fill=(240, 230, 210, 255))


def main() -> None:
    base = Image.open(MUG).convert("RGBA")
    draw_coffee(base)
    draw_pattern(base)
    draw_label(base)
    base.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
