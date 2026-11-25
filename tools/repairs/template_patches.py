"""Template patches for /heraldia update mend: the cells a generator fix changed in a template already published,
taken by comparing the templates the generator wrote before the fix with what it writes now.

Usage: python3 tools/repairs/template_patches.py --now build/generated/heraldia --before <commit>=<dir> [<commit>=<dir> ...]
       [--out src/main/resources/heraldia/mend]
Each <dir> is the output of `tools/gen/main.py --out <dir>` run on a checkout of <commit>; the FIRST --before is the
commit right before the fix: the cells it and today's template differ in are the patch (nothing else). The others are
earlier versions whose templates may also be in a world: their block at each of those cells is recorded too, so a
piece of any of them is recognised. A guard is a cell beside a patched one that every version and today agree on
(it must still be the template's block in the world, or the piece is somebody's and is left alone).

The patches are written as JSON (one file per kind) and read by update/GenerationMend. A JUnit test
(GenerationMendTest) checks each patch's `after` against the templates being built, so a later generator change that
touches a patched cell fails there.
"""
import argparse, glob, json, os, sys

import nbtlib

# kind -> (template folder under data/heraldia/structure, the files in it, what the patch is for, the mob whose post
# it records: the cell each such mob of today's template stands in)
KINDS = {
    "inn": ("medianas/posada", "*/*.nbt", "the Roadside Inn's bedroom door (the innkeeper's bed out of his reach)", None),
    "wharf": ("medianas/embarcadero_shulker", "*/*.nbt", "the Wharf Guard's post (a full block: a shulker cannot hold a wall)",
              "minecraft:shulker"),
}
AROUND = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def state_string(p):
    """A palette entry as a block state string (26.3 writes {id, properties}; earlier, {Name, Properties})."""
    name = str(p["id"] if "id" in p else p["Name"])
    props = p.get("properties") if "id" in p else p.get("Properties")
    if props:
        name += "[" + ",".join(f"{k}={props[k]}" for k in sorted(props)) + "]"
    return name


def read(path):
    """{(x, y, z): (state, has_block_entity)} of a template; air cells absent from the file are not listed."""
    t = nbtlib.load(path)
    palette = [state_string(p) for p in (t.get("palette") or t["palettes"][0])]
    out = {}
    for b in t["blocks"]:
        x, y, z = (int(v) for v in b["pos"])
        out[(x, y, z)] = (palette[int(b["state"])], "nbt" in b)
    size = tuple(int(v) for v in t["size"])
    return out, size


def posts(path):
    """[(cell, mob id)] of a template's entities."""
    t = nbtlib.load(path)
    return [(tuple(int(v) for v in e["blockPos"]), str(e["nbt"].get("id", ""))) for e in t.get("entities", [])]


def at(blocks, size, p):
    if p in blocks:
        return blocks[p][0]
    inside = all(0 <= p[i] < size[i] for i in range(3))
    return "minecraft:structure_void" if not inside else "minecraft:air_unset"


def patch(kind, now_dir, befores):
    folder, pattern = KINDS[kind][:2]
    root = os.path.join(now_dir, "data", "heraldia", "structure", folder)
    out = []
    for path in sorted(glob.glob(os.path.join(root, pattern))):
        rel = os.path.relpath(path, os.path.join(now_dir, "data", "heraldia", "structure"))
        tid = "heraldia:" + rel[:-4].replace(os.sep, "/")
        now, size = read(path)
        olds = []
        for commit, d in befores:
            p = os.path.join(d, "data", "heraldia", "structure", rel)
            olds.append((commit, read(p) if os.path.isfile(p) else None))
        first = olds[0][1]
        if first is None:
            continue
        b0, s0 = first
        if s0 != size:
            sys.exit(f"{tid}: the template's size changed ({s0} -> {size}); a patch cannot say what moved")
        changed = sorted(p for p in set(now) | set(b0) if at(now, size, p) != at(b0, s0, p))
        if not changed:
            continue
        versions, cells = [], []
        usable = [(c, o) for c, o in olds if o is not None and o[1] == size]
        versions = [c for c, _ in usable]
        for p in changed:
            cells.append({"pos": list(p), "after": at(now, size, p).replace("air_unset", "air"),
                          "before": [at(o[0], o[1], p).replace("air_unset", "air") for _, o in usable]})
        guards = []
        seen = set(changed)
        for p in changed:
            for d in AROUND:
                q = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
                if q in seen or not all(0 <= q[i] < size[i] for i in range(3)):
                    continue
                seen.add(q)
                s = at(now, size, q)
                if all(at(o[0], o[1], q) == s for _, o in usable) and "structure_void" not in s:
                    guards.append({"pos": list(q), "block": s.split("[")[0].replace("air_unset", "air")})
        # a container that left one cell for another: carried with what it holds
        moves = []
        entity = lambda blocks, p: blocks.get(p, (None, False))[1]
        gone = [c for c in cells if entity(b0, tuple(c["pos"])) and not entity(now, tuple(c["pos"]))]
        came = [c for c in cells if entity(now, tuple(c["pos"])) and not entity(b0, tuple(c["pos"]))]
        for g in gone:
            for c in came:
                if c["after"].split("[")[0] == b0[tuple(g["pos"])][0].split("[")[0]:
                    moves.append({"from": g["pos"], "to": c["pos"]})
                    came.remove(c)
                    break
        piece = {"template": tid, "versions": versions, "cells": cells, "guards": guards, "moves": moves}
        if KINDS[kind][3]:
            piece["posts"] = sorted(list(p) for p, e in posts(path) if e == KINDS[kind][3])
        out.append(piece)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", required=True)
    ap.add_argument("--before", nargs="+", required=True, help="<commit>=<generated dir>, the one right before the fix first")
    ap.add_argument("--out", default=os.path.join("src", "main", "resources", "heraldia", "mend"))
    ap.add_argument("--kind", choices=sorted(KINDS), nargs="+", default=sorted(KINDS))
    a = ap.parse_args()
    befores = [tuple(b.split("=", 1)) for b in a.before]
    os.makedirs(a.out, exist_ok=True)
    for kind in a.kind:
        pieces = patch(kind, a.now, befores)
        with open(os.path.join(a.out, f"{kind}.json"), "w", encoding="utf-8") as f:
            json.dump({"kind": kind, "what": KINDS[kind][2], "pieces": pieces}, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"{kind}: {len(pieces)} templates, {sum(len(p['cells']) for p in pieces)} cells, "
              f"{sum(len(p['guards']) for p in pieces)} guards, {sum(len(p['moves']) for p in pieces)} moves")


if __name__ == "__main__":
    main()
