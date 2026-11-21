"""Villager routes on a real dedicated 26.3 server: do the villagers of a Heraldia village walk around it during the day?

Usage: python3 tools/smoke/village_routes.py --jar build/libs/heraldia-X.jar --work build/smoke [--measure] [--sites N]
       [--terrain | --natural N [--seed S]] [--structures ID,...] [--verbose] [--fault bells]
Places several villages (different styles, standard and large) with /place structure on a superflat world (--terrain:
on the seed's terrain, whose hills and lakes cut some paths, at fixed coordinates whatever the biome: the worst case;
--natural N: the N villages the game places closest to the origin, naturally generated with its terrain adaptation and
its trees, the figure of how villages fit the terrain; --structures: other villages at the SITES' coordinates, e.g. the
styles --natural found, on a flat world as their reference), far enough apart not to share villagers, and lets one
in-game day pass at an accelerated tick rate (/tick rate) with the village chunks forced. Vanilla villager AI does the
rest: each villager claims a bed (home), a workstation of its profession (job site) and a bell (meeting point) within 48
blocks, and its schedule sends it to the job site in the morning, to the bell at midday and to bed at night. Every
sample reads each villager's position and whether it sleeps and, at the end, its brain memories.

Per village and in total it counts:
- moving: villagers whose positions during the day span 8 blocks or more (the rest are "still");
- commuting: those whose working position (mean of the work samples) is 12 blocks or more from their night position;
- sleeping: those asleep in a bed in the last night sample;
- home and job site memories and their distance (and how many work under 6 blocks from their bed); bell claimed.
It fails (unless --measure, which only prints the table, e.g. to compare with an earlier .jar) when a total is below
its MIN_* limit or above MAX_SAME_HOUSE, and prints every figure's margin over its limit, in villagers, pass or fail.
The heaviest part is the simulated day (14,000 ticks): about 3 minutes on 4 cores with the 8 villages.

--fault bells takes every bell away before the day starts: the proof that the check can fail (no villager can claim a
meeting point, so that figure must drop to 0 and the test must fail). Never part of a normal run.
"""
import argparse, json, math, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

# (structure, x, z): one style of each house shape (rectangular, round, stilts, long) and large villages. All of them are
# placed by default (CI): the limits below are fractions of THIS sample. The first three are the worst ones (those where
# the placement before this test left most villagers still: the large snowy village, the desert one with its workshops
# next to the beds, and a long-house one): --sites 3 places only them, a quicker look at the hard cases, NOT a sample
# the limits apply to. CI ran those three against the limits of the eight until Nov 2026: 37 villagers whose figures
# sit on the limits (bell 22-30 against 25, moving 31-35 against 32), red about four runs in ten with nothing wrong.
SITES = [("heraldia:nieve_alpina_grande", 600, -600), ("heraldia:desierto_obelisco", -600, 0),
         ("heraldia:taiga_nordica", 600, 0), ("heraldia:llanuras_castellana", 0, 0),
         ("heraldia:sabana_paja", 0, 600), ("heraldia:pantano_palafitos", 600, 600),
         ("heraldia:cerezos_japonesa", 0, -600), ("heraldia:llanuras_castellana_grande", -600, -600)]
DEFAULT_SITES = len(SITES)
RADIUS = 120            # forced box around each village (16 x 16 chunks, the forceload limit) and villager search radius
TICK_RATE = 200         # /tick rate during the simulated day (the server goes as fast as it can if it does not keep up)
SETTLE_UNTIL = 1500     # day time until which the villagers claim their bed, job site and bell (no sample)
WORK = (3000, 4500, 6000, 7500)          # day times of the work samples (the schedule's WORK runs 2000-9000)
MEET = (9800, 10600)                     # MEET runs 9000-11000: gathering at the bell
NIGHT = (13000, 14000)                   # REST from 12000: in bed
MOVE_SPAN, COMMUTE = 8, 12              # blocks
# Limits of the check (fractions of the villagers). Measured on a superflat world with the 8 SITES (107 villagers):
# before the route placement 0.77 moving, 0.26 commuting, 0.72 asleep, 0.53 with a bell and 0.28 working under 6 blocks
# from their bed; after, 0.91, 0.53, 0.67, 0.77 and 0.14. Thirteen runs in Nov 2026, all passing: moving 93-101 of 107
# (limit 91), commuting 50-58 (43), asleep 65-74 (54), with a bell 77-87 (70), under 6 blocks 9-14 (at most 21).
# "Moving" is the tight one: its worst runs passed by 2 and 3 villagers.
MIN_MOVING, MIN_COMMUTE, MIN_SLEEP, MIN_MEETING, MAX_SAME_HOUSE = 0.85, 0.4, 0.5, 0.65, 0.2
_ARR = r"\[I; (-?\d+), (-?\d+), (-?\d+), (-?\d+)\]"
_NUM = r"(-?[\d.]+(?:E-?\d+)?)d"


