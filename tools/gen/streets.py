"""Streets, main square, avenues, finishing pieces (towers, gates) and decoration."""
import math
from core import Template, nsid, golem, center_marker
from build import *

AIR = "minecraft:air"
VOID = "minecraft:structure_void"


def P(th, what):
    return nsid(f"{th['id']}/{what}")


def paving(rng, th):
    r = rng.random()
    if r < 0.18:
        return th["path2"]
    return th["path"]


def street_conn(t, x, z, facing, th, name="heraldia:street", pool=None, target="heraldia:street", place=0):
    t.jigsaw(x, 1, z, f"{facing}_up", name, target, pool or P(th, "streets"), final_state=AIR,
             joint="aligned", place=place)


def side_slot(t, x, z, facing, pool, sel=0, place=0):
    t.jigsaw(x, 1, z, f"{facing}_up", "heraldia:side", "heraldia:entrance", pool, final_state=VOID,
             joint="aligned", sel=sel, place=place)


def decor_slot(t, x, y, z, pool, final=VOID):
    t.jigsaw(x, y, z, "up_north", "heraldia:slot", "heraldia:bottom", pool, final_state=final, joint="rollable")


def golem_slot(t, x, y, z, final):
    t.jigsaw(x, y, z, "up_north", "heraldia:slot", "heraldia:bottom", nsid("golem"), final_state=final,
             joint="rollable", place=1)


