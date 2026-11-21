"""Roads out of the Herald's House (casa_heraldo.caminos.*): the reference layout, the roadside huts, the blueprint for
the Java side (heraldia/caminos_casa.json) and the texts (the guide's lore among them).

What the owner asked for: from each gate of the walled town a well built road goes out past the wall (at least
MIN_LENGTH blocks beyond the gate), lit with lanterns so no monster spawns on it, mostly moving away from spawn; small
low-means huts by the roads near the town, each with a villager who trades (vanilla trades: a profession and its vanilla
workstation inside); and the most direct road from the town to the wave arena built all the way, with a guide's hut right
at the town's exit whose villager tells, through the choice window (choice/, never the chat), that the road leads to the
arena where the best warriors fight.

They are not world generation: the Java side (herald/SpawnRoads) BUILDS them in chunks that already exist, spread over
ticks like the town itself, once the town is placed (or on /heraldia herald roads in a world whose town came before this
feature); the arena road is completed when the arena is placed, whichever comes first. The layout is pure arithmetic
on the seed and the gate positions, the same in Java (roads/SpawnRoadLayout, which reuses roads/RoadLayout's routes,
painting, water handling and paving) and here, where the invariants are checked as properties (tests/test_spawn_roads.py):
  - a road: from the gate cell, straight for STRAIGHT blocks (the huts stand along this stretch, so their places are
    exact and the door rule can be checked here), then a gentle bend to its end, LENGTH blocks out and up to END_LATERAL
    to one side (from the seed); the distance to the town's centre grows along most of its segments;
  - the arena road: that same road, continued from its end to the arena's entrance (the arena's gate is always on the
    south side of its template): through a waypoint chosen among a few detours so it does not cross the arena's box, the
    town or a chunk with a surface structure (villages, mines, medium and unique structures), the shortest that is clear;
  - lamp posts every LAMP_SPACING blocks of road, alternating sides: every road column stays within LIGHT_REACH blocks
    (horizontal, Manhattan) of a lantern, so its block light is at least 1 (monsters need 0 to spawn in 26.3) even with a
    few blocks of height between them.
The huts (one template per profession, HUT_SIZE): walls of cobblestone, planks and log posts, a wool awning over the
porch, the bed, the workstation and a lantern inside, and the bell on the porch floor next to the door (a resident with
no reachable meeting point leaves and drops its bed and workstation). errors() checks each template's door with the
door rule (doors.template_report) and the huts' places beside the four roads with the whole rule (doors.footprint_errors,
the town included); generation fails on any error.
"""
import math

from core import Template, NS, F, B
import filler_loot
import doors
import lint

TEMPLATE_PREFIX = "casa_heraldo/choza_"
VERSION = 1
# --- the layout (the Java reads these from caminos_casa.json) ---
STEP = 16                  # roads/RoadLayout.STEP: vertices every 16 blocks
STRAIGHT = 44              # blocks of straight road from the gate (the huts stand along it)
LENGTH = 72                # how far out (along) a road ends
END_LATERAL = 10           # up to this many blocks to one side at its end (from the seed)
MIN_LENGTH = 45            # the owner: at least 45 blocks beyond the gate
WIDTH = 5                  # the gates' road (herald_house.ROAD, 5 wide)
MEANDER = 0.06             # meander amplitude per block of segment length...
MAX_MEANDER = 12           # ...and its cap
LAMP_SPACING, LAMP_FIRST = 7, 4
LAMP_OFFSET = WIDTH / 2 + 1   # the post stands one block beyond the road's edge
SHARP = math.cos(math.radians(45))   # a bend sharper than this gets a lamp outside it
LIGHT_REACH = 10           # 15 - 1 - 2 (the lantern is 2 above the post's foot) - 2 of terrain allowance
ARENA_APPROACH = 10        # the last stretch to the arena's entrance comes straight out of it
ARENA_MARGIN = 3           # the road keeps this far from the arena's box (but for that last stretch)
TOWN_MARGIN = 8            # and this far from the town's footprint (but for its own gate's road)
MAX_ARENA_ROAD = 420       # an arena farther than this from the road's end is not joined (it is not "near spawn")
STRUCTURE_REACH = 4        # the road's sides checked for structures
DETOURS = (24, -24, 48, -48, 72, -72, 96, -96, 128, -128)
CORNER = 20                # the corner detours round the arena's box this far out
# --- the huts ---
HUT_SIZE = (7, 9, 7)       # along the road, height, depth (porch 2 + hut 5)
PORCH = 2
EDGE = WIDTH // 2 + 1      # the hut template's first row (the porch) is this far from the road's axis
DOOR = (3, 1, 2)           # the door's lower half (local), facing the road (local north)
BED = ((1, 1, 4), (1, 1, 5))   # foot and head (local), the head towards the back wall
STATION = (5, 1, 5)
BELL = (1, 1, 1)           # on the porch floor, beside the door (not in front of it)
VILLAGER = (3, 1, 4)
LANTERN = (3, 3, 4)
# (slot, side, along): side +1 right of the outward direction; the guide's slot is the first one out of the gate
GUIDE_SLOT = ("guia", 1, 8)
SLOTS = [("a", -1, 16), ("b", 1, 26)]
MAX_VILLAGERS = 8          # the owner's cap, the guide included
DEFAULT_VILLAGERS = 5      # the guide and one per road (the measured play cost: docs/DEVELOPMENT.md)
GUIDE_PROFESSION = "weaponsmith"
# the normal huts' professions in the order the huts are filled (low-means trades: food, wool, arrows, leather, stone)
PROFESSIONS = ["farmer", "fisherman", "shepherd", "fletcher", "leatherworker", "mason", "butcher"]
STATIONS = {"farmer": "composter[level=0]", "fisherman": "barrel[facing=up,open=false]", "shepherd": "loom[facing=north]",
            "fletcher": "fletching_table", "leatherworker": "cauldron", "mason": "stonecutter[facing=north]",
            "butcher": "smoker[facing=north,lit=false]", "weaponsmith": "grindstone[face=floor,facing=north]"}
