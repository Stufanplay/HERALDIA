"""Village ladders (ladders.py): a loft reached only by a ladder strands a villager, the closed fence gate in the
ladder's own foot keeps it out without taking a cell from anyone, and the audit fails when a closet is put wrong.

The three checks the audit has to make, each with a case that fails it on purpose:
  1. nobody stranded                      -> the loft before the gate;
  2. the player keeps every cell           -> a closet with a post in the room;
  3. the player reaches the ladder and up  -> a closet that walls the ladder in;
and a fourth, the trap the crude closet of the ladders work fell into: gating the cells BESIDE the ladder walls off
the room when the ladder stands in a passage.
"""
import pytest

import ladders
import lint
from core import Template
from pack import Registry, build_theme
from themes import THEMES

GATE = "oak_fence_gate"
TH = {"gate": GATE}


def room(w=5, d=5, corridor=False, rungs=4, far=False):
    """A room of w x d with a loft at y = 4 and a ladder in the corner from the floor (feet y = 1) to the loft.
    `corridor`: the room is 1 cell wide, so the ladder stands in the only passage from the door to the back."""
    t = Template("t/houses/toy")
    d = 9 if corridor else d
    w = 3 if corridor else w
    for x in range(w):
        for z in range(d):
            t.set(x, 0, z, "stone")
            t.set(x, 7, z, "stone")
    for y in range(1, 7):
        for x in range(w):
            for z in range(d):
                t.set(x, y, z, "stone" if x in (0, w - 1) or z in (0, d - 1) else "air")
    for x in range(1, w - 1):
        for z in range(1, d - 1):
            t.set(x, 4, z, "oak_planks")
    lx, lz = 1, (4 if corridor else (d - 2 if far else 1))
    for y in range(1, 1 + rungs):
        t.set(lx, y, lz, "ladder[facing=east]")
    dx = 1 if corridor else 2
    t.set(dx, 2, 0, "air")                       # the doorway is two blocks tall: a villager needs 1.95 of headroom
    t.jigsaw(dx, 1, 0, "north_up", "heraldia:entrance", "heraldia:street", "heraldia:empty")
    t.normalize()
    return t, (lx, lz)


def test_a_loft_up_a_ladder_strands_a_villager():
    t, (lx, lz) = room()
    stuck = ladders.stranded(t)
    assert stuck, "the loft is 4 above the floor: the search takes drops of 3 at most"
    assert all(c[1] == 5 for c in stuck), stuck
    assert [m for m, _ in ladders.issues(t)] == ["escalera de mano que deja al aldeano varado"]


def test_the_gate_goes_beside_the_ladder_when_there_is_room():
    """The shape of the medium structures: the player then walks in and climbs without jumping."""
    t, (lx, lz) = room(w=6, d=6, far=True)
    assert ladders.shut(t, TH) == 2
    assert t.closets[0]["shape"] == "beside"
    assert sorted(t.closets[0]["cells"]) == [(lx, 1, lz - 1), (lx + 1, 1, lz)]
    assert t.get(lx, 1, lz) == "minecraft:ladder[facing=east]"      # the rungs are untouched
    assert ladders.stranded(t) == set()
    assert ladders.issues(t) == []
    after = set(lint.walk(t))
    assert (lx, 5, lz) in after and (lx, 1, lz) in after            # the player reaches the ladder and the loft


def test_the_gate_falls_back_to_the_ladders_own_foot_when_it_would_shut_a_passage():
    t, (lx, lz) = room()                     # the door leads into the cell beside the ladder
    assert ladders.shut(t, TH) == 1
    assert t.closets[0]["shape"] == "rung"
    assert len(t.closets) == 1 and list(t.closets[0]["cells"]) == [(lx, 1, lz)]
    assert t.get(lx, 1, lz).startswith("minecraft:" + GATE) and "open=false" in t.get(lx, 1, lz)
    assert t.get(lx, 2, lz) == "minecraft:ladder[facing=east]"      # the rungs above are untouched
    assert ladders.stranded(t) == set()
    assert ladders.issues(t) == []


