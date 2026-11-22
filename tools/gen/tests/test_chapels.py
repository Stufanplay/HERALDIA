"""The chapel (specials.church for the twelve styles that share it): the bell is carried three ways by the land the
style stands in, each variant still has exactly one bell, and none has a ladder: a villager climbs a ladder by walking
into it and has no way to plan the way down, so a tower with a ladder from the floor is a trap for the cleric."""
import random

import pytest

import specials
from themes import THEMES

CHAPELS = [th for th in THEMES if th["church"] == "chapel"]


def name(st):
    return st.split("[")[0].replace("minecraft:", "")


def build(th, v):
    return specials.church(th, random.Random(5), f"{th['id']}/specials/church_{v}", v)


def test_twelve_styles_share_the_chapel_and_every_family_has_a_carrier():
    assert len(CHAPELS) == 12
    assert {th["family"] for th in CHAPELS} == set(specials.BELL_CARRIER)
    assert set(specials.BELL_CARRIER.values()) == {"bellcote", "frame", "stub"}


@pytest.mark.parametrize("v", (0, 1, 2))
@pytest.mark.parametrize("th", CHAPELS, ids=lambda th: th["id"])
def test_a_chapel_has_one_bell_and_no_ladder(th, v):
    t = build(th, v)
    blocks = [name(st) for st, _ in t.blocks.values()]
    assert blocks.count("bell") == 1
    assert "ladder" not in blocks
    assert not [b for b in blocks if b.endswith("scaffolding") or b == "vine"]      # nothing else to climb


@pytest.mark.parametrize("v", (0, 2))
def test_the_three_carriers_are_three_skylines(v):
    """The highest block over the nave's axis, front to back: a bellcote, a frame and a squat tower do not draw the same
    line, and two styles with the same carrier do."""
    def line(th):
        t = build(th, v)
        xs = sorted({x for (x, y, z) in t.blocks})
        cx = xs[len(xs) // 2]
        top = {}
        for (x, y, z), (st, _) in t.blocks.items():
            if abs(x - cx) <= 4 and st != "minecraft:air":
                top[z] = max(top.get(z, 0), y)
        return tuple(sorted(top.items()))
    by = {}
    for th in CHAPELS:
        by.setdefault(specials.BELL_CARRIER[th["family"]], set()).add(line(th))
    lines = [frozenset(s) for s in by.values()]
    assert len(by) == 3 and all(a.isdisjoint(b) for i, a in enumerate(lines) for b in lines[i + 1:])

