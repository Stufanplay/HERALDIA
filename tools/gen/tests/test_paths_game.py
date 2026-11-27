"""The model of the villager's path search (mediums/_paths) where it disagreed with the game's (26.3
WalkNodeEvaluator, read with javap, and measured on a server with tools/probes/wcemetery.py): it stands on the top of a
wall, a fence, a shut gate (getPathTypeStatic: an open cell over a FENCE block is WALKABLE, its floor at +1.5), and a
scaffold is air to it (getPathTypeFromState: a block pathfindable by land is OPEN, and a scaffold's collision is not a
full block). Both changes added no finding to any audit of the build."""
import ladders
from core import Template
from mediums import _paths as P


def _pen(outside=None):
    """A 5 x 5 pen walled at y = 1 on a stone floor, and against its east wall outside, `outside` a block up."""
    t = Template("t")
    for x in range(9):
        for z in range(5):
            t.set(x, 0, z, "stone")
    for x in range(5):
        for z in range(5):
            if x in (0, 4) or z in (0, 4):
                t.set(x, 1, z, "cobblestone_wall")
    if outside:
        for x in range(5, 8):
            for z in range(5):
                t.set(x, 1, z, outside)
    return t


def _inside(t):
    g = P.Ground(t, margin=3)
    return [c for c in ladders.ground_walk(t, g) if 1 <= c[0] <= 3 and 1 <= c[2] <= 3]


def test_a_wall_top_is_a_floor_and_a_step_up_from_a_block_beside_it():
    assert _inside(_pen()) == []                  # from the ground the top is 1.5 up: no way in
    t = _pen("stone")
    assert P.Ground(t, margin=3).floor(4, 2, 2) == 2.5
    assert len(_inside(t)) == 9                   # half a block up from the platform, and down inside


def test_a_fence_and_a_shut_gate_too_an_open_gate_not():
    for st, top in (("oak_fence", 2.5), ("oak_fence_gate[facing=north,open=false]", 2.5),
                    ("oak_fence_gate[facing=north,open=true]", None)):
        t = Template("t")
        t.set(0, 0, 0, "stone")
        t.set(0, 1, 0, st)
        assert P.Ground(t, margin=1).floor(0, 2, 0) == top, st


def test_a_scaffold_is_air():
    """No floor on top of a scaffold, and none on the scaffold platform beside it either: the search falls through."""
    t = _pen("scaffolding[bottom=false,distance=0,waterlogged=false]")
    g = P.Ground(t, margin=3)
    assert g.floor(6, 2, 2) is None and g.floor(6, 1, 2) == 1.0
    assert _inside(t) == []
