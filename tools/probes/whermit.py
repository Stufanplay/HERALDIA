"""Do the inhabitants of ONE medium structure keep their bed and their workstation? (issue #91)

`tools/smoke/medium_structures.py`'s settle check (check_settled) on one kind only -- the structure `/locate` finds
from 0, 0 on the test seed (`heraldia`); with the default `--kind ermita` that is the dark-forest hermitage at
-128, -1664 -- run over and over on a fresh world each round, to measure how often it fails. One round is one new
world: the server is started, the structure is located, its chunks are forceloaded and waited for, and then exactly
what the smoke test does (morning, job_site; one night run with /tick sprint, home and last_slept; a second night if
the first fails).

Each round traces EVERY inhabitant of the structure while it happens -- position, bed, workstation and whether those
two are still BLOCKS, every TRACE_S seconds -- so a red round says where each of them was when it lost them, which the
smoke test's one-shot DIAG at the end cannot, and so that the distance they really stroll can be measured instead of
guessed. With a trace every 5 s and the clock running at 500-3,000 ticks a second that distance is badly
undersampled: use --trace-s 1 for it.

Usage: python3 tools/probes/whermit.py --jar build/libs/heraldia-0.1.0.jar --rounds 40 --out results.json
       [--kind ermita|posada|molino|pescador|cazadores|torre_vigia] [--days N] [--census] [--tp X Y Z]
       [--weather thunder] [--trace-s 1] [--work build/probe-ermita] [--keep-world]
       (Java 25 on the PATH, HERALDIA pointing at the repository)
Prints `ROUND k: ...` per round, `ROAM` per inhabitant, the trap census with --census, and the proportion at the end.
Exit code 0 whatever it measures: it is a probe, not a test (tools/test.py never discovers tools/probes).
"""
import argparse, json, math, os, queue, statistics, subprocess, sys, threading, time
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import server_smoke as s          # noqa: E402
import medium_structures as ms    # noqa: E402
import terrain_traps as tt        # noqa: E402

FROM = (0, 0)                     # medium_structures.POINTS[0]: the point the failing /locate was run from
TRACE_S = 5                       # seconds between trace lines (--trace-s). Under /tick sprint the clock runs some
                                  # 500-3,000 ticks a second, so 5 s of trace is minutes of game time: to measure how
                                  # far the hermit really gets, not just where he was now and then, use 0.5.
_MEM = r"entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found|not found"


CENSUS_BOX = 48                   # blocks round the start read back from the saved world for the trap census
_ITEM = r'entity data: "(?:minecraft:)?([a-z_]+)"|Found no elements|No entity was found'


def census(ctx, px, pz, r=48):
    """What is loose on the ground round the structure, and whether it is burning: a bed or a lectern lying there as an
    item says the BLOCK was destroyed and dropped, not that the hermit could not walk to it. The two readings tell
    apart "it lost its way" from "it lost the block"."""
    box = f"x={px - r},y=-64,z={pz - r},dx={2 * r},dy=420,dz={2 * r}"
    n = ctx.count(f"@e[type=minecraft:item,{box}]")
    ids = []
    for k in range(min(n, 12)):
        ctx.run(f"tag @e[type=minecraft:item,{box},tag=!whermit_seen,limit=1] add whermit{k}", r"Added tag|Could not|No entity")
        one = f"@e[tag=whermit{k},limit=1]"
        ctx.run(f"tag {one} add whermit_seen", r"Added tag|Could not|No entity")
        m = ctx.run(f"data get entity {one} Item.id", _ITEM)
        ids.append(m.group(1) or "?")
        ctx.run(f"tag {one} remove whermit{k}", r"Removed tag|Could not|No entity")
    ctx.run(f"tag @e[{box},tag=whermit_seen] remove whermit_seen", r"Removed tag|Could not|No entity")
    return dict(items=n, item_ids=ids)


def memories(ctx, one):
    """{home, job_site, last_slept}: the bed and workstation the hermit remembers, and whether he has slept."""
    out = {}
    for key in ("home", "job_site"):
        m = ctx.run(f"data get entity {one} Brain.memories.\"minecraft:{key}\".value.pos", _MEM)
        out[key] = [int(v) for v in m.group(1, 2, 3)] if m.group(1) else None
    out["slept"] = ctx.count(f"{one[:-1]},nbt={{Brain:{{memories:{{\"minecraft:last_slept\":{{}}}}}}}}]") > 0
    return out


