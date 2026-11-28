"""tools/smoke/village_terrain.py, the doors of the terrain fit: the gate's figure reads the street under any piece placed
on it (`street_ground`), and the informative figure beside it the highest block of the street column, which reads a
piece over the street -- a well on an avenue, a terminator's tower -- as a step. A real step, with nothing on the street,
fails both; and the gate's own figure is the same whether the informative one is asked for or not."""
import os, sys

SMOKE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "smoke")
_path = list(sys.path)
sys.path.insert(0, SMOKE)
import village_terrain as vt  # noqa: E402
sys.path[:] = _path

HOUSE = dict(loc="heraldia:t/houses/h", proj="rigid", bb=[0, 10, 0, 8, 18, 8],
             junctions=[(4, 10, -1, 0, "terrain_matching")])    # its door opens north onto the street at z = -1


def _street(y=9):
    """The street: cobblestone at `y` (its walking floor y + 1) from z = -1 to -3, under the house's door."""
    return {(x, y, z): "minecraft:cobblestone" for x in range(2, 7) for z in (-1, -2, -3)}


def _doors(blocks, pieces):
    highest = {}
    _, gate, _ = vt.fit_figures(blocks, pieces, None, highest)
    return gate, (highest["ok"], highest["n"])


def test_a_door_on_its_street_passes_both():
    assert _doors(_street(), [HOUSE]) == ((1, 1), (1, 1))


def test_a_piece_over_the_street_passes_the_gate_and_fails_the_highest_block():
    """A tower terminator standing on the street column, as in the CI village: the gate reads the street under it, the
    informative figure its top (a step of -9)."""
    tower = dict(loc="heraldia:t/terminators/tower_b", proj="rigid", bb=[3, 10, -3, 5, 24, -2], junctions=[])
    blocks = _street()
    blocks.update({(4, y, -2): "minecraft:mossy_stone_bricks" for y in range(10, 25)})
    assert _doors(blocks, [HOUSE, tower]) == ((1, 1), (0, 1))


def test_a_real_step_fails_both():
    """The street three blocks above the door's floor, with nothing on it: a real step, and both figures see it."""
    assert _doors(_street(12), [HOUSE]) == ((0, 1), (0, 1))


def test_the_gate_is_the_same_with_or_without_the_informative_figure():
    tower = dict(loc="heraldia:t/terminators/tower_b", proj="rigid", bb=[3, 10, -3, 5, 24, -2], junctions=[])
    blocks = _street()
    blocks.update({(4, y, -2): "minecraft:mossy_stone_bricks" for y in range(10, 25)})
    for pieces in ([HOUSE], [HOUSE, tower]):
        assert vt.fit_figures(blocks, pieces) == vt.fit_figures(blocks, pieces, [], {})
