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


# ---------------------------------------------------------------- what the reader read, in the report
# `street_ground` returns one number, and four different columns come out of it the same way: the street read; no
# street in the column; the street skipped because a rigid piece's box covers its paving row, so what lies under the
# street is read instead; and every row of the column inside rigid boxes. The gate's figure cannot tell them apart and
# must not try to: what each bad door says it read is what tells them apart, so the line names the block, how many rows
# were skipped and whether the ground was read below them.
EAVE = dict(loc="heraldia:t/fillers/eave", proj="rigid", bb=[4, 4, -4, 7, 20, -1], junctions=[])


def _bad(blocks, pieces):
    bad = []
    vt.fit_figures(blocks, pieces, bad)
    assert len(bad) == 1, bad
    loc, bb, col, step, read = bad[0]
    return step, read


def test_the_report_says_the_street_was_read_with_nothing_skipped():
    """A real step, nothing over the street: the line names the paving it read and says no row was skipped."""
    step, read = _bad(_street(12), [HOUSE])
    assert step == -3
    assert read["name"] == "minecraft:cobblestone" and read["y"] == 12
    assert read["skipped"] == 0 and read["below_skip"] is False


def test_the_report_says_the_street_was_read_past_and_names_the_water():
    """The street is walkable and a neighbour's rigid box covers its paving row while holding no block in that column
    (an eave, a tower's hollow corner): the gate reads the water under the street and calls it a hole of 6. The figure
    is left as it is; the line now says the ground was water and that it was read below a skipped box."""
    blocks = _street()
    blocks.update({(4, 3, z): "minecraft:water" for z in (-1, -2, -3)})
    step, read = _bad(blocks, [HOUSE, EAVE])
    assert step == 6
    assert read["name"] == "minecraft:water" and read["y"] == 3
    assert read["skipped"] and read["below_skip"] is True
    assert EAVE["bb"] in read["boxes"]


def _ceiling():
    """A walkable street with a rock ceiling in the rows the window reaches over the door: two free rows under it, so a
    villager walks out without stooping."""
    blocks = _street()
    for y in range(16, 19):
        for z in (-1, -2, -3):
            blocks[(4, y, z)] = "minecraft:stone"
    return blocks


def test_a_rock_ceiling_over_a_walkable_street_does_not_make_a_step():
    """The owner's rule (#96): a door fits when the column holds SOME walkable ground within a step, not when the
    highest block of the column happens to be there. `street_ground` still reports the stone it would have taken."""
    assert _doors(_ceiling(), [HOUSE]) == ((1, 1), (0, 1))
    read = {}
    assert vt.street_step(_ceiling(), 4, -2, 10, [], read) == (0, 9)
    assert read["name"] == "minecraft:stone" and read["y"] == 18 and read["surfaces"] == [18, 9]


def test_a_street_on_an_overhang_with_ground_at_the_door_does_not_make_a_step():
    """The seed-s8 shape the owner ruled on: the street passes overhead, with three free rows under it and firm ground
    level with the door. The villager walks out onto the ground, so the door fits."""
    blocks = {(x, 14, z): "minecraft:cobblestone" for x in range(2, 7) for z in (-1, -2, -3)}
    blocks.update({(x, 9, z): "minecraft:grass_block" for x in range(2, 7) for z in (-1, -2, -3)})
    assert _doors(blocks, [HOUSE]) == ((1, 1), (0, 1))


def test_a_door_with_no_walkable_ground_within_a_step_still_fails():
    """The real defect: the only ground in the column is three rows under the door and nothing stands over it."""
    blocks = {(x, 6, z): "minecraft:coarse_dirt" for x in range(2, 7) for z in (-1, -2, -3)}
    assert _doors(blocks, [HOUSE]) == ((0, 1), (0, 1))
    assert _bad(blocks, [HOUSE])[0] == 3


def test_ground_with_nothing_over_it_to_stand_in_is_not_walkable():
    """The other side of the same hole: the paving is at the door's height but two solid rows sit straight on it, so
    nobody stands on the paving and it is not the street any more. The only surface left is the top of what blocks it,
    two over the door, and the door misses. (One row would be a doorstep a villager steps up on, and passes.)"""
    blocks = _street()
    blocks[(4, 10, -2)] = "minecraft:stone"
    blocks[(4, 11, -2)] = "minecraft:stone"
    assert vt.walkable_surfaces(blocks, 4, -2, 18, []) == [11]
    assert _doors(blocks, [HOUSE]) == ((0, 1), (0, 1))
    assert _bad(blocks, [HOUSE])[0] == -2
    one = _street()
    one[(4, 10, -2)] = "minecraft:stone"
    assert _doors(one, [HOUSE]) == ((1, 1), (1, 1))


def test_no_ground_tells_an_empty_column_from_one_all_inside_rigid_boxes():
    """`None` ("no ground under it") joined two columns: one with nothing in the 64 rows read, and one whose 64 rows all
    fell inside rigid boxes (with the street among them). They are told apart now."""
    step, read = _bad({}, [HOUSE])
    assert step is None and read["y"] is None and read["skipped"] == 0
    tall = dict(loc="heraldia:t/terminators/tower", proj="rigid", bb=[4, -60, -4, 7, 20, -1], junctions=[])
    step, read = _bad(_street(), [HOUSE, tall])
    assert step is None and read["y"] is None and read["skipped"] == 64


# ---------------------------------------------------------------- the parent, and the column measured inside it
STREET = dict(loc="heraldia:t/streets/s0", proj="terrain_matching", bb=[2, 9, -3, 6, 14, -1],
              junctions=[(4, 10, 0, 0, "rigid")])    # its side slot, on the house's door row


def test_the_report_names_the_piece_the_door_hangs_from():
    """A count of bad doors cannot say which street a door is off; the parent can only be read from the junctions, as
    the mod reads it, so the report reads it the same way."""
    step, read = _bad(_street(12), [STREET, HOUSE])
    assert step == -3
    assert read["parent"] == "heraldia:t/streets/s0" and read["parent_bb"] == STREET["bb"]


def test_the_measured_column_stays_inside_the_parent():
    """The column measured is chosen by geometry -- one step out from the joint, away from the house -- and nothing makes
    that land inside the parent: with a street one column deep it falls on the piece beyond it. Measuring there judges a
    door against somebody else's street, so the joint's own column is used instead."""
    narrow = dict(loc="heraldia:t/streets/s0", proj="terrain_matching", bb=[2, 9, -1, 6, 14, -1],
                  junctions=[(4, 10, 0, 0, "rigid")])
    blocks = {(x, 9, -1): "minecraft:cobblestone" for x in range(2, 7)}        # the street: one column deep
    blocks.update({(x, 3, -2): "minecraft:stone" for x in range(2, 7)})        # the next piece over, far below
    assert _doors(blocks, [narrow, HOUSE]) == ((1, 1), (0, 1))
    read = {}
    assert vt.street_step(blocks, 4, -1, 10, [], read) == (0, 9)


# ---------------------------------------------------------------- the seed of the fit phase
def test_the_fit_phase_takes_a_seed_and_its_default_is_the_one_the_battery_runs():
    """The door figure of one world is one sample of a figure about terrain, so the fit phase takes a seed; what the
    battery runs must not move, so the default is `FIT_SEED` and `--seeds` (the coastal phase's) is untouched."""
    a = vt.parser().parse_args(["--jar", "x.jar"])
    assert a.fit_seed == vt.FIT_SEED == "heraldia"
    assert a.seeds == vt.NATURAL_SEEDS
    assert vt.parser().parse_args(["--jar", "x.jar", "--fit-seed", "s4"]).fit_seed == "s4"
