"""Bed probe: does a medium structure's inhabitant get home? On a real 26.3 server, copies of medium-structure templates
are placed on a flat stone platform (MARGIN blocks around each) and, per copy, one villager is watched for --ticks.
A tool for calibrating mediums/_paths.TRAP_WALK_MAX, not a CI test (it is outside tools/smoke on purpose).

Usage: python3 tools/bed_probe.py --jar build/libs/heraldia-X.jar --trials trials.json --out results.json [--ret]
       [--ticks 2400] [--night] [--work build/probe]
- with --ret (the one the figures in mediums/_paths come from): the template's own villagers claim their beds by day;
  the one that claimed keep_bed is teleported to `cell` at nightfall (13000, the clock stopped) and left to come home;
- with --stay DAYS: the template's own inhabitants live in their copy for DAYS in-game days with the clock running
  (ending at nightfall); each result is one inhabitant: `home`, `job` (its workstation) and `pos`. `cell` is unused;
- without either: the template's villagers are removed and a villager with no bed is summoned at `cell` (with --night at
  13000): does it claim one? A villager's search never finds a walk of 16 or more, so this mostly measures distance.
Each result: the trial plus `home` (the bed it remembers, template coordinates, or null) and `pos` (where it is).
trials.json: [{"template": "medianas/posada/llanura/a", "cell": [x, y, z], "floor": feet height, "keep_bed": [x, y, z]
               or null (all other beds are removed), "edits": [[x, y, z, "state"], ...] (setblocks after placing)}, ...]
"""
import argparse, json, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke"))
import server_smoke as s
import medium_structures as ms

Y = 200
SPACING = 64
BASE_X, BASE_Z = 20000, 20000
MARGIN = 16
COLS = 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--trials", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "probe"))
    ap.add_argument("--ticks", type=int, default=1200)
    ap.add_argument("--night", action="store_true")
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--stay", type=float, default=0, help="stay probe: the copies keep their inhabitants and the clock runs "
                    "this many in-game days (to nightfall); then each inhabitant's position, bed and workstation")
    ap.add_argument("--ret", action="store_true", help="return probe: own villagers claim, one is teleported at dusk")
    ap.add_argument("--follow", type=float, default=None, help="set the probe villagers' follow_range")
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    trials = json.load(open(a.trials))
    ts = ms.templates()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump({}, f)
    proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    quiet = threading.Thread(target=reader, args=(proc, lines, a.work), daemon=True)
    quiet.start()
    ctx = s.Context(proc, lines, seen)
    results = []
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        ctx.run("gamerule spawn_mobs false", r"Gamerule|set to|now")
        ctx.run("gamerule advance_time false", r"Gamerule|set to|now")
        for i in range(0, len(trials), a.batch):
            results += run_batch(ctx, ts, trials[i:i + a.batch], a)
            json.dump(results, open(a.out, "w"), indent=1)
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            proc.wait(timeout=120)
    ok = sum(1 for r in results if r["home"])
    print(f"PROBE: {ok} of {len(results)} claimed a bed")


def reader(proc, lines, work):
    log = open(os.path.join(work, "console.txt"), "a")
    for line in proc.stdout:
        log.write(line)
        lines.put(line)
    lines.put(None)


