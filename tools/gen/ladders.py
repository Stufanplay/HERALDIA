"""Village ladders: the foot shut behind a fence gate, and the audit that says it was done right.

A villager climbs a ladder by just walking into one, but its path search never uses ladders and takes drops of 3 at
most, so from the top of a ladder that starts on the ground it has no way back: after 1,200 ticks it gives up its bed
AND its workstation (docs/LESSONS.md, "A villager gets by physics to places its path search cannot leave"). The loft
is content for the player, so the fix is not to remove it but to keep the villager out of it: a closed fence gate in
every cell from which a villager could walk into the ladder. Villagers never open a fence gate; players do, and the
walk audit (`lint.walk`, the player's model) goes through one, so the player loses nothing. This is what the medium
structures' windmill and watchtower already do (`mediums/_common.ladder_closet`, measured on a server: a villager left
inside stayed inside 12 times in 12).

`shut(t, th)` places the gates and records them on the template; `issues(t)` is the audit, three checks:
  1. nothing stranded: no cell a villager reaches by climbing from the ground that its search cannot walk back from;
  2. the player keeps every cell it could reach from the piece's entrance before the gates were placed;
  3. the player still reaches the ladder and can climb it.
It also checks that the gates took no walkable cell away from the VILLAGER either, apart from the ladder itself: that
is how a closet turns into a walled-off room (an experimental closet once walled off part of 30 church templates).
"""
import copy

MIN_RUNGS = 4          # a ladder of 4 or more: 3 is the longest drop a villager's search takes

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


def _ground(t):
    from mediums import _paths as P
    return P.Ground(t)


def ground_walk(t, g=None):
    """The cells a villager reaches on foot from the flat ground modelled around the piece (`_paths.MARGIN`)."""
    from mediums import _paths as P
    g = g or _ground(t)
    sx, _, sz = t.size()
    m = P.MARGIN
    starts = [(x, 0, z) for x in range(-m, sx + m) for z in (-m, sz + m - 1) if g.floor(x, 0, z) is not None]
    starts += [(x, 0, z) for z in range(-m, sz + m) for x in (-m, sx + m - 1) if g.floor(x, 0, z) is not None]
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


def shut(t, th):
    """Shut every ladder of the piece a villager could climb from the ground: the rung it would walk into becomes a
    CLOSED FENCE GATE in the ladder's own cell. The villager cannot pass it (and cannot stand on the rung above one
    either, `_paths.Ground._stand`); the player opens it, stands in it and climbs from the rung above, which is at its
    head. The gate takes no floor cell from anyone and leaves every passage clear -- gating the cells BESIDE the
    ladder instead walls off the room when the ladder stands in a corridor. Recorded on `t.closets` for the audit.
    Returns how many gates were placed."""
    g = _ground(t)
    walk = ground_walk(t, g)
    n = 0
    for lad, rungs in entries(t, walk, g):
        placed = {}
        for x, y, z in rungs:
            st = t.get(x, y, z) or ""
            facing = st.split("facing=")[1].split(",")[0].split("]")[0] if "facing=" in st else "north"
            placed[(x, y, z)] = t.blocks.get((x, y, z))
            t.set(x, y, z, f"{th['gate']}[facing={facing},in_wall=false,open=false,powered=false]")
            n += 1
        if placed:
            t.closets.append({"ladder": lad, "cells": placed})
    return n


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
    """[(message, position)] for the design audit: the three checks of this module's docstring."""
    out = []
    if not columns(t):
        return out
    g = _ground(t)
    walk = ground_walk(t, g)
    # 1. nobody stranded
    for c in sorted(stranded(t, walk, g)):
        out.append(("escalera de mano que deja al aldeano varado", c))
        break                         # one per template: the audit counts templates, not cells
    if not t.closets:
        return out
    before = _without_closets(t)
    # 2. the player keeps every cell it could reach from the entrance
    lost = _player_walk(before) - _player_walk(t)
    for c in sorted(lost):
        out.append(("el armario de la escalera quita al jugador una celda", c))
        break
    # 3. the player reaches the ladder and can climb it
    pw = _player_walk(t)
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
    for c in sorted(gone):
        out.append(("el armario de la escalera cierra al aldeano una celda que no es la escalera", c))
        break
    return out
