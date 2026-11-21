"""Inhabitants of the medium structures (mediums/_inhabitants.py): who lives where, and the contract that makes them
settle (a bed and a workstation each, walkable without ladders, no free bed to breed)."""
import copy

import pytest

import mediums
from mediums import _inhabitants as inh
from pack import Registry

# Who lives in each variant (professions of the inhabitant villagers, and their animals): the brief's choice, kind by kind.
EXPECTED = {
    "posada": {"a": (["butcher"], ["pig", "pig"]), "b": (["butcher", "farmer"], [])},
    "pescador": {"a": (["fisherman"], []), "b": (["fisherman"], [])},
    "cazadores": {"a": (["leatherworker", "fletcher"], []), "b": (["leatherworker"], [])},
    "molino": {"a": (["farmer"], []), "b": (["farmer"], [])},
    "torre_vigia": {"a": ([], []), "b": (["fletcher"], [])},
    "ermita": {"a": (["librarian"], []), "b": (["librarian"], [])},
}


@pytest.fixture(scope="module")
def reg():
    r = Registry()
    for mid, _ in mediums.modules():
        mediums.build(r, mid)
    assert not r.warnings, r.warnings
    return r


def _living(t):
    vs = [n["VillagerData"]["profession"].split(":")[1] for *_, n in t.entities
          if inh.is_inhabitant(n) and n["id"] == "minecraft:villager"]
    animals = [n["id"].split(":")[1] for *_, n in t.entities if inh.is_inhabitant(n) and n["id"] != "minecraft:villager"]
    return sorted(vs), sorted(animals)


def test_who_lives_where(reg):
    for name, t in reg.templates.items():
        _, mid, style, variant = name.split("/")
        want = EXPECTED.get(mid, {}).get(variant, ([], []))
        assert _living(t) == (sorted(want[0]), sorted(want[1])), name


def test_hostile_and_other_dimensions_have_no_inhabitants(reg):
    """Camps, shrines, the wizard's hut (its own Java) and the Nether and End kinds keep what they had."""
    for name, t in reg.templates.items():
        mid = name.split("/")[1]
        if mid not in EXPECTED:
            assert _living(t) == ([], []), name


def test_one_to_four_per_inhabited_structure(reg):
    for name, t in reg.templates.items():
        vs, animals = _living(t)
        if vs or animals:
            assert 1 <= len(t.entities) <= mediums.MAX_ENTITIES, name
            assert len(vs) <= inh.MAX_VILLAGERS, name


def test_every_template_meets_the_contract(reg):
    for name, t in reg.templates.items():
        assert inh.issues(t) == [], name


def test_villagers_live_with_ai_and_keep_their_trades(reg):
    for name, t in reg.templates.items():
        for *_, n in t.entities:
            if inh.is_inhabitant(n) and n["id"] == "minecraft:villager":
                assert "NoAI" not in n and n["Invulnerable"] == 1 and n["PersistenceRequired"] == 1, name
                assert n["Xp"] > 0, name                       # locked profession: it keeps the template's trades
                assert n["Offers"]["Recipes"], name
                assert n["CustomName"]["translate"].startswith("heraldia.medianas."), name


def test_old_figures_are_marked_still_before(reg):
    """The traders that were still figures before carry STILL_BEFORE (still again with the option off); the new ones do not."""
    before = {("posada", "butcher"), ("pescador", "fisherman"), ("cazadores", "leatherworker"), ("molino", "farmer")}
    for name, t in reg.templates.items():
        _, mid, _, variant = name.split("/")
        for *_, n in t.entities:
            if inh.is_inhabitant(n) and n["id"] == "minecraft:villager":
                prof = n["VillagerData"]["profession"].split(":")[1]
                was = (mid, prof) in before and (variant == "a" or mid == "posada")
                assert (inh.STILL_BEFORE in n["Tags"]) == was, (name, prof)
                assert inh.SEEN not in n["Tags"], name           # only the mod sets it


def test_animals_without_name_or_anchor(reg):
    import core
    for name, t in reg.templates.items():
        for *_, n in t.entities:
            if inh.is_inhabitant(n) and n["id"] != "minecraft:villager":
                assert "CustomName" not in n and core.ANCHORED_TAG not in n["Tags"], name


def _tower(reg):
    return copy.deepcopy(reg.templates["medianas/torre_vigia/colinas/b"])


def test_bed_only_by_ladder_does_not_count(reg):
    t = _tower(reg)
    for p, (st, _) in list(t.blocks.items()):
        if "_bed" in st and p[1] == 1:
            t.blocks[p] = ("minecraft:air", None)
    errs = inh.issues(t)
    assert any("without ladders" in e for e in errs), errs      # the upstairs bed (y = 6) is only reached by the ladder


