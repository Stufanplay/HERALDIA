"""herald_grounds.py: the Herald's House grounds (the houses and cherry trees around the town): the door rule, the
templates (loot, fire, nothing a villager claims), and, over many seeds and arena sites, that no road (the gates' roads,
their lamps and huts, the arena road) ever reaches a house's plot or a cherry tree."""
import random

import doors
import herald_grounds as g
import herald_house as h
import options
import spawn_roads as s
from tests.test_spawn_roads import _seeds, _world


def test_the_generator_keeps_its_rules():
    assert g.errors() == []


def test_several_different_houses_each_with_loot_and_a_door():
    ts = g.templates()
    assert len(ts) >= 4
    looks = {frozenset(g._name(st) for st, _ in t.blocks.values()) for t in ts.values()}
    assert len(looks) == len(ts)                     # no two houses built of the same blocks
    for name, t in ts.items():
        assert len(doors.doors_of(t)) == 1, name
        chests = [nbt for st, nbt in t.blocks.values() if g._name(st) == "chest"]
        assert chests and all(n["LootTable"].startswith("heraldia:relleno/") for n in chests), name
        assert not t.entities, name


def test_the_door_rule_is_really_checked_on_each_template():
    """A block in front of a house's door breaks the rule (the check does not skip the door)."""
    for name, t in g.templates().items():
        x, y, z = t.door
        t.set(x, 1, z - 2, "stone_bricks")
        t.set(x, 2, z - 2, "stone_bricks")
        assert doors.template_report(t), name


def test_a_villager_magnet_or_something_that_burns_fails():
    t = g.templates()["casa_barro"]
    t.set(2, 1, 5, "white_bed[facing=south,part=foot,occupied=false]")
    assert any("claim" in e for e in g.template_errors({"x": t, **{k: v for k, v in g.templates().items() if k != "casa_barro"}}))
    t = g.templates()["casa_barro"]
    t.set(2, 1, 5, "oak_planks")
    assert any("burns" in e for e in g.template_errors({"x": t}))


def test_every_slot_is_in_the_ring_out_of_the_corridors_and_apart():
    shapes = [g.slot_shapes(sl) for sl, _ in g.all_slots()]
    assert len({sl[0] for sl, _ in g.all_slots()}) == len(g.all_slots()) and len(g.SLOTS) >= g.DEFAULT_HOUSES
    assert len({sl[1] for sl in g.SLOTS[:g.DEFAULT_HOUSES]}) == len(g.templates())   # the default ones use every design
    for sh in shapes:
        x0, z0, x1, z1 = sh["plot"]
        for x, z in ((x0, z0), (x1, z1)):
            assert 10 <= g.depth(x, z) <= g.MAX_DEPTH < g.RING
    groups = [k for _, k in g.all_slots()]
    for i, a in enumerate(shapes):
        for j in range(i + 1, len(shapes)):
            if groups[i] == groups[j]:
                continue                                 # two places of one house: never both built
            pa, pb = a["plot"], shapes[j]["plot"]
            assert max(pb[0] - pa[2], pa[0] - pb[2], pb[1] - pa[3], pa[1] - pb[3]) > 8


def _plots():
    return [g.slot_shapes(sl)["plot"] for sl, _ in g.all_slots()]


def _house_chunks(plots, ox, oz):
    """The chunks a house's plot touches (world coordinates): what herald/Outskirts.houseChunk tells the arena road."""
    return {((x + ox) >> 4, (z + oz) >> 4) for x0, z0, x1, z1 in plots for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)}


def _touches(cells, plots, margin=1):
    return any((x, z) in cells for x0, z0, x1, z1 in plots for x in range(x0 - margin, x1 + margin + 1)
               for z in range(z0 - margin, z1 + margin + 1))


