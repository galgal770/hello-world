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


def _carve_capsule(mask, inside, anchored, grid_n, p, q, radius):
    """Carve a capsule — the segment p→q dilated by a disc of `radius` cells —
    turning those cells back into wood.

    Sweeping an axis-aligned SQUARE along a 4-connected staircase (the previous
    approach) left a blunt, ragged notch that ran diagonally across the stroke
    and grew spurs where the staircase turned.  A capsule is straight, of
    constant width, and closes with circular arcs, so the two stroke ends left
    behind read as a deliberate pen lift rather than as damage.

    Carving only ever turns cut cells back into wood, so it can never merge two
    separate cut shapes — at worst it interrupts the one stroke it crosses,
    which is exactly the intent.
    """
    (r0, c0), (r1, c1) = p, q
    dr, dc = r1 - r0, c1 - c0
    seg2 = dr * dr + dc * dc
    pad = int(math.ceil(radius)) + 1
    for r in range(max(0, min(r0, r1) - pad), min(grid_n, max(r0, r1) + pad + 1)):
        for c in range(max(0, min(c0, c1) - pad), min(grid_n, max(c0, c1) + pad + 1)):
            if not inside[r][c]:
                continue
            if seg2 == 0:
                t = 0.0
            else:
                t = ((r - r0) * dr + (c - c0) * dc) / seg2
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            fr, fc = r0 + t * dr, c0 + t * dc
            if (r - fr) ** 2 + (c - fc) ** 2 <= radius * radius:
                mask[r][c] = False
                if anchored is not None:
                    anchored[r][c] = True


def _oblique_span(p, q, angle_deg, radius):
    """Slant the crossing p->q by `angle_deg` about its midpoint.

    A cut taken square across a stroke leaves two blunt, flat ends.  Running it
    at an angle leaves two wedges that taper to a point instead — the way a
    brush lifts off the paper — which is exactly how the breaks already drawn
    into the artwork look.  The span is lengthened by 1/cos(angle) so the slanted
    cut still crosses the whole stroke.
    """
    if not angle_deg:
        return p, q
    dr, dc = q[0] - p[0], q[1] - p[1]
    ln = math.hypot(dr, dc)
    if ln < 1e-9:
        return p, q
    nr, nc = dr / ln, dc / ln          # across the stroke
    tr, tc = -nc, nr                   # along the stroke
    th = math.radians(angle_deg)
    ur = nr * math.cos(th) + tr * math.sin(th)
    uc = nc * math.cos(th) + tc * math.sin(th)
    half = ln / 2.0 / max(0.25, math.cos(th)) + radius + 1.0
    mr, mc = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
    return ((int(round(mr - half * ur)), int(round(mc - half * uc))),
            (int(round(mr + half * ur)), int(round(mc + half * uc))))


