"""Village houses (houses.py): the houses of one style are not one house. Each style's twelve houses show at least
eight different skylines (the highest block of every column) and its four small ones at least two, but for the styles
whose shape is their own and is not varied yet (round huts, pagodas, the long houses); the wall's weathering only swaps a
block for its kin; a dormer stands on the roof and changes nothing under it."""
import random

import pytest

import houses
from core import Template
from pack import Registry, build_theme
from themes import THEMES

OWN_SHAPE = {"sabana_paja": 3, "cerezos_japonesa": 6, "cerezos_templo": 6, "taiga_nordica": 6}   # style: its floor


def skyline(t):
    top = {}
    for (x, y, z), (st, _) in t.blocks.items():
        if st != "minecraft:air":
            top[(x, z)] = max(top.get((x, z), 0), y)
    return tuple(sorted(top.items()))


@pytest.mark.parametrize("th", THEMES, ids=lambda th: th["id"])
def test_a_styles_houses_are_not_one_house(th):
    reg = Registry()
    build_theme(reg, th, 2026 * 100 + THEMES.index(th))
    hs = {n: t for n, t in reg.templates.items() if "/houses/" in n}
    assert len(hs) == 12
    assert len({skyline(t) for t in hs.values()}) >= OWN_SHAPE.get(th["id"], 8), th["id"]
    if th["id"] not in OWN_SHAPE:
        assert len({skyline(t) for n, t in hs.items() if "small" in n}) >= 2, th["id"]


def test_weathering_only_swaps_a_block_for_its_kin():
    t = Template("x")
    for x in range(9):
        for z in range(9):
            if x in (0, 8) or z in (0, 8):
                for y in range(1, 7):
                    t.set(x, y, z, "stone_bricks" if y > 1 else "oak_planks")
    before = dict(t.blocks)
    houses.weather(t, {}, random.Random(3), 0, 0, 8, 8, 1, 6)
    changed = {p: (before[p][0], t.blocks[p][0]) for p in before if before[p] != t.blocks[p]}
    assert 10 < len(changed) < len(before) // 2
    for was, now in changed.values():
        assert was == "minecraft:stone_bricks" and now in ("minecraft:mossy_stone_bricks", "minecraft:cracked_stone_bricks")
    assert all(now == "minecraft:mossy_stone_bricks" for p, (was, now) in changed.items() if p[1] <= 2)


def test_a_dormer_stands_on_the_roof():
    th = THEMES[1]
    t = Template("x")
    for x in range(9):
        t.set(x, 5, 2, "stone")                       # the eaves row and the row behind it
        t.set(x, 6, 3, "stone")
    before = dict(t.blocks)
    houses.dormer(t, th, 4, 2, 5)
    assert all(t.blocks[p] == v for p, v in before.items())
    assert "pane" in t.get(4, 7, 2)
    added = [p for p in t.blocks if p not in before]
    assert added and min(p[1] for p in added) >= 7
