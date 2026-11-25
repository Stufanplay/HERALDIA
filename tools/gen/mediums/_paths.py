"""The way home of a medium structure's inhabitant, as the 26.3 villager path search sees it (a model, not the game's
code). What it rests on, read with javap from PathFinder.findPath and PathNavigation.createPath (26.3) and seen on a
server (docs/LESSONS.md, "A villager's search never finds a path of 16 blocks or more"):
- a search opens a node only while the walked distance to it (straight steps 1, diagonal ones sqrt 2) is under the
  villager's follow_range, 16: no path of 16 blocks or more is ever found, whatever the node budget (256);
- the heuristic is weighted (h x 1.5), so the search runs straight at the bed and, when it does not get there, the
  partial path it hands back ends at the explored node closest to the bed in a straight line;
- a villager walking home follows those partial paths, so behind the wall of its bedroom, with the door at the far end,
  it stops against the wall: the TRAP. From there it only gets out by luck (MoveToTargetSink tries random spots toward
  the bed), and after 1,200 ticks unable to reach it the game makes it give the bed up.
`trap_walk` gives, for each bed, the trap a villager coming home ends in and the walk from it to the bed. On a flat
platform (tools/bed_probe.py --ret), a villager taken to the yard at nightfall and left to come home failed from traps
26 blocks away or more (inn without its back door 26.1: 3 of 8 and 36.1: 4 of 8; hermitage 31.8: 5 of 8) and never from
24.4 or less (0 of 64 over six templates). The template is modelled standing on flat ground MARGIN blocks around it.
The walkable cells are a simplified WalkNodeEvaluator: feet in a passable or low (<= 0.6) block, solid ground under,
1.95 of headroom; steps up of a block (a jump), drops of up to 3; diagonals only past two clear sides and never through
a door; wooden doors open, iron doors, closed fence gates, fences, walls, panes and leaves do not; water costs 8."""
import heapq
import math

MARGIN = 16                 # flat ground modelled around the template
FOLLOW_RANGE = 16.0         # a villager's follow_range (26.3 default): the longest walk its search finds
TRAP_WALK_MAX = 25.0        # longest walk from a trap to its bed: between 24.4 (passed) and 26.1 (failed), see above


def _name(st):
    return st.split("[")[0].replace("minecraft:", "") if st else None


