"""Village pieces side by side: a place the game's path search reaches over the join of two pieces, that no template
audit can see because it is in neither template.

Found in the walled cemetery (`specials.cemetery`: a 1.5-high wall, one gate, shut on purpose, and nobody placed
inside). Villagers got in and stayed: the plot beside it (`fillers/plot`) carried its trace (`traces/<kind>`) a block
above the plot's ground, because a jigsaw facing up places its child's jigsaw in the cell ABOVE it, and from the
trace's floor the top of the cemetery wall is half a block up. The game's search walks there: in 26.3
`WalkNodeEvaluator.getPathTypeStatic` gives an open cell above a wall, a fence or a shut gate (`FENCE`) the type
`WALKABLE`, with its floor at the top of that block (+1.5), and a step up of 1.125 or less is a move. From the wall top
it drops inside, and from inside the wall top is 1.5 up: no way out. Measured on a server with
tools/probes/wcemetery.py (docs/LESSONS.md, "A villager gets into a walled cemetery").

What this audit does, at the cost of one walk per piece (not per pair):
  1. `placed(reg, h)`: each village piece as it stands once placed, with the children of its upward slots (`heraldia:slot`
     facing up) put where the game puts them, one cell above the slot. Only children whose footprint reaches the
     host's border are composed: a child inside the piece does not change what a neighbour can step onto.
  2. `profile(t)`: on flat ground, from the ground around it, with the model that stands on wall tops
     (`mediums/_paths.Ground`): the feet heights of the cells of its border a villager reaches on foot (`floors`), and
     the tops of the barriers on its border (walls, fences, shut gates) behind which lies a cell the search cannot walk
     out of (`traps`). Heights are from the piece's entrance (its `heraldia:entrance` jigsaw): pieces side by side
     along a street are placed with their entrances at the street's level.
  3. `issues(reg)`: within each style, a piece with a border floor from which a trap barrier of another piece is a
     move up (at most JUMP higher) or a drop (at most DROP lower) is a way in that neither piece shows. One finding per
     piece of each such pair (the audit counts templates); `pairs` names the other piece.
Streets, avenues and plazas are not paired: they are placed on the terrain, not at an entrance's level. Rollable
children are composed unrotated. Both are recorded as limits in docs/LESSONS.md.
"""
MARGIN = 3              # flat ground around the piece, as in ladders.py
JUMP = 1.125            # the highest step up of a villager's search (WalkNodeEvaluator: DEFAULT_MOB_JUMP_HEIGHT)
DROP = 3                # the longest drop it takes (_paths: drops of up to 3)
SIDE = ("house", "filler")   # the side pieces of a street (with `special:*`), placed at their entrance's level


def _ns(n):
    return n.replace("heraldia:", "")


def _name(st):
    return st.split("[")[0].replace("minecraft:", "") if st else ""


def is_side(kind):
    return kind in SIDE or kind.startswith("special:")


def _base(t):
    """The y of the piece's street entrance (0 for most; 1 for a filler with something dug below its floor)."""
    ys = [j["pos"][1] for j in t.jigsaws if j["name"] == "heraldia:entrance"
          and not j["orientation"].startswith(("up", "down"))]
    return min(ys) if ys else 0


def _at_entrance(t):
    """The piece moved down so that its entrance is at y = 0: `_paths.Ground` lays the flat ground at y = -1, and a piece
    with something below its floor (a well, the plot's slot) has its floor, and its entrance, at y = 1."""
    base = _base(t)
    if not base:
        return t
    from core import Template
    u = Template(t.name)
    u.blocks = {(x, y - base, z): v for (x, y, z), v in t.blocks.items()}
    u.jigsaws = [dict(j, pos=(j["pos"][0], j["pos"][1] - base, j["pos"][2])) for j in t.jigsaws]
    u.min_size = t.min_size
    return u