def _add_bridges(mask, inside, anchored, grid_n, bridge_cells,
                 side="auto", angle_deg=0.0):
    """Carve a material bridge from every white island to the anchored wood, so
    closed counters stay attached.  Mutates `mask` (carved cells become wood)
    and `anchored`.  Returns (bridge count, carved centre-line paths).

    `side` biases WHERE the break is put — among crossings nearly as thin as the
    thinnest, the one furthest toward that edge of the island wins, so the break
    can be placed where it reads best.  `angle_deg` slants the cut so the stroke
    ends taper instead of stopping square.
    """
    radius = bridge_cells / 2.0
    INF = 1 << 30

    # Steps from every cell to the nearest anchored wood cell.  For a cell in an
    # island that is the length of the crossing it would need.
    D = [[INF] * grid_n for _ in range(grid_n)]
    dq = deque()
    for r in range(grid_n):
        for c in range(grid_n):
            if inside[r][c] and anchored[r][c]:
                D[r][c] = 0
                dq.append((r, c))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if (0 <= ny < grid_n and 0 <= nx < grid_n and inside[ny][nx]
                    and D[ny][nx] == INF):
                D[ny][nx] = D[y][x] + 1
                dq.append((ny, nx))

    def pick(cells):
        best = min(D[r][c] for (r, c) in cells)
        tol = best + max(2, int(round(best * 0.6)))
        near = [(r, c) for (r, c) in cells if D[r][c] <= tol]
        if side == "bottom":
            return max(near, key=lambda rc: rc[0])
        if side == "top":
            return min(near, key=lambda rc: rc[0])
        if side == "right":
            return max(near, key=lambda rc: rc[1])
        if side == "left":
            return min(near, key=lambda rc: rc[1])
        return min(near, key=lambda rc: D[rc[0]][rc[1]])

    def downhill(start):
        r, c = start
        while D[r][c] > 0:
            step = None
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = r + dy, c + dx
                if (0 <= ny < grid_n and 0 <= nx < grid_n
                        and D[ny][nx] == D[r][c] - 1):
                    step = (ny, nx)
                    break
            if step is None:
                break
            r, c = step
        return (r, c)

    def connects(start):
        """Did the carve actually join `start` to wood that was already held?"""
        seen_w = {start}
        dq2 = deque([start])
        while dq2:
            y, x = dq2.popleft()
            if D[y][x] == 0:
                return True
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if (0 <= ny < grid_n and 0 <= nx < grid_n and inside[ny][nx]
                        and not mask[ny][nx] and (ny, nx) not in seen_w):
                    seen_w.add((ny, nx))
                    dq2.append((ny, nx))
        return False

    seen = [[False] * grid_n for _ in range(grid_n)]
    bridge_paths = []
    n_bridges = 0
    for r0 in range(grid_n):
        for c0 in range(grid_n):
            if (not inside[r0][c0] or mask[r0][c0] or anchored[r0][c0]
                    or seen[r0][c0]):
                continue
            island = []
            dq3 = deque([(r0, c0)])
            seen[r0][c0] = True
            while dq3:
                y, x = dq3.popleft()
                island.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < grid_n and 0 <= nx < grid_n and inside[ny][nx]
                            and not mask[ny][nx] and not anchored[ny][nx]
                            and not seen[ny][nx]):
                        seen[ny][nx] = True
                        dq3.append((ny, nx))

            reachable = [rc for rc in island if D[rc[0]][rc[1]] < INF]
            if reachable:
                p = pick(reachable)
                q = downhill(p)
                A, B = _oblique_span(p, q, angle_deg, radius)
                _carve_capsule(mask, inside, anchored, grid_n, A, B, radius)
                if not connects(p):
                    # The slanted cut missed the wood on one side; fall back to
                    # the square crossing, which always spans it.
                    _carve_capsule(mask, inside, anchored, grid_n, p, q, radius)
                    A, B = p, q
                span = int(math.hypot(B[0] - A[0], B[1] - A[1]))
                steps = max(2, span + 1)
                bridge_paths.append([
                    (int(round(A[0] + s / steps * (B[0] - A[0]))),
                     int(round(A[1] + s / steps * (B[1] - A[1]))))
                    for s in range(steps + 1)])
                n_bridges += 1
            for (y, x) in island:
                anchored[y][x] = True
    return n_bridges, bridge_paths

def _dist_to_cut(mask, grid_n):
    """Chamfer distance from every cell to the nearest CUT cell, in thirds of a
    cell.  For a wood cell that is its distance to the edge of the nearest hole,
    so twice it (less one cell) is the width of the wood there."""
    return _chamfer(mask, grid_n)


def _chamfer(seeds, grid_n):
    """Two-pass chamfer (3,4) distance from every cell to the nearest True cell
    of `seeds`.  Returned in THIRDS of a cell, so divide by 3 to get cells."""
    mask = seeds
    BIG = 1 << 30
    d = [[0 if mask[r][c] else BIG for c in range(grid_n)] for r in range(grid_n)]
    for r in range(grid_n):
        row  = d[r]
        prev = d[r - 1] if r > 0 else None
        for c in range(grid_n):
            v = row[c]
            if v == 0:
                continue
            if prev is not None:
                if c > 0:              v = min(v, prev[c - 1] + 4)
                v = min(v, prev[c] + 3)
                if c < grid_n - 1:     v = min(v, prev[c + 1] + 4)
            if c > 0:                  v = min(v, row[c - 1] + 3)
            row[c] = v
    for r in range(grid_n - 1, -1, -1):
        row = d[r]
        nxt = d[r + 1] if r < grid_n - 1 else None
        for c in range(grid_n - 1, -1, -1):
            v = row[c]
            if v == 0:
                continue
            if nxt is not None:
                if c < grid_n - 1:     v = min(v, nxt[c + 1] + 4)
                v = min(v, nxt[c] + 3)
                if c > 0:              v = min(v, nxt[c - 1] + 4)
            if c < grid_n - 1:         v = min(v, row[c + 1] + 3)
            row[c] = v
    return d


