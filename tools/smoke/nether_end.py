"""Heraldia content in the Nether and the End (T44) on a real 26.3 dedicated server, with the default configuration.

Usage: python3 tools/smoke/nether_end.py --jar build/libs/heraldia-X.jar [--work build/smoke-nether-end]
Checks:
- the log: the grid of each medium and unique structure of the Nether and the End with its default spacing, without biome search
  (it only reads the main world's noise) or exclusion zone around vanilla villages;
- /locate (with /execute in) of each type in its dimension, at a reasonable distance, and that in the main world there
  is none (their grids are not there);
- that they really generate where /locate says: loading is forced around it and /heraldia info here, at the height of the
  piece, says you are inside; each unique structure's guardian appears under the bedrock ceiling (Nether) or above its island (End),
  with its trophy table;
- /place structure of each style and of each unique structure in its dimension (with their guardians);
- /heraldia info nearby from the Nether and the End: those of its dimension;
- loot spawn of each new table, several times, with nothing from the forbidden list (netherite, elytra, the dragon's items).
Exit code 0 if everything passes.
"""
import argparse, json, math, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
import dimensions                   # noqa: E402  (the generator: what belongs to each dimension)
import mediums                      # noqa: E402
import uniques                        # noqa: E402

DIM = {"nether": "minecraft:the_nether", "end": "minecraft:the_end"}
# Where to search from: in the End, outside the central island (the outer islands start at ~1,000 blocks)
ORIGIN = {"nether": [(0, 0), (1500, -1200)], "end": [(2000, 0), (-1800, 1800)]}
LOCATE_MAX = 4000
PLACE = {"nether": (4000, 4000), "end": (6000, 6000)}
STEP = 64
ROLLS = 3


def kinds():
    median = [(mid, m) for mid, m in mediums.modules() if dimensions.dimension_of(m) != dimensions.MAIN]
    unique_mods = [(sid, m) for sid, m in uniques.modules() if dimensions.dimension_of(m) != dimensions.MAIN]
    return median, unique_mods


def en(dim, cmd):
    return f"execute in {DIM[dim]} {cmd}"


def forceload(ctx, dim, x0, z0, x1, z1, remove=False):
    ctx.run(en(dim, f"run forceload {'remove' if remove else 'add'} {x0} {z0} {x1} {z1}"),
            r"Marked|[Aa]dded|[Rr]emoved|force|already|[Uu]nmarked")