def compose(h, j, c):
    """The host `h` with the child `c` placed at the upward jigsaw `j` as the game places it: the child's matching
    jigsaw (facing down) in the cell above `j`, unrotated. Jigsaws are resolved to their final states; the child's air
    overwrites the host, its structure voids do not."""
    import lint
    from core import Template
    cj = next(k for k in c.jigsaws if k["name"] == j["target"] and k["orientation"].startswith("down_"))
    ox = j["pos"][0] - cj["pos"][0]
    oy = j["pos"][1] + 1 - cj["pos"][1]
    oz = j["pos"][2] - cj["pos"][2]
    u = Template(f"{h.name}+{c.name}")
    u.blocks = {p: (st, None) for p, (st, _) in lint.resolved(h).blocks.items()}
    for (x, y, z), (st, _) in lint.resolved(c).blocks.items():
        u.blocks[(x + ox, y + oy, z + oz)] = (st, None)
    u.jigsaws = [k for k in h.jigsaws if k is not j]
    u.min_size = h.size()
    return u


def _touches_border(h, j, c):
    sx, _, sz = h.size()
    cj = next((k for k in c.jigsaws if k["name"] == j["target"] and k["orientation"].startswith("down_")), None)
    if cj is None:
        return False
    ox, oz = j["pos"][0] - cj["pos"][0], j["pos"][2] - cj["pos"][2]
    return any(x + ox in (0, sx - 1) or z + oz in (0, sz - 1) or not (0 <= x + ox < sx and 0 <= z + oz < sz)
               for (x, _, z), (st, _) in c.blocks.items() if _name(st) not in ("air", "structure_void", "jigsaw"))


def placed(reg, name):
    """[(label, template)]: the piece as it stands once placed. The bare piece, and one composite per child of an
    upward slot that reaches its border (a slot's pool can also be switched off: the traces' option leaves the plot
    bare)."""
    h = reg.templates[name]
    out = [(name, h)]
    for j in h.jigsaws:
        if not j["orientation"].startswith("up_"):
            continue
        pool = reg.pools.get(j["pool"])
        for loc, *_ in (pool or {}).get("elements", ()):
            c = reg.templates.get(_ns(loc)) if loc else None
            if c is not None and _touches_border(h, j, c):
                out.append((f"{name} + {c.name}", compose(h, j, c)))
    return out


def profile(t):
    """(floors, traps): {feet height: a border cell} a villager reaches on foot from the ground, and {feet height: a
    border cell} it can stand on that is, or leads by one move of the search into, a cell the search cannot walk out
    of. Heights from the entrance's level."""
    import ladders
    from mediums import _paths as P
    t = _at_entrance(t)
    g = P.Ground(t, margin=MARGIN)
    sx, _, sz = t.size()
    base = 0
    walk = ladders.ground_walk(t, g)
    # the three sides a neighbour can stand against: not the entrance's (z = 0), which faces the street
    border = lambda x, z: 0 <= x < sx and 0 < z < sz and (x in (0, sx - 1) or z == sz - 1)
    # {feet height: (cell, highest feet it can rise to there)}. The rise matters: a step onto a wall's top lifts the
    # villager's box while it still stands over its own cell, so a roof above that cell stops it although the game's
    # search plans the step (measured: the well's rim under its roof, 4 of 4 villagers with the cemetery's lectern as
    # their potential job site, pressed against the wall, none of them on it)
    floors = {}
    for c in sorted(walk):
        if border(c[0], c[2]):
            f = round(g.floor(*c) - base, 3)
            rise = _ceiling(g, c) - 1.95 - base
            if f not in floors or rise > floors[f][1]:
                floors[f] = (c, rise)
    # the cells from which the search gets out: backwards from the ground ring over the search's own moves
    x0, z0, x1, z1 = g.box
    out_ring = {c for c in walk if c[0] in (x0, x1 - 1) or c[2] in (z0, z1 - 1)}
    traps, free = {}, {}

    def gets_out(start):
        """Does the search walk from `start` to the ground ring? Every cell such a walk reaches shares a no."""
        if start not in free:
            seen, todo, ok = {start}, [start], False
            while todo:
                n = todo.pop()
                if n in out_ring or free.get(n):
                    ok = True
                    break
                for m in g.neighbors(n):
                    if m not in seen:
                        seen.add(m)
                        todo.append(m)
            if ok:
                free[start] = True
            else:
                free.update(dict.fromkeys(seen, False))
        return free[start]

    # the cells of the border on the top of a barrier (a wall, a fence, a shut gate, a hedge) from which a villager is
    # in, or moves into, a cell it cannot walk out of: the way into a pen a neighbour may hand it. Only barriers: a
    # roof's eave next to a neighbour's high point is the model's too, but the one measured (the building site's
    # scaffold beside a house) the game's search never reached (0 of 48 strolling, 0 of 4 with a job site there)
    ys = range(min(p[1] for p in g.b), max(p[1] for p in g.b) + 2)
    for x in range(sx):
        for z in range(1, sz):
            if not border(x, z):
                continue
            for y in ys:
                e = (x, y, z)
                if g.floor(*e) is None or not _barrier(g.b.get((x, y - 1, z))):
                    continue
                if not gets_out(e) or any(not gets_out(m) for m in g.neighbors(e)):
                    traps.setdefault(round(g.floor(*e) - base, 3), e)
    return floors, traps


