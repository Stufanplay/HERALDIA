"""The Herald's House on the owner's own spawn (seed -2071092601429184301, large biomes, hard difficulty): steep desert
by a river, where the town's site drops 29 blocks. Our other tests' gentle terrain hid three faults the owner saw there
at once: a wall of still water standing in the air by the town, the grounds levelled into "rice terraces" (dozens of
one-block steps one after another all round the wall) and steps on the roads. The build's own audits counted only steps
of more than one block, so they passed; this test therefore also reads the saved world back from its region files and
measures the result itself, independently of the mod.

Usage: python3 tools/smoke/herald_steep.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-escarpado"
One world (the owner's seed, large biomes, hard; the arena off), then:
  1. a pond is made high up across the town's west wall before the town comes: a mound of dirt with POND_DEPTH blocks of
     still water on it, its surface POND_OVER blocks over the town's ground, as a lake the town cuts in two;
  2. the town is placed there (Carpet's player at the owner's spawn: /heraldia herald place here), and its roads and its
     grounds are built on their own;
  3. the log: the town settled the pond (drained what its template and margin left open), the roads' audit has no step of
     more than one block, the grounds' audit has no water standing in the air, no loose column or hole, at most
     RAMP_SHARE of its columns in ramps and STEP_SHARE in bare steps, and no step over SLOW_MS ms on the server thread;
  4. the world read back (the server stopped): no block of the town waterlogged where its template is not (the pond the
     town cuts into filled its own walls, stairs, slabs and lanterns, and nothing runs out of them until the first block
     update beside them: no measure of water sees it in a fresh world); in the footprint, its margin and the ring, no
     block of water with air beside or under it; in the ring, at most RAMP_SHARE of the natural columns' one-block steps
     in ramps (RAMP or more the same way, each within RAMP_GAP columns of the next) and at most STEP_SHARE bare steps
     (more than one block, the higher side not a retaining wall); on every road, no two side by side paved columns more
     than a block apart.
Exit code 0 if everything passes.
"""
import argparse, collections, gzip, io, json, os, re, shutil, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nbtlib
import server_smoke as s
import existing_world as ew
from guide import Server
from arena import Test
from trophies import CARPET
from modrinth import fetch
from herald_grounds import AUDIT, BUILT, SLOW_MS, ROADS_AUDIT, PLACED as PLACED_AT

SEED, LEVEL_TYPE = "-2071092601429184301", "minecraft\\:large_biomes"
# Where this test places the town by hand (`herald place here`; its ground at 90), on the owner's seed: steep land with a
# pond across the wall's line, chosen for that. It is NOT where the game puts the town in a new world of that seed: the
# site search, left to itself, picks 48 86 0 (dry, no dock). What is measured here is the hard case, not the owner's town.
SPAWN = (0, 91, 48)
P = "rep"                           # Carpet's player (it spawns lowercase)
POND_DEPTH, POND_OVER = 5, 9
RING, BLEND = 50, 4                 # herald/Grounds.RING; Outskirts.EDGE_BLEND (the natural ground's own rows)
MARGIN = 8                          # herald/Siting.MARGIN
RAMP, RAMP_GAP = 4, 2               # herald/OutskirtsPlan.RAMP, RAMP_GAP
LAWN_SHARE = 0.10                   # of the land columns just outside the wall, at most this share of grass (83 % before)
FORECOURT = 9                       # herald_house: the template's rows outside its south wall
RAMP_SHARE, STEP_SHARE = 0.04, 0.01     # (herald_grounds.py; 33 % of the columns in ramps here before terraces)
PLACED = r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+) \(box (-?\d+) (-?\d+) (-?\d+) to (-?\d+) (-?\d+) (-?\d+)\)"
SHORES = r"herald's house: shores: (\d+) ponds left open drained \((\d+) blocks of water\), (\d+) blocks of water banked; (\d+) blocks"
# what is not ground: the plants, trees and snow on it and our lamp posts and signs (looked through, as the audit does)
THROUGH = ("air", "leaves", "_log", "_wood", "grass", "fern", "bush", "flower", "petals", "dandelion", "poppy", "orchid",
           "allium", "tulip", "daisy", "cornflower", "lily", "rose", "peony", "lilac", "sunflower", "vine", "snow", "cane",
           "mushroom", "sapling", "torch", "lantern", "fence", "sign", "cactus", "litter", "dripleaf",
           "moss_carpet", "firefly", "pitcher", "azalea", "propagule")