def _gate_roads(seed, gates, ox, oz):
    """The columns the gates' roads may touch (their cells with the shoulders, lamps and huts), in town coordinates."""
    out = set()
    for k in s.SIDES:
        pts = s.normal_road(gates[k], k, seed)
        out |= s.cells(pts, s.WIDTH + 4)
        for lx, lz in s.lamps(pts):
            out |= {(lx + dx, lz + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
        for _, sd, along in s.slots(True):
            _, _, world = s.hut_frame(gates[k], k, sd, along)
            cs = [world(x, z) for x in (0, s.HUT_SIZE[0] - 1) for z in (0, s.HUT_SIZE[2] - 1)]
            out |= {(x, z) for x in range(min(c[0] for c in cs), max(c[0] for c in cs) + 1)
                    for z in range(min(c[1] for c in cs), max(c[1] for c in cs) + 1)}
    return {(x - ox, z - oz) for x, z in out}


def test_no_gate_road_ever_reaches_a_house_or_a_cherry_tree():
    """The gates' roads (built right after the grounds, or later with /heraldia herald roads): their columns, lamps
    and huts never touch a house's plot (and a block around it) nor come within 5 of a cherry's trunk, on any seed."""
    plots = _plots()
    r = random.Random(11)
    for seed in _seeds(300, 11):
        town, gates, arena = _world(r)
        bad = _gate_roads(seed, gates, town[0], town[1])
        assert not _touches(bad, plots), seed
        for cx, cz in g.CHERRY_SITES:
            assert not any((cx + dx, cz + dz) in bad for dx in range(-5, 6) for dz in range(-5, 6)), (seed, cx, cz)


def test_the_arena_road_goes_round_the_houses():
    """The arena road may come round the town as close as 17 blocks, so no depth is safe from it: it sees the houses'
    chunks as structures (herald/Outskirts.houseChunk in SpawnRoads.planArena) and goes round them as it goes round a
    village. A plan clear of structures never touches a house; only when every detour crosses one (the roads' own
    fallback, which then leaves those columns as they are) can it reach a house, in about 1% of worlds even with the
    most houses a world can have (one per group, here every first place)."""
    plots = [g.slot_shapes(sl)["plot"] for sl in g.SLOTS]
    r = random.Random(12)
    hits, n = 0, 0
    for seed in _seeds(600, 12):
        town, gates, arena = _world(r)
        ox, oz = town[0], town[1]
        chunks = _house_chunks(plots, ox, oz)
        side, nr, start, from_head, res = s.arena_plan(gates, town, arena, seed, lambda cx, cz: (cx, cz) in chunks)
        if res is None:
            continue
        n += 1
        cells = {(x - ox, z - oz) for x, z in s.cells(res[0], s.WIDTH + 4)}
        if res[2]:
            assert not _touches(cells, plots), seed
        elif _touches(cells, plots):
            hits += 1
    assert n > 500 and hits <= n // 100, (hits, n)


def test_the_blueprint():
    d = g.dataset()
    assert d["anillo"] == g.RING == 50
    assert d["corte"] <= 12 and d["relleno"] <= 12
    assert [c["nombre"] for c in d["casas"]] == list(g.templates())
    assert len(d["huecos"]) == len(g.all_slots()) and all(sl["casa"] in g.templates() for sl in d["huecos"])
    assert len({sl["grupo"] for sl in d["huecos"]}) == len(g.SLOTS) == g.MAX_HOUSES
    assert 4 <= d["cerezos"] <= len(d["sitios_cerezo"])


def test_the_options():
    keys = {k: (v, lo, hi) for k, v, lo, hi, *_ in options._FIXED}
    assert keys["casa_heraldo.alrededores.activado"][0] is True
    v, lo, hi = keys["casa_heraldo.alrededores.casas"]
    assert v == g.DEFAULT_HOUSES and lo == 0 and hi == g.MAX_HOUSES


def test_texts():
    l = g.lang()
    assert l["es_es"].keys() == l["en_us"].keys()
    assert all(k.startswith("heraldia.casa_heraldo.alrededores.") for k in l["es_es"])
    assert h.N == g.N


def test_no_two_houses_share_a_roof():
    """Five houses, five roofs (a gable with a porch, one with a dormer and a chimney, a hip, a terrace behind a parapet,
    a gable end to the yard): the highest block of every column, relative to the house's own walls, differs."""
    shapes = set()
    for name, t in g.templates().items():
        x0, z0, x1, z1 = t.walls
        top = {}
        for (x, y, z), (st, _) in t.blocks.items():
            if st != "minecraft:air" and x0 <= x <= x1 and z0 <= z <= z1:
                top[(x - x0, z - z0)] = max(top.get((x - x0, z - z0), 0), y)
        shapes.add(tuple(top.get((i, j), 0) for i in range(7) for j in range(6)))
    assert len(shapes) == len(g.templates())
