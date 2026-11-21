"""The Herald's House ("La Casa del Heraldo"): the world-spawn town (template, blueprint for the Java side, texts).

Like the wave arena (arena_waves.py) it is not a world-generation structure: the mod places it once per world, at the
spawn of a new world (casa_heraldo.generar_en_mundos_nuevos) or where an operator confirms it in a world that already
exists (/heraldia herald place), with this template (heraldia:casa_heraldo/casa). Version 2, a 128 x 128 walled town:
  - the wall: four blocks thick with a wall walk between battlements and a parapet, corner towers that rise above it
    with copper cones, banners and lightning rods, an arched gate in the north, west and east sides and, in the south,
    the gatehouse (two flanking towers over the arch) opening onto a forecourt with the approach avenue, banners and
    signposts; two iron golems keep the night watch on the wall walk (the tower doors keep them up there);
  - the plaza at the centre, where the roads cross: a raised dais with steps under a copper canopy holds the bell (the
    villagers' meeting point), with the clock tower over the plaza, the monument to the Herald, flagpoles with the
    town's banner, lamp posts and benches, and the villages' job board under its own canopy (board.piece, reused);
    its 23 x 23 middle is laid out like a village square so the village events (events/) can happen there;
  - every building has its own recipe (shell, roof, façade and furniture): the two-storey inn with the hearth, long
    tables and rooms upstairs, the chapel, the library, the smithy with its anvil yard and smoking chimney, the butcher
    with its awning and the meat hanging in frames, the cartographer, the bakery, the herbalist, the workshop, the
    weaver, the stable and the guardhouse in the gatehouse; 18 villagers live and work in them, with a bed each (two
    spare), their workstation and a bell they can walk to (four bells: the plaza's and three neighbourhood ones);
  - the market (eight stalls players can rent, market.*, off by default, and the office with the return barrels),
    the Nether portal (an obsidian frame under a pavilion, built and not lit: only an operator lights it), the farm,
    gardens, laundry lines, a cart and stacked crates (the villages' work-in-progress traces, traces.py, reused with
    fireproof materials), animals in the stable and the coop and cats on the roofs.
Nothing that burns is left where fire could reach it: the building materials are stone, brick, terracotta, deepslate,
tuff, calcite, copper, blackstone and crimson wood (fireproof), and the few flammable blocks a house needs (bookshelves,
carpets, the lectern, hay, the composters, the coal) are only allowed where a fire started by lightning cannot reach
them (fire_errors: a model of how lightning lights fire and how fire spreads in 26.3). Where things go is checked as
the template is generated (placement_errors: doors with room in front, no door facing a wall, buildings apart, every
door on a street); who lives where, by resident_errors (walked as a villager: no ladders, gates closed).
heraldia/casa_heraldo.json tells the Java side where everything is (positions relative to the template's minimum
corner); errors() checks that the template keeps those promises (generation fails otherwise). The blueprint of
version 1 (the 96 x 96 town of the first release) travels inside it too (herald_house_v1.json, frozen): a world that
placed that town keeps its protection, stalls and barrels exactly where they are. The dock
(heraldia:casa_heraldo/muelle) is a second template, placed by the Java side only if there is water in front of a gate.
"""
import json
import math
import os
import random

from core import Template, NS, B, F, villager
import filler_loot
import board
import build
import herald_dress
import lint
import traces
from themes import THEMES
from uniques._common import pieces
from mediums import _inhabitants

TEMPLATE = "casa_heraldo/casa"
DOCK = "casa_heraldo/muelle"
VERSION = 2
N = 128                    # side of the (square) template
C = N // 2                 # 64: the north-south axis
FLOOR = 4                  # y of the ground layer: it goes at terrain height (y 0-3 is the foundation)
HEIGHT = FLOOR + 30        # y = 0 .. 33 (the clock tower's spire)
THEME = next(th for th in THEMES if th["id"] == "llanuras_castellana")
STYLE, FAMILY = THEME["id"], THEME["family"]   # how the villagers' conversations see the town (dialogue/Dialogue)
HOUSE_TAG = "heraldia_casa"  # on every entity of the house (Building.finish keeps them where they are)
DOCK_SIZE = (5, 16)        # width (x) and length (z, out over the water) of the dock
V1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "herald_house_v1.json")

# the wall: WALL_T thick (battlements, a 2-wide walk, the parapet), the walk's floor at WALL_TOP
WALL_T = 4
WALL_TOP = FLOOR + 6       # the walk's floor (its feet at WALL_TOP + 1: six steps up from the ground)
SOUTH = 115                # first row of the south wall (z 115..118); beyond it, the forecourt (z 119..127)
TOWER = 9                  # corner towers, 9 x 9
TOWER_TOP = FLOOR + 12     # the corner towers' roof slab (a cone above it)
GATE_W = 5
PZ = 60                    # the east-west axis (the plaza's centre is (C, PZ))
ROAD = (C - 2, C + 2)      # north road (x) and, around PZ, the west and east roads (z): 5 wide
AVENUE = (C - 3, C + 3)    # the south avenue: 7 wide
PLAZA = (C - 16, PZ - 16, C + 16, PZ + 16)   # paved: x 48..80, z 44..76
SQUARE = 23                # events/Layout.N: the event square in the plaza's middle
SQ0 = (C - SQUARE // 2, PZ - SQUARE // 2)    # its minimum corner (53, 49)
BELL = (C, FLOOR + 4, PZ)  # hanging from the canopy over the dais
SPAWN = (C, FLOOR + 1, PZ + 13)   # the plaza, south of the event square: the world spawn
GATES = {"north": (C, 0), "south": (C, N - 1), "west": (0, PZ), "east": (N - 1, PZ)}
PORTAL = ((36, FLOOR + 1, 104), (39, FLOOR + 5, 104))   # obsidian frame (min, max corner): 4 wide, 5 tall
BOARD = (73, FLOOR + 1, 38)                # the job board's lectern, in the clock tower's loggia (the bailiff at z + 1)
WELL = (70, 74, 82, 86)                    # x0, x1, z0, z1
FARM = (108, 10, 118, 24)                  # x0, z0, x1, z1 of the farm
FARM_CELL = (110, FLOOR, 12)               # one of its farmland blocks (the server test drops a player on it)
STALL_W = 5
STALL_X = (25, 31, 37, 43)                 # west x of each stall in a row
STALL_ROWS = ((66, "south"), (76, "north"))  # (north z of the row, side the counter faces)
RETURNS = 12                               # return barrels in the office
# the return barrels hold a former stall tenant's things (Market.java): a barrel is free only while it is empty
RETURN_EMPTY = "return barrel: Market only uses it while it is empty"


def fill_nbt(block, table):
    """Block nbt of a container with filler table heraldia:relleno/<table> (filler_loot): the town has no rule of its
    own, each container gets the table that fits its room."""
    return {"id": "minecraft:" + block, "LootTable": filler_loot.table_id(table)}


from doors import CLEAR as CLEAR_FRONT, FACE as FACE_CLEAR, GAP   # the door rule (doors.py)
BED_PATH, BELL_PATH = 16, 24               # blocks' walk: a resident's bed from its workstation; its bell from both

# materials (none burns: crimson wood is fireproof; the sheltered flammables are checked by fire_errors)
PAVE, PAVE2 = "stone_bricks", "polished_andesite"
FLOORING = "crimson_planks"
DOOR, FENCE, GATE, WOOD_SLAB = "crimson_door", "crimson_fence", "crimson_fence_gate", "crimson_slab"
WSTAIRS, TRAPDOOR, BEAM = "crimson_stairs", "crimson_trapdoor", "stripped_crimson_stem"
LANTERN = "lantern[hanging=true]"
COPPER = "waxed_oxidized_cut_copper"       # the towers', the canopy's and the clock tower's roofs
FIREPROOF = dict(THEME, floor=FLOORING, planks=FLOORING, log="crimson_stem", stripped=BEAM, fence=FENCE, gate=GATE,
                 door=DOOR, trapdoor=TRAPDOOR, wstairs=WSTAIRS, wslab=WOOD_SLAB, plate="crimson_pressure_plate",
                 button="crimson_button", wall="stone_bricks", found="polished_andesite", leaves="air",
                 roof_stairs="brick_stairs", roof_slab="brick_slab", roof_full="bricks")
BANNER = {"id": "minecraft:banner", "patterns": [{"pattern": "minecraft:border", "color": "yellow"},
                                                 {"pattern": "minecraft:rhombus", "color": "white"},
                                                 {"pattern": "minecraft:circle", "color": "yellow"}]}

PROFESSION = {"blast_furnace": "armorer", "smithing_table": "toolsmith", "grindstone": "weaponsmith",
              "smoker": "butcher", "cauldron": "leatherworker", "lectern": "librarian",
              "cartography_table": "cartographer", "fletching_table": "fletcher", "stonecutter": "mason",
              "brewing_stand": "cleric", "composter": "farmer", "barrel": "fisherman", "loom": "shepherd"}
WORKSTATION = {p: s for s, p in PROFESSION.items()}


def text(key):
    return pieces.text(f"{NS}.casa_heraldo.{key}", TEXTS[key][0])


def stairs(mat, facing, half="bottom"):
    return f"{mat}[facing={facing},half={half},shape=straight]"


def _h(x, y, z):
    x, y, z = int(x), int(y), int(z)
    return ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791)) & 0xFFFF


def _theme(stairs_, slab, full, wall="stone_bricks"):
    """A theme-like dict for build.py's roofs."""
    return dict(FIREPROOF, roof_stairs=stairs_, roof_slab=slab, roof_full=full, wall=wall)


def _cu(state):
    return f"waxed_{state}_cut_copper"


OPEN_DIR = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
FACING_BYTE = {"north": 2, "south": 3, "west": 4, "east": 5}
ROT = {"south": 0, "west": 4, "north": 8, "east": 12}     # standing sign/banner rotation readable from that side


# ------------------------------------------------------------------ buildings: where they are (checked)
class Bld:
    """A building's footprint (x0..x1, z0..z1, walls included), its door (side, coordinate along that wall) and what
    is built there (recipe). `over`: {side: blocks} its upper storey overhangs (for the spacing)."""

    def __init__(self, name, x0, z0, x1, z1, side, along, recipe, sign=True, over=None, extra=(), door_y=FLOOR + 1):
        self.name, self.x0, self.z0, self.x1, self.z1 = name, x0, z0, x1, z1
        self.side, self.along, self.recipe, self.sign, self.over = side, along, recipe, sign, over or {}
        self.extra = list(extra)           # more doors: (side, along, feet y)
        self.door_y = door_y

    def door(self, side=None, along=None):
        """The door's lower block (x, z) (the main one, or the one on that side and coordinate)."""
        side, along = side or self.side, self.along if along is None else along
        return {"north": (along, self.z0), "south": (along, self.z1), "west": (self.x0, along), "east": (self.x1, along)}[side]

    def doors(self):
        """Every door: (side, x, y, z)."""
        if self.side is None:
            return []
        out = [(self.side, *self.door(), self.door_y)]
        out += [(s, *self.door(s, a), y) for s, a, y in self.extra]
        return [(s, x, y, z) for s, x, z, y in out]

    def out(self, k=1):
        """The cell k blocks straight out of the main door."""
        (x, z), (dx, dz) = self.door(), OPEN_DIR[self.side]
        return x + dx * k, z + dz * k

    def rect(self, over=False):
        """The footprint; with `over`, its upper storey's overhangs too."""
        o = self.over if over else {}
        return self.x0 - o.get("west", 0), self.z0 - o.get("north", 0), self.x1 + o.get("east", 0), self.z1 + o.get("south", 0)

    def inside(self, x, z, over=False):
        a, b, c, d = self.rect(over)
        return a <= x <= c and b <= z <= d


def _buildings():
    """Every building of the town, with its doors. placement_errors() checks them (and the regression test checks
    that the same rules fail on version 1's layout). The corner towers' upper doors open onto the wall walk."""
    up = WALL_TOP + 1
    out = [
        Bld("establo", 13, 10, 21, 21, "east", 15, stable),
        Bld("herbolario", 31, 9, 41, 18, "south", 36, herbalist),
        Bld("biblioteca", 44, 30, 58, 41, "east", 36, library),
        Bld("posada", 26, 46, 44, 56, "east", 53, inn, over={"east": 1}),
        Bld("carniceria", 9, 32, 19, 43, "east", 38, butcher),
        Bld("capilla", 70, 7, 84, 21, "west", 14, chapel),
        Bld("panaderia", 89, 9, 99, 19, "south", 94, bakery),
        Bld("granero", 108, 26, 114, 31, "north", 111, granary),
        Bld("cartografo", 84, 44, 96, 54, "south", 90, cartographer),
        Bld("tejedor", 110, 38, 120, 48, "west", 43, weaver),
        Bld("herreria", 104, 66, 116, 76, "north", 110, smithy, extra=[("south", 110, FLOOR + 1)]),
        Bld("ayuntamiento", 83, 65, 98, 77, "west", 71, town_hall, over={"west": 4},
            extra=[("west", 71, FLOOR + 6)]),
        Bld("taller", 46, 84, 56, 94, "east", 89, workshop),
        Bld("oficina", 26, 84, 36, 92, "west", 88, office),
        Bld("torre_reloj", 70, 35, 76, 41, None, None, clock_tower, sign=False),
        Bld("guardia", 52, 112, 58, 122, "north", 55, guardhouse),
        Bld("almacen", 70, 112, 76, 122, "north", 73, storehouse, sign=False),
    ]
    for k, x, z, sx, sz in (("no", 0, 0, 1, 1), ("ne", N - TOWER, 0, -1, 1), ("so", 0, SOUTH + WALL_T - TOWER, 1, -1),
                            ("se", N - TOWER, SOUTH + WALL_T - TOWER, -1, -1)):
        tw = Tower(x, z, sx, sz)
        side, (dx, dz) = tw.face("south"), tw.at(6, 8)
        b = Bld(f"torre_{k}", x, z, x + TOWER - 1, z + TOWER - 1, side, dx if side in ("north", "south") else dz,
                corner_tower, sign=False)
        (ex, ez), (wx, wz) = tw.at(8, 2), tw.at(1, 8)
        b.extra = [(tw.face("east"), ez, up), (tw.face("south"), wx, up)]
        b.tower = tw
        out.append(b)
    return out


class Tower:
    """Local frame of a corner tower: u and v run inwards (into the town) from its outer corner, 0..8."""

    def __init__(self, x0, z0, sx, sz):
        self.x0, self.z0, self.sx, self.sz = x0, z0, sx, sz

    def at(self, u, v):
        x = self.x0 + u if self.sx > 0 else self.x0 + TOWER - 1 - u
        z = self.z0 + v if self.sz > 0 else self.z0 + TOWER - 1 - v
        return x, z

    def face(self, local):
        """World direction of a local one (east = +u, south = +v)."""
        if local in ("east", "west"):
            return local if self.sx > 0 else {"east": "west", "west": "east"}[local]
        return local if self.sz > 0 else {"south": "north", "north": "south"}[local]


# ------------------------------------------------------------------ small pieces
def walls(t, x0, z0, x1, z1, y0, y1, mat, corner=None, base=None):
    """Hollow box walls x0..x1, z0..z1 from y0 to y1; `mat` a state or f(x, y, z)."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if x in (x0, x1) or z in (z0, z1):
                for y in range(y0, y1 + 1):
                    if corner and x in (x0, x1) and z in (z0, z1):
                        st = corner
                    elif base and y == y0:
                        st = base
                    else:
                        st = mat(x, y, z) if callable(mat) else mat
                    t.set(x, y, z, st)


def slab_fill(t, x0, z0, x1, z1, y, mat):
    t.fill(x0, y, z0, x1, y, z1, mat)


def room(t, x0, z0, x1, z1, y0, y1):
    """Air inside the walls x0..x1, z0..z1 from y0 to y1."""
    t.fill(x0 + 1, y0, z0 + 1, x1 - 1, y1, z1 - 1, "air")


def window(t, x, y, z, side, kind="tall", glass="glass_pane", arch=None, shutter=None, box=None):
    """A window in the wall cell (x, z), facing out towards `side`: `tall` (2 panes), `slit` (1), `arched` (3 wide, 2
    tall and the arch: `arch` stairs, upside down, at its top corners). `shutter`: trapdoors open against the wall on
    both sides, outside; `box`: a ledge (state) under it, outside, with a flower pot on it."""
    dx, dz = OPEN_DIR[side]
    ax, az = (1, 0) if side in ("north", "south") else (0, 1)
    if kind == "arched":
        for k in (-1, 0, 1):
            for yy in (y, y + 1):
                t.set(x + ax * k, yy, z + az * k, glass)
        lo, hi = (("west", "east") if side in ("north", "south") else ("north", "south"))
        t.set(x - ax, y + 2, z - az, stairs(arch, lo, "top"))
        t.set(x + ax, y + 2, z + az, stairs(arch, hi, "top"))
        t.set(x, y + 2, z, glass)
        return
    for yy in ((y,) if kind == "slit" else (y, y + 1)):
        t.set(x, yy, z, glass)
    if shutter:
        for k in (-1, 1):
            for yy in ((y,) if kind == "slit" else (y, y + 1)):
                t.set(x + ax * k + dx, yy, z + az * k + dz, f"{shutter}[facing={side},half=bottom,open=true]")
    if box:
        t.set(x + dx, y - 1, z + dz, box)
        flowers = ("potted_red_tulip", "potted_poppy", "potted_cornflower", "potted_oxeye_daisy", "potted_allium")
        t.set(x + dx, y, z + dz, flowers[_h(x, y, z) % len(flowers)])


def chimney(t, x, z, y0, y1, mat="bricks", smoke=True):
    """A chimney column from y0 to y1 with a lit campfire on top (the smoke)."""
    t.fill(x, y0, z, x, y1, z, mat)
    if smoke:
        t.set(x, y1 + 1, z, "campfire[lit=true,signal_fire=false,facing=north]")


def sign_over(t, b, key=None):
    """The building's name on a sign over its door, outside."""
    (x, z), (dx, dz) = b.door(), OPEN_DIR[b.side]
    pieces.sign(t.set, x + dx, FLOOR + 3, z + dz, b.side, [text(key or f"edificio.{b.name}")], wood="crimson")


def door(t, b, y=FLOOR + 1, mat=DOOR, hinge="left"):
    (x, z) = b.door()
    t.set(x, y - 1, z, PAVE2)
    t.set(x, y, z, f"{mat}[facing={b.side},half=lower,hinge={hinge},open=false]")
    t.set(x, y + 1, z, f"{mat}[facing={b.side},half=upper,hinge={hinge},open=false]")
    if b.sign:
        sign_over(t, b)


