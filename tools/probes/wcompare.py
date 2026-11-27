"""Two saved worlds of wlayout.py compared block by block over the box of each of the 8 villages of village_routes:
how many blocks differ, and what each difference is (state in A -> state in B), counted.

Usage: wcompare.py <world A> <world B>   (HERALDIA pointing at the repository)
"""
import collections, os, sys
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import saved_world
import village_routes as vr


def main():
    a, b = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    R = vr.RADIUS
    total, diff, kinds, where = 0, 0, collections.Counter(), []
    for sid, x, z in vr.SITES:
        ba = saved_world.blocks(a, x - R, x + R - 1, -64, 80, z - R, z + R - 1)
        bb = saved_world.blocks(b, x - R, x + R - 1, -64, 80, z - R, z + R - 1)
        keys = set(ba) | set(bb)
        total += len(keys)
        n = 0
        for k in keys:
            sa, sb = ba.get(k, "minecraft:air"), bb.get(k, "minecraft:air")
            if sa != sb:
                n += 1
                kinds[(sa, sb)] += 1
                where.append((sid, k))
        diff += n
        print(f"{sid}: {len(keys)} blocks, {n} differ", flush=True)
    print(f"TOTAL: {diff} of {total} non-air blocks differ")
    for (sa, sb), c in kinds.most_common():
        print(f"  {c:5d}  {sa} -> {sb}")


if __name__ == "__main__":
    main()