def test_the_gate_takes_no_cell_from_the_player_and_it_still_climbs():
    t, (lx, lz) = room()
    before = set(lint.walk(t))
    ladders.shut(t, TH)
    after = set(lint.walk(t))
    assert before - after == set(), "the player opens a fence gate: it loses nothing"
    assert (lx, 5, lz) in after and (lx, 1, lz) in after      # it stands in the gate and gets to the loft


def test_the_villager_keeps_every_cell_but_the_ladder():
    t, (lx, lz) = room()
    before = ladders.ground_walk(t)
    ladders.shut(t, TH)
    assert before - ladders.ground_walk(t) == {(lx, 1, lz)}


def test_a_closet_beside_the_ladder_walls_off_a_passage():
    """What the crude closet of the ladders work did: it walled off part of 30 church templates."""
    t, (lx, lz) = room(corridor=True)
    free = ladders.ground_walk(t)
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):            # gates in the cells BESIDE the ladder
        c = (lx + dx, 1, lz + dz)
        if c in free:
            t.set(c[0], c[1], c[2], f"{GATE}[facing=north,in_wall=false,open=false,powered=false]")
            t.closets.append({"ladder": (lx, lz, 1, 4), "cells": {c: ("minecraft:air", None)}})
    msgs = [m for m, _ in ladders.issues(t)]
    assert "el armario de la escalera cierra al aldeano una celda que no es la escalera" in msgs


def test_a_post_in_the_room_takes_a_cell_from_the_player():
    t, (lx, lz) = room()
    c = (lx + 1, 1, lz)
    t.closets.append({"ladder": (lx, lz, 1, 4), "cells": {c: ("minecraft:air", None),
                                                          (c[0], c[1] + 1, c[2]): ("minecraft:air", None)}})
    t.set(c[0], c[1], c[2], "oak_log[axis=y]")
    t.set(c[0], c[1] + 1, c[2], "oak_log[axis=y]")
    msgs = [m for m, _ in ladders.issues(t)]
    assert "el armario de la escalera quita al jugador una celda" in msgs


def test_a_closet_that_walls_the_ladder_in_leaves_the_player_out():
    t, (lx, lz) = room()
    cells = {}
    for dx, dz in ((1, 0), (0, 1)):
        for dy in (0, 1):
            c = (lx + dx, 1 + dy, lz + dz)
            cells[c] = t.blocks.get(c)
            t.set(c[0], c[1], c[2], "stone")
    t.closets.append({"ladder": (lx, lz, 1, 4), "cells": cells})
    msgs = [m for m, _ in ladders.issues(t)]
    assert "el jugador no puede subir la escalera del armario" in msgs


def test_a_short_ladder_is_left_alone():
    """A drop of 3 is one a villager's search takes: a ladder of 3 rungs needs no gate."""
    t, _ = room(rungs=3)
    assert ladders.entries(t) == []


SOME = ["llanuras_castellana", "oscuro_gotica", "sabana_paja"]        # a rectangular, a tall-tower and an own-shape style


@pytest.mark.parametrize("th", [t for t in THEMES if t["id"] in SOME], ids=lambda th: th["id"])
def test_every_village_ladder_of_a_style_is_shut_and_the_audit_is_clean(th):
    reg = Registry()
    build_theme(reg, th, 2026 * 100 + THEMES.index(th))
    withlad = 0
    for n, t in reg.templates.items():
        assert lint.template_issues(t, reg.kinds.get(n)) == [], n
        if ladders.entries(t):                       # nothing climbable from the ground is left open
            raise AssertionError(f"{n}: ladder a villager can still climb from the ground")
        if t.closets:
            withlad += 1
            for c in t.closets:
                for p in c["cells"]:
                    assert "fence_gate" in t.get(*p) and "open=false" in t.get(*p), (n, p)
    assert withlad >= 4, f"{th['id']}: only {withlad} pieces with a shut ladder"
