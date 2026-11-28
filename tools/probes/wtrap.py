"""Report of the terrain traps round a medium structure, on a saved world (issue #91).

The model is `tools/smoke/terrain_traps.py` (which says what a trap is and why the build's own audits cannot see
one); this only runs it over the box the settle check forceloads (+-ROAM blocks around the structure start, the only
ground the inhabitant can walk on while the test runs) and ranks every trap by the WALK into it: a trap 60 blocks away
is a curiosity, one 20 blocks from the bell is the bug.

Usage: wtrap.py <world> <start x> <start z> <inhabitant x> <y> <z> [roam]
       (HERALDIA pointing at the repository; no server and no .jar: it only reads region files)

The figure it gave on develop 7cfe5d2, seed `heraldia`, the dark-forest hermitage at -128, -1664, walked from the
cell beside the hermit's bed (-137, 71, -1676), which is the anchor `inhabitant_lost.py` uses: 1,314,951 blocks
read, 35,584 cells walked, 469 traps away from the box edge; the closest 34.1 blocks' walk (20.6 flat, 2 below) --
the lip of a natural cave shaft nine blocks east of the structure, 10 blocks deep, whose walls step down two and
three blocks at a time, and from which its search reaches 17 cells. Inside the structure and out to 32 blocks'
walk: none. Started from where the hermit happens to STAND instead (on his own lectern, say) the walk starts
somewhere else and the same terrain gives other numbers: anchor it at the bed.
"""
import os
import sys
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import terrain_traps as tt           # noqa: E402

ROAM = 80                            # medium_structures.ROAM: the blocks the settle check forceloads


def main():
    world, sx, sz = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    hx, hy, hz = (int(v) for v in sys.argv[4:7])
    roam = int(sys.argv[7]) if len(sys.argv) > 7 else ROAM
    box = (sx - roam, sz - roam, sx + roam - 1, sz + roam - 1)
    g, n = tt.ground(world, box[0], box[2], hy - 50, hy + 40, box[1], box[3])
    print(f"{n} blocks read in the forceloaded box {box}")
    start = tt.stand(g, hx, hy, hz)
    if start is None:
        raise SystemExit(f"the inhabitant's cell {(hx, hy, hz)} is not a cell it can stand in")
    beds = tt.beds(g)
    if not beds:
        raise SystemExit("no bed head in the box: are those the right coordinates?")
    dist, prev = tt.walk_from(g, start)
    print(f"the inhabitant walks to {len(dist)} cells from {start}; beds {beds}")
    found = tt.traps(g, start, beds, box)
    print(f"{len(found)} cells it walks to and its search cannot walk back to a bed from (box edge left out)")
    for cell, walk, straight, dy in found[:10]:
        route, p = [], cell
        while p:
            route.append(p)
            p = prev[p]
        route.reverse()
        sub = tt.reach(g, cell)
        print(f"  {cell}: walk {walk}, straight {straight}, dy {dy:+d}, standing on "
              f"{g.b.get((cell[0], cell[1] - 1, cell[2]))}")
        print("      last cells of the walk in: " + " -> ".join(f"{q[0]},{q[1]},{q[2]}" for q in route[-8:]))
        print(f"      from there its search reaches {len(sub)} cells (lowest y {min(q[1] for q in sub)})")
    for lim in (12, 16, 20, 24, 32, 40, 60):
        print(f"traps within {lim} blocks' walk of the inhabitant: {sum(1 for t in found if t[1] <= lim)}")


if __name__ == "__main__":
    main()
