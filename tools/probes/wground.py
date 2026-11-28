"""Where the ground is around a medium structure in a real world: the height of its layer 0 and, just outside its box,
the height of the highest block of the terrain. `mediums/_paths.Ground` models a medium structure's ground at
y = base - 1 of the template. If the terrain's top is level with the layer 0, the feet of a villager outside are at
layer 0 + 1 (base 1). If it is one block below, they are at layer 0 (base 0). A start piece is placed by its own rule,
`JigsawPlacement.addPieces`, not at the height of a jigsaw, so it is measured here (#86).

For each type, the structure /locate finds nearest the origin is generated (forceload), the world is saved and its start
is read from the regions. Printed: the start piece and its box, the blocks of its layer 0, and for each column one,
two and three blocks outside each side of the box, the highest ground block (`village_terrain.ground`: vegetation and
air do not count, water does) relative to the layer 0, as a histogram and with a few literal columns.

Usage: wground.py <work> <jar> [<type> ...]   (HERALDIA pointing at the repository; Java 25 on the PATH). Without types,
TYPES: one of each family whose inhabitants the build walks with `_paths`. Default configuration. Not a test, not run by
CI (tools/probes/README.md). ~3 min.
"""
import collections, json, os, sys, time
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import server_smoke as s
import village_terrain as vt

TYPES = ("posada", "molino", "pescador", "cazadores", "ermita", "torre_vigia")
LOAD = 48            # blocks forced around the /locate position: a medium structure is at most ~20 across


def start_piece(world, x, z):
    nbt = vt.region_chunk(world, x >> 4, z >> 4)
    for sid, start in (nbt.get("structures", {}).get("starts", {}) or {}).items() if nbt is not None else ():
        if "medianas" not in str(sid) or "Children" not in start:
            continue
        c = start["Children"][0]
        return str(sid), str(c.get("pool_element", {}).get("location", "")), [int(v) for v in c["BB"]]
    return None


def measure(blocks, bb):
    x0, y0, z0, x1, y1, z1 = bb
    layer0 = collections.Counter(blocks.get((x, y0, z), "minecraft:air") for x in range(x0, x1 + 1) for z in range(z0, z1 + 1))
    rows = []
    for d in (1, 2, 3):
        cols = [(x, z0 - d) for x in range(x0, x1 + 1)] + [(x, z1 + d) for x in range(x0, x1 + 1)]
        cols += [(x0 - d, z) for z in range(z0, z1 + 1)] + [(x1 + d, z) for z in range(z0, z1 + 1)]
        for x, z in cols:
            g = vt.ground(blocks, x, z, y0 + 12)
            rows.append((d, x, z, None if g is None else g - y0, None if g is None else blocks.get((x, g, z))))
    return layer0, rows


def main():
    work, jar, types = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3:] or TYPES
    os.makedirs(work, exist_ok=True)
    launcher = s.prepare(work, jar, s.gradle_properties())
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump({}, f)                                        # the default configuration
    proc, ctx = vt.start_server(work, launcher)
    found = []
    try:
        for t in types:
            m = ctx.run(f"execute positioned 0 100 0 run locate structure #heraldia:medianas/{t}",
                        r"is at \[(-?\d+), ~, (-?\d+)\]|Could not find|not a valid|Unknown")
            if not m.lastindex or m.group(1) is None:
                print(f"{t}: /locate finds nothing ({m.group(0)})", flush=True)
                continue
            x, z = int(m.group(1)), int(m.group(2))
            ctx.run(f"forceload add {x - LOAD} {z - LOAD} {x + LOAD} {z + LOAD}", r"Marked|[Aa]dded|force|already")
            found.append((t, x, z))
        for t, x, z in found:
            for dx, dz in ((-LOAD, -LOAD), (LOAD, LOAD), (0, 0)):
                ctx.until(f"execute if loaded {x + dx} 0 {z + dz}", timeout=300)
        time.sleep(5)
        ctx.run("save-all flush", r"Saved the game|saved")
    finally:
        vt.stop(proc)
    world = os.path.join(work, "world")
    for t, x, z in found:
        st = start_piece(world, x, z)
        if st is None:
            print(f"{t}: no medium structure start saved in the chunk of {x} {z}")
            continue
        sid, loc, bb = st
        blocks = vt.read_blocks(world, bb[0] - 4, bb[2] - 4, bb[3] + 4, bb[5] + 4)
        layer0, rows = measure(blocks, bb)
        print(f"{t}: {sid} {loc} BB {bb} (layer 0 at y = {bb[1]})")
        print("  layer 0:", ", ".join(f"{n.replace('minecraft:', '')} {k}" for n, k in layer0.most_common(6)))
        for d in (1, 2, 3):
            h = collections.Counter(r[3] for r in rows if r[0] == d)
            print(f"  {d} outside: terrain top - layer 0:", dict(sorted(h.items(), key=lambda kv: (kv[0] is None, kv[0]))))
        for r in [r for r in rows if r[0] == 1][::9][:6]:
            print(f"    e.g. column {r[1]} {r[2]}: top y = {bb[1] + r[3] if r[3] is not None else None} ({r[4]}), layer 0 + {r[3]}")


if __name__ == "__main__":
    main()
