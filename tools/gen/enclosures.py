"""Village pieces: a villager placed somewhere whose only way out is a shut fence gate.

Villagers open doors but never a fence gate, so a villager the piece places (a jigsaw into a `villagers/` pool: the
villager stands on the cell above it) inside a fence or a wall whose only opening is a closed gate never walks out:
not to a bed in a house of the village, not to the bell. Found in the cloister library (`specials.library_variant`:
its court is the only way in and the librarian is placed in the hall behind it) and in every farm (the farmer is
placed in the barn, inside the outer fence and its two gates). Both now leave those gates open, as the village gardens
do since #148; pens keep theirs shut, nobody is placed in one.

The village_routes figure `shut in` cannot see this when the place is large: it counts a villager as shut in only if
its search cannot get 12 blocks away, and a farm is 21 x 19. So the build checks it here instead, on the template: from
each villager's cell, the search's walk (`mediums/_paths`: no ladders, closed gates as fences) with the gates as they
are must reach the flat ground around the piece whenever it does with every gate open. `issues(t)` is the audit
(`lint.template_issues`, village pieces); tests/test_enclosures.py makes it fire.
"""
MARGIN = 3              # flat ground around the piece, as in ladders.py: enough to walk round it and in at its doors


def _name(st):
    return st.split("[")[0].replace("minecraft:", "") if st else ""


def opened(t):
    """A copy of the piece with every fence gate open."""
    from core import Template, with_props
    u = Template(t.name + "#open")
    u.blocks = {p: (with_props(st, open=True) if _name(st).endswith("_fence_gate") else st, nbt)
                for p, (st, nbt) in t.blocks.items()}
    u.jigsaws, u.entities, u.min_size = t.jigsaws, t.entities, t.min_size
    return u


def spawns(t, g):
    """The cells the piece's villagers stand in: above each jigsaw into a `villagers/` pool (or at it, or two above,
    whichever has a floor)."""
    out = []
    for j in t.jigsaws:
        if ":villagers/" not in j["pool"]:
            continue
        x, y, z = j["pos"]
        for c in ((x, y + 1, z), (x, y, z), (x, y + 2, z)):
            if g.floor(*c) is not None:
                out.append(c)
                break
    return out


def gets_out(g, start):
    """Does the search's walk from `start` reach the edge of the flat ground modelled around the piece?"""
    x0, z0, x1, z1 = g.box
    seen, todo = {start}, [start]
    while todo:
        x, y, z = todo.pop()
        if x in (x0, x1 - 1) or z in (z0, z1 - 1):
            return True
        for m in g.neighbors((x, y, z)):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return False


def shut_in(t):
    """[cell]: the villagers' cells from which the search gets out only with the gates open."""
    from mediums import _paths as P
    if not any(":villagers/" in j["pool"] for j in t.jigsaws):
        return []
    if not any(_name(st).endswith("_fence_gate") and "open=true" not in st for st, _ in t.blocks.values()):
        return []
    g = P.Ground(t, margin=MARGIN)
    out = [c for c in spawns(t, g) if not gets_out(g, c)]
    if not out:
        return []
    go = P.Ground(opened(t), margin=MARGIN)
    return [c for c in out if gets_out(go, c)]


def issues(t):
    """[(message, position)] for the design audit: one per template (the audit counts templates)."""
    cells = shut_in(t)
    return [("a villager is placed where its only way out is a shut fence gate", min(cells))] if cells else []