def frame(t, x, y, z, facing, item, rot=0):
    """An item frame hanging on the wall behind (x, y, z), facing `facing` (out of the wall), with `item`."""
    n = pieces.item_frame(x, y, z, FACING_BYTE[facing], item)
    if rot:
        n["ItemRotation"] = B(rot)
    n["Tags"] = [HOUSE_TAG]
    n["Fixed"] = B(1)
    t.entity(x, y, z, n)


def table_row(t, x0, x1, z, y=FLOOR + 1, top=f"{WOOD_SLAB}[type=top]", bench=WSTAIRS, along="x"):
    """A long table (top slabs) with benches on both sides (stairs, backs out)."""
    for a in range(x0, x1 + 1):
        if along == "x":
            t.set(a, y, z, top)
            t.set(a, y, z - 1, stairs(bench, "north"))
            t.set(a, y, z + 1, stairs(bench, "south"))
        else:
            t.set(z, y, a, top)
            t.set(z - 1, y, a, stairs(bench, "west"))
            t.set(z + 1, y, a, stairs(bench, "east"))


def bed(t, x, z, facing, color="red", y=FLOOR + 1):
    """A bed whose head is at (x, z), pointing `facing` (towards the head)."""
    dx, dz = OPEN_DIR[facing]
    t.set(x, y, z, f"{color}_bed[facing={facing},part=head,occupied=false]")
    t.set(x - dx, y, z - dz, f"{color}_bed[facing={facing},part=foot,occupied=false]")
    t.beds.append((x, z))


def station(t, x, z, block, facing="north", y=FLOOR + 1):
    """A villager's workstation (recorded for the residents check)."""
    st = {"blast_furnace": f"blast_furnace[facing={facing},lit=false]", "smoker": f"smoker[facing={facing},lit=false]",
          "grindstone": f"grindstone[face=floor,facing={facing}]",
          "lectern": f"lectern[facing={facing},has_book=false,powered=false]",
          "stonecutter": f"stonecutter[facing={facing}]", "loom": f"loom[facing={facing}]",
          "barrel": "barrel[facing=up,open=false]", "composter": "composter[level=0]",
          "brewing_stand": "brewing_stand[has_bottle_0=false,has_bottle_1=false,has_bottle_2=false]",
          "cauldron": "cauldron"}.get(block, block)
    t.set(x, y, z, st, fill_nbt("barrel", "pesca") if block == "barrel" else None)
    t.stations.append((block, x, z))


def resident(t, prof, x, z, y=FLOOR + 1):
    """A villager of the house (Heraldia villager, its trade locked)."""
    n = villager(prof, THEME["vtype"])
    n["Rotation"] = [F(float(_h(x, y, z) % 360)), F(0.0)]
    n["Tags"] = n["Tags"] + [HOUSE_TAG]
    t.entity(x, y, z, n)
    t.villagers.append((prof, x, z))


def mob(t, x, y, z, kind, still=True, **extra):
    """An animal of the house: persistent, tagged and (`still`) without AI (horses in their stalls, the cats on the
    roofs: they cost nothing to tick, see LESSONS)."""
    n = {"id": "minecraft:" + kind, "PersistenceRequired": B(1), "Tags": [HOUSE_TAG],
         "Rotation": [F(float(_h(x, y, z) % 360)), F(0.0)]}
    if still:
        n["NoAI"] = B(1)
    n.update(extra)
    t.entity(x, y, z, n)


def bell_post(t, x, z, facing="north"):
    """A neighbourhood bell: on a stone post under a small roof, at the height of a villager's hand."""
    t.set(x, FLOOR + 1, z, "chiseled_stone_bricks")
    t.set(x, FLOOR + 2, z, f"bell[attachment=floor,facing={facing},powered=false]")
    t.bells.append((x, FLOOR + 2, z))


def flagpole(t, x, z, h=6, facing="south"):
    t.fill(x, FLOOR + 1, z, x, FLOOR + h, z, FENCE)
    t.set(x, FLOOR + h + 1, z, f"blue_banner[rotation={ROT[facing]}]", dict(BANNER))


def lamp_post(t, x, z, h=2, post="polished_deepslate_wall"):
    t.fill(x, FLOOR + 1, z, x, FLOOR + h, z, post)
    t.set(x, FLOOR + h + 1, z, "lantern[hanging=false]")


def wall_banner(t, x, y, z, facing):
    t.set(x, y, z, f"blue_wall_banner[facing={facing}]", dict(BANNER))


def flight(t, x, z, facing, y, steps, mat=WSTAIRS, fill=FLOORING, width=1):
    """A straight staircase: `steps` stairs from feet height y (the first step at y) climbing towards `facing`, solid
    under each step, headroom cleared above. Returns the landing cell (x, z) at the top (feet y + steps)."""
    dx, dz = OPEN_DIR[facing]
    ax, az = (abs(dz), abs(dx))
    for k in range(steps):
        for w in range(width):
            cx, cz = x + dx * k + ax * w, z + dz * k + az * w
            for yy in range(y, y + k):
                t.set(cx, yy, cz, fill)
            t.set(cx, y + k, cz, stairs(mat, facing))
            for yy in range(y + k + 1, y + k + 4):
                t.set(cx, yy, cz, "air")
    lx, lz = x + dx * steps, z + dz * steps
    for w in range(width):
        for yy in range(y + steps, y + steps + 3):
            t.set(lx + ax * w, yy, lz + az * w, "air")
    return lx, lz


def shell(t, b, wall, top, roof, corner=None, base=None, floor=FLOORING, ceiling=None, light=True):
    """The plain parts every recipe starts from: floor, walls up to `top`, a flat ceiling at `top` (if `ceiling`), its
    roof (callable(t, b, top)), the door. Each recipe adds its own façade and inside."""
    for x in range(b.x0, b.x1 + 1):
        for z in range(b.z0, b.z1 + 1):
            t.set(x, FLOOR, z, floor if b.x0 < x < b.x1 and b.z0 < z < b.z1 else (base or "stone_bricks"))
    walls(t, b.x0, b.z0, b.x1, b.z1, FLOOR + 1, top - 1, wall, corner=corner, base=base)
    room(t, b.x0, b.z0, b.x1, b.z1, FLOOR + 1, top - 1)
    slab_fill(t, b.x0, b.z0, b.x1, b.z1, top, ceiling or (wall if isinstance(wall, str) else base or "stone_bricks"))
    roof(t, b, top)
    if light:
        for x in range(b.x0 + 3, b.x1 - 1, 5):
            for z in range(b.z0 + 3, b.z1 - 1, 5):
                t.set(x, top - 1, z, LANTERN)
    door(t, b)


def gable(stairs_, slab, full, along="x", steep=False, gable_wall=None, over=1):
    def make(t, b, top):
        th = _theme(stairs_, slab, full, wall=gable_wall or full)
        build.gable_roof(t, th, b.x0, b.z0, b.x1, b.z1, top + 1, along=along, steep=steep, overhang=over,
                         gable_fill=gable_wall)
    return make


def hip(stairs_, slab, full, over=1):
    def make(t, b, top):
        build.hip_roof(t, _theme(stairs_, slab, full), b.x0, b.z0, b.x1, b.z1, top + 1, overhang=over)
    return make


def door_at(t, side, x, z, y=FLOOR + 1, mat=DOOR, hinge="left", sill=True):
    if sill:
        t.set(x, y - 1, z, PAVE2)
    t.set(x, y, z, f"{mat}[facing={side},half=lower,hinge={hinge},open=false]")
    t.set(x, y + 1, z, f"{mat}[facing={side},half=upper,hinge={hinge},open=false]")


# ------------------------------------------------------------------ the recipes (one per building)
def inn(t, b):
    """The inn (posada): two storeys, tuff below and calcite between crimson beams above, the upper one overhanging
    the plaza on corbels; a deepslate roof and two chimneys. Downstairs, the hall: the hearth, two long tables with
    mugs and candles, the bar with its kegs (the innkeeper's barrel) and the kitchen; a stair up to three rooms (a bed
    each) off a corridor and a sitting room."""
    x0, z0, x1, z1 = b.rect()
    mid, top = FLOOR + 5, FLOOR + 10        # the upper floor and the ceiling
    ux1 = x1 + 1                            # the upper storey overhangs the plaza by one
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, FLOORING if x0 < x < x1 and z0 < z < z1 else "polished_tuff")
    walls(t, x0, z0, x1, z1, FLOOR + 1, mid - 1, "tuff_bricks", corner="polished_deepslate", base="polished_tuff")
    room(t, x0, z0, x1, z1, FLOOR + 1, mid - 1)
    slab_fill(t, x0, z0, ux1, z1, mid, FLOORING)
    t.fill(x0, mid, z0, ux1, mid, z0, BEAM + "[axis=x]")
    t.fill(x0, mid, z1, ux1, mid, z1, BEAM + "[axis=x]")
    t.fill(ux1, mid, z0, ux1, mid, z1, BEAM + "[axis=z]")
    for z in range(z0, z1 + 1, 3):          # corbels under the overhang
        t.set(ux1, mid - 1, z, stairs("deepslate_brick_stairs", "west", "top"))

    def upper(x, y, z):
        post = x in (x0, ux1) and (z - z0) % 5 == 0 or z in (z0, z1) and (x - x0) % 5 == 0
        return BEAM + "[axis=y]" if post or x in (x0, ux1) and z in (z0, z1) else "calcite"
    walls(t, x0, z0, ux1, z1, mid + 1, top - 1, upper)
    room(t, x0, z0, ux1, z1, mid + 1, top - 1)
    slab_fill(t, x0, z0, ux1, z1, top, "polished_deepslate")
    build.gable_roof(t, _theme("deepslate_tile_stairs", "deepslate_tile_slab", "deepslate_tiles", "calcite"),
                     x0, z0, ux1, z1, top + 1, along="x", overhang=1, gable_fill="calcite")
    door(t, b)
    # windows: arched downstairs, shuttered with flower boxes upstairs
    window(t, x1, FLOOR + 2, z0 + 3, "east", "arched", arch="tuff_brick_stairs")
    for z in (z0 + 3, z1 - 3):
        window(t, x0, FLOOR + 2, z, "west", "tall")
    for x in (x0 + 4, x0 + 9, x0 + 14):
        window(t, x, FLOOR + 2, z0, "north", "arched", arch="tuff_brick_stairs")
    for x in (x0 + 4, x0 + 9):
        window(t, x, FLOOR + 2, z1, "south", "arched", arch="tuff_brick_stairs")
    for x in (x0 + 2, x0 + 7, x0 + 12, x0 + 17):
        for z, s in ((z0, "north"), (z1, "south")):
            window(t, x, mid + 2, z, s, "tall", shutter=TRAPDOOR, box="mud_brick_slab[type=top]")
    for z in (z0 + 2, z1 - 2):
        window(t, ux1, mid + 2, z, "east", "tall", shutter=TRAPDOOR, box="mud_brick_slab[type=top]")
    # the hearth in the west wall, its chimney up through the roof
    hz = (z0 + z1) // 2
    for z in (hz - 1, hz + 1):
        t.fill(x0 + 1, FLOOR + 1, z, x0 + 1, FLOOR + 3, z, "bricks")
    t.set(x0 + 1, FLOOR + 1, hz, "campfire[lit=true,signal_fire=false,facing=east]")
    t.set(x0 + 1, FLOOR + 2, hz, "air")
    t.set(x0 + 1, FLOOR + 3, hz, "bricks")
    chimney(t, x0, hz, FLOOR + 1, top + 6)
    t.fill(x0 + 1, FLOOR + 4, hz - 1, x0 + 1, mid - 1, hz + 1, "bricks")
    chimney(t, x0 + 13, z0, mid + 1, top + 5)
    # two long tables with mugs (empty pots) and candles
    for z in (z0 + 3, z0 + 7):
        table_row(t, x0 + 5, x0 + 10, z)
        for x in range(x0 + 5, x0 + 11):
            t.set(x, FLOOR + 2, z, ("flower_pot", "candle[candles=2,lit=true]", "flower_pot")[x % 3])
    # the bar: the counter, the kegs behind it and the innkeeper's barrel
    t.set(x0 + 13, FLOOR + 1, z0 + 3, "polished_deepslate")
    for x in range(x0 + 14, x1):
        t.set(x, FLOOR + 1, z0 + 3, "polished_deepslate_slab[type=top]")
    for x in range(x0 + 14, x1):
        t.set(x, FLOOR + 1, z0 + 1, "barrel[facing=south,open=false]", fill_nbt("barrel", "bodega"))
        if x % 2:
            t.set(x, FLOOR + 2, z0 + 1, "barrel[facing=south,open=false]", fill_nbt("barrel", "bodega"))
    t.set(x0 + 13, FLOOR + 1, z0 + 1, "polished_deepslate_slab[type=top]")
    t.set(x0 + 13, FLOOR + 2, z0 + 1, "brewing_stand[has_bottle_0=false,has_bottle_1=false,has_bottle_2=false]")
    station(t, x1 - 1, z0 + 2, "barrel")
    resident(t, "fisherman", x1 - 2, z0 + 2)
    t.set(x0 + 14, FLOOR + 2, z0 + 3, "flower_pot")
    t.set(x0 + 16, FLOOR + 2, z0 + 3, "candle[candles=3,lit=true]")
    # the kitchen corner (south-west): smoker, the stew in a cauldron, a pot, the worktop
    t.set(x0 + 1, FLOOR + 1, z1 - 1, "smoker[facing=east,lit=false]")
    t.set(x0 + 2, FLOOR + 1, z1 - 1, "water_cauldron[level=3]")
    t.set(x0 + 3, FLOOR + 1, z1 - 1, "decorated_pot[facing=north]")
    t.set(x0 + 4, FLOOR + 1, z1 - 1, "polished_deepslate_slab[type=top]")
    t.set(x0 + 4, FLOOR + 2, z1 - 1, "potted_red_mushroom")
    # the stair up along the south wall, climbing east, the opening in the upper floor above it
    sx = x1 - 6
    land = flight(t, sx, z1 - 1, "east", FLOOR + 1, mid - FLOOR, fill="tuff_bricks")
    t.set(land[0], mid, land[1], FLOORING)
    bed(t, x1 - 1, z1 - 1, "south", "green")              # the innkeeper's, under the landing, by the bar
    # upstairs: a corridor along z0 + 5, three rooms to the north (a bed each), the sitting room and the stairwell to
    # the south
    cz = z0 + 5
    t.fill(x0 + 1, mid + 1, cz - 1, ux1 - 1, top - 1, cz - 1, "calcite")
    for px in (x0 + 6, x0 + 12):
        t.fill(px, mid + 1, z0 + 1, px, top - 1, cz - 2, "calcite")
    for dx_ in (x0 + 3, x0 + 9, x0 + 15):
        door_at(t, "south", dx_, cz - 1, mid + 1, sill=False)
    # the rooms upstairs: the card room, the store of kegs and sacks, the parlour (nobody sleeps upstairs: a free bed
    # would let the villagers breed, and a child takes the nearest free bed, perhaps a resident's)
    t.set(x0 + 2, mid + 1, z0 + 2, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 3, mid + 1, z0 + 2, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 2, mid + 2, z0 + 2, "candle[candles=2,lit=true]")
    for x in (x0 + 2, x0 + 3):
        t.set(x, mid + 1, z0 + 1, stairs(WSTAIRS, "north"))
    for x in range(x0 + 7, x0 + 12):
        t.set(x, mid + 1, z0 + 1, "barrel[facing=south,open=false]", fill_nbt("barrel", "despensa"))
        if x % 2:
            t.set(x, mid + 2, z0 + 1, "barrel[facing=south,open=false]", fill_nbt("barrel", "despensa"))
    t.set(x0 + 14, mid + 1, z0 + 1, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 14, mid + 2, z0 + 1, "potted_cornflower")
    t.set(x0 + 15, mid + 1, z0 + 1, stairs(WSTAIRS, "north"))
    for rx in (x0 + 2, x0 + 8, x0 + 14):
        t.set(rx + 2, mid + 1, z0 + 3, "red_carpet")
        t.set(rx + 1, mid + 1, z0 + 3, "red_carpet")
    for x in range(x0 + 2, x0 + 9):
        t.set(x, mid + 1, z1 - 2, "green_carpet")
    t.set(x0 + 1, mid + 1, z1 - 1, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 1, mid + 2, z1 - 1, "potted_lily_of_the_valley")
    t.set(x0 + 2, mid + 1, z1 - 1, stairs(WSTAIRS, "south"))
    t.set(x0 + 4, mid + 1, z1 - 1, stairs(WSTAIRS, "south"))
    for x in (x0 + 3, x0 + 9, x0 + 15):
        t.set(x, top - 1, cz, LANTERN)
        t.set(x, top - 1, z0 + 2, LANTERN)
    for x in (x0 + 4, x0 + 9, x0 + 14):
        t.set(x, mid - 1, hz, LANTERN)
    frame(t, x0 + 9, FLOOR + 3, z0 + 1, "south", "goat_horn")
    frame(t, x0 + 1, FLOOR + 3, z0 + 3, "east", "honey_bottle")
    # a cat on the ridge
    ridge = top + 1 + (z1 - z0 + 2) // 2
    mob(t, x0 + 4, ridge + 0.5, hz, "cat", variant="minecraft:black", Sitting=B(1))


