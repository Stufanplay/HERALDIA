"""Terrain traps round a structure, read from a saved 26.3 world: cells an inhabitant can WALK INTO and whose path
search finds no way back to its bed.

`mediums/_paths` and `mediums/_inhabitants` audit a template standing on FLAT ground (`_paths.Ground` pads it with
MARGIN blocks of stone), so no audit of the build sees what the terrain next to the structure does. A villager walks
DOWN a drop of up to 3 blocks and climbs UP at most 1.125, so a hillside that steps down two blocks at a time, a leaf
canopy or an open cave shaft is a one-way street: from below it its search finds no path home, and after 1,200 ticks
the game makes it release its bed AND its workstation (`SetWalkTargetFromBlockMemory`, 26.3). That is the family of
docs/LESSONS.md, "A villager gets by physics to places its path search cannot leave", made by the terrain instead of
by a template.

Not a server test itself (no --jar): `tools/smoke/inhabitant_lost.py` uses it to find the trap it then puts an
inhabitant in, and `tools/probes/wtrap.py` to report every trap round a structure."""
import collections
import heapq
import math
import os
import sys

import saved_world

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import lint                          # noqa: E402
from mediums import _paths           # noqa: E402

# Plants a villager walks through: they are neither ground nor wall.
PLANTS = ("short_grass", "tall_grass", "fern", "large_fern", "dead_bush", "snow", "leaf_litter")


def spell(st):
    """A 26.3 region palette writes an all-default block state as a bare id, and `_paths.Ground` only calls a gate
    solid when it reads `open=false`: spell the defaults out before the model sees them (tools/probes/README.md)."""
    if "[" in st:
        return st
    n = st.replace("minecraft:", "")
    if n.endswith("_fence_gate"):
        return st + "[in_wall=false,open=false,powered=false]"
    if n.endswith("_door"):
        return st + "[half=lower,hinge=left,open=false,powered=false]"
    if n.endswith("_trapdoor"):
        return st + "[half=bottom,open=false,powered=false]"
    return st


def ground(world, x0, x1, y0, y1, z0, z1):
    """(`_paths.Ground` over the saved blocks of the box, how many blocks were read)."""
    b = saved_world.blocks(world, x0, x1, y0, y1, z0, z1)
    g = _paths.Ground.__new__(_paths.Ground)
    g.lint, g._floor, g._nb = lint, {}, {}
    g.b = {p: spell(st) for p, st in b.items() if not st.endswith(PLANTS)}
    g.box = (x0, z0, x1 + 1, z1 + 1)
    return g, len(b)


def stand(g, x, y, z):
    """The cell at (x, z) an entity standing near y is in, or None."""
    return next(((x, y + dy, z) for dy in (0, 1, -1, 2, -2) if g.floor(x, y + dy, z) is not None), None)


def beside(g, pos):
    """The cells an entity can stand in next to the block at `pos`, in a fixed order."""
    return sorted(c for c in _paths._beside(g, pos))


def beds(g):
    return sorted(p for p, st in g.b.items() if st.split("[")[0].endswith("_bed") and "part=head" in st)


def walk_from(g, start):
    """({cell: walk from `start`}, {cell: where it came from}), over the search's own moves."""
    dist, prev = {start: 0.0}, {start: None}
    heap = [(0.0, start)]
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist[n]:
            continue
        for m in g.neighbors(n):
            nd = d + _paths.dist(n, m)
            if nd < dist.get(m, 1e9):
                dist[m], prev[m] = nd, n
                heapq.heappush(heap, (nd, m))
    return dist, prev


def no_way_back(g, walk, anchors):
    """(the cells of `walk` whose search reaches no cell beside one of `anchors`, the cells beside the anchors)."""
    targets = {c for a in anchors for c in _paths._beside(g, a) if c in walk}
    if not targets:
        return set(walk), targets
    back = {}
    for n in walk:
        for m in g.neighbors(n):
            back.setdefault(m, []).append(n)
    home, todo = set(targets), list(targets)
    while todo:
        n = todo.pop()
        for m in back.get(n, ()):
            if m not in home:
                home.add(m)
                todo.append(m)
    return set(walk) - home, targets


def reach(g, cell):
    """The cells the search gets to from `cell` (1 means it cannot move at all)."""
    seen, q = {cell}, collections.deque([cell])
    while q:
        for m in g.neighbors(q.popleft()):
            if m not in seen:
                seen.add(m)
                q.append(m)
    return seen


def traps(g, start, anchors, box, margin=2):
    """[(cell, walk, straight, dy)] sorted by the walk into it: every cell the inhabitant walks to from `start` and
    whose search finds no way back to `anchors`, leaving out those within `margin` of the box's edge, which have no
    neighbours outside it and are the box's own artefact, not a trap."""
    x0, z0, x1, z1 = box
    dist, _ = walk_from(g, start)
    lost, _ = no_way_back(g, dist, anchors)
    out = []
    for c in lost:
        if c[0] <= x0 + margin or c[0] >= x1 - margin or c[2] <= z0 + margin or c[2] >= z1 - margin:
            continue
        out.append((c, round(dist[c], 1), round(math.hypot(c[0] - start[0], c[2] - start[2]), 1), c[1] - start[1]))
    return sorted(out, key=lambda t: (t[1], t[0]))     # the walk, then the cell: the same order every run
