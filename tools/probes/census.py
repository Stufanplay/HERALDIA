"""Census of village templates: ladder columns a villager can climb from the ground, and whether the top is a place
its path search cannot walk back down from. Model: tools/gen/mediums/_paths (the 26.3 search: no ladders, drops of 3).

Usage: census.py <repo> [out.json]
"""
import json, os, sys, collections

REPO = os.path.abspath(sys.argv[1])
GEN = os.path.join(REPO, "tools", "gen")
sys.path.insert(0, GEN)

VILLAGE = ("house", "street", "tower", "gate", "decor", "plaza", "avenue", "filler", "tablon", "trace")


def is_village(kind):
    return kind in VILLAGE or kind.startswith("special:")


def analyse(t):
    """(ladders_from_ground, [(ladder, n_stranded_cells, max_drop)]) for one template."""
    from mediums import _paths as P
    g = P.Ground(t)
    sx, _, sz = t.size()
    m = P.MARGIN
    # the flat ground modelled around the template: start the walk from the outer ring
    starts = []
    for x in range(-m, sx + m):
        for z in (-m, sz + m - 1):
            if g.floor(x, 0, z) is not None:
                starts.append((x, 0, z))
    for z in range(-m, sz + m):
        for x in (-m, sx + m - 1):
            if g.floor(x, 0, z) is not None:
                starts.append((x, 0, z))
    if not starts:
        return 0, [], 0
    walk, todo = set(starts), list(starts)
    while todo:
        for c in g.neighbors(todo.pop()):
            if c not in walk:
                walk.add(c)
                todo.append(c)

    ladders = P._ladder_columns(t)
    landing = []
    for x, z, y0, y1 in ladders:
        cs = set()
        for y in range(y0, y1 + 2):
            for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (0, 1):
                    c = (x + dx, y + dy, z + dz)
                    if g.floor(*c) is not None:
                        cs.add(c)
        landing.append(((x, z, y0, y1), cs))

    # physically reachable: walking from the outside ground, plus up and down every ladder reached
    reach, todo = set(walk), list(walk)
    while todo:
        n = todo.pop()
        nxt = list(g.neighbors(n))
        for _, cs in landing:
            if n in cs:
                nxt += cs
        for c in nxt:
            if c not in reach:
                reach.add(c)
                todo.append(c)
    # from where the search walks back to the outside ground (reverse edges, no ladders)
    back = {}
    for n in reach:
        for c in g.neighbors(n):
            back.setdefault(c, []).append(n)
    home, todo = set(walk), list(walk)
    while todo:
        n = todo.pop()
        for c in back.get(n, ()):
            if c not in home:
                home.add(c)
                todo.append(c)

    stuck = reach - home
    from_ground, bad = 0, []
    nstuck = len(stuck)
    for lad, cs in landing:
        x, z, y0, y1 = lad
        # climbed from the ground: a cell of the walk is beside the lowest rungs
        low = {c for c in cs if c[1] <= y0 + 1}
        if not (low & walk):
            continue
        if y1 - y0 < 3:
            continue
        from_ground += 1
        s = sorted(c for c in cs if c in stuck)
        if s:
            # how far the search would have to drop to get out, as the loft's height over the walk floor
            top = max(c[1] for c in s)
            bad.append((list(lad), len(s), top - y0, [list(c) for c in s[:3]]))
    return from_ground, bad, nstuck


def stranded_cells(t):
    """The cells a villager reaches by climbing but its search cannot walk back from, for one template."""
    from mediums import _paths as P
    g = P.Ground(t)
    sx, _, sz = t.size()
    m = P.MARGIN
    starts = [(x, 0, z) for x in range(-m, sx + m) for z in (-m, sz + m - 1) if g.floor(x, 0, z) is not None]
    starts += [(x, 0, z) for z in range(-m, sz + m) for x in (-m, sx + m - 1) if g.floor(x, 0, z) is not None]
    if not starts:
        return set()
    walk, todo = set(starts), list(starts)
    while todo:
        for c in g.neighbors(todo.pop()):
            if c not in walk:
                walk.add(c)
                todo.append(c)
    landing = []
    for x, z, y0, y1 in P._ladder_columns(t):
        cs = set()
        for y in range(y0, y1 + 2):
            for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (0, 1):
                    c = (x + dx, y + dy, z + dz)
                    if g.floor(*c) is not None:
                        cs.add(c)
        landing.append(cs)
    reach, todo = set(walk), list(walk)
    while todo:
        n = todo.pop()
        nxt = list(g.neighbors(n))
        for cs in landing:
            if n in cs:
                nxt += cs
        for c in nxt:
            if c not in reach:
                reach.add(c)
                todo.append(c)
    back = {}
    for n in reach:
        for c in g.neighbors(n):
            back.setdefault(c, []).append(n)
    home, todo = set(walk), list(walk)
    while todo:
        n = todo.pop()
        for c in back.get(n, ()):
            if c not in home:
                home.add(c)
                todo.append(c)
    return reach - home


def main():
    import pack
    reg = pack.build_all()
    names = sorted(n for n, k in reg.kinds.items() if is_village(k))
    print(len(names), "village templates of", len(reg.templates), flush=True)
    rows = {}
    for i, n in enumerate(names):
        try:
            rows[n] = analyse(reg.templates[n])
        except Exception as e:                       # noqa: BLE001
            rows[n] = ("error", repr(e))
        if (i + 1) % 100 == 0:
            print("...", i + 1, flush=True)
    out = {}
    tot_lad = tot_bad_t = 0
    bykind = collections.Counter()
    badkind = collections.Counter()
    errors = []
    for n, r in rows.items():
        if r[0] == "error":
            errors.append((n, r[1]))
            continue
        fg, bad, nstuck = r
        k = reg.kinds[n]
        if fg:
            bykind[k] += 1
            tot_lad += fg
        if bad:
            badkind[k] += 1
            tot_bad_t += 1
        out[n] = dict(kind=k, from_ground=fg, bad=bad, stranded_cells=nstuck)
    print("ERRORS:", len(errors), errors[:5])
    print("templates with a ladder of 4+ from the ground:", sum(bykind.values()),
          "| ladder columns:", tot_lad)
    print("of those, templates where the top is a place the search cannot leave:", tot_bad_t)
    print("--- by kind (with ladder / with a no-way-down top) ---")
    for k in sorted(set(bykind) | set(badkind)):
        print(f"  {k:24s} {bykind[k]:4d} {badkind[k]:4d}")
    json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "census.json", "w"), indent=1)


if __name__ == "__main__":
    main()