GROUND = ("grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "mycelium", "sand", "red_sand", "sandstone",
          "terracotta", "stone", "granite", "diorite", "andesite", "gravel", "clay", "mud", "mud_bricks", "packed_mud",
          "dirt_path", "cobblestone", "mossy_cobblestone", "stone_bricks", "mossy_stone_bricks", "snow_block", "deepslate",
          "tuff", "calcite", "ice", "packed_ice")
PAVING = ("dirt_path", "smooth_sandstone", "smooth_red_sandstone", "packed_mud", "gravel")   # BuiltRoads.deck, not its kerb
KERB = ("coarse_dirt", "cut_sandstone", "cut_red_sandstone", "cobblestone", "mud_bricks")
WET = ("water", "flowing_water", "seagrass", "tall_seagrass", "kelp", "kelp_plant", "bubble_column")       # a column of water
# what water beside would run into (Shores.open: air, or a plant it would wash away)
OPEN = ("air", "cave_air", "short_grass", "tall_grass", "fern", "large_fern", "dead_bush", "snow", "short_dry_grass", "tall_dry_grass",
        "bush")
ROAD_PIECE = 30                     # a paved stretch at least this many columns is a road (a house's yard path is smaller)
WALLS = ("cobblestone", "mossy_cobblestone", "cut_sandstone", "smooth_sandstone", "cut_red_sandstone", "smooth_red_sandstone",
         "mud_bricks", "packed_mud", "stone_bricks", "mossy_stone_bricks")                  # Outskirts.wallBlock


def name(state):
    """A block's name; flowing water (level over 0) is "flowing_water", still water (a source) "water"."""
    n = state[0].split(":")[-1]
    return "flowing_water" if n == "water" and dict(state[1]).get("level", "0") != "0" else n


class World:
    """The saved overworld's blocks (names), decoded section by section on demand; None where a chunk is not full."""

    def __init__(self, path):
        self.path, self.chunks, self.sections = path, {}, {}

    def block(self, x, y, z):
        cx, cz, sy = x >> 4, z >> 4, y >> 4
        if (cx, cz) not in self.chunks:
            n = ew.read_chunk(self.path, cx, cz)
            self.chunks[(cx, cz)] = n if n is not None and str(n.get("Status", "")).endswith("full") else None
        n = self.chunks[(cx, cz)]
        if n is None:
            return None
        key = (cx, cz, sy)
        if key not in self.sections:
            st = None
            for sec in n.get("sections", []):
                if int(sec["Y"]) == sy and sec.get("block_states") is not None:
                    st = [name(p) for p in ew.states(ew._blueprint(sec["block_states"]))]
            self.sections[key] = st
        st = self.sections[key]
        return "air" if st is None else st[((y & 15) << 8) | ((z & 15) << 4) | (x & 15)]


def through(name):
    return any(k in name for k in THROUGH) and name not in GROUND and name not in WET


def ground(name):
    return name in GROUND or name.endswith("sandstone") or name.endswith("terracotta")


def survey(world, box, ylo, yhi):
    """Each column of the box: (top y, top block) of what is not looked through, or None where not generated."""
    x0, z0, x1, z1 = box
    out = {}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            y, b = yhi, world.block(x, yhi, z)
            while b is not None and y > ylo and through(b):
                y -= 1
                b = world.block(x, y, z)
            out[(x, z)] = None if b is None else (y, "water" if b in WET else b)
    return out


def standing(world, cols):
    """The still water blocks (sources), from each column's top down, with air (or a plant) beside or under them."""
    found = []
    for (x, z), c in cols.items():
        if c is None or c[1] != "water":
            continue
        y = c[0]
        while world.block(x, y, z) in ("water", "flowing_water"):
            if world.block(x, y, z) == "flowing_water":
                y -= 1
                continue
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, -1, 0)):
                if world.block(x + dx, y + dy, z + dz) in OPEN:
                    found.append((x, y, z))
                    break
            y -= 1
    return found


def orphans(world, cols):
    """The running water with no source: from each wet column's top down, every flowing block from which no source is
    reached through water going sideways or up (water never runs up: whatever feeds a block lies that way). A stream the
    town left when it drained what fed it stays for good, because the build takes water away without block updates."""
    flowing = set()
    for (x, z), c in cols.items():
        if c is None or c[1] != "water":
            continue
        y = c[0]
        while world.block(x, y, z) in ("water", "flowing_water"):
            if world.block(x, y, z) == "flowing_water":
                flowing.add((x, y, z))
            y -= 1
    fed, lost = set(), []
    for start in sorted(flowing):
        if start in fed or start in lost:
            continue
        seen, todo, source = {start}, [start], False
        while todo and not source:
            x, y, z = todo.pop()
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, 1, 0)):
                o = (x + dx, y + dy, z + dz)
                if o in seen:
                    continue
                b = world.block(*o)
                if b is None or b == "water" or o in fed:
                    source = True
                    break
                if b == "flowing_water":
                    seen.add(o)
                    todo.append(o)
        (fed.update if source else lost.extend)(seen)
    return sorted(set(lost))