class Ground:
    """The template (as a villager sees it: _inhabitants._no_ladders) on flat ground."""

    def __init__(self, t, margin=MARGIN):
        import lint
        from . import _inhabitants as inh
        self.lint = lint
        view = lint.resolved(inh._no_ladders(t))
        self.b = {p: st for p, (st, _) in view.blocks.items() if st and _name(st) not in ("air", "structure_void", "jigsaw")}
        sx, _, sz = t.size()
        self.box = (-margin, -margin, sx + margin, sz + margin)
        for x in range(-margin, sx + margin):
            for z in range(-margin, sz + margin):
                self.b.setdefault((x, -1, z), "minecraft:stone")
        self._floor, self._nb = {}, {}

    def solid(self, st):
        if st is None:
            return False
        n = _name(st)
        if n == "water":
            return False
        if n.endswith("_door"):
            return n == "iron_door"
        if self.lint.passable(st):
            return n.endswith("_fence_gate") and "open=false" in st
        return True

    def floor(self, x, y, z):
        """Feet height of a villager with its feet in cell (x, y, z), or None if it cannot stand there."""
        k = (x, y, z)
        if k not in self._floor:
            self._floor[k] = self._stand(x, y, z)
        return self._floor[k]

    def _stand(self, x, y, z):
        x0, z0, x1, z1 = self.box
        if not (x0 <= x < x1 and z0 <= z < z1):
            return None
        top_height = self.lint.top_height
        f = self.b.get((x, y, z))
        n = _name(f)
        if n and (n.endswith(("_fence", "_wall", "_leaves", "_pane")) or n == "iron_bars"
                  or n.endswith("_fence_gate") and "open=false" in f):
            return None
        if f is not None and self.solid(f):
            h = top_height(f)
            if h is None or h > 0.6:
                return None
            fl = y + h
        else:
            below = self.b.get((x, y - 1, z))
            if below is None or not self.solid(below) and _name(below) != "water":
                return None
            nb = _name(below)
            if nb.endswith(("_fence", "_wall", "_fence_gate")):
                return None
            if nb != "water" and (top_height(below) or 0) < 1.0:
                return None              # standing in the low block below: that is the cell of y - 1
            fl = float(y)
        top, cy = fl + 1.95, y + 1
        while cy < top:
            st = self.b.get((x, cy, z))
            if self.solid(st) and cy + (0.5 if ("half=top" in st or "type=top" in st) else 0.0) < top:
                return None
            cy += 1
        return fl

    def _door(self, c):
        n = _name(self.b.get(c))
        return bool(n) and n.endswith("_door")

    def malus(self, c):
        return 8.0 if _name(self.b.get(c)) == "water" else 0.0

    def _step(self, x, y, z, dx, dz):
        f = self.floor(x, y, z)
        nx, nz = x + dx, z + dz
        clear_jump = not self.solid(self.b.get((x, y + 2, z)))
        fn = self.floor(nx, y, nz)
        if fn is not None:
            return (nx, y, nz) if fn - f <= 0.6 or fn - f <= 1.125 and clear_jump else None
        if self.solid(self.b.get((nx, y, nz))) or self.solid(self.b.get((nx, y + 1, nz))):
            fu = self.floor(nx, y + 1, nz)
            return (nx, y + 1, nz) if fu is not None and fu - f <= 1.125 and clear_jump else None
        for d in range(1, 4):
            if self.floor(nx, y - d, nz) is not None:
                return (nx, y - d, nz)
            if self.solid(self.b.get((nx, y - d, nz))):
                return None
        return None

    def neighbors(self, n):
        if n in self._nb:
            return self._nb[n]
        x, y, z = n
        orth, out = {}, []
        for dx, dz in ((0, 1), (-1, 0), (1, 0), (0, -1)):
            m = orth[(dx, dz)] = self._step(x, y, z, dx, dz)
            if m:
                out.append(m)
        if not self._door(n):
            for dx, dz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                a, b = orth[(dx, 0)], orth[(0, dz)]
                if not a or not b or a[1] > y or b[1] > y or self._door(a) or self._door(b):
                    continue
                m = self._step(x, y, z, dx, dz)
                if m and m[1] <= y and not self._door(m):
                    out.append(m)
        self._nb[n] = out
        return out

    def cells(self):
        x0, z0, x1, z1 = self.box
        ys = range(min(p[1] for p in self.b), max(p[1] for p in self.b) + 2)
        return [(x, y, z) for x in range(x0, x1) for z in range(z0, z1) for y in ys if self.floor(x, y, z) is not None]


def dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def find_path(g, start, target, follow=FOLLOW_RANGE, reach=1):
    """PathFinder.findPath (26.3): (reached, the node the path ends at). Budget follow x 16 visited nodes; a node is opened
    only while its walked distance is under `follow` and expanded only within `follow` of the start; h is the straight
    distance to the target x 1.5; reached at a Manhattan distance <= `reach` from the target (a bed: 1)."""
    budget = int(follow * 16)
    gs, walked, closed, inopen = {start: 0.0}, {start: 0.0}, set(), {start}
    best = (dist(start, target), start)
    heap, k, visited = [(best[0], 0, start)], 0, 0
    while heap and visited < budget:
        _, _, n = heapq.heappop(heap)
        if n not in inopen:
            continue
        inopen.discard(n)
        closed.add(n)
        visited += 1
        if abs(n[0] - target[0]) + abs(n[1] - target[1]) + abs(n[2] - target[2]) <= reach:
            return True, n
        if dist(n, start) >= follow:
            continue
        for m in g.neighbors(n):
            if m in closed:
                continue
            d = dist(n, m)
            walked[m] = walked[n] + d           # kept even when the update is turned down, as in the game
            tg = gs[n] + d + g.malus(m)
            if walked[m] < follow and (m not in inopen or tg < gs[m]):
                gs[m] = tg
                hm = dist(m, target)
                if hm < best[0]:
                    best = (hm, m)
                k += 1
                inopen.add(m)
                heapq.heappush(heap, (tg + 1.5 * hm, k, m))
    return False, best[1]


def walks(g, bed):
    """{cell: walk to the bed} over the cells connected to it (straight steps 1, diagonal ones sqrt 2)."""
    src = [c for c in _beside(g, bed)]
    d = {c: 0.0 for c in src}
    heap = [(0.0, c) for c in src]
    while heap:
        dd, n = heapq.heappop(heap)
        if dd > d[n]:
            continue
        for m in g.neighbors(n):
            nd = dd + dist(n, m)
            if nd < d.get(m, 1e9):
                d[m] = nd
                heapq.heappush(heap, (nd, m))
    return d


