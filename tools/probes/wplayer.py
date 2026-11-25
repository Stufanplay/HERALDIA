"""Can a player open the closet's gate and climb the village ladder behind it? Carpet's fake player, from the same
cell in both jars: look at the gate (if there is one), use it, then walk forward toward the ladder, and if walking
alone did not do it, walk and jump.

Usage: wplayer2.py <work dir> <jar> <lofts.json>    (a jar without closets is the control: no gate to open)
"""
import json, os, queue, shutil, subprocess, sys, threading
REPO = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(REPO, "tools", "smoke"))
import server_smoke as s
import village_routes as vr
from trophies import CARPET
from modrinth import fetch

work, jar = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
LADDERS = [l["ladder"] for l in json.load(open(sys.argv[3])) if l["site"] == [0, 0]]
FACE = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
YAW = {(0, -1): 180.0, (0, 1): 0.0, (1, 0): -90.0, (-1, 0): 90.0}     # yaw to look toward (dx, dz)
P = "Probe"                                                            # Carpet capitalises the name

launcher = s.prepare(work, jar, s.gradle_properties())
shutil.copy(fetch(work, *CARPET), os.path.join(work, "mods"))
with open(os.path.join(work, "server.properties"), "a") as f:
    f.write("level-type=minecraft:flat\n")
proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines, seen = queue.Queue(), []


def _read():
    with open(os.path.join(work, "console.txt"), "w") as f:
        for l in proc.stdout:
            f.write(l)
            f.flush()
            lines.put(l)
    lines.put(None)


threading.Thread(target=_read, daemon=True).start()
ctx = s.Context(proc, lines, seen)
rows = []
try:
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    for c in ("gamerule spawn_mobs false", "difficulty peaceful", "time set 1000"):
        ctx.run(c, r"Set|set|Gamerule|now|difficulty|already|changed")
    assert vr.place(ctx, "heraldia:llanuras_castellana", 0, 0)
    ctx.ticks(40)
    s.send(proc, f"player {P} spawn at 0.5 -59 0.5")
    if not ctx.until(f"execute if entity @a[name={P}]"):
        raise SystemExit("the fake player did not join\n" + ctx.log()[-2000:])
    ctx.run(f"gamemode survival {P}", r"Set|set|game mode")
    for x, z, y0, y1 in LADDERS:
        rung = next((y for y in (y0, y0 + 1) if ctx.test(f"execute if block {x} {y} {z} #minecraft:climbable")), None)
        if rung is None:
            rows.append(dict(at=(x, z), outcome="no ladder"))
            print(f"LADDER {x},{z}: no ladder at {y0} or {y0 + 1}", flush=True)
            continue
        facing = next(f for f in FACE if ctx.test(f"execute if block {x} {rung} {z} minecraft:ladder[facing={f}]"))
        dx, dz = FACE[facing]                     # the ladder's open side
        # the gate: in the ladder's own foot, or in the cell beside it on the open side
        shape = None
        if ctx.test(f"execute if block {x} {y0} {z} #minecraft:fence_gates"):
            shape, gate = "rung", (x, y0, z)
        elif ctx.test(f"execute if block {x + dx} {y0} {z + dz} #minecraft:fence_gates"):
            shape, gate = "beside", (x + dx, y0, z + dz)
        else:
            shape, gate = "none (control)", None
        # the same approach cell in every jar: two cells out from the ladder, on its open side
        px, pz = x + 2 * dx + 0.5, z + 2 * dz + 0.5
        if not (ctx.test(f"execute if block {x + 2 * dx} {y0} {z + 2 * dz} #minecraft:air")
                and ctx.test(f"execute if block {x + 2 * dx} {y0 + 1} {z + 2 * dz} #minecraft:air")):
            rows.append(dict(at=(x, z), outcome="no room to stand two cells out", shape=shape))
            print(f"LADDER {x},{z} ({shape}): no clear cell two out on the {facing} side", flush=True)
            continue
        ctx.run(f"tp {P} {px} {y0} {pz} {YAW[(-dx, -dz)]} 0", r"Teleported|No entity")
        ctx.ticks(10)
        opened = None
        if gate:
            s.send(proc, f"player {P} look at {gate[0] + 0.5} {gate[1] + 0.5} {gate[2] + 0.5}")
            ctx.ticks(3)
            s.send(proc, f"player {P} use once")
            ctx.ticks(6)
            opened = ctx.test(f"execute if block {gate[0]} {gate[1]} {gate[2]} #minecraft:fence_gates[open=true]")
        s.send(proc, f"player {P} look {YAW[(-dx, -dz)]} 0")
        s.send(proc, f"player {P} move forward")
        ctx.ticks(120)
        s.send(proc, f"player {P} stop")
        walked = ctx.pos(f"@a[name={P}]")
        s.send(proc, f"player {P} move forward")
        s.send(proc, f"player {P} jump continuous")
        ctx.ticks(160)
        s.send(proc, f"player {P} stop")
        jumped = ctx.pos(f"@a[name={P}]")
        rows.append(dict(at=(x, z), outcome="ok", shape=shape, opened=opened,
                         walked=walked and round(walked[1], 1), jumped=jumped and round(jumped[1], 1),
                         top=y1, by_walking=bool(walked and walked[1] >= y1),
                         by_jumping=bool(jumped and jumped[1] >= y1)))
        print(f"LADDER {x},{z} rungs {rung}..{y1} [{shape}]: gate opened {opened}; walking -> "
              f"{rows[-1]['walked']} (top {y1}) {'REACHED' if rows[-1]['by_walking'] else ''}; "
              f"then jumping -> {rows[-1]['jumped']} {'REACHED' if rows[-1]['by_jumping'] else ''}", flush=True)
        if gate:
            ctx.run(f"setblock {gate[0]} {gate[1]} {gate[2]} minecraft:air", r"Changed|Could not")
finally:
    s.send(proc, "stop"); proc.wait(timeout=120)
ok = [r for r in rows if r["outcome"] == "ok"]
json.dump(rows, open(os.path.join(work, "wplayer.json"), "w"), indent=1, default=str)
print(f"TOTAL: {len(ok)} of {len(rows)} ladders tried; gates opened {sum(1 for r in ok if r['opened'])} of "
      f"{sum(1 for r in ok if r['opened'] is not None)}; reached the top by walking "
      f"{sum(1 for r in ok if r['by_walking'])} of {len(ok)}; by walking or jumping "
      f"{sum(1 for r in ok if r['by_walking'] or r['by_jumping'])} of {len(ok)}; "
      f"not tried: {[r['outcome'] for r in rows if r['outcome'] != 'ok']}", flush=True)