def _worn(x, z, k=0):
    """A fixed pseudo-random number in [0, 1) for a cell (no draw from the theme's random source: the pieces built after
    a street keep the choices they had)."""
    h = (x * 73856093 ^ z * 19349663 ^ k * 83492791) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def path_strip(t, th, rng, x0, x1, z0, z1):
    """A street's ground: the theme's paving, with a kerb along both edges (the second paving material and, in runs, the
    theme's stone) so that a street reads as laid and edged, not as a stripe. Flush with the paving: nothing to step over."""
    along_x = x1 - x0 > z1 - z0
    kerb = stone_like(th)
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            b = paving(rng, th)
            edge = (z in (z0, z1)) if along_x else (x in (x0, x1))
            if edge and x1 - x0 != z1 - z0:              # a crossing has no kerb: streets run through it
                run = _worn((x if along_x else z) // 3, z if along_x else x, 7)        # the same stone for 3 cells along
                b = kerb if run < 0.30 else th["path2"] if _worn(x, z, 9) < 0.75 else b
            t.set(x, 0, z, b)
            t.set(x, 1, z, "air")


# ------------------------------------------------------------------ generic streets
def straight(th, rng, name, L):
    t = Template(name); t.min_size = (7, 6, L)
    path_strip(t, th, rng, 1, 5, 0, L - 1)
    street_conn(t, 3, 0, "north", th)
    street_conn(t, 3, L - 1, "south", th)
    slots = [3, 12] if L >= 16 else [L // 2]
    for z in slots:
        side_slot(t, 0, z, "west", P(th, "houses"))
        side_slot(t, 6, z, "east", P(th, "houses"))
    for z in ([7, 8] if L >= 16 else [1]):
        decor_slot(t, 0 if z % 2 else 6, 0, z, P(th, "decor"))
    return t


def crossroad(th, rng, name, kind):
    t = Template(name); t.min_size = (7, 6, 7)
    path_strip(t, th, rng, 0, 6, 0, 6)
    street_conn(t, 3, 0, "north", th)
    if kind in ("x", "t"):
        street_conn(t, 3, 6, "south", th)
    street_conn(t, 6, 3, "east", th)
    if kind == "x":
        street_conn(t, 0, 3, "west", th)
    else:
        side_slot(t, 0, 3, "west", P(th, "houses"))
    if kind == "l":
        side_slot(t, 3, 6, "south", P(th, "houses"))
    return t


def terminator_end(th, rng, name):
    t = Template(name); t.min_size = (7, 6, 4)
    for x in range(1, 6):
        for z in range(0, 3):
            if z < 2 or 2 <= x <= 4:
                t.set(x, 0, z, paving(rng, th) if z < 2 else th["path2"])
                t.set(x, 1, z, "air")
    t.jigsaw(3, 1, 0, "north_up", "heraldia:street", "heraldia:street", "minecraft:empty", final_state=AIR)
    t.set(3, 1, 3, th["fence"]); t.set(3, 2, 3, lantern(th, False))
    return t


def watchtower(th, rng, name, stone=True, with_golem=True):
    t = Template(name)
    wallm = stone_like(th) if stone else th["log"]
    base = stone_like(th)
    t.fill(0, 0, 0, 6, 0, 1, base)
    t.jigsaw(3, 0, 0, "north_up", "heraldia:street", "heraldia:street", "minecraft:empty",
             final_state=stairs(th["trim"], "south"))
    x0, x1, z0, z1 = 1, 5, 2, 6
    Ht = 12
    t.fill(x0, 0, z0, x1, 0, z1, base)
    for y in range(1, Ht + 1):
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                edge = x in (x0, x1) or z in (z0, z1)
                if edge:
                    t.set(x, y, z, wallm if stone else log(wallm, "y"))
                else:
                    t.set(x, y, z, "air")
    door(t, 3, 1, z0, th["door"], "north")
    for y in (4, 8):
        for (x, z) in ((3, z1), (x0, 4), (x1, 4)):
            t.set(x, y, z, "iron_bars" if stone else th["window"])
    # crenellated platform; the ladder passes through the platform and comes out on top
    t.fill(0, Ht + 1, 1, 6, Ht + 1, 7, th["roof_full"] if stone else th["planks"])
    for y in range(1, Ht + 2):
        t.set(2, y, 5, "ladder[facing=north]")
    for x in range(0, 7):
        for z in (1, 7):
            if x % 2 == 0:
                t.set(x, Ht + 2, z, wallm if stone else log(wallm, "y"))
    for z in range(2, 7):
        for x in (0, 6):
            if z % 2 == 1:
                t.set(x, Ht + 2, z, wallm if stone else log(wallm, "y"))
    t.set(4, Ht + 2, 3, lantern(th, False))
    if with_golem:
        t.entity(0, 1, 1, golem())
    return t


def gate(th, rng, name):
    """Section of wall with a passage arch and two solid turrets."""
    t = Template(name)
    W = 15
    wallm = stone_like(th)
    for x in range(6, 9):
        for z in range(0, 5):
            t.set(x, 0, z, paving(rng, th))
            for y in range(1, 5):
                t.set(x, y, z, "air")
    t.jigsaw(7, 1, 0, "north_up", "heraldia:street", "heraldia:street", "minecraft:empty", final_state=AIR)
    for x in range(0, W):
        for y in range(0, 6):
            if 6 <= x <= 8 and y <= 3:
                continue
            t.set(x, y, 2, wallm)
        if x % 2 == 0:
            t.set(x, 6, 2, wallm)
    t.set(6, 3, 2, stairs(th["trim"], "east", half="top"))
    t.set(8, 3, 2, stairs(th["trim"], "west", half="top"))
    for tx in (0, 12):
        for y in range(0, 9):
            t.fill(tx, y, 1, tx + 2, y, 3, wallm)
        for (x, z) in ((tx, 1), (tx + 2, 1), (tx, 3), (tx + 2, 3)):
            t.set(x, 9, z, wallm)
        t.set(tx + 1, 9, 2, lantern(th, False))
    for x in (5, 9):
        t.set(x, 4, 1, f"{th['banner']}_wall_banner[facing=north]")
        t.set(x, 2, 1, "wall_torch[facing=north]")
    return t


def stone_like(th):
    for k in ("wall2", "found", "wall"):
        m = th[k]
        if not any(w in m for w in ("log", "planks", "bamboo", "wood")):
            return m
    return "cobblestone"


# ------------------------------------------------------------------ plaza mayor
def plaza(th, rng, name, large=False):
    t = Template(name)
    N = 23
    c = N // 2
    for x in range(N):
        for z in range(N):
            d = max(abs(x - c), abs(z - c))
            if d == c:
                b = th["found"]
            elif d in (4, 8):
                b = th["path2"]
            else:
                b = th["path"]
            t.set(x, 0, z, b)
            for y in range(1, 5):
                t.set(x, y, z, "air")
    # fountain: stone basin with curb and a central pillar with a lantern
    rim = stone_like(th)
    for x in range(c - 3, c + 4):
        for z in range(c - 3, c + 4):
            edge = abs(x - c) == 3 or abs(z - c) == 3
            t.set(x, 0, z, rim)
            t.set(x, 1, z, rim if edge else "water")
    t.set(c, 1, c, rim); t.set(c, 2, c, rim)
    t.set(c, 3, c, lantern(th, False))
    # benches and street lamps
    for (x, z) in ((2, 2), (2, N - 3), (N - 3, 2), (N - 3, N - 3)):
        t.set(x, 1, z, th["fence"]); t.set(x, 2, z, th["fence"]); t.set(x, 3, z, lantern(th, False))
    for (x, z, f) in ((c - 2, c - 5, "north"), (c + 2, c - 5, "north"), (c - 2, c + 5, "south"), (c + 2, c + 5, "south"),
                      (c - 5, c - 2, "west"), (c - 5, c + 2, "west"), (c + 5, c - 2, "east"), (c + 5, c + 2, "east")):
        t.set(x, 1, z, stairs(th["wstairs"], f))
    # trees in planters
    for (x, z) in ((5, 5), (5, N - 6), (N - 6, 5), (N - 6, N - 6)):
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                t.set(x + dx, 0, z + dz, "grass_block")
        for y in range(1, 4):
            t.set(x, y, z, log(th["log"], "y"))
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                for y in (4, 5):
                    if not (y == 5 and abs(dx) + abs(dz) == 2):
                        t.set(x + dx, y, z + dz, leaves(th))
    # bell hung from a wooden gantry
    for z in (c - 1, c + 1):
        for y in (1, 2, 3):
            t.set(c - 6, y, z, th["fence"])
    for z in (c - 1, c, c + 1):
        t.set(c - 6, 4, z, f"{th['wslab']}[type=bottom]")
    t.set(c - 6, 3, c, "bell[attachment=ceiling,facing=east]")
    # centre marker (for the golem function)
    t.entity(1, 1, 1, center_marker(["heraldia_centro", "heraldia_grande" if large else "heraldia_std"]))
    # golems
    golem_slot(t, c - 8, 0, c - 3, th["path"])
    golem_slot(t, c + 8, 0, c + 3, th["path"])
    if large:
        golem_slot(t, c + 3, 0, c - 8, th["path"])
    # quest board (separate piece: lectern with its book and the sheriff; board.py)
    import board
    board.slot(t, th)
    # salidas a avenidas
    for (x, z, f, av) in ((c, 0, "north", "a"), (N - 1, c, "east", "b"), (c, N - 1, "south", "c"), (0, c, "west", "d")):
        t.jigsaw(x, 1, z, f"{f}_up", "heraldia:street", "heraldia:avenue", P(th, f"avenue_{av}"), final_state=AIR,
                 joint="aligned", sel=10, place=10)
    t.min_size = (N, 8, N)
    return t


# ------------------------------------------------------------------ avenidas
def avenue(th, rng, name, left_pool, right_pool):
    L = 40
    t = Template(name); t.min_size = (7, 6, L)
    path_strip(t, th, rng, 1, 5, 0, L - 1)
    t.jigsaw(3, 1, 0, "north_up", "heraldia:avenue", "heraldia:street", "minecraft:empty", final_state=AIR)
    street_conn(t, 3, L - 1, "south", th)
    side_slot(t, 0, 8, "west", P(th, "houses"))
    side_slot(t, 6, 8, "east", P(th, "houses"))
    side_slot(t, 0, 27, "west", left_pool, sel=5, place=5)
    side_slot(t, 6, 27, "east", right_pool, sel=5, place=5)
    for z in (3, 17, 35):
        decor_slot(t, 0, 0, z, P(th, "decor"))
        decor_slot(t, 6, 0, z, P(th, "decor"))
    return t


# ------------------------------------------------------------------ small decoration (1x1)
STREET_THINGS = ("bench", "woodpile", "hay", "milestone")
# The street's decoration slots: lamps keep 7 parts in 13, as before the street's things came (they took their share
# from the empty slots and one of the planter's two), so a street is as lit as it was.
DECOR_WEIGHTS = (("lamp", 5), ("lamp_tall", 2), ("flower", 1), ("bench", 1), ("woodpile", 1), ("hay", 1), ("milestone", 1))
DECOR_EMPTY = 1
def decor_piece(th, rng, name, kind):
    t = Template(name)
    if kind == "lamp":
        t.jigsaw(0, 0, 0, "down_north", "heraldia:bottom", "heraldia:slot", "minecraft:empty", final_state=nsfix(th["fence"]), joint="rollable")
        t.set(0, 1, 0, th["fence"]); t.set(0, 2, 0, lantern(th, False))
    elif kind == "lamp_tall":
        t.jigsaw(0, 0, 0, "down_north", "heraldia:bottom", "heraldia:slot", "minecraft:empty", final_state=nsfix(stone_like(th)), joint="rollable")
        for y in (1, 2):
            t.set(0, y, 0, th["fence"])
        t.set(0, 3, 0, lantern(th, False))
    elif kind in STREET_THINGS:
        # what a lived-in street has beside its lamps: somewhere to sit, the winter's wood, fodder, a stone that says
        # how far. One block wide like a lamp, no light, no container, nothing a villager takes for a workstation
        foot = stone_like(th) if kind == "milestone" else th["path2"]
        t.jigsaw(0, 0, 0, "down_north", "heraldia:bottom", "heraldia:slot", "minecraft:empty", final_state=nsfix(foot), joint="rollable")
        if kind == "bench":
            t.set(0, 1, 0, stairs(th["wstairs"], "north"))
        elif kind == "woodpile":
            t.set(0, 1, 0, log(th["log"], "x"))
            if rng.random() < 0.5:
                t.set(0, 2, 0, log(th["log"], "x"))
        elif kind == "hay":
            t.set(0, 1, 0, "hay_block[axis=y]")
        else:
            t.set(0, 1, 0, "cobblestone_wall[up=true,north=none,south=none,east=none,west=none,waterlogged=false]")
            t.set(0, 2, 0, "stone_button[face=floor,facing=north,powered=false]")
    else:   # jardinera
        t.jigsaw(0, 0, 0, "down_north", "heraldia:bottom", "heraldia:slot", "minecraft:empty", final_state=nsfix(stone_like(th)), joint="rollable")
        t.set(0, 1, 0, potted(rng.choice(th["plants"])))
    t.min_size = (1, 4, 1)
    return t


def nsfix(s):
    from core import parse_state, state_str
    b, p = parse_state(s)
    return state_str(b, p)