def uuid_of(ints):
    h = "".join(f"{(int(i) & 0xffffffff):08x}" for i in ints)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def collect(ctx, cmd, pattern, n, timeout=s.COMMAND_TIMEOUT_S):
    """Sends a command that answers with n lines (execute as ...) and returns the n matches of `pattern`."""
    s.pending(ctx.lines, ctx.seen)
    s.send(ctx.proc, cmd)
    return [s.wait_for(ctx.lines, pattern, timeout, ctx.seen) for _ in range(n)]


def place(ctx, sid, x, z):
    for x0, x1 in ((x - RADIUS, x - 1), (x, x + RADIUS - 1)):
        ctx.run(f"forceload add {x0} {z - RADIUS} {x1} {z + RADIUS - 1}", r"Marked|Added|force|already")
    for _ in range(s.PLACE_ATTEMPTS):
        m = ctx.run(f"place structure {sid} {x} ~ {z}", r"Generated structure")
        if "not loaded" not in m.group(0):
            return "Generated" in m.group(0)
        time.sleep(s.PLACE_RETRY_S)
    return False


# --natural: villages of a real world, generated as in normal play (with the game's own terrain adaptation, which
# /place leaves out): the minimum grid (aldeas.separacion_bloques), half of them large, searched with /locate around the
# origin.
NATURAL_GRID = 1000
# Only the villages: no roads, caravans, wayfarers or medium structures, whose villagers are not the village's.
NATURAL_CONFIG = {"aldeas": {"separacion_bloques": NATURAL_GRID, "maximo": 100, "porcentaje_grandes": 50,
                             "caminos": {"activado": False}},
                  "caravanas": {"activado": False}, "viajeros": {"activado": False}, "medianas": {"activadas": False}}


def natural_sites(ctx, n):
    """The n villages of the world closest to 0, 0 (structure, x, z), searched from a mesh of points with /locate."""
    found = {}
    r = 3 * NATURAL_GRID
    pts = sorted(((x, z) for x in range(-r, r + 1, NATURAL_GRID) for z in range(-r, r + 1, NATURAL_GRID)),
                 key=lambda p: (p[0] ** 2 + p[1] ** 2, p))
    for x, z in pts:
        m = ctx.run(f"execute positioned {x} 100 {z} run locate structure #heraldia:aldeas",
                    r"The nearest \S+ \((\S+)\) is at \[(-?\d+), ~, (-?\d+)\]|Could not find")
        if m.group(1):
            found.setdefault((int(m.group(2)), int(m.group(3))), m.group(1))
        if len(found) >= n:
            break
    return [(sid, x, z) for (x, z), sid in sorted(found.items(), key=lambda kv: kv[0][0] ** 2 + kv[0][1] ** 2)][:n]


def load(ctx, x, z):
    """Forces the box around (x, z) and waits until its chunks are generated (natural generation)."""
    for x0, x1 in ((x - RADIUS, x - 1), (x, x + RADIUS - 1)):
        ctx.run(f"forceload add {x0} {z - RADIUS} {x1} {z + RADIUS - 1}", r"Marked|Added|force|already")
    for cx, cz in ((x - RADIUS, z - RADIUS), (x + RADIUS - 1, z + RADIUS - 1), (x, z)):
        if not ctx.until(f"execute if loaded {cx} 0 {cz}", timeout=900):
            return False
    return True


def villagers(ctx, x, z):
    """UUIDs of the villagers with AI around (x, z) (not the bailiff of the job board, who has NoAI)."""
    sel = f"@e[type=villager,x={x - RADIUS},y=-64,z={z - RADIUS},dx={2 * RADIUS},dy=400,dz={2 * RADIUS},nbt=!{{NoAI:1b}}]"
    n = ctx.count(sel)
    if not n:
        return []
    ms = collect(ctx, f"execute as {sel} run data get entity @s UUID", rf"has the following entity data: {_ARR}", n)
    return [uuid_of(m.groups()) for m in ms]