def _thin_links(mask, inside, grid_n, cell_mm, min_mm, widen=False, rounds=4):
    """Find — and optionally widen — wood that is the SOLE link between two wood
    regions yet thinner than `min_mm`.

    A bridge can be full width and the stencil still fail: where two lines of
    the artwork happen to run close, the sliver of wood between them is just as
    fragile, merges under the laser kerf, and drops whatever it was holding.

    Stroke tips are deliberately left alone.  Only pinch points — where wood
    grown out from two DIFFERENT thick regions meets — are widened, so tapering
    terminals keep their points and the lettering is not blunted.

    Returns the number of pinch points widened.
    """
    r_cells = (min_mm / 2.0) / cell_mm
    fixed = 0
    for _ in range(rounds):
        wood = [[inside[r][c] and not mask[r][c] for c in range(grid_n)]
                for r in range(grid_n)]
        d = _chamfer(mask, grid_n)
        # "Thick" wood = a disc of diameter min_mm fits here.
        thick = [[wood[r][c] and d[r][c] / 3.0 >= r_cells
                  for c in range(grid_n)] for r in range(grid_n)]

        label = [[0] * grid_n for _ in range(grid_n)]
        k = 0
        for r in range(grid_n):
            for c in range(grid_n):
                if not thick[r][c] or label[r][c]:
                    continue
                k += 1
                dq = deque([(r, c)])
                label[r][c] = k
                while dq:
                    y, x = dq.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if (0 <= ny < grid_n and 0 <= nx < grid_n
                                and thick[ny][nx] and not label[ny][nx]):
                            label[ny][nx] = k
                            dq.append((ny, nx))
        if k < 2:
            break

        # Grow each thick region outwards over the thin wood; every wood cell
        # ends up owned by its nearest thick region.
        dq = deque((r, c) for r in range(grid_n) for c in range(grid_n)
                   if label[r][c])
        while dq:
            y, x = dq.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if (0 <= ny < grid_n and 0 <= nx < grid_n and wood[ny][nx]
                        and not label[ny][nx]):
                    label[ny][nx] = label[y][x]
                    dq.append((ny, nx))

        # Where two different owners touch, the wood between them is a pinch.
        pinch = []
        for r in range(grid_n):
            for c in range(grid_n):
                if not label[r][c]:
                    continue
                for dy, dx in ((1, 0), (0, 1)):
                    ny, nx = r + dy, c + dx
                    if (ny < grid_n and nx < grid_n and label[ny][nx]
                            and label[ny][nx] != label[r][c]):
                        pinch.append((r, c))
                        break
        if not pinch:
            break

        # Count distinct pinch SITES, not cells: one isthmus shows up as a whole
        # cross-section of meeting cells.
        pset, seen_p, sites = set(pinch), set(), 0
        for p in pset:
            if p in seen_p:
                continue
            sites += 1
            dq = deque([p])
            seen_p.add(p)
            while dq:
                y, x = dq.popleft()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        q = (y + dy, x + dx)
                        if q in pset and q not in seen_p:
                            seen_p.add(q)
                            dq.append(q)
        if not widen:
            return sites                      # detection only; artwork untouched
        for (r, c) in pinch:
            _carve_capsule(mask, inside, None, grid_n, (r, c), (r, c), r_cells)
        fixed += sites
    return fixed


def _min_bridge_neck_mm(mask, grid_n, cell_mm, bridge_paths):
    """Narrowest wood neck along any carved bridge, in mm.

    At a bridge centre-line cell the wood reaches out to the nearest cut cell
    in either direction, so the neck there spans (2·distance − 1) cells.  The
    bottleneck is the minimum over every centre-line cell of every bridge.
    Returns None when the design needed no bridges."""
    if not bridge_paths:
        return None
    d = _dist_to_cut(mask, grid_n)
    best = None
    for path in bridge_paths:
        for (r, c) in path:
            neck = (2.0 * (d[r][c] / 3.0) - 1.0) * cell_mm
            if best is None or neck < best:
                best = neck
    return best


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


def _rdp_open(seq, eps):
    """Douglas–Peucker simplification of an OPEN polyline (iterative, so long
    contours can't blow the recursion limit)."""
    n = len(seq)
    if n < 3:
        return list(seq)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        x0, y0 = seq[i]
        x1, y1 = seq[j]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        imax, dmax = -1, -1.0
        for k in range(i + 1, j):
            x, y = seq[k]
            d = (math.hypot(x - x0, y - y0) if L < 1e-12
                 else abs(dy * (x - x0) - dx * (y - y0)) / L)
            if d > dmax:
                dmax, imax = d, k
        if dmax > eps and imax > 0:
            keep[imax] = True
            stack.append((i, imax))
            stack.append((imax, j))
    return [seq[k] for k in range(n) if keep[k]]