AWNING = {"farmer": ("lime_wool", "white_wool"), "fisherman": ("light_blue_wool", "white_wool"),
          "shepherd": ("white_wool", "brown_wool"), "fletcher": ("green_wool", "white_wool"),
          "leatherworker": ("brown_wool", "orange_wool"), "mason": ("gray_wool", "white_wool"),
          "butcher": ("red_wool", "white_wool"), "weaponsmith": ("red_wool", "black_wool")}
HUT_TAG, GUIDE_TAG = "heraldia_choza", "heraldia_guia"
SIDES = ("north", "east", "south", "west")    # the order the roads are built and the huts filled


# ------------------------------------------------------------------ Java's arithmetic (roads/RoadLayout)
M64 = (1 << 64) - 1


def mix(z):
    z &= M64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
    return z ^ (z >> 31)


def rng(seed, a, b):
    """RoadLayout.rng: a number in [0, 1) from the seed and two longs."""
    inner = mix(((a * 0x9E3779B97F4A7C15) & M64) ^ mix((b + 0x632BE59BD9B4E019) & M64))
    return (mix((seed & M64) ^ inner) >> 11) * 2.0 ** -53


def pack(x, z):
    return ((x & 0xFFFFFFFF) << 32) | (z & 0xFFFFFFFF)


def jround(v):
    """Java's Math.round (half up), not Python's banker's rounding."""
    return math.floor(v + 0.5)


def segment(pts, ax, az, bx, bz, h, first, amp):
    """RoadLayout.Route.segment with its amplitude given: vertices of a straight segment plus a meander (two sines of
    random phase and frequency, zero at the ends)."""
    dx, dz = bx - ax, bz - az
    ln = math.hypot(dx, dz)
    n = max(1, jround(ln / STEP))
    nx, nz = (0.0, 0.0) if ln == 0 else (-dz / ln, dx / ln)
    f1, f2 = 1 + (h >> 8 & 1), 3 + (h >> 9 & 3)
    p1 = ((h >> 16) & 0xFFFF) / 65536.0 * 2 * math.pi
    p2 = ((h >> 32) & 0xFFFF) / 65536.0 * 2 * math.pi
    for i in range(0 if first else 1, n + 1):
        t = i / n
        off = amp * math.sin(math.pi * t) * (0.7 * math.sin(2 * math.pi * f1 * t + p1) + 0.3 * math.sin(2 * math.pi * f2 * t + p2))
        pts.append((ax + dx * t + nx * off, az + dz * t + nz * off))


def amplitude(ax, az, bx, bz):
    return min(MAX_MEANDER, math.hypot(bx - ax, bz - az) * MEANDER)


def route(knots, seed, straight_first=False, straight_last=False):
    """Vertices through the knots: each knot-to-knot stretch with its own meander (none on the first one with
    `straight_first`, nor on the last with `straight_last`)."""
    pts = []
    for i in range(len(knots) - 1):
        (ax, az), (bx, bz) = knots[i], knots[i + 1]
        h = mix((seed & M64) ^ mix(pack(math.floor(ax), math.floor(az))) ^ mix((pack(math.floor(bx), math.floor(bz)) * 31) & M64))
        amp = 0.0 if (straight_first and i == 0) or (straight_last and i == len(knots) - 2) else amplitude(ax, az, bx, bz)
        segment(pts, ax, az, bx, bz, h, i == 0, amp)
    return pts


# ------------------------------------------------------------------ the roads
def outward(side):
    return {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}[side]


def right(side):
    dx, dz = outward(side)
    return -dz, dx


def axis(gate, side, u, v=0.0):
    """The point u blocks out of the gate cell along its road and v to its right (block centres at .5)."""
    (gx, gz), (dx, dz), (rx, rz) = gate, outward(side), right(side)
    return gx + 0.5 + dx * u + rx * v, gz + 0.5 + dz * u + rz * v


def lateral(seed, gate):
    """How far to the right (negative: left) a road's end lies, from the seed and its gate."""
    return jround((rng(seed, pack(*gate), 41) * 2 - 1) * END_LATERAL)


def normal_road(gate, side, seed):
    """A gate's road: straight for STRAIGHT blocks, then a bend to its end LENGTH out."""
    knots = [axis(gate, side, 1), axis(gate, side, STRAIGHT), axis(gate, side, LENGTH, lateral(seed, gate))]
    return route(knots, seed, straight_first=True)


