"""Village ladders: the foot shut behind a fence gate, and the audit that says it was done right.

A villager climbs a ladder by just walking into one, but its path search never uses ladders and takes drops of 3 at
most, so from the top of a ladder that starts on the ground it has no way back: after 1,200 ticks it gives up its bed
AND its workstation (docs/LESSONS.md, "A villager gets by physics to places its path search cannot leave"). The loft
is content for the player, so the fix is not to remove it but to keep the villager out of it: a closed fence gate in
every cell from which a villager could walk into the ladder. Villagers never open a fence gate; players do, and the
walk audit (`lint.walk`, the player's model) goes through one, so the player loses nothing. This is what the medium
structures' windmill and watchtower already do (`mediums/_common.ladder_closet`, measured on a server: a villager left
inside stayed inside 12 times in 12).

`shut(t, th)` places the gates and records them on the template; `issues(t)` is the audit, and the build fails on any
of its four findings:
  1. nothing stranded: no cell a villager reaches by climbing from the ground that its search cannot walk back from;
  2. the player keeps every cell it could reach from the piece's entrance before the gates were placed;
  3. the player still reaches the ladder and can get off it at the top;
  4. no cell that is NOT the ladder itself is shut away from the villager -- that is how a closet turns into a
     walled-off room (an experimental closet once walled off part of 30 church templates, 162 cells each, and the
     first shape tried here did the same to 18 of them, 167 cells each).
Each of the four has a case in tests/test_ladders.py that makes it fire.
"""
import copy

MIN_RUNGS = 4          # a ladder of 4 or more: 3 is the longest drop a villager's search takes
MARGIN = 3             # flat ground modelled around the piece. Less than `_paths.MARGIN` (16, the walk to a bed):
                       # here the ground is only needed to walk round the piece and in at its doors, and a ring three
                       # blocks wide does that, at a fifth of the cells.

# The kinds of `pack.Registry.kinds` that are village pieces: those a village's jigsaw places, and so the ones a
# village's villagers walk. The medium structures keep their own closets (`mediums/_common.ladder_closet`) and the
# unique structures are audited as a whole in their own modules.
VILLAGE = ("house", "street", "tower", "gate", "decor", "plaza", "avenue", "filler", "tablon", "trace", "bed",
           "villager", "villager_nobed", "rug", "golem")


def is_village(kind):
    return kind in VILLAGE or kind.startswith("special:")


def columns(t):
    from mediums import _paths as P
    return P._ladder_columns(t)


def level(t):
    """The height, in the piece, of the feet of a villager on the ground outside it. A jigsaw joins two pieces side by
    side at the same height, and a village's pieces are joined at the height of their walkers' feet, one above the
    ground, so it is the y of the jigsaw that joins the piece to its parent: its entrance, or, for a piece without one
    (a street, a terminator), its lowest horizontal jigsaw; 0 for a piece with neither (a bed, a decor: placed inside
    another piece). A house is joined at y = 0, a well or a pond at y = 1: its layer 0 is at the ground's height."""
    hz = [j for j in t.jigsaws if not j["orientation"].startswith(("up", "down"))]
    ent = [j["pos"][1] for j in hz if j["name"] == "heraldia:entrance"]
    return min(ent or [j["pos"][1] for j in hz] or [0])


def _ground(t):
    from mediums import _paths as P
    return P.Ground(t, margin=MARGIN, base=level(t))


def ground_walk(t, g=None):
    """The cells a villager reaches on foot from the flat ground modelled around the piece (its outer ring in)."""
    g = g or _ground(t)
    x0, z0, x1, z1 = g.box
    y = g.base
    starts = [(x, y, z) for x in range(x0, x1) for z in (z0, z1 - 1) if g.floor(x, y, z) is not None]
    starts += [(x, y, z) for z in range(z0, z1) for x in (x0, x1 - 1) if g.floor(x, y, z) is not None]
    walk, todo = set(starts), list(starts)
    while todo:
        for c in g.neighbors(todo.pop()):
            if c not in walk:
                walk.add(c)
                todo.append(c)
    return walk