def _rdp_closed(pts, eps):
    """Douglas–Peucker simplification of a CLOSED polygon.  Marching squares
    walks the cell edges, so every traced contour is a staircase of 90° steps;
    simplifying with a tolerance of a fraction of a millimetre collapses those
    steps onto the line the artwork actually followed."""
    n = len(pts)
    if n < 8:
        return list(pts)
    half = n // 2
    a = _rdp_open(pts[:half + 1], eps)
    b = _rdp_open(pts[half:] + [pts[0]], eps)
    out = a[:-1] + b[:-1]
    return out if len(out) >= 4 else list(pts)


def _bezier_path(pts):
    """Closed cubic-Bézier path through `pts` (Catmull–Rom converted to Bézier).
    The curve interpolates every point and is C1-continuous, so the cut reads as
    one flowing line instead of a chain of straight segments."""
    n = len(pts)
    d = [f"M {pts[0][0]:.3f} {pts[0][1]:.3f}"]
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(f"C {c1[0]:.3f} {c1[1]:.3f}, {c2[0]:.3f} {c2[1]:.3f},"
                 f" {p2[0]:.3f} {p2[1]:.3f}")
    d.append("Z")
    return " ".join(d)


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


def generate_svg_cutout(sampler, diameter_mm=95.0, grid_n=300, bridge_mm=2.4,
                        handle=False, total_width_mm=None, bulb_diameter_mm=None,
                        smooth_mm=0.15, min_wood_mm=2.0,
                        bridge_side="auto", bridge_angle=0.0):
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
    bridge_paths = []
    for _ in range(8):
        anchored = _anchor_white(mask, inside, grid_n)
        added, paths = _add_bridges(mask, inside, anchored, grid_n,
                                    bridge_cells, side=bridge_side,
                                    angle_deg=bridge_angle)
        n_bridges += added
        bridge_paths.extend(paths)
        if added == 0:
            break
    # A bridge can still end up thinner than asked for: where the crossing runs
    # close to a NEIGHBOURING hole, that hole pinches the wood even though the
    # capsule itself is full width — and two cut lines that close together merge
    # under the kerf.  Widen any short bridge until it measures up (widening also
    # pushes back the neighbouring hole, since carving turns cut cells to wood).
    extra = 0
    for _ in range(6):
        d = _dist_to_cut(mask, grid_n)
        short = [p for p in bridge_paths
                 if min((2.0 * (d[r][c] / 3.0) - 1.0) * cell_mm for (r, c) in p)
                 < bridge_mm - 0.5 * cell_mm]
        if not short:
            break
        extra += 1
        anchored = _anchor_white(mask, inside, grid_n)
        for p in short:
            _carve_capsule(mask, inside, anchored, grid_n, p[0], p[-1],
                           bridge_cells / 2.0 + extra)

    # Same failure, different cause: where two lines of the artwork run close,
    # the sliver between them is as fragile as an undersized bridge.
    widen   = bool(min_wood_mm and min_wood_mm > 0)
    n_pinch = _thin_links(mask, inside, grid_n, cell_mm,
                          min_wood_mm if widen else 2.0, widen=widen)

    n_enclosed = _count_enclosed(mask, inside, grid_n)
    neck_mm    = _min_bridge_neck_mm(mask, grid_n, cell_mm, bridge_paths)
    loops      = _extract_loops(mask, inside, grid_n)

    def corner_mm(X, Y):
        dx = X / grid_n * 2 - 1
        dy = Y / grid_n * 2 - 1
        return (disk_cx + dx * radius_mm, disk_cy + dy * radius_mm)

    # One CLOSED CONTOUR per cut region (no even-odd, no fill) so the cutter can
    # import each shape on its own.
    cut_paths = []
    n_nodes = 0
    for i, loop in enumerate(loops):
        pts = [corner_mm(X, Y) for (X, Y) in loop]
        pts = _rdp_closed(pts, smooth_mm)   # collapse the marching-squares steps
        pts = _chaikin(pts, iters=1)        # relax the remaining corners
        n_nodes += len(pts)
        cut_paths.append(f'    <path id="cut{i}" d="{_bezier_path(pts)}"/>')

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

    neck_note = (f'  |  narrowest wood neck {neck_mm:.2f} mm'
                 if neck_mm is not None else '')
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!-- Coffee Stencil (cutout)  |  {size_note}  |  {len(loops)} cut shapes'
        f'  |  {n_bridges} bridges  |  {n_enclosed} enclosed islands{neck_note}'
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
             recall, precision, n_enclosed, neck_mm, n_pinch))


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
        "--bridge-width", dest="bridge_mm", type=float, default=2.4, metavar="MM",
        help="Width of the material bridges that hold cut-out islands in place "
             "(only used with --cutout, default: 2.4).  Each bridge is carved as "
             "a straight capsule across the THINNEST crossing of the stroke, so "
             "it reads as a pen lift rather than a notch.  Don't go below ~2 mm: "
             "the laser kerf eats ~0.2 mm per side, and a 1.6 mm bridge has been "
             "observed to burn away entirely and drop the part it was holding.",
    )
    parser.add_argument(
        "--smooth", dest="smooth_mm", type=float, default=0.15, metavar="MM",
        help="Contour smoothing tolerance in mm (only used with --cutout, "
             "default: 0.15).  Contours are traced on the grid and so come out "
             "as 90° staircases; they are simplified to within this tolerance "
             "and emitted as cubic Béziers, which removes the pixelation.  "
             "Raise it for smoother/softer curves, lower it to track the "
             "artwork more literally.",
    )
    parser.add_argument(
        "--bridge-side", dest="bridge_side", default="auto",
        choices=("auto", "top", "bottom", "left", "right"),
        help="Where to put each bridge (only with --cutout, default: auto). "
             "'auto' takes the thinnest crossing; the others take the thinnest "
             "crossing that also sits furthest toward that edge, so the break "
             "can be placed where it reads best in the drawing.",
    )
    parser.add_argument(
        "--bridge-angle", dest="bridge_angle", type=float, default=0.0,
        metavar="DEG",
        help="Slant of the bridge cut in degrees (only with --cutout, default: "
             "0 = square across the stroke).  A slanted cut leaves the two "
             "stroke ends tapering to a point, like a brush lifting off, "
             "instead of stopping blunt.  40-60 reads well.",
    )
    parser.add_argument(
        "--min-wood", dest="min_wood_mm", type=float, default=0.0, metavar="MM",
        help="Minimum width of wood that is the sole link between two regions "
             "(only used with --cutout, default: 2.0).  Where two lines of the "
             "artwork run this close, the sliver between them merges under the "
             "kerf and drops whatever it held.  Default 0 = report only, so the "
             "artwork is reproduced untouched; set e.g. 2.0 to carve the "
             "neighbouring holes back until such links measure up (this trims "
             "the design, so check the agreement figure).  Tips stay pointed.",
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
         n_enclosed, neck_mm, n_pinch) = generate_svg_cutout(
            sampler,
            diameter_mm=args.diameter,
            grid_n=grid_n,
            bridge_mm=args.bridge_mm,
            handle=args.handle,
            total_width_mm=args.total_width,
            bulb_diameter_mm=args.bulb_d,
            smooth_mm=args.smooth_mm,
            min_wood_mm=args.min_wood_mm,
            bridge_side=args.bridge_side,
            bridge_angle=args.bridge_angle,
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg_text)
        png_path = os.path.splitext(out_path)[0] + ".png"
        _svg_to_png(os.path.abspath(out_path), png_path)

        cinnamon_g = fill_ratio * 3.0
        enclosed_note = ("all interiors bridged ✓" if n_enclosed == 0
                         else f"⚠ {n_enclosed} still enclosed")
        if args.min_wood_mm and args.min_wood_mm > 0:
            thin_note = (f"{n_pinch} pinch point(s) widened to "
                         f"{args.min_wood_mm} mm")
        elif n_pinch:
            thin_note = (f"⚠ {n_pinch} link(s) under 2.0 mm — artwork left as "
                         f"drawn; pass --min-wood to widen")
        else:
            thin_note = "no link under 2.0 mm  ✓"
        neck_note = ("no bridges needed" if neck_mm is None
                     else f"{neck_mm:.2f} mm narrowest wood neck"
                          + ("" if neck_mm >= 2.0 else "  ⚠ fragile"))
        print(
            f"Saved:  {out_path}  (contour cutout mode)\n"
            f"  Pattern    : {label}\n"
            f"  Disk       : ⌀{args.diameter} mm  (design auto-centred)\n"
            f"  Resolution : {grid_n}×{grid_n}  ({args.diameter/grid_n:.2f} mm/cell)\n"
            f"  Cut shapes : {n_loops} closed contours  ·  {n_bridges} bridges (⌀{args.bridge_mm} mm)\n"
            f"  Nesting    : {enclosed_note}  (no shape-inside-a-shape)\n"
            f"  Strength   : {neck_note}\n"
            f"  Thin wood  : {thin_note}\n"
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