def head(normal):
    """The vertices of a gate's road up to the end of its straight stretch."""
    n = max(1, jround((STRAIGHT - 1) / STEP))
    return normal[:n + 1]


def joined(normal, from_head):
    """The vertex before the arena road's first: on the gate's road it continues."""
    pts = head(normal) if from_head else normal
    return pts[-2]


def arena_points(arena_box):
    """The arena's entrance (just outside the south side of its box, on its centre column) and the approach point
    ARENA_APPROACH out of it: (entrance, approach)."""
    x0, z0, x1, z1 = arena_box
    cx = (x0 + x1) // 2 + 0.5
    return (cx, z1 + 1.5), (cx, z1 + 1.5 + ARENA_APPROACH)


def arena_candidates(start, arena_box):
    """The knot lists tried for the arena road, in order: straight, side detours at the middle, round the corners."""
    entrance, approach = arena_points(arena_box)
    sx, sz = start
    qx, qz = approach
    mx, mz = (sx + qx) / 2, (sz + qz) / 2
    ln = math.hypot(qx - sx, qz - sz) or 1.0
    px, pz = -(qz - sz) / ln, (qx - sx) / ln
    x0, z0, x1, z1 = arena_box
    sw, se = (x0 - CORNER + 0.5, z1 + CORNER + 0.5), (x1 + CORNER + 0.5, z1 + CORNER + 0.5)
    nw, ne = (x0 - CORNER + 0.5, z0 - CORNER + 0.5), (x1 + CORNER + 0.5, z0 - CORNER + 0.5)
    out = [[]] + [[(mx + px * k, mz + pz * k)] for k in DETOURS] + [[sw], [se], [nw, sw], [ne, se]]
    return [[start] + w + [approach, entrance] for w in out]


def polyline_length(knots):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(knots, knots[1:]))


def samples(pts, every=2.0):
    """Points every `every` blocks along the polyline, each with its unit normal and the distance left to its end."""
    out = []
    total = polyline_length(pts)
    done = 0.0
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        ln = math.hypot(bx - ax, bz - az)
        if ln == 0:
            continue
        nx, nz = -(bz - az) / ln, (bx - ax) / ln
        k = 0
        while k * every <= ln:
            t = k * every / ln
            out.append((ax + (bx - ax) * t, az + (bz - az) * t, nx, nz, total - done - k * every))
            k += 1
        done += ln
    return out


def _in(box, x, z, m=0):
    return box[0] - m <= x <= box[2] + m and box[1] - m <= z <= box[3] + m


def clear(pts, arena_box, town_box, structure):
    """(no arena or town in the way, no structure in the way) for the road through these vertices: its edges keep
    ARENA_MARGIN from the arena's box (but for the last stretch, into its entrance) and TOWN_MARGIN from the town's
    footprint; no chunk within STRUCTURE_REACH of its edges holds a surface structure."""
    free_boxes, free_structures = True, True
    edge, reach = WIDTH / 2, WIDTH / 2 + STRUCTURE_REACH
    for x, z, nx, nz, left in samples(pts):
        for w in (-edge, 0.0, edge):
            cx, cz = math.floor(x + nx * w), math.floor(z + nz * w)
            if left > ARENA_APPROACH + 1 and _in(arena_box, cx, cz, ARENA_MARGIN) or _in(town_box, cx, cz, TOWN_MARGIN):
                free_boxes = False
        if not free_boxes:
            break
        for w in (-reach, 0.0, reach):
            if free_structures and structure(math.floor(x + nx * w) >> 4, math.floor(z + nz * w) >> 4):
                free_structures = False
    return free_boxes, free_structures


def arena_road(start, arena_box, town_box, seed, structure=lambda cx, cz: False):
    """The road from `start` (the end of the most aligned gate's road) to the arena's entrance: (vertices, knots,
    clear of structures) or None if the arena is too far or no candidate keeps out of the arena's box and the town."""
    entrance, _ = arena_points(arena_box)
    if math.hypot(entrance[0] - start[0], entrance[1] - start[1]) > MAX_ARENA_ROAD:
        return None
    best, fallback = None, None
    for knots in arena_candidates(start, arena_box):
        pts = route(knots, seed, straight_last=True)
        boxes, structures = clear(pts, arena_box, town_box, structure)
        if not boxes:
            continue
        ln = polyline_length(knots)
        if structures and (best is None or ln < best[0]):
            best = (ln, pts, knots)
        if fallback is None or ln < fallback[0]:
            fallback = (ln, pts, knots)
    if best:
        return best[1], best[2], True
    if fallback:
        return fallback[1], fallback[2], False
    return None


def hits_arena(pts, arena_box):
    """Does the road through these vertices come within ARENA_MARGIN of the arena's box?"""
    r = WIDTH / 2
    return any(_in(arena_box, math.floor(x + nx * w), math.floor(z + nz * w), ARENA_MARGIN + 4)
               for x, z, nx, nz, _ in samples(pts) for w in (-r, 0.0, r))


