"""The village cemetery keeps a ring of bare ground a block wide between its wall and the edge of its piece, on the
three sides away from its gate (specials.ringed): the game's path search walks on a wall's top, and anything a block
high that a neighbouring piece puts against the wall from outside was a step onto it and into the cemetery (measured on
a server: a haystack beside it, 26 villagers inside out of 48; the gate stays shut, as the owner chose)."""
import random

import specials
from themes import THEMES


def _name(st):
    return st.split("[")[0].replace("minecraft:", "") if st else ""


def test_every_cemetery_has_its_ring_and_its_gate_shut():
    for th in THEMES:
        for v in range(specials.VARIANTS["cemetery"]):
            t = specials.cemetery(th, random.Random(f"{th['id']}/{v}"), f"{th['id']}/specials/cemetery", v)
            t.normalize()
            sx, _, sz = t.size()
            assert (sx, sz) == (17, 17), (th["id"], v, t.size())
            ring = [(x, z) for x in range(sx) for z in range(1, sz) if x in (0, sx - 1) or z == sz - 1]
            for x, z in ring:
                assert _name(t.get(x, 0, z)) == "coarse_dirt", (th["id"], v, x, z)
                assert all(_name(t.get(x, y, z)) in ("air", "") for y in (1, 2, 3)), (th["id"], v, x, z)
            # the wall (or hedge) is one cell in, all round, and the gate in it is shut
            for x in range(1, sx - 1):
                assert _name(t.get(x, 1, sz - 2)).endswith(("_wall", "_leaves")), (th["id"], v, x)
            for z in range(2, sz - 1):
                for x in (1, sx - 2):
                    assert _name(t.get(x, 1, z)).endswith(("_wall", "_leaves")), (th["id"], v, x, z, t.get(x, 1, z))
            gate = t.get(8, 1, 1)
            assert _name(gate).endswith("_fence_gate") and "open=false" in gate, (th["id"], v, gate)
            assert t.jigsaws[0]["pos"] == (8, 0, 0)