def name_them(ctx, sel, n):
    """Tags each inhabitant `whermit.N` so that every one of them has a selector of its own that survives the whole
    round (medium_structures.diagnose_settled does the same to name them in a red run). Returns [(selector,
    profession)]."""
    out = []
    for k in range(n):
        ctx.run(f"tag {sel[:-1]},tag=!whermit.named,limit=1] add whermit.{k}", r"Added tag|Could not|No entity")
        one = f"@e[tag=whermit.{k},limit=1]"
        ctx.run(f"tag {one} add whermit.named", r"Added tag|Could not|No entity")
        m = ctx.run(f"data get entity {one} VillagerData.profession",
                    r'entity data: "(?:minecraft:)?([a-z_]+)"|No entity|not found')
        out.append((one, (m.group(1) if m.lastindex and m.group(1) else "?")))
    return out


def trace(ctx, who, log, label, seen=None):
    """One line of the trace PER INHABITANT: where it is, what it remembers, and -- once its bed and its workstation
    have been seen once -- whether those two BLOCKS are still in the world. Losing the memory and losing the block are
    two different bugs and only that second reading tells them apart."""
    t = ctx.gametime()
    rows = []
    for i, (one, prof) in enumerate(who):
        p = ctx.pos(one)
        mem = memories(ctx, one)
        row = dict(label=label, gametime=t, who=i, profession=prof,
                   pos=[round(v, 1) for v in p] if p else None,
                   home=mem["home"], job=mem["job_site"], slept=mem["slept"])
        if seen is not None:
            # the bed is read as a bed; a workstation is whatever the kind uses (lectern, barrel, composter,
            # fletching table...), so it is enough that the cell is not air
            for key in ("home", "job_site"):
                if mem[key] and (i, key) not in seen:
                    seen[(i, key)] = mem[key]
                if (i, key) in seen:
                    row[key + "_block"] = ctx.block(seen[(i, key)], "#minecraft:beds") if key == "home" \
                        else not ctx.block(seen[(i, key)], "minecraft:air")
        log.append(row)
        print(f"  TRACE {label} t={t} {prof}#{i} at {row['pos']} home={row['home']} job={row['job']} "
              f"slept={row['slept']} bed_block={row.get('home_block')} job_block={row.get('job_site_block')}",
              flush=True)
        rows.append(row)
    return rows


def wait_traced(ctx, who, log, label, ready, timeout, seen=None):
    """Waits for `ready()` while tracing every TRACE_S seconds. True if it was met."""
    end = time.monotonic() + timeout
    while True:
        if ready():
            return True
        if time.monotonic() > end:
            return False
        trace(ctx, who, log, label, seen)
        time.sleep(TRACE_S)


def sprint_traced(ctx, who, log, ticks, seen=None):
    """ms.sprint, tracing while the clock runs (commands still answer during /tick sprint)."""
    t0 = ctx.gametime()
    end = time.monotonic() + 900
    while ctx.gametime() < t0 + ticks and time.monotonic() < end:
        step = min(ms.SPRINT_STEP, t0 + ticks - ctx.gametime())
        t1 = ctx.gametime()
        s.send(ctx.proc, f"tick sprint {step}")
        while ctx.gametime() < t1 + step and time.monotonic() < end:
            trace(ctx, who, log, "sprint", seen)
            time.sleep(TRACE_S)
    return ctx.gametime() - t0


