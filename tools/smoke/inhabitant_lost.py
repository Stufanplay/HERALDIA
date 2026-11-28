"""An inhabitant of a medium structure that gets lost outside it comes home (issue #91), on a real 26.3 dedicated
server with the default configuration.

Usage: python3 tools/smoke/inhabitant_lost.py --jar build/libs/heraldia-X.jar [--work build/smoke-habitante-perdido]

The structure stands alone on the seed's real terrain, and a villager walks DOWN a drop of three blocks and climbs UP
at most 1.125: a hillside, a leaf canopy or an open cave shaft inside its day's stroll is a one-way street with no path
home out of it, and the templates are audited standing on flat ground, so no audit of the build sees it
(docs/LESSONS.md, "A villager gets by physics to places its path search cannot leave"). After 1,200 ticks unable to
reach a remembered block the game makes the villager release it, and the hermit then arrives at nightfall with neither
bed nor workstation -- which is what `medium_structures.py` saw once in 40 runs at -128, -1664.

What this test does, deterministically instead of once in 40:
- generates the hermitage `/locate` finds from 0, 0 on the test seed and lets its hermit claim his bed and his lectern,
  exactly as medium_structures.check_settled does;
- saves the world and FINDS, in the ground the test forceloads, the nearest cell the hermit can walk into and whose
  path search finds no way back to his bed (`tools/smoke/terrain_traps.py`). The trap is measured, not written down
  here, so the test does not quietly pass if the terrain of the seed ever changes: with no trap found it fails and says
  so;
- puts him in it at midday (the return control of `tools/bed_probe.py --ret`, on real terrain) and runs the day to
  nightfall, which is far more than the 1,200 ticks the game gives him;
- then he must be back inside the structure, with his bed, with his workstation and asleep, and the log must say
  Heraldia brought him home.
Exit code 0 if everything passes.
"""
import argparse, json, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import medium_structures as ms
import terrain_traps as tt

MID = "ermita"                       # the hermit: one inhabitant, one bed, one lectern, and the kind that was seen failing
FROM = (0, 0)                        # medium_structures.POINTS[0]: where the failing /locate was run from
BOX = 48                             # blocks around the structure read back from the saved world to look for the trap
MIN_WALK = 24.0                      # a trap closer than this would be the BUILD's fault (mediums/_paths.TRAP_WALK_MAX
                                     # is 25): this test is about the terrain, so it uses one further out than that
DAY_TICKS = 11000                    # medium_structures: from the morning (2000) to nightfall
HOME_BLOCKS = 10                     # blocks of his bed he must be within at nightfall (the chapel is 7 x 11)
_MEM = r"entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found|not found"


def settle(ctx, px, pz, sel, n):
    """The morning of medium_structures.check_settled: everyone takes their workstation."""
    ctx.run("time set 2000", r"Set the time|time to|Set minecraft:\w+ to")
    end = time.monotonic() + 120
    while with_mem(ctx, sel, "job_site") < n and time.monotonic() < end:
        time.sleep(3)
    return with_mem(ctx, sel, "job_site")


def with_mem(ctx, sel, mem):
    return ctx.count(f"{sel[:-1]},nbt={{Brain:{{memories:{{\"minecraft:{mem}\":{{}}}}}}}}]")


def memory(ctx, one, key):
    m = ctx.run(f"data get entity {one} Brain.memories.\"minecraft:{key}\".value.pos", _MEM)
    return tuple(int(v) for v in m.group(1, 2, 3)) if m.group(1) else None


def saved_ground(ctx, work, box, y0, y1, tries=4):
    """`save-all flush` and the box read back, repeated until every column of it is really in the region files.
    Reading a box one of whose chunks has not been saved yet gives the model a wall where there is ground, and then
    the traps it finds (and which one is the closest) change from run to run."""
    world = os.path.join(work, "world")
    want = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    for k in range(tries):
        ctx.must("save-all flush", r"Saved the game|saved|Saving")
        time.sleep(3)
        g, read = tt.ground(world, box[0], box[2], y0, y1, box[1], box[3])
        columns = len({(p[0], p[2]) for p in g.b})
        print(f"the saved world round the structure: {read} blocks, {columns} of {want} columns (try {k + 1})")
        if columns == want:
            return g, read
    raise SystemExit(f"only {columns} of {want} columns of the box {box} are in the region files after {tries} saves: "
                     f"the forceloaded area is not all generated")


