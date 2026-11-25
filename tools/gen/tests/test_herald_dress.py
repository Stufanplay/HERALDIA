"""The Herald's House, dressed (herald_dress.py): relief, texture and a skyline over the plain build, and nothing else.
The dressed template has the same entities, block entities and light sources as the plain one, the wall walk stays
open from tower to tower (two lanes, three blocks of headroom), the mural towers stand two to a side clear of every
building and every door, and each roof gets its eaves, its ridge and (the long gables) its dormers."""
import collections

import pytest

import herald_dress as d
import herald_house as h

LIGHTS = ("lantern", "torch", "campfire", "candle", "glowstone", "lamp", "froglight", "shroomlight")


@pytest.fixture(scope="module")
def plain():
    return h.construct(dressed=False)


@pytest.fixture(scope="module")
def t():
    return h.construct()


def names(t, keys):
    return collections.Counter(h._name(st) for st, _ in t.blocks.values() if any(k in st for k in keys))


def test_only_blocks_are_added(t, plain):
    assert len(t.entities) == len(plain.entities)
    assert sorted(p for p, v in t.blocks.items() if v[1]) == sorted(p for p, v in plain.blocks.items() if v[1])
    assert names(t, LIGHTS) == names(plain, LIGHTS)
    assert t.size() == plain.size()


def test_the_detail_is_modest_in_blocks(t, plain):
    solid = lambda tt: sum(1 for st, _ in tt.blocks.values() if st != "minecraft:air")
    assert solid(plain) < solid(t) <= solid(plain) * 1.03


def test_nothing_that_was_kept_free_is_filled(t, plain):
    """What players and villagers walk on and through at ground level stays as it was, but for the towers' feet and the
    wall's buttresses (on grass the plain town leaves empty). The planting (trees, hedges, pots) has its own tests
    below: it stands on lawn away from every way, and the town's own rules (walks, doors, fire) still hold with it."""
    planted = t.trees | {(x, h.FLOOR + 1, z) for x, z in t.pots}
    filled = [p for p, (st, _) in t.blocks.items() if p[1] in (h.FLOOR + 1, h.FLOOR + 2) and st != "minecraft:air"
              and plain.blocks[p][0] == "minecraft:air" and p not in planted]
    assert filled
    for x, y, z in filled:
        assert h._name(plain.get(x, h.FLOOR, z)) == "grass_block", (x, y, z)
        assert min(x, z, h.N - 1 - x, h.SOUTH + h.WALL_T - 1 - z) <= d.TOWER_D, (x, y, z)


def test_two_mural_towers_a_side_clear_of_buildings_and_doors(t):
    assert collections.Counter(side for side, _ in t.mural_towers) == {"north": 2, "south": 2, "west": 2, "east": 2}
    sides = d._sides()
    for side, i0 in t.mural_towers:
        at, (dx, dz), _ = sides[side]
        foot = [(at(i0 + j)[0] + dx * k, at(i0 + j)[1] + dz * k) for j in range(d.TOWER_W) for k in range(d.TOWER_D)]
        for b in t.blds:
            if b.name.startswith("torre_") and b.name != "torre_reloj":
                continue
            assert all(not (b.x0 - h.GAP <= x <= b.x1 + h.GAP and b.z0 - h.GAP <= z <= b.z1 + h.GAP) for x, z in foot), (side, i0, b.name)
            for dside, x, y, z in b.doors():
                ox, oz = h.OPEN_DIR[dside]
                front = {(x + ox * k + w * abs(oz), z + oz * k + w * abs(ox)) for k in range(1, h.FACE_CLEAR + 1) for w in (-1, 0, 1)}
                assert not front & set(foot), (side, i0, b.name)


