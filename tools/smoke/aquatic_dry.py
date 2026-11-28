"""Dry rooms of the aquatic structures stay dry, on a real 26.3 dedicated server (natural generation).

Usage: python3 tools/smoke/aquatic_dry.py --jar build/libs/heraldia-X.jar [--work build/smoke-aquatic-dry]

One start of the world with the fixed seed of server_smoke and random ticks on. For every aquatic structure:
Atlantis (its central district: temple, vestibule, galleries, chambers and houses), the stranded galleon, the
Corsair's isle, the lighthouse, a coastal lighthouse, a coastal shipwreck and a coastal village (its harbor; only the
coastal family is active),
/locate finds it (Atlantis: the anchor in the log) and its chunks are generated with forceload; then the
server runs 200 more ticks (water that got in through a gap would have time to flow) and stops. The saved
region files are read back and, for every template piece of those structures (the starts saved in the chunks:
template, position, rotation and liquid settings), every cell the template leaves as air is looked up in the
world: none may hold water (water, bubble column, sea plant or a waterlogged block); and in the pieces placed with
ignore_waterlogging, no block the template has dry (waterlogged=false) may come out waterlogged. And, without
looking at the templates' data (so that a template that lost its air cells is also caught), below sea level inside
the box of every piece no water or waterlogged block may have the air of a room beside it (20 or more air cells,
some of them air in a template: not a geode or a cave carved by a vanilla feature of the next chunk): the
templates never leave water beside their air (only below it, a moon pool). Water there is either sea water the
template did not clear or water that leaked in afterwards.
Pieces that follow the terrain (terrain_matching: streets) are skipped (their cells move column by column), and so
are the cells of chunks that were not fully generated. Exit code 0 if everything passes.
"""
import argparse, gzip, io, os, re, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import existing_world as ew
import nbtlib

sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
from themes import FAMILIES                              # noqa: E402

# (label, /locate target or None for Atlantis, half side in chunks of the square that is generated around it)
TARGETS = [
    ("atlantis", None, 8),
    ("galleon", "heraldia:unicas/galeon", 5),
    ("corsair_island", "heraldia:unicas/isla_corsario", 6),
    ("lighthouse", "heraldia:unicas/faro", 4),
    ("coast_lighthouse", "#heraldia:costa/faro", 3),
    ("coast_shipwreck", "#heraldia:costa/naufragio", 3),
    ("coastal_village", "#heraldia:aldeas/costa", 7),
]
# the structure ids whose pieces are checked, by label
IDS = {"atlantis": ("heraldia:unicas/atlantida",), "galleon": ("heraldia:unicas/galeon",),
       "corsair_island": ("heraldia:unicas/isla_corsario",), "lighthouse": ("heraldia:unicas/faro",),
       "coast_lighthouse": ("heraldia:costa/faro/",), "coast_shipwreck": ("heraldia:costa/naufragio/",),
       "coastal_village": ("heraldia:costa_",)}
ATLANTIS_LOG = re.compile(r"Atlántida (?:situada )?en el bloque (-?\d+), (-?\d+)")
WET_BLOCKS = {"minecraft:water", "minecraft:bubble_column", "minecraft:kelp", "minecraft:kelp_plant",
              "minecraft:seagrass", "minecraft:tall_seagrass"}
TICKS_AFTER = 200
SEA = 63                 # sea level of the overworld
ROOM = 20                # air cells that make a room
EXAMPLES = 8
# only coastal villages, on a 1,000-block grid (as in village_terrain.py): with the default families the closest
# village of the test seed is inland
CONFIG = dict(s.TEST_CONFIG, aldeas={"separacion_bloques": 1000, "maximo": 100, "familias": {f: f == "costa" for f in FAMILIES}})


def rotate(x, z, rotation):
    """Template position -> offset from the piece's position (the pivot of a pool element is its 0, 0, 0)."""
    return {"NONE": (x, z), "CLOCKWISE_90": (-z, x), "CLOCKWISE_180": (-x, -z), "COUNTERCLOCKWISE_90": (z, -x)}[rotation]


def wet(state):
    name, props = state
    return name in WET_BLOCKS or ("waterlogged", "true") in props


