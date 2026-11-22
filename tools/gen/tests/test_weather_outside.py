"""Lived-in wear on the special buildings (houses.weather_outside): moss low and cracks high on the stone that faces
the open air, never a hole, nothing indoors, the ground course left to the foundation processor, and no draw from any
random source."""
import random

import pytest

import houses
import pack
import specials
from core import Template
from themes import THEMES

STONE = [th for th in THEMES if th["church"] in ("romanesque", "gothic")]


def name(st):
    return st.split("[")[0].replace("minecraft:", "")


def test_only_the_stone_that_faces_the_open_air_weathers_and_only_into_its_kin():
    t = Template("x/specials/box")
    for x in range(7):
        for z in range(7):
            for y in range(6):
                edge = x in (0, 6) or z in (0, 6)
                t.set(x, y, z, "stone_bricks" if edge or y in (0, 5) else "air")
    t.set(3, 2, 3, "stone_bricks")                      # a pillar indoors
    t.set(0, 2, 3, "oak_planks")                        # wood in the wall
    before = dict(t.blocks)
    n = houses.weather_outside(t)
    changed = {p: (name(before[p][0]), name(t.blocks[p][0])) for p in before if before[p] != t.blocks[p]}
    assert n == len(changed) > 0
    for (x, y, z), (was, now) in changed.items():
        assert was == "stone_bricks" and now in houses.KIN["stone_bricks"]
        assert y > 0 and (x in (0, 6) or z in (0, 6))                      # not the ground course, not indoors
        assert now == ("mossy_stone_bricks" if y <= 2 else "cracked_stone_bricks")
    assert name(t.get(3, 2, 3)) == "stone_bricks" and name(t.get(0, 2, 3)) == "oak_planks"
    assert set(t.blocks) == set(before)                                    # never a hole, never a block more


@pytest.mark.parametrize("th", STONE[:6], ids=lambda th: th["id"])
def test_a_weathered_special_is_the_same_building(th):
    """The same blocks in the same places but for stone swapped for its kin; what the building does (its villagers,
    chest, bell, workstations and connectors) is untouched; and the wear is there to be seen."""
    plain = specials.townhall(th, random.Random(4), f"{th['id']}/specials/townhall")
    worn = specials.townhall(th, random.Random(4), f"{th['id']}/specials/townhall")
    n = houses.weather_outside(worn)
    assert set(plain.blocks) == set(worn.blocks)
    diff = [p for p in plain.blocks if plain.blocks[p] != worn.blocks[p]]
    assert len(diff) == n
    for p in diff:
        was, now = name(plain.blocks[p][0]), name(worn.blocks[p][0])
        assert now in houses.KIN[was], (was, now)
        assert not plain.blocks[p][1]
    assert pack.function_signature(plain) == pack.function_signature(worn)
    assert plain.jigsaws == worn.jigsaws and len(plain.entities) == len(worn.entities)


def test_the_wear_draws_nothing_and_is_the_same_every_time():
    th = STONE[0]
    a = specials.townhall(th, random.Random(4), f"{th['id']}/specials/townhall")
    b = specials.townhall(th, random.Random(4), f"{th['id']}/specials/townhall")
    state = random.getstate()
    houses.weather_outside(a)
    assert random.getstate() == state
    houses.weather_outside(b)
    assert a.blocks == b.blocks