def entries(t, walk=None, g=None):
    """[(ladder, [rungs])]: for each ladder column of 4 rungs or more, the rungs a villager could walk into from the
    ground (it climbs by just walking into one, at the height of its own feet). Normally only the lowest one: higher
    up, the cells beside the rungs are wall or upper floor."""
    g = g or _ground(t)
    walk = walk if walk is not None else ground_walk(t, g)
    out = []
    for x, z, y0, y1 in columns(t):
        if y1 - y0 + 1 < MIN_RUNGS:
            continue
        rungs = [(x, y, z) for y in range(y0, y1 + 1)
                 if any((x + dx, y, z + dz) in walk and g.floor(x + dx, y, z + dz) is not None
                        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        if rungs:
            out.append(((x, z, y0, y1), rungs))
    return out


FACING = {(0, -1): "north", (0, 1): "south", (1, 0): "east", (-1, 0): "west"}


ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _gate(th, facing):
    return f"{th['gate']}[facing={facing},in_wall=false,open=false,powered=false]"


def _undo(t, cells):
    for c, was in cells.items():
        if was is None:
            t.blocks.pop(c, None)
        else:
            t.blocks[c] = was


def _beside(t, th, lad, rungs, g, walk, player):
    """The closet of the medium structures: a gate in each cell a villager would walk into the ladder from. The
    player then walks in and climbs without jumping. Returns the cells, or None when this shape would shut the
    villager out of a cell that is not the ladder (the ladder stands in a passage: that is how the crude closet
    walled off the nave of 18 church templates) or take a cell from the player."""
    x, z, _, _ = lad
    cells = {}
    for rx, ry, rz in rungs:
        for dx, dz in ORTH:
            c = (rx + dx, ry, rz + dz)
            if c not in cells and c in walk and g.floor(*c) is not None:
                cells[c] = t.blocks.get(c)
    if not cells or any(c in {tuple(j["pos"]) for j in t.jigsaws} for c in cells):
        return None
    for c in cells:
        t.set(c[0], c[1], c[2], _gate(th, FACING[(c[0] - x, c[2] - z)]))
    rung_cells = {(lx, ly, lz) for lx, lz, y0, y1 in columns(t) for ly in range(y0, y1 + 2)}
    if (walk - ground_walk(t) - set(cells) - rung_cells) or (player - _player_walk(t)):
        _undo(t, cells)
        return None
    return cells


def _in_the_rungs(t, th, rungs):
    """The ladder's own foot becomes the gate: it takes no floor cell and leaves every passage clear, but the lowest
    rung is then at the player's head and it has to jump once to catch the ladder (measured with Carpet's fake
    player). Used only where `_beside` does not fit."""
    cells = {}
    for x, y, z in rungs:
        st = t.get(x, y, z) or ""
        facing = st.split("facing=")[1].split(",")[0].split("]")[0] if "facing=" in st else "north"
        cells[(x, y, z)] = t.blocks.get((x, y, z))
        t.set(x, y, z, _gate(th, facing))
    return cells


def shut(t, th):
    """Shut every ladder of the piece a villager could climb from the ground, behind a closed fence gate: villagers
    never open one, players do (`lint.passable`, and measured on a server: 12 of 12 gates opened by a fake player).
    The shape is chosen per ladder, by measuring: the gate goes in the cells BESIDE the ladder, so that the player
    climbs without jumping, unless that would shut the villager out of a passage or cost the player a cell, in which
    case the ladder's own foot becomes the gate. Recorded on `t.closets` for the audit; returns how many gates were
    placed."""
    n = 0
    while True:
        g = _ground(t)
        walk = ground_walk(t, g)
        todo = entries(t, walk, g)
        if not todo:
            return n
        lad, rungs = todo[0]
        player = _player_walk(t)
        cells, shape = _beside(t, th, lad, rungs, g, walk, player), "beside"
        if cells is None:
            cells, shape = _in_the_rungs(t, th, rungs), "rung"
        if not cells:
            return n                       # nothing could be placed: the audit fails on the ladder instead
        t.closets.append({"ladder": lad, "cells": cells, "shape": shape})
        n += len(cells)


def _without_closets(t):
    """The piece as it was before `shut`: a copy with the closets' gates undone."""
    u = copy.copy(t)
    u.blocks = dict(t.blocks)
    u.closets = []
    for c in t.closets:
        for p, was in c["cells"].items():
            if was is None:
                u.blocks.pop(p, None)
            else:
                u.blocks[p] = was
    return u


def stranded(t, walk=None, g=None):
    """The cells a villager gets to by walking from the ground and climbing the ladders it reaches, from which its
    search finds no way back to the ground."""
    g = g or _ground(t)
    walk = walk if walk is not None else ground_walk(t, g)
    landing = []
    for x, z, y0, y1 in columns(t):
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


def _player_walk(t):
    """The cells a player entering through the piece's access can stand in (`lint.walk`: it opens fence gates and
    climbs ladders). The piece itself, never a `lint_view`: no village piece has one, and the before/after comparison
    of `issues` has to walk the same thing on both sides."""
    import lint
    return set(lint.walk(t))


def issues(t):
    """[(message, position)] for the design audit: the four findings of this module's docstring. One position per
    finding and per template (the audit counts templates, not cells: `lint.summarize`)."""
    out = []
    if not columns(t):
        return out
    g = _ground(t)
    walk = ground_walk(t, g)
    # 1. nobody stranded
    stuck = stranded(t, walk, g)
    if stuck:
        out.append(("escalera de mano que deja al aldeano varado", min(stuck)))
    if not t.closets:
        return out
    before = _without_closets(t)
    pw = _player_walk(t)
    # 2. the player keeps every cell it could reach from the entrance
    lost = _player_walk(before) - pw
    if lost:
        out.append(("el armario de la escalera quita al jugador una celda", min(lost)))
    # 3. the player reaches the ladder and can get off it at the top
    for c in t.closets:
        x, z, y0, y1 = c["ladder"]
        if not any((x, y, z) in pw for y in range(y0, y1 + 2)):
            out.append(("el jugador no puede subir la escalera del armario", (x, y0, z)))
            continue
        if (x, y1 + 1, z) not in pw and not any((x + dx, y1 + 1, z + dz) in pw
                                                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            out.append(("el armario deja la escalera sin salida arriba", (x, y1, z)))
    # 4. the gates took nothing else away from the villager either (the walled-off room of the crude closet)
    gates = {p for c in t.closets for p in c["cells"]}
    ladders = {(x, y, z) for x, z, y0, y1 in columns(t) for y in range(y0, y1 + 2)}
    gone = ground_walk(before) - walk - gates - ladders
    if gone:
        out.append(("el armario de la escalera cierra al aldeano una celda que no es la escalera", min(gone)))
    return out