HUT_AT = r"herald's house roads: hut \S+ \(\S+\) at (-?\d+) -?\d+ (-?\d+)"
HOUSE_AT = r"herald's house grounds: house \S+ \(\S+\) at (-?\d+) -?\d+ (-?\d+)"
HUT_REACH, HOUSE_REACH = 6, 10     # a 7 x 7 hut and a house of at most 11 x 11, turned any way about the corner the log gives
TEMPLATE = "data/heraldia/structure/casa_heraldo/casa.nbt"      # the town's own template: its box is the footprint


def roofs(log):
    """Whether a column is under a roadside hut or a house of the grounds: (x, z) -> bool, from where the log says each
    was placed. Their roofs and porches can be of planks too, and they are not road walkways."""
    at = [(int(m.group(1)), int(m.group(2)), r) for pat, r in ((HUT_AT, HUT_REACH), (HOUSE_AT, HOUSE_REACH))
          for m in re.finditer(pat, log)]
    return lambda x, z: any(abs(x - bx) <= r and abs(z - bz) <= r for bx, bz, r in at)


def dry_decks(world, cols, town, roof):
    """Road walkways over no water: a column outside the town and off every hut and house whose top is planks with no
    source water in the three blocks under it (a bridge stands over a river's or a pond's water; these were laid over
    water that was only passing). Returns (those columns, how many plank tops were set aside as a building's)."""
    out, aside = [], 0
    for (x, z), c in cols.items():
        if c is None or town(x, z) or not c[1].endswith("_planks"):
            continue
        if roof(x, z):
            aside += 1
            continue
        under = [world.block(x, c[0] - k, z) or "" for k in (1, 2, 3)]
        if "water" not in under and not under[0].endswith("_fence"):     # a bridge's post down to the bottom is waterlogged
            out.append((x, c[0], z))
    return out, aside


def ramps(cols, inside):
    """OutskirtsPlan.ramps over the columns in `inside` ({(x, z): y})."""
    xs = sorted({x for x, _ in inside}) if inside else []
    zs = sorted({z for _, z in inside}) if inside else []
    total = 0
    for axis in (0, 1):
        for a in (xs if axis == 0 else zs):
            run, way, last = 0, 0, -10 ** 6
            line = zs if axis == 0 else xs
            for k in range(line[0], line[-1]):
                p, q = ((a, k), (a, k + 1)) if axis == 0 else ((k, a), (k + 1, a))
                d = inside[q] - inside[p] if p in inside and q in inside else None
                if d == 0:
                    continue
                if d is not None and abs(d) == 1 and d == way and k - last <= RAMP_GAP:
                    run += 1
                else:
                    total += run if run >= RAMP else 0
                    run, way = (1, d) if d is not None and abs(d) == 1 else (0, 0)
                last = k
            total += run if run >= RAMP else 0
    return total


def pieces(paved):
    """The paved columns in stretches of at least ROAD_PIECE side by side (the roads; not a house's yard, a river's gravel)."""
    out, seen = {}, set()
    for k in paved:
        if k in seen:
            continue
        piece, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            piece.append(c)
            for q in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if q in paved and q not in seen:
                    seen.add(q)
                    todo.append(q)
        if len(piece) >= ROAD_PIECE:
            out.update({c: paved[c] for c in piece})
    return out


def own_waterlogged(jar):
    """The town's template's own waterlogged cells (x, y, z from its origin): the only ones the town may leave full of water."""
    with zipfile.ZipFile(jar) as z:
        t = nbtlib.File.parse(io.BytesIO(gzip.decompress(z.read(TEMPLATE))))
    wet = {i for i, e in enumerate(ew._blueprint(t["palette"])) if waterlogged(e)}
    return {tuple(int(v) for v in b["pos"]) for b in t["blocks"] if int(b["state"]) in wet}