def test_the_wall_walk_stays_open(t):
    """Both lanes of the walk, feet to three blocks up, all along every side between the corner towers and the gates:
    the golems that keep the night watch walk it, through the mural towers too."""
    top = h.WALL_TOP
    for side, (at, (dx, dz), length) in d._sides().items():
        for i in range(length):
            if d._blocked(t, side, i):
                continue
            ox, oz = at(i)
            for k in (1, 2):
                x, z = ox + dx * k, oz + dz * k
                assert lint_solid(t.get(x, top, z)), (side, i, k)
                for y in range(top + 1, top + 4):
                    assert t.is_free(x, y, z), (side, i, k, y, t.get(x, y, z))


def lint_solid(st):
    import lint
    return lint.top_height(st) == 1.0


def test_nobody_falls_off_the_battlements(t):
    """Outside, over the walk's floor, every cell is a merlon, a crenel's low wall or a tower's breast: no gap."""
    top = h.WALL_TOP
    for side, (at, _, length) in d._sides().items():
        for i in range(length):
            if not d._blocked(t, side, i):
                assert not t.is_free(*at(i)[:1], top + 1, at(i)[1]), (side, i)


def test_every_roof_gets_eaves_and_a_ridge(t, plain):
    changed = collections.Counter()
    for p, (st, _) in t.blocks.items():
        if plain.blocks[p][0] != st and p[1] > h.FLOOR + 4:
            for b in t.blds:
                if b.x0 - 2 <= p[0] <= b.x1 + 2 and b.z0 - 2 <= p[2] <= b.z1 + 2:
                    changed[b.name] += 1
    for b in t.blds:
        if not b.name.startswith(d.SKIP_ROOFS):
            assert changed[b.name] >= 20, (b.name, changed[b.name])


def test_long_gables_get_dormers(t, plain):
    inner = lambda x, z: min(x, z, h.N - 1 - x, h.SOUTH + h.WALL_T - 1 - z) >= d.TOWER_D     # not a mural tower's window
    panes = [p for p, (st, _) in t.blocks.items() if "glass_pane" in st and plain.blocks[p][0] == "minecraft:air"
             and p[1] > h.FLOOR + 5 and inner(p[0], p[2])]
    assert len(panes) >= 10, len(panes)
    for x, y, z in panes:                       # a dormer's pane stands on the roof, between two posts
        assert not t.is_free(x, y - 1, z)
        assert sum(h._name(t.get(x + dx, y, z + dz)) == h.BEAM for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))) == 2


def test_door_lanes_are_cobbled_and_still_walkable(t, plain):
    """Every cell of a door's path that the plain town lays as dirt path is a full block or a path in the dressed one,
    with the same free space over it; most of them are stone now."""
    import lint
    cells = {c for _, _, cs in plain.paths for c in cs or () if h._name(plain.get(c[0], h.FLOOR, c[1])) == "dirt_path"
             and not plain.street.get(c)}
    assert len(cells) > 100
    stone = 0
    for x, z in cells:
        st = t.get(x, h.FLOOR, z)
        assert lint.top_height(st) in (1.0, 0.9375) or h._name(st) == "dirt_path", (x, z, st)
        assert t.is_free(x, h.FLOOR + 1, z) and t.is_free(x, h.FLOOR + 2, z), (x, z)
        stone += h._name(st) != "dirt_path"
    assert stone > 0.7 * len(cells)


def test_real_trees_stand_on_the_lawns_and_the_town_does_not_burn(t, plain):
    trunks = {(x, z) for (x, y, z) in t.trees if h._name(t.get(x, y, z)).endswith("_log")}
    assert len(trunks) >= 20
    for x, z in trunks:
        assert h._name(plain.get(x, h.FLOOR, z)) == "grass_block" and h._name(t.get(x, h.FLOOR, z)) == "rooted_dirt"
        assert all(max(abs(x - a), abs(z - b)) >= d.TREE_APART for a, b in trunks if (a, b) != (x, z))
        # bare lawn round the trunk in the plain town: no path, no door's way out, no building under the crown
        assert all(h._name(plain.get(x + a, h.FLOOR, z + b)) == "grass_block" and plain.is_free(x + a, h.FLOOR + 1, z + b)
                   for a in range(-2, 3) for b in range(-2, 3)), (x, z)
    assert h.fire_errors(t) == []


