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
  • Holes mode  – red disk outline (#ff0000) to score, blue dots (#0000ff)
    to drill/cut through.
  • Cutout mode (--cutout) – every element is a CLOSED CONTOUR to cut, with
    fill off so only the outlines import.  Shapes are guaranteed hole-free:
    no contour is nested inside another, so a contour-fill cutter removes
    exactly the drawing and never a shape's interior (e.g. the inside of a
    cup handle stays attached via a thin bridge).

Recommended settings for a 3 mm thin-ply or 2 mm cardboard disk:
  --diameter 88   (matches a standard espresso / cappuccino cup rim)
  --grid     40   (2.2 mm cell spacing, good balance of detail and strength)
  --hole-diameter 1.5
"""

import math
import argparse
import sys
import os
from collections import deque, defaultdict

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

def _handle_outline_path(disk_cx, disk_cy, disk_r, bulb_cx, bulb_cy, bulb_r,
                         disk_angle_deg=73, bulb_angle_deg=38):
    """Return an SVG <path d="..."> string for a ping-pong-racket outline.

    G1 continuity at every junction: Bezier control points lie along the
    circle tangent so the path flows without kinks or corners.

    In SVG y-down coords the CW tangent at a point with outward unit radius
    u = (ux, uy) is t = (-uy, ux).  This gives:
      disk  upper connection (angle a from vertical): t = ( cos a, -sin a)
      disk  lower connection:                         t = (-cos a, -sin a)
      bulb  upper connection (angle b from vertical): t = ( cos b,  sin b)
      bulb  lower connection:                         t = (-cos b,  sin b)
    Control points are placed 0.40 x chord-length along these tangents.
    """
    a = math.radians(disk_angle_deg)
    b = math.radians(bulb_angle_deg)

    # Connection points on the disk (left side)
    dtx     = disk_cx - disk_r * math.sin(a)
    dty_top = disk_cy - disk_r * math.cos(a)
    dty_bot = disk_cy + disk_r * math.cos(a)

    # Connection points on the bulb (right side)
    btx     = bulb_cx + bulb_r * math.sin(b)
    bty_top = bulb_cy - bulb_r * math.cos(b)
    bty_bot = bulb_cy + bulb_r * math.cos(b)

    d_top = 0.40 * math.hypot(dtx - btx, dty_top - bty_top)
    d_bot = 0.40 * math.hypot(dtx - btx, dty_bot - bty_bot)

    # TOP edge  bulb→disk  (arc just left bulb going (cos b, sin b); disk arc
    # will depart going (cos a, -sin a))
    cp1_top = (btx + d_top * math.cos(b), bty_top + d_top * math.sin(b))
    cp2_top = (dtx - d_top * math.cos(a), dty_top + d_top * math.sin(a))

    # BOTTOM edge  disk→bulb  (disk arc just arrived going (-cos a, -sin a);
    # bulb arc will depart going (-cos b, sin b))
    cp1_bot = (dtx - d_bot * math.cos(a), dty_bot - d_bot * math.sin(a))
    cp2_bot = (btx + d_bot * math.cos(b), bty_bot - d_bot * math.sin(b))

    # large-arc=1, sweep=1 → CW arc >180° (right half of disk, left cap of bulb)
    return (
        f"M {btx:.3f} {bty_top:.3f} "
        f"C {cp1_top[0]:.3f} {cp1_top[1]:.3f}, "
        f"{cp2_top[0]:.3f} {cp2_top[1]:.3f}, "
        f"{dtx:.3f} {dty_top:.3f} "
        f"A {disk_r:.3f} {disk_r:.3f} 0 1 1 {dtx:.3f} {dty_bot:.3f} "
        f"C {cp1_bot[0]:.3f} {cp1_bot[1]:.3f}, "
        f"{cp2_bot[0]:.3f} {cp2_bot[1]:.3f}, "
        f"{btx:.3f} {bty_bot:.3f} "
        f"A {bulb_r:.3f} {bulb_r:.3f} 0 1 1 {btx:.3f} {bty_top:.3f} "
        f"Z"
    )


# ── Cutout (contour) mode ──────────────────────────────────────────────────────
# Instead of approximating the design with a grid of round holes, this mode cuts
# the solid dark areas out as real contours.  Closed shapes (the inside of an
# "o", a cup interior, a coffee-bean groove) would otherwise drop out as loose
# islands, so we detect every such island and carve a thin bridge of material
# back to the surrounding disk — exactly how a paper/laser stencil keeps its
# counters attached.

def _content_transform(img, target_frac=0.85):
    """Find the dark content's centre and the scale that makes it fill
    `target_frac` of the disk radius.  Returns (cx, cy, scale) in the image's
    normalised [-1, 1] space.  Used to centre any image inside the big circle.
    """
    w, h = img.size
    px = img.load()
    minx = miny = 1e9
    maxx = maxy = -1e9
    step = max(1, min(w, h) // 400)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if px[x, y] < 128:
                nx = x / w * 2 - 1
                ny = y / h * 2 - 1
                minx = min(minx, nx); maxx = max(maxx, nx)
                miny = min(miny, ny); maxy = max(maxy, ny)
    if maxx < minx:                       # no dark pixels
        return 0.0, 0.0, 1.0
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    rad = 0.0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if px[x, y] < 128:
                nx = x / w * 2 - 1
                ny = y / h * 2 - 1
                rad = max(rad, math.hypot(nx - cx, ny - cy))
    scale = target_frac / rad if rad > 0 else 1.0
    return cx, cy, scale


def make_image_sampler(image_path, invert=False, content_frac=0.85):
    """Return (sampler, transform) where sampler(dx, dy) -> bool says whether the
    centred/scaled image is dark at disk-normalised coords (dx, dy) ∈ [-1, 1]."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit("ERROR: Pillow is required for --image mode.  pip install Pillow")

    img = Image.open(image_path).convert("L")
    w, h = img.size
    px = img.load()
    cx, cy, scale = _content_transform(img, content_frac)

    def sampler(dx, dy):
        sx = cx + dx / scale
        sy = cy + dy / scale
        if not (-1.0 <= sx <= 1.0 and -1.0 <= sy <= 1.0):
            return False
        ix = min(w - 1, max(0, int((sx + 1) / 2 * w)))
        iy = min(h - 1, max(0, int((sy + 1) / 2 * h)))
        return (px[ix, iy] < 128) != invert

    return sampler, (cx, cy, scale)


