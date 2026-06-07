#!/usr/bin/env python3
"""
Extract the smiley's facial features (eyes + open mouth) from the source image
and emit a clean B&W stencil input.

The source is a white smiley silhouette on a black background, with BLACK
facial features cut into the white face.  We want only those features as the
cinnamon pattern — NOT the black background and NOT the outer "Q" silhouette.

Method
------
  • threshold to black / white
  • flood-fill the black BACKGROUND inward from the image border
  • whatever black remains (i.e. is enclosed by the white face) = the features
  • output: features black on a white field, padded to a square so the disk
    mapping keeps the smiley's aspect ratio

Output: samples/smiley_input.png
"""

import os
from collections import deque
from PIL import Image

SRC = "/root/.claude/uploads/7ebed545-4d01-58b6-b8fd-9eb97a6e11c8/b247d0d7-1000690336.jpg"
THRESH = 128

img = Image.open(SRC).convert("L")
w, h = img.size
px = img.load()


def dark(x, y):
    return px[x, y] < THRESH


# ── Flood-fill the black background from the border ──────────────────────────
visited = [[False] * w for _ in range(h)]
dq = deque()
for x in range(w):
    for y in (0, h - 1):
        if dark(x, y) and not visited[y][x]:
            visited[y][x] = True
            dq.append((x, y))
for y in range(h):
    for x in (0, w - 1):
        if dark(x, y) and not visited[y][x]:
            visited[y][x] = True
            dq.append((x, y))
while dq:
    x, y = dq.popleft()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and dark(nx, ny):
            visited[ny][nx] = True
            dq.append((nx, ny))

# ── Build output: enclosed dark features = black, everything else = white ────
out = Image.new("L", (w, h), 255)
op = out.load()
feature_px = 0
for y in range(h):
    for x in range(w):
        if dark(x, y) and not visited[y][x]:
            op[x, y] = 0
            feature_px += 1

# ── Pad to a square canvas so aspect ratio is preserved in the round disk ────
side = max(w, h)
square = Image.new("L", (side, side), 255)
square.paste(out, ((side - w) // 2, (side - h) // 2))

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")
os.makedirs(out_dir, exist_ok=True)
dst = os.path.join(out_dir, "smiley_input.png")
square.save(dst)

print(f"Feature pixels kept: {feature_px}")
print(f"Saved → {dst}  ({side}×{side})")
