"""A villager a village piece places behind a shut fence gate never walks out (enclosures.py): the audit finds it, an
open gate or a door clears it, and the farms and the cloister library of every style now leave theirs open while
their pens keep theirs shut."""
import random

import enclosures
import lint
import specials
from core import Template
from themes import THEMES

MSG = "a villager is placed where its only way out is a shut fence gate"


def yard(way="gate_shut"):
    """A 7 x 7 yard walled with fence on flat ground, a villager placed in the middle, and in the middle of the north
    side `way`: a shut gate, an open one, a wooden door, or a gate with a gap in the fence beside it."""
    t = Template("t/specials/yard")
    for x in range(7):
        for z in range(7):
            t.set(x, 0, z, "grass_block")
            if x in (0, 6) or z in (0, 6):
                t.set(x, 1, z, "oak_fence")
    if way == "door":
        t.set(3, 1, 0, "oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]")
        t.set(3, 2, 0, "oak_door[facing=north,half=upper,hinge=left,open=false,powered=false]")
    else:
        t.set(3, 1, 0, f"oak_fence_gate[facing=north,in_wall=false,open={'true' if way == 'gate_open' else 'false'},"
                       f"powered=false]")
    if way == "gap":
        t.set(5, 1, 6, "air")
    t.jigsaw(3, 0, 3, "up_south", "heraldia:slot", "heraldia:bottom", "heraldia:villagers/plains/nobed_farmer",
             final_state="grass_block")
    return t


def test_a_villager_behind_a_shut_gate_is_found():
    t = yard()
    assert enclosures.shut_in(t) == [(3, 1, 3)]
    assert [m for m, _ in enclosures.issues(t)] == [MSG]
    assert MSG in [m for m, _ in lint.template_issues(t, "special:farm")]


def test_an_open_gate_a_door_or_another_way_out_clears_it():
    for way in ("gate_open", "door", "gap"):
        assert enclosures.issues(yard(way)) == [], way


def test_only_villagers_count():
    """A pen with animals and nobody placed in it keeps its gate shut: the audit leaves it alone."""
    t = yard()
    t.jigsaws.clear()
    t.set(3, 0, 3, "grass_block")
    assert enclosures.issues(t) == []


def _gates(t):
    return {p: st for p, (st, _) in t.blocks.items() if st.split("[")[0].endswith("_fence_gate")}


def test_farms_and_the_cloister_library_let_their_villager_out():
    n = 0
    for i, th in enumerate(THEMES):
        for v in (0, 1, 2):
            t = specials.farm(th, random.Random(i), f"t/specials/farm_{v}", v)
            gates = _gates(t)
            outer = {p: st for p, st in gates.items() if p[2] in (1, 19)}
            pen = {p: st for p, st in gates.items() if p not in outer}
            assert len(outer) == 2 and all("open=true" in st for st in outer.values()), (th["id"], v, outer)
            assert len(pen) == 1 and all("open=false" in st for st in pen.values()), (th["id"], v, pen)
            assert enclosures.issues(t) == [], (th["id"], v)
            n += 1
        t = specials.library(th, random.Random(i), "t/specials/library_c", 2)
        assert [st for st in _gates(t).values()] and all("open=true" in st for st in _gates(t).values()), th["id"]
        assert enclosures.issues(t) == [], th["id"]
    assert n >= 100


def plateau():
    """A piece joined at y = 1 (its layer 0 a foundation at the ground's height): a villager on a block three
    high, fenced on its south side, where a shut gate opens onto steps down. Its other sides are a drop of 3 to the
    street, which the search takes."""
    t = Template("t/specials/plateau")
    for x in range(5):
        for z in range(8):
            t.set(x, 0, z, "stone")
    for x in range(5):
        for z in range(5):
            for y in (1, 2, 3):
                t.set(x, y, z, "stone")
        t.set(x, 4, 4, "oak_fence")
    t.set(2, 4, 4, "oak_fence_gate[facing=south,in_wall=false,open=false,powered=false]")
    for y in (1, 2):
        t.set(2, y, 5, "stone")
    t.set(2, 1, 6, "stone")
    t.jigsaw(1, 3, 1, "up_south", "heraldia:slot", "heraldia:bottom", "heraldia:villagers/plains/nobed_farmer",
             final_state="stone")
    t.jigsaw(0, 1, 7, "west_up", "heraldia:entrance", "heraldia:street", "heraldia:empty")
    return t


def test_the_street_is_at_the_height_of_the_jigsaw_that_joins_the_piece():
    """#86: with the ground modelled at y = -1, a block below the piece's foundation, the plateau's sides were a drop
    of 4, which the search never takes, and the gate looked like the only way down."""
    t = plateau()
    assert enclosures.issues(t) == []
    for x in range(5):
        for z in range(4):
            if x in (0, 4) or z == 0:
                t.set(x, 4, z, "oak_fence")
    assert [m for m, _ in enclosures.issues(t)] == [MSG], "fenced all round, the gate is the only way out again"