def _build_cut_mask(grid_n, sampler):
    """Sample the design onto a grid_n×grid_n boolean mask (True = cut)."""
    mask   = [[False] * grid_n for _ in range(grid_n)]
    inside = [[False] * grid_n for _ in range(grid_n)]
    for r in range(grid_n):
        dy = (r + 0.5) / grid_n * 2 - 1
        for c in range(grid_n):
            dx = (c + 0.5) / grid_n * 2 - 1
            if dx * dx + dy * dy <= 1.0:
                inside[r][c] = True
                if sampler(dx, dy):
                    mask[r][c] = True
    return mask, inside


def _remove_small(mask, inside, grid_n, min_cells):
    """Drop dark specks smaller than `min_cells` (8-connected)."""
    seen = [[False] * grid_n for _ in range(grid_n)]
    for r in range(grid_n):
        for c in range(grid_n):
            if not mask[r][c] or seen[r][c]:
                continue
            comp = []
            dq = deque([(r, c)])
            seen[r][c] = True
            while dq:
                y, x = dq.popleft()
                comp.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if (0 <= ny < grid_n and 0 <= nx < grid_n
                                and mask[ny][nx] and not seen[ny][nx]):
                            seen[ny][nx] = True
                            dq.append((ny, nx))
            if len(comp) < min_cells:
                for (y, x) in comp:
                    mask[y][x] = False


