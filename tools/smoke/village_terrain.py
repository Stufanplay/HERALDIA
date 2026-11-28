"""Villages and terrain on a real dedicated 26.3 server (complements server_smoke.py).

Usage: python3 tools/smoke/village_terrain.py --jar build/libs/heraldia-X.jar --work build/smoke [--measure]
Checks:
- Port that seeks water: /place of a coastal village on several beaches (/locate biome) puts the hut and the pier
  on the nearest free shore ("pier at ... tip x z" log line): at the tip there are planks at sea level
  with water underneath and the piles go down through the water to the bottom. Inland, the same village comes out without a port or, if there is
  water within reach, with the pier over it.
- Port in natural generation: with only the coastal family active and the minimum grid, /locate finds N real coastal
  villages (generated as in a normal world, not with /place). Reading the saved start of each one (its
  pieces and boxes) it counts how many have a pier; for each pier, at the tip and halfway there are planks at sea level
  with water underneath and its box does not overlap any other piece (streets in plan, buildings in 3D; only the hut). At least
  NATURAL_RATE of the villages must have a pier. With -Dheraldia.depurar.puerto the mod also writes the search time
  of each village, which is summarized.
- Slopes: /place of a cherry-grove village (on a slope; /place does not adjust the terrain, the worst case) leaves very few
  foundation blocks in the air: the buildings' foundations go down to the ground with the style's material.
  They are counted by reading the saved regions (save-all) with a minimal Anvil-format reader.
- Terrain fit in natural generation (villages/TerrainFit and Clearing): in a new world with only the forest and taiga
  families (hills and trees), the nearest village is generated whole and read from the saved regions: the mod logs how it
  fitted it ("terrain fit"); the ground under each grading point of its graded streets and doors is where it was asked
  (a block below the standing height, give or take one), every building's door is within a step of its street, and no
  tree of world generation grows on its pieces (a trunk on soil with leaves above, two blocks around each piece box).
--measure: only prints the figures (to compare with an earlier .jar), without failing anything.
--only-natural: only the natural generation phase (the slowest to measure with an earlier .jar).
--only-fit: only the terrain fit phase.
"""
import argparse, glob, io, json, os, queue, re, struct, subprocess, sys, threading, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import server_smoke as s
import ground_blocks
import nbtlib
from themes import FAMILIES

SEA = 63
COAST = "heraldia:costa_pescadores"
SLOPE = ("heraldia:cerezos_japonesa", "minecraft:cherry_grove", "minecraft:stone_bricks")
RADIUS = 112            # box forced and read around each village (standard radius + margin; forceload: <= 256 chunks)
MAX_FLOATING = 0.05     # at most 5 %: eaves and design arches, and foundations that reach the cap (16) on a cliff
# Natural generation: coastal villages searched for (in the 100 cells of a 1,000-block grid closest
# to 0,0) and minimum fraction that must have a pier. In one world only 0-5 of those cells fall on a beach: several
# seeds are needed (these three give 2 + 3 + 5). Measured with 12 seeds (21 villages): before T23, 0 of 21 with a pier;
# after, 21 of 21 (--seeds heraldia costa1 ... costa11 --measure).
NATURAL_N, NATURAL_RATE, NATURAL_GRID = 10, 0.8, 1000
NATURAL_SEEDS = ["heraldia", "costa1", "costa2"]
NATURAL_CONFIG = {"aldeas": {"separacion_bloques": NATURAL_GRID, "maximo": 100,
                             "familias": {f: f == "costa" for f in FAMILIES}}}
AIR_BLOCK = {"minecraft:air", "minecraft:cave_air", "minecraft:water", "minecraft:short_grass", "minecraft:tall_grass",
        "minecraft:fern", "minecraft:large_fern", "minecraft:pink_petals", "minecraft:snow"}


def place(ctx, sid, x, z):
    ctx.run(f"forceload add {x - RADIUS} {z - RADIUS} {x + RADIUS} {z + RADIUS}", r"Marked|Added|force|already")
    for _ in range(s.PLACE_ATTEMPTS):
        m = ctx.run(f"place structure {sid} {x} ~ {z}", r"Generated structure|not loaded(?! yet)")
        if "not loaded" not in m.group(0):
            return "Generated" in m.group(0)
        time.sleep(s.PLACE_RETRY_S)
    return False