def run_stay(ctx, slots, a):
    """--stay: the inhabitants live in their copy for a.stay days with the clock running; where are they at the end?"""
    ctx.run("gamerule advance_time true", r"Gamerule|set to|now")
    ctx.run("time set 1000", r"Set the time|time to|Set minecraft:\w+ to|already set")
    t0 = ctx.gametime()
    ms.sprint(ctx, int(a.stay * 24000) + 13000 - 1000)        # ends at nightfall (13000)
    time.sleep(20)                                              # a moment at normal speed for them to bed down
    out = []
    for k, (tr, t, ox, oz, (x0, z0, x1, z1)) in enumerate(slots):
        box = f"x={x0 - 8},y={Y - 10},z={z0 - 8},dx={x1 - x0 + 16},dy=60,dz={z1 - z0 + 16}"
        sel = f"@e[type=minecraft:villager,{box}]"
        n = ctx.count(sel)
        for j in range(n):
            ctx.run(f"tag {sel[:-1]},tag=!probe_seen,limit=1] add probe_seen{j}", r"Added tag|Could not|No entity")
            one = f"@e[tag=probe_seen{j},limit=1]"
            ctx.run(f"tag {one} add probe_seen", r"Added tag|Could not|No entity")
            mem = {}
            for key in ("home", "job_site"):
                m = ctx.run(f"data get entity {one} Brain.memories.\"minecraft:{key}\".value.pos",
                            r"entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found|not found")
                mem[key] = [int(m.group(1)) - ox, int(m.group(2)) - Y, int(m.group(3)) - oz] if m.group(1) else None
            p = ctx.pos(one)
            pos = [round(p[0] - ox, 1), round(p[1] - Y, 1), round(p[2] - oz, 1)] if p else None
            r = dict(tr, villager=j, home=mem["home"], job=mem["job_site"], pos=pos, ticks=ctx.gametime() - t0)
            print("RESULT", json.dumps(r), flush=True)
            out.append(r)
            ctx.run(f"tag {one} remove probe_seen{j}", r"Removed tag|Could not|No entity")
        ctx.run(f"kill {sel}", r"Killed|No entity was found")
    for tr, t, ox, oz, (x0, z0, x1, z1) in slots:
        ms.forceload(ctx, x0 - 16, z0 - 16, x1 + 16, z1 + 16, remove=True)
    return out


