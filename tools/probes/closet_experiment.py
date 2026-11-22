"""The EXPERIMENTAL ladder closet of Nov 2026, as it was patched into tools/gen/pack.py to build the jar the figures
below came from (never committed there). To rebuild that jar: paste _closet_villages into pack.py, call it at the end of
build_all() when HERALDIA_EXPERIMENT_CLOSET is set, and run HERALDIA_EXPERIMENT_CLOSET=1 ./gradlew build.
It is CRUDE on purpose and NOT the fix: it puts the gate on the first open side of the ladder's foot and 2-high posts on
every other open side, which walls off part of the building in 30 church templates (162 ground cells each) and left 2
villagers shut in near a closet in the 12-day run. A real closet chooses its sides and is checked in the build."""


def _closet_villages(reg):
    import json as _json, lint as _lint
    nm = lambda st: st.split("[")[0].replace("minecraft:", "") if st else None
    log = {"closed": 0, "blocked": [], "cells": {}}
    for n, t in reg.templates.items():
        if n.startswith(("medianas/", "unicas/", "minas/", "costa/")):
            continue
        cols = {}
        for (x, y, z), (st, _) in t.blocks.items():
            if nm(st) == "ladder":
                cols.setdefault((x, z), []).append(y)
        for (x, z), ys in cols.items():
            if min(ys) != 1 or max(ys) - min(ys) + 1 < 4:
                continue
            open_sides = []
            for dx, dz, face in ((0, -1, "north"), (0, 1, "south"), (1, 0, "east"), (-1, 0, "west")):
                a = t.blocks.get((x + dx, 1, z + dz), (None,))[0]
                b = t.blocks.get((x + dx, 2, z + dz), (None,))[0]
                if a and not _lint.passable(a) and nm(a) not in ("air",):
                    continue                                   # a wall or furniture: closed already
                if (a is None or nm(a) == "air") and (b is None or nm(b) == "air" or _lint.passable(b)):
                    open_sides.append((dx, dz, face))
                else:
                    log["blocked"].append((n, (x, z), nm(a), nm(b)))
            for k, (dx, dz, face) in enumerate(open_sides):
                if k == 0:
                    t.set(x + dx, 1, z + dz, f"oak_fence_gate[facing={face},in_wall=false,open=false,powered=false]")
                else:
                    t.set(x + dx, 1, z + dz, "oak_log[axis=y]")
                    t.set(x + dx, 2, z + dz, "oak_log[axis=y]")
                log["cells"].setdefault(n, []).append([x + dx, z + dz, "gate" if k == 0 else "post"])
            log["closed"] += 1
    _json.dump(log, open("closet_log.json", "w"))
