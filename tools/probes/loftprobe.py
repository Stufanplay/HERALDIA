"""Village loft probe: in two placed villages (flat world, as village_routes), villagers that have claimed a bed are
taken at nightfall onto a ladder-reached upper floor ('loft') or, as control, to the ground at the foot of the same
ladder, and left 2,400 ticks: back in their bed?"""
import json, math, os, queue, subprocess, sys, threading, time
sys.path.insert(0, "/home/user/HERALDIA/tools/smoke")
import server_smoke as s
import village_routes as vr
import medium_structures as ms

work, jar, rounds = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3])
LOFTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lofts.json")))
SITES = [(sid, x, z) for sid, x, z in vr.SITES]
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
res = []
try:
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    for cmd in ("difficulty peaceful", "gamerule advance_weather false", "weather clear", "gamerule spawn_mobs false",
                "gamerule advance_time false", "time set 1000"):
        ctx.run(cmd, r"Set|set|Changed|changed|Gamerule|now|weather|difficulty|already")
    for sid, x, z in SITES:
        assert vr.place(ctx, sid, x, z), sid
    ctx.ticks(100)
    ms.sprint(ctx, 1500)                      # let them claim beds, job sites and bells
    for lo in LOFTS:          # the layout is the one the lofts were read from
        x, z, y0, y1 = lo["ladder"]
        lo["ok"] = ctx.test(f"execute if block {x} {y0} {z} minecraft:ladder")
    print("LOFTS present", sum(lo["ok"] for lo in LOFTS), "of", len(LOFTS), flush=True)
    for i in range(rounds):
        n = 0
        for sid, x, z in SITES:
            for u in vr.villagers(ctx, x, z):
                m = vr.memories(ctx, u)
                if "home" not in m:
                    continue
                h = m["home"]
                near = [lo for lo in LOFTS if lo["ok"] and math.hypot(lo["loft"][0] - h[0], lo["loft"][2] - h[2]) <= 10]
                if not near:
                    continue
                lo = min(near, key=lambda lo: math.hypot(lo["loft"][0] - h[0], lo["loft"][2] - h[2]))
                where = "loft" if (n + i) % 2 == 0 else "foot"
                p = lo[where]
                n += 1
                ctx.run(f"tp {u} {p[0]} {p[1]} {p[2]}", r"Teleported|No entity")
                res.append(dict(round=i, site=sid, uuid=u, arm=where, home=list(h), ladder=lo["ladder"]))
        ctx.run("time set 13000", r"Set|set|already")
        ms.sprint(ctx, 2400)
        for r in res:
            if r["round"] != i:
                continue
            m = vr.memories(ctx, r["uuid"])
            rr = vr.read(ctx, r["uuid"])
            pos = rr[0] if rr else None
            h = r["home"]
            r["pos"] = pos and [round(v, 1) for v in pos]
            r["has_home"] = "home" in m
            r["in_bed"] = bool(pos and "home" in m and math.hypot(pos[0] - h[0] - 0.5, pos[2] - h[2] - 0.5) < 2)
            print("RESULT", json.dumps(r), flush=True)
        ctx.run("time set 1000", r"Set|set|already")
        ms.sprint(ctx, 1200)                  # a morning for anyone who lost its bed to claim one again
    json.dump(res, open(os.path.join(work, "loft.json"), "w"), indent=1)
finally:
    if proc.poll() is None:
        s.send(proc, "stop"); proc.wait(timeout=120)
for arm in ("loft", "foot"):
    rs = [r for r in res if r["arm"] == arm and "in_bed" in r]
    dead = [r for r in rs if r["pos"] is None]
    alive = [r for r in rs if r["pos"] is not None]
    print(f"{arm}: {len(dead)} died (a probe fault); of {len(alive)} alive, {sum(r['in_bed'] for r in alive)} back in their "
          f"bed, {sum(1 for r in alive if not r['has_home'])} lost it")
