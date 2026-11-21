"""The Herald's House, dressed (design pass, phase 1): what herald_house.py builds plain gets relief, texture and a
skyline here, without moving a wall, a door, a bed or a light.

  - the wall (wall): a rough plinth, pilasters every BAY blocks carried up into taller merlons, merlons two wide between
    them, a corbel course under the battlements, an arrow loop in each bay outside and a blind arch in each bay inside,
    weathering in patches (moss low, cracks high) instead of salt and pepper, a buttress at each pilaster's foot where
    the ground is free, and two roofed hoardings on each side's walk;
  - the gatehouse and its towers (gatehouse): machicolations under the battlements, string courses, arrow loops, a
    keystone over the arch and a tiled roof inside each tower's parapet;
  - the roofs (roofs): each one's eaves and ridge in a kin material, the sheet broken with a few kin blocks in patches,
    dormers on the long gables and a lantern (a small raised roof) on the wide hips.

Only blocks: nothing here adds an entity, a block entity or a light source. construct() calls dress(t) once every
building stands and before the door paths are drawn; herald_house.errors() then checks the result like the rest.
"""
from core import parse_state

BAY = 8                    # the wall's rhythm: a pilaster every BAY blocks, the parapet's lantern in the middle of each


def _hh():
    import herald_house
    return herald_house


def _name(st):
    return (st or "minecraft:air").split("[")[0].replace("minecraft:", "")