def _anchor_white(mask, inside, grid_n):
    """Flag every 'kept' white cell connected to the disk rim (anchored
    material).  White cells NOT reachable from the rim are islands."""
    anchored = [[False] * grid_n for _ in range(grid_n)]
    dq = deque()
    for r in range(grid_n):
        for c in range(grid_n):
            if not inside[r][c] or mask[r][c]:
                continue
            rim = (r == 0 or c == 0 or r == grid_n - 1 or c == grid_n - 1
                   or not inside[r - 1][c] or not inside[r + 1][c]
                   or not inside[r][c - 1] or not inside[r][c + 1])
            if rim and not anchored[r][c]:
                anchored[r][c] = True
                dq.append((r, c))
    while dq:
        r, c = dq.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if (0 <= nr < grid_n and 0 <= nc < grid_n and inside[nr][nc]
                    and not mask[nr][nc] and not anchored[nr][nc]):
                anchored[nr][nc] = True
                dq.append((nr, nc))
    return anchored


def _add_bridges(mask, inside, anchored, grid_n, bridge_cells):
    """Carve a thin material bridge from every white island to the nearest
    anchored white cell, so closed counters stay attached.  Mutates `mask`
    (carved cells become white) and `anchored`.  Returns the bridge count."""
    half = max(0, bridge_cells // 2)

    def carve(r, c):
        for dr in range(-half, half + 1):
            for dc in range(-half, half + 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < grid_n and 0 <= nc < grid_n and inside[nr][nc]:
                    mask[nr][nc] = False
                    anchored[nr][nc] = True

    seen = [[False] * grid_n for _ in range(grid_n)]
    n_bridges = 0
    for r0 in range(grid_n):
        for c0 in range(grid_n):
            if (not inside[r0][c0] or mask[r0][c0] or anchored[r0][c0]
                    or seen[r0][c0]):
                continue
            # Collect this island (4-connected white, not anchored)
            island = []
            dq = deque([(r0, c0)])
            seen[r0][c0] = True
            while dq:
                y, x = dq.popleft()
                island.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < grid_n and 0 <= nx < grid_n and inside[ny][nx]
                            and not mask[ny][nx] and not anchored[ny][nx]
                            and not seen[ny][nx]):
                        seen[ny][nx] = True
                        dq.append((ny, nx))

            # BFS through the grid from the island to the nearest anchored cell
            parent = {}
            frontier = deque()
            for cell in island:
                parent[cell] = None
                frontier.append(cell)
            target = None
            while frontier and target is None:
                y, x = frontier.popleft()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < grid_n and 0 <= nx < grid_n) or not inside[ny][nx]:
                        continue
                    if (ny, nx) in parent:
                        continue
                    parent[(ny, nx)] = (y, x)
                    if anchored[ny][nx]:
                        target = (ny, nx)
                        break
                    frontier.append((ny, nx))

            # Carve the path (target → island) and the island itself
            if target is not None:
                node = target
                while node is not None:
                    carve(*node)
                    node = parent[node]
                n_bridges += 1
            for (y, x) in island:        # island is kept material now
                anchored[y][x] = True
    return n_bridges


def _count_enclosed(mask, inside, grid_n):
    """Count 'kept' white regions fully enclosed by cut cells (i.e. not reachable
    from the disk rim).  Each such region is a shape-inside-a-shape whose centre
    would drop out of a contour-fill cutter — after bridging this MUST be 0."""
    anchored = _anchor_white(mask, inside, grid_n)
    seen = [[False] * grid_n for _ in range(grid_n)]
    n = 0
    for r in range(grid_n):
        for c in range(grid_n):
            if (not inside[r][c] or mask[r][c] or anchored[r][c]
                    or seen[r][c]):
                continue
            n += 1
            dq = deque([(r, c)])
            seen[r][c] = True
            while dq:
                y, x = dq.popleft()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < grid_n and 0 <= nx < grid_n and inside[ny][nx]
                            and not mask[ny][nx] and not anchored[ny][nx]
                            and not seen[ny][nx]):
                        seen[ny][nx] = True
                        dq.append((ny, nx))
    return n


