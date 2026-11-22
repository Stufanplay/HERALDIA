"""Garden escape probe: in the 8 placed villages, two villagers per garden per round are taken inside it at nightfall
and left 2,400 ticks: are they still inside? 'Inside' is judged on the shut-gate geometry (develop's saved world), the
same for both jars, so only the gate differs."""
import json, math, os, queue, subprocess, sys, threading, time
sys.path.insert(0, "/home/user/HERALDIA/tools/smoke")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import village_routes as vr
import medium_structures as ms
import vr_strand as v
work, jar, rounds = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3])
REF = "/home/user/HERALDIA/build/layGA/world"
G = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gardens.json")))
for g in G:
    g["cells"] = {(c[0], c[2]) for c in v.component(REF, tuple(g["inside"]))[1]}
launcher = s.prepare(work, jar, s.gradle_properties())
with open(os.path.join(work, "server.properties"), "a") as f:
    f.write("level-type=minecraft:flat\n")
proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines, seen = queue.Queue(), []
threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout] and lines.put(None), daemon=True).start()
ctx = s.Context(proc, lines, seen)
res = []
try:
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    for cmd in ("difficulty peaceful", "gamerule advance_weather false", "weather clear", "gamerule spawn_mobs false",
                "gamerule advance_time false", "time set 1000"):
        ctx.run(cmd, r"Set|set|Changed|changed|Gamerule|now|weather|difficulty|already")
    for sid, x, z in vr.SITES:
        assert vr.place(ctx, sid, x, z), sid
    ctx.ticks(100)
    ms.sprint(ctx, 1500)
    pool = [u for sid, x, z in vr.SITES for u in vr.villagers(ctx, x, z)]
    for i in range(rounds):
        k = 0
        for g in G:
            for _ in range(2):
                u = pool[(i * 2 * len(G) + k) % len(pool)]
                k += 1
                p = g["inside"]
                ctx.run(f"tp {u} {p[0]} {p[1]} {p[2]}", r"Teleported|No entity")
                res.append(dict(round=i, uuid=u, gate=g["gate"]))
        ctx.run("time set 13000", r"Set|set|already")
        ms.sprint(ctx, 2400)
        for r in res:
            if r["round"] != i:
                continue
            rr = vr.read(ctx, r["uuid"])
            g = next(g for g in G if g["gate"] == r["gate"])
            pos = rr[0] if rr else None
            r["pos"] = pos and [round(x, 1) for x in pos]
            r["inside"] = bool(pos and (math.floor(pos[0]), math.floor(pos[2])) in g["cells"])
            print("RESULT", json.dumps(r), flush=True)
        ctx.run("time set 1000", r"Set|set|already")
        ms.sprint(ctx, 600)
finally:
    if proc.poll() is None:
        s.send(proc, "stop"); proc.wait(timeout=120)
alive = [r for r in res if r.get("pos")]
print(f"ESCAPE: {len(res) - len(alive)} gone (a probe fault); of {len(alive)} alive, {sum(r['inside'] for r in alive)} still "
      f"inside the garden, {sum(not r['inside'] for r in alive)} out")