def _beside(g, bed):
    x, y, z = bed
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = (x + dx, y + dy, z + dz)
                if abs(dx) + abs(dy) + abs(dz) <= 1 and g.floor(*c) is not None:
                    yield c


def beds(t):
    return sorted(p for p, (st, _) in t.blocks.items() if _name(st).endswith("_bed") and "part=head" in st)


def trap_walk(t):
    """[(bed, trap, walk)]: for each bed of the template, the worst trap (a cell where the search, run from it, hands back
    a partial path that does not move it) within 16 blocks of the bed in a straight line and near its floor, and the walk
    from it to the bed; (bed, None, 0.0) if there is none."""
    g = Ground(t)
    out = []
    for bed in beds(t):
        d = walks(g, bed)
        worst = (0.0, None)
        # the longest walks first: the first trap is the worst one (a walk under 16 is always found)
        for c, wd in sorted(d.items(), key=lambda kv: -kv[1]):
            if wd < FOLLOW_RANGE:
                break
            if abs(c[1] - bed[1]) > 1 or math.hypot(c[0] - bed[0], c[2] - bed[2]) > FOLLOW_RANGE:
                continue
            ok, end = find_path(g, c, bed)
            if not ok and end == c:
                worst = (wd, c)
                break
        out.append((bed, worst[1], round(worst[0], 1)))
    return out


def _ladder_columns(t):
    """[(x, z, y0, y1)]: each run of ladders stacked in a column of the template (as written, before _no_ladders)."""
    cells = sorted(p for p, (st, _) in t.blocks.items() if _name(st) == "ladder")
    runs, seen = [], set()
    for x, y, z in cells:
        if (x, y, z) in seen:
            continue
        y1 = y
        while (x, y1 + 1, z) in t.blocks and _name(t.blocks[(x, y1 + 1, z)][0]) == "ladder":
            y1 += 1
        seen.update((x, yy, z) for yy in range(y, y1 + 1))
        runs.append((x, z, y, y1))
    return runs


def stranded(t):
    """[(cell, ladder)]: cells a villager can get to (walking, and climbing a ladder, which it does by just walking into
    one; its path search never uses ladders) from which its search finds no way back to a bed the inhabitants use: up
    there it cannot get home or to work, and after 1,200 ticks the game makes it give both up. Seen in CI: the hunters'
    lodge's two inhabitants on top of its lookout, 4 blocks above the ground (a search allows drops of 3 at most)."""
    from . import _inhabitants as inh
    g = Ground(t)
    # the beds an inhabitant can use: those its search reaches from where the inhabitants spawn (a bed up a ladder is
    # not one: the watchtower's upper bed, which its search never claims)
    spawn = [tuple(int(v // 1) for v in (x, y, z)) for x, y, z, n in t.entities
             if n["id"] == "minecraft:villager" and inh.is_inhabitant(n)]
    ground, todo = set(), [c for x, y, z in spawn for c in ((x, y, z), (x, y + 1, z)) if g.floor(*c) is not None]
    ground.update(todo)
    while todo:
        for m in g.neighbors(todo.pop()):
            if m not in ground:
                ground.add(m)
                todo.append(m)
    targets = {c for b in beds(t) for c in _beside(g, b) if c in ground}
    if not targets:
        return []
    ladders = _ladder_columns(t)
    # the cells at each ladder: the ladder cells themselves and those beside them, at any height of the run (+1)
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
    # where a villager physically gets: walking from the beds, plus up and down every ladder it reaches
    reach, todo = set(targets), list(targets)
    while todo:
        n = todo.pop()
        nxt = list(g.neighbors(n))
        for _, cs in landing:
            if n in cs:
                nxt += cs
        for m in nxt:
            if m not in reach:
                reach.add(m)
                todo.append(m)
    # from where its search gets back to a bed: backwards over the search's own moves (no ladders)
    back = {}
    for n in reach:
        for m in g.neighbors(n):
            back.setdefault(m, []).append(n)
    home, todo = set(targets), list(targets)
    while todo:
        n = todo.pop()
        for m in back.get(n, ()):
            if m not in home:
                home.add(m)
                todo.append(m)
    out = []
    for lad, cs in landing:
        for c in sorted(reach - home):
            out.append((c, lad))
    seen, res = set(), []
    for c, lad in out:
        if c not in seen:
            seen.add(c)
            res.append((c, lad))
    return res