def _extract_loops(mask, inside, grid_n):
    """Trace the boundary of the cut region as closed corner loops using
    marching-squares edge segments chained together."""
    def D(r, c):
        return 0 <= r < grid_n and 0 <= c < grid_n and inside[r][c] and mask[r][c]

    adj = defaultdict(list)
    def seg(p, q):
        adj[p].append(q)
        adj[q].append(p)

    for r in range(grid_n):
        for c in range(grid_n):
            if not D(r, c):
                continue
            if not D(r - 1, c): seg((c, r),     (c + 1, r))
            if not D(r + 1, c): seg((c, r + 1), (c + 1, r + 1))
            if not D(r, c - 1): seg((c, r),     (c, r + 1))
            if not D(r, c + 1): seg((c + 1, r), (c + 1, r + 1))

    loops = []
    while adj:
        start = next(iter(adj))
        if not adj[start]:
            del adj[start]
            continue
        loop = [start]
        cur, prev = start, None
        while True:
            nbrs = adj[cur]
            nxt = next((p for p in nbrs if p != prev), nbrs[0])
            adj[cur].remove(nxt)
            adj[nxt].remove(cur)
            if not adj[cur]:
                del adj[cur]
            prev, cur = cur, nxt
            if cur == start:
                break
            loop.append(cur)
        adj.pop(start, None)
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def _chaikin(pts, iters=2):
    """Corner-cutting smoothing of a closed polygon (staircase → soft curve)."""
    for _ in range(iters):
        out = []
        n = len(pts)
        for i in range(n):
            (px, py), (qx, qy) = pts[i], pts[(i + 1) % n]
            out.append((0.75 * px + 0.25 * qx, 0.75 * py + 0.25 * qy))
            out.append((0.25 * px + 0.75 * qx, 0.25 * py + 0.75 * qy))
        pts = out
    return pts


def _cut_agreement(sampler, mask, grid_n, fine=400):
    """Recall/precision of the cut region vs. the original design (in-disk)."""
    cov = orig = cut = 0
    for j in range(fine):
        dy = (j + 0.5) / fine * 2 - 1
        for i in range(fine):
            dx = (i + 0.5) / fine * 2 - 1
            if dx * dx + dy * dy > 1.0:
                continue
            o = sampler(dx, dy)
            r = min(grid_n - 1, max(0, int((dy + 1) / 2 * grid_n)))
            c = min(grid_n - 1, max(0, int((dx + 1) / 2 * grid_n)))
            m = mask[r][c]
            if o:        orig += 1
            if m:        cut  += 1
            if o and m:  cov  += 1
    recall = cov / orig if orig else 0.0
    prec   = cov / cut  if cut  else 0.0
    return recall, prec