def _barrier(st):
    n = _name(st)
    return n.endswith(("_wall", "_fence", "_leaves")) or n.endswith("_fence_gate") and "open=true" not in (st or "")


def _ceiling(g, c, up=8):
    """The height of the first solid block over the cell `c` (its bottom; a top slab or stair starts half a block up)."""
    x, y, z = c
    for cy in range(y + 1, y + up):
        st = g.b.get((x, cy, z))
        if g.solid(st):
            return cy + (0.5 if ("half=top" in st or "type=top" in st) else 0.0)
    return float("inf")


def _style(name):
    return name.split("/")[0]


def profiles(reg, names=None):
    """{label: (style, template name, floors, traps)} of every side piece as placed (in parallel, like the audit)."""
    import parallel
    names = names if names is not None else [n for n in reg.templates if is_side(reg.kinds.get(n, ""))]
    jobs = [(n, lab, t) for n in names for lab, t in placed(reg, n)]
    found = parallel.map_obj(lambda job: profile(job[2]), jobs, chunksize=8)
    return {lab: (_style(n), n, fl, tr) for (n, lab, _), (fl, tr) in zip(jobs, found)}


def pairs(profs):
    """[(label A, floor, cell A, label B, top, barrier B)]: A's border floor from which B's trap barrier is a move."""
    by_style = {}
    for lab, (st, n, fl, tr) in profs.items():
        by_style.setdefault(st, []).append((lab, fl, tr))
    out = []
    for st, items in by_style.items():
        tops = sorted({top for _, _, tr in items for top in tr})
        if not tops:
            continue
        for la, fl, _ in items:
            for f, (ca, rise) in fl.items():
                for top in tops:
                    if top - JUMP <= f <= top + DROP and (top <= f or top <= rise):
                        for lb, _, tr in items:
                            if top in tr and lb != la:
                                out.append((la, f, ca, lb, top, tr[top]))
    return out


MSG = "a villager steps from a neighbouring piece onto a barrier with a pen behind it that it cannot leave"


def issues(reg):
    """{template: [(message, position)]} for the design audit: each template on either side of a pair, once (the audit
    counts templates; `pairs` gives the other piece of each)."""
    res = {}
    for la, f, ca, lb, top, cb in pairs(profiles(reg)):
        for lab, pos in ((la, ca), (lb, cb)):
            name = lab.split(" + ")[0]
            if name not in res:
                res[name] = [(MSG, pos)]
    return res