class Templates:
    """Templates read from the .jar (the same data the server loads): {location: (air cells, dry waterloggable cells)}."""

    def __init__(self, jar):
        self.zip, self.cache = zipfile.ZipFile(jar), {}

    def get(self, location):
        if location not in self.cache:
            ns, path = location.split(":", 1)
            raw = gzip.decompress(self.zip.read(f"data/{ns}/structure/{path}.nbt"))
            t = nbtlib.File.parse(io.BytesIO(raw))
            pal = []
            for p in t["palette"]:
                props = p.get("properties") or p.get("Properties") or {}
                pal.append((str(p.get("id", p.get("Name"))), {str(k): str(v) for k, v in props.items()}))
            air, dry = [], []
            for b in t["blocks"]:
                name, props = pal[int(b["state"])]
                pos = tuple(int(c) for c in b["pos"])
                if name == "minecraft:air":
                    air.append(pos)
                elif props.get("waterlogged") == "false":
                    dry.append((pos, name))
            self.cache[location] = (air, dry)
        return self.cache[location]


class World:
    """Blocks of the saved region files, decoded section by section on demand."""

    def __init__(self, path):
        self.path, self.chunks, self.sections = path, {}, {}

    def chunk(self, cx, cz):
        if (cx, cz) not in self.chunks:
            n = ew.read_chunk(self.path, cx, cz)
            self.chunks[(cx, cz)] = n if n is not None and str(n.get("Status", "")).endswith("full") else None
        return self.chunks[(cx, cz)]

    def block(self, x, y, z):
        """(name, props) or None if the chunk is not fully generated."""
        cx, cz, sy = x >> 4, z >> 4, y >> 4
        key = (cx, cz, sy)
        if key not in self.sections:
            n = self.chunk(cx, cz)
            st = None
            if n is not None:
                for sec in n.get("sections", []):
                    if int(sec["Y"]) == sy and sec.get("block_states") is not None:
                        st = ew.states(ew._blueprint(sec["block_states"]))
            self.sections[key] = st
        st = self.sections[key]
        if st is None:
            return None
        return st[((y & 15) << 8) | ((z & 15) << 4) | (x & 15)]


def starts(world, chunks, prefixes):
    """{(structure id, chunk): start} of the structures whose id begins with one of the prefixes, in those chunks."""
    out = {}
    for cx, cz in chunks:
        n = world.chunk(cx, cz)
        if n is None or "structures" not in n:
            continue
        for sid, st in ew._blueprint(n["structures"]).get("starts", {}).items():
            if sid.startswith(prefixes) and st.get("id") != "INVALID":
                out[(sid, cx, cz)] = st
    return out


def check_pieces(world, templates, found, air_cells):
    """(checked air cells, failures, examples) of every template piece in the starts; adds the world position of
    every air cell of the templates to air_cells."""
    checked, bad, examples = 0, 0, []
    for (sid, _, _), st in sorted(found.items()):
        for piece in st.get("Children", []):
            el = piece.get("pool_element")
            if not el or el.get("element_type") != "minecraft:single_pool_element" or el.get("projection") == "terrain_matching":
                continue
            ignore = piece.get("liquid_settings") == "ignore_waterlogging" or el.get("override_liquid_settings") == "ignore_waterlogging"
            air, dry = templates.get(el["location"])
            px, py, pz, rot = piece["PosX"], piece["PosY"], piece["PosZ"], piece["rotation"]
            for (x, y, z) in air:
                dx, dz = rotate(x, z, rot)
                b = world.block(px + dx, py + y, pz + dz)
                if b is None:
                    continue
                checked += 1
                air_cells.add((px + dx, py + y, pz + dz))
                if wet(b):
                    bad += 1
                    if len(examples) < EXAMPLES:
                        examples.append(f"{sid} {el['location']}: {b[0]} at {px + dx} {py + y} {pz + dz} (air in the template)")
            if not ignore:
                continue
            for (x, y, z), name in dry:
                dx, dz = rotate(x, z, rot)
                b = world.block(px + dx, py + y, pz + dz)
                if b is not None and b[0] == name and ("waterlogged", "true") in b[1]:
                    bad += 1
                    if len(examples) < EXAMPLES:
                        examples.append(f"{sid} {el['location']}: waterlogged {name} at {px + dx} {py + y} {pz + dz} (dry in the template)")
    return checked, bad, examples


def is_air(b):
    return b is not None and b[0] in ("minecraft:air", "minecraft:cave_air")


