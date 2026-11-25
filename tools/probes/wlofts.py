"""From a saved world with the 8 village_routes villages: every ladder column from the ground, and whether its top
lands where the 26.3 villager path search cannot walk out of (tools/probes/findlofts.py, on tools/smoke/saved_world).

Usage: wlofts.py <world dir> [out.json]
"""
import json, math, os, sys, collections
REPO = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(REPO, "tools", "smoke"))
sys.path.insert(0, os.path.join(REPO, "tools", "gen"))
import saved_world as world
import lint
from mediums import _paths as P

R, FAR = 24, 12
SITES = [(600, -600), (-600, 0), (600, 0), (0, 0), (0, 600), (600, 600), (0, -600), (-600, -600)]


def ground(blocks, box):
    g = P.Ground.__new__(P.Ground)
    g.lint = lint
    g.b = {p: st for p, st in blocks.items() if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
    g.box = box
    g._floor, g._nb = {}, {}
    return g


def component(wd, pos):
    x, y, z = pos
    bx, bz = int(math.floor(x)), int(math.floor(z))
    b = world.blocks(wd, bx - R, bx + R, int(y) - 30, int(y) + 10, bz - R, bz + R)
    g = ground(b, (bx - R, bz - R, bx + R + 1, bz + R + 1))
    starts = [(cx, cy, cz) for cx in (bx - 1, bx, bx + 1) for cz in (bz - 1, bz, bz + 1)
              for cy in range(int(math.floor(y)) - 3, int(math.floor(y)) + 2) if g.floor(cx, cy, cz) is not None]
    if not starts:
        return "no floor", []
    start = min(starts, key=lambda c: (abs(c[0] + 0.5 - x) + abs(c[2] + 0.5 - z), abs(g.floor(*c) - y)))
    seen, todo, far = {start}, [start], 0
    while todo:
        n = todo.pop()
        far = max(far, math.hypot(n[0] - start[0], n[2] - start[2]))
        for m in g.neighbors(n):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return ("shut in" if far < FAR else "free"), [(c[0], c[1], c[2], g.floor(*c)) for c in seen]


def classify(wd, pos):
    return component(wd, pos)[0]


def main():
    wd = sys.argv[1]
    out, tally = [], collections.Counter()
    for sx, sz in SITES:
        b = world.blocks(wd, sx - 110, sx + 110, -61, -20, sz - 110, sz + 110)
        lad = {p for p, st in b.items() if "ladder" in st}
        cols = {}
        for x, y, z in lad:
            cols.setdefault((x, z), []).append(y)
        from_ground = 0
        site_lofts = 0
        for (x, z), ys in cols.items():
            y0, y1 = min(ys), max(ys)
            if y0 > -59 or y1 - y0 < 3:
                continue
            from_ground += 1
            top, foot, deep = None, None, None
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for yy in (y1, y1 + 1):
                    c = (x + dx + 0.5, float(yy), z + dz + 0.5)
                    if top is None:
                        kind, comp = component(wd, c)
                        if kind == "shut in" and comp:
                            top = c
                            cx, cy, cz, fl = max(comp, key=lambda q: (q[0] - x) ** 2 + (q[2] - z) ** 2)
                            deep = (cx + 0.5, fl, cz + 0.5)
                c = (x + dx + 0.5, -59.0, z + dz + 0.5)
                if foot is None and classify(wd, c) == "free":
                    foot = c
            if top:
                site_lofts += 1
                out.append(dict(site=[sx, sz], ladder=[x, z, y0, y1], loft=deep, foot=foot,
                                hole=round(((deep[0] - x - 0.5) ** 2 + (deep[2] - z - 0.5) ** 2) ** 0.5, 1),
                                free_foot=foot is not None))
        tally["ladders"] += from_ground
        tally["lofts"] += site_lofts
        print(sx, sz, "ladders from the ground", from_ground, "with a top the search cannot leave", site_lofts, flush=True)
    print("TOTAL ladders from the ground", tally["ladders"], "| tops the search cannot leave", tally["lofts"])
    json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "lofts.json", "w"), indent=1)


if __name__ == "__main__":
    main()