def one_round(ctx, k, a):
    """The smoke test's check on the hermitage alone. Returns the round's record."""
    mid = a.kind
    r = dict(round=k, kind=mid, locate=None, n=0, job=0, home=0, slept=0, nights=0, fail=None, trace=[])
    m = ctx.run(f"execute positioned {FROM[0]} 64 {FROM[1]} run locate structure #heraldia:medianas/{mid}",
                r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
    if not m.group(1):
        r["fail"] = f"/locate does not find medianas/{mid}"
        return r
    px, pz = int(m.group(1)), int(m.group(2))
    r["locate"] = [px, pz]
    ms.forceload(ctx, px - ms.ROAM, pz - ms.ROAM, px + ms.ROAM - 1, pz + ms.ROAM - 1)
    if not ms.wait_generated(ctx, px, pz, mid):
        r["fail"] = f"/locate gives {px}, {pz} but nothing has been generated there"
        return r
    sel = (f"@e[type=minecraft:villager,tag=heraldia_habitante,tag=heraldia_mediana.{mid},"
           f"x={px - 48},y=-64,z={pz - 48},dx=96,dy=420,dz=96]")
    if not ctx.until(f"execute if entity {sel}", timeout=20):
        r["fail"] = "no inhabitant (the smoke test would call this a variant without inhabitants)"
        return r
    r["loaded"] = ms.wait_loaded(ctx, px, pz, ms.ROAM)
    n = r["n"] = ctx.count(sel)
    who = name_them(ctx, sel, n)
    r["who"] = [prof for _, prof in who]
    with_mem = lambda mem: ctx.count(f"{sel[:-1]},nbt={{Brain:{{memories:{{\"minecraft:{mem}\":{{}}}}}}}}]")
    seen = {}
    trace(ctx, who, r["trace"], "generated", seen)
    if a.weather:
        # --weather thunder: the control. In a fresh world no bolt can fall before tick 12,000 (thunderTime starts
        # between 12,000 and 180,000), so a short round cannot show a fire even if fire is the cause.
        ctx.run(f"weather {a.weather} 1000000", r"[Cc]hanging the weather|thunder|rain|clear")
    if a.warm:
        sprint_traced(ctx, who, r["trace"], a.warm, seen)
    ctx.run("time set 2000", r"Set the time|time to|Set minecraft:\w+ to")
    wait_traced(ctx, who, r["trace"], "morning", lambda: with_mem("job_site") >= n, 120, seen)
    r["job"] = with_mem("job_site")
    trace(ctx, who, r["trace"], "noon", seen)
    if a.tp:
        # The return control (tools/bed_probe.py --ret, on the seed's real terrain instead of a flat platform): with
        # his bed and his lectern already claimed, put him at midday where the terrain model says his search has no
        # way back from, and let the day run to nightfall. That is more than the 1,200 ticks the game gives a villager
        # to reach a remembered block, so if the model is right he arrives at the night check with neither.
        x, y, z = a.tp
        m = ctx.run(f"tp {who[0][0]} {x + 0.5} {y} {z + 0.5}", r"Teleported|No entity|not loaded")
        r["tp"] = [x, y, z]
        r["tp_reply"] = m.group(0).strip()
        trace(ctx, who, r["trace"], "teleported", seen)
    sprint_traced(ctx, who, r["trace"], a.night_ticks, seen)
    nights = 0
    while True:
        nights += 1
        wait_traced(ctx, who, r["trace"], f"night{nights}",
                    lambda: with_mem("home") >= n and with_mem("last_slept") >= n, 150, seen)
        r["home"], r["slept"] = with_mem("home"), with_mem("last_slept")
        if (r["home"] == n and r["slept"] == n) or nights == 2:
            break
        sprint_traced(ctx, who, r["trace"], 24000, seen)
    r["nights"] = nights
    r["days"] = []
    for day in range(a.days):
        sprint_traced(ctx, who, r["trace"], 24000, seen)
        wait_traced(ctx, who, r["trace"], f"day{day + 2}",
                    lambda: with_mem("home") >= n and with_mem("job_site") >= n and with_mem("last_slept") >= n, 150,
                    seen)
        row = dict(day=day + 2, job=with_mem("job_site"), home=with_mem("home"), slept=with_mem("last_slept"),
                   pos=[[round(v, 1) for v in (ctx.pos(o) or (0, 0, 0))] for o, _ in who])
        r["days"].append(row)
        print(f"  DAY {row['day']}: job {row['job']}, home {row['home']}, slept {row['slept']}, at {row['pos']}",
              flush=True)
        if row["job"] < n or row["home"] < n:
            r["lost_on_day"] = row["day"]
            break
    r["job"] = with_mem("job_site")              # re-read at the end, as check_stay does: he may have given it up
    end_rows = trace(ctx, who, r["trace"], "end", seen)
    r["beds_seen"] = [seen.get((i, "home")) for i in range(n)]
    r["jobs_seen"] = [seen.get((i, "job_site")) for i in range(n)]
    r["bed_block_end"] = all(row.get("home_block") for row in end_rows)
    r["job_block_end"] = all(row.get("job_site_block") for row in end_rows)
    r["ground"] = census(ctx, px, pz)
    print(f"  GROUND {r['ground']}", flush=True)
    if r["job"] < n or r["home"] < n or r["slept"] < n:
        r["fail"] = (f"{mid} at {px}, {pz}: of {n} inhabitants, {r['job']} took a workstation, {r['home']} a bed and "
                     f"{r['slept']} slept")
        if r.get("lost_on_day"):
            r["fail"] += f" (on day {r['lost_on_day']} of {a.days + 1})"
    r["roam"] = roam(r)
    for row in r["roam"]:
        print(f"  ROAM {row['profession']}#{row['who']}: {row['samples']} samples, farthest {row['max']} flat blocks "
              f"from its bed at {row['bed']}, median of the samples {row['median']}", flush=True)
    if a.census:
        r["traps"] = trap_census(ctx, a.work, px, pz, r)
    ms.forceload(ctx, px - ms.ROAM, pz - ms.ROAM, px + ms.ROAM - 1, pz + ms.ROAM - 1, remove=True)
    return r


def roam(r):
    """How far each inhabitant really got from its own bed, flat, over the round's trace. Flat because that is how
    `mediums/_paths.trap_walk` measures its own reach, so the two figures can be compared."""
    out = []
    for i, prof in enumerate(r.get("who", [])):
        bed = next((row["home"] for row in r["trace"] if row["who"] == i and row["home"]), None)
        ds = [math.hypot(row["pos"][0] - bed[0], row["pos"][2] - bed[2])
              for row in r["trace"] if row["who"] == i and row.get("pos") and bed]
        out.append(dict(who=i, profession=prof, bed=bed, samples=len(ds),
                        max=round(max(ds), 1) if ds else None,
                        median=round(statistics.median(ds), 1) if ds else None))
    return out


def trap_census(ctx, work, px, pz, r):
    """--census: the one-way traps of the REAL terrain round this structure (tools/smoke/terrain_traps.py), walked
    from the cell beside each inhabitant's bed, inside the box the settle check forceloads. Saves the world first and
    repeats the save until every column of the box is really in the region files: a box one of whose chunks has not
    been saved gives the model a wall where there is ground."""
    box = (px - CENSUS_BOX, pz - CENSUS_BOX, px + CENSUS_BOX, pz + CENSUS_BOX)
    want = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    beds = [b for b in r.get("beds_seen", []) if b]
    if not beds:
        return dict(error="no inhabitant ever claimed a bed: nothing to walk back to")
    y = beds[0][1]
    for attempt in range(4):
        ctx.must("save-all flush", r"Saved the game|saved|Saving")
        time.sleep(3)
        g, read = tt.ground(os.path.join(work, "world"), box[0], box[2], y - 24, y + 20, box[1], box[3])
        columns = len({(p[0], p[2]) for p in g.b})
        if columns == want:
            break
    else:
        return dict(error=f"only {columns} of {want} columns of {box} are saved after 4 flushes")
    out = dict(blocks=read, columns=columns, box=list(box), per_bed=[])
    for i, bed in enumerate(r.get("beds_seen", [])):
        if not bed:
            out["per_bed"].append(dict(who=i, error="never claimed a bed"))
            continue
        sides = tt.beside(g, tuple(bed))
        if not sides:
            out["per_bed"].append(dict(who=i, bed=bed, error="no standable cell beside the bed"))
            continue
        found = tt.traps(g, sides[0], [tuple(bed)], box)
        walked = len(tt.walk_from(g, sides[0])[0])
        row = dict(who=i, bed=bed, start=list(sides[0]), walked=walked, traps=len(found),
                   nearest=(dict(cell=list(found[0][0]), walk=found[0][1], flat=found[0][2], dy=found[0][3],
                                 search_reaches=len(tt.reach(g, found[0][0]))) if found else None),
                   within={str(lim): sum(1 for t in found if t[1] <= lim) for lim in (16, 24, 32, 40, 60)})
        out["per_bed"].append(row)
        print(f"  TRAPS bed {bed}: {walked} cells walked, {len(found)} with no way back; nearest "
              f"{row['nearest']}", flush=True)
    return out


def main():
    global TRACE_S
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--rounds", type=int, default=40)
    ap.add_argument("--kind", default="ermita",
                    help="the medium structure kind to measure (medium_structures.INHABITED: ermita, posada, molino, "
                         "pescador, cazadores, torre_vigia). /locate finds it from 0, 0, as the smoke test does.")
    ap.add_argument("--census", action="store_true",
                    help="after the round, the one-way traps of the real terrain round the structure, walked from "
                         "beside each inhabitant's bed (tools/smoke/terrain_traps.py)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default=os.path.join(ROOT, "build", "probe-ermita"))
    ap.add_argument("--keep-world", action="store_true", help="keep the world of a failing round (build/probe-ermita/world-N)")
    ap.add_argument("--trace-s", type=float, default=TRACE_S, help="seconds between trace lines (see TRACE_S)")
    ap.add_argument("--weather", choices=["clear", "rain", "thunder"], default=None,
                    help="force the weather right after the structure is generated (the control: thunder is what a bolt needs)")
    ap.add_argument("--warm", type=int, default=0,
                    help="game ticks run before the morning, so the round sees the same clock the full battery reaches")
    ap.add_argument("--night-ticks", type=int, default=11000, help="ticks from the morning to nightfall (the smoke test's 11,000)")
    ap.add_argument("--days", type=int, default=0,
                    help="after the smoke test's own night, run this many more in-game days and read the hermit every "
                         "nightfall. One round is then several inhabitant-days for the price of one world, which is "
                         "how check_stay and the figures in docs/LESSONS.md are measured. A round is red at the first "
                         "night he arrives without his bed or without his workstation.")
    ap.add_argument("--tp", nargs=3, type=int, default=None, metavar=("X", "Y", "Z"),
                    help="the return control (tools/bed_probe.py --ret): once he has claimed his bed and his lectern, "
                         "put him in this cell at nightfall and watch whether he gets home. The cell is given in world "
                         "coordinates, so it is tied to the seed; -118 67 -1666 is the lip of the hole east of the "
                         "hermitage at -128, -1664.")
    a = ap.parse_args()
    a.work, a.jar, a.out = os.path.abspath(a.work), os.path.abspath(a.jar), os.path.abspath(a.out)
    TRACE_S = a.trace_s
    os.makedirs(a.work, exist_ok=True)
    results = []
    for k in range(1, a.rounds + 1):
        t0 = time.monotonic()
        launcher = s.prepare(a.work, a.jar, s.gradle_properties())      # a fresh world every round
        with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
            json.dump({}, f)                                            # the default configuration, as the smoke test
        proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines, seen = queue.Queue(), []

        def rd(p=proc, q=lines):
            with open(os.path.join(a.work, f"console-{k}.txt"), "w") as f:
                for line in p.stdout:
                    f.write(line)
                    q.put(line)
            q.put(None)
        threading.Thread(target=rd, daemon=True).start()
        ctx = s.Context(proc, lines, seen)
        r = dict(round=k, fail="the server did not start")
        try:
            s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
            ctx.run("gamerule spawn_mobs false", r"Gamerule|set to|now")
            r = one_round(ctx, k, a)
        finally:
            if proc.poll() is None:
                s.send(proc, "stop")
                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
        r["seconds"] = round(time.monotonic() - t0)
        results.append(r)
        json.dump(results, open(a.out, "w"), indent=1)
        bad = sum(1 for x in results if x["fail"])
        print(f"ROUND {k}: {'FAIL: ' + r['fail'] if r['fail'] else 'ok'} "
              f"(locate {r.get('locate')}, {r.get('n')} inhabitants, job {r.get('job')}, home {r.get('home')}, "
              f"slept {r.get('slept')}, night {r.get('nights')}, {r['seconds']} s) -- {bad} of {len(results)} red",
              flush=True)
        if r["fail"] and a.keep_world:
            os.rename(os.path.join(a.work, "world"), os.path.join(a.work, f"world-{k}"))
    bad = [r for r in results if r["fail"]]
    print(f"PROBE ERMITA: {len(bad)} of {len(results)} rounds red")
    for r in bad:
        print("  ", r["round"], r["fail"])


if __name__ == "__main__":
    main()
