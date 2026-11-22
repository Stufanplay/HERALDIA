"""Does it accumulate? The 8 villages of village_routes on a flat world, N in-game days with the clock running; every
night (day time 14000) every villager's position, saved to disk, and village_routes.shut_in on it."""
import json, os, queue, subprocess, sys, threading, time
sys.path.insert(0, "/home/user/HERALDIA/tools/smoke")
import server_smoke as s
import village_routes as vr
import medium_structures as ms

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
    for d in range(1, days + 1):
        pos = {}
        for sid, x, z in vr.SITES:
            for u in vr.villagers(ctx, x, z):
                r = vr.read(ctx, u)
                if r:
                    pos[u] = (r[0], "home" in vr.memories(ctx, u))
        ctx.run("save-all flush", r"Saved the game|saved|Saving")
        time.sleep(3)
        shut = sorted(u for u, (p, _) in pos.items() if vr.shut_in(os.path.join(work, "world"), p))
        hist[d] = dict(n=len(pos), shut=shut, homeless=sum(1 for p, h in pos.values() if not h),
                       where={u: [round(v, 1) for v in pos[u][0]] for u in shut})
        print(f"DAY {d}: {len(pos)} villagers, {len(shut)} shut in, {hist[d]['homeless']} without a bed; shut in: "
              + ", ".join(f"{u[:8]} {hist[d]['where'][u]}" for u in shut), flush=True)
        json.dump(hist, open(os.path.join(work, "days.json"), "w"), indent=1)
        ms.sprint(ctx, 24000)                               # to the next night
finally:
    if proc.poll() is None:
        s.send(proc, "stop"); proc.wait(timeout=120)