def arena_plan(gates, town_box, arena_box, seed, structure=lambda cx, cz: False):
    """The arena road from the town: (gate side, its normal road, where the arena road starts, whether that is the end
    of the straight stretch, the arena road's result from arena_road or None). It starts where the gate's road ends or,
    if that road's bend would come too close to the arena (an arena 200 blocks from spawn and the town on its side),
    where its straight stretch ends (and the gate's road is only that stretch)."""
    x0, z0, x1, z1 = arena_box
    side = arena_gate(gates, ((town_box[0] + town_box[2]) / 2, (town_box[1] + town_box[3]) / 2), ((x0 + x1) / 2, (z0 + z1) / 2))
    nr = normal_road(gates[side], side, seed)
    from_head = hits_arena(nr, arena_box)
    start = axis(gates[side], side, STRAIGHT) if from_head else nr[-1]
    return side, nr, start, from_head, arena_road(start, arena_box, town_box, seed, structure)


def arena_gate(gates, center, arena_center):
    """The gate whose road points closest to the arena (largest cosine), ties in SIDES order."""
    def score(side):
        gx, gz = gates[side]
        dx, dz = outward(side)
        vx, vz = arena_center[0] - gx, arena_center[1] - gz
        ln = math.hypot(vx, vz) or 1.0
        return (dx * vx + dz * vz) / ln
    return max(SIDES, key=lambda s: (score(s), -SIDES.index(s)))


def lamps(pts, before=None, first=LAMP_FIRST):
    """Lamp posts along the road: one every LAMP_SPACING blocks of it, alternating sides, LAMP_OFFSET off the axis, one
    more by its end if the last one is more than half a spacing back, and one outside each sharp bend (`before`: the
    vertex before its first, when it continues another road: the arena road, whose first bend is where it joins)."""
    out = []
    arc, k = 0.0, 0
    target = first

    def put(ax, az, bx, bz, t, ln):
        nx, nz = -(bz - az) / ln, (bx - ax) / ln
        side = 1 if k % 2 == 0 else -1
        out.append((math.floor(ax + (bx - ax) * t + nx * LAMP_OFFSET * side),
                    math.floor(az + (bz - az) * t + nz * LAMP_OFFSET * side)))
    last = None
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        ln = math.hypot(bx - ax, bz - az)
        if ln == 0:
            continue
        last = (ax, az, bx, bz, ln)
        while target <= arc + ln:
            put(ax, az, bx, bz, (target - arc) / ln, ln)
            k += 1
            target += LAMP_SPACING
        arc += ln
    if last and arc - (target - LAMP_SPACING) > LAMP_SPACING / 2:
        ax, az, bx, bz, ln = last
        put(ax, az, bx, bz, max(0.0, (ln - 1) / ln), ln)
    # and one outside each sharp bend (a detour round the arena's corner): its outer edge is the farthest from the others
    full = ([before] if before else []) + list(pts)
    for (ax, az), (bx, bz), (cx, cz) in zip(full, full[1:], full[2:]):
        l1, l2 = math.hypot(bx - ax, bz - az), math.hypot(cx - bx, cz - bz)
        if l1 == 0 or l2 == 0:
            continue
        d1x, d1z, d2x, d2z = (bx - ax) / l1, (bz - az) / l1, (cx - bx) / l2, (cz - bz) / l2
        if d1x * d2x + d1z * d2z < SHARP:
            ox, oz = d1x - d2x, d1z - d2z
            lo = math.hypot(ox, oz)
            out.append((math.floor(bx + ox / lo * LAMP_OFFSET), math.floor(bz + oz / lo * LAMP_OFFSET)))
    return out


def cells(pts, width=WIDTH):
    """The road's columns (RoadLayout.paint without the jagged edge, which only takes some away)."""
    half = max(width / 2, 0.75)
    out = set()
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        dx, dz = bx - ax, bz - az
        l2 = dx * dx + dz * dz
        for x in range(math.floor(min(ax, bx) - half - 1), math.ceil(max(ax, bx) + half + 1) + 1):
            for z in range(math.floor(min(az, bz) - half - 1), math.ceil(max(az, bz) + half + 1) + 1):
                cx, cz = x + 0.5, z + 0.5
                t = 0 if l2 == 0 else min(1, max(0, ((cx - ax) * dx + (cz - az) * dz) / l2))
                if math.hypot(cx - (ax + dx * t), cz - (az + dz * t)) <= half:
                    out.add((x, z))
    return out


def away_share(pts, center):
    """The share of the road's segments along which the distance to `center` grows."""
    d = [math.hypot(x - center[0], z - center[1]) for x, z in pts]
    steps = [b > a for a, b in zip(d, d[1:])]
    return sum(steps) / len(steps) if steps else 0.0


# ------------------------------------------------------------------ the huts
def hut_frame(gate, side, slot_side, along):
    """Where a hut stands: (rotation, the world cell of its local origin) and a function local (x, z) -> world (x, z).
    The local x runs along the road (towards the outside on the right side, towards the town on the left) and the local
    z away from it; the template's first row is EDGE blocks off the axis."""
    (gx, gz), (dx, dz), (rx, rz) = gate, outward(side), right(side)

    def world(lx, lz):
        u = along + lx if slot_side > 0 else along + HUT_SIZE[0] - 1 - lx
        v = slot_side * (EDGE + lz)
        return gx + dx * u + rx * v, gz + dz * u + rz * v
    ax, az = world(1, 0)
    ox, oz = world(0, 0)
    xdir = (ax - ox, az - oz)
    rotation = {(1, 0): "none", (0, 1): "clockwise_90", (-1, 0): "clockwise_180", (0, -1): "counterclockwise_90"}[xdir]
    return rotation, (ox, oz), world