def biome(ctx, b, x=0, z=0):
    m = ctx.run(f"execute positioned {x} 100 {z} run locate biome {b}", r"nearest.*?\[(-?\d+), ~?(-?\d+|~), (-?\d+)\]|Could not find")
    return (int(m.group(1)), int(m.group(3))) if m.group(1) else None


def test(ctx, cmd):
    return "passed" in ctx.run(cmd, r"Test passed|Test failed").group(0)


def count(ctx, x0, y0, z0, x1, y1, z1, block, dest):
    """Blocks of a type in a box, without touching it: clone filtered to an empty zone (counts what was copied)."""
    m = ctx.run(f"clone {x0} {y0} {z0} {x1} {y1} {z1} {dest[0]} {dest[1]} {dest[2]} filtered {block}",
                r"[Ss]uccessfully cloned (\d+)|No blocks|cloned 0")
    return int(m.group(1)) if m.group(1) else 0


def coast_line(ctx, n):
    return next((l for l in ctx.seen[n:] if "aldea de costa en" in l), "")


def pier_ok(ctx, fails, tx, tz):
    """Pier tip (from the log line): planks at sea level with water underneath and piles down to the bottom."""
    if not test(ctx, f"execute if block {tx} {SEA} {tz} #minecraft:planks"):
        fails.append(f"port: no planks at the pier tip ({tx} {SEA} {tz})")
    if not test(ctx, f"execute if block {tx} {SEA - 1} {tz} minecraft:water"):
        # a street that reaches the sea (planks over water from its processor) under the pier would leave its planks here:
        # AldeaStructure descarta esas orillas
        under = "tablas de una calle" if test(ctx, f"execute if block {tx} {SEA - 1} {tz} #minecraft:planks") else "otra cosa"
        fails.append(f"port: no water under the pier tip ({tx} {SEA - 1} {tz}): {under}")
    # piles: logs under the water-surface row next to the tip
    logs = count(ctx, tx - 6, SEA - 24, tz - 6, tx + 6, SEA - 2, tz + 6, "#minecraft:logs", (tx - 6, 250, tz - 6))
    print("coast: pile logs under the water at the tip:", logs)
    if logs == 0:
        fails.append("port: the piles do not go down to the bottom")


def coast(ctx, fails, measure):
    beach = [biome(ctx, "minecraft:beach", *p) for p in ((0, 0), (1500, 0), (0, 1500), (-1500, 0), (0, -1500))]
    done = 0
    for b in [p for p in beach if p]:
        n = len(ctx.seen)
        if not place(ctx, COAST, *b):
            fails.append(f"place {COAST} at {b} failed")
            continue
        time.sleep(1)
        line = coast_line(ctx, n)
        print("costa:", b, line.strip())
        m = re.search(r"punta (-?\d+) (-?\d+)", line)
        if not m:
            continue
        pier_ok(ctx, fails, int(m.group(1)), int(m.group(2)))
        done += 1
    total = len([p for p in beach if p])
    print(f"coast: {done} of {total} beaches with a pier")
    if done < NATURAL_RATE * total:
        fails.append(f"only {done} of {total} nearby beaches gave a site with water for the port")


def inland(ctx, fails, p):
    """Inland (the cherry hill of the slope test): the coastal village comes out without a port or, if it finds
    water within reach (with the test seed, about 80 blocks away), with the pier over it, never on land."""
    n = len(ctx.seen)
    if not place(ctx, COAST, *p):
        fails.append(f"place {COAST} at {p} failed")
        return
    time.sleep(1)
    line = coast_line(ctx, n)
    print("costa tierra adentro:", line.strip())
    m = re.search(r"punta (-?\d+) (-?\d+)", line)
    if m:
        pier_ok(ctx, fails, int(m.group(1)), int(m.group(2)))
    elif "sin orilla" not in line:
        fails.append("inland: the port line is missing from the log")


