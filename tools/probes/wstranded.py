"""The question itself, on a saved world and over a whole village: starting from its streets, which cells can a
villager get to -- walking, and climbing every ladder it can walk into -- from which its path search finds no way
back? No height criterion, no per-piece model: the real blocks of the placed village.

Reading fix declared in wclimb.py: a 26.3 region palette writes an all-default state as a bare id, so a closed
"minecraft:<wood>_fence_gate" carries no "open=false" for the model to see. It is spelled out before the model runs.
"""
import collections, os, sys
REPO = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(REPO, "tools", "smoke"))
sys.path.insert(0, os.path.join(REPO, "tools", "gen"))
import saved_world as world
import lint
from mediums import _paths as P

SITES = [(600, -600), (-600, 0), (600, 0), (0, 0), (0, 600), (600, 600), (0, -600), (-600, -600)]
RAD, Y0, Y1 = 110, -64, 30
DEFAULTS = "[facing=north,in_wall=false,open=false,powered=false]"


def main():
    wd = sys.argv[1]
    total = collections.Counter()
    for sx, sz in SITES:
        b = world.blocks(wd, sx - RAD, sx + RAD, Y0, Y1, sz - RAD, sz + RAD)
        g = P.Ground.__new__(P.Ground)
        g.lint = lint
        g.b = {p: (st + DEFAULTS if st.endswith("_fence_gate") else st) for p, st in b.items()
               if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
        g.box = (sx - RAD, sz - RAD, sx + RAD + 1, sz + RAD + 1)
        g._floor, g._nb = {}, {}
        # Seeded ONLY from the natural ground at the edge of the box, so the walk has to come into the village the
        # way a villager does: over the street and through the doors. (Seeding every standable cell at the walking
        # level, as a first version of this probe did, hands the walk the inside of every building AND the foot of
        # every ladder, and then says a shut ladder is open. That run was wrong and is discarded.)
        starts = []
        for x in range(sx - RAD, sx + RAD):
            for z in (sz - RAD, sz + RAD - 1):
                starts += [(x, y, z) for y in range(-62, -54) if g.floor(x, y, z) is not None][:1]
        for z in range(sz - RAD, sz + RAD):
            for x in (sx - RAD, sx + RAD - 1):
                starts += [(x, y, z) for y in range(-62, -54) if g.floor(x, y, z) is not None][:1]
        walk, todo = set(starts), list(starts)
        while todo:
            for c in g.neighbors(todo.pop()):
                if c not in walk:
                    walk.add(c)
                    todo.append(c)
        cols = {}
        for (x, y, z), st in b.items():
            if "ladder" in st:
                cols.setdefault((x, z), []).append(y)
        landing = []
        for (x, z), ys in cols.items():
            cs = set()
            for y in range(min(ys), max(ys) + 2):
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
        stuck = reach - home
        climbed = sum(1 for cs in landing if cs & walk)
        print(sx, sz, "| street walk", len(walk), "| ladders it can walk into", climbed,
              "of", len(landing), "| cells it cannot walk back from", len(stuck),
              "| heights", sorted({c[1] for c in stuck})[:8], flush=True)
        total["walk"] += len(walk)
        total["climbable"] += climbed
        total["ladders"] += len(landing)
        total["stranded"] += len(stuck)
    print("TOTAL", dict(total))


if __name__ == "__main__":
    main()