def read(ctx, u):
    """(position, asleep) of a villager, or None if it no longer exists."""
    m = ctx.run(f"data get entity {u} Pos", rf"has the following entity data: \[{_NUM}, {_NUM}, {_NUM}\]|No entity was found")
    if not m.group(1):
        return None
    pos = tuple(float(v) for v in m.groups())
    sl = ctx.run(f"data get entity {u} sleeping_pos", r"has the following entity data: \[I;|Found no elements|No entity was found")
    return pos, "has the following" in sl.group(0)


def memories(ctx, u):
    """{memory: (x, y, z)} of home, job_site and meeting_point (those it has)."""
    out = {}
    for mem in ("home", "job_site", "meeting_point"):
        m = ctx.run(f'data get entity {u} Brain.memories."minecraft:{mem}".value.pos',
                    r"has the following entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found")
        if m.group(1):
            out[mem] = tuple(int(v) for v in m.groups())
    return out


def wait_daytime(ctx, target, start):
    """Waits until the day time reaches `target`. In 26.3 `/time query daytime` no longer exists (the day is a timeline
    clock): the world clock was set to 0 with time stopped and runs since `start` (the game time then), one tick per tick.
    Returns the day time reached."""
    end = time.monotonic() + 3600
    while time.monotonic() < end:
        now = ctx.gametime() - start
        if now >= target:
            return now
        time.sleep(1)
    raise SystemExit(f"the server does not reach day time {target}")