def test_the_fire_rule_sees_a_tree_beside_something_that_burns():
    """The check that lets trees in can say no: a carpet under a crown is reached by a fire in the tree."""
    tt = h.construct()
    x, y, z = next(p for p in sorted(tt.trees) if h._name(tt.get(*p)).endswith("_leaves") and p[1] > h.FLOOR + 3)
    tt.set(x, y + 1, z, "red_carpet") if tt.is_free(x, y + 1, z) else tt.set(x, y, z, "red_carpet")
    assert any("carpet" in e for e in h.fire_errors(tt))


def test_wood_and_leaves_only_where_the_planting_put_them(t):
    tt = h.construct()
    tt.set(60, h.FLOOR + 1, 60, "oak_log[axis=y]")
    assert any("oak_log burns" in e for e in h.errors(tt))
    assert not any("burns" in e for e in h.errors(t))


def test_hedges_and_pots_keep_off_the_ways(t, plain):
    assert len(t.hedges) >= 100 and len(t.pots) >= 20
    ways = {c for _, start, cells in t.paths for c in [start] + list(cells or ())}
    for x, z in list(t.hedges) + list(t.pots):
        assert h._name(plain.get(x, h.FLOOR, z)) == "grass_block" and plain.is_free(x, h.FLOOR + 1, z)
        assert all(max(abs(x - a), abs(z - b)) > 2 for a, b in ways), (x, z)
    assert all(h._name(t.get(x, h.FLOOR + 1, z)).endswith("_leaves") for x, z in t.hedges)
    assert all(h._name(t.get(x, h.FLOOR + 1, z)).startswith("potted_") for x, z in t.pots)


def _reach(tt):
    """Where a walker gets to from the spawn point (a step up of one block, a drop of at most three, two free blocks
    to stand in; leaves count as solid ground), and the cells among them with no way back."""
    import lint
    from collections import deque
    B = tt.blocks
    free = lambda p: p not in B or lint.passable(B[p][0])
    stand = {(x, y + 1, z) for (x, y, z), (st, _) in B.items() if not lint.passable(st)
             and free((x, y + 1, z)) and free((x, y + 2, z))}
    step = {}
    for (x, y, z) in stand:
        out = []
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in (1, 0, -1, -2, -3):
                q = (x + dx, y + dy, z + dz)
                if q in stand and (dy != 1 or free((x, y + 2, z))) \
                        and all(free((x + dx, y + k, z + dz)) for k in range(dy + 2, 2)):
                    out.append(q)
                    break
        step[(x, y, z)] = out
    start = tuple(h.SPAWN)
    there, todo = {start}, deque([start])
    while todo:
        for n in step[todo.popleft()]:
            if n not in there:
                there.add(n)
                todo.append(n)
    back = {}
    for p in there:
        for n in step[p]:
            back.setdefault(n, []).append(p)
    home, todo = {start}, deque([start])
    while todo:
        for n in back.get(todo.popleft(), ()):
            if n not in home:
                home.add(n)
                todo.append(n)
    return there, there - home


def test_the_planting_is_no_way_up_and_no_trap(t, monkeypatch):
    """A hedge is a step of one block: nothing above a hedge's top becomes reachable by it, and nowhere a walker gets
    to is without a way back (a villager that climbs to where its path search cannot bring it down loses its bed).
    Compared with the same dressed town with nothing planted."""
    there, stuck = _reach(t)
    monkeypatch.setattr(d, "trees", lambda tt: [])
    monkeypatch.setattr(d, "hedges", lambda tt, blds: ([], []))
    before, _ = _reach(h.construct())
    assert not stuck, sorted(stuck)[:5]
    assert not [p for p in there - before if p[1] > h.FLOOR + 2]
