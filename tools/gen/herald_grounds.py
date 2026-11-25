"""The Herald's House grounds (casa_heraldo.alrededores.*): the protected ring around the town levelled into walkable,
gentle ground, with a few cherry trees and a few small houses with something inside.

What the owner asked for: wherever the town lands, the protected margin around it (Grounds.RING blocks on each side of
the 128 x 128 town) flattened and decorated: a few cherry trees and small, eye-catching houses around it with contents
inside. The orchestrator's decisions: "flattened" is walkable, gentle ground (no vertical cuts, no loose columns, no
holes, its outer edge blended into the natural terrain), not one plateau; cut and fill capped (as the roads do); a few
cherry trees, not a forest; several different small houses, each with a chest whose contents come from a filler loot table
(heraldia:relleno/*: a few cheap stacks, never empty, never restocked nor scaled by the difficulty);
no new villagers (nothing in them a villager would claim: no bed, bell or workstation).

Like the town and its roads it is not world generation: the Java side (herald/Outskirts, herald/OutskirtsPlan) BUILDS it
in chunks that already exist, once, after the town (and its roads, if they are on) is placed, or on /heraldia herald
grounds in a world whose town came before this feature. This module writes:
  - the house templates (heraldia:casa_heraldo/alrededores/<name>): fireproof materials only (nothing burns where
    lightning could start a fire: the same rule as the town), a crimson door with room in front of it, a chest with a
    loot table, and furniture that no villager claims;
  - heraldia/alrededores_casa.json: the plan's numbers (cut, fill, smoothing) and the house slots and cherry sites,
    relative to the town template's minimum corner. The slots stand in the four sides and corners of the ring, away from
    the gates' roads and their huts (which the roads own), and inside the depth the arena road never reaches;
  - the texts.
errors() checks the door rule over the town, the roadside huts and every house slot (doors.footprint_errors), each
template's door (doors.template_report), the loot tables, the fire rule and the spacing of the cherries.
"""
import herald_house as hh
import doors
import lint
import filler_loot
import spawn_roads as sr
from core import Template, NS

VERSION = 1
TEMPLATE_PREFIX = "casa_heraldo/alrededores/"
RING = 50                  # herald/Grounds.RING: the protected blocks on each side of the town
N = hh.N                   # the town's side (128)
# --- the ground (the Java plan reads these) ---
CUT, FILL = 10, 10         # at most this many blocks cut away or filled in at a column (the roads' own caps)
SMOOTH = 6                 # the radius of the mean that makes the ground gentle (a 13 x 13 window)
EDGE = 1                   # the outermost columns of the ring stay as they are: the natural ground the rest blends into
# --- what stays clear of houses and trees ---
CORRIDOR = 16              # half width of each gate's road corridor kept free (its road, lamps, signs and huts)
MAX_DEPTH = 36             # a house's plot never reaches deeper than this into the ring (the arena road keeps beyond 42)
TREE_DEPTH = 40            # nor a cherry tree's trunk
YARD = 3                   # the front yard (rows in front of the door: the door rule's room)
DEFAULT_HOUSES = 8
CHERRIES = 10              # the cherry trees planted, at most (some sites may not fit)
TREE_GAP = 7               # a cherry's trunk at least this far from any house's plot
FLAT = 5                   # a house's plot is built only where the planned ground varies by at most this much

# Blocks no house may hold: a villager would claim them (beds, bells, workstations: the town's 18 residents are the
# entity budget, and a free bed lets them breed) or they are a fire source.
POI = ("_bed", "bell", "barrel", "composter", "loom", "lectern", "cauldron", "smoker", "blast_furnace", "brewing_stand",
       "cartography_table", "fletching_table", "grindstone", "smithing_table", "stonecutter", "beehive", "bee_nest",
       "lodestone", "lightning_rod", "campfire", "fire", "lava", "magma_block", "torch")