def locate(ctx, dim, target, x, z):
    m = ctx.run(en(dim, f"positioned {x} 64 {z} run locate structure {target}"), r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
    return (int(m.group(1)), int(m.group(2))) if m.group(1) else None


def inside(ctx, dim, x, z, route, ys):
    """/heraldia info here at (x, y, z) for some y in `ys` and around the start: does it say you are in `route`?"""
    # /locate gives the corner, NOT of the chunk; the start is at its center or half a chunk from it (DimensionStructure.POINTS)
    for dx, dz in ((8, 8), (16, 8), (0, 8), (8, 16), (8, 0)):
        for y in ys:
            m = ctx.run(en(dim, f"positioned {x + dx} {y} {z + dz} run heraldia info here"),
                        r"\((heraldia:[^)]+)\)|no hay ninguna|no Heraldia|not loaded|no está cargada")
            if m.group(1) and route in m.group(1):
                return True
    return False


def heights(dim):
    # In the Nether, by eye between the lava sea and the ceiling; in the End, near the surface of the islands
    return range(36, 118, 5) if dim == "nether" else range(46, 90, 5)


def check_log(ctx, median, unique_mods):
    fails, log = [], ctx.log()
    for mid, mod in median:
        sp = round(mod.SEPARATION / 16)
        m = re.search(rf"rejilla medianas/{mid}: activada, cada {sp} chunks \([^)]*origen desplazado\), sin máximo, exclusión ninguna([^\n]*)", log)
        if not m or "candidata en el bioma" in m.group(1):
            fails.append(f"the log is missing the grid of medianas/{mid} (every {sp} chunks, no biome or exclusion)")
    for sid, mod in unique_mods:
        sp = round(mod.STRUCTURE["spacing"])
        if not re.search(rf"rejilla unicas/{sid}: activada, cada {sp} chunks", log):
            fails.append(f"the log is missing the grid of unicas/{sid} (every {sp} chunks)")
    return fails


def check_locate(ctx, median, unique_mods):
    fails, generate = [], []
    for kind, lst in (("medianas", median), ("unicas", unique_mods)):
        for i, mod in lst:
            dim = dimensions.dimension_of(mod)
            target = f"#heraldia:medianas/{i}" if kind == "medianas" else f"heraldia:unicas/{i}"
            for k, (x, z) in enumerate(ORIGIN[dim]):
                t0 = time.monotonic()
                p = locate(ctx, dim, target, x, z)
                dt = time.monotonic() - t0
                if p is None:
                    fails.append(f"/locate does not find {target} in {dim} from {x}, {z}")
                    continue
                d = math.dist((x, z), p)
                print(f"{target} ({dim}) from {x}, {z}: at {p[0]}, {p[1]} {d:.0f} blocks away ({dt:.2f} s)")
                if d > LOCATE_MAX * (2 if kind == "unicas" else 1):
                    fails.append(f"{target} in {dim} from {x}, {z} at {d:.0f} blocks")
                if dim == "end" and math.hypot(*p) < 1000:
                    fails.append(f"{target}: on the End's central island ({p})")
                if k == 0:
                    generate.append((kind, i, dim, p))
            # in the main world there is none (the search ends right away: there is no grid there)
            m = ctx.run(f"execute positioned 0 64 0 run locate structure {target}", r"is at \[|Could not find|no structure|There is no")
            if m.group(0).startswith("is at"):
                fails.append(f"{target} appears in the main world")
    return fails, generate


def check_generated(ctx, generate):
    """Really generates the first of each type (forceload around what /locate said) and checks that it is there."""
    fails = []
    for kind, i, dim, (x, z) in generate:
        forceload(ctx, dim, x - 24, z - 24, x + 24, z + 24)
        route = f"medianas/{i}/" if kind == "medianas" else f"unicas/{i}"
        ok = False
        finish = time.monotonic() + s.UNTIL_S
        while time.monotonic() < finish and not ok:
            ok = inside(ctx, dim, x, z, route, heights(dim))
            if not ok:
                time.sleep(3)
        if not ok:
            fails.append(f"{route} ({dim}) is not where /locate said ({x}, {z})")
        elif kind == "unicas":
            fails += guardian(ctx, i, dim)
        forceload(ctx, dim, x - 24, z - 24, x + 24, z + 24, remove=True)
    return fails


def guardian(ctx, sid, dim):
    sel = f"@e[tag=heraldia_guardian.{sid},limit=1]"          # no position: search in all dimensions
    if not ctx.wait_entity(sel):
        return [f"{sid}: no aparece su guardián"]
    fails = []
    p = ctx.pos(sel)
    if p and dim == "nether" and not (dimensions_and_min() <= p[1] < 123):
        fails.append(f"{sid}: guardian at y = {p[1]:.0f}, outside the playable Nether (above the lava and below the ceiling)")
    if p and dim == "end" and p[1] < 45:
        fails.append(f"{sid}: guardian at y = {p[1]:.0f} (above the void)")
    m = ctx.run(f"data get entity {sel} DeathLootTable", r'has the following entity data: "([^"]+)"|No entity')
    if not (m.group(1) or "").startswith(f"heraldia:guardianes/{sid}/"):
        fails.append(f"{sid}: the guardian does not have the trophy table: {m.string.strip()}")
    m = ctx.run(f"data get entity {sel} Tags", r"has the following entity data: \[([^\]]*)\]|No entity")
    if "heraldia_guardian" not in (m.group(1) or ""):
        fails.append(f"{sid}: the guardian lacks the advancements tag")
    return fails


def dimensions_and_min():
    return 32


def check_place(ctx, median, unique_mods):
    fails, k = [], 0
    for mid, mod in median:
        dim = dimensions.dimension_of(mod)
        for style in mod.STYLES:
            fails += place(ctx, dim, f"heraldia:medianas/{mid}/{style}", PLACE[dim][0] + k * STEP, PLACE[dim][1])
            k += 1
    for sid, mod in unique_mods:
        dim = dimensions.dimension_of(mod)
        x, z = PLACE[dim][0] + k * STEP, PLACE[dim][1] + 400
        k += 1
        ctx.run(f"kill @e[tag=heraldia_guardian.{sid}]", r"Killed|No entity")       # the one of the generated structure, if it is still loaded
        fails += place(ctx, dim, f"heraldia:unicas/{sid}", x, z, remove=False)       # its entities, with the chunk loaded
        if not ctx.wait_entity(f"@e[tag=heraldia_guardian.{sid}]"):
            fails.append(f"{sid}: /place without a guardian")
        ctx.run(f"kill @e[tag=heraldia_guardian.{sid}]", r"Killed|No entity")
        forceload(ctx, dim, x - 24, z - 24, x + 48, z + 48, remove=True)
    return fails


def place(ctx, dim, sid, x, z, remove=True):
    forceload(ctx, dim, x - 24, z - 24, x + 48, z + 48)
    m = None
    for _ in range(s.PLACE_ATTEMPTS):
        t0 = time.monotonic()
        m = ctx.run(en(dim, f"run place structure {sid} {x} 64 {z}"), r"Generated structure|not loaded(?! yet)")
        print(f"/place {sid} en {dim}: {time.monotonic() - t0:.2f} s")
        if "not loaded" not in m.group(0):
            break
        time.sleep(s.PLACE_RETRY_S)
    if remove:
        forceload(ctx, dim, x - 24, z - 24, x + 48, z + 48, remove=True)
    return [] if "Generated" in m.group(0) else [f"place structure {sid} en {dim}: {m.string.strip()}"]


def check_info(ctx, median, unique_mods):
    fails = []
    for dim, (x, z) in (("nether", (0, 0)), ("end", (2000, 0))):
        m = ctx.run(en(dim, f"positioned {x} 64 {z} run heraldia info nearby 4000"),
                    r"info nearby \d+ en [^:]+: \d+ estructuras en (\d+) ms")
        text = "".join(s.drain(ctx))
        seen_all = {g[0] for g in s.INFO_LINE.findall(text)}
        own_items = {f"heraldia:medianas/{mid}" for mid, mod in median if dimensions.dimension_of(mod) == dim}
        if not m.lastindex:
            fails.append(f"/heraldia info nearby en {dim} no responde")
            continue
        if not any(v.startswith("heraldia:medianas/") or v.startswith("heraldia:unicas/") for v in seen_all):
            fails.append(f"/heraldia info nearby in {dim} gives none of Heraldia's: {sorted(seen_all)}")
        foreign = {v for v in seen_all if v.startswith("heraldia:aldeas") or v.startswith("heraldia:minas/")}
        if foreign:
            fails.append(f"/heraldia info nearby in {dim} gives main-world structures: {sorted(foreign)}")
        print(f"info nearby en {dim}: {sorted(seen_all)} (propias esperadas {sorted(own_items)})")
    return fails


def check_loot(ctx, median, unique_mods):
    fails = []
    ctx.run("forceload add 0 0 0 0", r"Marked|[Aa]dded|force|already")
    tables = [f"heraldia:medianas/{mid}/{t}" for mid, m in median for t in m.LOOT] + \
             [f"heraldia:unicas/{sid}/{t}" for sid, m in unique_mods for t in m.LOOT]
    for t in tables:
        for _ in range(ROLLS):
            m = ctx.run(f"loot spawn 0 200 0 loot {t}", r"Dropped \d+|No items")
            if not m.group(0).startswith(("Dropped", "No items")):
                fails.append(f"loot {t}: {m.string.strip()}")
                break
    for o in dimensions.FORBIDDEN:
        if ctx.test(f'execute if entity @e[type=minecraft:item,nbt={{Item:{{id:"minecraft:{o}"}}}}]'):
            fails.append(f"the Nether or End loot gives {o}")
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    ctx.run("forceload remove 0 0 0 0", r"[Uu]nmarked|[Rr]emoved|force")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-nether-end"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    median, unique_mods = kinds()
    assert median and unique_mods
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump({}, f)                 # default configuration
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen, fails = queue.Queue(), [], []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        ctx.run("gamerule spawn_mobs false", r"Gamerule|set to|now")
        fails += check_log(ctx, median, unique_mods)
        f, generate = check_locate(ctx, median, unique_mods)
        fails += f
        fails += check_generated(ctx, generate)
        fails += check_place(ctx, median, unique_mods)
        fails += check_info(ctx, median, unique_mods)
        fails += check_loot(ctx, median, unique_mods)
        if re.search(r"Registry loading errors|Failed to load structure|Missing data pack", ctx.log()):
            fails.append("loading errors in the log")
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            proc.wait(timeout=120)
    print("NETHER AND END:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
