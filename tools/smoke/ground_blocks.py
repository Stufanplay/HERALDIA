"""Which blocks count as ground for village_terrain's ground reader (#98), from the 26.3 registry, not from a list of names.

A block is ground when its default state has a collision box whose top is above GROUND_MIN_TOP (1/8: a carpet, a lily
pad or a repeater is walked over as the block under it) and it is not a plant: a member of one of PLANT_TAGS, the
registry's own tags for trees and plants (a trunk or a pumpkin on a street column is not its ground). Water is ground,
on purpose (`village_terrain.ground`'s docstring): it is the one exception, and it is spelled out in `is_ground`.

ground_blocks.json holds the blocks of the registry with no collision box above GROUND_MIN_TOP, with the top of theirs
(tools/smoke/BlockCollision.java, run against the game, gives it for every block), the members of PLANT_TAGS (expanded
from the tags of mcmeta-summary) and the sha256 of the registry's sorted block ids it was made from. It is regenerated,
for a new version of the game, with

  java -cp "<minecraft-common-deobf jar>:<server libraries>" tools/smoke/BlockCollision.java > collision.json
  python3 tools/smoke/ground_blocks.py collision.json build/mcmeta-summary

and tools/gen/tests/test_ground_blocks.py fails while the registry is not the one it was made from.
"""
import json
import os
import sys

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ground_blocks.json")
GROUND_MIN_TOP = 0.125
PLANT_TAGS = ("logs", "leaves", "saplings", "flowers", "crops", "sword_efficient")
WATER = "minecraft:water"

_table = None


def table():
    global _table
    if _table is None:
        with open(TABLE, encoding="utf-8") as f:
            _table = json.load(f)
    return _table


def is_ground(name):
    """Is the block `name` (a namespaced id, no properties) ground? A block the table does not name (another mod's)
    counts as ground, as every block not named in the old lists did."""
    if name == WATER:
        return True
    t = table()
    return name not in t["no_collision_box"] and name not in t["plants"]


def tag_members(tags, name, seen=None):
    """The blocks of the tag `name` of the registry's block tags (mcmeta-summary data/tag/block), nested tags expanded."""
    seen = set() if seen is None else seen
    out = set()
    for v in tags[name]["values"]:
        v = v if isinstance(v, str) else v["id"]
        if v.startswith("#"):
            n = v[1:].split(":", 1)[-1]
            if n not in seen:
                seen.add(n)
                out |= tag_members(tags, n, seen)
        else:
            out.add(v if ":" in v else "minecraft:" + v)
    return out


def plants(summary):
    with open(os.path.join(summary, "data", "tag", "block", "data.json"), encoding="utf-8") as f:
        tags = json.load(f)
    return sorted(set().union(*(tag_members(tags, n) for n in PLANT_TAGS)))


def registry(summary):
    """Every block id of the registry, from mcmeta-summary blocks/data.json."""
    with open(os.path.join(summary, "blocks", "data.json"), encoding="utf-8") as f:
        return sorted("minecraft:" + k for k in json.load(f))


def registry_sha256(ids):
    import hashlib
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def main():
    collision, summary = sys.argv[1], sys.argv[2]
    with open(collision, encoding="utf-8") as f:
        tops = json.load(f)
    with open(os.path.join(summary, "version.txt"), encoding="utf-8") as f:
        version = f.read().strip()
    reg = registry(summary)
    assert sorted(tops) == reg, "the collision dump and mcmeta-summary are not the same registry"
    out = {"version": version, "registry_blocks": len(reg), "registry_sha256": registry_sha256(reg),
           "ground_min_top": GROUND_MIN_TOP, "plant_tags": list(PLANT_TAGS),
           "no_collision_box": {k: tops[k] for k in reg if tops[k] <= GROUND_MIN_TOP}, "plants": plants(summary)}
    with open(TABLE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=0)
        f.write("\n")
    print(f"{TABLE}: {len(reg)} blocks, {len(out['no_collision_box'])} with no collision box, {len(out['plants'])} plants,"
          f" version {version}")


if __name__ == "__main__":
    main()