def test_missing_workstation(reg):
    t = _tower(reg)
    for p, (st, _) in list(t.blocks.items()):
        if "fletching_table" in st:
            t.blocks[p] = ("minecraft:air", None)
    assert any("fletching_table" in e for e in inh.issues(t))


def test_two_villagers_one_workstation(reg):
    t = copy.deepcopy(reg.templates["medianas/cazadores/nieve/a"])
    for p, (st, _) in list(t.blocks.items()):
        if "fletching_table" in st:
            t.blocks[p] = ("minecraft:air", None)
    assert any("fletcher" in e for e in inh.issues(t))


def test_free_bed_for_two_lets_them_breed(reg):
    t = copy.deepcopy(reg.templates["medianas/cazadores/nieve/a"])
    t.blocks[(12, 1, 9)] = ("minecraft:white_bed[facing=west,occupied=false,part=head]", None)
    t.blocks[(13, 1, 9)] = ("minecraft:white_bed[facing=west,occupied=false,part=foot]", None)
    assert any("breed" in e for e in inh.issues(t))


def test_too_many_villagers(reg):
    t = copy.deepcopy(reg.templates["medianas/posada/llanura/b"])
    x, y, z, n = t.entities[0]
    t.entities.append((x, y, z, copy.deepcopy(n)))
    assert any("maximum" in e for e in inh.issues(t))


def test_inhabitant_without_ai_or_villager_with_ai_untagged(reg):
    t = copy.deepcopy(reg.templates["medianas/molino/llanura/a"])
    (x, y, z, n) = next(e for e in t.entities if e[3]["id"] == "minecraft:villager")
    n["NoAI"] = 1
    assert any("NoAI" in e for e in inh.issues(t))
    del n["NoAI"]
    n["Tags"] = [g for g in n["Tags"] if g != inh.TAG]
    assert any("without" in e and inh.TAG in e for e in inh.issues(t))


def test_named_animal_would_be_anchored(reg):
    t = copy.deepcopy(reg.templates["medianas/posada/llanura/a"])
    pig = next(n for *_, n in t.entities if n["id"] == "minecraft:pig")
    pig["CustomName"] = {"translate": "heraldia.medianas.posada.cerdo"}
    assert any("anchor" in e for e in inh.issues(t))


def test_workstations_match_vanilla():
    """Each profession used here has its 26.3 workstation (PoiTypes)."""
    assert inh.WORKSTATION["butcher"] == ("smoker",) and inh.WORKSTATION["farmer"] == ("composter",)
    assert inh.WORKSTATION["fisherman"] == ("barrel",) and inh.WORKSTATION["fletcher"] == ("fletching_table",)
    assert "cauldron" in inh.WORKSTATION["leatherworker"] and inh.WORKSTATION["librarian"] == ("lectern",)


def test_no_bell_they_would_drift(reg):
    """The bell is their meeting point: without one, idle villagers stroll away (and in rough terrain get lost)."""
    t = copy.deepcopy(reg.templates["medianas/molino/llanura/b"])
    for p, (st, _) in list(t.blocks.items()):
        if "bell" in st:
            t.blocks[p] = ("minecraft:air", None)
    assert any("bell" in e for e in inh.issues(t))


def test_every_inhabited_template_has_a_bell_on_the_ground(reg):
    for name, t in reg.templates.items():
        if _living(t)[0]:
            bells = [st for (x, y, z), (st, _) in t.blocks.items() if "bell[" in st and y == 1 and "attachment=floor" in st]
            assert bells, name


def test_a_step_against_a_fence_is_a_trap(reg):
    """The hermitage's composter against its garden fence: the hermit hopped over into the garden and could not get out
    (villagers do not open gates). The contract finds it."""
    t = copy.deepcopy(reg.templates["medianas/ermita/oscuro/b"])
    for p, (st, _) in list(t.blocks.items()):
        if "composter" in st:
            t.blocks[p] = ("minecraft:air", None)
            t.blocks[(p[0], p[1], p[2] + 1)] = (st, None)        # back against the fence, as it was
    assert any("hops over" in e for e in inh.issues(t))


def _walled(t, door_xz, wall_xz):
    """A copy of the template with the door at door_xz (y 1 and 2) bricked up with the wall block at wall_xz."""
    import core
    w = core.Template(t.name + "#walled")
    w.blocks = dict(t.blocks)
    wall = t.blocks[(wall_xz[0], 1, wall_xz[1])]
    w.blocks[(door_xz[0], 1, door_xz[1])] = w.blocks[(door_xz[0], 2, door_xz[1])] = wall
    w.jigsaws, w.entities = t.jigsaws, t.entities
    return w


