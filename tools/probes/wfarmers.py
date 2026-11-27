"""wdays.py with each villager's profession, and a second shut-in test that sees large places: the 8 villages of
village_routes on a flat world, N in-game days with the clock running; every night (day time 14000) every villager's
position, profession and home (bed) memory, saved to disk, and two readings of where it stands:
  - `village_routes.shut_in` (its search cannot get 12 blocks away), unchanged;
  - `penned`: its search cannot get FAR (40) blocks away. A farm is 21 x 19, so a farmer shut inside one is NOT shut in
    by the first reading (its search gets 12 blocks away inside the fence) and is penned by this one. The village is
    far larger than 40 blocks, so a villager out in it is never penned.
Prints, per night, both counts and, per profession, how many there are, how many have a bed and how many are penned.

Usage: wfarmers.py <work> <jar> <days>   (HERALDIA pointing at the repository; Java 25 on the PATH)
"""
import collections, json, math, os, queue, subprocess, sys, threading, time
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import server_smoke as s
import village_routes as vr
import medium_structures as ms

FAR, R = 40, 48


def penned(world_dir, pos):
    """village_routes.shut_in with a reach of FAR blocks instead of 12 (read over R blocks around)."""
    import saved_world
    sys.path.insert(0, os.path.join(ROOT, "tools", "gen"))
    import lint
    from mediums import _paths
    x, y, z = pos
    bx, bz, by = int(math.floor(x)), int(math.floor(z)), int(math.floor(y))
    b = saved_world.blocks(world_dir, bx - R, bx + R, by - 30, by + 10, bz - R, bz + R)
    g = _paths.Ground.__new__(_paths.Ground)
    g.lint, g._floor, g._nb = lint, {}, {}
    g.b = {p: st for p, st in b.items() if not st.endswith(("short_grass", "tall_grass")) and "fern" not in st}
    g.box = (bx - R, bz - R, bx + R + 1, bz + R + 1)
    starts = [(cx, cy, cz) for cx in (bx - 1, bx, bx + 1) for cz in (bz - 1, bz, bz + 1)
              for cy in range(by - 3, by + 2) if g.floor(cx, cy, cz) is not None]
    if not starts:
        return True
    start = min(starts, key=lambda c: (abs(c[0] + 0.5 - x) + abs(c[2] + 0.5 - z), abs(g.floor(*c) - y)))
    seen, todo = {start}, [start]
    while todo:
        n = todo.pop()
        if math.hypot(n[0] - start[0], n[2] - start[2]) >= FAR:
            return False
        for m in g.neighbors(n):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return True


def profession(ctx, u):
    m = ctx.run(f"data get entity {u} VillagerData.profession",
                r'has the following entity data: "(?:minecraft:)?([a-z_]+)"|Found no elements|No entity was found')
    return m.group(1) or "?"


def main():
    work, jar, days = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3])
    launcher = s.prepare(work, jar, s.gradle_properties())
    with open(os.path.join(work, "server.properties"), "a") as f:
        f.write("level-type=minecraft:flat\n")
    proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []

    def rd():
        with open(os.path.join(work, "console.txt"), "w") as f:
            for l in proc.stdout:
                f.write(l); lines.put(l)
        lines.put(None)
    threading.Thread(target=rd, daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    hist = {}
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        for cmd in ("difficulty peaceful", "gamerule advance_weather false", "weather clear", "gamerule spawn_mobs false",
                    "gamerule advance_time true", "time set 0"):
            ctx.run(cmd, r"Set|set|Changed|changed|Gamerule|now|weather|difficulty|already")
        for sid, x, z in vr.SITES:
            assert vr.place(ctx, sid, x, z), sid
        ctx.ticks(100)
        ms.sprint(ctx, 14000)                                   # to the first night
        prof = {}
        for d in range(1, days + 1):
            pos = {}
            for sid, x, z in vr.SITES:
                for u in vr.villagers(ctx, x, z):
                    r = vr.read(ctx, u)
                    if r:
                        if u not in prof or prof[u] in ("none", "?"):
                            prof[u] = profession(ctx, u)
                        pos[u] = (r[0], "home" in vr.memories(ctx, u))
            ctx.run("save-all flush", r"Saved the game|saved|Saving")
            time.sleep(3)
            wd = os.path.join(work, "world")
            shut = sorted(u for u, (p, _) in pos.items() if vr.shut_in(wd, p))
            pen = sorted(u for u, (p, _) in pos.items() if penned(wd, p))
            by = collections.defaultdict(lambda: [0, 0, 0])
            for u, (p, h) in pos.items():
                by[prof.get(u, "?")][0] += 1
                by[prof.get(u, "?")][1] += h
                by[prof.get(u, "?")][2] += u in pen
            hist[d] = dict(n=len(pos), shut=shut, penned=pen, homeless=sum(1 for p, h in pos.values() if not h),
                           by_profession={k: v for k, v in sorted(by.items())},
                           where={u: [round(v, 1) for v in pos[u][0]] for u in set(shut) | set(pen)},
                           profession={u: prof.get(u) for u in set(shut) | set(pen)})
            print(f"DAY {d}: {len(pos)} villagers, {len(shut)} shut in, {len(pen)} penned (search under {FAR} blocks), "
                  f"{hist[d]['homeless']} without a bed", flush=True)
            print(f"DAY {d}:   by profession [villagers, with a bed, penned]: "
                  + ", ".join(f"{k} {v}" for k, v in sorted(by.items())), flush=True)
            print(f"DAY {d}:   penned: " + ", ".join(f"{u[:8]} {prof.get(u)} {hist[d]['where'][u]}" for u in pen),
                  flush=True)
            json.dump(hist, open(os.path.join(work, "days.json"), "w"), indent=1)
            ms.sprint(ctx, 24000)                               # to the next night
    finally:
        if proc.poll() is None:
            s.send(proc, "stop"); proc.wait(timeout=120)


if __name__ == "__main__":
    main()