def generate_svg_cutout(sampler, diameter_mm=95.0, grid_n=300, bridge_mm=1.6,
                        handle=False, total_width_mm=None, bulb_diameter_mm=None):
    """Build SVG text for a contour-cut stencil (solid areas cut out, with
    auto-bridges holding every closed counter).  The design is centred in the
    big disk by the sampler's own transform.

    Returns (svg_text, n_loops, fill_ratio, n_bridges, recall, precision).
    """
    radius_mm = diameter_mm / 2.0
    disk_area = math.pi * radius_mm ** 2
    cell_mm   = diameter_mm / grid_n
    pad = 6.0

    # ── Canvas + disk/bulb placement (mirrors generate_svg) ──────────────────
    if handle:
        if total_width_mm is None:
            total_width_mm = diameter_mm + 51.0
        if bulb_diameter_mm is None:
            bulb_diameter_mm = diameter_mm * 0.295
        bulb_r   = bulb_diameter_mm / 2.0
        canvas_w = total_width_mm + 2 * pad
        canvas_h = diameter_mm + 2 * pad
        disk_cy  = canvas_h / 2.0
        disk_cx  = canvas_w - pad - radius_mm
        bulb_cx  = pad + bulb_r
        bulb_cy  = canvas_h / 2.0
    else:
        canvas_w = canvas_h = diameter_mm + 2 * pad
        disk_cx  = disk_cy = canvas_w / 2.0
        bulb_r   = None

    # ── Mask → islands → bridges → contours ──────────────────────────────────
    # Every shape must end up hole-free: a contour-fill cutter treats each closed
    # path as a solid region, so any kept island enclosed by a cut (the inside of
    # the cup handle, a letter's counter, …) would be sliced away with it.  We
    # bridge every enclosed island out to the anchored rim material, repeating
    # until _count_enclosed() reports zero, so no contour is ever nested inside
    # another and filling each contour solid reproduces the drawing exactly.
    mask, inside = _build_cut_mask(grid_n, sampler)
    _remove_small(mask, inside, grid_n, min_cells=3)
    bridge_cells = max(2, round(bridge_mm / cell_mm))
    n_bridges = 0
    for _ in range(8):
        anchored = _anchor_white(mask, inside, grid_n)
        added = _add_bridges(mask, inside, anchored, grid_n, bridge_cells)
        n_bridges += added
        if added == 0:
            break
    n_enclosed = _count_enclosed(mask, inside, grid_n)
    loops      = _extract_loops(mask, inside, grid_n)

    def corner_mm(X, Y):
        dx = X / grid_n * 2 - 1
        dy = Y / grid_n * 2 - 1
        return (disk_cx + dx * radius_mm, disk_cy + dy * radius_mm)

    # One CLOSED CONTOUR per cut region (no even-odd, no fill) so the cutter can
    # import each shape on its own.
    cut_paths = []
    for i, loop in enumerate(loops):
        pts = _chaikin([corner_mm(X, Y) for (X, Y) in loop], iters=2)
        d = "M " + f"{pts[0][0]:.3f} {pts[0][1]:.3f} " + " ".join(
            f"L {x:.3f} {y:.3f}" for x, y in pts[1:]) + " Z"
        cut_paths.append(f'    <path id="cut{i}" d="{d}"/>')

    n_cells    = sum(1 for r in range(grid_n) for c in range(grid_n) if mask[r][c])
    fill_ratio = n_cells * cell_mm ** 2 / disk_area
    recall, precision = _cut_agreement(sampler, mask, grid_n)
    cinnamon_g = fill_ratio * 3.0

    # ── SVG assembly ─────────────────────────────────────────────────────────
    if handle:
        outline_shape = (
            f'<path id="outline" '
            f'd="{_handle_outline_path(disk_cx, disk_cy, radius_mm, bulb_cx, bulb_cy, bulb_r)}"/>'
        )
        size_note = f"{total_width_mm}×{diameter_mm} mm paddle"
    else:
        outline_shape = (
            f'<circle id="outline" cx="{disk_cx}" cy="{disk_cy}" r="{radius_mm}"/>'
        )
        size_note = f"⌀{diameter_mm} mm disk"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!-- Coffee Stencil (cutout)  |  {size_note}  |  {len(loops)} cut shapes'
        f'  |  {n_bridges} bridges  |  {n_enclosed} enclosed islands'
        f'  |  fill {fill_ratio*100:.1f}%  |  agree {recall*100:.1f}% -->',
        '<!-- Generated by stencil_generator.py (contour cutout mode). -->',
        '<!-- Every element below is a CLOSED CONTOUR to cut.  Shapes are hole-free -->',
        '<!-- (no contour nested inside another), so a contour-fill cutter removes  -->',
        '<!-- exactly the drawing and never a shape\'s interior (e.g. the handle).   -->',
        '<svg xmlns="http://www.w3.org/2000/svg"',
        f'     width="{canvas_w}mm" height="{canvas_h}mm"',
        f'     viewBox="0 0 {canvas_w} {canvas_h}">',
        f'  <title>Coffee Stencil – {size_note} (cutout)</title>',
        '',
        '  <!-- Cut lines: fill is OFF so only the contours import into the cutter. -->',
        '  <g id="cut-contours" fill="none" stroke="#000000" stroke-width="0.3"',
        '     stroke-linejoin="round">',
        '',
        '    <!-- Paddle / disk silhouette (cut this last) -->',
        f'    {outline_shape}',
        '',
        '    <!-- Design cut-outs, one closed contour each -->',
        *cut_paths,
        '  </g>',
        '</svg>',
    ]
    return (('\n'.join(lines), len(loops), fill_ratio, n_bridges,
             recall, precision, n_enclosed))


