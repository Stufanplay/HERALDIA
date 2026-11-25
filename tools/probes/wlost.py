"""Which cells of the villagers' walk the closets cost, over the 8 villages: the gates' own cells, the ladders' feet,
and anything else (there must be nothing else). Same model and same seeding as wstranded.py."""
import collections, os, sys
REPO = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(REPO, "tools", "smoke"))
sys.path.insert(0, os.path.join(REPO, "tools", "gen"))
import saved_world as world
import lint
from mediums import _paths as P
SITES = [(600, -600), (-600, 0), (600, 0), (0, 0), (0, 600), (600, 600), (0, -600), (-600, -600)]
RAD, Y0, Y1 = 110, -64, 30
D = "[facing=north,in_wall=false,open=false,powered=false]"


def walk(wd, sx, sz):
    b = world.blocks(wd, sx - RAD, sx + RAD, Y0, Y1, sz - RAD, sz + RAD)
    g = P.Ground.__new__(P.Ground)
    g.lint = lint
    g.b = {p: (st + D if st.endswith("_fence_gate") else st) for p, st in b.items()
           if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
    g.box = (sx - RAD, sz - RAD, sx + RAD + 1, sz + RAD + 1)
    g._floor, g._nb = {}, {}
    starts = []
    for x in range(sx - RAD, sx + RAD):
        for z in (sz - RAD, sz + RAD - 1):
            starts += [(x, y, z) for y in range(-62, -54) if g.floor(x, y, z) is not None][:1]
    for z in range(sz - RAD, sz + RAD):
        for x in (sx - RAD, sx + RAD - 1):
            starts += [(x, y, z) for y in range(-62, -54) if g.floor(x, y, z) is not None][:1]
    seen, todo = set(starts), list(starts)
    while todo:
        for c in g.neighbors(todo.pop()):
            if c not in seen:
                seen.add(c)
                todo.append(c)
    return seen, b


tot = collections.Counter()
for sx, sz in SITES:
    a, ba = walk(sys.argv[1], sx, sz)
    c, bc = walk(sys.argv[2], sx, sz)
    for p in a - c:
        after, before = bc.get(p, "air"), ba.get(p, "air")
        if "fence_gate" in after and "ladder" in before:
            tot["the ladder's own foot, now a gate"] += 1
        elif "fence_gate" in after:
            tot["a cell beside the ladder, now a gate"] += 1
        elif "ladder" in before and "ladder" in after:
            tot["the ladder's foot (no longer reachable)"] += 1
        else:
            tot[f"SOMETHING ELSE: {before.split('[')[0]} -> {after.split('[')[0]}"] += 1
    tot["gained"] += len(c - a)
print("cells the villagers' walk loses, by what is there now:")
for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
    print(f"  {v:5d}  {k}")