def hut_rect(gate, side, slot_side, along):
    """The hut's walls (not its porch) as a rectangle and its door: ((x0, z0, x1, z1), (facing, x, z))."""
    _, _, world = hut_frame(gate, side, slot_side, along)
    corners = [world(x, z) for x in (0, HUT_SIZE[0] - 1) for z in (PORCH, HUT_SIZE[2] - 1)]
    xs, zs = [c[0] for c in corners], [c[1] for c in corners]
    door = world(DOOR[0], DOOR[2])
    rx, rz = right(side)
    facing = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east"}[(-rx * slot_side, -rz * slot_side)]
    return (min(xs), min(zs), max(xs), max(zs)), (facing, door[0], door[1])


def slots(guide):
    """[(slot, side, along)] of one road's huts, the guide's first when `guide`."""
    return ([GUIDE_SLOT] if guide else []) + SLOTS


# Each hut is its own building (design pass, phase 2): the same plan (door, bed, workstation, bell and lanterns where the
# Java side expects them) under its own walls, roof, porch and what stands on the porch. `roof`: "x" a gable with its
# ridge along the road, "z" a gable whose end faces the road, "hip" or "lean" (a single slope rising to the back).
LOOK = {
    "farmer": dict(wall="oak_planks", base="cobblestone", post="oak_log", roof="x", tile="spruce", porch="awning",
                   prop=("hay_block", "hay_block")),
    "fisherman": dict(wall="spruce_planks", base="stone_bricks", post="spruce_log", roof="z", tile="dark_oak", porch="roof",
                      prop=("dried_kelp_block",)),
    "shepherd": dict(wall="white_terracotta", base="cobblestone", post="dark_oak_log", roof="hip", tile="spruce",
                     porch="awning", prop=("white_wool", "light_gray_wool")),
    "fletcher": dict(wall="spruce_log[axis=x]", base="mossy_cobblestone", post="spruce_log", roof="x", tile="dark_oak",
                     porch="roof", prop=("target",)),
    "leatherworker": dict(wall="mud_bricks", base="packed_mud", post="stripped_oak_log", roof="lean", tile="spruce",
                          porch="awning", prop=("brown_wool",)),
    "mason": dict(wall="stone_bricks", base="andesite", post="polished_andesite", roof="hip", tile="dark_oak",
                  porch="roof", prop=("chiseled_stone_bricks", "stone_brick_slab[type=bottom,waterlogged=false]")),
    "butcher": dict(wall="bricks", base="cobblestone", post="spruce_log", roof="z", tile="mud_brick", porch="awning",
                    prop=(), chimney=True),
    "guia": dict(wall="cobblestone", base="mossy_cobblestone", post="dark_oak_log", roof="x", tile="deepslate_tile",
                 porch="awning", prop=("anvil[facing=north]",), chimney=True),
}
WOOD_TILES = ("spruce", "dark_oak", "oak")


def _st(mat, facing, half="bottom"):
    return f"{mat}_stairs[facing={facing},half={half},shape=straight,waterlogged=false]"


def _slab(mat, kind="bottom"):
    return f"{mat}_slab[type={kind},waterlogged=false]"


def _full(mat):
    return {"brick": "bricks", "mud_brick": "mud_bricks", "stone_brick": "stone_bricks", "deepslate_tile": "deepslate_tiles"}.get(
        mat, mat + "_planks")