def waterlogged(entry):
    """Is this palette entry a waterlogged=true state? (26.3: a state without properties is a plain string.)"""
    if not isinstance(entry, dict):
        return False
    props = entry.get("Properties") or entry.get("properties") or {}
    return str(props.get("waterlogged", "")) == "true"


def drowned(path, foot, own):
    """The blocks of the footprint with waterlogged=true that the template does not have waterlogged: (x, y, z, block).

    The pond the town cuts into is the one that fills them. StructureTemplate.placeInWorld keeps the water a cell held
    by default: it sets the template's block and then puts that water back inside it if it can hold any (a wall, a
    stair, a slab, a lantern), and the ones whose water was not a source are waterlogged again from any source beside
    them.

    Why no measure of water finds it: placeLiquid schedules a fluid tick, so the wall does pour, while the town is
    still being built -- and the build's own shores step takes that water away again (on the .jar before the fix this
    world cleared 347 blocks out of the footprint and dried 80 of running water; with it, 0 and 64). So the finished
    world has no standing water, no running water without a source and no walkway over none of it, and every water
    check passes over a wall that is still full of it. What is left is the waterlogged blocks, which pour again at the
    first block update beside them. Read from the saved region files, so it measures the result and not what the mod
    says it did."""
    ox, oy, oz, mx, my, mz = foot
    out, missing = [], 0
    for cx in range(ox >> 4, (mx >> 4) + 1):
        for cz in range(oz >> 4, (mz >> 4) + 1):
            n = ew.read_chunk(path, cx, cz)
            if n is None or not str(n.get("Status", "")).endswith("full"):
                missing += 1
                continue
            for sec in n.get("sections", []):
                sy = int(sec["Y"])
                if sec.get("block_states") is None or (sy << 4) + 15 < oy or (sy << 4) > my:
                    continue
                bs = ew._blueprint(sec["block_states"])
                if not any(waterlogged(e) for e in bs["palette"]):
                    continue                        # nothing waterlogged in this section's palette at all
                for i, (block, props) in enumerate(ew.states(bs)):
                    if dict(props).get("waterlogged") != "true":
                        continue
                    y, z, x = (sy << 4) + (i >> 8), (cz << 4) + ((i >> 4) & 15), (cx << 4) + (i & 15)
                    if oy <= y <= my and ox <= x <= mx and oz <= z <= mz and (x - ox, y - oy, z - oz) not in own:
                        out.append((x, y, z, block.split(":")[-1]))
    return sorted(out), missing


