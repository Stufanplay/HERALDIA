"""Lived-in wear on the special buildings (houses.weather_outside): moss and cracks low on the stone that faces the
open air (and a little higher beside water), nothing higher up, never a hole, nothing indoors, the ground course left to the foundation processor, and no draw from any
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
        assert y <= 2, (x, y, z)                                           # low on the wall, nothing higher up
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


def test_beside_water_the_wear_climbs_two_courses_more_and_no_further():
    """A wall with a pond at its foot: within two blocks of the water the moss and the cracks reach the fourth course,
    not the fifth; away from it, and on a dry wall, the second and no higher."""
    def box(water):
        t = Template("x/specials/wet")
        for x in range(2, 22):
            for z in range(2, 9):
                for y in range(8):
                    t.set(x, y, z, "cobblestone" if x in (2, 21) or z in (2, 8) or y in (0, 7) else "air")
        if water:
            for x in range(8, 16):
                t.set(x, 0, 0, "water")                 # a pond outside, two blocks from the long wall z = 2
        return t
    dry, wet = box(False), box(True)
    houses.weather_outside(dry)
    houses.weather_outside(wet)
    worn = lambda t: {p for p, (st, _) in t.blocks.items() if st != "minecraft:cobblestone" and st != "minecraft:air"
                      and st != "minecraft:water"}
    assert worn(dry) and max(p[1] for p in worn(dry)) <= 2
    high = {p for p in worn(wet) if p[1] > 2}
    assert high, "the wall by the water shows no wear above the second course"
    assert all(p[1] <= 4 and 6 <= p[0] <= 17 and p[2] == 2 for p in high), sorted(high)
    assert {p for p in worn(wet) if p[1] <= 2} == worn(dry)                # the rest of the building is as the dry one