def generate_svg(pattern_fn, diameter_mm=90.0, grid_n=40, hole_d_mm=1.5,
                 max_fill=0.20, handle=False, total_width_mm=None,
                 bulb_diameter_mm=None):
    """Build SVG text for the stencil.

    Parameters
    ----------
    pattern_fn       : callable(nx, ny) -> bool
    diameter_mm      : outer diameter of the wooden disk in mm
    grid_n           : number of grid cells across the full diameter
    hole_d_mm        : requested hole diameter in mm; auto-scaled down if needed
    max_fill         : maximum fraction of disk area that may be holes (default 0.20)
    handle           : if True, add a paddle handle to the left of the disk
    total_width_mm   : total outline width (disk + handle).  Defaults to
                       diameter_mm + 51 to match a 95→146 mm reference design.
    bulb_diameter_mm : handle-end bulb diameter.  Defaults to ~26 % of the disk
                       diameter (≈25 mm for a 95 mm disk).

    Returns
    -------
    svg_text      : str
    n_holes       : int
    fill_ratio    : float
    actual_hole_d : float
    """
    radius_mm = diameter_mm / 2.0
    disk_area = math.pi * radius_mm ** 2
    cell      = diameter_mm / grid_n
    hole_r    = hole_d_mm / 2.0

    pad = 6.0

    # ── Canvas + disk/bulb placement ─────────────────────────────────────────
    if handle:
        if total_width_mm is None:
            total_width_mm = diameter_mm + 51.0          # 95 → 146 mm reference
        if bulb_diameter_mm is None:
            bulb_diameter_mm = diameter_mm * 0.295       # ≈28 mm for 95 mm disk
        bulb_r   = bulb_diameter_mm / 2.0
        canvas_w = total_width_mm + 2 * pad
        canvas_h = diameter_mm   + 2 * pad
        disk_cy  = canvas_h / 2.0
        disk_cx  = canvas_w - pad - radius_mm
        bulb_cx  = pad + bulb_r
        bulb_cy  = canvas_h / 2.0
    else:
        canvas_w = canvas_h = diameter_mm + 2 * pad
        disk_cx  = disk_cy  = canvas_w / 2.0
        bulb_r   = None

    # Collect hole centres — holes live ONLY inside the disk, never the handle.
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
                hole_centres.append((disk_cx + mx, disk_cy + my))

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

    if handle:
        outline_svg = (
            f'  <path d="{_handle_outline_path(disk_cx, disk_cy, radius_mm, bulb_cx, bulb_cy, bulb_r)}"\n'
            '        fill="none" stroke="#ff0000" stroke-width="0.3"/>'
        )
        size_note = f"{total_width_mm}×{diameter_mm} mm paddle"
    else:
        outline_svg = (
            f'  <circle cx="{disk_cx}" cy="{disk_cy}" r="{radius_mm}"\n'
            '          fill="none" stroke="#ff0000" stroke-width="0.3"/>'
        )
        size_note = f"⌀{diameter_mm} mm disk"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!-- Coffee Stencil  |  {size_note}  |  {n_holes} holes'
        f'  |  fill {fill_ratio*100:.1f}%  |  ~{cinnamon_g:.1f} g cinnamon -->',
        f'<!-- Generated by stencil_generator.py -->',
        '<svg xmlns="http://www.w3.org/2000/svg"',
        f'     width="{canvas_w}mm" height="{canvas_h}mm"',
        f'     viewBox="0 0 {canvas_w} {canvas_h}">',
        f'  <title>Coffee Stencil – {size_note}</title>',
        '',
        '  <!-- Outline: RED = laser-cut / score this line -->',
        outline_svg,
        '',
        '  <!-- Holes: BLUE = cut/drill through -->',
        f'  <g fill="#0000ff" stroke="none">',
    ]

    for (hx, hy) in hole_centres:
        lines.append(f'    <circle cx="{hx:.4f}" cy="{hy:.4f}" r="{hole_r:.4f}"/>')

    lines += [
        '  </g>',
        '',
        f'  <text x="{disk_cx}" y="{canvas_h - 1.5}"',
        '        text-anchor="middle" font-family="sans-serif"',
        '        font-size="2.5" fill="#999999">',
        f'    {size_note} · {n_holes} holes · hole ⌀{actual_hole_d:.2f} mm'
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

              # Contour CUTOUT mode: cut solid shapes (with auto-bridges),
              # design auto-centred in the disk
              python stencil_generator.py --image logo.png --cutout --handle

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
        "--grid", type=int, default=None, metavar="N",
        help="Grid resolution – cells across the diameter.  Default 40 in holes "
             "mode, 300 in --cutout mode.  Higher = finer detail.",
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
        "--handle", action="store_true",
        help="Add a paddle handle to the left of the disk (95→146 mm reference "
             "shape: round disk + small teardrop bulb joined by a smooth waist).",
    )
    parser.add_argument(
        "--total-width", dest="total_width", type=float, default=None, metavar="MM",
        help="Total outline width (disk + handle).  Only used with --handle. "
             "Defaults to diameter + 51 mm.",
    )
    parser.add_argument(
        "--bulb-diameter", dest="bulb_d", type=float, default=None, metavar="MM",
        help="Handle-end bulb diameter.  Only used with --handle. "
             "Defaults to ~26%% of disk diameter.",
    )
    parser.add_argument(
        "--cutout", action="store_true",
        help="Contour-cut mode: cut the solid dark areas out as real shapes "
             "(with auto-bridges holding every closed counter) instead of "
             "approximating the design with a grid of round holes.  The design "
             "is auto-centred in the disk.",
    )
    parser.add_argument(
        "--bridge-width", dest="bridge_mm", type=float, default=1.6, metavar="MM",
        help="Width of the material bridges that hold cut-out islands in place "
             "(only used with --cutout, default: 1.6).",
    )
    parser.add_argument(
        "--content-scale", dest="content_frac", type=float, default=0.85,
        metavar="FRAC",
        help="Fraction of the disk radius the design fills when auto-centred "
             "(only used with --cutout + --image, default: 0.85).",
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

    if args.image:
        default_out = os.path.splitext(os.path.basename(args.image))[0] + "_stencil.svg"
        label       = os.path.basename(args.image)
    else:
        default_out = f"{args.pattern}_stencil.svg"
        label       = args.pattern
    out_path = args.output or default_out

    # ── Cutout (contour) mode ────────────────────────────────────────────────
    if args.cutout:
        grid_n = args.grid or 300
        if args.image:
            sampler, (cx, cy, scale) = make_image_sampler(
                args.image, invert=args.invert, content_frac=args.content_frac)
        else:
            base_fn = PATTERNS[args.pattern]
            sampler = ((lambda dx, dy, _f=base_fn: not _f(dx, dy))
                       if args.invert else base_fn)

        (svg_text, n_loops, fill_ratio, n_bridges, recall, precision,
         n_enclosed) = generate_svg_cutout(
            sampler,
            diameter_mm=args.diameter,
            grid_n=grid_n,
            bridge_mm=args.bridge_mm,
            handle=args.handle,
            total_width_mm=args.total_width,
            bulb_diameter_mm=args.bulb_d,
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg_text)
        png_path = os.path.splitext(out_path)[0] + ".png"
        _svg_to_png(os.path.abspath(out_path), png_path)

        cinnamon_g = fill_ratio * 3.0
        enclosed_note = ("all interiors bridged ✓" if n_enclosed == 0
                         else f"⚠ {n_enclosed} still enclosed")
        print(
            f"Saved:  {out_path}  (contour cutout mode)\n"
            f"  Pattern    : {label}\n"
            f"  Disk       : ⌀{args.diameter} mm  (design auto-centred)\n"
            f"  Resolution : {grid_n}×{grid_n}  ({args.diameter/grid_n:.2f} mm/cell)\n"
            f"  Cut shapes : {n_loops} closed contours  ·  {n_bridges} bridges (⌀{args.bridge_mm} mm)\n"
            f"  Nesting    : {enclosed_note}  (no shape-inside-a-shape)\n"
            f"  Fill ratio : {fill_ratio*100:.1f}%  →  ~{cinnamon_g:.1f} g cinnamon\n"
            f"  Agreement  : {recall*100:.1f}% recall · {precision*100:.1f}% precision\n"
        )
        return

    # ── Holes mode (default) ─────────────────────────────────────────────────
    grid_n = args.grid or 40
    if args.image:
        pattern_fn = load_image_pattern(args.image, invert=args.invert)
    else:
        base_fn = PATTERNS[args.pattern]
        if args.invert:
            pattern_fn = lambda nx, ny, _f=base_fn: not _f(nx, ny)
        else:
            pattern_fn = base_fn

    # Generate
    svg_text, n_holes, fill_ratio, actual_hole_d = generate_svg(
        pattern_fn,
        diameter_mm=args.diameter,
        grid_n=grid_n,
        hole_d_mm=args.hole_d,
        max_fill=args.max_fill,
        handle=args.handle,
        total_width_mm=args.total_width,
        bulb_diameter_mm=args.bulb_d,
    )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(svg_text)
    png_path = os.path.splitext(out_path)[0] + ".png"
    _svg_to_png(os.path.abspath(out_path), png_path)

    cell_mm      = args.diameter / grid_n
    cinnamon_g   = fill_ratio * 3.0
    scaled_note  = (f"  (auto-scaled from ⌀{args.hole_d} mm to stay within "
                    f"{args.max_fill*100:.0f}% fill cap)"
                    if actual_hole_d < args.hole_d - 0.01 else "")
    print(
        f"Saved:  {out_path}\n"
        f"  Pattern    : {label}\n"
        f"  Disk       : ⌀{args.diameter} mm\n"
        f"  Grid       : {grid_n}×{grid_n}  ({cell_mm:.1f} mm/cell)\n"
        f"  Holes      : {n_holes}  (⌀{actual_hole_d:.2f} mm each){scaled_note}\n"
        f"  Fill ratio : {fill_ratio*100:.1f}%  →  ~{cinnamon_g:.1f} g cinnamon per dusting\n"
    )


def _svg_to_png(svg_path, png_path, dpi=150):
    """Render svg_path → png_path at the given DPI using cairosvg."""
    try:
        import cairosvg
    except ImportError:
        print("  (PNG skipped — install cairosvg for PNG output: pip install cairosvg)")
        return
    # cairosvg scale: SVG is in mm; 1 mm = dpi/25.4 px
    scale = dpi / 25.4
    cairosvg.svg2png(url=svg_path, write_to=png_path, scale=scale)
    print(f"  PNG    : {png_path}  ({dpi} dpi)")


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