# ------------------------------------------------------------------ minimal region reader (Anvil)
def palette_name(p):
    """26.3 stores the palette as strings ("minecraft:stone", blocks without properties) or compounds with "id" and
    "properties" (those with properties: stairs, logs, lanterns...); before 26.x, "Name"."""
    if isinstance(p, str):
        return str(p).split("[")[0]
    return str(p.get("id", p.get("Name", p.get("", "minecraft:air")))).split("[")[0]


def read_blocks(world, x0, z0, x1, z1):
    """{(x, y, z): name} of the non-air blocks of the box (all heights), reading the saved regions."""
    out = {}
    # 26.x: world/dimensions/minecraft/overworld/region (antes world/region)
    paths = glob.glob(os.path.join(world, "dimensions", "minecraft", "overworld", "region", "r.*.mca")) or \
        glob.glob(os.path.join(world, "region", "r.*.mca"))
    for path in paths:
        rx, rz = (int(v) for v in os.path.basename(path).split(".")[1:3])
        with open(path, "rb") as f:
            data = f.read()
        for i in range(1024):
            cx, cz = rx * 32 + i % 32, rz * 32 + i // 32
            if cx * 16 + 15 < x0 or cx * 16 > x1 or cz * 16 + 15 < z0 or cz * 16 > z1:
                continue
            off = int.from_bytes(data[i * 4:i * 4 + 3], "big") * 4096
            if not off:
                continue
            length, comp = struct.unpack(">IB", data[off:off + 5])
            raw = data[off + 5:off + 4 + length]
            nbt = nbtlib.File.parse(io.BytesIO(zlib.decompress(raw) if comp == 2 else raw))
            for sec in nbt.get("sections", []):
                bs = sec.get("block_states")
                if not bs:
                    continue
                pal = [palette_name(p) for p in bs["palette"]]
                if pal == ["minecraft:air"]:
                    continue
                sy = int(sec["Y"]) * 16
                if len(pal) == 1:
                    vals = [0] * 4096
                else:
                    bits = max(4, (len(pal) - 1).bit_length())
                    per, mask = 64 // bits, (1 << bits) - 1
                    vals = []
                    for v in bs["data"]:
                        v = int(v) & 0xFFFFFFFFFFFFFFFF
                        for k in range(per):
                            vals.append((v >> (k * bits)) & mask)
                for idx in range(4096):
                    name = pal[vals[idx]]
                    if name == "minecraft:air":
                        continue
                    x, z = cx * 16 + idx % 16, cz * 16 + (idx // 16) % 16
                    if x0 <= x <= x1 and z0 <= z <= z1:
                        out[(x, sy + idx // 256, z)] = name
    return out


def slope(ctx, work, fails, measure):
    sid, b, found = SLOPE
    p = biome(ctx, b)
    if not p:
        fails.append(f"no {b} nearby")
        return None
    if not place(ctx, sid, *p):
        fails.append(f"place {sid} at {p} failed")
        return None
    time.sleep(3)
    ctx.run("save-all flush", r"Saved the game|saved")
    x, z = p
    blocks = read_blocks(os.path.join(work, "world"), x - RADIUS, z - RADIUS, x + RADIUS, z + RADIUS)
    total = [q for q, n in blocks.items() if n == found]
    floating = [q for q in total if blocks.get((q[0], q[1] - 1, q[2]), "minecraft:air") in AIR_BLOCK]
    ys = [q[1] for q in total]
    print(f"slope: {sid} at {p}: {len(total)} blocks of {found}, {len(floating)} in the air "
          f"(desnivel de la aldea: alturas {min(ys) if ys else '-'}..{max(ys) if ys else '-'})")
    if not measure and total and len(floating) > MAX_FLOATING * len(total):
        fails.append(f"slope: {len(floating)} of {len(total)} foundation blocks in the air")
    return p


# ------------------------------------------------------------------ port in natural generation
def region_chunk(world, cx, cz):
    """NBT of the saved chunk (cx, cz) or None."""
    rx, rz = cx >> 5, cz >> 5
    path = os.path.join(world, "dimensions", "minecraft", "overworld", "region", f"r.{rx}.{rz}.mca")
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    i = (cx & 31) + (cz & 31) * 32
    off = int.from_bytes(data[i * 4:i * 4 + 3], "big") * 4096
    if not off:
        return None
    length, comp = struct.unpack(">IB", data[off:off + 5])
    raw = data[off + 5:off + 4 + length]
    return nbtlib.File.parse(io.BytesIO(zlib.decompress(raw) if comp == 2 else raw))


def village_start(world, x, z):
    """Pieces of the village start saved in the chunk of (x, z): [(template, projection, box, rotation)] or None."""
    nbt = region_chunk(world, x >> 4, z >> 4)
    if nbt is None:
        return None
    for sid, start in (nbt.get("structures", {}).get("starts", {}) or {}).items():
        if not str(sid).startswith("heraldia:") or "Children" not in start:
            continue
        pieces = []
        for c in start["Children"]:
            el = c.get("pool_element", {})
            pieces.append((str(el.get("location", "")), str(el.get("projection", "")), [int(v) for v in c["BB"]],
                           str(c.get("rotation", "NONE"))))
        return str(sid), pieces
    return None


# Direction towards the sea of each pier rotation (the template's +z rotated): (dx, dz)
SEA_DIR = {"NONE": (0, 1), "CLOCKWISE_90": (-1, 0), "CLOCKWISE_180": (0, -1), "COUNTERCLOCKWISE_90": (1, 0)}


def pier_points(bb, rot):
    """Tip and middle of the pier (central column) from its box and its rotation."""
    x0, _, z0, x1, _, z1 = bb
    dx, dz = SEA_DIR[rot]
    if dx:
        cz = (z0 + z1) // 2
        tip, base = (x1 if dx > 0 else x0), (x0 if dx > 0 else x1)
        return (tip, cz), ((tip + base) // 2, cz)
    cx = (x0 + x1) // 2
    tip, base = (z1 if dz > 0 else z0), (z0 if dz > 0 else z1)
    return (cx, tip), (cx, (tip + base) // 2)


def overlaps(a, b, floor_plan=False):
    return (a[0] <= b[3] and b[0] <= a[3] and a[2] <= b[5] and b[2] <= a[5]
            and (floor_plan or (a[1] <= b[4] and b[1] <= a[4])))


def start_server(work, launcher, props=()):
    proc = subprocess.Popen(["java", "-Xmx2G", *props, "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    return proc, s.Context(proc, lines, seen)


def natural_points():
    """Points from which /locate is requested: a mesh with the grid's spacing that covers its 100 allowed cells."""
    r = 5 * NATURAL_GRID
    pts = [(x, z) for x in range(-r, r + 1, NATURAL_GRID) for z in range(-r, r + 1, NATURAL_GRID)]
    return sorted(pts, key=lambda p: (p[0] ** 2 + p[1] ** 2, p))


def natural_world(ctx, work, fails, want):
    """Coastal villages of this world (at most `want`): [(x, z, sid, pieces)]."""
    found = {}
    for x, z in natural_points():
        m = ctx.run(f"execute positioned {x} 100 {z} run locate structure #heraldia:aldeas",
                    r"is at \[(-?\d+), ~, (-?\d+)\]|Could not find")
        if m.group(1):
            found.setdefault((int(m.group(1)), int(m.group(2))), None)
    villages = list(found)[:want]
    # the start (with its pieces) is already created: /locate generates the start chunk up to STRUCTURE_STARTS. It is loaded
    # in full and saved to read it.
    for x, z in villages:
        ctx.run(f"forceload add {x} {z}", r"Marked|Added|force|already")
    for x, z in villages:
        ctx.until(f"execute if loaded {x} 0 {z}")
    ctx.run("save-all flush", r"Saved the game|saved")
    out = []
    for x, z in villages:
        st = village_start(os.path.join(work, "world"), x, z)
        if st is None:
            fails.append(f"natural: could not read the village start at {x} {z}")
        else:
            out.append((x, z) + st)
    return out


def natural_piers(ctx, fails, villages):
    """Checks the pier of each village; returns how many have one."""
    with_pier = 0
    for x, z, sid, pieces in villages:
        pier = [p for p in pieces if p[0].endswith("/specials/port_pier")]
        shed = [p for p in pieces if "/specials/port" in p[0] and not p[0].endswith("_pier")]
        print(f"natural: {sid} at {x} {z}: {len(pieces)} pieces, {'with' if pier else 'WITHOUT'} pier")
        if not pier:
            continue
        with_pier += 1
        _, _, bb, rot = pier[0]
        for other in pieces:
            if other is pier[0] or other in shed:
                continue
            street = other[1] == "terrain_matching"
            if overlaps(bb, other[2], floor_plan=street):
                fails.append(f"natural: the pier at {x} {z} overlaps {other[0]} ({'street' if street else 'building'})")
        # planks at sea level and water underneath at the tip and halfway: only the chunk of each point is loaded
        for name, (px, pz) in zip(("punta", "mitad"), pier_points(bb, rot)):
            ctx.run(f"forceload add {px} {pz}", r"Marked|Added|force|already")
            ctx.until(f"execute if loaded {px} 0 {pz}")
            if not ctx.block((px, SEA, pz), "#minecraft:planks"):
                fails.append(f"natural: no planks at the {name} of the pier at {x} {z} ({px} {SEA} {pz})")
            if not ctx.block((px, SEA - 1, pz), "minecraft:water"):
                fails.append(f"natural: no water under the {name} of the pier at {x} {z} ({px} {SEA - 1} {pz}): pier on land")
    return with_pier


def natural(jar, work, fails, measure, seeds):
    """Several worlds (fixed seeds) with only the coastal family, until NATURAL_N villages are gathered."""
    total, with_pier, times, queries = 0, 0, [], []
    for seed in seeds:
        if total >= NATURAL_N:
            break
        launcher = s.prepare(work, jar, s.gradle_properties())
        with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
            json.dump(NATURAL_CONFIG, f)
        props = os.path.join(work, "server.properties")
        with open(props) as f:
            text = re.sub(r"level-seed=.*", f"level-seed={seed}", f.read())
        with open(props, "w") as f:
            f.write(text)
        proc, ctx = start_server(work, launcher, ["-Dheraldia.depurar.puerto=true"])
        try:
            villages = natural_world(ctx, work, fails, NATURAL_N - total)
            print(f"natural: seed {seed}: {len(villages)} coastal villages")
            with_pier += natural_piers(ctx, fails, villages)
            total += len(villages)
            for m in re.finditer(r"aldea de costa en .*? (\d+) consultas del fondo.*? en (\d+) µs", ctx.log()):
                queries.append(int(m.group(1)))
                times.append(int(m.group(2)))
        finally:
            stop(proc)
    if times:
        # Informational, not a limit: the search runs when a coastal village's start is created, on a world-generation
        # thread; the server thread does not run it, but a /locate that creates the start waits for it (here: "Locating
        # element ... took 700 ms", 126 ms of it this search). Its wall time moved 0.76x-1.35x for the same village between
        # two identical runs (#90, 12 villages). Its seabed queries are what is deterministic (12 of 12
        # identical), and they bound the work: about 0.56 ms each. Measured over 30 seeds (71 villages): queries median 78,
        # max 252; time median 64 ms, max 194 ms, against ~470 ms median to assemble the village itself.
        times.sort()
        queries.sort()
        print(f"natural: port search (informational: wall time on a world-generation thread; /locate waits for it) in "
              f"{len(times)} villages: median {times[len(times) // 2] / 1000:.1f} ms, max {times[-1] / 1000:.1f} ms; "
              f"seabed queries (deterministic): median {queries[len(queries) // 2]}, max {queries[-1]}")
    rate = with_pier / total if total else 0
    print(f"natural: {with_pier} of {total} coastal villages with a pier ({rate:.0%})")
    if total < NATURAL_N:
        fails.append(f"natural: only {total} coastal villages in the test seeds ({NATURAL_N} requested)")
    if not measure and rate < NATURAL_RATE:
        fails.append(f"natural: {with_pier} of {total} coastal villages with a pier (minimum {NATURAL_RATE:.0%})")


# ------------------------------------------------------------------ terrain fit in natural generation
FIT_SEED = "heraldia"
FIT_CONFIG = {"aldeas": {"separacion_bloques": NATURAL_GRID, "maximo": 100, "caminos": {"activado": False},
                         "familias": {f: f in ("bosque", "taiga") for f in FAMILIES}},
              "caravanas": {"activado": False}, "viajeros": {"activado": False}, "medianas": {"activadas": False}}
FIT_RADIUS = 104          # forced and read around the village start (the pieces of a standard village reach ~90 blocks)
FIT_GRADE_OK = 0.85       # share of grading points whose ground is where it was asked (± 1; 27 of 29 in the test village)
FIT_DOORS_OK = 0.9        # share of buildings whose door is within a step of its street (read by `street_ground`)
FIT_MAX_TREES = 10        # natural trunks left on the pieces (the forest villages had 60-170 before the clearing)
SOIL = ("grass_block", "dirt", "podzol", "mud", "coarse_dirt", "rooted_dirt", "moss_block", "snow_block", "mycelium")


def _is_ground(name):
    """Does this block count as ground? (vegetation and air do not; water does.) Decided from the 26.3 registry by
    `ground_blocks.is_ground`: a collision box above 1/8 of a block, and not in the registry's tags for trees and
    plants (#98). The lists of names it replaces let 123 blocks with no collision box through as ground, among them
    12 of the 13 plants #98 found (blue orchids, sugar cane, wildflowers...; one flower is the whole ±1 tolerance)."""
    return ground_blocks.is_ground(name)


def ground(blocks, x, z, top):
    """Height of the highest ground block of the column at or below `top` (vegetation and air do not count; water does)."""
    for y in range(top, top - 64, -1):
        if _is_ground(blocks.get((x, y, z), "minecraft:air")):
            return y
    return None


def start_pieces(world, x, z):
    """Pieces of the village start in the chunk of (x, z), with their junctions: [dict(loc, proj, bb, junctions)]."""
    nbt = region_chunk(world, x >> 4, z >> 4)
    for sid, start in (nbt.get("structures", {}).get("starts", {}) or {}).items():
        if not str(sid).startswith("heraldia:") or "Children" not in start:
            continue
        return str(sid), [dict(loc=str(c.get("pool_element", {}).get("location", "")),
                               proj=str(c.get("pool_element", {}).get("projection", "")),
                               bb=[int(v) for v in c["BB"]],
                               junctions=[(int(j["source_x"]), int(j["source_ground_y"]), int(j["source_z"]), int(j["delta_y"]),
                                           str(j["dest_proj"])) for j in c.get("junctions", [])]) for c in start["Children"]]
    return None, []


def inside(bb, x, z, margin=0):
    return bb[0] - margin <= x <= bb[3] + margin and bb[2] - margin <= z <= bb[5] + margin


def street_ground(blocks, x, z, top, rigid_boxes):
    """`ground` that reads the street, not what stands on it: the blocks inside the box of a rigid piece (a filler, a
    terminator's tower, a building) are skipped, so a piece placed over the street column does not count as its ground.
    `ground` takes the highest block of the column, which there is the top of that piece (a well over an avenue, a
    tower over a street: measured with the doors named, Nov 2026). The doors of the fit are read with it."""
    for y in range(top, top - 64, -1):
        if any(b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] <= z <= b[5] for b in rigid_boxes):
            continue
        if _is_ground(blocks.get((x, y, z), "minecraft:air")):
            return y
    return None


def fit_figures(blocks, pieces, bad_doors=None, highest=None):
    """(graded points ok, total), (doors ok, total), natural trunks on the pieces. A door is read with `street_ground`:
    the street under any piece placed on it. With `bad_doors` (a list), each door that is not within a step of its
    street is appended to it: (piece, its box, the street column, the step). With `highest` (a dict), the same doors
    read with `ground` (the highest block of the street column, what the test read until Nov 2026) go into it as ok,
    n and bad: an informative figure, which the test prints and never compares."""
    g_ok = g_n = d_ok = d_n = 0
    boxes = [p["bb"] for p in pieces]
    rigid = [p["bb"] for p in pieces if p["proj"] == "rigid"]
    if highest is not None:
        highest.update(ok=0, n=0, bad=[])
    for p in pieces:
        bb = p["bb"]
        # grading points: junctions of a piece inside its own footprint with no height difference (a joint's junction lies
        # on the other piece, one block outside the footprint)
        for jx, jy, jz, dy, proj in p["junctions"]:
            if dy == 0 and proj == "terrain_matching" and inside(bb, jx, jz) and p["proj"] == "terrain_matching":
                h = ground(blocks, jx, jz, jy + 2)
                g_n += 1
                g_ok += h is not None and abs(h - (jy - 1)) <= 1
        # the door of a building that hangs from a street: the street column next to the joint
        if p["proj"] != "rigid" or not any(k in p["loc"] for k in ("/houses/", "/specials/")):
            continue
        joint = next(((jx, jz) for jx, jy, jz, dy, proj in p["junctions"] if proj == "terrain_matching" and not inside(bb, jx, jz)), None)
        if not joint:
            continue
        jx, jz = joint
        dx = -1 if jx < bb[0] else 1 if jx > bb[3] else 0
        dz = -1 if jz < bb[2] else 1 if jz > bb[5] else 0
        h = street_ground(blocks, jx + dx, jz + dz, bb[1] + 8, [b for b in rigid if b is not bb])
        d_n += 1
        # standing on the street (h + 1) against standing at the door's joint column (the floor row, bb[1])
        ok = h is not None and abs(h + 1 - bb[1]) <= 1
        d_ok += ok
        if not ok and bad_doors is not None:
            bad_doors.append((p["loc"], bb, (jx + dx, jz + dz), None if h is None else bb[1] - (h + 1)))
        if highest is not None:
            hh = ground(blocks, jx + dx, jz + dz, bb[1] + 8)
            ok_h = hh is not None and abs(hh + 1 - bb[1]) <= 1
            highest["n"] += 1
            highest["ok"] += ok_h
            if not ok_h:
                highest["bad"].append((p["loc"], bb, (jx + dx, jz + dz), None if hh is None else bb[1] - (hh + 1)))
    trunks = 0
    for (x, y, z), name in blocks.items():
        if not name.endswith("_log") or not blocks.get((x, y - 1, z), "").endswith(SOIL):
            continue
        if not any(inside(b, x, z, 2) for b in boxes):
            continue
        if any("leaves" in blocks.get((x + a, y + h, z + c), "") for h in range(2, 14) for a in (-1, 0, 1) for c in (-1, 0, 1)):
            trunks += 1
    return (g_ok, g_n), (d_ok, d_n), trunks


def terrain_fit(jar, work, fails, measure):
    launcher = s.prepare(work, jar, s.gradle_properties())
    with open(os.path.join(work, "config", "heraldia.json")) as f:
        cfg = json.load(f)
    for k, v in FIT_CONFIG.items():
        cfg[k] = {**cfg.get(k, {}), **v}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)
    props = os.path.join(work, "server.properties")
    with open(props) as f:
        text = re.sub(r"level-seed=.*", f"level-seed={FIT_SEED}", f.read())
    with open(props, "w") as f:
        f.write(text)
    proc, ctx = start_server(work, launcher, ["-Dheraldia.depurar.puerto=true", "-Dheraldia.perfil=true"])
    try:
        m = ctx.run("locate structure #heraldia:aldeas", r"is at \[(-?\d+), ~, (-?\d+)\]|Could not find")
        if not m.group(1):
            fails.append("fit: no forest or taiga village near the origin")
            return
        x, z = int(m.group(1)), int(m.group(2))
        for x0, x1 in ((x - FIT_RADIUS, x - 1), (x, x + FIT_RADIUS)):
            ctx.run(f"forceload add {x0} {z - FIT_RADIUS} {x1} {z + FIT_RADIUS}", r"Marked|Added|force|already")
        for cx, cz in ((x - FIT_RADIUS, z - FIT_RADIUS), (x + FIT_RADIUS, z + FIT_RADIUS), (x, z)):
            ctx.until(f"execute if loaded {cx} 0 {cz}", timeout=600)
        ctx.ticks(40)
        ctx.run("save-all flush", r"Saved the game|saved")
        log = next((l for l in ctx.seen if "terrain fit" in l), "")
    finally:
        stop(proc)
    print("fit:", log.strip())
    while not ctx.lines.empty():    # the profile is written when the server stops (None: end of the output)
        line = ctx.lines.get()
        if line is not None:
            ctx.seen.append(line)
    cost = re.search(r'"aldea_terreno":\{[^}]*\}', ctx.log())
    print("fit: cost of the fit (profile):", cost.group(0) if cost else "-")
    if not log:
        fails.append("fit: the mod did not log how the village fitted the terrain")
    world = os.path.join(work, "world")
    sid, pieces = start_pieces(world, x, z)
    blocks = read_blocks(world, x - FIT_RADIUS - 16, z - FIT_RADIUS - 16, x + FIT_RADIUS + 16, z + FIT_RADIUS + 16)
    bad, highest = [], {}
    (g_ok, g_n), (d_ok, d_n), trunks = fit_figures(blocks, pieces, bad, highest)
    print(f"fit: {sid} at {x} {z}: {len(pieces)} pieces; ground at {g_ok} of {g_n} grading points; {d_ok} of {d_n} doors "
          f"within a step of their street; {trunks} natural trunks on the pieces")
    share = lambda a, n: f"{a / n:.3f}" if n else "-"
    print(f"fit: doors within a step: {d_ok} of {d_n} ({share(d_ok, d_n)}, the gate: the street under any piece on it) "
          f"| {highest['ok']} of {highest['n']} ({share(highest['ok'], highest['n'])}, the highest block of the street "
          f"column, informative: compared with nothing)")
    # every door that misses, by name: a count alone cannot tell one mechanism from four accidents
    for loc, bb, (cx, cz), step in bad:
        print(f"fit:   door off its street: {loc} box {bb} street column ({cx}, {cz}) "
              f"{'no ground under it' if step is None else f'floor {step:+d} from the street'}")
    for loc, bb, (cx, cz), step in highest["bad"]:
        print(f"fit:   (informative) door off the highest block of its street column: {loc} box {bb} street column ({cx}, {cz}) "
              f"{'no ground under it' if step is None else f'floor {step:+d} from the street'}")
    if measure:
        return
    if not pieces:
        fails.append(f"fit: could not read the village start at {x} {z}")
    if g_n and g_ok < FIT_GRADE_OK * g_n:
        fails.append(f"fit: the ground is where it was asked at only {g_ok} of {g_n} grading points")
    if d_n and d_ok < FIT_DOORS_OK * d_n:
        fails.append(f"fit: only {d_ok} of {d_n} doors within a step of their street")
    if trunks > FIT_MAX_TREES:
        fails.append(f"fit: {trunks} trees of world generation on the village pieces (at most {FIT_MAX_TREES})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-aldeas"))
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--only-natural", action="store_true")
    ap.add_argument("--only-fit", action="store_true")
    ap.add_argument("--seeds", nargs="*", default=NATURAL_SEEDS)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    fails = []
    # a new world with only the forest and taiga families: the terrain fit in natural generation
    terrain_fit(os.path.abspath(a.jar), a.work, fails, a.measure)
    if a.only_fit:
        print("VILLAGES AND TERRAIN:", "OK" if not fails else fails)
        return 1 if fails and not a.measure else 0
    if not a.only_natural:
        launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
        proc, ctx = start_server(a.work, launcher)
        try:
            p = slope(ctx, a.work, fails, a.measure)
            if not a.measure:
                coast(ctx, fails, a.measure)
                if p:
                    inland(ctx, fails, p)
        finally:
            stop(proc)
    # new worlds with only the coastal family: natural generation
    natural(os.path.abspath(a.jar), a.work, fails, a.measure, a.seeds)
    print("VILLAGES AND TERRAIN:", "OK" if not fails else fails)
    return 1 if fails and not a.measure else 0


def stop(proc):
    if proc.poll() is None:
        s.send(proc, "stop")
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
