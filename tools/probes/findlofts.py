"""Lofts of the placed villages in a saved village_routes world: ladder columns whose top lands on cells the search
cannot leave (classify: shut in), with the foot of the ladder (a free ground cell beside its bottom rung)."""
import json, sys, math
import world, vr_strand as v
wd = sys.argv[1]
SITES = [(600, -600), (0, 600), (-600, 0), (600, 0), (0, 0), (600, 600), (0, -600), (-600, -600)]
out = []
for sx, sz in SITES:
    b = world.blocks(wd, sx - 110, sx + 110, -61, -30, sz - 110, sz + 110)
    lad = {p for p, st in b.items() if "ladder" in st}
    cols = {}
    for x, y, z in lad:
        cols.setdefault((x, z), []).append(y)
    for (x, z), ys in cols.items():
        y0, y1 = min(ys), max(ys)
        if y0 > -59 or y1 - y0 < 3:
            continue
        top, foot, deep = None, None, None
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for yy in (y1, y1 + 1):
                c = (x + dx + 0.5, float(yy), z + dz + 0.5)
                if top is None:
                    kind, comp = v.component(wd, c)
                    if kind == "shut in" and comp:
                        top = c
                        # the cell of the loft farthest from the ladder, on its floor (a villager there is not by the hole)
                        cx, cy, cz, fl = max(comp, key=lambda q: (q[0] - x) ** 2 + (q[2] - z) ** 2)
                        deep = (cx + 0.5, fl, cz + 0.5)
            c = (x + dx + 0.5, -59.0, z + dz + 0.5)
            if foot is None and v.classify(wd, c)[0] == "free":
                foot = c
        if top and foot:
            out.append(dict(site=[sx, sz], ladder=[x, z, y0, y1], loft=deep, foot=foot,
                            hole=round(((deep[0] - x - 0.5) ** 2 + (deep[2] - z - 0.5) ** 2) ** 0.5, 1)))
    print(sx, sz, "ladders from the ground", sum(1 for (x, z), ys in cols.items() if min(ys) <= -59 and max(ys) - min(ys) >= 3),
          "lofts", sum(1 for o in out if o["site"] == [sx, sz]), flush=True)
json.dump(out, open("lofts.json", "w"), indent=1)
