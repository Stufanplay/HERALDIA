"""The fenced garden pieces between a village's houses (fillers.filler: garden, flower bed, herb garden): a villager
inside one can walk out. Villagers never open a gate; with the gate shut one that got in stayed there (seen in
village_routes over twelve days, without a bed), and on a server 31 of 60 left inside at nightfall were still there
2,400 ticks later, 1 of 60 with the gate open."""
import random

import fillers
from mediums import _paths
from themes import THEMES


def _gardens():
    for th in THEMES:
        if fillers.soil_of(th) != "grass_block":
            continue                       # dry styles turn the garden into a palm
        for kind in ("garden", "flowerbed", "herbgarden"):
            yield th, kind, fillers.filler(th, random.Random(1), f"test/{kind}", kind)


def _reach(t, start):
    g = _paths.Ground(t, margin=4)
    seen, todo = {start}, [start]
    while todo:
        for m in g.neighbors(todo.pop()):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return seen


def test_a_villager_in_a_garden_can_walk_out():
    n = 0
    for th, kind, t in _gardens():
        n += 1
        gate = [st for st, _ in t.blocks.values() if st.split("[")[0].endswith("_fence_gate")]
        assert gate and all("open=true" in st for st in gate), (th.get("id"), kind, gate)
        # from the middle of the garden (the path column, x 3) its search gets out past the fence (z beyond 8 or below 1)
        seen = _reach(t, (3, 1, 4))
        assert any(z < 1 or z > 7 or x < 0 or x > 6 for x, _, z in seen), (th.get("id"), kind)
    assert n >= 30