def read_back(p, work, jar, foot, ground_y, log):
    """The world as it was saved, measured here (step 4)."""
    world = World(os.path.join(work, "world"))
    ox, oz, mx, mz = foot[0], foot[2], foot[3], foot[5]
    # the town's own blocks left full of water by the pond it cuts into: latent (nothing runs until a block update
    # beside them), so neither the audit's standing water nor the running water with no source above sees them
    own = own_waterlogged(jar)
    wet_blocks, ungenerated = drowned(os.path.join(work, "world"), foot, own)
    kinds = ", ".join(f"{n} {k}" for k, n in sorted(collections.Counter(b[3] for b in wet_blocks).items(),
                                                    key=lambda kv: -kv[1])[:6])
    print(f"READ BACK: the template has {len(own)} waterlogged cells; {len(wet_blocks)} waterlogged blocks in the footprint "
          f"that it does not" + (f" ({kinds}), e.g. {wet_blocks[:5]}" if wet_blocks else ""), flush=True)
    p.check(not ungenerated, f"read back: {ungenerated} chunks of the footprint are not saved full")
    p.check(not wet_blocks, f"read back: {len(wet_blocks)} blocks of the town are waterlogged where its template is not "
            f"({kinds}): {wet_blocks[:5]}")
    area = (ox - RING, oz - RING, mx + RING, mz + RING)
    cols = survey(world, area, ground_y - 70, ground_y + 60)
    town = lambda x, z: ox <= x <= mx and oz <= z <= mz
    blend = lambda x, z: min(x - area[0], area[2] - x, z - area[1], area[3] - z) < BLEND
    wet = standing(world, cols)
    print(f"READ BACK: {len(wet)} blocks of water standing in the air" + (f", e.g. {wet[:5]}" if wet else ""), flush=True)
    p.check(not wet, f"read back: {len(wet)} blocks of water standing in the air in the town, its margin and the ring: {wet[:5]}")
    # no stream from nowhere, and no walkway over one: the pond the town cut open ran down the hillside before it was
    # drained, and what had run out stayed (193 and 105 blocks in two runs of the same build) with plank walkways over it
    lost = orphans(world, cols)
    print(f"READ BACK: {len(lost)} blocks of running water with no source" + (f", e.g. {lost[:5]}" if lost else ""), flush=True)
    p.check(not lost, f"read back: {len(lost)} blocks of running water with no source in the town, its margin and the ring: {lost[:5]}")
    decks, aside = dry_decks(world, cols, town, roofs(log))
    print(f"READ BACK: {len(decks)} walkway columns over no water ({aside} plank tops set aside: a hut's or a house's)"
          + (f", e.g. {decks[:5]}" if decks else ""), flush=True)
    p.check(not decks, f"read back: {len(decks)} plank walkway columns with no water under them: {decks[:5]}")
    # the town does not lay a lawn on the desert: its margin and its forecourt keep the land's own ground
    out = lambda x, z: max(ox - x, x - mx, oz - z, z - mz, 0)
    edge = [c[1] for (x, z), c in cols.items() if c is not None and c[1] != "water"
            and (1 <= out(x, z) <= MARGIN or out(x, z) == 0 and z > mz - FORECOURT)]
    lawn = sum(b == "grass_block" for b in edge)
    print(f"READ BACK: {lawn} of {len(edge)} land columns of the margin and the forecourt are grass", flush=True)
    p.check(len(edge) > 3000, f"read back: only {len(edge)} land columns in the margin and the forecourt")
    p.check(lawn <= LAWN_SHARE * len(edge), f"read back: {lawn} of {len(edge)} columns round the wall are grass on desert land")
    # nor inside the wall: the town's own ground is the land's too (the crops keep their plots, the trees their pits)
    yard = [c[1] for (x, z), c in cols.items() if c is not None and out(x, z) == 0 and z <= mz - FORECOURT
            and (ground(c[1]) or c[1] in ("sand", "red_sand", "gravel", "mud"))]
    green = sum(b == "grass_block" for b in yard)
    print(f"READ BACK: {green} of {len(yard)} open ground columns inside the wall are grass", flush=True)
    p.check(len(yard) > 3000, f"read back: only {len(yard)} open ground columns inside the wall")
    p.check(green <= LAWN_SHARE * len(yard), f"read back: {green} of {len(yard)} columns inside the wall are grass on desert land")
    inside = {}
    for (x, z), c in cols.items():
        if c is None or town(x, z) or blend(x, z) or not ground(c[1]) or c[1] in PAVING or c[1] in KERB:
            continue
        inside[(x, z)] = c[0]
    found, bare = ramps(cols, inside), 0
    for (x, z), y in inside.items():
        for q in ((x + 1, z), (x, z + 1)):
            if q in inside and abs(inside[q] - y) > 1:
                hx, hz = (x, z) if y > inside[q] else q
                bare += world.block(hx, min(y, inside[q]) + 1, hz) not in WALLS
    print(f"READ BACK: {len(inside)} natural columns in the ring, {found} one-block steps in ramps, {bare} bare steps", flush=True)
    p.check(len(inside) > 20000, f"read back: only {len(inside)} natural columns in the ring")
    p.check(found <= RAMP_SHARE * len(inside), f"read back: {found} one-block steps in ramps (of {len(inside)} columns)")
    p.check(bare <= STEP_SHARE * len(inside), f"read back: {bare} bare steps of more than one block (of {len(inside)} columns)")
    road = pieces({k: c[0] for k, c in survey(world, (area[0] - 160, area[1] - 160, area[2] + 160, area[3] + 160), ground_y - 70,
                                                    ground_y + 60).items() if c is not None and c[1] in PAVING and not town(*k)})
    jumps = [(k, q) for k, y in road.items() for q in ((k[0] + 1, k[1]), (k[0], k[1] + 1)) if q in road and abs(road[q] - y) > 1]
    print(f"READ BACK: {len(road)} paved road columns, {len(jumps)} steps of more than one block" + (f", e.g. {jumps[:3]}" if jumps else ""),
          flush=True)
    p.check(len(road) > 500, f"read back: only {len(road)} paved road columns")
    p.check(not jumps, f"read back: {len(jumps)} steps of more than one block on the roads: {jumps[:3]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-escarpado"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False}
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)
    props = os.path.join(a.work, "server.properties")
    with open(props) as f:
        text = f.read().replace("level-seed=heraldia", f"level-seed={SEED}\nlevel-type={LEVEL_TYPE}\ndifficulty=hard")
    with open(props, "w") as f:
        f.write(text)
    fails, t0 = [], time.monotonic()
    srv = Server(a.work, launcher)
    p = Test(srv.ctx, fails)
    ctx, box, ground_y = srv.ctx, None, SPAWN[1] - 1
    try:
        x, y, z = SPAWN
        wx = x - 64                                     # the town's west wall (its template is 128 wide, centred on x)
        ctx.run(f"forceload add {wx - 24} {z + 2} {wx + 24} {z + 30}", r"[Cc]hunk|marked|already")
        if not p.check(ctx.until(f"execute if loaded {wx - 12} {y} {z + 18}"), "the pond's chunks do not load"):
            return 1
        top = ground_y + POND_OVER
        ctx.run(f"fill {wx - 10} {ground_y - 30} {z + 8} {wx + 10} {top} {z + 28} minecraft:dirt", r"filled|Successfully|No blocks")
        ctx.run(f"fill {wx - 6} {top - POND_DEPTH + 1} {z + 12} {wx + 6} {top} {z + 24} minecraft:water", r"filled|Successfully|No blocks")
        ctx.ticks(10)
        ctx.run(f"forceload remove {wx - 24} {z + 2} {wx + 24} {z + 30}", r"[Cc]hunk|unmarked|No")
        ctx.run(f"player {P} spawn at {x} {y} {z}", r"joined the game|Unknown|Incorrect")
        if not p.check(ctx.until(f"execute if entity @a[name={P}]"), "Carpet's player does not appear"):
            return 1
        ctx.run(f"tp {P} {x} {y} {z}", r"Teleported|Unknown")
        ctx.run(f"execute as {P} run heraldia herald place here", r"heraldia|Herald|Heraldo|place|confirm")
        ctx.run(f"execute as {P} run heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
        m = p.wait_log(PLACED, 900)
        if not p.check(m, "the town is not placed"):
            return 1
        box = [int(v) for v in m.groups()[3:]]
        ground_y = int(m.group(2))
        sh = re.search(SHORES, ctx.log())
        if p.check(sh, "no shores line from the town's build"):
            ponds, drained, banked, cleared = (int(v) for v in sh.groups())
            print(f"STEEP shores: {sh.group(0)}", flush=True)
            p.check(ponds >= 1 and drained > 0, "the pond the town cut open was not drained")
        if not p.check(p.wait_log(BUILT, 900), "the grounds' build does not finish"):
            return 1
        log = ctx.log()
        ra = re.search(ROADS_AUDIT, log)
        if p.check(ra, "no roads' audit"):
            cols, blocked, unpaved, steps, orphans = (int(v) for v in ra.groups())
            print(f"STEEP roads: {ra.group(0)}", flush=True)
            p.check(steps == 0, f"the roads' audit: {steps} steps of more than one block")
        au, bu = re.search(AUDIT, log), re.search(BUILT, log)
        print(f"STEEP grounds: {au.group(0) if au else 'no audit line'}", flush=True)
        print(f"STEEP grounds: {bu.group(0)}", flush=True)
        b = [int(v) for v in bu.groups()]
        p.check(b[2] <= SLOW_MS, f"a step of {b[2]} ms on the server thread (at most {SLOW_MS})")
        if p.check(au, "no grounds' audit"):
            g = [int(v) for v in au.groups()]
            cols, steps, before, edge, faced, bare, ramp, ramp0, pillars, holes, wet = g[:11]
            p.check(wet == 0, f"the grounds' audit: {wet} blocks of water standing in the air")
            p.check(ramp <= RAMP_SHARE * cols, f"the grounds' audit: {ramp} one-block steps in ramps (of {cols} columns; {ramp0} before)")
            p.check(bare <= STEP_SHARE * cols, f"the grounds' audit: {bare} bare steps (of {cols} columns)")
            p.check(pillars == 0 and holes == 0, f"the grounds' audit: {pillars} loose columns and {holes} holes")
        print(f"COST grounds: {b[0]} ticks, {b[1]} ms on the server thread, the slowest step {b[2]} ms (the plan {b[3]} ms off it)")
    finally:
        srv.stop()
    for bad in ("Registry loading errors", "at io.github.albertosa23", "the plan failed", "step "):
        if bad in ctx.log() and (bad != "step " or re.search(r"herald's house (grounds|roads): step .* failed", ctx.log())):
            fails.append(f"the log contains {bad!r}")
    if box:
        read_back(p, a.work, os.path.abspath(a.jar), box, ground_y, ctx.log())
    print(f"HERALD STEEP: {time.monotonic() - t0:.0f} s;", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
