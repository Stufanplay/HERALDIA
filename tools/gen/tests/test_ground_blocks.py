"""tools/smoke/ground_blocks.py, what village_terrain's ground reader counts as ground (#98): decided for every block of
the 26.3 registry from its collision box and the registry's tags for trees and plants, not from a list of names. The
table records the registry it was made from, so a block a new version adds fails here until it is regenerated."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SMOKE = os.path.join(ROOT, "tools", "smoke")
_path = list(sys.path)
sys.path.insert(0, SMOKE)
import ground_blocks as gb  # noqa: E402
import village_terrain as vt  # noqa: E402
sys.path[:] = _path

SUMMARY = os.environ.get("MCMETA_SUMMARY") or os.path.join(ROOT, "build", "mcmeta-summary")
needs_summary = pytest.mark.skipif(not os.path.isfile(os.path.join(SUMMARY, "blocks", "data.json")),
                                   reason="without build/mcmeta-summary")
# The 13 classes #98 found counted as ground by the old lists of names: all but the cactus have no collision box above
# 1/8. The cactus has one (15/16) and no tag of the registry calls it a plant, so it is ground, as a log would be
# without its tag.
FOUND = ("blue_orchid", "allium", "azure_bluet", "oxeye_daisy", "lilac", "peony", "wildflowers", "sugar_cane",
         "lily_pad", "kelp", "seagrass", "pitcher_plant")


@needs_summary
def test_the_table_covers_the_whole_registry_and_its_tags():
    t = gb.table()
    with open(os.path.join(SUMMARY, "version.txt"), encoding="utf-8") as f:
        assert t["version"] == f.read().strip()
    reg = gb.registry(SUMMARY)
    assert (t["registry_blocks"], t["registry_sha256"]) == (len(reg), gb.registry_sha256(reg)), \
        "the registry is not the one ground_blocks.json was made from: regenerate it (tools/smoke/ground_blocks.py)"
    assert set(t["no_collision_box"]) <= set(reg)
    assert t["plants"] == gb.plants(SUMMARY)
    assert t["plant_tags"] == list(gb.PLANT_TAGS) and t["ground_min_top"] == gb.GROUND_MIN_TOP


def test_every_block_without_a_collision_box_is_not_ground_but_water():
    t = gb.table()
    assert len(t["no_collision_box"]) >= 250 and all(top <= gb.GROUND_MIN_TOP for top in t["no_collision_box"].values())
    for name in t["no_collision_box"]:
        assert vt._is_ground(name) == (name == gb.WATER), name
    assert vt._is_ground("minecraft:water"), "water counts as ground, on purpose"


def test_trees_and_plants_with_a_collision_box_are_not_ground():
    t = gb.table()
    for name in t["plants"]:
        assert not vt._is_ground(name), name
    for name in ("oak_log", "stripped_spruce_log", "oak_leaves", "pumpkin", "cocoa", "chorus_plant", "azalea"):
        assert "minecraft:" + name not in t["no_collision_box"] and not vt._is_ground("minecraft:" + name), name


def test_what_the_old_lists_of_names_got_wrong():
    for name in FOUND + ("lava", "cobweb", "white_banner", "wheat", "redstone_wire"):
        assert not vt._is_ground("minecraft:" + name), name
    # solid blocks a substring of the old lists left out ("snow", "bamboo", a potted plant's "poppy")
    for name in ("snow_block", "bamboo_planks", "potted_poppy", "stone", "dirt_path", "oak_slab", "cactus"):
        assert vt._is_ground("minecraft:" + name), name
    assert not vt._is_ground("minecraft:snow") and not vt._is_ground("minecraft:white_carpet")


def test_a_flower_on_the_street_is_not_its_ground():
    """The door of s3 in #98: wildflowers on coarse dirt, read a block too high by the old lists."""
    blocks = {(0, 72, 0): "minecraft:coarse_dirt", (0, 73, 0): "minecraft:wildflowers", (0, 71, 0): "minecraft:dirt"}
    assert vt.ground(blocks, 0, 0, 80) == 72
    assert vt.street_ground(blocks, 0, 0, 80, []) == 72


def test_a_block_the_table_does_not_know_counts_as_ground():
    assert vt._is_ground("othermod:strange_block")


def test_the_table_is_valid_json_with_no_tabs():
    with open(gb.TABLE, encoding="utf-8") as f:
        text = f.read()
    assert "\t" not in text and json.loads(text)["no_collision_box"]