def _roof(t, kind, tile, wall, x0, x1, z0, z1, y):
    """The hut's roof over x0..x1, z0..z1 from the wall plate at y, inside the template's footprint (no overhang)."""
    w, d = x1 - x0 + 1, z1 - z0 + 1
    if kind == "x":                                    # ridge along x: the eaves over the front and the back walls
        for k in range(d // 2):
            for x in range(x0, x1 + 1):
                t.set(x, y + k, z0 + k, _st(tile, "south"))
                t.set(x, y + k, z1 - k, _st(tile, "north"))
            for z in range(z0 + k + 1, z1 - k):         # the gable ends
                for x in (x0, x1):
                    t.set(x, y + k, z, wall)
        for x in range(x0, x1 + 1):
            t.set(x, y + d // 2, z0 + d // 2, _slab(tile))
            t.set(x, y + d // 2 - 1, z0 + d // 2, wall if x in (x0, x1) else "air")
    elif kind == "z":                                  # ridge along z: a gable end over the door
        for k in range(w // 2):
            for z in range(z0, z1 + 1):
                t.set(x0 + k, y + k, z, _st(tile, "east"))
                t.set(x1 - k, y + k, z, _st(tile, "west"))
            for x in range(x0 + k + 1, x1 - k):
                for z in (z0, z1):
                    t.set(x, y + k, z, wall)
        for z in range(z0, z1 + 1):
            t.set(x0 + w // 2, y + w // 2, z, _slab(tile))
            t.set(x0 + w // 2, y + w // 2 - 1, z, wall if z in (z0, z1) else "air")
    elif kind == "hip":
        for k in range(min(w, d) // 2 + 1):
            a, b, c, e = x0 + k, x1 - k, z0 + k, z1 - k
            if a > b or c > e:
                break
            for x in range(a, b + 1):
                for z in range(c, e + 1):
                    if x in (a, b) or z in (c, e):
                        if c == e:
                            st = _slab(tile)
                        else:
                            st = _st(tile, "south" if z == c else "north" if z == e else "east" if x == a else "west")
                        t.set(x, y + k, z, st)
    else:                                              # a single slope, low over the door and high at the back
        for k, z in enumerate(range(z0, z1 + 1)):
            h = y + k // 2
            for x in range(x0, x1 + 1):
                t.set(x, h, z, _slab(tile) if k % 2 == 0 else _slab(tile, "top"))
                for yy in range(y, h):                 # the side walls and the back follow the slope up
                    if x in (x0, x1) or z == z1:
                        t.set(x, yy, z, wall)


def hut(profession, guide=False):
    """A roadside hut for that profession: local x along the road, z away from it (the porch rows z 0-1, the hut 2-6)."""
    name = "guia" if guide else profession
    look = LOOK[name]
    t = Template(TEMPLATE_PREFIX + name)
    sx, sy, sz = HUT_SIZE
    a, b = AWNING[profession]
    wall, base, post, tile = look["wall"], look["base"], look["post"], look["tile"]
    for x in range(sx):
        for z in range(sz):
            t.set(x, 0, z, "cobblestone" if z >= PORCH else "coarse_dirt")
            for y in range(1, sy):
                t.set(x, y, z, "air")
    axis = lambda st, ax: st.replace("[axis=y]", "").split("[")[0] + f"[axis={ax}]" if "_log" in st else st
    for x in range(sx):                                  # the hut: posts at the corners, a footing, its own walls
        for z in range(PORCH, sz):
            edge = x in (0, sx - 1) or z in (PORCH, sz - 1)
            if not edge:
                t.set(x, 0, z, "spruce_planks")
                continue
            corner = x in (0, sx - 1) and z in (PORCH, sz - 1)
            for y in (1, 2, 3):
                st = axis(post, "y") if corner else (base if y == 1 else wall)
                if not corner and y > 1 and "axis=x" in wall and x in (0, sx - 1):
                    st = wall.replace("axis=x", "axis=z")          # a log wall's logs lie along each wall
                t.set(x, y, z, st)
    _roof(t, look["roof"], tile, wall.replace("[axis=x]", "[axis=y]") if "_log" in wall else wall, 0, sx - 1, PORCH, sz - 1, 4)
    for x in (1, 5):                                     # two counter windows: 1 high, nobody walks through them
        t.set(x, 2, PORCH, "air")
    t.set(sx - 1, 2, 4, "air")
    for x, z in ((0, 1), (sx - 1, 1)):                    # the porch's two posts
        for y in (1, 2, 3):
            t.set(x, y, z, post.split("[")[0].replace("_log", "_fence").replace("stripped_", "")
                  if "_log" in post else "cobblestone_wall" if "andesite" not in post else "andesite_wall")
    dx, dy, dz = DOOR
    # over the porch: a striped awning, or a slab roof of the hut's tile. Open over the door either way: the door rule
    # only checks a door whose way out is under the sky (doors.template_report skips one under a cover)
    for x in range(sx):
        if look["porch"] == "awning":
            if x != dx:                                  # open over the door: the way in stays under the sky
                t.set(x, 4, 1, a if x % 2 == 0 else b)
        elif x != dx:
            t.set(x, 4, 1, _slab(tile))
            t.set(x, 4, 0, _slab(tile)) if x not in (0, sx - 1) else None
    door = "spruce_door" if tile in WOOD_TILES or "planks" in wall or "_log" in wall else "dark_oak_door"
    t.set(dx, dy, dz, f"{door}[facing=north,half=lower,hinge=left,open=false,powered=false]")
    t.set(dx, dy + 1, dz, f"{door}[facing=north,half=upper,hinge=left,open=false,powered=false]")
    (fx, fy, fz), (hx, hy, hz) = BED
    color = "brown" if not guide else "red"
    t.set(fx, fy, fz, f"{color}_bed[facing=south,part=foot,occupied=false]")
    t.set(hx, hy, hz, f"{color}_bed[facing=south,part=head,occupied=false]")
    st = STATIONS[profession]
    # the fisherman's workstation barrel holds what a fisherman keeps (filler_loot: no container is left empty)
    t.set(*STATION, st, {"id": "minecraft:barrel", "LootTable": filler_loot.table_id("pesca")} if st.startswith("barrel") else None)
    t.set(*BELL, "bell[attachment=floor,facing=east,powered=false]")
    t.set(*LANTERN, "lantern[hanging=true,waterlogged=false]")
    t.set(5, 3, 1, "lantern[hanging=true,waterlogged=false]")       # under the porch's cover
    t.set(4, 1, 5, "spruce_trapdoor[facing=north,half=bottom,open=false,powered=false,waterlogged=false]")   # a stool
    t.set(2, 1, 5, "flower_pot")
    for k, prop in enumerate(look["prop"]):              # what the trade leaves on the porch, beside the door's way
        t.set(5, 1 + k, 1, prop)
    if look.get("chimney"):                              # a stack up the back corner, through the roof (no fire in it)
        top = max(y for (x, y, z) in t.blocks if t.blocks[(x, y, z)][0] != "minecraft:air")
        for y in range(1, min(sy - 1, top + 1) + 1):
            t.set(sx - 2, y, sz - 1, "bricks" if y < sy - 1 else "brick_wall")
    n = {"id": "minecraft:villager", "PersistenceRequired": B(1), "Tags": [HUT_TAG] + ([GUIDE_TAG] if guide else ["heraldia"]),
         "VillagerData": {"profession": "minecraft:" + profession, "level": 1, "type": "minecraft:plains"}, "Xp": 1,
         "Rotation": [F(0.0), F(0.0)]}
    t.entity(*VILLAGER, n)
    return t


def templates():
    """{profession or "guia": template} of every hut."""
    out = {p: hut(p) for p in PROFESSIONS}
    out["guia"] = hut(GUIDE_PROFESSION, guide=True)
    return out


# ------------------------------------------------------------------ what the Java side reads
def dataset():
    return {
        "version": VERSION,
        "recto": STRAIGHT, "largo": LENGTH, "lateral": END_LATERAL, "minimo": MIN_LENGTH, "ancho": WIDTH,
        "meandro": MEANDER, "meandro_max": MAX_MEANDER,
        "farolas": {"cada": LAMP_SPACING, "primera": LAMP_FIRST, "separacion": LAMP_OFFSET, "curva": SHARP},
        "arena": {"acercamiento": ARENA_APPROACH, "margen": ARENA_MARGIN, "pueblo": TOWN_MARGIN, "maximo": MAX_ARENA_ROAD,
                  "lados": STRUCTURE_REACH, "desvios": list(DETOURS), "esquina": CORNER},
        "chozas": {
            "tamano": list(HUT_SIZE), "borde": EDGE, "puerta": list(DOOR), "cama": [list(p) for p in BED],
            "puesto": list(STATION), "campana": list(BELL),
            "guia": {"hueco": GUIDE_SLOT[0], "lado": GUIDE_SLOT[1], "desde": GUIDE_SLOT[2],
                     "plantilla": f"{NS}:{TEMPLATE_PREFIX}guia", "oficio": GUIDE_PROFESSION},
            "huecos": [{"hueco": s, "lado": sd, "desde": al} for s, sd, al in SLOTS],
            "oficios": [{"oficio": p, "plantilla": f"{NS}:{TEMPLATE_PREFIX}{p}"} for p in PROFESSIONS],
            "maximo": MAX_VILLAGERS,
        },
        "lados": list(SIDES),
    }


# ------------------------------------------------------------------ checks
def _town():
    import herald_house as h
    return h


def layout_errors():
    """The door rule over the huts beside the four roads and the town (all the slots filled, the guide's included)."""
    h = _town()
    blds = [("casa_heraldo", (0, 0, h.N - 1, h.N - 1), [])]
    for side in SIDES:
        gate = h.GATES[side]
        for name, sd, along in slots(True):
            rect, door = hut_rect(gate, side, sd, along)
            blds.append((f"choza_{side}_{name}", rect, [door]))
    return doors.footprint_errors(blds)


def template_errors(ts=None):
    e = []
    for name, t in (ts or templates()).items():
        for msg in doors.template_report(t):
            e.append(f"spawn_roads: hut {name}: {msg}")
        if not any("_door" in st and "half=lower" in st for st, _ in t.blocks.values()):
            e.append(f"spawn_roads: hut {name}: no door")
        if t.size() != HUT_SIZE:
            e.append(f"spawn_roads: hut {name}: size {t.size()} instead of {HUT_SIZE}")
        for what, p in (("bell", BELL), ("bed", BED[0]), ("bed", BED[1])):
            if what not in (t.get(*p) or ""):
                e.append(f"spawn_roads: hut {name}: no {what} at {p}")
        if t.get(*STATION) is None or t.get(*STATION) == "minecraft:air":
            e.append(f"spawn_roads: hut {name}: no workstation")
        if len(t.entities) != 1:
            e.append(f"spawn_roads: hut {name}: {len(t.entities)} villagers")
        if any("torch" in st for st, _ in t.blocks.values()):
            e.append(f"spawn_roads: hut {name}: a torch (lanterns only: nothing burns beside them)")
        # the villager walks from its spot to the bed, the workstation and out of the door to the bell (no stairs)
        free = lambda x, z: lint.passable(t.get(x, 1, z)) and lint.passable(t.get(x, 2, z)) and 0 <= x < HUT_SIZE[0] and 0 <= z < HUT_SIZE[2]
        seen, todo = {(VILLAGER[0], VILLAGER[2])}, [(VILLAGER[0], VILLAGER[2])]
        while todo:
            x, z = todo.pop()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, z + dz)
                st = t.get(n[0], 1, n[1]) or ""
                if n not in seen and (free(*n) or "_door" in st):
                    seen.add(n)
                    todo.append(n)
        for what, p in (("bed", BED[0]), ("workstation", STATION), ("bell", BELL)):
            if not any((p[0] + dx, p[2] + dz) in seen for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                e.append(f"spawn_roads: hut {name}: its villager cannot reach the {what}")
    return e


def text_errors(translations=None):
    """[] if every sign line fits (90 px) in each language."""
    import languages
    base = lang()
    e = []
    for code, texts in [("es_es", base["es_es"]), ("en_us", base["en_us"])] + list((translations or {}).items()):
        for k in SIGN:
            s = texts.get(f"{NS}.casa_heraldo.{k}")
            if s is None:
                continue
            if languages.sign_width(languages.format_text(s, []), False) > languages.SIGN_WIDTH:
                e.append(f"spawn_roads: {code}: the sign line {k} does not fit: «{s}»")
    return e


def errors():
    return layout_errors() + template_errors()


# ------------------------------------------------------------------ texts
TEXTS = {
    "caminos.arena": ("A la Arena", "To the Arena"),
    "caminos.guia.nombre": ("Garcés, vigía del camino", "Garcés, warden of the road"),
    "caminos.guia.saludo": ("Buen día, viajero. Si buscas gloria, este camino es el tuyo.",
                            "Good day, traveller. If it is glory you seek, this is your road."),
    "caminos.guia.linea1": ("Sigue las farolas y llegarás a la Arena, donde combaten los mejores guerreros de la comarca.",
                            "Follow the lanterns and you will reach the Arena, where the finest warriors of these lands fight."),
    "caminos.guia.linea2": ("Está a unos %s bloques de aquí. Nadie la ha cruzado sin oír antes su campana.",
                            "It lies some %s blocks from here. Nobody has crossed it without hearing its bell first."),
    "caminos.guia.sin_arena": ("Dicen que pronto alzarán una arena al final de este camino. Hasta entonces, solo hay polvo y viento.",
                               "They say an arena will rise at the end of this road soon. Until then there is only dust and wind."),
    "caminos.guia.mas1": ("El Heraldo mandó trazar este camino el mismo año en que se alzó la muralla: quería que los campeones "
                          "llegaran a la arena sin perderse entre los pinos.",
                          "The Herald had this road laid the same year the wall went up: he wanted the champions to reach the "
                          "arena without getting lost among the pines."),
    "caminos.guia.mas2": ("Toca la campana del ruedo y saldrán a por ti, oleada tras oleada. Los nombres de quienes más aguantan "
                          "quedan escritos en los carteles de la entrada hasta la semana siguiente.",
                          "Ring the bell in the ring and they will come for you, wave after wave. The names of those who last "
                          "longest stay written on the signs at the entrance until the next week."),
    "caminos.guia.mas3": ("Yo serví en esas gradas cuando era joven. Ahora vendo hojas afiladas a los que van y escucho lo que "
                          "cuentan los que vuelven.",
                          "I served on those stands when I was young. Now I sell sharp blades to those who go, and listen to "
                          "what those who come back have to tell."),
    "caminos.guia.adios": ("Que tu acero no se mella. La arena te espera.", "May your steel never chip. The arena awaits you."),
    "caminos.guia.boton.mas": ("Cuéntame más", "Tell me more"),
    "caminos.guia.boton.tratar": ("Ver lo que vendes", "Show me your wares"),
    "caminos.guia.boton.adios": ("Adiós", "Farewell"),
    "caminos.guia.boton.cerrar": ("Cerrar", "Close"),
    "caminos.construyendo": ("Construyendo los caminos de la Casa del Heraldo…", "Building the roads out of the Herald's House…"),
    "caminos.hechos": ("Caminos de la Casa del Heraldo listos: %s caminos, %s chozas, %s aldeanos",
                       "The Herald's House roads are ready: %s roads, %s huts, %s villagers"),
    "caminos.nada": ("Los caminos de la Casa del Heraldo ya están construidos: no queda nada por hacer",
                     "The Herald's House roads are already built: there is nothing left to do"),
    "caminos.desactivados": ("Los caminos de la Casa del Heraldo están desactivados (casa_heraldo.caminos.activado)",
                             "The Herald's House roads are disabled (casa_heraldo.caminos.activado)"),
    "caminos.ocupado": ("Ya se están construyendo los caminos (o la casa): espera a que terminen",
                        "The roads (or the house) are being built already: wait for them to finish"),
}
# what has to fit on a sign line in each language (the arena road's two signs; camino.cartel2 is the town's own)
SIGN = ["caminos.arena"]


def lang():
    out = {"es_es": {}, "en_us": {}}
    for k, (es, en) in TEXTS.items():
        out["es_es"][f"{NS}.casa_heraldo.{k}"], out["en_us"][f"{NS}.casa_heraldo.{k}"] = es, en
    return out


def write(out, jdump):
    """Writes the hut templates and heraldia/caminos_casa.json; returns the texts. Fails on any broken rule."""
    ts = templates()
    e = layout_errors() + template_errors(ts) + text_errors()
    if e:
        raise SystemExit("\n".join(e))
    for t in ts.values():
        t.save(out)
    jdump(out, f"{NS}/caminos_casa.json", dataset())
    return lang()
