"""How the inhabitants of the medium structures get home: a report of the check that `_inhabitants.issues` applies.

Usage: python3 tools/gen/inhabitant_walks.py
For every medium-structure template with inhabitant villagers and every bed in it: the trap (mediums/_paths.trap_walk:
where a villager coming home stops against a wall, the bed behind it) and the walk from it to the bed, against the
limit _paths.TRAP_WALK_MAX that the build enforces; and, as before, the longest walk to the bed from any walkable cell of
the template within 16 blocks of it in a straight line (mediums/_inhabitants.worst_walk). That second figure does not
tell a template that fails from one that does not (on a server, the mill at 43 got home 8 times in 8; the hermitage at
41, 3 in 8): it is kept for reference only.
"""
import mediums
from mediums import _inhabitants as inh, _paths
from pack import Registry


def rows():
    reg = Registry()
    for mid, _ in mediums.modules():
        mediums.build(reg, mid)
    out = []
    for name, t in sorted(reg.templates.items()):
        living = [n for *_, n in t.entities if n["id"] == "minecraft:villager" and inh.is_inhabitant(n)]
        if name.startswith("medianas/") and living:
            traps = _paths.trap_walk(t)
            worst = max(traps, key=lambda r: r[2])
            out.append((worst[2], name, len(living), worst[0], worst[1], inh.worst_walk(t)[0]))
    return sorted(out, reverse=True)


if __name__ == "__main__":
    rs = rows()
    for walk, name, n, bed, trap, steps in rs:
        where = f"trap {trap}, {walk:4.1f} blocks' walk" if trap else "no trap"
        print(f"{name:34s} {n} villagers  bed {bed}: {where}   (longest walk from the yard: {steps} steps)")
    print(f"over the limit ({_paths.TRAP_WALK_MAX}): {sum(1 for r in rs if r[0] > _paths.TRAP_WALK_MAX)} of {len(rs)} "
          f"templates; with a trap at all (a walk of {int(_paths.FOLLOW_RANGE)} or more): {sum(1 for r in rs if r[4])}")