def hdist(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def mean(ps):
    return tuple(sum(p[i] for p in ps) / len(ps) for i in range(3))


def analyse(samples, mem):
    """Figures of one villager from its samples {day time: (pos, asleep)} and its memories."""
    ps = [p for p, _ in samples.values()]
    span = max((hdist(a, b) for a in ps for b in ps), default=0)
    work = [samples[t][0] for t in WORK if t in samples]
    night = [samples[t] for t in NIGHT if t in samples]
    night_pos = [p for p, _ in night]
    commute = hdist(mean(work), mean(night_pos)) if work and night_pos else 0
    home, job = mem.get("home"), mem.get("job_site")
    return dict(moving=span >= MOVE_SPAN, span=span, commute=commute >= COMMUTE, commute_d=commute,
                sleeping=bool(night) and night[-1][1], home=home is not None, job=job is not None,
                meeting=mem.get("meeting_point") is not None,
                home_job=hdist(home, job) if home and job else None)


def summary(rows):
    n = len(rows)
    hj = [r["home_job"] for r in rows if r["home_job"] is not None]
    c = lambda k: sum(1 for r in rows if r[k])
    return dict(n=n, moving=c("moving"), still=n - c("moving"), commute=c("commute"), sleeping=c("sleeping"),
                home=c("home"), job=c("job"), meeting=c("meeting"),
                home_job=(sum(hj) / len(hj)) if hj else 0, same_house=sum(1 for d in hj if d < 6))


def line(name, r):
    return (f"{name:42s} {r['n']:3d} villagers: {r['moving']:3d} move, {r['still']:3d} still, {r['commute']:3d} commute, "
            f"{r['sleeping']:3d} sleep at night | home {r['home']}, job site {r['job']} (home-job {r['home_job']:.1f} blocks, "
            f"{r['same_house']} under 6), bell {r['meeting']}")


def limits(n):
    """[(figure, limit in villagers, True if it is a minimum)] for n villagers: the same comparisons the check makes."""
    return [(k, math.ceil(lim * n), True) for k, lim in (("moving", MIN_MOVING), ("commute", MIN_COMMUTE),
                                                          ("sleeping", MIN_SLEEP), ("meeting", MIN_MEETING))] \
        + [("same_house", math.floor(MAX_SAME_HOUSE * n), False)]


SHUT_R, SHUT_FAR = 24, 12      # blocks read around a villager; how far its search must get for it not to be shut in


def shut_in(world_dir, pos):
    """Is the villager at `pos` somewhere its path search cannot walk out of (a loft reached only by a ladder, a fenced
    garden with its gate shut)? Read from the saved world: from its cell, the cells its search reaches (the generator's
    model of the 26.3 search, mediums/_paths: no ladders, drops of 3 at most); shut in if none is SHUT_FAR blocks away.
    On a slope or upstairs by a staircase it reaches the whole village: not shut in, however high it stands."""
    import saved_world
    sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
    import lint
    from mediums import _paths
    x, y, z = pos
    bx, bz, by = int(math.floor(x)), int(math.floor(z)), int(math.floor(y))
    b = saved_world.blocks(world_dir, bx - SHUT_R, bx + SHUT_R, by - 30, by + 10, bz - SHUT_R, bz + SHUT_R)
    g = _paths.Ground.__new__(_paths.Ground)
    g.lint, g._floor, g._nb = lint, {}, {}
    g.b = {p: st for p, st in b.items() if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
    g.box = (bx - SHUT_R, bz - SHUT_R, bx + SHUT_R + 1, bz + SHUT_R + 1)
    starts = [(cx, cy, cz) for cx in (bx - 1, bx, bx + 1) for cz in (bz - 1, bz, bz + 1)
              for cy in range(by - 3, by + 2) if g.floor(cx, cy, cz) is not None]
    if not starts:
        return True                                   # no floor under it: in a ladder shaft
    start = min(starts, key=lambda c: (abs(c[0] + 0.5 - x) + abs(c[2] + 0.5 - z), abs(g.floor(*c) - y)))
    seen, todo = {start}, [start]
    while todo:
        n = todo.pop()
        if math.hypot(n[0] - start[0], n[2] - start[2]) >= SHUT_FAR:
            return False
        for m in g.neighbors(n):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return True


def remove_bells(ctx, sites):
    """--fault bells: every bell of the placed villages becomes air."""
    ctx.run("gamerule max_block_modifications 4000000", r"Gamerule|set|now")
    gone = 0
    for _, x, z in sites:
        for x0, x1 in ((x - RADIUS, x - 1), (x, x + RADIUS - 1)):
            m = ctx.run(f"fill {x0} -64 {z - RADIUS} {x1} 0 {z + RADIUS - 1} air replace bell",
                        r"Successfully filled (\d+) block|No blocks were filled")
            gone += int(m.group(1) or 0)
    return gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke"))
    ap.add_argument("--measure", action="store_true", help="only print the figures, without failing")
    ap.add_argument("--terrain", action="store_true",
                    help="the seed's terrain instead of a superflat world (its hills and lakes cut some paths: fewer "
                         "villagers find a bed; the default measures the placement alone)")
    ap.add_argument("--natural", type=int, default=0, metavar="N",
                    help="instead of /place, the N villages of the seed's world closest to the origin, generated naturally")
    ap.add_argument("--verbose", action="store_true", help="also print each villager's first and last sample and memories")
    ap.add_argument("--seed", default=None, help="world seed (default: the tests' seed)")
    ap.add_argument("--structures", default=None, metavar="ID,ID,...",
                    help="place these villages (at the SITES' coordinates) instead of the SITES' own: e.g. the styles that "
                         "--natural found, on a flat world, as their reference")
    ap.add_argument("--sites", type=int, default=DEFAULT_SITES, help=f"how many of the SITES to place (up to {len(SITES)})")
    ap.add_argument("--fault", choices=["bells"], default=None,
                    help="inject a real fault to prove the check fails: 'bells' removes every bell (flat world only)")
    a = ap.parse_args()
    if a.fault and (a.terrain or a.natural):
        ap.error("--fault only on the flat world (the bells are searched between y -64 and 0)")
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    if a.natural:
        cfg_path = os.path.join(a.work, "config", "heraldia.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        for k, v in NATURAL_CONFIG.items():
            cfg[k] = {**cfg.get(k, {}), **v}
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)
    if a.seed:
        props = os.path.join(a.work, "server.properties")
        with open(props) as f:
            text = re.sub(r"level-seed=.*", f"level-seed={a.seed}", f.read())
        with open(props, "w") as f:
            f.write(text)
    if not a.terrain and not a.natural:
        with open(os.path.join(a.work, "server.properties"), "a") as f:
            f.write("level-type=minecraft:flat\n")
    # with natural generation the mod logs how each village fitted the terrain (with /place it always does)
    # and the generation profile ("Heraldia: perfil: {...}" when it stops: the time of the villages and of their fit)
    debug = ["-Dheraldia.depurar.puerto=true", "-Dheraldia.perfil=true"] if a.natural else []
    proc = subprocess.Popen(["java", "-Xmx3G", *debug, "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    fails, samples = [], {}
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        for cmd in ("difficulty peaceful", "gamerule advance_weather false", "weather clear", "gamerule spawn_mobs false",
                    "gamerule advance_time false", "time set 0"):
            ctx.run(cmd, r"Set|set|Changed|changed|Gamerule|now|weather|difficulty|already")
        sites = natural_sites(ctx, a.natural) if a.natural else SITES[:a.sites]
        if a.structures and not a.natural:
            sites = [(sid, x, z) for sid, (_, x, z) in zip(a.structures.split(","), SITES)]
        placed = []
        for sid, x, z in sites:
            if (load(ctx, x, z) if a.natural else place(ctx, sid, x, z)):
                placed.append((sid, x, z))
            else:
                fails.append(f"{'loading' if a.natural else '/place structure'} {sid} failed at {x}, {z}")
        ctx.ticks(100)    # the template entities appear a few ticks after the blocks
        who = {(sid, x, z): villagers(ctx, x, z) for sid, x, z in placed}
        for k, us in who.items():
            print(f"RUTAS: {k[0]} at {k[1]}, {k[2]}: {len(us)} villagers")
            if not us:
                fails.append(f"{k[0]}: no villagers")
        if a.fault == "bells":
            gone = remove_bells(ctx, placed)
            print(f"RUTAS: FAULT INJECTED: {gone} bells removed")
            if not gone:
                fails.append("--fault bells removed no bell: the fault was not injected")
        ctx.run("gamerule advance_time true", r"Gamerule|set|now")
        ctx.run(f"tick rate {TICK_RATE}", r"rate|Set|set")
        start = ctx.gametime()
        wait_daytime(ctx, SETTLE_UNTIL, start)
        samples = {u: {} for us in who.values() for u in us}
        for t in sorted(WORK + MEET + NIGHT):
            got = wait_daytime(ctx, t, start)
            for u in samples:
                r = read(ctx, u)
                if r:
                    samples[u][t] = r
            print(f"RUTAS: sample at day time {t} (read at {got})")
        ctx.run("tick rate 20", r"rate|Set|set")
        rows_all = []
        print("RUTAS: results")
        for (sid, x, z), us in who.items():
            mems = {u: memories(ctx, u) for u in us if samples[u]}
            rows = [analyse(samples[u], mems[u]) for u in mems]
            if a.verbose:
                for u in mems:
                    first = samples[u][min(samples[u])][0]
                    last = samples[u][max(samples[u])]
                    print(f"RUTAS:     {u[:8]} from {tuple(round(v) for v in first)} to {tuple(round(v) for v in last[0])}"
                          f"{' asleep' if last[1] else ''}: " + ", ".join(f"{k} {v}" for k, v in sorted(mems[u].items())))
            rows_all += rows
            print("RUTAS: " + line(sid, summary(rows)))
            bells = {}
            for m in mems.values():
                if "meeting_point" in m:
                    bells[m["meeting_point"]] = bells.get(m["meeting_point"], 0) + 1
            print(f"RUTAS:   bells claimed: " + ", ".join(f"{b} by {n}" for b, n in sorted(bells.items())))
        tot = summary(rows_all)
        print("RUTAS: " + line("TOTAL", tot))
        n = tot["n"]
        # the margin of every figure, pass or fail: a figure drifting towards its limit shows here before it is a red run
        for key, lim, least in limits(n) if n else []:
            margin = tot[key] - lim if least else lim - tot[key]
            print(f"RUTAS: margin {key:10s} {tot[key]:3d} of {n} ({'at least' if least else 'at most'} {lim}): "
                  f"{margin:+d} villagers")
        if not a.measure and n:
            for key, lim in (("moving", MIN_MOVING), ("commute", MIN_COMMUTE), ("sleeping", MIN_SLEEP), ("meeting", MIN_MEETING)):
                if tot[key] < lim * n:
                    fails.append(f"only {tot[key]} of {n} villagers {key} (at least {lim:.0%} expected)")
            if tot["same_house"] > MAX_SAME_HOUSE * n:
                fails.append(f"{tot['same_house']} of {n} villagers work under 6 blocks from their bed "
                             f"(at most {MAX_SAME_HOUSE:.0%} expected)")
    finally:
        s.send(proc, "stop")
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
    # a figure, not a check (no limit yet): villagers that end the day shut in where their search cannot walk out of,
    # read from the world the server saved (docs/LESSONS.md, "A villager gets by physics to places its path search cannot
    # leave"); the "still" villagers above may include them
    last = {u: sm[max(sm)][0] for u, sm in samples.items() if sm}
    world_dir = os.path.join(a.work, "world")
    if last and os.path.isdir(world_dir):
        shut = [(u, p) for u, p in last.items() if shut_in(world_dir, p)]
        print(f"RUTAS: shut in at the last sample (its search cannot walk 12 blocks from where it is): {len(shut)} of "
              f"{len(last)} villagers")
        for u, p in shut:
            print(f"RUTAS:   shut in: {u[:8]} at {tuple(round(v, 1) for v in p)}")
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("OK: village routes")


if __name__ == "__main__":
    main()