def find_trap(ctx, work, px, pz, hermit, bed):
    """The nearest cell (by walk) the hermit can walk into and his search cannot walk back to his bed from."""
    hx, hy, hz = hermit
    box = (px - BOX, pz - BOX, px + BOX, pz + BOX)
    g, read = saved_ground(ctx, work, box, hy - 24, hy + 20)
    # the walk is measured from a cell BESIDE HIS BED, not from wherever he happens to be standing: on top of his own
    # lectern the model starts somewhere else and the same terrain gives another set of traps
    sides = tt.beside(g, bed)
    start = sides[0] if sides else None
    print(f"his bed is at {bed}, the walk starts beside it at {start} (he is standing in {tt.stand(g, hx, hy, hz)})")
    if start is None:
        return None, f"no cell beside the bed at {bed} that the model can walk from"
    found = [t for t in tt.traps(g, start, [bed], box) if t[1] >= MIN_WALK]
    for cell, walk, straight, dy in found[:5]:
        print(f"  trap {cell}: {walk} blocks' walk, {straight} straight, dy {dy:+d}, standing on "
              f"{g.b.get((cell[0], cell[1] - 1, cell[2]))}, its search reaches {len(tt.reach(g, cell))} cells from there")
    if not found:
        return None, (f"no cell within {BOX} blocks of {px}, {pz} that the hermit walks into and cannot walk back from "
                      f"(at least {MIN_WALK} blocks' walk): this test's premise is gone, measure the terrain again with "
                      f"tools/probes/wtrap.py")
    return found[0], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-habitante-perdido"))
    a = ap.parse_args()
    a.work, a.jar = os.path.abspath(a.work), os.path.abspath(a.jar)
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, a.jar, s.gradle_properties())
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump({}, f)                                   # the default configuration, as medium_structures.py
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen, fails = queue.Queue(), [], []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        ctx.run("gamerule spawn_mobs false", r"Gamerule|set to|now")
        m = ctx.run(f"execute positioned {FROM[0]} 64 {FROM[1]} run locate structure #heraldia:medianas/{MID}",
                    r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
        if not m.group(1):
            raise SystemExit(f"/locate does not find medianas/{MID} from {FROM}")
        px, pz = int(m.group(1)), int(m.group(2))
        print(f"{MID}: /locate from {FROM} gives {px}, {pz}")
        ms.forceload(ctx, px - ms.ROAM, pz - ms.ROAM, px + ms.ROAM - 1, pz + ms.ROAM - 1)
        if not ms.wait_generated(ctx, px, pz, MID):
            raise SystemExit(f"/locate gives {px}, {pz} but nothing has been generated there")
        sel = (f"@e[type=minecraft:villager,tag=heraldia_habitante,tag=heraldia_mediana.{MID},"
               f"x={px - 48},y=-64,z={pz - 48},dx=96,dy=420,dz=96]")
        if not ctx.wait_entity(sel, timeout=60):
            raise SystemExit(f"no inhabitant of medianas/{MID} at {px}, {pz}")
        if not ms.wait_loaded(ctx, px, pz, ms.ROAM):
            raise SystemExit(f"the forceloaded area round {px}, {pz} does not finish loading")
        one = sel[:-1] + ",limit=1]"
        n = ctx.count(sel)
        job = settle(ctx, px, pz, sel, n)
        bed, work_block = memory(ctx, one, "home"), memory(ctx, one, "job_site")
        print(f"{n} inhabitant(s), {job} with their workstation; bed {bed}, workstation {work_block}")
        if n != 1 or not bed or not work_block:
            raise SystemExit(f"the hermit does not start with his bed and his workstation: {n}, {bed}, {work_block}")
        here = ctx.pos(one)
        hermit = tuple(int(v // 1) for v in here)
        trap, why = find_trap(ctx, a.work, px, pz, hermit, bed)
        if why:
            raise SystemExit(why)
        cell, walk, straight, dy = trap
        ctx.must(f"tp {one} {cell[0] + 0.5} {cell[1]} {cell[2] + 0.5}", r"Teleported")
        print(f"the hermit is put at {cell}: {walk} blocks' walk from his bed, {straight} straight, {dy:+d} in height; "
              f"from there his search finds no way back to it")
        after = ctx.pos(one)
        if not after or max(abs(after[0] - cell[0] - 0.5), abs(after[2] - cell[2] - 0.5)) > 1.5:
            raise SystemExit(f"the teleport did not take: he is at {after}, not at {cell}")
        ms.sprint(ctx, DAY_TICKS)                          # the day to nightfall: well over the 1,200 ticks he is given
        end = time.monotonic() + 240                       # and a few real minutes at normal speed to get home and sleep
        while (with_mem(ctx, sel, "home") < n or with_mem(ctx, sel, "job_site") < n
               or with_mem(ctx, sel, "last_slept") < n) and time.monotonic() < end:
            time.sleep(3)
        home, work, slept = (with_mem(ctx, sel, k) for k in ("home", "job_site", "last_slept"))
        where = ctx.pos(one)
        # back home means back AT HIS BED, not merely inside the structure's chunk: the trap is only some twenty
        # blocks from it, so a box round the structure's start would hold the trap too
        near_bed = (f"@e[type=minecraft:villager,tag=heraldia_habitante,tag=heraldia_mediana.{MID},"
                    f"x={bed[0] - HOME_BLOCKS},y={bed[1] - HOME_BLOCKS},z={bed[2] - HOME_BLOCKS},"
                    f"dx={2 * HOME_BLOCKS},dy={2 * HOME_BLOCKS},dz={2 * HOME_BLOCKS}]")
        back = ctx.count(near_bed)
        print(f"after the day: {work} with their workstation, {home} with their bed, {slept} asleep, {back} within "
              f"{HOME_BLOCKS} blocks of his bed, at {where}")
        if home < n or work < n or slept < n:
            fails.append(f"{MID} at {px}, {pz}: put at {cell} ({walk} blocks' walk from his bed), of {n} inhabitants "
                         f"{work} took a workstation, {home} a bed and {slept} slept")
        if back < n:
            fails.append(f"{MID} at {px}, {pz}: the hermit is not back at his bed ({HOME_BLOCKS} blocks of {bed}): "
                         f"he is at {where}")
        if not re.search(r"Heraldia: habitante perdido a \d+ bloques", ctx.log()):
            fails.append("the log does not say Heraldia brought the lost inhabitant home")
        ms.forceload(ctx, px - ms.ROAM, pz - ms.ROAM, px + ms.ROAM - 1, pz + ms.ROAM - 1, remove=True)
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            proc.wait(timeout=120)
    print("HABITANTE PERDIDO:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