def run_batch(ctx, ts, batch, a):
    slots = []
    for k, tr in enumerate(batch):
        t = ts[tr["template"]]
        sx, sy, sz = t.size()
        ox, oz = BASE_X + (k % COLS) * SPACING, BASE_Z + (k // COLS) * SPACING
        x0, z0, x1, z1 = ox - MARGIN, oz - MARGIN, ox + sx + MARGIN - 1, oz + sz + MARGIN - 1
        ms.forceload(ctx, x0 - 16, z0 - 16, x1 + 16, z1 + 16)
        slots.append((tr, t, ox, oz, (x0, z0, x1, z1)))
    for tr, t, ox, oz, (x0, z0, x1, z1) in slots:
        ms.wait_loaded(ctx, ox + 8, oz + 8, 24)
        box = f"x={x0 - 8},y={Y - 10},z={z0 - 8},dx={x1 - x0 + 16},dy=60,dz={z1 - z0 + 16}"
        ctx.run(f"kill @e[type=!minecraft:player,{box}]", r"Killed|No entity was found")
        ctx.run(f"fill {x0} {Y - 1} {z0} {x1} {Y - 1} {z1} minecraft:stone", r"Successfully filled|No blocks")
        m = ctx.run(f"place template heraldia:{tr['template']} {ox} {Y} {oz}", r"Loaded template|Failed")
        assert "Loaded" in m.group(0), m.string
    time.sleep(3)
    for tr, t, ox, oz, (x0, z0, x1, z1) in slots:
        box = f"x={x0 - 8},y={Y - 10},z={z0 - 8},dx={x1 - x0 + 16},dy=60,dz={z1 - z0 + 16}"
        end = time.monotonic() + 15
        while not ctx.test(f"execute if entity @e[type=minecraft:villager,{box}]") and time.monotonic() < end:
            time.sleep(1)
        if not a.ret and not a.stay:
            ctx.run(f"kill @e[type=minecraft:villager,{box}]", r"Killed|No entity was found")
        for ex, ey, ez, st in tr.get("edits", []):
            ctx.run(f"setblock {ox + ex} {Y + ey} {oz + ez} {st}", r"Changed the block|Could not set")
        keep = tr.get("keep_bed")
        if keep:
            for (bx, by, bz), (st, _) in t.blocks.items():
                if st.split("[")[0].endswith("_bed") and "part=head" in st and [bx, by, bz] != keep:
                    ctx.run(f"setblock {ox + bx} {Y + by} {oz + bz} minecraft:air", r"Changed the block|Could not set")
    time.sleep(2)
    if a.stay:
        return run_stay(ctx, slots, a)
    if a.ret:
        ctx.run("time set 1000", r"Set the time|time to|Set minecraft:\w+ to|already set")
        homes = {}
        for k, (tr, t, ox, oz, (x0, z0, x1, z1)) in enumerate(slots):
            box = f"x={x0 - 8},y={Y - 10},z={z0 - 8},dx={x1 - x0 + 16},dy=60,dz={z1 - z0 + 16}"
            bx, by, bz = ox + tr["keep_bed"][0], Y + tr["keep_bed"][1], oz + tr["keep_bed"][2]
            sel = (f"@e[type=minecraft:villager,{box},nbt={{Brain:{{memories:{{\"minecraft:home\":{{value:{{pos:[I;{bx},{by},{bz}]}}}}}}}}}},limit=1]")
            end = time.monotonic() + 90
            while not ctx.test(f"execute if entity {sel}") and time.monotonic() < end:
                time.sleep(2)
            ok = ctx.test(f"execute if entity {sel}")
            homes[k] = ok
            if ok:
                ctx.run(f"tag {sel} add probe{k}", r"Added tag|Could not|No entity")
                ctx.run(f"tag @e[tag=probe{k}] add probe", r"Added tag|Could not|No entity")
        ctx.run("time set 13000", r"Set the time|time to|Set minecraft:\w+ to|already set")
        for k, (tr, t, ox, oz, _) in enumerate(slots):
            cx, cy, cz = tr["cell"]
            fy = tr.get("floor", cy)
            if homes[k]:
                ctx.run(f"tp @e[tag=probe{k},limit=1] {ox + cx + 0.5} {Y + fy} {oz + cz + 0.5}", r"Teleported|No entity")
    else:
        ctx.run("time set 13000" if a.night else "time set 1000", r"Set the time|time to|Set minecraft:\w+ to|already set")
        for k, (tr, t, ox, oz, _) in enumerate(slots):
            cx, cy, cz = tr["cell"]
            fy = tr.get("floor", cy)
            extra = ""
            if a.follow:
                extra = f",attributes:[{{id:\"minecraft:follow_range\",base:{a.follow}d}}]"
            ctx.run(f"summon minecraft:villager {ox + cx + 0.5} {Y + fy} {oz + cz + 0.5} "
                    f"{{PersistenceRequired:1b,Invulnerable:1b,Tags:[\"probe\",\"probe{k}\"]{extra}}}",
                    r"Summoned new|Unable to summon")
    t0 = ctx.gametime()
    ms.sprint(ctx, a.ticks)
    out = []
    for k, (tr, t, ox, oz, _) in enumerate(slots):
        sel = f"@e[type=minecraft:villager,tag=probe{k},limit=1]"
        m = ctx.run(f"data get entity {sel} Brain.memories.\"minecraft:home\".value.pos",
                    r"entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found|not found")
        home = [int(m.group(1)) - ox, int(m.group(2)) - Y, int(m.group(3)) - oz] if m.group(1) else None
        p = ctx.pos(sel)
        pos = [round(p[0] - ox, 1), round(p[1] - Y, 1), round(p[2] - oz, 1)] if p else None
        r = dict(tr, home=home, pos=pos, ticks=ctx.gametime() - t0)
        print("RESULT", json.dumps(r), flush=True)
        out.append(r)
    ctx.run("kill @e[type=minecraft:villager,tag=probe]", r"Killed|No entity was found")
    for tr, t, ox, oz, (x0, z0, x1, z1) in slots:
        ms.forceload(ctx, x0 - 16, z0 - 16, x1 + 16, z1 + 16, remove=True)
    return out


if __name__ == "__main__":
    main()