def test_no_inhabitant_is_trapped_behind_its_bedroom_wall(reg):
    """Every inhabited template passes the trap check (mediums/_paths.trap_walk), and the two templates seen failing on a
    server fail it again with their bedroom door bricked up: the inn without its back door (traps 26.1 and 36.1 blocks'
    walk from the beds; 7 villagers in 16 did not get home) and the hermitage without its cell door (31.8; 5 in 8)."""
    from mediums import _paths, hermitage, inn
    seen = 0
    for name, t in reg.templates.items():
        if name.startswith("medianas/") and any(inh.is_inhabitant(n) for *_, n in t.entities):
            seen += 1
            assert inh.trap_issues(t) == [], name
    assert seen == 28
    t = reg.templates["medianas/posada/llanura/a"]
    old = _walled(t, (inn.X1, 8), (inn.X1, 7))
    assert sorted(w for _, _, w in _paths.trap_walk(old)) == [26.1, 36.1]
    assert len(inh.trap_issues(old)) == 2 and inh.issues(old) != []
    t = reg.templates["medianas/ermita/oscuro/a"]
    old = _walled(t, (hermitage.X1 - 2, hermitage.Z1), (hermitage.X1 - 3, hermitage.Z1))
    assert [w for _, _, w in _paths.trap_walk(old)] == [31.8]
    assert len(inh.trap_issues(old)) == 1


def test_a_trap_is_where_the_search_stops_short(reg):
    """The model of the 26.3 search: a walk of 16 or more is never found (the hard limit), a shorter one is; the partial
    path of a failed search ends at the explored cell closest to the bed in a straight line."""
    import core
    from mediums import _paths
    t = core.Template("wall")
    for z in range(-6, 7):
        for y in (0, 1, 2):
            t.set(5, y, z, "stone")               # a wall at x = 5 from z -6 to 6, ground of the platform under it
    t.set(0, 0, 0, "stone")
    g = _paths.Ground(t)
    ok, end = _paths.find_path(g, (3, 0, 0), (8, 0, 0))   # 5 blocks across, some 17 round the end of the wall
    assert not ok and end == (4, 0, 0)
    ok, _ = _paths.find_path(g, (3, 0, 6), (8, 0, 6))      # near the end of the wall: a short way round
    assert ok


def test_no_inhabitant_is_stranded_up_a_ladder(reg):
    """No inhabited template lets a villager climb a ladder to where its search has no way back (mediums/_paths.stranded),
    and the three seen or found stranding fail it again as they were: the hunters' lookout a block higher (a drop of 4:
    both inhabitants stranded on it in CI; 6 of 12 left on top got home on a server, 12 of 12 with it lower), and the
    windmill's and the watchtower's ladders with their foot open."""
    import core
    from mediums import _paths
    seen = 0
    for name, t in reg.templates.items():
        if name.startswith("medianas/") and any(inh.is_inhabitant(n) for *_, n in t.entities):
            seen += 1
            assert inh.stranded_issues(t) == [], name
    assert seen == 28

    def edited(t, changes):
        w = core.Template(t.name + "#old")
        w.blocks = dict(t.blocks)
        for p, st in changes.items():
            if st is None:
                w.blocks.pop(p, None)
            else:
                w.blocks[p] = (st, None)
        w.jigsaws, w.entities = t.jigsaws, t.entities
        return w

    t = reg.templates["medianas/cazadores/sabana/a"]
    # the old lookout: everything from y = 1 up one block higher (x 10..12, z 1..4), the ladder to y = 4
    old = {}
    for (x, y, z), (st, _) in t.blocks.items():
        if 10 <= x <= 12 and 1 <= z <= 4 and y >= 1:
            old[(x, y, z)] = None
    for (x, y, z), (st, _) in t.blocks.items():
        if 10 <= x <= 12 and 1 <= z <= 4 and y >= 1:
            old[(x, y + 1, z)] = st
    for (x, z) in ((10, 1), (12, 1), (10, 3), (12, 3), (11, 4)):
        old[(x, 1, z)] = t.blocks[(x, 1, z)][0]
    old[(11, 1, 3)] = t.blocks[(11, 1, 3)][0]
    lookout = edited(t, old)
    assert _paths.stranded(lookout) and inh.issues(lookout) != []
    for name, gate, posts in (("medianas/molino/llanura/b", (4, 1, 9), [(5, 1, 10), (5, 2, 10)]),
                              ("medianas/torre_vigia/taiga/b", (7, 1, 9), [(6, 1, 10), (6, 2, 10), (8, 1, 10), (8, 2, 10)])):
        t = reg.templates[name]
        assert t.blocks[gate][0].split("[")[0].endswith("_fence_gate"), name
        opened = edited(t, {p: None for p in [gate] + posts})
        assert _paths.stranded(opened), name
