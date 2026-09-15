#!/usr/bin/env python3
"""
Extract the "Good Morning" script lettering from the reference photo and emit a
clean, smooth, high-resolution stencil input.

The source is a photo of a white "Good Morning" coffee stencil lying on a tan
table: the plate is bright (~235), the lettering reads through as mid-grey
(~175), and the tan background and the rim shadow are darker still.

Method
------
  • keep only what is inside the plate circle (a generous inset clears the rim)
  • map luminance through a soft ramp instead of a hard threshold, so the
    letter edges keep their sub-pixel (anti-aliased) detail
  • drop connected components that touch the rim — those are the two crescent
    shadows cast by the plate edge, not lettering
  • upscale, then Gaussian-blur: the photo is only ~10 px/mm, so its edges carry
    JPEG ringing and sensor noise.  Blurring the anti-aliased mask removes that
    high-frequency wobble while leaving the 50% level — and therefore the
    letterform itself — where it was.

Output: samples/good_morning_input.png
"""

import os
import sys
import math
from collections import deque

from PIL import Image, ImageFilter

SRC = ("/root/.claude/uploads/7ebed545-4d01-58b6-b8fd-9eb97a6e11c8/"
       "6d6e3dbe-1000726076.jpg")

CX, CY, R = 504.0, 689.0, 489.0   # plate circle found in the photo
RIM_INSET = 34.0                  # stay clear of the rim shadow
HI, LO = 226.0, 196.0             # plate -> ink ramp
RIM_TOUCH = 450.0                 # components reaching this far out are shadows
MIN_COMP = 20                     # speck rejection
MARGIN = 40                       # crop margin, source px
OUT_SIDE = 2600                   # final square size
BLUR = float(sys.argv[1]) if len(sys.argv) > 1 else 7.0


def main():
    img = Image.open(SRC).convert("L")
    px = img.load()
    w, h = img.size

    # ── Soft-ramp the lettering out of the plate, inside the rim only ────────
    ink = Image.new("L", (w, h), 255)
    ip = ink.load()
    inset2 = (R - RIM_INSET) ** 2
    for y in range(h):
        dy = y - CY
        for x in range(w):
            dx = x - CX
            if dx * dx + dy * dy > inset2:
                continue
            t = (HI - px[x, y]) / (HI - LO)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            ip[x, y] = int(round(255 * (1.0 - t)))

    # ── Drop the rim-shadow crescents, keep the lettering ────────────────────
    seen = [[False] * w for _ in range(h)]
    keep = Image.new("L", (w, h), 0)
    kp = keep.load()
    n_kept = 0
    for y in range(h):
        for x in range(w):
            if ip[x, y] >= 128 or seen[y][x]:
                continue
            dq = deque([(x, y)])
            seen[y][x] = True
            cells = []
            while dq:
                a, b = dq.popleft()
                cells.append((a, b))
                for da in (-1, 0, 1):
                    for db in (-1, 0, 1):
                        na, nb = a + da, b + db
                        if (0 <= na < w and 0 <= nb < h and not seen[nb][na]
                                and ip[na, nb] < 128):
                            seen[nb][na] = True
                            dq.append((na, nb))
            far = max(math.hypot(a - CX, b - CY) for a, b in cells)
            if far >= RIM_TOUCH or len(cells) < MIN_COMP:
                continue
            n_kept += 1
            for a, b in cells:
                kp[a, b] = 255

    # Grow the keep-mask so the anti-aliased halo around each stroke survives.
    keep = keep.filter(ImageFilter.MaxFilter(5))
    kp = keep.load()
    out = Image.new("L", (w, h), 255)
    op = out.load()
    for y in range(h):
        for x in range(w):
            if kp[x, y]:
                op[x, y] = ip[x, y]

    # ── Crop to the lettering, pad square, upscale, de-noise ─────────────────
    xs = [x for x in range(w) for y in range(h) if op[x, y] < 250]
    ys = [y for y in range(h) for x in range(w) if op[x, y] < 250]
    x0, x1 = max(0, min(xs) - MARGIN), min(w - 1, max(xs) + MARGIN)
    y0, y1 = max(0, min(ys) - MARGIN), min(h - 1, max(ys) + MARGIN)
    crop = out.crop((x0, y0, x1 + 1, y1 + 1))
    cw, ch = crop.size
    side = max(cw, ch)
    square = Image.new("L", (side, side), 255)
    square.paste(crop, ((side - cw) // 2, (side - ch) // 2))

    big = square.resize((OUT_SIDE, OUT_SIDE), Image.BICUBIC)
    if BLUR > 0:
        big = big.filter(ImageFilter.GaussianBlur(BLUR))

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "samples")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "good_morning_input.png")
    big.save(dst)

    print(f"Components kept : {n_kept}  (rim-shadow crescents dropped)")
    print(f"Lettering crop  : {cw}×{ch} px -> square {side}")
    print(f"Blur            : {BLUR} px at {OUT_SIDE}px")
    print(f"Saved           : {dst}")


if __name__ == "__main__":
    main()