# ------------------------------------------------------------------ building blocks
def _house(name, width, depth, wall, corner, roof, gable, floor, door_x, loot_table, kind="x"):
    """A house: local x across its front (the roof's side overhang at x 0 and width - 1), local z from the front of the
    yard (z 0 .. YARD - 1) to the back wall (depth - 1); y 0 is the ground layer, the floor; the walls rise to y 3 and a
    roof above: `kind` "x" a gable with its ridge along x, "z" a gable whose end faces the yard, "hip", or "flat" (a
    terrace behind a parapet). The door, in the front wall (z = YARD) at x = door_x, opens to local north."""
    t = Template(TEMPLATE_PREFIX + name)
    zf, zb = YARD, depth - 1
    x0, x1 = 1, width - 2
    rows = zb - zf + 1
    top = 4 + (rows + 1) // 2
    for x in range(width):
        for z in range(depth):
            inside = x0 <= x <= x1 and zf <= z <= zb
            t.set(x, 0, z, floor if inside else "grass_block[snowy=false]")
            for y in range(1, top + 1):
                t.set(x, y, z, "air")
    for x in range(x0, x1 + 1):                        # the walls (log posts at the corners, a plinth row)
        for z in range(zf, zb + 1):
            if x not in (x0, x1) and z not in (zf, zb):
                continue
            post = x in (x0, x1) and z in (zf, zb)
            for y in (1, 2, 3):
                t.set(x, y, z, corner if post else wall)
    st = lambda facing: f"{roof}[facing={facing},half=bottom,shape=straight,waterlogged=false]"
    slab = roof.replace("_stairs", "_slab") + "[type=bottom,waterlogged=false]"
    if kind == "z":                                     # a gable whose end faces the yard: the eaves over each side
        top = 4 + (width + 1) // 2
        for y in range(top + 1):
            for x in range(width):
                for z in range(depth):
                    if t.get(x, y, z) is None:
                        t.set(x, y, z, "air")
        for k in range((width + 1) // 2):
            y, lo, hi = 4 + k, k, width - 1 - k
            for z in range(zf, zb + 1):
                if lo == hi:
                    t.set(lo, y, z, slab)
                    continue
                t.set(lo, y, z, st("east"))
                t.set(hi, y, z, st("west"))
            for z in (zf, zb):                          # the gable ends under that row
                for x in range(max(lo + 1, x0), min(hi, x1 + 1)):
                    t.set(x, y, z, gable)
        for z in range(zf, zb + 1):                     # the wall plate under the eaves
            for x in (x0, x1):
                t.set(x, 4, z, wall)
    elif kind == "hip":
        for k in range(max(width, rows)):
            a, b_, c, d = k, width - 1 - k, zf + k, zb - k
            if a > b_ or c > d:
                break
            for x in range(a, b_ + 1):
                for z in range(c, d + 1):
                    if x in (a, b_) or z in (c, d):
                        t.set(x, 4 + k, z, slab if c == d or a == b_ else
                              st("south" if z == c else "north" if z == d else "east" if x == a else "west"))
    elif kind == "flat":                                # a terrace: the roof's block behind a low parapet, beams out front
        for x in range(x0, x1 + 1):
            for z in range(zf, zb + 1):
                edge = x in (x0, x1) or z in (zf, zb)
                t.set(x, 4, z, wall if edge else gable)
                if edge and ((x + z) % 2 == 0 or (x in (x0, x1) and z in (zf, zb))):
                    t.set(x, 5, z, slab)
        for x in range(x0 + 1, x1, 2):
            if x != door_x:
                t.set(x, 3, zf - 1, "stripped_crimson_stem[axis=z]")
    for k in range((rows + 1) // 2 if kind == "x" else 0):   # the gable roof: one row of stairs up per row in
        y = 4 + k
        for x in range(width):
            front, back = zf + k, zb - k
            if front == back:
                t.set(x, y, front, roof.replace("_stairs", "_slab") + "[type=bottom,waterlogged=false]")
                continue
            if front > back:
                break
            t.set(x, y, front, f"{roof}[facing=south,half=bottom,shape=straight,waterlogged=false]")
            t.set(x, y, back, f"{roof}[facing=north,half=bottom,shape=straight,waterlogged=false]")
        for x in (x0, x1):                              # the gable ends under that row
            for z in range(zf + k + 1, zb - k):
                t.set(x, y, z, gable)
    for x in range(x0 + 1, x1):                         # the ceiling under the roof (the inside's top at y 3)
        for z in range(zf + 1, zb):
            if t.get(x, 4, z) == "minecraft:air":
                t.set(x, 4, z, gable)
    t.set(door_x, 1, zf, "crimson_door[facing=north,half=lower,hinge=left,open=false,powered=false]")
    t.set(door_x, 2, zf, "crimson_door[facing=north,half=upper,hinge=left,open=false,powered=false]")
    for z in range(YARD):                               # the path from the door to the front of the yard
        t.set(door_x, 0, z, "dirt_path")
    top = max(y for (x, y, z), (bst, _) in t.blocks.items() if bst != "minecraft:air")
    t.min_size = (width, top + 1, depth)
    t.door = (door_x, 1, zf)
    t.loot = loot_table
    t.walls = (x0, zf, x1, zb)
    return t


def _windows(t, spots, pane="glass_pane"):
    for x, y, z in spots:
        t.set(x, y, z, pane)


def _flowers(t, spots, kinds):
    for i, (x, z) in enumerate(spots):
        t.set(x, 1, z, kinds[i % len(kinds)])


def _table(t, x, z, chairs=()):
    t.set(x, 1, z, "crimson_fence")
    t.set(x, 2, z, "crimson_pressure_plate[powered=false]")
    for cx, cz, facing in chairs:
        t.set(cx, 1, cz, f"crimson_stairs[facing={facing},half=bottom,shape=straight,waterlogged=false]")


def _lantern_post(t, x, z):
    t.set(x, 1, z, "crimson_fence")
    t.set(x, 2, z, "lantern[hanging=false,waterlogged=false]")


# ------------------------------------------------------------------ the houses
def cherry_cottage():
    """White and pink, a granite roof: the house that goes with the cherry trees."""
    t = _house("casita_cerezo", 9, 10, "white_terracotta", "stripped_crimson_stem[axis=y]", "granite_stairs",
               "pink_terracotta", "crimson_planks", 4, filler_loot.table_id("casa"))
    # a porch either side of the door: a post and a granite cover each. The door's own column stays under the open sky:
    # the door rule only checks a door whose way out it can see (doors.template_report skips one under a cover)
    for x in (2, 6):
        t.set(x, 1, YARD - 1, "crimson_fence")
        t.set(x, 2, YARD - 1, "crimson_fence")
    for x in (2, 3, 5, 6):
        t.set(x, 3, YARD - 1, "granite_slab[type=bottom,waterlogged=false]")
    _windows(t, [(2, 2, 3), (6, 2, 3), (1, 2, 6), (7, 2, 6), (4, 2, 9)])
    _flowers(t, [(1, 1), (2, 1), (6, 1), (7, 1)], ["pink_tulip", "allium", "pink_tulip", "lily_of_the_valley"])
    t.chest(6, 1, 8, "north", t.loot)
    t.set(2, 1, 8, "crafting_table")
    _table(t, 3, 6, [(2, 6, "east")])
    t.set(6, 1, 5, "potted_cherry_sapling")
    t.set(4, 3, 6, "lantern[hanging=true,waterlogged=false]")
    t.set(2, 1, 4, "decorated_pot[cracked=false,facing=north,waterlogged=false]", {"id": "minecraft:decorated_pot"})
    _lantern_post(t, 8, 0)
    return t


def brick_house():
    """Brick walls, a dark tiled roof and a chimney: the widest house."""
    t = _house("casa_ladrillo", 11, 10, "bricks", "stone_bricks", "deepslate_tile_stairs", "bricks",
               "polished_andesite", 5, filler_loot.table_id("despensa"))
    # a dormer over the door: two posts and a pane on the slope, its own little gable
    tile = "deepslate_tile_stairs[facing={},half=bottom,shape=straight,waterlogged=false]"
    for x in (4, 6):
        t.set(x, 6, YARD + 1, "stone_bricks")
    t.set(5, 6, YARD + 1, "glass_pane[east=true,west=true]")
    for z in (YARD + 1, YARD + 2):
        t.set(4, 7, z, tile.format("east"))
        t.set(6, 7, z, tile.format("west"))
        t.set(5, 8, z, "deepslate_tile_slab[type=bottom,waterlogged=false]")
    t.set(5, 7, YARD + 1, "bricks")
    _windows(t, [(2, 2, 3), (3, 2, 3), (7, 2, 3), (8, 2, 3), (1, 2, 6), (9, 2, 6)])
    for y in range(1, 9):                               # the chimney (no fire: only its stack)
        t.set(8, y, 9, "bricks")
    t.set(8, 9, 9, "brick_wall[east=none,north=none,south=none,up=true,waterlogged=false,west=none]")
    t.set(8, 1, 8, "furnace[facing=north,lit=false]")
    t.set(7, 1, 8, "furnace[facing=north,lit=false]")
    t.chest(2, 1, 8, "north", t.loot)
    _table(t, 4, 6, [(3, 6, "east"), (5, 6, "west")])
    t.set(5, 3, 6, "lantern[hanging=true,waterlogged=false]")
    t.set(9, 1, 4, "decorated_pot[cracked=false,facing=west,waterlogged=false]", {"id": "minecraft:decorated_pot"})
    _flowers(t, [(1, 1), (3, 0), (8, 1), (9, 0)], ["poppy", "dandelion", "oxeye_daisy", "poppy"])
    _lantern_post(t, 0, 0)
    return t


def stone_house():
    """Stone bricks gone mossy, a blackstone roof, candles on the sill: the old house."""
    t = _house("casa_piedra", 9, 10, "mossy_stone_bricks", "polished_andesite", "polished_blackstone_brick_stairs",
               "stone_bricks", "stone_bricks", 4, filler_loot.table_id("granja"), kind="hip")
    _windows(t, [(2, 2, 3), (6, 2, 3), (1, 2, 7), (7, 2, 7)], "iron_bars")
    t.chest(2, 1, 8, "north", t.loot)
    t.set(6, 1, 8, "crafting_table")
    t.set(7 - 1, 2, 8, "candle[candles=3,lit=false,waterlogged=false]")
    t.set(2, 1, 5, "potted_fern")
    t.set(6, 1, 5, "potted_red_mushroom")
    t.set(4, 3, 6, "lantern[hanging=true,waterlogged=false]")
    _flowers(t, [(1, 0), (2, 1), (6, 1), (7, 0)], ["cornflower", "azure_bluet", "cornflower", "oxeye_daisy"])
    t.set(7, 0, 1, "mossy_cobblestone")
    _lantern_post(t, 8, 1)
    return t


def mud_house():
    """Mud brick walls and roof, a waxed copper lantern: the warm one."""
    t = _house("casa_barro", 10, 9, "mud_bricks", "packed_mud", "mud_brick_stairs", "packed_mud", "packed_mud", 5,
               filler_loot.table_id("molino"), kind="flat")
    _windows(t, [(3, 2, 3), (7, 2, 3), (1, 2, 6), (8, 2, 6)])
    t.chest(7, 1, 7, "north", t.loot)
    t.set(2, 1, 7, "furnace[facing=north,lit=false]")
    _table(t, 4, 5, [(3, 5, "east")])
    t.set(5, 3, 6, "waxed_copper_lantern[hanging=true,waterlogged=false]")
    t.set(7, 1, 4, "decorated_pot[cracked=false,facing=west,waterlogged=false]", {"id": "minecraft:decorated_pot"})
    _flowers(t, [(1, 1), (3, 0), (7, 1), (8, 0)], ["orange_tulip", "dandelion", "red_tulip", "orange_tulip"])
    _lantern_post(t, 9, 0)
    return t


def tuff_house():
    """Tuff bricks, a polished tuff roof, a bench in the yard: the reading house."""
    t = _house("casa_toba", 9, 11, "tuff_bricks", "chiseled_tuff_bricks", "polished_tuff_stairs", "polished_tuff",
               "polished_tuff", 4, filler_loot.table_id("estudio"), kind="z")
    _windows(t, [(2, 2, 3), (6, 2, 3), (1, 2, 7), (7, 2, 7), (4, 2, 10)])
    t.chest(6, 1, 9, "north", t.loot)
    t.set(2, 1, 9, "crafting_table")
    _table(t, 4, 7, [(3, 7, "east"), (5, 7, "west")])
    t.set(2, 1, 5, "potted_azalea_bush")
    t.set(4, 3, 7, "lantern[hanging=true,waterlogged=false]")
    for x in (1, 2):                                    # a bench in the yard, beside the path
        t.set(x, 1, 1, "polished_tuff_stairs[facing=south,half=bottom,shape=straight,waterlogged=false]")
    _flowers(t, [(6, 1), (7, 1), (7, 0)], ["allium", "blue_orchid", "allium"])
    _lantern_post(t, 8, 2)
    return t


DESIGNS = [cherry_cottage, brick_house, stone_house, mud_house, tuff_house]


def templates():
    """{name: template} of every house."""
    out = {}
    for f in DESIGNS:
        t = f()
        out[t.name.removeprefix(TEMPLATE_PREFIX)] = t
    return out


# ------------------------------------------------------------------ the slots
ROTATION = {"north": "none", "east": "clockwise_90", "south": "clockwise_180", "west": "counterclockwise_90"}


def rotate(rotation, x, z):
    """StructureTemplate.transform without a pivot (Mirror.NONE)."""
    return {"none": (x, z), "clockwise_90": (-z, x), "clockwise_180": (-x, -z), "counterclockwise_90": (z, -x)}[rotation]


# (slot, house, centre x, centre z, the way its door faces), in template coordinates of the town (0..127 its footprint);
# the order is the order they are built in (DEFAULT_HOUSES first: two per side, spread), then the corners. Each has an
# alternative place (ALTERNATIVES, the same group): tried only if the first one does not fit (water, a slope, a road), so
# a town by a lake still gets its houses; at most one house per group.
SLOTS = [
    ("n1", "casita_cerezo", 20, -22, "north"),
    ("s2", "casa_ladrillo", 104, 148, "south"),
    ("o1", "casa_piedra", -22, 18, "west"),
    ("e2", "casa_barro", 149, 104, "east"),
    ("n2", "casa_toba", 108, -25, "north"),
    ("s1", "casita_cerezo", 23, 151, "south"),
    ("o2", "casa_barro", -24, 100, "west"),
    ("e1", "casa_piedra", 151, 20, "east"),
    ("no", "casa_ladrillo", -27, -26, "west"),
    ("ne", "casa_toba", 155, -24, "north"),
    ("so", "casa_piedra", -25, 154, "south"),
    ("se", "casita_cerezo", 154, 153, "east"),
]
ALTERNATIVES = [
    ("n1b", "casita_cerezo", 34, -30, "north"),
    ("s2b", "casa_ladrillo", 96, 156, "south"),
    ("o1b", "casa_piedra", -30, 34, "west"),
    ("e2b", "casa_barro", 157, 88, "east"),
    ("n2b", "casa_toba", 94, -30, "north"),
    ("s1b", "casita_cerezo", 38, 156, "south"),
    ("o2b", "casa_barro", -30, 84, "west"),
    ("e1b", "casa_piedra", 158, 36, "east"),
    ("nob", "casa_ladrillo", -12, -30, "north"),
    ("neb", "casa_toba", 142, -30, "north"),
    ("sob", "casa_piedra", -30, 140, "west"),
    ("seb", "casita_cerezo", 140, 158, "south"),
]
MAX_HOUSES = len(SLOTS)    # one per group at most


def all_slots():
    """Every slot with its group (the index of its first place): the first places, then the alternatives."""
    return [(sl, k) for k, sl in enumerate(SLOTS)] + [(sl, k) for k, sl in enumerate(ALTERNATIVES)]
# cherry trunks (template coordinates): one or two near each house and a few loose pairs
CHERRY_SITES = [(4, -14), (36, -36), (122, -38), (90, -14), (162, 36), (164, 86), (140, 120), (124, 162), (88, 160),
                (40, 166), (8, 140), (-36, 120), (-14, 80), (-38, 36), (-10, -38), (166, -6)]


def frame(slot):
    """(rotation, world origin (x, z), local -> world) of a slot: the template's middle on the slot's centre."""
    _, house, cx, cz, facing = slot
    t = templates()[house]
    sx, _, sz = t.size()
    rot = ROTATION[facing]
    mx, mz = rotate(rot, (sx - 1) // 2, (sz - 1) // 2)
    ox, oz = cx - mx, cz - mz

    def world(lx, lz):
        rx, rz = rotate(rot, lx, lz)
        return ox + rx, oz + rz
    return rot, (ox, oz), world


def _rect(world, x0, z0, x1, z1):
    a, b = world(x0, z0), world(x1, z1)
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def slot_shapes(slot):
    """{plot, walls, door: (facing, x, z), rotation, origin} of a slot in template coordinates of the town."""
    t = templates()[slot[1]]
    sx, _, sz = t.size()
    rot, origin, world = frame(slot)
    dx, _, dz = t.door
    x, z = world(dx, dz)
    return {"plot": _rect(world, 0, 0, sx - 1, sz - 1), "walls": _rect(world, *t.walls), "door": (slot[4], x, z),
            "rotation": rot, "origin": origin}


def depth(x, z):
    """How far (x, z) lies out of the town's footprint (Chebyshev; 0 inside)."""
    return max(-x, x - (N - 1), -z, z - (N - 1), 0)


def corridor_distance(x, z):
    """The distance across from (x, z) to the nearest gate's road axis, within that road's side of the ring."""
    best = 10 ** 9
    for side, (gx, gz) in hh.GATES.items():
        if side in ("north", "south") and (z < 0 if side == "north" else z > N - 1):
            best = min(best, abs(x - gx))
        if side in ("west", "east") and (x < 0 if side == "west" else x > N - 1):
            best = min(best, abs(z - gz))
    return best


# ------------------------------------------------------------------ what the Java side reads
def dataset():
    ts = templates()
    return {
        "version": VERSION, "anillo": RING, "corte": CUT, "relleno": FILL, "suavizado": SMOOTH, "borde": EDGE,
        "pasillo": CORRIDOR, "llano": FLAT, "casas_por_defecto": DEFAULT_HOUSES, "cerezos": CHERRIES,
        "casas": [{"nombre": n, "plantilla": f"{NS}:{t.name}", "tamano": list(t.size()), "botin": t.loot}
                  for n, t in ts.items()],
        "huecos": [dict(hueco=s[0], grupo=k, casa=s[1], giro=sh["rotation"], origen=list(sh["origin"]), parcela=list(sh["plot"]),
                        muros=list(sh["walls"]), puerta=[sh["door"][1], sh["door"][2]], mira=s[4])
                   for s, k in all_slots() for sh in [slot_shapes(s)]],
        "sitios_cerezo": [list(c) for c in CHERRY_SITES],
    }


# ------------------------------------------------------------------ checks
def layout_errors():
    """The door rule over the town, every roadside hut slot and every house slot; and every house inside its bounds."""
    blds = [("casa_heraldo", (0, 0, N - 1, N - 1), [])]
    for side in sr.SIDES:
        gate = hh.GATES[side]
        for name, sd, along in sr.slots(True):
            rect, door = sr.hut_rect(gate, side, sd, along)
            blds.append((f"choza_{side}_{name}", rect, [door]))
    e = []
    houses = []
    for s, k in all_slots():
        sh = slot_shapes(s)
        houses.append((k, (f"alrededores_{s[0]}", sh["walls"], [sh["door"]])))
        x0, z0, x1, z1 = sh["plot"]
        if max(depth(x, z) for x in (x0, x1) for z in (z0, z1)) > MAX_DEPTH:
            e.append(f"herald_grounds: house {s[0]}: its plot reaches deeper than {MAX_DEPTH} into the ring")
        if min(depth(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)) < 10:
            e.append(f"herald_grounds: house {s[0]}: its plot comes within 10 blocks of the town")
        if min(corridor_distance(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)) < CORRIDOR:
            e.append(f"herald_grounds: house {s[0]}: its plot is inside a gate's road corridor")
    # the rule over the town, the huts and every pair of houses that can stand together (not two places of one group)
    seen = set()
    for _, b in houses:
        seen.update(doors.footprint_errors(blds + [b]))
    for i, (ga, a) in enumerate(houses):
        for gb, b in houses[i + 1:]:
            if ga != gb:
                seen.update(doors.footprint_errors([a, b]))
    return e + [f"herald_grounds: {m}" for m in sorted(seen)]


def cherry_errors():
    e = []
    plots = [slot_shapes(s)["plot"] for s in SLOTS]   # the first places (a tree by a chosen alternative: the plan skips it)
    for x, z in CHERRY_SITES:
        if not 6 <= depth(x, z) <= TREE_DEPTH:
            e.append(f"herald_grounds: cherry at {x} {z}: {depth(x, z)} blocks out (6 to {TREE_DEPTH})")
        if corridor_distance(x, z) < CORRIDOR:
            e.append(f"herald_grounds: cherry at {x} {z}: inside a gate's road corridor")
        for p in plots:
            gap = max(p[0] - x, x - p[2], p[1] - z, z - p[3])
            if gap < TREE_GAP:
                e.append(f"herald_grounds: cherry at {x} {z}: {gap} blocks from a house's plot (at least {TREE_GAP})")
    return e


def _name(st):
    return (st or "minecraft:air").split("[")[0].removeprefix("minecraft:")


def template_errors(ts=None):
    e = []
    names = [_name(st) for t in (ts or templates()).values() for st, _ in t.blocks.values()]
    if len(ts or templates()) < 4:
        e.append("herald_grounds: fewer than four house designs")
    for name, t in (ts or templates()).items():
        for msg in doors.template_report(t):
            e.append(f"herald_grounds: house {name}: {msg}")
        if not doors.doors_of(t):
            e.append(f"herald_grounds: house {name}: no door")
        if t.entities:
            e.append(f"herald_grounds: house {name}: entities (no new villagers or animals)")
        chests = [(p, nbt) for p, (st, nbt) in t.blocks.items() if _name(st) in ("chest", "trapped_chest")]
        if not chests:
            e.append(f"herald_grounds: house {name}: no chest")
        for p, nbt in chests:
            tbl = str((nbt or {}).get("LootTable", ""))
            if tbl not in {filler_loot.table_id(k) for k in filler_loot.TABLES}:
                e.append(f"herald_grounds: house {name}: the chest at {p} has no filler loot table ({tbl!r})")
        for p, (st, _) in t.blocks.items():
            n = _name(st)
            if any(n == k or n.endswith(k) for k in POI):
                e.append(f"herald_grounds: house {name}: {n} at {p} (a villager would claim it, or it burns)")
            if hh._burns(n) and n not in hh.PLANTS:
                e.append(f"herald_grounds: house {name}: {n} at {p} burns (fireproof materials only)")
    if len(set(names)) < 10:
        e.append("herald_grounds: the houses look alike")
    return e


def errors():
    return layout_errors() + cherry_errors() + template_errors()


# ------------------------------------------------------------------ texts
TEXTS = {
    "alrededores.construyendo": ("Preparando los alrededores de la Casa del Heraldo…", "Preparing the Herald's House grounds…"),
    "alrededores.hechos": ("Alrededores de la Casa del Heraldo listos: %s columnas allanadas, %s casas, %s cerezos",
                           "The Herald's House grounds are ready: %s columns levelled, %s houses, %s cherry trees"),
    "alrededores.nada": ("Los alrededores de la Casa del Heraldo ya están preparados: no queda nada por hacer",
                         "The Herald's House grounds are already prepared: there is nothing left to do"),
    "alrededores.desactivados": ("Los alrededores de la Casa del Heraldo están desactivados (casa_heraldo.alrededores.activado)",
                                 "The Herald's House grounds are disabled (casa_heraldo.alrededores.activado)"),
    "alrededores.ocupado": ("Ya se está construyendo algo de la Casa del Heraldo: espera a que termine",
                            "Something of the Herald's House is being built already: wait for it to finish"),
}


def lang():
    out = {"es_es": {}, "en_us": {}}
    for k, (es, en) in TEXTS.items():
        out["es_es"][f"{NS}.casa_heraldo.{k}"], out["en_us"][f"{NS}.casa_heraldo.{k}"] = es, en
    return out


def write(out, jdump):
    """Writes the house templates and heraldia/alrededores_casa.json; returns the texts. Fails on any broken rule."""
    ts = templates()
    e = layout_errors() + cherry_errors() + template_errors(ts)
    if e:
        raise SystemExit("\n".join(e))
    for t in ts.values():
        t.save(out)
    jdump(out, f"{NS}/alrededores_casa.json", dataset())
    return lang()
