"""Filler pieces next to the streets (large themed decoration) and villager/golem pieces."""
import math
from core import Template, nsid, villager, golem, animal
from build import *


def fentrance(t, th, x):
    t.jigsaw(x, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty", final_state=th["path"])


def base(t, th, w, d, block=None, z0=1):
    for x in range(w):
        for z in range(z0, z0 + d):
            t.set(x, 0, z, block or "grass_block")
            for y in (1, 2, 3):
                t.set(x, y, z, "air")


def tree(t, th, x, y, z, h=4, kind=None):
    lg = log(kind or th["log"], "y")
    for k in range(h):
        t.set(x, y + k, z, lg)
    lv = leaves(th)
    for dy in (h - 1, h):
        r = 2 if dy == h - 1 else 1
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                if abs(dx) + abs(dz) <= r + 1 and (dx or dz or dy == h):
                    if t.get(x + dx, y + dy, z + dz) in (None, "minecraft:air"):
                        t.set(x + dx, y + dy, z + dz, lv)


def soil_of(th):
    return {"desierto": "sand", "badlands": "red_sand"}.get(th["family"], "grass_block")


def stone_like(th):
    from streets import stone_like as sl
    return sl(th)


def filler(th, rng, name, kind):
    """Small pieces between houses. Each one is a complete set that makes sense on its own."""
    t = Template(name)
    W = 7
    c = 3
    fentrance(t, th, c)
    st = stone_like(th)
    soil = soil_of(th)
    dry = soil != "grass_block"
    if kind == "garden" and dry:
        kind = "palm"
    if kind == "well":
        base(t, th, W, 6, th["path"])
        for x in range(1, 6):
            for z in range(2, 7):
                d = max(abs(x - 3), abs(z - 4))
                if d == 2:
                    t.set(x, 0, z, st); t.set(x, 1, z, st)
                elif d < 2:
                    t.set(x, -1, z, st); t.set(x, 0, z, "water"); t.set(x, 1, z, "air")
        for (x, z) in ((1, 2), (5, 2), (1, 6), (5, 6)):
            for y in (2, 3):
                t.set(x, y, z, th["fence"])
        hip_roof(t, th, 1, 2, 5, 6, 4, overhang=0)
    elif kind == "fountain_small":
        base(t, th, W, 6, th["path"])
        for x in range(1, 6):
            for z in range(2, 7):
                d = max(abs(x - 3), abs(z - 4))
                t.set(x, 0, z, st)
                if d == 2:
                    t.set(x, 1, z, st)
                elif d == 1:
                    t.set(x, 1, z, "water")
        t.set(3, 1, 4, st); t.set(3, 2, 4, st); t.set(3, 3, 4, lantern(th, False))
    elif kind in ("garden", "flowerbed", "herbgarden"):
        base(t, th, W, 7, soil)
        for x in range(W):
            for z in (1, 7):
                t.set(x, 1, z, th["fence"])
        for z in range(1, 8):
            t.set(0, 1, z, th["fence"]); t.set(W - 1, 1, z, th["fence"])
        # the gate stands open: villagers never open a gate, and one that got in (seen in village_routes: a villager
        # shut in a garden day after day, without a bed) had no way out with it shut
        t.set(c, 1, 1, f"{th['gate']}[facing=north,open=true]")
        flowers = [p for p in th["plants"] if not p.endswith("_pot") and p != "sweet_berry_bush"] or ["poppy", "dandelion"]
        for x in range(1, W - 1):
            for z in range(2, 7):
                if x == c:
                    t.set(x, 0, z, th["path"])
                elif kind == "herbgarden" and not dry:
                    t.set(x, 0, z, "water" if (x in (2, 4) and z == 4) else "farmland[moisture=7]")
                    if not (x in (2, 4) and z == 4):
                        t.set(x, 1, z, ["carrots[age=7]", "potatoes[age=7]", "beetroots[age=3]", "wheat[age=7]"][(x + (x > c)) % 4])
                elif not dry:
                    t.set(x, 1, z, flowers[(x + z) % len(flowers)] if (x + z) % 2 == 0 else "short_grass")
                elif (x + z) % 3 == 0:
                    t.set(x, 1, z, "dead_bush")
        if kind == "herbgarden" and not dry:
            t.set(c, 0, 6, soil)
            t.set(c, 1, 6, "composter[level=4]")
    elif kind in ("haystack", "camel_post"):
        base(t, th, W, 5, soil)
        for (x, z, h) in ((1, 4, 2), (2, 4, 2), (1, 5, 1), (2, 5, 1), (3, 5, 1)):
            for y in range(1, h + 1):
                t.set(x, y, z, "hay_block[axis=x]")
    elif kind == "cart":
        base(t, th, W, 5, th["path2"])
        for x in (2, 3, 4):
            t.set(x, 1, 3, f"{th['wslab']}[type=top]")
        for x in (2, 4):
            t.set(x, 1, 2, f"{th['trapdoor']}[facing=north,half=bottom,open=true]")
            t.set(x, 1, 4, f"{th['trapdoor']}[facing=south,half=bottom,open=true]")
        t.set(3, 2, 3, "hay_block[axis=x]"); t.set(2, 2, 3, "barrel[facing=up]")
        t.set(5, 1, 3, th["fence"])
    elif kind == "minecart":
        base(t, th, W, 5, th["path2"])
        for z in range(1, 6):
            t.set(3, 1, z, "rail[shape=north_south]")
        t.set(3, 1, 5, stone_like(th))
        t.entity(3, 1, 3, {"id": "minecraft:chest_minecart", "LootTable": "heraldia:cofres/comun"})
        t.set(5, 1, 4, "barrel[facing=up]"); t.set(5, 1, 5, "raw_iron_block")
    elif kind in ("logpile", "stump"):
        base(t, th, W, 5, soil)
        for x in range(1, 6):
            t.set(x, 1, 4, log(th["log"], "x"))
        for x in range(2, 5):
            t.set(x, 2, 4, log(th["log"], "x"))
        t.set(3, 1, 2, log(th["stripped"], "y"))
    elif kind == "palisade":
        base(t, th, W, 5, soil)
        for x in range(W):
            for y in range(1, 4 + (x % 2)):
                t.set(x, y, 5, log(th["log"], "y"))
    elif kind == "beehives":
        base(t, th, W, 5, soil)
        for x in (1, 3, 5):
            t.set(x, 1, 4, "beehive[facing=north,honey_level=2]")
        if not dry:
            for x in (1, 2, 3, 4, 5):
                t.set(x, 1, 2, ["poppy", "cornflower", "dandelion", "allium", "poppy"][x - 1])
    elif kind == "horreo":
        base(t, th, W, 7, soil)
        for (x, z) in ((1, 2), (5, 2), (1, 6), (5, 6), (3, 2), (3, 6)):
            t.set(x, 1, z, "stone_brick_wall"); t.set(x, 2, z, "smooth_stone_slab[type=top]")
        for x in range(1, 6):
            for z in range(2, 7):
                t.set(x, 3, z, "stone_bricks")
                for y in (4, 5):
                    edge = x in (1, 5) or z in (2, 6)
                    t.set(x, y, z, ("oak_planks" if x % 2 else "spruce_planks") if edge else "air")
        gable_roof(t, th, 1, 2, 5, 6, 6, along="x", overhang=0, gable_fill="stone_bricks")
    elif kind == "cruceiro":
        base(t, th, W, 5, th["path2"])
        t.fill(2, 1, 2, 4, 1, 4, "stone_brick_slab[type=bottom]")
        t.set(3, 1, 3, "stone_bricks")
        t.fill(3, 2, 3, 3, 5, 3, "stone_brick_wall")
        t.set(3, 6, 3, "chiseled_stone_bricks")
        t.set(2, 6, 3, "stone_brick_wall"); t.set(4, 6, 3, "stone_brick_wall")
        t.set(3, 7, 3, "stone_brick_wall")
    elif kind == "torii":
        base(t, th, W, 3, th["path"])
        red = th["id"] != "cerezos_templo"
        for x in (1, 5):
            for y in range(1, 6):
                t.set(x, y, 2, "red_concrete" if red else log(th["log"], "y"))
        for x in range(2, 5):
            t.set(x, 4, 2, "red_concrete" if red else log(th["log"], "x"))
        for x in range(0, 7):
            t.set(x, 6, 2, f"{th['roof_slab']}[type=bottom]")
    elif kind == "stone_lantern":
        base(t, th, W, 4, th["path2"])
        for x in (1, 5):
            t.set(x, 1, 3, "stone_brick_wall"); t.set(x, 2, 3, "lantern[hanging=false]")
    elif kind == "pond":
        base(t, th, W, 6, soil)
        for x in range(1, 6):
            for z in range(2, 6):
                if not ((x in (1, 5)) and (z in (2, 5))):
                    t.set(x, 0, z, "water"); t.set(x, -1, z, "clay")
        t.set(3, 1, 3, "lily_pad"); t.set(2, 1, 4, "lily_pad")
    elif kind == "obelisk":
        base(t, th, W, 5, th["path"])
        t.fill(2, 1, 2, 4, 1, 4, th["wall2"])
        for y in range(2, 9):
            t.set(3, y, 3, "chiseled_sandstone" if y in (4, 7) else th["wall"])
        t.set(3, 9, 3, "gold_block")
    elif kind in ("palm", "planter"):
        base(t, th, W, 5, th["path"])
        for x in range(2, 5):
            for z in range(2, 5):
                t.set(x, 0, z, soil)
        tree(t, th, 3, 1, 3, h=5 if kind == "palm" else 4, kind="jungle_log" if kind == "palm" else None)
    elif kind in ("tent", "awning"):
        base(t, th, W, 5, th["path"])
        wool = f"{th['carpet'][0]}_wool"
        for (x, z) in ((1, 1), (5, 1), (1, 5), (5, 5)):
            for y in (1, 2):
                t.set(x, y, z, th["fence"])
        for x in range(1, 6):
            for z in range(1, 6):
                t.set(x, 3, z, wool if (x % 2) else "white_wool")
        t.set(2, 1, 5, "barrel[facing=up]"); t.set(3, 1, 5, f"{th['wslab']}[type=top]"); t.set(4, 1, 5, "barrel[facing=up]")
    elif kind in ("jars", "barrels", "crates"):
        base(t, th, W, 4, th["path2"])
        b = "decorated_pot" if kind == "jars" else "barrel[facing=up]"
        for (x, z) in ((1, 4), (2, 4), (3, 4), (1, 3)):
            t.set(x, 1, z, b)
        if kind != "jars":
            t.set(1, 2, 4, b)
    elif kind in ("fishrack", "dryrack"):
        base(t, th, W, 4, th["path2"])
        for x in (1, 5):
            for y in (1, 2):
                t.set(x, y, 4, th["fence"])
        for x in range(2, 5):
            t.set(x, 2, 4, th["fence"])
        t.set(1, 1, 2, "barrel[facing=up]")
    elif kind == "sheep_pen":
        base(t, th, W, 6, soil)
        for x in range(W):
            t.set(x, 1, 1, th["fence"]); t.set(x, 1, 6, th["fence"])
        for z in range(1, 7):
            t.set(0, 1, z, th["fence"]); t.set(W - 1, 1, z, th["fence"])
        t.set(3, 1, 1, f"{th['gate']}[facing=north,open=false]")
        t.set(5, 1, 5, "hay_block[axis=y]")
        for i in range(2):
            t.entity(2 + i * 2, 1, 3, animal("sheep"))
    elif kind == "campfire":
        base(t, th, W, 5, th["path2"])
        t.set(3, 1, 3, "campfire[lit=true,signal_fire=false]")
        t.set(1, 1, 3, log(th["stripped"], "z")); t.set(5, 1, 3, log(th["stripped"], "z"))
        t.set(3, 1, 5, log(th["stripped"], "x"))
    elif kind == "targets":
        base(t, th, W, 5, soil)
        for x in (1, 3, 5):
            t.set(x, 1, 5, "hay_block[axis=y]"); t.set(x, 2, 5, "target")
    elif kind in ("idol", "runestone", "gargoyle"):
        base(t, th, W, 5, th["path2"])
        m = {"idol": ("mossy_cobblestone", "chiseled_stone_bricks"), "runestone": ("stone", "chiseled_stone_bricks"),
             "gargoyle": ("cobbled_deepslate", "chiseled_deepslate")}[kind]
        t.fill(2, 1, 2, 4, 1, 4, m[0])
        for y in (2, 3):
            t.set(3, y, 3, m[0])
        t.set(3, 4, 3, m[1])
    elif kind == "cauldrons":
        base(t, th, W, 4, th["path2"])
        t.set(2, 1, 4, "water_cauldron[level=3]"); t.set(4, 1, 4, "cauldron")
        t.set(3, 1, 4, "campfire[lit=true,signal_fire=false]")
    elif kind == "boat":
        base(t, th, W, 5, "sand")
        t.entity(3, 1, 3, {"id": "minecraft:oak_boat"})
        t.set(1, 1, 5, th["fence"]); t.set(1, 2, 5, lantern(th, False))
    elif kind in ("sled", "lamp_tall", "vines_post", "ladders"):
        base(t, th, W, 3, th["path2"])
        t.set(3, 1, 2, st)
        for y in range(2, 4):
            t.set(3, y, 2, th["fence"])
        t.set(3, 4, 2, lantern(th, False))
        for x in (2, 4):
            t.set(x, 1, 2, stairs(th["wstairs"], "south"))
    else:
        return filler(th, rng, name, "garden")
    return t


# ------------------------------------------------------------------ villagers and golems
BED_COLOR = {"plains": "red", "taiga": "green", "snow": "light_blue", "desert": "orange", "savanna": "yellow",
             "jungle": "lime", "swamp": "brown"}


def villager_piece(vtype, name, depth=None, employed=True, bed=True):
    t = Template(name)
    col = BED_COLOR[vtype]
    if bed:
        t.jigsaw(0, 0, 0, "down_south", "heraldia:bottom", "heraldia:slot", "minecraft:empty",
                 final_state=f"minecraft:{col}_bed[facing=south,occupied=false,part=foot]", joint="aligned")
        t.set(0, 0, 1, f"{col}_bed[facing=south,occupied=false,part=head]")
    else:
        t.jigsaw(0, 0, 0, "down_south", "heraldia:bottom", "heraldia:slot", "minecraft:empty",
                 final_state="minecraft:structure_void", joint="aligned")
    if depth is not None:
        t.entity(0, 1 if bed else 0, 0, villager(depth, vtype, employed))
    t.min_size = (1, 3, 2 if bed else 1)
    return t


def rug_piece(vtype, name):
    """House without a bed: in its place, a mat of two carpets so the corner is not left empty."""
    t = Template(name)
    col = BED_COLOR[vtype]
    t.jigsaw(0, 0, 0, "down_south", "heraldia:bottom", "heraldia:slot", "minecraft:empty",
             final_state=f"minecraft:{col}_carpet", joint="aligned")
    t.set(0, 0, 1, f"{col}_carpet")
    t.min_size = (1, 3, 2)
    return t


def golem_piece(name):
    t = Template(name)
    t.jigsaw(0, 0, 0, "down_north", "heraldia:bottom", "heraldia:slot", "minecraft:empty",
             final_state="minecraft:structure_void", joint="rollable")
    t.entity(0, 0, 0, golem())
    t.min_size = (1, 3, 1)
    return t