def room(world, start, cache, air_cells):
    """Is the air cell part of a room: an air space of at least ROOM cells with some cell that a template leaves as air?
    (Not the pocket a broken sea plant leaves, nor the hollow of a geode or a cave that a vanilla feature of the
    neighbouring chunk carved after the structure was placed.)"""
    if start in cache:
        return cache[start]
    seen, todo, ours = {start}, [start], start in air_cells
    while todo and (len(seen) < ROOM or not ours) and len(seen) < 50 * ROOM:
        x, y, z = todo.pop()
        for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            n = (x + d[0], y + d[1], z + d[2])
            if n not in seen and is_air(world.block(*n)):
                seen.add(n)
                todo.append(n)
                ours = ours or n in air_cells
    ok = len(seen) >= ROOM and ours
    for c in seen:
        cache[c] = ok
    return ok


def scan_boxes(world, found, air_cells):
    """Independent of the templates' data: (cells looked at, wet cells, examples) of the water (or waterlogged blocks)
    below sea level, inside the box of a piece, that has a room's air beside it. The templates never leave water beside
    their air (the generator's audits forbid it; only below, a moon pool), so that is water that was not cleared or
    that got in. It also catches a template that lost its air cells, which the check of the templates' air cannot."""
    boxes = []
    for st in found.values():
        for piece in st.get("Children", []):
            el = piece.get("pool_element") or {}
            if "BB" in piece and el.get("projection") != "terrain_matching" and piece.get("id") != "heraldia:atlantida_base":
                boxes.append(piece["BB"])
    looked, bad, examples, cache, done = 0, 0, [], {}, set()
    for x0, y0, z0, x1, y1, z1 in boxes:
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                for y in range(y0, min(y1, SEA - 1) + 1):
                    if (x, y, z) in done:
                        continue
                    done.add((x, y, z))
                    b = world.block(x, y, z)
                    if b is None:
                        continue
                    looked += 1
                    if not wet(b):
                        continue
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        n = (x + dx, y, z + dz)
                        if is_air(world.block(*n)) and room(world, n, cache, air_cells):
                            bad += 1
                            if len(examples) < EXAMPLES:
                                examples.append(f"{b[0]} at {x} {y} {z} beside the air of a room")
                            break
    return looked, bad, examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-aquatic-dry"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    t0 = time.monotonic()
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    proc, ctx = ew.start_up(a.work, launcher, CONFIG)
    failures, areas = [], {}
    try:
        ctx.run("gamerule random_tick_speed 3", r"Gamerule|set to")
        for label, target, half in TARGETS:
            if target is None:
                m = ATLANTIS_LOG.search(ctx.log())
                if not m:
                    failures.append("the log does not say where Atlantis is")
                    continue
                x, z = int(m.group(1)), int(m.group(2))
            else:
                m = ctx.run(f"locate structure {target}", r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
                if not m.lastindex or m.group(1) is None:
                    failures.append(f"{label}: /locate {target} finds nothing")
                    continue
                x, z = int(m.group(1)), int(m.group(2))
            chunks = ew.square((x >> 4) - half, (z >> 4) - half, 2 * half)
            ew.load_data(ctx, chunks)
            areas[label] = chunks
            print(f"{label}: generated around {x} {z}", flush=True)
        ctx.ticks(TICKS_AFTER)
    finally:
        ew.halt(proc, ctx)
    world, templates = World(os.path.join(a.work, "world")), Templates(a.jar)
    for label, chunks in areas.items():
        found = starts(world, chunks, IDS[label])
        if not found:
            failures.append(f"{label}: no start of {IDS[label]} in the generated chunks")
            continue
        air_cells = set()
        checked, bad, examples = check_pieces(world, templates, found, air_cells)
        print(f"{label}: {len(found)} start(s), {checked} air cells of the templates checked, {bad} wet", flush=True)
        if checked < 50:
            failures.append(f"{label}: only {checked} air cells checked")
        if bad:
            failures.append(f"{label}: {bad} wet cells where the template is dry, e.g. " + "; ".join(examples))
        looked, bad, examples = scan_boxes(world, found, air_cells)
        print(f"{label}: {looked} cells below sea level in the pieces' boxes, {bad} wet beside a room's air", flush=True)
        if bad:
            failures.append(f"{label}: {bad} wet cells beside a room's air, e.g. " + "; ".join(examples))
    print(f"aquatic_dry: {time.monotonic() - t0:.0f} s")
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("OK: the dry cells of every aquatic structure are dry")


if __name__ == "__main__":
    main()
