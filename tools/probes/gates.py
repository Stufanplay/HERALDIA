"""Census of village templates: walled or fenced places a villager can stand in whose only way to the street is a shut
fence gate (villagers open doors, never gates). Model: tools/gen/mediums/_paths (the 26.3 search: no ladders, closed
gates as fences, drops of 3).

For each template, the search's walk from the flat ground around it is taken twice, with its gates as they are and
with every one of them open; what only the second reaches is BEHIND a gate. Each connected place behind a gate is
reported with what puts a villager in it: a villager spawned inside it (a jigsaw into a `villagers/` pool, whose
villager stands on the cell above), a bed, a workstation, or none of those (an animal pen, a garden).

Usage: gates.py <repo> [out.json]
"""
import collections
import json
import os
import sys

REPO = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(REPO, "tools", "gen"))

VILLAGE = ("house", "street", "tower", "gate", "decor", "plaza", "avenue", "filler", "tablon", "trace")
WORKSTATIONS = ("lectern", "composter", "barrel", "smoker", "blast_furnace", "cartography_table", "brewing_stand",
                "fletching_table", "grindstone", "loom", "smithing_table", "stonecutter", "cauldron")


def is_village(kind):
    return kind in VILLAGE or kind.startswith("special:")


def _name(st):
    return st.split("[")[0].replace("minecraft:", "") if st else ""


def _opened(t):
    """A copy of the template with every fence gate open (the audit's own, enclosures.opened)."""
    import enclosures
    return enclosures.opened(t)


def _walk(g, sx, sz):
    m, y = g.box[0], g.base
    starts = [(x, y, z) for x in range(m, sx - m) for z in (m, sz - m - 1) if g.floor(x, y, z) is not None]
    starts += [(x, y, z) for z in range(m, sz - m) for x in (m, sx - m - 1) if g.floor(x, y, z) is not None]
    seen, todo = set(starts), list(starts)
    while todo:
        for c in g.neighbors(todo.pop()):
            if c not in seen:
                seen.add(c)
                todo.append(c)
    return seen


def analyse(t):
    """[place behind a gate: dict(cells, gates, spawns, beds, workstations, floor_y)] for one template."""
    from mediums import _paths as P
    sx, _, sz = t.size()
    from ladders import level
    shut = P.Ground(t, base=level(t))       # the ground at the height of the jigsaw that joins the piece (#86)
    opened = P.Ground(_opened(t), base=level(t))
    a = _walk(shut, sx, sz)
    b = _walk(opened, sx, sz)
    behind = b - a
    gates = {p for p, (st, _) in t.blocks.items() if _name(st).endswith("_fence_gate") and "open=true" not in st}
    # the gates of the ladder closets (#152) shut a ladder away from the villager on purpose: not what is counted here
    closet = {p for c in getattr(t, "closets", ()) for p in c["cells"] if p in gates}
    places, done = [], set()
    for c in sorted(behind):
        if c in done or c in gates:
            continue
        comp, todo = {c}, [c]
        while todo:
            for m in opened.neighbors(todo.pop()):
                if m in behind and m not in comp and m not in gates:
                    comp.add(m)
                    todo.append(m)
        done |= comp
        near = lambda p: any((p[0] + dx, p[1] + dy, p[2] + dz) in comp
                             for dx in (-1, 0, 1) for dz in (-1, 0, 1) for dy in (-1, 0, 1))
        spawns = [j["pool"] for j in t.jigsaws if ":villagers/" in j["pool"]
                  and (j["pos"][0], j["pos"][1] + 1, j["pos"][2]) in comp]
        beds = sum(1 for p, (st, _) in t.blocks.items() if _name(st).endswith("_bed") and "part=head" in st and near(p))
        work = sorted({_name(st) for p, (st, _) in t.blocks.items() if _name(st) in WORKSTATIONS and near(p)})
        gs = sorted(p for p in gates if near(p))
        if gs and all(p in closet for p in gs):
            continue
        places.append(dict(cells=len(comp), gates=[list(p) for p in gs], spawns=spawns, beds=beds, workstations=work,
                           floor_y=sorted({y for _, y, _ in comp})))
    return places


def main():
    import pack
    reg = pack.build_all()
    names = sorted(n for n, k in reg.kinds.items() if is_village(k))
    print(len(names), "village templates of", len(reg.templates), flush=True)
    out, errors = {}, []
    for i, n in enumerate(names):
        try:
            out[n] = dict(kind=reg.kinds[n], places=analyse(reg.templates[n]))
        except Exception as e:                       # noqa: BLE001
            errors.append((n, repr(e)))
        if (i + 1) % 200 == 0:
            print("...", i + 1, flush=True)
    print("ERRORS:", len(errors), errors[:5])
    any_t = collections.Counter()
    spawn_t = collections.Counter()
    bed_t = collections.Counter()
    work_t = collections.Counter()
    family = collections.Counter()
    for n, r in out.items():
        ps = r["places"]
        if not ps:
            continue
        fam = n.split("/", 1)[1] if "/" in n else n
        fam = "/".join(fam.split("/")[:2]).rstrip("0123456789_")
        any_t[r["kind"]] += 1
        if any(p["spawns"] for p in ps):
            spawn_t[r["kind"]] += 1
            family["spawn: " + fam] += 1
        elif any(p["beds"] for p in ps):
            bed_t[r["kind"]] += 1
            family["bed: " + fam] += 1
        elif any(p["workstations"] for p in ps):
            work_t[r["kind"]] += 1
            family["workstation: " + fam] += 1
        else:
            family["empty: " + fam] += 1
    print("templates with a place behind a shut gate:", sum(any_t.values()),
          "| a villager spawned in it:", sum(spawn_t.values()),
          "| else a bed:", sum(bed_t.values()), "| else a workstation:", sum(work_t.values()))
    print("--- by kind (any / spawn / bed / workstation) ---")
    for k in sorted(any_t):
        print(f"  {k:24s} {any_t[k]:4d} {spawn_t[k]:4d} {bed_t[k]:4d} {work_t[k]:4d}")
    print("--- by piece ---")
    for f, c in sorted(family.items()):
        print(f"  {c:4d}  {f}")
    json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "gates.json", "w"), indent=1)


if __name__ == "__main__":
    main()
