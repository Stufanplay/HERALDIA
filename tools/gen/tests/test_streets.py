"""Village streets and plaza (streets.py): a street has a kerb and things beside its lamps, and is as lit as it was;
the things are not containers and nothing a villager takes for a workstation; the plaza keeps every place the village's
welcome decorations use (welcome/Spots.plaza: the fountain's rim, the banners' cells at the four entrances), and nothing
in its beds hurts whoever walks through."""
import random

import pytest

import lint
import streets
from themes import THEMES

N, C = 23, 11
# blocks a villager claims as a workstation or a bed, and containers (the rule: no empty chest)
TAKEN = ("barrel", "chest", "composter", "cauldron", "lectern", "grindstone", "smithing_table", "fletching_table",
         "cartography_table", "brewing_stand", "blast_furnace", "smoker", "furnace", "loom", "stonecutter", "bell",
         "_bed", "hopper", "dropper", "dispenser", "shulker_box")
HURTS = ("cactus", "sweet_berry_bush", "wither_rose", "campfire", "magma_block", "fire")
LIGHTS = ("lamp", "lamp_tall")


def name(st):
    return st.split("[")[0].replace("minecraft:", "")


def test_a_street_is_as_lit_as_it_was():
    """Lamps had 7 parts in 13 of a street's decoration slots (5 + 2 against 2 planters and 4 empty)."""
    total = sum(w for _, w in streets.DECOR_WEIGHTS) + streets.DECOR_EMPTY
    lamps = sum(w for k, w in streets.DECOR_WEIGHTS if k in LIGHTS)
    assert lamps * 13 >= 7 * total, (lamps, total)
    assert {k for k, _ in streets.DECOR_WEIGHTS} >= set(streets.STREET_THINGS) | set(LIGHTS)


@pytest.mark.parametrize("th", THEMES, ids=lambda th: th["id"])
def test_the_streets_things_are_one_block_wide_and_nobodys_workstation(th):
    for kind in streets.STREET_THINGS:
        t = streets.decor_piece(th, random.Random(1), f"{th['id']}/decor/{kind}", kind)
        solid = {p: name(st) for p, (st, _) in t.blocks.items() if name(st) not in ("air", "jigsaw")}
        assert solid and all((x, z) == (0, 0) and 1 <= y <= 2 for (x, y, z) in solid), (kind, solid)
        assert not [b for b in solid.values() if any(k in b for k in TAKEN + HURTS)], (kind, solid)
        assert not any(v[1] for v in t.blocks.values() if name(v[0]) != "jigsaw"), kind      # no block entity
        assert not t.entities
        assert not [b for b in solid.values() if "lantern" in b or "torch" in b], kind        # no light either


@pytest.mark.parametrize("th", THEMES, ids=lambda th: th["id"])
def test_a_street_keeps_its_ground_whole_and_its_air_free(th):
    t = streets.straight(th, random.Random(2), f"{th['id']}/streets/x", 16)
    for x in range(1, 6):
        for z in range(16):
            assert not lint.passable(t.get(x, 0, z)), (x, z, t.get(x, 0, z))        # paving or kerb: something to walk on
            assert name(t.get(x, 1, z)) in ("air", "jigsaw"), (x, z)
    edge = {name(t.get(x, 0, z)) for x in (1, 5) for z in range(16)}
    mid = {name(t.get(3, 0, z)) for z in range(16)}
    assert edge - mid or len(edge) > 1, (edge, mid)                                  # the edge is not the middle's stripe


@pytest.mark.parametrize("large", (False, True))
@pytest.mark.parametrize("th", THEMES, ids=lambda th: th["id"])
def test_the_plaza_keeps_what_the_welcome_uses_and_harms_nobody(th, large):
    t = streets.plaza(th, random.Random(3), f"{th['id']}/plaza/x", large)
    assert t.min_size[0] == t.min_size[2] == N
    lo, hi = C - 3, C + 3
    for x, z in ((lo, lo), (hi, lo), (lo, hi), (hi, hi), (C, lo), (hi, C), (C, hi), (lo, C)):     # pots on the rim
        assert not lint.passable(t.get(x, 1, z)) and name(t.get(x, 2, z)) == "air", (x, z)
    for d in (-3, 3):                                                                             # banners at the entrances
        for x, z in ((C + d, 1), (C + d, N - 2), (1, C + d), (N - 2, C + d)):
            assert not lint.passable(t.get(x, 0, z)) and name(t.get(x, 1, z)) == "air", (x, z)
    for (x, z) in ((C, 0), (N - 1, C), (C, N - 1), (0, C)):                                       # the four avenues
        assert name(t.get(x, 1, z)) == "jigsaw"
    blocks = {p: name(st) for p, (st, _) in t.blocks.items()}
    assert not [(p, b) for p, b in blocks.items() if any(k in b for k in HURTS)]
    assert sum(1 for b in blocks.values() if b == "bell") == 1
    # every plant of a bed stands on its grass, and the way from each avenue to the fountain's step is open
    for (x, y, z), b in blocks.items():
        if y == 1 and b in set(th["plants"]) | set(streets.BEDDING.values()):
            assert blocks.get((x, 0, z)) == "grass_block", (x, z, b)
    for k in range(1, C - 4):
        for x, z in ((C, k), (C, N - 1 - k), (k, C), (N - 1 - k, C)):
            assert blocks.get((x, 1, z), "air") == "air" and blocks.get((x, 2, z), "air") == "air", (x, z)