def chapel(t, b):
    """The chapel: a tall nave of stone with buttresses and a steep copper roof, a rose window over the door, stained
    glass in arched windows; inside, pews facing the altar with its candles, the cleric's brewing stand and, behind a
    wall, the vestry with the cleric's bed."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 9
    shell(t, b, "stone_bricks", top, gable(_cu("weathered") + "_stairs", _cu("weathered") + "_slab", f"waxed_weathered_cut_copper",
                                            along="x", gable_wall="stone_bricks"),
          corner="chiseled_stone_bricks", base="polished_andesite", floor="polished_andesite", light=False)
    for x in range(x0 + 1, x1):
        for z in range(z0 + 1, z1):
            if (x + z) % 2:
                t.set(x, FLOOR, z, "stone_bricks")
    for x in (x0 + 3, x0 + 7, x0 + 11):     # buttresses
        for z, f in ((z0 - 1, "north"), (z1 + 1, "south")):
            t.fill(x, FLOOR + 1, z, x, FLOOR + 5, z, "stone_bricks")
            t.set(x, FLOOR + 6, z, stairs("stone_brick_stairs", {"north": "south", "south": "north"}[f]))
            t.set(x, FLOOR, z, "polished_andesite")
    for x in (x0 + 5, x0 + 9):
        for z, s in ((z0, "north"), (z1, "south")):
            window(t, x, FLOOR + 3, z, s, "arched", glass="yellow_stained_glass_pane", arch="stone_brick_stairs")
            t.set(x, FLOOR + 6, z, "light_blue_stained_glass_pane")
    cz = (z0 + z1) // 2
    for dz, dy in ((0, 0), (-1, 1), (1, 1), (0, 2), (-1, -1), (1, -1), (0, -2)):   # the rose window
        t.set(x0, FLOOR + 7 + dy, cz + dz, "light_blue_stained_glass" if (dz, dy) == (0, 0) else "yellow_stained_glass")
    # inside: the altar at the east end, the cleric's stand, the pews, the lights
    t.set(x1 - 2, FLOOR + 1, cz, "chiseled_stone_bricks")
    t.set(x1 - 2, FLOOR + 1, cz - 1, stairs("stone_brick_stairs", "north", "top"))
    t.set(x1 - 2, FLOOR + 1, cz + 1, stairs("stone_brick_stairs", "south", "top"))
    t.set(x1 - 2, FLOOR + 2, cz, "candle[candles=4,lit=true]")
    t.set(x1 - 2, FLOOR + 2, cz - 1, "candle[candles=2,lit=true]")
    t.set(x1 - 2, FLOOR + 2, cz + 1, "candle[candles=2,lit=true]")
    wall_banner(t, x1 - 1, FLOOR + 4, cz, "west")
    for z in range(cz - 1, cz + 2):
        t.set(x1 - 4, FLOOR, z, "polished_deepslate")
    station(t, x1 - 1, z0 + 1, "brewing_stand")
    resident(t, "cleric", x1 - 2, z0 + 2)
    for x in range(x0 + 3, x1 - 5, 2):
        for z in list(range(z0 + 2, cz - 1)) + list(range(cz + 2, z1 - 1)):
            t.set(x, FLOOR + 1, z, stairs(WSTAIRS, "west"))
    for x in range(x0 + 1, x1 - 4):
        t.set(x, FLOOR + 1, cz, "red_carpet")
    for x in range(x0 + 2, x1 - 1, 4):
        for z in (z0 + 3, z1 - 3):
            t.set(x, top - 1, z, "iron_chain[axis=y]")
            t.set(x, top - 2, z, LANTERN)
    # the vestry (north-east corner): a wall with a door, the cleric's bed, a chest
    vx = x1 - 4
    t.fill(vx, FLOOR + 1, z1 - 4, vx, FLOOR + 4, z1 - 1, "stone_bricks")
    t.fill(vx, FLOOR + 1, z1 - 4, x1 - 1, FLOOR + 4, z1 - 4, "stone_bricks")
    t.fill(vx + 1, FLOOR + 5, z1 - 3, x1 - 1, FLOOR + 5, z1 - 1, "stone_bricks")
    door_at(t, "south", vx + 2, z1 - 4, sill=False)
    bed(t, x1 - 1, z1 - 2, "east", "white")
    t.set(vx + 1, FLOOR + 1, z1 - 1, "chest[facing=north,type=single]", fill_nbt("chest", "templo"))
    t.set(vx + 2, FLOOR + 4, z1 - 2, LANTERN)
    window(t, x1 - 2, FLOOR + 2, z1, "south", "slit", glass="yellow_stained_glass_pane")
    # a small belfry spire over the west gable (decorative: no bell, the town's bell is the plaza's)
    t.fill(x0, top + 1, cz - 1, x0 + 2, top + 10, cz + 1, "stone_bricks")
    for y in (top + 8, top + 9):                  # the belfry's openings, on its four faces
        for x, z in ((x0 + 1, cz - 1), (x0 + 1, cz + 1), (x0, cz), (x0 + 2, cz)):
            t.set(x, y, z, "air")
    build.spire(t, x0 + 1, cz, top + 11, 1, _cu("oxidized") + "_stairs", COPPER)
    t.set(x0 + 1, top + 14, cz, "lightning_rod[facing=up]")


def library(t, b):
    """The library: dark deepslate walls under a copper hip roof, tall arched windows. Inside, walls of bookshelves,
    the two librarians' lecterns at the reading tables, a reading nook with armchairs, a carpet, and behind a wall the
    bedroom with their two beds."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 6
    shell(t, b, "deepslate_bricks", top, hip(_cu("exposed") + "_stairs", _cu("exposed") + "_slab", "waxed_exposed_cut_copper"),
          corner="polished_deepslate", base="cobbled_deepslate", floor=FLOORING, light=False)
    for x in (x0 + 3, x0 + 7, x0 + 11):
        window(t, x, FLOOR + 2, z0, "north", "arched", arch="deepslate_brick_stairs")
    for z in (z0 + 3, z1 - 3):
        window(t, x1, FLOOR + 2, z, "east", "arched", arch="deepslate_brick_stairs")
    window(t, x0 + 10, FLOOR + 2, z1, "south", "arched", arch="deepslate_brick_stairs")
    window(t, x0, FLOOR + 2, z0 + 3, "west", "tall")
    # bookshelves along the north wall (between the windows) and the west wall, two high, a cornice above
    for x in range(x0 + 1, x1):
        if all(abs(x - w) > 1 for w in (x0 + 3, x0 + 7, x0 + 11)):
            for y in (FLOOR + 1, FLOOR + 2, FLOOR + 3):
                t.set(x, y, z0 + 1, "bookshelf")
    for z in range(z0 + 5, z1 - 4):
        for y in (FLOOR + 1, FLOOR + 2, FLOOR + 3):
            t.set(x0 + 1, y, z, "bookshelf")
    # the bedroom (south-west): a wall with a door, two beds, a chest
    bx = x1 - 5
    t.fill(bx, FLOOR + 1, z1 - 4, x1 - 1, top - 1, z1 - 4, "deepslate_bricks")
    t.fill(bx, FLOOR + 1, z1 - 4, bx, top - 1, z1 - 1, "deepslate_bricks")
    door_at(t, "north", x1 - 2, z1 - 4, sill=False)
    bed(t, x1 - 1, z1 - 2, "east", "blue")
    bed(t, bx + 1, z1 - 1, "south", "blue")
    t.set(bx + 2, FLOOR + 1, z1 - 1, "chest[facing=north,type=single]", fill_nbt("chest", "casa"))
    t.set(x1 - 3, top - 1, z1 - 2, LANTERN)
    # two reading tables with the lecterns
    for lx in (x0 + 8, x0 + 12):
        station(t, lx, z0 + 4, "lectern", facing="south")
        resident(t, "librarian", lx + 1, z0 + 4)
        t.set(lx - 1, FLOOR + 1, z0 + 6, f"{WOOD_SLAB}[type=top]")
        t.set(lx - 2, FLOOR + 1, z0 + 6, f"{WOOD_SLAB}[type=top]")
        t.set(lx - 1, FLOOR + 2, z0 + 6, "candle[candles=1,lit=true]")
        t.set(lx - 1, FLOOR + 1, z0 + 5, stairs(WSTAIRS, "north"))
        t.set(lx - 2, FLOOR + 1, z0 + 5, stairs(WSTAIRS, "north"))
    # the reading nook (south-east corner): two armchairs, a low table, a carpet, a plant
    for x in range(x0 + 2, x0 + 6):
        for z in range(z1 - 3, z1):
            t.set(x, FLOOR + 1, z, "blue_carpet")
    t.set(x0 + 2, FLOOR + 1, z1 - 1, stairs(WSTAIRS, "south"))
    t.set(x0 + 4, FLOOR + 1, z1 - 1, stairs(WSTAIRS, "south"))
    t.set(x0 + 3, FLOOR + 1, z1 - 1, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 3, FLOOR + 2, z1 - 1, "potted_fern")
    for x in (x0 + 9, x0 + 12):
        t.set(x, top - 1, z0 + 6, LANTERN)
    t.set(x0 + 3, top - 1, z1 - 3, LANTERN)
    for x, item in ((x0 + 5, "writable_book"), (x0 + 9, "book"), (x0 + 13, "feather")):
        frame(t, x, FLOOR + 4, z0 + 1, "south", item)


def butcher(t, b):
    """The butcher: mud brick below and white terracotta above, a brick gable; over the door a red-and-white awning
    on posts with the counter below. Inside, the meat hangs in frames on the wall, the chopping table, the smoker (the
    butcher's) under the smokehouse chimney; behind, the tannery with the leatherworker's cauldron and their beds."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5

    def wall(x, y, z):
        return "mud_bricks" if y <= FLOOR + 2 else "white_terracotta"
    shell(t, b, wall, top, gable("brick_stairs", "brick_slab", "bricks", along="z", gable_wall="white_terracotta"),
          corner=BEAM + "[axis=y]", base="packed_mud", light=False)
    cz = b.along
    # the awning: alternating red and white slabs on two posts
    for z in range(z0 + 1, z1):
        for x in (x1 + 1, x1 + 2):
            t.set(x, FLOOR + 4, z, "red_nether_brick_slab[type=bottom]" if z % 2 else "smooth_quartz_slab[type=bottom]")
    for z in (z0 + 1, z1 - 1):
        t.fill(x1 + 2, FLOOR + 1, z, x1 + 2, FLOOR + 3, z, FENCE)
    for z in (z0 + 2, z0 + 3, z1 - 3, z1 - 2):
        t.set(x1 + 1, FLOOR + 1, z, "polished_andesite_slab[type=top]")
    t.set(x1 + 1, FLOOR + 2, z0 + 2, "decorated_pot[facing=east]")
    t.set(x1 + 1, FLOOR + 2, z1 - 2, "decorated_pot[facing=east]")
    for z in (z0 + 2, z1 - 2):
        window(t, x1, FLOOR + 2, z, "east", "tall")
    for x in (x0 + 3, x0 + 7):
        window(t, x, FLOOR + 2, z1, "south", "tall", shutter=TRAPDOOR)
    window(t, x0, FLOOR + 2, z0 + 3, "west", "slit")
    # the shop: meat on the north wall, the chopping table, the smoker and its chimney
    for x, item in ((x0 + 2, "beef"), (x0 + 3, "porkchop"), (x0 + 4, "mutton"), (x0 + 5, "chicken"), (x0 + 6, "rabbit")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    for x in range(x0 + 3, x0 + 7):
        t.set(x, FLOOR + 1, z0 + 4, "polished_andesite_slab[type=top]")
    station(t, x0 + 1, z0 + 2, "smoker", facing="east")
    resident(t, "butcher", x0 + 2, z0 + 2)
    chimney(t, x0, z0 + 2, FLOOR + 1, top + 5)
    t.set(x0 + 1, top - 1, z0 + 6, LANTERN)
    t.set(x0 + 5, top - 1, z0 + 6, LANTERN)
    # the tannery behind (z1 - 3 .. z1 - 1): the wall with its door, the cauldron, the hides, two beds
    t.fill(x0 + 1, FLOOR + 1, z1 - 4, x1 - 1, top - 1, z1 - 4, "mud_bricks")
    door_at(t, "south", x0 + 5, z1 - 4, sill=False)
    station(t, x1 - 1, z1 - 1, "cauldron")
    resident(t, "leatherworker", x1 - 2, z1 - 1)
    bed(t, x0 + 1, z1 - 3, "west", "brown")
    bed(t, x0 + 1, z1 - 1, "west", "brown")
    for x, item in ((x1 - 2, "leather"), (x1 - 3, "rabbit_hide")):
        frame(t, x, FLOOR + 3, z1 - 1, "north", item)
    t.set(x0 + 4, top - 1, z1 - 2, LANTERN)
    # a cat on the awning
    mob(t, x1 + 1, FLOOR + 4.5, z0 + 4, "cat", variant="minecraft:red", Sitting=B(1))


def stable(t, b):
    """The stable: stone below and crimson beams, a brick gable along its length. Three stalls with their hay and
    water along the west wall (two horses and a donkey, still in their stalls), the aisle, and the saddler's corner:
    the leatherworker's cauldron, the tack in frames, the saddler's bed."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5

    def wall(x, y, z):
        return "stone_bricks" if y <= FLOOR + 1 else ("stripped_crimson_hyphae" if (x + z) % 4 == 0 else "mud_bricks")
    shell(t, b, wall, top, gable("brick_stairs", "brick_slab", "bricks", along="z", gable_wall="mud_bricks"),
          corner=BEAM + "[axis=y]", base="stone_bricks", floor="polished_andesite", light=False)
    for x in range(x0 + 1, x0 + 4):            # the stalls' floor
        for z in range(z0 + 1, z1):
            t.set(x, FLOOR, z, "coarse_dirt")
    for z in (z0 + 4, z0 + 8):
        t.fill(x0 + 1, FLOOR + 1, z, x0 + 3, FLOOR + 1, z, FENCE)
    for z in range(z0 + 1, z1):
        if z not in (z0 + 4, z0 + 8):
            t.set(x0 + 4, FLOOR + 1, z, FENCE if z % 3 else f"{GATE}[facing=east,in_wall=false,open=false,powered=false]")
        else:
            t.set(x0 + 4, FLOOR + 1, z, FENCE)
    for z0_, (kind, extra) in zip((z0 + 2, z0 + 6, z0 + 9), (("horse", {"Variant": 0}), ("horse", {"Variant": 1026}),
                                                           ("donkey", {}))):
        t.set(x0 + 1, FLOOR + 1, z0_ - 1, "hay_block[axis=y]")
        t.set(x0 + 1, FLOOR + 1, z0_ + 1, "water_cauldron[level=3]")
        mob(t, x0 + 2, FLOOR + 1, z0_, kind, **extra)
    for z in (z0 + 2, z0 + 6, z0 + 10):
        window(t, x0, FLOOR + 3, z, "west", "slit")
    window(t, x0 + 6, FLOOR + 2, z0, "north", "tall", shutter=TRAPDOOR)
    window(t, x0 + 6, FLOOR + 2, z1, "south", "tall", shutter=TRAPDOOR)
    station(t, x1 - 1, z1 - 1, "cauldron")
    resident(t, "leatherworker", x1 - 2, z1 - 1)
    bed(t, x1 - 1, z0 + 1, "north", "brown")
    t.set(x1 - 1, FLOOR + 1, z0 + 3, "chest[facing=west,type=single]", fill_nbt("chest", "granja"))
    for z, item in ((z0 + 5, "saddle"), (z0 + 6, "lead"), (z0 + 9, "leather")):
        frame(t, x1 - 1, FLOOR + 3, z, "west", item)
    for z in (z0 + 3, z0 + 7):
        t.set(x0 + 5, top - 1, z, LANTERN)
        t.set(x0 + 2, top - 1, z, LANTERN)
    t.set(x0 + 5, top - 1, z1 - 1, LANTERN)


