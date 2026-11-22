"""From a village_routes --verbose log and its saved world: which villagers end the day where their path search cannot
get out of (a loft, a belfry, the top of a ladder), as opposed to just standing high on a slope or upstairs by stairs."""
import math, re, sys
sys.path.insert(0, "/home/user/HERALDIA/tools/gen")
import lint, world
from mediums import _paths as P

R = 24              # blocks read around each villager
FAR = 12            # its search gets at least this far horizontally: it is not shut in


def ground(blocks, box):
    g = P.Ground.__new__(P.Ground)
    g.lint = lint
    g.b = {p: st for p, st in blocks.items() if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
    g.box = box
    g._floor, g._nb = {}, {}
    return g


def component(wd, pos):
    """(kind, [(x, y, z, floor)] of the cells its search reaches from pos) on the real blocks."""
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
    x, y, z = pos
    bx, bz = int(math.floor(x)), int(math.floor(z))
    b = world.blocks(wd, bx - R, bx + R, int(y) - 30, int(y) + 10, bz - R, bz + R)
    g = ground(b, (bx - R, bz - R, bx + R + 1, bz + R + 1))
    starts = [(cx, cy, cz) for cx in (bx - 1, bx, bx + 1) for cz in (bz - 1, bz, bz + 1)
              for cy in range(int(math.floor(y)) - 3, int(math.floor(y)) + 2) if g.floor(cx, cy, cz) is not None]
    if not starts:
        return "no floor (in a shaft or on a ladder)", 0, None
    start = min(starts, key=lambda c: (abs(c[0] + 0.5 - x) + abs(c[2] + 0.5 - z), abs(g.floor(*c) - y)))
    seen, todo, far = {start}, [start], 0
    while todo:
        n = todo.pop()
        far = max(far, math.hypot(n[0] - start[0], n[2] - start[2]))
        for m in g.neighbors(n):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    # naive: how high above the lowest standable cell within 3 blocks horizontally
    low = min((c[1] for c in g._floor if g._floor[c] is not None and abs(c[0] - bx) <= 3 and abs(c[2] - bz) <= 3), default=start[1])
    return ("shut in" if far < FAR else "free"), round(far, 1), start[1] - low


if __name__ == "__main__":
    log, wd = sys.argv[1], sys.argv[2]
    rows = []
    for l in open(log):
        m = re.search(r"RUTAS:\s+(\w{8}) from \(([^)]*)\) to \(([^)]*)\)( asleep)?: (.*)", l)
        if m:
            rows.append((m.group(1), tuple(float(v) for v in m.group(3).split(",")), bool(m.group(4)), m.group(5)))
    out = {"shut in": 0, "free": 0, "no floor (in a shaft or on a ladder)": 0}
    high = 0
    for u, pos, asleep, mem in rows:
        kind, far, naive = classify(wd, pos)
        out[kind] += 1
        high += naive is not None and naive > 3
        if kind != "free" or (naive is not None and naive > 3):
            print(u, pos, kind, "reach", far, "naive height", naive, "asleep" if asleep else "", mem[:120])
    print(len(rows), "villagers:", out, "| naive: more than 3 above the lowest ground within 3 blocks:", high)