def _noise(a, b, c=0):
    """0..1, the same for neighbours two apart: weathering comes in patches."""
    hh = _hh()
    return (hh._h(a // 2, b // 2, c) % 997) / 997.0


def _grain(x, y, z):
    return (_hh()._h(x, y, z) % 991) / 991.0


def stone(x, y, z, low, high, along=None):
    """A wall block for a face between heights low..high: mossy and cobbled near the ground, cracked near the top."""
    f = (y - low) / max(1, high - low)
    n = _noise(x + z if along is None else along, y, 7) * 0.7 + _grain(x, y, z) * 0.3
    if f < 0.34:
        if n < 0.22:
            return "mossy_cobblestone"
        if n < 0.42:
            return "cobblestone"
        if n < 0.62:
            return "mossy_stone_bricks"
        if n < 0.72:
            return "andesite"
        return "stone_bricks"
    if n < 0.10 * (1.2 - f):
        return "mossy_stone_bricks"
    if n > 0.90 - 0.10 * f:
        return "cracked_stone_bricks"
    return "stone_bricks"


def deep(x, y, z):
    """Deepslate masonry with a few cracked and cobbled blocks in patches."""
    n = _noise(x + z, y, 3) * 0.7 + _grain(x, y, z) * 0.3
    return "cracked_deepslate_bricks" if n > 0.86 else "cobbled_deepslate" if n < 0.10 else "deepslate_bricks"


# ------------------------------------------------------------------ the wall
def _sides():
    hh = _hh()
    n, s = hh.N, hh.SOUTH + hh.WALL_T - 1
    return {"north": (lambda i: (i, 0), (0, 1), n), "south": (lambda i: (i, s), (0, -1), n),
            "west": (lambda i: (0, i), (1, 0), s + 1), "east": (lambda i: (n - 1, i), (-1, 0), s + 1)}


def _blocked(t, side, i):
    """True where the wall is something else: a corner tower, a gate's opening or the gatehouse."""
    hh = _hh()
    if i < hh.TOWER + 1 or i > (hh.N if side in ("north", "south") else hh.SOUTH + hh.WALL_T) - hh.TOWER - 2:
        return True
    if side == "south":
        return hh.C - 14 <= i <= hh.C + 14
    mid = hh.C if side == "north" else hh.PZ
    return abs(i - mid) <= 5


TOWER_W, TOWER_D = 7, 5    # a mural tower: along the wall, and across it (the wall's 4 and 1 into the town)
TOWER_AT = (33, 41, 25, 89, 81, 97, 49, 73, 17, 105)   # where one may stand along a side (first cell), best first


def wall(t, blds=()):
    hh = _hh()
    F, top = hh.FLOOR, hh.WALL_TOP
    inv = {(0, 1): "south", (0, -1): "north", (1, 0): "east", (-1, 0): "west"}
    for side, (at, (dx, dz), length) in _sides().items():
        inward, outward = inv[(dx, dz)], inv[(-dx, -dz)]
        for i in range(length):
            if _blocked(t, side, i):
                continue
            ox, oz = at(i)
            ph = i % BAY
            cell = lambda k, y: (ox + dx * k, y, oz + dz * k)
            # weathering in patches on both faces and on the foundation that shows where the town stands over its land
            for k in (0, hh.WALL_T - 1):
                for y in range(0, top + 1):
                    t.set(*cell(k, y), stone(*cell(k, y), F - 2 if k == 0 else F, top, along=i))
            # outside: the pilaster, the corbel course, the arrow loop, the battlements
            if ph == 0:
                for y in range(F + 1, top):
                    t.set(*cell(0, y), "stone_bricks")
                t.set(*cell(0, top), "chiseled_stone_bricks")
            else:
                t.set(*cell(0, top), hh.stairs("stone_brick_stairs", inward, "top"))
            if ph == 4:
                t.set(*cell(0, F + 3), hh.stairs("stone_brick_stairs", inward))
                t.set(*cell(0, F + 4), hh.stairs("stone_brick_stairs", inward, "top"))
            if False:
                pass
            elif ph == 0:
                t.set(*cell(0, top + 1), "stone_bricks")
                t.set(*cell(0, top + 2), "stone_bricks")
                t.set(*cell(0, top + 3), "stone_brick_slab[type=bottom]")
            elif ph in (2, 3, 5, 6):
                t.set(*cell(0, top + 1), "stone_bricks")
                t.set(*cell(0, top + 2), "stone_brick_slab[type=bottom]")
            else:
                t.set(*cell(0, top + 1), "stone_brick_wall")
                t.set(*cell(0, top + 2), "air")
            # inside: a blind arch in each bay (one block deep, the walk's floor over it), a buttress under each pilaster
            k3 = hh.WALL_T - 1
            free = all(_name(t.get(*cell(hh.WALL_T, y))) == "air" for y in range(F + 1, F + 5)) \
                and _name(t.get(*cell(hh.WALL_T, F))) == "grass_block"
            bay_free = all(_name(t.get(ox + dx * hh.WALL_T + (j - ph) * abs(dz), F, oz + dz * hh.WALL_T + (j - ph) * abs(dx)))
                           in ("grass_block", "dirt_path", "coarse_dirt", "stone_bricks") for j in range(0, BAY + 1))
            if 2 <= ph <= 6 and bay_free:
                for y in range(F + 1, F + 5):
                    t.set(*cell(k3, y), "air")
                    t.set(*cell(k3 - 1, y), stone(*cell(k3 - 1, y), F, top, along=i + 3))
                t.set(*cell(k3, F), "stone_bricks" if ph % 2 else "polished_andesite")
                if ph in (2, 6):
                    turn = {("north", 2): "west", ("north", 6): "east", ("south", 2): "west", ("south", 6): "east",
                            ("west", 2): "north", ("west", 6): "south", ("east", 2): "north", ("east", 6): "south"}[(side, ph)]
                    t.set(*cell(k3, F + 4), hh.stairs("stone_brick_stairs", turn, "top"))
                if ph == 4:
                    t.set(*cell(k3, F + 5), "chiseled_stone_bricks")
            if ph == 0 and free and bay_free:
                for y in range(F + 1, F + 3):
                    t.set(*cell(hh.WALL_T, y), stone(*cell(hh.WALL_T, y), F, top, along=i))
                t.set(*cell(hh.WALL_T, F), "stone_bricks")
                t.set(*cell(hh.WALL_T, F + 3), hh.stairs("stone_brick_stairs", outward))


def mural_towers(t, blds):
    """Two towers on each side of the wall, between a corner and a gate: the wall's own thickness and one block into
    the town, a room the walk passes through, a tiled hip roof. Each stands only where the ground inside is free, clear
    of every building (doors.GAP) and of every door's front."""
    import build
    hh = _hh()
    F, top = hh.FLOOR, hh.WALL_TOP
    inv = {(0, 1): "south", (0, -1): "north", (1, 0): "east", (-1, 0): "west"}
    fronts = set()
    for b in blds:
        for side, x, y, z in b.doors():
            ddx, ddz = hh.OPEN_DIR[side]
            for k in range(1, hh.FACE_CLEAR + 1):
                for w in (-1, 0, 1):
                    fronts.add((x + ddx * k + w * abs(ddz), z + ddz * k + w * abs(ddx)))
    placed = []
    for side, (at, (dx, dz), length) in _sides().items():
        inward, outward = inv[(dx, dz)], inv[(-dx, -dz)]
        done = []
        for i0 in TOWER_AT:
            if len(done) == 2 or any(abs(i0 - d) < 40 for d in done):
                continue
            if any(_blocked(t, side, i) for i in (i0 - 2, i0 + TOWER_W + 1)):
                continue

            def cell(j, k, y):
                ox, oz = at(i0 + j)
                return ox + dx * k, y, oz + dz * k
            ground = [cell(j, k, F) for j in range(-1, TOWER_W + 1) for k in range(hh.WALL_T, TOWER_D + 1)]
            if any(_name(t.get(*c)) not in ("grass_block", "stone_bricks") for c in ground):
                continue
            if any(_name(t.get(x, y, z)) != "air" and (x, F, z) in [cell(j, k, F) for j in range(TOWER_W) for k in (4,)]
                   for (x, _, z) in ground for y in range(F + 4, F + 6)):
                continue
            foot = [(cell(j, k, F)[0], cell(j, k, F)[2]) for j in range(TOWER_W) for k in range(hh.WALL_T, TOWER_D)]
            if any((x, z) in fronts for x, z in foot):
                continue
            if any(b.x0 - hh.GAP <= x <= b.x1 + hh.GAP and b.z0 - hh.GAP <= z <= b.z1 + hh.GAP
                   for b in blds if not b.name.startswith("torre_") or b.name == "torre_reloj" for x, z in foot):
                continue
            done.append(i0)
            placed.append((side, i0))
            for j in range(TOWER_W):
                end = j in (0, TOWER_W - 1)
                for k in range(TOWER_D):
                    rim = end or k in (0, TOWER_D - 1)
                    corner = end and k in (0, TOWER_D - 1)
                    if k >= hh.WALL_T:                         # the part that stands in the town: solid to the walk
                        for y in range(F, top):
                            x, _, z = cell(j, k, y)
                            t.set(x, y, z, stone(x, y, z, F, top + 6, along=i0 + j))
                    for y in range(top + 1, top + 4):
                        x, _, z = cell(j, k, y)
                        t.set(x, y, z, ("polished_andesite" if corner else stone(x, y, z, F, top + 6, along=i0 + j)) if rim else "air")
                    x, _, z = cell(j, k, top)
                    if k:
                        t.set(x, top, z, "polished_andesite" if 0 < k < TOWER_D - 1 else "stone_bricks")
                    t.set(*cell(j, k, top + 4), "polished_andesite" if rim else "stone_bricks")
                for k in (1, 2):                               # the walk goes through
                    if end:
                        for y in range(top + 1, top + 4):
                            t.set(*cell(j, k, y), "air")
            mid = TOWER_W // 2
            # an arrow loop outwards, a window towards the town, a niche under it at ground level, the walk's lantern
            t.set(*cell(mid, 0, top + 2), hh.stairs("stone_brick_stairs", inward))
            t.set(*cell(mid, 0, top + 3), hh.stairs("stone_brick_stairs", inward, "top"))
            axis = "east=true,west=true" if side in ("north", "south") else "north=true,south=true"
            t.set(*cell(mid, TOWER_D - 1, top + 2), f"glass_pane[{axis}]")
            for j in (mid - 1, mid, mid + 1):
                for y in range(F + 1, F + 4):
                    t.set(*cell(j, TOWER_D - 1, y), "air")
                t.set(*cell(j, TOWER_D - 1, F), "polished_andesite")
            left, right = ("west", "east") if side in ("north", "south") else ("north", "south")
            t.set(*cell(mid - 1, TOWER_D - 1, F + 3), hh.stairs("stone_brick_stairs", left, "top"))
            t.set(*cell(mid + 1, TOWER_D - 1, F + 3), hh.stairs("stone_brick_stairs", right, "top"))
            t.set(*cell(mid, 3, top + 3), hh.LANTERN)          # beside the walk's two lanes, not over them
            (xa, _, za), (xb, _, zb) = cell(0, 0, 0), cell(TOWER_W - 1, TOWER_D - 1, 0)
            build.hip_roof(t, hh._theme("brick_stairs", "brick_slab", "bricks"), min(xa, xb), min(za, zb), max(xa, xb),
                           max(za, zb), top + 5, overhang=0)
    return placed


# ------------------------------------------------------------------ the gatehouse
def gatehouse(t, blds):
    hh = _hh()
    F = hh.FLOOR
    towers = [b for b in blds if b.name in ("guardia", "almacen")]
    for b in towers:
        x0, z0, x1, z1 = b.rect()
        top = F + 12
        # masonry in patches, a string course at the wall walk's height and another under the machicolations
        for (x, y, z), (st, nbt) in list(t.blocks.items()):
            if x0 <= x <= x1 and z0 <= z <= z1 and F < y <= top and (x in (x0, x1) or z in (z0, z1)):
                if _name(st) == "deepslate_bricks":
                    band = y in (F + 6, top - 1)
                    t.set(x, y, z, "polished_deepslate" if band else deep(x, y, z))
        # machicolations: the parapet carried out one block on corbels (not over the wall that joins the tower)
        ring = [(x, z) for x in range(x0 - 1, x1 + 2) for z in range(z0 - 1, z1 + 2)
                if x in (x0 - 1, x1 + 1) or z in (z0 - 1, z1 + 1)]
        for x, z in ring:
            if not (0 <= x < hh.N and 0 <= z < hh.N):
                continue
            corner = x in (x0 - 1, x1 + 1) and z in (z0 - 1, z1 + 1)
            if _name(t.get(x, top, z)) != "air" or _name(t.get(x, top - 1, z)) != "air":
                continue
            fac = "east" if x == x0 - 1 else "west" if x == x1 + 1 else "south" if z == z0 - 1 else "north"
            t.set(x, top, z, "polished_deepslate" if corner else hh.stairs("deepslate_brick_stairs", fac, "top"))
            t.set(x, top + 1, z, "deepslate_bricks" if corner or (x + z) % 2 == 0 else "deepslate_brick_wall")
            if corner:
                t.set(x, top + 2, z, "deepslate_brick_slab[type=bottom]")
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                if x in (x0, x1) or z in (z0, z1):
                    t.set(x, top + 1, z, "air")
        # a tiled roof inside the parapet, the lightning rod on its ridge
        cx = (x0 + x1) // 2
        for k, x in enumerate(range(x0, cx + 1)):
            for z in range(z0, z1 + 1):
                e = min(z - z0, z1 - z)
                y = top + 1 + min(k, e)
                for xx in {x, x1 - (x - x0)}:
                    if min(xx - x0, x1 - xx) <= e:
                        fac = "east" if xx < cx else "west"
                        st = hh.stairs("deepslate_tile_stairs", fac) if xx != cx else "deepslate_tile_slab[type=bottom]"
                    else:
                        st = hh.stairs("deepslate_tile_stairs", "south" if z - z0 < z1 - z else "north")
                    t.set(xx, y, z, st)
        t.set(cx, top + 2 + (cx - x0), (z0 + z1) // 2, "lightning_rod[facing=up]")
        # arrow loops on the outer faces of the upper storey
        for z in (z0 + 3, z1 - 3):
            for x, fac in ((x0, "east"), (x1, "west")):
                if _name(t.get(x + (-1 if x == x0 else 1), F + 9, z)) == "air":
                    t.set(x, F + 8, z, hh.stairs("deepslate_brick_stairs", fac))
                    t.set(x, F + 9, z, hh.stairs("deepslate_brick_stairs", fac, "top"))
    # the gate itself: masonry in patches, a keystone and voussoirs over the arch, machicolations over the outer mouth
    x0, x1 = hh.AVENUE[0] - 2, hh.AVENUE[1] + 2
    z0, z1 = hh.SOUTH - 2, hh.SOUTH + hh.WALL_T + 2
    top = F + 10
    for (x, y, z), (st, nbt) in list(t.blocks.items()):
        if x0 <= x <= x1 and z0 <= z <= z1 and F < y <= top and _name(st) in ("stone_bricks", "deepslate_bricks"):
            if z in (z0, z1) or x in (hh.AVENUE[0] - 1, hh.AVENUE[1] + 1):
                t.set(x, y, z, deep(x, y, z) if y <= F + 2 else stone(x, y, z, F, top + 6))
    for z, out in ((z0, -1), (z1, 1)):
        t.set(hh.C, F + 7, z, "chiseled_stone_bricks")
        for x in (hh.C - 3, hh.C + 3):
            t.set(x, F + 6, z, "polished_andesite")
        for x in range(x0, x1 + 1):
            t.set(x, top - 1, z, "polished_andesite")
            if _name(t.get(x, top, z + out)) == "air" and _name(t.get(x, top - 1, z + out)) == "air":
                fac = "south" if out < 0 else "north"
                t.set(x, top, z + out, hh.stairs("stone_brick_stairs", fac, "top"))
                t.set(x, top + 1, z + out, "stone_bricks" if x % 2 else "stone_brick_wall")
                t.set(x, top + 1, z, "air")


def towers(t, blds):
    """The corner towers: masonry in patches and a string course under the roof."""
    hh = _hh()
    F = hh.FLOOR
    for b in blds:
        if not b.name.startswith("torre_") or b.name == "torre_reloj":
            continue
        x0, z0, x1, z1 = b.rect()
        for (x, y, z), (st, nbt) in list(t.blocks.items()):
            if not (x0 <= x <= x1 and z0 <= z <= z1 and (x in (x0, x1) or z in (z0, z1))) or y > hh.TOWER_TOP:
                continue
            n = _name(st)
            if n == "stone_bricks":
                t.set(x, y, z, "polished_andesite" if y == hh.TOWER_TOP - 1 else stone(x, y, z, F + 2, hh.TOWER_TOP + 8))
            elif n == "deepslate_bricks":
                t.set(x, y, z, deep(x, y, z))


# ------------------------------------------------------------------ the roofs
# a roof's block family -> (kin stairs for the patches, eaves stairs, ridge slab, ridge block)
KIN = {
    "brick": ("granite_stairs", "granite_stairs", "mud_brick_slab", "mud_bricks"),
    "mud_brick": ("brick_stairs", "granite_stairs", "brick_slab", "bricks"),
    "deepslate_tile": ("deepslate_brick_stairs", "polished_deepslate_stairs", "polished_deepslate_slab", "polished_deepslate"),
    "waxed_weathered_cut_copper": ("waxed_oxidized_cut_copper_stairs", "waxed_exposed_cut_copper_stairs",
                                   "waxed_exposed_cut_copper_slab", "waxed_exposed_cut_copper"),
    "waxed_exposed_cut_copper": ("waxed_weathered_cut_copper_stairs", "waxed_cut_copper_stairs",
                                 "waxed_weathered_cut_copper_slab", "waxed_weathered_cut_copper"),
}
SKIP_ROOFS = ("torre_", "guardia", "almacen")


def _family(n):
    for f in KIN:
        if n in (f + "_stairs", f + "_slab", f, f + "s"):
            return f
    return None


def _swap(st, new):
    """`new` with the properties of `st` (a stair keeps its facing, half and shape)."""
    bid, props = parse_state(st)
    return new + ("[" + ",".join(f"{k}={v}" for k, v in sorted(props.items())) + "]" if props else "")


def roofs(t, blds):
    hh = _hh()
    for b in blds:
        if b.name.startswith(SKIP_ROOFS):
            continue
        a, bz0, c, d = b.rect()
        cells = {}
        for (x, y, z), (st, nbt) in t.blocks.items():
            if a - 2 <= x <= c + 2 and bz0 - 2 <= z <= d + 2 and y > hh.FLOOR + 3:
                f = _family(_name(st))
                if f and _name(t.get(x, y + 1, z)) == "air":
                    if (x, z) not in cells or y > cells[(x, z)][0]:
                        cells[(x, z)] = (y, st, f)
        if not cells:
            continue
        fams = {}
        for y, st, f in cells.values():
            fams[f] = fams.get(f, 0) + 1
        fam = max(fams, key=fams.get)
        kin, eave, ridge_slab, ridge_full = KIN[fam]
        ylo = min(y for y, st, f in cells.values() if f == fam and "stairs" in st)
        yhi = max(y for y, st, f in cells.values() if f == fam)
        ridge = sorted(p for p, (y, st, f) in cells.items() if y == yhi and f == fam)
        for (x, z), (y, st, f) in cells.items():
            if f != fam or "stairs" not in st:
                continue
            if y == ylo:
                t.set(x, y, z, _swap(st, eave))
            elif y < yhi and _noise(x + 1, z + y, b.x0) * 0.8 + _grain(x, y, z) * 0.2 > 0.83:
                t.set(x, y, z, _swap(st, kin))
        for x, z in ridge:
            y, st, f = cells[(x, z)]
            if "slab" in st:
                t.set(x, y, z, _swap(st, ridge_slab))
            elif "stairs" not in st:
                t.set(x, y, z, ridge_full)
        xs, zs = [p[0] for p in ridge], [p[1] for p in ridge]
        long_x, long_z = max(xs) - min(xs), max(zs) - min(zs)
        if max(long_x, long_z) >= 8 and min(long_x, long_z) <= 1 and "slab" in cells[ridge[0]][1]:
            _dormers(t, b, cells, fam, ylo, yhi, "x" if long_x > long_z else "z", ridge)
            for x, z in (ridge[0], ridge[-1]):                 # a finial at each end of the ridge
                t.set(x, yhi, z, ridge_full)
        elif len(ridge) <= 6 and c - a >= 10 and d - bz0 >= 9:
            _lantern(t, ridge, yhi, fam)


def _dormers(t, b, cells, fam, ylo, yhi, along, ridge):
    """Small gabled dormers standing on both slopes of a long gable roof, a pane in each front."""
    hh = _hh()
    if yhi - ylo < 4:
        return
    r0 = ridge[0][0] if along == "x" else ridge[0][1]
    r1 = ridge[-1][0] if along == "x" else ridge[-1][1]
    n = 2 if r1 - r0 >= 14 else 1
    spots = [r0 + (r1 - r0) * (2 * k + 1) // (2 * n) for k in range(n)]
    mid = ridge[0][1] if along == "x" else ridge[0][0]
    stairs_, slab_ = fam + "_stairs", fam + "_slab"
    for sgn in (-1, 1):
        # the slope's cells on this side, at one and two rows over the eaves
        for cpos in spots:
            def at(u, v):                                   # u along the ridge, v out from it
                return (u, mid + sgn * v) if along == "x" else (mid + sgn * v, u)
            vs = [v for v in range(1, 12) if at(cpos, v) in cells and cells[at(cpos, v)][0] == ylo + 1]
            if not vs:
                continue
            v = vs[0]
            if any(at(cpos + du, v) not in cells or cells[at(cpos + du, v)][0] != ylo + 1 for du in (-1, 0, 1)):
                continue
            if any(_name(t.get(*_p(at(cpos + du, v + dv), ylo + 2 + dy))) not in ("air",)
                   for du in (-1, 0, 1) for dv in (0, 1) for dy in (0, 1, 2)):
                continue
            left, right = ("west", "east") if along == "x" else ("north", "south")
            # the front: two posts and a pane, a little gable over them, carried back to the slope
            for du, st in ((-1, hh.BEAM), (1, hh.BEAM)):
                t.set(*_p(at(cpos + du, v), ylo + 2), st)
            axis = "east=true,west=true" if along == "x" else "north=true,south=true"
            t.set(*_p(at(cpos, v), ylo + 2), f"glass_pane[{axis}]")
            for dv in (0, -1):
                if dv and cells.get(at(cpos, v + dv), (0,))[0] > ylo + 2:
                    continue
                t.set(*_p(at(cpos - 1, v + dv), ylo + 3), hh.stairs(stairs_, right))
                t.set(*_p(at(cpos + 1, v + dv), ylo + 3), hh.stairs(stairs_, left))
                t.set(*_p(at(cpos, v + dv), ylo + 3), hh.BEAM if dv == 0 else "air")
                t.set(*_p(at(cpos, v + dv), ylo + 4), f"{slab_}[type=bottom]")
            for dv in (-2, -3):
                if at(cpos, v + dv) in cells and cells[at(cpos, v + dv)][0] < ylo + 4:
                    t.set(*_p(at(cpos, v + dv), ylo + 4), f"{slab_}[type=bottom]")


def _p(xz, y):
    return xz[0], y, xz[1]


def _lantern(t, ridge, yhi, fam):
    """A small raised roof on a wide hip's top: a ring of posts and a cap, where the plane ends in a point."""
    xs, zs = [p[0] for p in ridge], [p[1] for p in ridge]
    cx, cz = (min(xs) + max(xs)) // 2, (min(zs) + max(zs)) // 2
    slab_ = fam + "_slab"
    if any(_name(t.get(cx + dx, yhi + dy, cz + dz)) != "air" for dx in (-1, 0, 1) for dz in (-1, 0, 1) for dy in (1, 2, 3)):
        return
    full = KIN[fam][3]
    t.set(cx, yhi, cz, full)
    t.set(cx, yhi + 1, cz, "polished_deepslate_wall")
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            t.set(cx + dx, yhi + 2, cz + dz, f"{slab_}[type=bottom]" if dx or dz else full)
    t.set(cx, yhi + 3, cz, f"{KIN[fam][2]}[type=bottom]")


def forecourt(t):
    """The forecourt's edge (outside the wall, where the template ends): masonry under the ground, not bare stone, for
    where the town stands over lower land."""
    hh = _hh()
    z0 = hh.SOUTH + hh.WALL_T
    for x in range(hh.N):
        for z in range(z0, hh.N):
            if min(x, hh.N - 1 - x, hh.N - 1 - z) < hh.WALL_T:
                for y in range(0, hh.FLOOR):
                    t.set(x, y, z, stone(x, y, z, 0, hh.FLOOR * 3, along=x + z))


LANE = ("cobblestone", "cobblestone", "cobblestone", "mossy_cobblestone", "andesite", "stone", "gravel", "dirt_path")
VERGE = ("coarse_dirt", "rooted_dirt", "gravel")


def lanes(t):
    """The paths from each door to its street, cobbled: a worn mix instead of one thread of dirt path, and a verge that
    fades into the grass in patches. Full blocks or a path under every step: a villager walks it as before."""
    hh = _hh()
    F = hh.FLOOR
    done = set()
    for _, _, cells in t.paths:
        for x, z in cells or ():
            if (x, z) in done or t.street.get((x, z)) or _name(t.get(x, F, z)) != "dirt_path":
                continue
            done.add((x, z))
            t.set(x, F, z, LANE[hh._h(x, 3, z) % len(LANE)])
    for x, z in done:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if n in done or _name(t.get(n[0], F, n[1])) != "grass_block" or not t.is_free(n[0], F + 1, n[1]):
                continue
            if _noise(n[0] * 2, n[1] * 2, 11) > 0.55:
                t.set(n[0], F, n[1], VERGE[hh._h(n[0], 5, n[1]) % len(VERGE)])
    return len(done)


TREE_ROOM = 3        # a tree stands where the lawn is bare this far round its trunk (its crown is 5 x 5)
TREE_APART = 8       # and no closer than this to another
TREES = (("oak_log[axis=y]", "oak_leaves[persistent=true,distance=1,waterlogged=false]"),
         ("birch_log[axis=y]", "birch_leaves[persistent=true,distance=1,waterlogged=false]"))


def _lawn(t):
    """The bare lawn inside the wall: grass at ground level with nothing over it up to the sky."""
    hh = _hh()
    F = hh.FLOOR
    return {(x, z) for x in range(hh.WALL_T, hh.N - hh.WALL_T) for z in range(hh.WALL_T, hh.SOUTH)
            if _name(t.get(x, F, z)) == "grass_block"
            and all(_name(t.get(x, y, z)) == "air" for y in range(F + 1, hh.HEIGHT))}


def trees(t):
    """Real trees on the town's widest lawns: each where the grass is bare TREE_ROOM blocks round the trunk, the ones
    with most room first, none within TREE_APART of another. They burn, as trees do: herald_house.fire_errors proves
    that a fire in one reaches nothing of the town that burns, and its errors() only lets wood and leaves stand where
    this function put them (t.trees). The trunk stands in a pit of rooted dirt and coarse dirt, so that the tree has
    soil when the land's own ground (sand, gravel) takes the lawn's place. Returns the trunks' (x, z)."""
    hh = _hh()
    F = hh.FLOOR
    lawn = _lawn(t)
    room = {}
    for (x, z) in lawn:
        r = 0
        while r < 9 and all((x + a, z + b) in lawn for a in range(-r - 1, r + 2) for b in range(-r - 1, r + 2)):
            r += 1
        room[(x, z)] = r
    picked = []
    for (x, z) in sorted((c for c in lawn if room[c] >= TREE_ROOM), key=lambda c: (-room[c], hh._h(c[0], 11, c[1]))):
        if all(max(abs(x - px), abs(z - pz)) >= TREE_APART for px, pz in picked):
            picked.append((x, z))
    t.trees = set()
    for i, (x, z) in enumerate(picked):
        log, leaves = TREES[hh._h(x, 13, z) % len(TREES)]
        tall = 5 + hh._h(x, 17, z) % 3
        t.set(x, F, z, "rooted_dirt")
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            t.set(x + dx, F, z + dz, "coarse_dirt")
        for y in range(F + 1, F + 1 + tall):
            t.set(x, y, z, log)
            t.trees.add((x, y, z))
        top = F + tall
        for dy, r in ((-1, 2), (0, 2), (1, 1), (2, 1)):
            for dx in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    if r == 2 and abs(dx) == 2 and abs(dz) == 2 and (dy == 0 or hh._h(x + dx, top + dy, z + dz) % 2):
                        continue            # the crown's corners, cut unevenly
                    if dy == 2 and dx and dz:
                        continue
                    q = (x + dx, top + dy, z + dz)
                    if _name(t.get(*q)) == "air":
                        t.set(*q, leaves)
                        t.trees.add(q)
    return picked


HEDGE = ("azalea_leaves[persistent=true,distance=1,waterlogged=false]",
         "flowering_azalea_leaves[persistent=true,distance=1,waterlogged=false]",
         "oak_leaves[persistent=true,distance=1,waterlogged=false]")
POTS = ("potted_fern", "potted_azalea_bush", "potted_flowering_azalea_bush", "potted_red_tulip", "potted_oxeye_daisy",
        "potted_cornflower", "potted_dead_bush", "potted_cactus")
HEDGE_CLEAR = 6      # a hedge found to carry fire to something that burns is cleared this far round that block


def hedges(t, blds):
    """Planting at the foot of the houses: low hedges (one block of leaves) against a wall, in runs with gaps, and a
    potted plant here and there in a run. Only on bare lawn beside a building's wall, never beside a path, a lane or a
    door's way out, so nobody's walk changes. Leaves burn: a run that would carry a fire started by lightning to
    anything that burns indoors is taken out again (herald_house.fire_errors, until it reports nothing). Returns
    (hedge cells, pots)."""
    hh = _hh()
    F = hh.FLOOR
    lawn = {(x, z) for x in range(hh.WALL_T, hh.N - hh.WALL_T) for z in range(hh.WALL_T, hh.SOUTH)
            if _name(t.get(x, F, z)) == "grass_block" and _name(t.get(x, F + 1, z)) == "air"
            and _name(t.get(x, F + 2, z)) == "air"}          # under an eave too: that is where a house is planted
    plots = {(x, z) for b in blds for x in range(b.x0, b.x1 + 1) for z in range(b.z0, b.z1 + 1)}
    ways = {c for _, start, cells in t.paths for c in [start] + list(cells or ())}
    side = ((1, 0), (-1, 0), (0, 1), (0, -1))
    spots = []
    for (x, z) in sorted(lawn):
        if any(max(abs(x - wx), abs(z - wz)) <= 2 for wx, wz in ways):
            continue
        walls = [(x + dx, z + dz) for dx, dz in side if (x + dx, z + dz) in plots
                 and not t.is_free(x + dx, F + 1, z + dz) and not t.is_free(x + dx, F + 2, z + dz)]
        if not walls or any((x + dx, z + dz) not in lawn and (x + dx, z + dz) not in walls for dx, dz in side):
            continue
        if _noise(x * 3, z * 3, 23) > 0.42:
            spots.append((x, z))
    pots = [c for c in spots if hh._h(c[0], 29, c[1]) % 6 == 0]
    green = [c for c in spots if c not in pots]
    for x, z in green:
        t.set(x, F + 1, z, HEDGE[int(_noise(x, z, 31) * 2.99)])
        t.trees.add((x, F + 1, z))
    for x, z in pots:
        t.set(x, F + 1, z, POTS[hh._h(x, 37, z) % len(POTS)])
    for _ in range(8):
        bad = hh.fire_errors(t)
        if not bad:
            break
        import re
        for line in bad:
            bx, by, bz = (int(v) for v in re.search(r"at \((-?\d+), (-?\d+), (-?\d+)\)", line).groups())
            for x, z in list(green):
                if max(abs(x - bx), abs(z - bz)) <= HEDGE_CLEAR:
                    green.remove((x, z))
                    t.set(x, F + 1, z, "air")
                    t.trees.discard((x, F + 1, z))
    return green, pots


def dress(t, blds):
    forecourt(t)
    wall(t, blds)
    placed = mural_towers(t, blds)
    towers(t, blds)
    gatehouse(t, blds)
    roofs(t, blds)
    return placed