def herbalist(t, b):
    """The herbalist: mud brick under a steep weathered-copper gable, shutters and flower boxes. Inside, shelves of
    potted herbs, the brewing stand (the herbalist is a cleric), a cauldron, the jars in frames and the bed."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5
    shell(t, b, "mud_bricks", top, gable(_cu("weathered") + "_stairs", _cu("weathered") + "_slab", "waxed_weathered_cut_copper",
                                         along="x", steep=True, gable_wall="mud_bricks"),
          corner=BEAM + "[axis=y]", base="packed_mud", light=False)
    for x in (x0 + 2, x1 - 2):
        window(t, x, FLOOR + 2, z1, "south", "tall", shutter=TRAPDOOR, box="mud_brick_slab[type=top]")
    for x in (x0 + 3, x1 - 3):
        window(t, x, FLOOR + 2, z0, "north", "tall", shutter=TRAPDOOR, box="mud_brick_slab[type=top]")
    window(t, x0, FLOOR + 2, z0 + 4, "west", "tall")
    window(t, x1, FLOOR + 2, z0 + 4, "east", "tall")
    herbs = ("potted_fern", "potted_azure_bluet", "potted_allium", "potted_blue_orchid", "potted_red_mushroom",
             "potted_brown_mushroom", "potted_oxeye_daisy")
    for i, z in enumerate(range(z0 + 2, z1 - 1)):
        t.set(x0 + 1, FLOOR + 1, z, f"{WOOD_SLAB}[type=top]")
        t.set(x0 + 1, FLOOR + 2, z, herbs[i % len(herbs)])
    station(t, x1 - 2, z0 + 1, "brewing_stand")
    resident(t, "cleric", x1 - 3, z0 + 2)
    t.set(x1 - 1, FLOOR + 1, z0 + 1, "water_cauldron[level=3]")
    t.set(x1 - 4, FLOOR + 1, z0 + 1, f"{WOOD_SLAB}[type=top]")
    t.set(x1 - 4, FLOOR + 2, z0 + 1, "decorated_pot[facing=south]")
    bed(t, x1 - 1, z1 - 2, "east", "green")
    t.set(x1 - 1, FLOOR + 1, z1 - 4, "chest[facing=west,type=single]", fill_nbt("chest", "granja"))
    for x, item in ((x0 + 4, "glass_bottle"), (x0 + 5, "nether_wart"), (x0 + 6, "glow_berries")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    t.set(x0 + 4, top - 1, z0 + 4, LANTERN)
    t.set(x1 - 3, top - 1, z0 + 5, LANTERN)
    chimney(t, x1, z0 + 1, FLOOR + 1, top + 6)


def bakery(t, b):
    """The bakery: terracotta between brick corners, a mud brick gable, the domed oven in the back with its chimney,
    the counter with the bread, sacks of flour (barrels), the baker's composter (the baker is a farmer: it sells bread)
    and its bed."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5
    shell(t, b, "terracotta", top, gable("mud_brick_stairs", "mud_brick_slab", "mud_bricks", along="x", gable_wall="terracotta"),
          corner="bricks", base="bricks", light=False)
    for x in (x0 + 2, x1 - 2):
        window(t, x, FLOOR + 2, z1, "south", "arched", arch="brick_stairs")
    window(t, x0, FLOOR + 2, z0 + 5, "west", "tall", shutter=TRAPDOOR)
    window(t, x1, FLOOR + 2, z0 + 5, "east", "tall", shutter=TRAPDOOR)
    # the oven against the north wall: a brick mass with two furnace mouths and its chimney
    cx = (x0 + x1) // 2
    t.fill(cx - 2, FLOOR + 1, z0 + 1, cx + 2, FLOOR + 2, z0 + 2, "bricks")
    t.fill(cx - 1, FLOOR + 3, z0 + 1, cx + 1, FLOOR + 3, z0 + 1, "bricks")
    for x in (cx - 1, cx + 1):
        t.set(x, FLOOR + 1, z0 + 2, "furnace[facing=south,lit=false]")
    t.set(cx, FLOOR + 3, z0 + 2, stairs("brick_stairs", "north"))
    chimney(t, cx, z0, FLOOR + 1, top + 5)
    # the counter with bread and a cake
    for x in range(x0 + 2, x0 + 6):
        t.set(x, FLOOR + 1, z0 + 6, "smooth_stone_slab[type=top]")
    t.set(x0 + 3, FLOOR + 2, z0 + 6, "cake[bites=2]")
    for x, item in ((x1 - 2, "bread"), (x1 - 3, "cookie")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    for z in (z0 + 7, z0 + 8):
        t.set(x1 - 1, FLOOR + 1, z, "barrel[facing=up,open=false]", fill_nbt("barrel", "molino"))
    t.set(x1 - 1, FLOOR + 2, z0 + 8, "barrel[facing=up,open=false]", fill_nbt("barrel", "molino"))
    station(t, x0 + 1, z0 + 3, "composter")
    resident(t, "farmer", x0 + 2, z0 + 4)
    bed(t, x0 + 1, z1 - 1, "west", "yellow")
    t.set(cx, top - 1, z0 + 5, LANTERN)


def granary(t, b):
    """The farm's granary and the farmer's cottage: stone under a brick hip, the farmer's composter just inside the
    door (the farmland is a few steps away), sacks (barrels), hay and the bed."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5
    shell(t, b, "stone_bricks", top, hip("brick_stairs", "brick_slab", "bricks"),
          corner="polished_andesite", base="polished_andesite", floor=FLOORING, light=False)
    station(t, b.along + 1, z0 + 1, "composter")
    resident(t, "farmer", b.along + 1, z0 + 2)
    bed(t, x1 - 1, z1 - 1, "south", "yellow")
    t.set(x0 + 1, FLOOR + 1, z1 - 1, "hay_block[axis=y]")
    t.set(x0 + 1, FLOOR + 2, z1 - 1, "hay_block[axis=y]")
    t.set(x0 + 2, FLOOR + 1, z1 - 1, "hay_block[axis=x]")
    t.set(x0 + 1, FLOOR + 1, z1 - 2, "barrel[facing=up,open=false]", fill_nbt("barrel", "granja"))
    frame(t, x0 + 3, FLOOR + 3, z1 - 1, "north", "wheat")
    window(t, x0, FLOOR + 2, z0 + 2, "west", "tall", shutter=TRAPDOOR)
    window(t, x1, FLOOR + 2, z0 + 2, "east", "tall", shutter=TRAPDOOR)
    t.set(b.along, top - 1, z0 + 3, LANTERN)


def cartographer(t, b):
    """The cartographer: brick with calcite quoins under an exposed-copper gable, arched windows. Inside, the
    cartography table, a map table, maps, a compass and a spyglass in frames on the walls, a globe of sorts (a
    lodestone on a stand), and the bedroom at the back."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5
    shell(t, b, "bricks", top, gable(_cu("exposed") + "_stairs", _cu("exposed") + "_slab", "waxed_exposed_cut_copper",
                                     along="x", gable_wall="bricks"),
          corner="calcite", base="polished_andesite", light=False)
    for x in (x0 + 3, x1 - 3):
        window(t, x, FLOOR + 2, z1, "south", "arched", arch="brick_stairs")
    for x in (x0 + 3, x0 + 7):
        window(t, x, FLOOR + 2, z0, "north", "tall", shutter=TRAPDOOR)
    window(t, x0, FLOOR + 2, z0 + 5, "west", "tall")
    station(t, x0 + 1, z0 + 1, "cartography_table")
    resident(t, "cartographer", x0 + 2, z0 + 2)
    for x in range(x0 + 3, x0 + 6):
        t.set(x, FLOOR + 1, z0 + 5, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 4, FLOOR + 2, z0 + 5, "candle[candles=1,lit=true]")
    t.set(x0 + 1, FLOOR + 1, z0 + 7, "lodestone")
    for x, item in ((x0 + 3, "map"), (x0 + 4, "compass"), (x0 + 5, "map"), (x0 + 6, "spyglass")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    for z, item in ((z0 + 3, "map"), (z0 + 4, "recovery_compass"), (z0 + 6, "map")):
        frame(t, x0 + 1, FLOOR + 3, z, "east", item)
    # the bedroom (east end): a wall with a door, the bed, a chest
    px = x1 - 4
    t.fill(px, FLOOR + 1, z0 + 1, px, top - 1, z1 - 1, "bricks")
    door_at(t, "west", px, z0 + 4, sill=False)
    bed(t, x1 - 1, z0 + 1, "north", "light_blue")
    t.set(x1 - 1, FLOOR + 1, z0 + 3, "chest[facing=west,type=single]", fill_nbt("chest", "casa"))
    t.set(x1 - 2, top - 1, z0 + 5, LANTERN)
    t.set(x0 + 4, top - 1, z0 + 3, LANTERN)
    t.set(x0 + 4, top - 1, z1 - 2, LANTERN)


def weaver(t, b):
    """The weaver: andesite with crimson beams and a deepslate hip roof. The shepherd's loom, bolts of cloth (wool)
    stacked on the walls, finished banners hung on the wall, the bed; outside, the sheep's pen."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5

    def wall(x, y, z):
        return BEAM + "[axis=y]" if (x - x0) % 5 == 0 and z in (z0, z1) or (z - z0) % 5 == 0 and x in (x0, x1) \
            else "polished_andesite"
    shell(t, b, wall, top, hip("deepslate_tile_stairs", "deepslate_tile_slab", "deepslate_tiles"),
          corner=BEAM + "[axis=y]", base="andesite", light=False)
    for z in (z0 + 2, z1 - 2):
        window(t, x0, FLOOR + 2, z, "west", "tall", shutter=TRAPDOOR, box="mud_brick_slab[type=top]")
    for x in (x0 + 3, x1 - 3):
        window(t, x, FLOOR + 2, z0, "north", "tall")
    station(t, x0 + 2, z0 + 1, "loom", facing="south")
    resident(t, "shepherd", x0 + 3, z0 + 2)
    colors = ("red", "yellow", "blue", "white", "green", "light_blue")
    for i, z in enumerate(range(z0 + 1, z1 - 3)):
        t.set(x1 - 1, FLOOR + 1, z, f"{colors[i % len(colors)]}_wool")
        if i % 2 == 0:
            t.set(x1 - 1, FLOOR + 2, z, f"{colors[(i + 2) % len(colors)]}_wool")
    for x, c in ((x0 + 5, "red"), (x0 + 7, "blue")):
        t.set(x, FLOOR + 3, z0 + 1, f"{c}_wall_banner[facing=south]")
    bed(t, x1 - 1, z1 - 1, "south", "white")
    t.set(x0 + 1, FLOOR + 1, z1 - 1, "chest[facing=east,type=single]", fill_nbt("chest", "mercado"))
    for x in range(x0 + 3, x0 + 7):
        t.set(x, FLOOR + 1, z1 - 3, "white_carpet")
    frame(t, x0 + 1, FLOOR + 3, z0 + 5, "east", "shears")
    t.set(x0 + 5, top - 1, z0 + 5, LANTERN)
    # the sheep's pen outside, to the south (two sheep standing in it)
    px0, pz0, px1, pz1 = x0, z1 + 4, x1, z1 + 8
    for x in range(px0, px1 + 1):
        for z in range(pz0, pz1 + 1):
            if x in (px0, px1) or z in (pz0, pz1):
                t.set(x, FLOOR + 1, z, FENCE)
    t.set(px0, FLOOR + 1, (pz0 + pz1) // 2, f"{GATE}[facing=west,in_wall=false,open=false,powered=false]")
    for i, c in enumerate((0, 15)):
        mob(t, px0 + 3 + 4 * i, FLOOR + 1, pz0 + 2, "sheep", Color=B(c))


def smithy(t, b):
    """The smithy: polished blackstone under a deepslate gable, a tall forge with its chimney smoking; inside, the
    blast furnace (the armorer's) by the forge, the smithing table (the toolsmith's), two anvils, the coal bin and
    the smiths' bedroom; the back door opens on the anvil yard with the grindstone (the weaponsmith's), a quenching
    trough and a rack of weapons."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 6
    shell(t, b, "polished_blackstone_bricks", top, gable("deepslate_tile_stairs", "deepslate_tile_slab", "deepslate_tiles",
                                                        along="x", gable_wall="polished_blackstone_bricks"),
          corner="polished_basalt[axis=y]", base="blackstone", floor="polished_blackstone", light=False)
    door_at(t, "south", b.along, z1)
    for x in (x0 + 3, x1 - 3):
        window(t, x, FLOOR + 2, z0, "north", "tall")
    for z in (z0 + 3,):
        window(t, x0, FLOOR + 2, z, "west", "tall")
    # the forge against the east wall: bricks, a lava cauldron in its mouth, the blast furnace beside it
    fz = z0 + 3
    t.fill(x1 - 2, FLOOR + 1, fz - 1, x1 - 1, FLOOR + 3, fz + 1, "bricks")
    t.set(x1 - 2, FLOOR + 1, fz, "lava_cauldron")
    t.set(x1 - 2, FLOOR + 2, fz, "air")
    t.set(x1 - 2, FLOOR + 3, fz, stairs("brick_stairs", "east", "top"))
    t.fill(x1 - 1, FLOOR + 4, fz - 1, x1 - 1, top - 1, fz + 1, "bricks")
    chimney(t, x1, fz, FLOOR + 1, top + 6)
    station(t, x1 - 1, fz + 2, "blast_furnace", facing="west")
    resident(t, "armorer", x1 - 2, fz + 2)
    station(t, x0 + 1, z0 + 1, "smithing_table")
    resident(t, "toolsmith", x0 + 2, z0 + 2)
    t.set(x0 + 4, FLOOR + 1, z0 + 3, "anvil[facing=east]")
    t.set(x0 + 6, FLOOR + 1, z0 + 3, "chipped_anvil[facing=east]")
    t.set(x0 + 1, FLOOR + 1, z0 + 4, "water_cauldron[level=3]")
    for x, item in ((x0 + 3, "iron_pickaxe"), (x0 + 4, "iron_axe"), (x0 + 5, "iron_shovel"), (x0 + 6, "iron_hoe")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    # the bedroom at the back (z1 - 3 .. z1 - 1): a wall with a door, three beds, the coal bin
    t.fill(x0 + 1, FLOOR + 1, z1 - 4, x1 - 1, top - 1, z1 - 4, "polished_blackstone_bricks")
    door_at(t, "south", x0 + 7, z1 - 4, sill=False)
    for x in (x0 + 1, x0 + 3, x0 + 5):
        bed(t, x, z1 - 1, "south", "gray")
    t.fill(x1 - 2, FLOOR + 1, z1 - 2, x1 - 1, FLOOR + 1, z1 - 1, "coal_block")
    t.set(x1 - 2, FLOOR + 2, z1 - 1, "coal_block")
    t.set(x1 - 3, FLOOR + 1, z1 - 1, "polished_blackstone_slab[type=bottom]")
    t.set(x0 + 4, top - 1, z1 - 2, LANTERN)
    for x in (x0 + 3, x0 + 8):
        t.set(x, top - 1, z0 + 5, LANTERN)
    # the anvil yard behind: a low wall with a gap to the west, the grindstone, the trough, the weapon rack
    yz0, yz1 = z1 + 1, z1 + 7
    for x in range(x0, x1 + 1):
        for z in range(yz0, yz1 + 1):
            t.set(x, FLOOR, z, "polished_blackstone" if (x + z) % 3 else "cobblestone")
            if x in (x0, x1) or z == yz1:
                if not (x == x0 and yz0 + 2 <= z <= yz0 + 4):
                    t.set(x, FLOOR + 1, z, "polished_blackstone_wall")
    station(t, x1 - 3, yz0 + 3, "grindstone", facing="west")
    resident(t, "weaponsmith", x1 - 4, yz0 + 3)
    t.set(x1 - 1, FLOOR + 1, yz0 + 1, "water_cauldron[level=3]")
    t.set(x0 + 3, FLOOR + 1, yz1 - 1, "anvil[facing=east]")
    for x, item in ((x0 + 5, "iron_sword"), (x0 + 6, "shield"), (x0 + 7, "crossbow"), (x0 + 8, "iron_sword")):
        t.set(x, FLOOR + 2, yz1, "polished_blackstone_bricks")
        frame(t, x, FLOOR + 2, yz1 - 1, "north", item)
    for x in (x0 + 2, x1 - 2):
        t.set(x, FLOOR + 2, yz1, "lantern[hanging=false]")


def workshop(t, b):
    """The workshop: tuff and tuff bricks under a mud brick gable. The fletcher's table and the mason's stonecutter,
    bows and arrows in frames, a workbench, stacked stone, and the bedroom with two beds."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5

    def wall(x, y, z):
        return "tuff_bricks" if y > FLOOR + 1 else "polished_tuff"
    shell(t, b, wall, top, gable("mud_brick_stairs", "mud_brick_slab", "mud_bricks", along="z", gable_wall="tuff_bricks"),
          corner="chiseled_tuff", base="polished_tuff", light=False)
    for z in (z0 + 2, z1 - 2):
        window(t, x1, FLOOR + 2, z, "east", "tall", shutter=TRAPDOOR)
    window(t, x0 + 5, FLOOR + 2, z0, "north", "arched", arch="tuff_brick_stairs")
    station(t, x0 + 2, z0 + 1, "fletching_table")
    resident(t, "fletcher", x0 + 2, z0 + 2)
    station(t, x1 - 2, z0 + 1, "stonecutter", facing="south")
    resident(t, "mason", x1 - 2, z0 + 2)
    t.set(x0 + 4, FLOOR + 1, z0 + 1, "crafting_table")
    for x, item in ((x0 + 4, "bow"), (x0 + 5, "arrow"), (x0 + 6, "brick")):
        frame(t, x, FLOOR + 3, z0 + 1, "south", item)
    for z in (z0 + 4, z0 + 5):
        t.set(x0 + 1, FLOOR + 1, z, "polished_tuff")
    t.set(x0 + 1, FLOOR + 2, z0 + 4, "polished_tuff_slab[type=bottom]")
    # the bedroom along the south: a wall with a door, two beds, a chest
    t.fill(x0 + 1, FLOOR + 1, z1 - 4, x1 - 1, top - 1, z1 - 4, "tuff_bricks")
    door_at(t, "south", x0 + 5, z1 - 4, sill=False)
    bed(t, x0 + 1, z1 - 3, "west", "orange")
    bed(t, x0 + 1, z1 - 1, "west", "orange")
    t.set(x1 - 1, FLOOR + 1, z1 - 1, "chest[facing=west,type=single]", fill_nbt("chest", "casa"))
    t.set(x0 + 5, top - 1, z1 - 2, LANTERN)
    t.set(x0 + 5, top - 1, z0 + 3, LANTERN)
    chimney(t, x0, z0 + 6, FLOOR + 1, top + 5)


def office(t, b):
    """The market office: stone with a weathered-copper hip roof, the counter, the return barrels in two rows on the
    east wall with their sign."""
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 5
    shell(t, b, "stone_bricks", top, hip(_cu("weathered") + "_stairs", _cu("weathered") + "_slab", "waxed_weathered_cut_copper"),
          corner="polished_andesite", base="polished_andesite", light=False)
    for i in range(RETURNS):
        z = z0 + 1 + i % 6
        y = FLOOR + 1 + i // 6
        t.set(x1 - 1, y, z, "barrel[facing=west,open=false]", filler_loot.empty_nbt("barrel", RETURN_EMPTY))
        t.returns.append([x1 - 1, y, z])
    pieces.sign(t.set, x1 - 2, FLOOR + 3, z1 - 1, "west", [text("devolucion.cartel1"), text("devolucion.cartel2")],
                wood="crimson")
    t.set(x1 - 1, FLOOR + 3, z1 - 1, "stone_bricks")
    for z in range(z0 + 2, z0 + 6):
        t.set(x0 + 4, FLOOR + 1, z, "polished_andesite_slab[type=top]")
    t.set(x0 + 4, FLOOR + 2, z0 + 3, "candle[candles=2,lit=true]")
    for z in (z0 + 2, z1 - 2):
        window(t, x0, FLOOR + 2, z, "west", "tall")
    window(t, x0 + 5, FLOOR + 2, z1, "south", "tall")
    t.set(x0 + 4, top - 1, (z0 + z1) // 2, LANTERN)


def clock_tower(t, b):
    """The clock tower over the plaza: 16 blocks of stone to the cornice, an open belfry and a copper spire with a
    lightning rod; a clock face on every side (a real clock in a frame at its centre); its ground floor is an open
    loggia (arches on every side) that shelters the villages' job board and its bailiff."""
    x0, z0, x1, z1 = b.rect()
    cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
    body = FLOOR + 16
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, "polished_andesite" if (x + z) % 2 else "stone_bricks")
            edge = x in (x0, x1) or z in (z0, z1)
            corner = x in (x0, x1) and z in (z0, z1)
            for y in range(FLOOR + 1, body + 1):
                if y <= FLOOR + 4:
                    st = "polished_andesite" if corner else ("stone_bricks" if edge else "air")
                elif y == FLOOR + 5:
                    st = "chiseled_stone_bricks" if edge else "stone_bricks"
                elif y >= body - 3:
                    st = ("polished_andesite" if corner else "stone_bricks") if edge else "air"
                else:
                    st = "polished_andesite" if corner else "stone_bricks"
                t.set(x, y, z, st)
            t.set(x, body + 1, z, "stone_brick_slab[type=bottom]" if edge else "stone_bricks")
    # the loggia's arches: open 3 wide in each side, an arch above
    for side in ("north", "south", "west", "east"):
        for k in (-1, 0, 1):
            x, z = {"north": (cx + k, z0), "south": (cx + k, z1), "west": (x0, cz + k), "east": (x1, cz + k)}[side]
            for y in range(FLOOR + 1, FLOOR + 4):
                t.set(x, y, z, "air")
            if k:
                fac = {"north": ("west", "east"), "south": ("west", "east"), "west": ("north", "south"),
                       "east": ("north", "south")}[side][(k + 1) // 2]
                t.set(x, FLOOR + 4, z, stairs("stone_brick_stairs", fac, "top"))
            else:
                t.set(x, FLOOR + 4, z, "air")
    t.set(cx, FLOOR + 4, cz - 2, LANTERN)
    t.set(cx, FLOOR + 4, cz + 2, LANTERN)
    # the belfry's openings and the clock faces
    for side in ("north", "south", "west", "east"):
        dx, dz = OPEN_DIR[side]
        for k in (-1, 1):
            x, z = {"north": (cx + k, z0), "south": (cx + k, z1), "west": (x0, cz + k), "east": (x1, cz + k)}[side]
            for y in range(body - 2, body):
                t.set(x, y, z, "air")
        fx, fz = {"north": (cx, z0), "south": (cx, z1), "west": (x0, cz), "east": (x1, cz)}[side]
        ax, az = (1, 0) if side in ("north", "south") else (0, 1)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                t.set(fx + ax * i, FLOOR + 10 + j, fz + az * i, "smooth_quartz" if (i, j) != (0, 0) else "chiseled_quartz_block")
        for i, j in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            t.set(fx + ax * i, FLOOR + 10 + j, fz + az * i, "gold_block")
        frame(t, fx + dx, FLOOR + 10, fz + dz, side, "clock")
        wall_banner(t, fx + dx, FLOOR + 7, fz + dz, side)
    build.spire(t, cx, cz, body + 2, 3, _cu("oxidized") + "_stairs", COPPER)
    t.set(cx, body + 10, cz, "lightning_rod[facing=up]")
    t.set(cx, body - 3, cz, "air")


def guardhouse(t, b):
    """The gatehouse's west tower: the guardhouse of the watch, with the guard's grindstone, the weapon rack, a table
    for the dice and the guard's bed; arrow slits outwards."""
    gate_tower(t, b, guard=True)


def storehouse(t, b):
    """The gatehouse's east tower: the watch's storehouse, stacked crates (barrels) and the arms chest."""
    gate_tower(t, b, guard=False)


def gate_tower(t, b, guard):
    x0, z0, x1, z1 = b.rect()
    top = FLOOR + 12
    room_top = FLOOR + 5
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, "polished_andesite" if x0 < x < x1 and z0 < z < z1 else "deepslate_bricks")
            for y in range(FLOOR + 1, top + 1):
                edge = x in (x0, x1) or z in (z0, z1)
                t.set(x, y, z, ("polished_deepslate" if x in (x0, x1) and z in (z0, z1) else "deepslate_bricks")
                      if edge or y >= room_top else "air")
            if x in (x0, x1) or z in (z0, z1):
                if (x + z) % 2 == 0:
                    t.set(x, top + 1, z, "deepslate_brick_wall")
    door(t, b)
    for z in (z1 - 2,):
        window(t, (x0 + x1) // 2, FLOOR + 2, z1, "south", "slit", glass="iron_bars")
    window(t, x0 if guard else x1, FLOOR + 2, z1 - 3, "west" if guard else "east", "slit", glass="iron_bars")
    for z in (z0 + 2, z1 - 2):
        t.set((x0 + x1) // 2, room_top - 1, z, LANTERN)
    wall_banner(t, (x0 + x1) // 2, FLOOR + 9, z1 + 1, "south")
    wall_banner(t, (x0 + x1) // 2, FLOOR + 9, z0 - 1, "north")
    t.set((x0 + x1) // 2, top + 1, (z0 + z1) // 2, "lightning_rod[facing=up]")
    if guard:
        station(t, x1 - 1, z0 + 2, "grindstone", facing="west")
        resident(t, "weaponsmith", x1 - 2, z0 + 2)
        bed(t, x0 + 1, z1 - 1, "south", "blue")
        t.set(x0 + 3, FLOOR + 1, z0 + 4, f"{WOOD_SLAB}[type=top]")
        t.set(x0 + 3, FLOOR + 1, z0 + 3, stairs(WSTAIRS, "north"))
        t.set(x0 + 3, FLOOR + 1, z0 + 5, stairs(WSTAIRS, "south"))
        t.set(x0 + 3, FLOOR + 2, z0 + 4, "candle[candles=1,lit=true]")
        for z, item in ((z0 + 3, "iron_sword"), (z0 + 4, "shield"), (z0 + 5, "bow")):
            frame(t, x1 - 1, FLOOR + 3, z, "west", item)
        t.set(x1 - 1, FLOOR + 1, z1 - 1, "chest[facing=west,type=single]", fill_nbt("chest", "almacen"))
    else:
        for z in range(z0 + 2, z1 - 1):
            t.set(x1 - 1, FLOOR + 1, z, "barrel[facing=west,open=false]", fill_nbt("barrel", "almacen"))
            if z % 2:
                t.set(x1 - 1, FLOOR + 2, z, "barrel[facing=west,open=false]", fill_nbt("barrel", "almacen"))
        t.set(x0 + 1, FLOOR + 1, z1 - 1, "chest[facing=east,type=single]", fill_nbt("chest", "almacen"))
        t.set(x0 + 1, FLOOR + 1, z1 - 2, "barrel[facing=up,open=false]", fill_nbt("barrel", "almacen"))


def corner_tower(t, b):
    """A corner tower: deepslate-based stone rising above the wall, a ground room with a stair up (two flights of
    three, a landing between) to the room at the height of the wall walk, with a door onto each walk; arrow slits
    outwards, banners and a copper cone with a lightning rod."""
    tw = b.tower
    put = lambda u, y, v, st, nbt=None: t.set(*_xyz(tw, u, y, v), st, nbt)
    f = tw.face
    up = WALL_TOP + 1
    for u in range(TOWER):
        for v in range(TOWER):
            edge = u in (0, TOWER - 1) or v in (0, TOWER - 1)
            corner = u in (0, TOWER - 1) and v in (0, TOWER - 1)
            for y in range(0, TOWER_TOP + 1):
                if y <= FLOOR:
                    st = "deepslate_bricks"
                elif edge:
                    st = "polished_deepslate" if corner else ("deepslate_bricks" if y <= FLOOR + 2 else "stone_bricks")
                elif y in (WALL_TOP, TOWER_TOP):
                    st = "polished_andesite"
                else:
                    st = "air"
                put(u, y, v, st)
            if not edge:
                put(u, FLOOR, v, FLOORING if (u + v) % 2 else "polished_andesite")
    # the ground entrance (inwards) is a fence gate: players open it, villagers do not, so they never climb onto the
    # wall walk (on seed terrain a smith did, and lost its bed and its workstation up there); the walk doors
    dx, dz = tw.at(6, 8)
    t.set(dx, FLOOR, dz, PAVE2)
    t.set(dx, FLOOR + 1, dz, f"{GATE}[facing={f('south')},in_wall=false,open=false,powered=false]")
    t.set(dx, FLOOR + 2, dz, "air")
    ex, ez = tw.at(8, 2)
    door_at(t, f("east"), ex, ez, up)
    wx, wz = tw.at(1, 8)
    door_at(t, f("south"), wx, wz, up)
    # the stair: three steps along v = 7 climbing towards -u, a landing at u = 2, three along u = 2 towards -v
    s1 = [(5, 7), (4, 7), (3, 7)]
    for k, (u, v) in enumerate(s1):
        y = FLOOR + 1 + k
        for yy in range(FLOOR + 1, y):
            put(u, yy, v, "stone_bricks")
        put(u, y, v, stairs("stone_brick_stairs", f("west")))
        for yy in range(y + 1, y + 4):
            put(u, yy, v, "air")
    for yy in range(FLOOR + 1, FLOOR + 4):
        put(2, yy, 7, "stone_bricks")
    for yy in range(FLOOR + 4, FLOOR + 7):
        put(2, yy, 7, "air")
    s2 = [(2, 6), (2, 5), (2, 4)]
    for k, (u, v) in enumerate(s2):
        y = FLOOR + 4 + k
        for yy in range(FLOOR + 1, y):
            put(u, yy, v, "stone_bricks")
        put(u, y, v, stairs("stone_brick_stairs", f("north")))
        for yy in range(y + 1, y + 4):
            put(u, yy, v, "air")
    put(2, WALL_TOP, 3, "polished_andesite")
    put(3, up, 6, "stone_brick_wall")              # a railing by the stairwell
    # light, slits, banners, the cone and its rod
    put(5, WALL_TOP - 1, 4, LANTERN)
    put(5, TOWER_TOP - 1, 4, LANTERN)
    for (u, v), side in (((0, 4), "west"), ((4, 0), "north")):
        put(u, up + 1, v, "iron_bars")
        put(u, FLOOR + 3, v, "iron_bars")
    for (u, v), side in (((8, 5), "east"), ((4, 8), "south")):     # on the faces towards the town
        x, z = tw.at(u, v)
        dx_, dz_ = OPEN_DIR[f(side)]
        wall_banner(t, x + dx_, up + 3, z + dz_, f(side))
    cx, cz = tw.at(4, 4)
    build.cone_roof(t, _theme(_cu("oxidized") + "_stairs", _cu("oxidized") + "_slab", COPPER), cx, cz, 3, TOWER_TOP + 1,
                    mat=_cu("oxidized") + "_stairs", top=COPPER)
    t.set(cx, TOWER_TOP + 6, cz, "lightning_rod[facing=up]")


def _xyz(tw, u, y, v):
    x, z = tw.at(u, v)
    return x, y, z


def town_hall(t, b):
    """The town hall (ayuntamiento), facing the plaza: two storeys of stone and calcite under a weathered-copper hip
    with the town's flag on top; over its door the balcony the Herald speaks from, on corbels, with the town's banners
    hanging from it. Downstairs the council hall: two long tables, the carpet up to the Herald's seat under the
    banners; upstairs, by a stair, the archive (shelves of books, the map table, the chests). Nobody sleeps here."""
    x0, z0, x1, z1 = b.rect()
    mid, top = FLOOR + 5, FLOOR + 10

    def wall(x, y, z):
        if x in (x0, x1) and z in (z0, z1):
            return "chiseled_stone_bricks"
        if y <= mid:
            return "stone_bricks" if y > FLOOR + 1 else "polished_andesite"
        return "polished_deepslate" if ((x - x0) % 5 == 0 and z in (z0, z1) or (z - z0) % 4 == 0 and x in (x0, x1)) \
            else "calcite"
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, "polished_andesite" if x0 < x < x1 and z0 < z < z1 and (x + z) % 2 else
                  ("stone_bricks" if x0 < x < x1 and z0 < z < z1 else "polished_andesite"))
    walls(t, x0, z0, x1, z1, FLOOR + 1, top - 1, wall)
    room(t, x0, z0, x1, z1, FLOOR + 1, mid - 1)
    room(t, x0, z0, x1, z1, mid + 1, top - 1)
    slab_fill(t, x0 + 1, z0 + 1, x1 - 1, z1 - 1, mid, FLOORING)
    slab_fill(t, x0, z0, x1, z1, top, "polished_deepslate")
    th = _theme(_cu("weathered") + "_stairs", _cu("weathered") + "_slab", "waxed_weathered_cut_copper")
    ridge = build.hip_roof(t, th, x0, z0, x1, z1, top + 1, overhang=1)
    cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
    t.fill(cx, top + 1, cz, cx, ridge, cz, "polished_deepslate")
    t.fill(cx, ridge + 1, cz, cx, ridge + 3, cz, FENCE)
    t.set(cx, ridge + 4, cz, "blue_banner[rotation=4]", dict(BANNER))
    door(t, b)
    door_at(t, "west", x0, b.along, mid + 1, sill=False)
    # the balcony: four blocks out over the plaza, its railing, corbels and the banners hanging from it
    for x in range(x0 - 4, x0):
        for z in range(b.along - 2, b.along + 3):
            t.set(x, mid, z, "polished_deepslate")
            if x == x0 - 4 or z in (b.along - 2, b.along + 2):
                t.set(x, mid + 1, z, "polished_deepslate_wall")
    for z in (b.along - 2, b.along + 2):
        for x in range(x0 - 4, x0):
            t.set(x, mid - 1, z, stairs("stone_brick_stairs", "east", "top"))
    for z in (b.along - 1, b.along + 1):
        wall_banner(t, x0 - 5, mid, z, "west")
    # windows
    for z in (z0 + 2, z1 - 2):
        window(t, x0, FLOOR + 2, z, "west", "arched", arch="stone_brick_stairs")
        window(t, x0, mid + 2, z, "west", "arched", arch="stone_brick_stairs")
    for x in (x0 + 4, x0 + 10):
        for z, s in ((z0, "north"), (z1, "south")):
            window(t, x, FLOOR + 2, z, s, "arched", arch="stone_brick_stairs")
            window(t, x, mid + 2, z, s, "tall", shutter=TRAPDOOR)
    window(t, x1, mid + 2, cz, "east", "arched", arch="stone_brick_stairs")
    # the council hall
    for z in (z0 + 3, z1 - 3):
        table_row(t, x0 + 5, x1 - 5, z)
        for x in range(x0 + 5, x1 - 4, 2):
            t.set(x, FLOOR + 2, z, ("candle[candles=3,lit=true]", "flower_pot")[(x // 2) % 2])
    for x in range(x0 + 1, x1 - 1):
        t.set(x, FLOOR + 1, b.along, "red_carpet")
    t.set(x1 - 1, FLOOR + 1, b.along, stairs("polished_deepslate_stairs", "east"))
    for z in (b.along - 1, b.along + 1):
        t.set(x1 - 1, FLOOR + 1, z, "polished_deepslate")
        t.set(x1 - 1, FLOOR + 2, z, "candle[candles=2,lit=true]")
        wall_banner(t, x1 - 1, FLOOR + 3, z, "west")
    for x in (x0 + 4, x0 + 8, x0 + 12):
        t.set(x, mid - 1, b.along, LANTERN)
    # the stair up along the north wall, climbing east
    flight(t, x0 + 5, z0 + 1, "east", FLOOR + 1, mid - FLOOR, fill="stone_bricks")
    # the archive upstairs
    for x in range(x0 + 1, x1):
        if all(abs(x - w) > 1 for w in (x0 + 4, x0 + 10)):
            for y in (mid + 1, mid + 2, mid + 3):
                t.set(x, y, z1 - 1, "bookshelf")
    for x in range(x0 + 6, x0 + 10):
        t.set(x, mid + 1, b.along, f"{WOOD_SLAB}[type=top]")
    t.set(x0 + 7, mid + 2, b.along, "candle[candles=1,lit=true]")
    for x in (x1 - 1,):
        for z in (z0 + 4, z0 + 5):
            t.set(x, mid + 1, z, "chest[facing=west,type=single]", fill_nbt("chest", "estudio"))
    for x in (x0 + 4, x0 + 10):
        t.set(x, top - 1, b.along, LANTERN)
    for x, item in ((x0 + 6, "map"), (x0 + 8, "writable_book")):
        frame(t, x, mid + 3, z0 + 1, "south", item)


def training_yard(t, x0, z0, x1, z1):
    """The watch's training yard: beaten earth inside a fence with gaps, three practice dummies, a rack of weapons
    and the archery butt (terracotta rings) at its end, benches and lamps."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, ("coarse_dirt", "packed_mud", "dirt_path")[(x * 3 + z) % 3])
            edge = x in (x0, x1) or z in (z0, z1)
            gap = abs(z - (z0 + z1) // 2) <= 1 and x in (x0, x1) or abs(x - (x0 + x1) // 2) <= 1 and z in (z0, z1)
            if edge and not gap:
                t.set(x, FLOOR + 1, z, FENCE)
    for i, x in enumerate((x0 + 4, x0 + 8, x0 + 12)):
        dummy = {"id": "minecraft:armor_stand", "ShowArms": B(1), "Invulnerable": B(1), "PersistenceRequired": B(1),
                 "Tags": [HOUSE_TAG], "Rotation": [F(90.0), F(0.0)],
                 "equipment": {"head": {"id": "minecraft:leather_helmet", "count": 1},
                               "chest": {"id": "minecraft:leather_chestplate", "count": 1},
                               "mainhand": {"id": ("minecraft:wooden_sword", "minecraft:stone_sword", "minecraft:shield")[i],
                                            "count": 1}}}
        t.entity(x, FLOOR + 1, z0 + 4, dummy)
    # the archery butt at the east end: rings of terracotta on a stone frame
    bx, bz = x1 - 2, z1 - 4
    for dz in (-1, 0, 1):
        for y in (FLOOR + 1, FLOOR + 2, FLOOR + 3):
            t.set(bx, y, bz + dz, "red_terracotta" if (dz, y) == (0, FLOOR + 2) else "white_terracotta")
    for dz in (-2, 2):
        t.fill(bx, FLOOR + 1, bz + dz, bx, FLOOR + 3, bz + dz, "polished_deepslate_wall")
    # the weapon rack: posts with arms in frames, facing the yard
    for z, item in ((z1 - 3, "bow"), (z1 - 2, "iron_sword"), (z1 - 1, "crossbow")):
        t.set(x0 + 1, FLOOR + 1, z, "polished_deepslate")
        t.set(x0 + 1, FLOOR + 2, z, "polished_deepslate")
        frame(t, x0 + 2, FLOOR + 2, z, "east", item)
    for x in range(x0 + 6, x0 + 10):
        t.set(x, FLOOR + 1, z1 - 1, stairs("stone_brick_stairs", "south"))
    lamp_post(t, x0 + 2, z0 + 2)
    lamp_post(t, x1 - 2, z0 + 2)


# ------------------------------------------------------------------ the town around the buildings
def town_wall(t):
    """The wall, WALL_T thick: battlements outside (merlons and lower crenels: nobody falls), the walk, the parapet
    with lanterns inside. The corner towers and the gatehouse are built over it afterwards."""
    def cells():
        for i in range(N):
            for k in range(WALL_T):
                yield (i, k, "north", k)                   # x, z
                yield (k, i, "west", k)
                yield (N - 1 - k, i, "east", k)
                yield (i, SOUTH + WALL_T - 1 - k, "south", k)
    for x, z, side, k in cells():
        if side in ("west", "east") and z > SOUTH + WALL_T - 1:
            continue
        for y in range(0, WALL_TOP + 1):
            v = _h(x, y, z) % 11
            t.blocks[(x, y, z)] = ("minecraft:" + ("mossy_stone_bricks" if v == 0 else "cracked_stone_bricks" if v == 1
                                                   else "stone_bricks"), None)
        if k == 0:                                         # outside: merlons and crenels
            i = x if side in ("north", "south") else z
            t.set(x, WALL_TOP + 1, z, "stone_bricks" if i % 3 == 0 else "stone_brick_wall")
            if i % 3 == 0:
                t.set(x, WALL_TOP + 2, z, "stone_brick_slab[type=bottom]")
        elif k == WALL_T - 1:                              # inside: the parapet, a lantern every 8
            i = x if side in ("north", "south") else z
            t.set(x, WALL_TOP + 1, z, "stone_brick_wall")
            if i % 8 == 4:
                t.set(x, WALL_TOP + 2, z, "lantern[hanging=false]")
        else:
            t.set(x, WALL_TOP, z, "polished_andesite")


def gate(t, side):
    """An arched gate through the wall (north, west, east), 5 wide and 4 high, a lantern under the arch, the town's
    banners outside and a signpost inside naming where the road goes."""
    gx, gz = GATES[side]
    ax = side in ("north", "south")
    lo, hi = ROAD if ax else (PZ - 2, PZ + 2)
    depth = range(0, WALL_T) if side in ("north", "west") else range(N - WALL_T, N)
    for d in depth:
        for k in range(lo, hi + 1):
            x, z = (k, d) if ax else (d, k)
            t.set(x, FLOOR, z, PAVE)
            for y in range(FLOOR + 1, FLOOR + 5):
                t.set(x, y, z, "air")
        for k, fac in ((lo, "west" if ax else "north"), (hi, "east" if ax else "south")):
            x, z = (k, d) if ax else (d, k)
            t.set(x, FLOOR + 4, z, stairs("stone_brick_stairs", fac, "top"))
    mid = depth[1]
    x, z = (C, mid) if ax else (mid, PZ)
    t.set(x, FLOOR + 4, z, LANTERN)
    out = 0 if side in ("north", "west") else N - 1
    # banners hanging on the outer face, either side of the arch
    for k in (lo - 2, hi + 2):
        x, z = (k, out) if ax else (out, k)
        dx, dz = OPEN_DIR[side]
        wall_banner(t, x + dx, FLOOR + 5, z + dz, side) if 0 <= x + dx < N and 0 <= z + dz < N else None
    signpost(t, side)


def signpost(t, side):
    """A signpost on a post, just inside the gate, to the right of the road (readable from inside the town)."""
    gx, gz = GATES[side]
    dx, dz = OPEN_DIR[side]
    inner = WALL_T + 1
    if side == "south":
        px, pz = AVENUE[1] + 2, SOUTH - 3
    elif side == "north":
        px, pz = ROAD[1] + 1, inner
    elif side == "west":
        px, pz = inner, ROAD[1] + 1
    else:
        px, pz = N - 1 - inner, ROAD[1] + 1
    t.set(px, FLOOR + 1, pz, FENCE)
    t.set(px, FLOOR + 2, pz, f"crimson_sign[rotation={ROT[{'north': 'south', 'south': 'north', 'west': 'east', 'east': 'west'}[side]]}]",
          {"id": "minecraft:sign", "is_waxed": B(1),
           "front_text": {"messages": [text("puerta." + side), text("hacia_mundo"), {"text": ""}, {"text": ""}],
                          "color": "black", "has_glowing_text": B(0)},
           "back_text": {"messages": [text("camino.cartel"), {"text": ""}, {"text": ""}, {"text": ""}],
                         "color": "black", "has_glowing_text": B(0)}})


def gatehouse(t):
    """The gatehouse over the south arch, between the guardhouse and the storehouse towers: a stone mass with
    battlements, the arch 7 wide (the avenue's width) and 5 high with a portcullis hanging over its mouth, lanterns in
    the passage and the town's banners on both faces."""
    x0, x1 = AVENUE[0] - 2, AVENUE[1] + 2
    z0, z1 = SOUTH - 2, SOUTH + WALL_T + 2
    top = FLOOR + 10
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(FLOOR + 1, top + 1):
                t.set(x, y, z, "deepslate_bricks" if y <= FLOOR + 2 else "stone_bricks")
            if x in (x0, x1) or z in (z0, z1):
                t.set(x, top + 1, z, "stone_bricks" if (x + z) % 2 else "stone_brick_wall")
    for x in range(AVENUE[0], AVENUE[1] + 1):
        for z in range(z0, z1 + 1):
            for y in range(FLOOR + 1, FLOOR + 6):
                t.set(x, y, z, "air")
        for z in (z0, z1):
            t.set(x, FLOOR + 6, z, "air")
    for z in range(z0, z1 + 1):
        t.set(AVENUE[0], FLOOR + 5, z, stairs("stone_brick_stairs", "west", "top"))
        t.set(AVENUE[1], FLOOR + 5, z, stairs("stone_brick_stairs", "east", "top"))
    for x in range(AVENUE[0] + 1, AVENUE[1]):
        t.set(x, FLOOR + 6, z1, "iron_bars")              # the portcullis, raised
    for z in (z0 + 2, z1 - 2):
        t.set(C, FLOOR + 5, z, LANTERN)
    for x in (C - 2, C + 2):
        wall_banner(t, x, FLOOR + 8, z1 + 1, "south")
        wall_banner(t, x, FLOOR + 8, z0 - 1, "north")


def roads(t):
    """The north road and the west and east roads (5 wide, paved with a path down the middle), the south avenue
    (7 wide, all paved) and the forecourt outside the gatehouse, with its banner poles and lamp posts."""
    pave = lambda x, z: PAVE if (x + z) % 2 else PAVE2
    for z in range(0, PLAZA[1]):
        for x in range(ROAD[0], ROAD[1] + 1):
            t.set(x, FLOOR, z, pave(x, z) if x in ROAD else "dirt_path")
    for x in list(range(0, PLAZA[0])) + list(range(PLAZA[2] + 1, N)):
        for z in range(ROAD[0] - C + PZ, ROAD[1] - C + PZ + 1):
            t.set(x, FLOOR, z, pave(x, z) if z in (PZ - 2, PZ + 2) else "dirt_path")
    for z in range(PLAZA[3] + 1, N):
        for x in range(AVENUE[0], AVENUE[1] + 1):
            edge = x in AVENUE
            t.set(x, FLOOR, z, "polished_andesite" if edge else ("stone_bricks" if (x + z) % 3 else "chiseled_stone_bricks"))
    # lamp posts along the roads, banner poles along the avenue and the forecourt
    for d in range(12, PLAZA[1] - 2, 10):
        lamp_post(t, ROAD[0] - 1, d)
        lamp_post(t, ROAD[1] + 1, d)
    for d in list(range(12, PLAZA[0] - 2, 10)) + list(range(PLAZA[2] + 6, N - 6, 10)):
        lamp_post(t, d, PZ - 3)
        lamp_post(t, d, PZ + 3)
    for z in range(PLAZA[3] + 6, SOUTH - 3, 8):
        lamp_post(t, AVENUE[0] - 1, z)
        lamp_post(t, AVENUE[1] + 1, z)
    for z in range(SOUTH + WALL_T + 4, N - 1, 4):
        flagpole(t, AVENUE[0] - 2, z, 5, "east")
        flagpole(t, AVENUE[1] + 2, z, 5, "west")
    garden(t, AVENUE[0] - 15, SOUTH + WALL_T + 4, AVENUE[0] - 7, N - 2, 2, ["poppy", "dandelion"])
    garden(t, AVENUE[1] + 7, SOUTH + WALL_T + 4, AVENUE[1] + 15, N - 2, 2, ["poppy", "dandelion"])


def plaza(t):
    """The plaza: paving in rings, the dais in the middle with steps on every side and a copper canopy over the bell,
    the monument to the Herald, flagpoles, lamp posts and benches. Its middle 23 x 23 (SQ0) is a village square for the
    village events: a solid floor in the bays around each road's mouth and nothing standing there."""
    a, b_, c, d = PLAZA
    for x in range(a, c + 1):
        for z in range(b_, d + 1):
            ring = max(abs(x - C), abs(z - PZ))
            st = "polished_andesite" if ring in (5, 11) else ("smooth_stone" if ring % 2 else "stone_bricks")
            if ring > 11:
                st = PAVE if (x + z) % 2 else PAVE2
            t.set(x, FLOOR, z, st)
    # the dais: 7 x 7, a block high, steps in the middle of each side, the canopy on four posts
    for x in range(C - 3, C + 4):
        for z in range(PZ - 3, PZ + 4):
            edge = max(abs(x - C), abs(z - PZ)) == 3
            t.set(x, FLOOR + 1, z, "polished_deepslate_bricks" if edge else "polished_deepslate")
    for k in (-1, 0, 1):
        t.set(C + k, FLOOR + 1, PZ - 3, stairs("polished_deepslate_stairs", "south"))
        t.set(C + k, FLOOR + 1, PZ + 3, stairs("polished_deepslate_stairs", "north"))
        t.set(C - 3, FLOOR + 1, PZ + k, stairs("polished_deepslate_stairs", "east"))
        t.set(C + 3, FLOOR + 1, PZ + k, stairs("polished_deepslate_stairs", "west"))
    for x, z in ((C - 3, PZ - 3), (C + 3, PZ - 3), (C - 3, PZ + 3), (C + 3, PZ + 3)):
        t.fill(x, FLOOR + 2, z, x, FLOOR + 4, z, "polished_deepslate_wall")
        t.set(x, FLOOR + 5, z, "polished_deepslate")
    build.hip_roof(t, _theme(_cu("oxidized") + "_stairs", _cu("oxidized") + "_slab", COPPER), C - 3, PZ - 3, C + 3, PZ + 3,
                   FLOOR + 6, overhang=1, mat=_cu("oxidized") + "_stairs", slabm=_cu("oxidized") + "_slab", fullm=COPPER)
    t.fill(C - 2, FLOOR + 5, PZ - 2, C + 2, FLOOR + 5, PZ + 2, "polished_deepslate_slab[type=top]")
    t.set(C, FLOOR + 5, PZ, "chiseled_polished_blackstone")
    t.set(*BELL, "bell[attachment=ceiling,facing=north,powered=false]")
    t.bells.append(BELL)
    for x, z in ((C - 2, PZ - 2), (C + 2, PZ + 2)):
        t.set(x, FLOOR + 4, z, LANTERN)
    # the monument to the Herald (south-west corner of the plaza): a plinth, the Herald, a plaque
    mx, mz = a + 2, d - 2
    t.fill(mx - 1, FLOOR + 1, mz - 1, mx + 1, FLOOR + 1, mz + 1, "polished_blackstone_bricks")
    t.fill(mx - 1, FLOOR + 2, mz - 1, mx + 1, FLOOR + 2, mz + 1, "chiseled_stone_bricks")
    t.set(mx, FLOOR + 3, mz, "polished_blackstone_slab[type=bottom]")
    herald = {"id": "minecraft:armor_stand", "ShowArms": B(1), "Invulnerable": B(1), "PersistenceRequired": B(1),
              "Tags": [HOUSE_TAG], "Rotation": [F(-135.0), F(0.0)],
              "Pose": {"RightArm": [F(-110.0), F(0.0), F(10.0)]},
              "equipment": {"head": {"id": "minecraft:golden_helmet", "count": 1},
                            "chest": {"id": "minecraft:leather_chestplate", "count": 1,
                                      "components": {"minecraft:dyed_color": 0x2B4FA8}},
                            "legs": {"id": "minecraft:leather_leggings", "count": 1,
                                     "components": {"minecraft:dyed_color": 0x2B4FA8}},
                            "feet": {"id": "minecraft:leather_boots", "count": 1,
                                     "components": {"minecraft:dyed_color": 0x3A2A1A}},
                            "mainhand": {"id": "minecraft:goat_horn", "count": 1},
                            "offhand": {"id": "minecraft:blue_banner", "count": 1,
                                        "components": {"minecraft:banner_patterns": BANNER["patterns"]}}}}
    t.entity(mx, FLOOR + 3.5, mz, herald)
    pieces.sign(t.set, mx + 2, FLOOR + 2, mz, "east", [text("monumento"), text("monumento2")], wood="crimson")
    t.set(mx + 2, FLOOR + 1, mz, "polished_blackstone_bricks")
    pieces.sign(t.set, mx, FLOOR + 2, mz - 2, "north", [text("monumento"), text("monumento2")], wood="crimson")
    t.set(mx, FLOOR + 1, mz - 2, "polished_blackstone_bricks")
    # flagpoles flanking the north road's and the avenue's mouths, lamp posts at the square's corners, benches
    for x in (ROAD[0] - 2, ROAD[1] + 2):
        flagpole(t, x, b_, 7, "south")
    for x in (AVENUE[0] - 2, AVENUE[1] + 2):
        flagpole(t, x, d, 7, "north")
    for x, z in ((SQ0[0] - 1, SQ0[1] - 1), (SQ0[0] + SQUARE, SQ0[1] - 1), (SQ0[0] - 1, SQ0[1] + SQUARE),
                 (SQ0[0] + SQUARE, SQ0[1] + SQUARE)):
        lamp_post(t, x, z, 3)
    for x0 in (a + 6, c - 8):
        for x in range(x0, x0 + 3):
            t.set(x, FLOOR + 1, b_ + 1, stairs("stone_brick_stairs", "north"))
    for z0 in (b_ + 6, d - 8):
        for z in range(z0, z0 + 3):
            t.set(c - 1, FLOOR + 1, z, stairs("stone_brick_stairs", "east"))
    for x, z in ((a + 1, b_ + 1), (c - 1, b_ + 1), (c - 1, d - 1)):
        t.set(x, FLOOR + 1, z, "polished_deepslate")
        t.set(x, FLOOR + 2, z, ("potted_red_tulip", "potted_cornflower", "potted_oxeye_daisy")[(x + z) % 3])


HOUSE_BELLS = ((30, 20), (20, 36), (59, 38), (69, 16), (96, 20), (108, 36), (92, 55), (112, 65), (58, 91), (53, 111),
               (45, 51))


def neighbourhood_bells(t):
    """The house bells: one on a post a few steps from each house's door (or between two neighbours), so that every
    resident's bed, workstation and meeting point are a short walk apart (resident_errors). A villager takes the
    closest bell as its meeting point and idles around it; in 26.3 it finds no path much longer than about 16 blocks,
    and on the seed's terrain residents who idled at a bell 30-45 blocks' walk from their beds lost them at night. The
    plaza's bell under the canopy stays the town's (and the events' centre). Positions found by a search over the walk
    (never on a door's front or a path), kept fixed here."""
    for x, z in HOUSE_BELLS:
        bell_post(t, x, z)


def garden(t, x0, z0, x1, z1, seed, plants=None):
    flowers = plants or ["poppy", "dandelion", "cornflower", "oxeye_daisy", "azure_bluet", "allium", "red_tulip",
                         "lily_of_the_valley"]
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if (x - x0) % 4 == 0 or (z - z0) % 4 == 0:
                t.set(x, FLOOR, z, "dirt_path")
            else:
                t.set(x, FLOOR, z, "grass_block[snowy=false]")
                t.set(x, FLOOR + 1, z, flowers[((x - x0) // 4 + (z - z0) // 4 * 3 + seed) % len(flowers)])


def farm(t, x0, z0, x1, z1):
    """Wheat, carrots and potatoes on farmland around two water channels (covered at their ends by the border)."""
    crops = ("wheat[age=7]", "carrots[age=7]", "potatoes[age=7]", "wheat[age=5]")
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if x in (x0, x1) or z in (z0, z1):
                t.set(x, FLOOR, z, "dirt_path")
            elif (z - z0) % 5 == 0:
                t.set(x, FLOOR, z, "water")
                t.set(x, FLOOR - 1, z, "stone_bricks")
            else:
                t.set(x, FLOOR, z, "farmland[moisture=7]")
                t.set(x, FLOOR + 1, z, crops[((z - z0) // 5 + x // 4) % len(crops)])


def coop(t, x0, z0):
    """A chicken run: a fenced yard (its gate shut) with a little roofed coop and three hens (they do not lay: a
    yard full of eggs would be items on the ground)."""
    x1, z1 = x0 + 5, z0 + 5
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            t.set(x, FLOOR, z, "coarse_dirt" if (x + z) % 2 else "grass_block[snowy=false]")
            if x in (x0, x1) or z in (z0, z1):
                t.set(x, FLOOR + 1, z, FENCE)
    t.set((x0 + x1) // 2, FLOOR + 1, z1, f"{GATE}[facing=south,in_wall=false,open=false,powered=false]")
    for x in (x0 + 1, x0 + 2):
        for z in (z0 + 1, z0 + 2):
            t.set(x, FLOOR + 3, z, f"{WOOD_SLAB}[type=bottom]")
    for i in range(3):
        mob(t, x0 + 2 + i, FLOOR + 1, z0 + 3, "chicken", still=False, EggLayTime=2_000_000_000)


def stall(t, x0, zn, faces, number):
    """A 5 x 5 market stall: floor, four posts, a slab roof, the counter on the open side and a sign with its number.
    Returns (editable box, sign position): the 3 x 3 x 3 inside behind the counter is what the tenant may use."""
    z_counter = zn if faces == "north" else zn + STALL_W - 1
    z_back = zn + STALL_W - 1 if faces == "north" else zn
    for x in range(x0, x0 + STALL_W):
        for z in range(zn, zn + STALL_W):
            t.set(x, FLOOR, z, PAVE2 if x in (x0, x0 + STALL_W - 1) or z in (zn, zn + STALL_W - 1) else "smooth_stone")
            for y in range(FLOOR + 1, FLOOR + 4):
                t.set(x, y, z, "air")
            t.set(x, FLOOR + 4, z, ("red_nether_brick_slab[type=bottom]" if x % 2 else "smooth_quartz_slab[type=bottom]"))
    for x in (x0, x0 + STALL_W - 1):
        for z in (zn, zn + STALL_W - 1):
            t.fill(x, FLOOR + 1, z, x, FLOOR + 3, z, FENCE)
    for x in range(x0 + 1, x0 + STALL_W - 1):
        t.set(x, FLOOR + 1, z_counter, f"{WOOD_SLAB}[type=top]")
        t.set(x, FLOOR + 1, z_back, "stone_bricks")
        t.set(x, FLOOR + 2, z_back, "stone_bricks")
    sx, sz = x0 + 1, z_counter
    t.set(sx, FLOOR + 2, sz, f"crimson_sign[rotation={8 if faces == 'north' else 0}]",
          {"id": "minecraft:sign", "is_waxed": B(1),
           "front_text": {"messages": [text("puesto"), {"text": f"#{number}"}, text("se_alquila"), {"text": ""}],
                          "color": "black", "has_glowing_text": B(0)},
           "back_text": {"messages": [{"text": ""}] * 4, "color": "black", "has_glowing_text": B(0)}})
    zi0, zi1 = (zn + 1, zn + 3)
    box = [[x0 + 1, FLOOR + 1, zi0], [x0 + 3, FLOOR + 3, zi1]]
    return box, [sx, FLOOR + 2, sz]


def market(t):
    number = 1
    for zn, faces in STALL_ROWS:
        for x0 in STALL_X:
            box, sign = stall(t, x0, zn, faces, number)
            t.stalls.append({"id": number, "caja": box, "cartel": sign})
            number += 1
    lane = (STALL_ROWS[0][0] + STALL_W, STALL_ROWS[1][0] - 1)
    for x in range(STALL_X[0] - 3, PLAZA[0]):
        for z in range(lane[0], lane[1] + 1):
            t.set(x, FLOOR, z, "dirt_path" if (x + z) % 3 else "coarse_dirt")
    # stacked crates (barrels) and a cart at the lane's west end
    for x, z, h in ((STALL_X[0] - 3, lane[0], 2), (STALL_X[0] - 3, lane[0] + 1, 1), (STALL_X[-1] + 6, lane[1] + 5, 2)):
        for y in range(FLOOR + 1, FLOOR + 1 + h):
            t.set(x, y, z, "barrel[facing=west,open=false]", fill_nbt("barrel", "mercado"))


def portal(t):
    (ax, ay, az), (bx, by, bz) = PORTAL
    for x in range(ax, bx + 1):
        for y in range(ay, by + 1):
            edge = x in (ax, bx) or y in (ay, by)
            t.set(x, y, az, "obsidian" if edge else "air")
    # pavilion: a platform, four pillars and a stepped roof, open on every side
    for x in range(ax - 4, bx + 5):
        for z in range(az - 4, az + 5):
            t.set(x, FLOOR, z, "polished_blackstone_bricks" if (x + z) % 2 else "polished_blackstone")
            edge = x in (ax - 4, bx + 4) and z in (az - 4, az + 4)
            if edge:
                t.fill(x, FLOOR + 1, z, x, FLOOR + 6, z, "polished_blackstone_bricks")
            t.set(x, FLOOR + 7, z, "polished_blackstone_brick_slab[type=bottom]")
    t.fill(ax - 2, FLOOR + 7, az - 2, bx + 2, FLOOR + 7, az + 2, "polished_blackstone_bricks")
    t.fill(ax - 1, FLOOR + 8, az - 1, bx + 1, FLOOR + 8, az + 1, "polished_blackstone_brick_slab[type=bottom]")
    for x, z in ((ax - 3, az - 3), (bx + 3, az - 3), (ax - 3, az + 3), (bx + 3, az + 3)):
        t.set(x, FLOOR + 6, z, "soul_lantern[hanging=true]")
    pieces.sign(t.set, ax - 1, FLOOR + 2, az, "west", [text("portal.cartel1"), text("portal.cartel2")], wood="crimson")


def well(t):
    x0, x1, z0, z1 = WELL
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            inner = x0 < x < x1 and z0 < z < z1
            for y in range(1, FLOOR + 1):
                t.set(x, y, z, "water" if inner else "stone_bricks")
            t.set(x, FLOOR + 1, z, "air" if inner else "stone_brick_wall")
            t.set(x, FLOOR + 4, z, "stone_brick_slab[type=bottom]")
            if x in (x0, x1) and z in (z0, z1):
                t.fill(x, FLOOR + 1, z, x, FLOOR + 3, z, "stone_bricks")
    t.set((x0 + x1) // 2, FLOOR + 3, (z0 + z1) // 2, LANTERN)
    t.set((x0 + x1) // 2, FLOOR + 4, (z0 + z1) // 2, "stone_bricks")


def paste_trace(t, kind, x0, z0, rot_ok=True):
    """One of the villages' work-in-progress traces (traces.py, aldeas.vida.rastros), built with fireproof materials,
    pasted at (x0, z0) on the town's ground; whatever of it would burn in the open (carpet, hay) is left out."""
    tr = traces.trace(FIREPROOF, "casa_heraldo", kind)
    for (x, y, z), (st, nbt) in tr.blocks.items():
        n = _name(st)
        if n == "jigsaw" or y == 0 or n.endswith("_carpet") or n in ("hay_block", "pumpkin", "scaffolding"):
            continue
        t.set(x0 + x, FLOOR + y, z0 + z, st, nbt)


def path(t, start, protect):
    """A path from the cell in front of a door to the nearest street cell (breadth-first over open ground, never
    through a building's plot), paved 1 wide with dirt path. Returns the cells or None."""
    from collections import deque
    sx, sz = start
    if t.street.get((sx, sz)):
        return [(sx, sz)]
    prev = {(sx, sz): None}
    q = deque([(sx, sz)])
    end = None
    while q:
        x, z = q.popleft()
        if t.street.get((x, z)):
            end = (x, z)
            break
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if n in prev or not (WALL_T <= n[0] < N - WALL_T and WALL_T <= n[1] < SOUTH) or n in protect:
                continue
            if not (t.is_free(n[0], FLOOR + 1, n[1]) and t.is_free(n[0], FLOOR + 2, n[1])) or \
                    _name(t.get(n[0], FLOOR, n[1])) in ("farmland", "water"):
                continue
            prev[n] = (x, z)
            q.append(n)
    if end is None:
        return None
    cells = []
    c = end
    while c is not None:
        cells.append(c)
        c = prev[c]
    for x, z in cells:
        if not t.street.get((x, z)) and _name(t.get(x, FLOOR, z)) in ("grass_block", "dirt", "coarse_dirt"):
            t.set(x, FLOOR, z, "dirt_path")
    return cells


def golems(t):
    """The night watch: an iron golem on the north wall walk and another on the south-west one (the tower doors keep
    them up there: golems do not open doors), and the plaza's golem."""
    watch = {"id": "minecraft:iron_golem", "PlayerCreated": B(0), "PersistenceRequired": B(1), "Tags": [HOUSE_TAG]}
    t.entity(40, WALL_TOP + 1, 1.5, dict(watch, Rotation=[F(-90.0), F(0.0)]))
    t.entity(30, WALL_TOP + 1, SOUTH + 1.5, dict(watch, Rotation=[F(90.0), F(0.0)]))
    t.entity(C + 8, FLOOR + 1, PZ + 8, dict(watch))


# ------------------------------------------------------------------ the whole town
def construct(dressed=True):
    """The town's template. `dressed` False leaves out herald_dress (the relief, texture and skyline over the plain
    build): the tests compare the two."""
    t = Template(TEMPLATE)
    t.villagers, t.beds, t.stalls, t.returns, t.stations, t.bells, t.paths = [], [], [], [], [], [], []
    stone, grass, air = ("minecraft:stone", None), ("minecraft:grass_block[snowy=false]", None), ("minecraft:air", None)
    for x in range(N):
        for z in range(N):
            for y in range(0, FLOOR):
                t.blocks[(x, y, z)] = stone
            t.blocks[(x, FLOOR, z)] = grass
            for y in range(FLOOR + 1, HEIGHT):
                t.blocks[(x, y, z)] = air
    town_wall(t)
    roads(t)
    plaza(t)
    market(t)
    t.street = {}
    for (x, y, z), (st, _) in list(t.blocks.items()):
        if y == FLOOR and _name(st) in (PAVE, PAVE2, "dirt_path", "coarse_dirt", "smooth_stone", "chiseled_stone_bricks"):
            if WALL_T <= x < N - WALL_T and WALL_T <= z < SOUTH:
                t.street[(x, z)] = True
    gatehouse(t)
    blds = _buildings()
    for b in blds:
        b.recipe(t, b)
    for side in ("north", "west", "east"):
        gate(t, side)
    signpost(t, "south")
    farm(t, *FARM)
    coop(t, 102, 11)
    garden(t, 45, 8, 57, 20, 0)
    garden(t, 72, 98, 100, 108, 3)
    garden(t, 104, 98, 118, 108, 5)
    garden(t, 8, 96, 20, 106, 1)
    farm(t, 6, 73, 21, 93)
    training_yard(t, 78, 82, 98, 95)
    portal(t)
    well(t)
    paste_trace(t, "laundry", 5, 48)
    paste_trace(t, "laundry", 13, 48)
    paste_trace(t, "cart", 13, 66)
    paste_trace(t, "workyard", 46, 97)
    paste_trace(t, "meal", 100, 84)
    neighbourhood_bells(t)
    job_board(t)
    t.mural_towers = herald_dress.dress(t, blds) if dressed else []
    # paths from each door to the nearest street
    plots = {(x, z) for b in blds for x in range(b.x0, b.x1 + 1) for z in range(b.z0, b.z1 + 1)}
    for b in blds:
        for side, x, y, z in b.doors():
            if y != FLOOR + 1:
                continue
            dx, dz = OPEN_DIR[side]
            start = (x + dx, z + dz)
            t.paths.append((b.name, start, path(t, start, plots)))
    t.trees = set()
    if dressed:
        herald_dress.lanes(t)
        herald_dress.trees(t)
        t.hedges, t.pots = herald_dress.hedges(t, blds)
    golems(t)
    t.blds = blds
    return t


def job_board(t):
    """The villages' job board (board.piece), reused as it is: lectern with the book and the bailiff behind it."""
    b = board.piece(THEME, f"{TEMPLATE}_tablon")
    bx, by, bz = BOARD
    for (x, y, z), (st, nbt) in b.blocks.items():
        if st.startswith("minecraft:jigsaw"):
            st, nbt = "minecraft:air", None
        t.set(bx + x, by + y, bz + z, st, nbt)
    for x, y, z, nbt in b.entities:
        t.entity(bx + x, by + y, bz + z, dict(nbt, Tags=list(nbt["Tags"]) + [HOUSE_TAG]))


def dock():
    """Dock out over the water (along +z): a slab deck on posts down to y = 0 of the template (the Java side
    places it with y = 1 at the water's surface), with a railing and lanterns."""
    w, length = DOCK_SIZE
    t = Template(DOCK)
    for x in range(w):
        for z in range(length):
            t.set(x, 1, z, "stone_brick_slab[type=top]" if 0 < x < w - 1 else PAVE2)
            if x in (0, w - 1) and z % 4 == 0:
                t.set(x, 0, z, "stone_bricks")
                t.set(x, 2, z, "stone_brick_wall")
                t.set(x, 3, z, "lantern[hanging=false]")
            elif x in (0, w - 1):
                t.set(x, 2, z, "stone_brick_wall")
    t.set(w // 2, 2, length - 1, "stone_brick_wall")
    return t


def previous():
    """The blueprints of the earlier versions ({version: blueprint}), frozen as they were published."""
    with open(V1) as f:
        return {"1": json.load(f)}


def dataset(t=None):
    """What the Java side reads (heraldia/casa_heraldo.json): positions relative to the template's minimum corner;
    `anteriores` carries the blueprints of the earlier versions, for the worlds that placed one of them."""
    t = t or construct()
    w, length = DOCK_SIZE
    return {
        "version": VERSION,
        "plantilla": f"{NS}:{TEMPLATE}",
        "tamano": [N, HEIGHT, N],
        "suelo": FLOOR,
        "aparicion": list(SPAWN),
        "campana": list(BELL),
        "puertas": {side: list(p) for side, p in GATES.items()},
        "camino": [ROAD[0] - C, ROAD[1] - C],
        "portal": [list(PORTAL[0]), list(PORTAL[1])],
        "puestos": t.stalls,
        "devolucion": t.returns,
        "muelle": {"plantilla": f"{NS}:{DOCK}", "tamano": [w, 4, length]},
        "estilo": STYLE,
        "huerto": list(FARM_CELL),
        "plaza_eventos": [SQ0[0], FLOOR, SQ0[1], SQUARE],
        # outside the wall (the forecourt): its bare ground takes the land's own surface (herald/Building.exterior)
        "exterior": [0, SOUTH + WALL_T, N - 1, N - 1],
        "anteriores": previous(),
    }


# ------------------------------------------------------------------ audit
def _name(st):
    return (st or "minecraft:air").split("[")[0].removeprefix("minecraft:")


# never anywhere: flammable wood and the like (crimson and warped are fireproof)
FLAMMABLE = ("oak_", "spruce_", "birch_", "jungle_", "acacia_", "dark_oak_", "mangrove_", "cherry_", "bamboo", "pale_oak_",
             "leaves", "_log", "tnt", "thatch", "scaffolding", "dried_kelp_block", "beehive", "bee_nest", "target")
# allowed only where fire_errors proves a fire started by lightning cannot reach them
SHELTERED = ("bookshelf", "chiseled_bookshelf", "lectern", "composter", "hay_block", "coal_block")
SHELTERED_SUFFIX = ("_carpet", "_wool")
# plants burn too, but a garden that burns is not the town burning: they only carry fire in the model
PLANTS = ("poppy", "dandelion", "cornflower", "oxeye_daisy", "azure_bluet", "allium", "red_tulip", "orange_tulip",
          "white_tulip", "pink_tulip", "lily_of_the_valley", "blue_orchid", "short_grass", "tall_grass", "fern",
          "large_fern", "sweet_berry_bush", "vine", "rose_bush", "peony", "lilac", "sunflower")


def _sheltered(n):
    return n in SHELTERED or n.endswith(SHELTERED_SUFFIX)


def _burns(n):
    return _sheltered(n) or n in PLANTS or any(n.startswith(f) or n.endswith(f) for f in FLAMMABLE)


def fire_errors(t):
    """Can a fire started by lightning reach a flammable block of the town? A model of 26.3 (LightningBolt.spawnFire,
    FireBlock.tick): a bolt strikes the air above the top of a column (or a creature standing in the open) and lights
    that cell and up to four cells within one block of it, each only if it is air and fire can stand there (a solid
    block below or something flammable beside it); a fire then lights any air cell within 1 block sideways, 1 below and
    4 above that has something flammable beside it, and burns away a flammable block beside it. Walls and roofs are
    not modelled as shields (the game does not either): only distance and what is flammable matter. Plants carry the
    fire but are not reported; the sheltered blocks (SHELTERED) must stay out of its reach, and the never-flammable
    ones (FLAMMABLE) are reported anywhere by errors()."""
    from collections import deque
    g = lambda x, y, z: _name(t.get(x, y, z)) if (x, y, z) in t.blocks else None
    burn = {p for p, (st, _) in t.blocks.items() if _burns(_name(st))}

    def air(p):
        return g(*p) == "air"

    def flammable_beside(p):
        x, y, z = p
        return any(q in burn for q in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)))

    def stands(p):
        x, y, z = p
        below = t.get(x, y - 1, z)
        return below is not None and not lint.passable(below) or flammable_beside(p)
    fire = set()
    q = deque()
    for x in range(N):
        for z in range(N):
            top = None
            for y in range(HEIGHT - 1, -1, -1):
                st = t.get(x, y, z)
                if st is not None and (not lint.passable(st) or _name(st) == "water"):
                    top = y
                    break
            if top is None:
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        p = (x + dx, top + 1 + dy, z + dz)
                        if p not in fire and air(p) and stands(p):
                            fire.add(p)
                            q.append(p)
    reached = set()
    while q:
        x, y, z = q.popleft()
        for n in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            if n in burn and n not in reached:
                reached.add(n)
                if n not in fire:                  # it burns away: fire where it was
                    fire.add(n)
                    q.append(n)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for dy in range(-1, 5):
                    p = (x + dx, y + dy, z + dz)
                    if p not in fire and air(p) and flammable_beside(p):
                        fire.add(p)
                        q.append(p)
    out = []
    for p in sorted(reached):
        n = g(*p)
        if _sheltered(n):
            out.append(f"casa_heraldo: {n} at {p} is within reach of a fire started by lightning")
    return out


def _walk_view(t):
    """The template as a villager walks it (no ladders, gates shut), entered from the spawn point on the plaza."""
    u = _inhabitants._no_ladders(t)
    u.jigsaws = [{"name": "heraldia:entrance", "pos": (SPAWN[0], FLOOR, SPAWN[2])}]
    return u


def walk_cells(t, player=False):
    """The cells a villager (or, with `player`, a player: gates open) walks to from the plaza."""
    if player:
        u = Template(t.name + "#jugador")
        u.blocks, u.entities = t.blocks, []
        u.jigsaws = [{"name": "heraldia:entrance", "pos": (SPAWN[0], FLOOR, SPAWN[2])}]
        return set(lint.walk(u))
    return set(lint.walk(_walk_view(t)))


def placement_errors(blds, t=None, cells=None):
    """The door rule (doors.py, the owner's, mandatory here) on the town's buildings: doors.footprint_errors on the
    footprints (room in front of every door, no door facing another building's wall, buildings apart) and, with the
    template, the cells in front of each door free and walkable, every door walkable from the plaza and the path laid
    from it reaching a street."""
    e = []
    if t is not None:
        for b in blds:
            for side, x, y, z in b.doors():
                dx, dz = OPEN_DIR[side]
                for k in range(1, CLEAR_FRONT + 1):
                    cx, cz = x + dx * k, z + dz * k
                    if not (lint.passable(t.get(cx, y, cz)) and lint.passable(t.get(cx, y + 1, cz))
                            and lint.top_height(t.get(cx, y - 1, cz)) == 1.0):
                        e.append(f"casa_heraldo: the door of {b.name} at {x} {z}: {cx} {y} {cz} ({k} out) is not free and walkable")
                        break
    import doors
    e += ["casa_heraldo: " + m for m in doors.footprint_errors(
        [(b.name, b.rect(True), [(side, x, z) for side, x, y, z in b.doors()]) for b in blds])]
    if t is not None:
        cells = walk_cells(t, player=True)          # players: they open gates (the towers' entrances)
        for b in blds:
            for side, x, y, z in b.doors():
                dx, dz = OPEN_DIR[side]
                if (x + dx, y, z + dz) not in cells or (x - dx, y, z - dz) not in cells:
                    e.append(f"casa_heraldo: the door of {b.name} at {x} {y} {z} cannot be walked to from the plaza")
        villager = walk_cells(t) if t is not None else set()
        for b in blds:
            if b.recipe is corner_tower and any((x, WALL_TOP + 1, z) in villager for x in range(N) for z in (1, 2)):
                e.append("casa_heraldo: a villager can walk onto the wall walk")
                break
        for name, start, cells_ in t.paths:
            if not cells_ or not t.street.get(cells_[0]) or cells_[-1] != start:
                e.append(f"casa_heraldo: the path from the door of {name} does not reach a street")
            elif any((x, FLOOR + 1, z) not in villager for x, z in cells_):
                e.append(f"casa_heraldo: the path from the door of {name} cannot be walked")
    return e


def _paths(cells, sources):
    """Walking distance (blocks) from the source cells to every cell a villager reaches (steps of one block, up or down
    one where the walk allows)."""
    from collections import deque
    d = {c: 0 for c in sources if c in cells}
    q = deque(d)
    while q:
        x, y, z = q.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in (0, 1, -1):
                n = (x + dx, y + dy, z + dz)
                if n in cells and n not in d:
                    d[n] = d[(x, y, z)] + 1
                    q.append(n)
    return d


def _around(cells, p, dys=(-1, 0, 1)):
    x, y, z = p
    return [(x + dx, y + dy, z + dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)) for dy in dys
            if (x + dx, y + dy, z + dz) in cells]


def _to(d, cells, p, dys=(-1, 0, 1)):
    near = [d[c] for c in _around(cells, p, dys) if c in d]
    return min(near) if near else None


def resident_errors(t, cells=None):
    """Who lives where, walked as a villager: each resident starts where it can walk, next to a workstation of its
    trade of its own; a free bed at most BED_PATH blocks' walk from that workstation (one each and no spare: a free
    bed lets villagers breed, and on the seed's terrain the children took the nearest free beds, residents' among them); and the bell it will take as its meeting point (the game takes the closest one in a
    straight line) at most BELL_PATH blocks' walk from both its workstation and its bed: a villager idles around its
    bell and, in 26.3, finds no path much longer than that, so a bed far from its bell is given up at night (measured on
    seed terrain: the librarians idled at a bell 45 blocks' walk from their beds and lost them). No fence it can hop
    into and not out of."""
    e = []
    cells = cells if cells is not None else walk_cells(t)
    view = _walk_view(t)
    beside = lambda p: _inhabitants._beside(cells, *p)
    beds = [(x, y, z) for (x, y, z), (st, _) in t.blocks.items() if _name(st).endswith("_bed") and "part=head" in st]
    reach = [p for p in beds if beside(p)]
    for p in beds:
        if p not in reach:
            e.append(f"casa_heraldo: the bed at {p} cannot be walked to")
    if len(reach) != len(t.villagers):
        e.append(f"casa_heraldo: {len(reach)} beds for {len(t.villagers)} villagers (one each and no spare)")
    bell_dys = lambda b: tuple(range(-3, 1))
    bells = [b for b in t.bells if _around(cells, b, bell_dys(b))]
    if len(bells) != len(t.bells):
        e.append("casa_heraldo: a bell cannot be walked to")
    bell_paths = {b: _paths(cells, _around(cells, b, bell_dys(b))) for b in bells}
    used_jobs, used_beds = set(), set()
    t.report = []
    for prof, x, z in t.villagers:
        if (x, FLOOR + 1, z) not in cells:
            e.append(f"casa_heraldo: the {prof} at {x} {z} starts where it cannot walk")
            continue
        jobs = [(s, jx, jz) for s, jx, jz in t.stations if PROFESSION[s] == prof and (s, jx, jz) not in used_jobs
                and max(abs(jx - x), abs(jz - z)) <= 1 and beside((jx, FLOOR + 1, jz))]
        if not jobs:
            e.append(f"casa_heraldo: the {prof} at {x} {z} has no {WORKSTATION[prof]} of its own beside it")
            continue
        used_jobs.add(jobs[0])
        _, jx, jz = jobs[0]
        w = (jx, FLOOR + 1, jz)
        dw = _paths(cells, _around(cells, w))
        free = sorted((_to(dw, cells, p), p) for p in reach if p not in used_beds and _to(dw, cells, p) is not None)
        if not free or free[0][0] > BED_PATH:
            e.append(f"casa_heraldo: the {prof} at {x} {z} has no free bed within {BED_PATH} blocks' walk of its "
                     f"workstation ({free[0][0] if free else None})")
            continue
        bed_path, bed_ = free[0]
        used_beds.add(bed_)
        bell = min(bells, key=lambda b: (b[0] - jx) ** 2 + (b[2] - jz) ** 2)
        to_job, to_bed = _to(bell_paths[bell], cells, w), _to(bell_paths[bell], cells, bed_)
        t.report.append((prof, w, bed_, bed_path, bell, to_job, to_bed))
        if to_job is None or to_bed is None or max(to_job, to_bed) > BELL_PATH:
            e.append(f"casa_heraldo: the {prof} at {x} {z}: its bell at {bell} is {to_job} blocks' walk from its "
                     f"workstation and {to_bed} from its bed (at most {BELL_PATH})")
    if len(t.stations) != len(t.villagers):
        e.append(f"casa_heraldo: {len(t.stations)} workstations for {len(t.villagers)} villagers")
    e += [f"casa_heraldo: {m}" for m in _inhabitants._fence_traps(view, cells)]
    return e


def errors(t=None):
    """[] if the template keeps what casa_heraldo.json promises and every rule above holds."""
    t = t or construct()
    d = dataset(t)
    e = []
    if t.size() != (N, HEIGHT, N):
        e.append(f"casa_heraldo: size {t.size()} instead of {(N, HEIGHT, N)}")
    for (x, y, z), (st, _) in t.blocks.items():
        n = _name(st)
        if any(n.startswith(f) or n.endswith(f) for f in FLAMMABLE) and (x, y, z) not in getattr(t, "trees", ()):
            e.append(f"casa_heraldo: {n} burns ({x} {y} {z})")
    if _name(t.get(*BELL)) != "bell":
        e.append("casa_heraldo: no bell where the blueprint says")
    if _name(t.get(BELL[0], BELL[1] + 1, BELL[2])) in ("air", "lantern"):
        e.append("casa_heraldo: the bell hangs from nothing")
    sx, sy, sz = SPAWN
    if not (t.is_free(sx, sy, sz) and t.is_free(sx, sy + 1, sz)) or t.is_free(sx, sy - 1, sz):
        e.append("casa_heraldo: the spawn point is not a free spot on the ground")
    (ax, ay, az), (bx, by, bz) = PORTAL
    if bx - ax + 1 < 4 or by - ay + 1 < 5:
        e.append("casa_heraldo: the portal frame is smaller than a Nether portal's minimum (4 x 5)")
    for x in range(ax, bx + 1):
        for y in range(ay, by + 1):
            edge = x in (ax, bx) or y in (ay, by)
            if edge and (x, y) not in ((ax, ay), (bx, ay), (ax, by), (bx, by)) and _name(t.get(x, y, az)) != "obsidian":
                e.append(f"casa_heraldo: portal frame broken at {x} {y} {az}")
            if not edge and not t.is_free(x, y, az):
                e.append(f"casa_heraldo: the portal's inside is not empty at {x} {y} {az}")
    if not any(_name(st) == "lectern" and nbt and "Book" in nbt for st, nbt in t.blocks.values()):
        e.append("casa_heraldo: the job board's lectern has no book")
    if not _name(t.get(*FARM_CELL)).startswith("farmland"):
        e.append("casa_heraldo: no farmland where the blueprint says (huerto)")
    if len(t.stalls) < 8:
        e.append("casa_heraldo: fewer than 8 market stalls")
    for s in t.stalls:
        (x0, y0, z0), (x1, y1, z1) = s["caja"]
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    if not t.is_free(x, y, z):
                        e.append(f"casa_heraldo: stall {s['id']} is not empty at {x} {y} {z}")
        if "sign" not in _name(t.get(*s["cartel"])):
            e.append(f"casa_heraldo: stall {s['id']} has no sign")
    if len(t.returns) != RETURNS or any(_name(t.get(*p)) != "barrel" for p in t.returns):
        e.append("casa_heraldo: the return barrels are not where the blueprint says")
    for side, (gx, gz) in GATES.items():
        for y in range(FLOOR + 1, FLOOR + 4):
            if not t.is_free(gx, y, gz):
                e.append(f"casa_heraldo: the {side} gate is closed")
    if not 18 <= len(t.villagers) <= 20:
        e.append(f"casa_heraldo: {len(t.villagers)} residents (18 to 20)")
    if len({(x, z) for _, x, z in t.villagers}) != len(t.villagers):
        e.append("casa_heraldo: two villagers start on the same cell")
    # the event square: the bays (around each road's mouth) free and on a solid floor, a road in each side's middle
    x0, _, z0, n = d["plaza_eventos"]
    for x in range(x0, x0 + n):
        for z in range(z0, z0 + n):
            ring = max(abs(x - (x0 + n // 2)), abs(z - (z0 + n // 2)))
            if 4 <= ring <= 9 and min(abs(x - (x0 + n // 2)), abs(z - (z0 + n // 2))) <= 4:
                if lint.top_height(t.get(x, FLOOR, z)) != 1.0 or any(not t.is_free(x, y, z) for y in range(FLOOR + 1, FLOOR + 5)):
                    e.append(f"casa_heraldo: the event square's bay is not free at {x} {z}")
    cells = walk_cells(t)
    e += placement_errors(t.blds, t, cells)
    e += resident_errors(t, cells)
    e += fire_errors(t)
    return e


# ------------------------------------------------------------------ texts
TEXTS = {
    "nombre": ("La Casa del Heraldo", "The Herald's House"),
    "edificio.posada": ("Posada", "Inn"),
    "edificio.hostal": ("Hostal", "Guest House"),
    "edificio.capilla": ("Capilla", "Chapel"),
    "edificio.herreria": ("Herrería", "Smithy"),
    "edificio.carniceria": ("Carnicería", "Butcher"),
    "edificio.biblioteca": ("Biblioteca", "Library"),
    "edificio.cartografo": ("Cartógrafo", "Cartographer"),
    "edificio.taller": ("Taller", "Workshop"),
    "edificio.oficina": ("Mercado", "Market Office"),
    "edificio.establo": ("Establo", "Stable"),
    "edificio.herbolario": ("Herbolario", "Herbalist"),
    "edificio.panaderia": ("Panadería", "Bakery"),
    "edificio.granero": ("Granero", "Granary"),
    "edificio.tejedor": ("Tejedor", "Weaver"),
    "edificio.ayuntamiento": ("Ayuntamiento", "Town Hall"),
    "edificio.guardia": ("Guardia", "Guardhouse"),
    "monumento": ("Al Heraldo", "To the Herald"),
    "monumento2": ("de los caminos", "of the roads"),
    "puerta.north": ("Puerta Norte", "North Gate"),
    "puerta.south": ("Puerta Sur", "South Gate"),
    "puerta.west": ("Puerta Oeste", "West Gate"),
    "puerta.east": ("Puerta Este", "East Gate"),
    "hacia_mundo": ("Al mundo", "To the world"),
    "camino.cartel": ("Casa del Heraldo", "Herald's House"),
    "camino.cartel2": ("%s bloques", "%s blocks"),
    "puesto": ("Puesto", "Stall"),
    "se_alquila": ("Se alquila", "For rent"),
    "cerrado": ("Cerrado", "Closed"),
    "portal.cartel1": ("Portal al Nether", "Nether Portal"),
    "portal.cartel2": ("Solo un operador", "Operators only"),
    "devolucion.cartel1": ("Devoluciones", "Returned"),
    "devolucion.cartel2": ("de los puestos", "stall items"),
    # chat
    "prohibido": ("La Casa del Heraldo está protegida: aquí no se puede construir ni cambiar nada",
                  "The Herald's House is protected: nothing can be built or changed here"),
    "solo_ver": ("En la Casa del Heraldo puedes mirar, pero no llevarte nada",
                 "In the Herald's House you can look, but not take anything"),
    "portal.prohibido": ("Solo un operador puede encender el portal de la Casa del Heraldo",
                         "Only an operator can light the Herald's House portal"),
    "tablon": ("Tablón de encargos de la Casa del Heraldo:", "The Herald's House job board:"),
    "info": ("La Casa del Heraldo está en %s %s %s", "The Herald's House is at %s %s %s"),
    "no_existe": ("Este mundo aún no tiene Casa del Heraldo (un operador la coloca con /heraldia herald place)",
                  "This world has no Herald's House yet (an operator places it with /heraldia herald place)"),
    "desactivada": ("La Casa del Heraldo está desactivada (casa_heraldo.activado)",
                    "The Herald's House is disabled (casa_heraldo.activado)"),
    "ya_existe": ("Este mundo ya tiene su Casa del Heraldo, en %s %s %s", "This world already has its Herald's House, at %s %s %s"),
    "trabajando": ("La Casa del Heraldo se está construyendo; espera a que termine", "The Herald's House is being built; wait for it to finish"),
    "buscando": ("Buscando sitio cerca del spawn…", "Looking for a site near spawn…"),
    "sin_sitio": ("No hay sitio a menos de %s bloques del spawn sin la arena ni otra estructura; prueba /heraldia herald place here",
                  "No site within %s blocks of spawn clear of the arena and other structures; try /heraldia herald place here"),
    "propuesta": ("Sitio propuesto: centro en %s %s %s (128 × 128, protección hasta %s bloques alrededor). Las columnas de luz "
                  "marcan las esquinas: todo lo que haya dentro del cuadrado se sustituye.",
                  "Proposed site: centre at %s %s %s (128 × 128, protected up to %s blocks around). The columns of light mark "
                  "the corners: everything inside the square is replaced."),
    "propuesta.confirmar": ("Para construirla: %s", "To build it: %s"),
    "sin_propuesta": ("No hay ninguna propuesta: usa antes %s", "There is no proposal: use %s first"),
    "colocando": ("Construyendo la Casa del Heraldo en %s %s %s…", "Building the Herald's House at %s %s %s…"),
    "colocada": ("La Casa del Heraldo está lista en %s %s %s", "The Herald's House is ready at %s %s %s"),
    "spawn": ("El spawn del mundo no se ha movido. Para que los jugadores aparezcan en la plaza: %s",
              "The world spawn has not moved. To have players appear on the plaza: %s"),
    # the market
    "mercado.desactivado": ("Los puestos del mercado no se alquilan en este servidor", "Market stalls are not for rent on this server"),
    "mercado.libre": ("Puesto %s: libre. Entrada %s esmeraldas y %s de alquiler cada %s días. %s",
                      "Stall %s: free. Entry %s emeralds and %s rent every %s days. %s"),
    "mercado.alquilar": ("[Alquilar]", "[Rent it]"),
    "mercado.ocupado": ("Puesto %s: de %s, pagado durante %s días más", "Stall %s: %s's, paid for %s more days"),
    "mercado.tuyo": ("Puesto %s: tuyo, pagado durante %s días más. %s %s", "Stall %s: yours, paid for %s more days. %s %s"),
    "mercado.pagar": ("[Pagar %s]", "[Pay %s]"),
    "mercado.dejar": ("[Dejarlo]", "[Give it up]"),
    "mercado.vencido": ("Puesto %s: el alquiler venció; queda libre en cuanto se recojan sus cosas",
                        "Stall %s: the rent ran out; it is free as soon as its things are collected"),
    "mercado.sin_esmeraldas": ("Hacen falta %s esmeraldas (llevas %s)", "You need %s emeralds (you have %s)"),
    "mercado.alquilado": ("El puesto %s es tuyo hasta dentro de %s días. Paga antes con /heraldia herald stall pay %s",
                          "Stall %s is yours for %s days. Pay before then with /heraldia herald stall pay %s"),
    "mercado.pagado": ("Puesto %s pagado: es tuyo %s días más", "Stall %s paid: it is yours for %s more days"),
    "mercado.tope": ("Puedes pagar como mucho %s periodos por adelantado", "You can pay at most %s periods in advance"),
    "mercado.ya_tienes": ("Ya tienes el puesto %s: solo uno por jugador", "You already have stall %s: one per player"),
    "mercado.no_es_tuyo": ("Ese puesto no es tuyo", "That stall is not yours"),
    "mercado.no_existe": ("No hay ningún puesto %s", "There is no stall %s"),
    "mercado.aviso": ("Tu puesto %s del mercado de la Casa del Heraldo vence en %s días: /heraldia herald stall pay %s",
                      "Your stall %s at the Herald's House market is due in %s days: /heraldia herald stall pay %s"),
    "mercado.gracia": ("El alquiler de tu puesto %s venció: tienes %s días para pagar o lo pierdes (/heraldia herald stall pay %s)",
                       "The rent on your stall %s ran out: you have %s days to pay or you lose it (/heraldia herald stall pay %s)"),
    "mercado.perdido": ("Has perdido el puesto %s por no pagar. Tus cosas están en el barril de devoluciones de la "
                        "oficina del mercado, en %s %s %s (solo tú puedes abrirlo)",
                        "You lost stall %s for not paying. Your things are in the return barrel of the market office, at "
                        "%s %s %s (only you can open it)"),
    "mercado.dejado": ("Has dejado el puesto %s. Tus cosas están en el barril de devoluciones, en %s %s %s",
                       "You gave up stall %s. Your things are in the return barrel, at %s %s %s"),
    "mercado.desalojado": ("Un operador ha desalojado el puesto %s. Tus cosas están en el barril de devoluciones, en %s %s %s",
                           "An operator has cleared stall %s. Your things are in the return barrel, at %s %s %s"),
    "mercado.devolucion_llena": ("Los barriles de devoluciones están llenos: el puesto %s sigue cerrado hasta que un operador "
                                 "vacíe alguno", "The return barrels are full: stall %s stays closed until an operator empties one"),
    "mercado.barril_ajeno": ("Ese barril de devoluciones guarda las cosas de otro jugador", "That return barrel holds another player's things"),
    "mercado.pendiente": ("Tienes cosas en el barril de devoluciones del mercado, en %s %s %s",
                          "You have things in the market's return barrel, at %s %s %s"),
    "mercado.lista": ("Puestos del mercado:", "Market stalls:"),
    "mercado.linea_libre": ("  %s: libre", "  %s: free"),
    "mercado.linea": ("  %s: %s, %s días", "  %s: %s, %s days"),
}
# signs: what has to fit on a sign line in each language (key, bold, worst-case arguments)
SIGN = [("puesto", False, []), ("se_alquila", False, []), ("cerrado", False, []),
        ("portal.cartel1", False, []), ("portal.cartel2", False, []), ("devolucion.cartel1", False, []),
        ("devolucion.cartel2", False, []), ("hacia_mundo", False, []), ("camino.cartel", False, []),
        ("camino.cartel2", False, ["150"])] + [(f"puerta.{s}", False, []) for s in GATES] + \
       [(f"edificio.{b.name}", False, []) for b in _buildings() if b.sign] + \
       [("edificio.hostal", False, []), ("monumento", False, []), ("monumento2", False, [])]


def lang():
    out = {"es_es": {}, "en_us": {}}
    for k, (es, en) in TEXTS.items():
        out["es_es"][f"{NS}.casa_heraldo.{k}"], out["en_us"][f"{NS}.casa_heraldo.{k}"] = es, en
    return out


def text_errors(translations=None):
    """[] if every sign line fits (90 px) in each language. `translations`: {code: texts} of the other languages."""
    import languages
    base = lang()
    e = []
    for code, texts in [("es_es", base["es_es"]), ("en_us", base["en_us"])] + list((translations or {}).items()):
        for k, bold, args in SIGN:
            s = languages.format_text(texts[f"{NS}.casa_heraldo.{k}"], args)
            if languages.sign_width(s, bold) > languages.SIGN_WIDTH:
                e.append(f"casa_heraldo: {code}: the sign line {k} does not fit: «{s}»")
    return e


def write(out, jdump):
    """Writes the two templates and heraldia/casa_heraldo.json; returns the texts. Fails if the template does not keep
    what it promises."""
    t = construct()
    e = errors(t) + text_errors()
    if e:
        raise SystemExit("\n".join(e))
    t.save(out)
    dock().save(out)
    jdump(out, f"{NS}/casa_heraldo.json", dataset(t))
    return lang()
