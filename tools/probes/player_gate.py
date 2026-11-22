"""Can a player open the closet gate and climb the ladder? Carpet's fake player in front of the gate at the foot of a
village ladder (experimental closet jar): look at the gate, use it, walk forward through it and on against the ladder."""
import json, os, queue, shutil, subprocess, sys, threading, time
sys.path.insert(0, "/home/user/HERALDIA/tools/smoke")
import server_smoke as s
import village_routes as vr
from trophies import CARPET
from modrinth import fetch
work, jar = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
LADDERS = [l for l in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lofts.json")))
           if l["site"] == [0, 0]][:4]
launcher = s.prepare(work, jar, s.gradle_properties())
shutil.copy(fetch(work, *CARPET), os.path.join(work, "mods"))
with open(os.path.join(work, "server.properties"), "a") as f:
    f.write("level-type=minecraft:flat\n")
proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines, seen = queue.Queue(), []
threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout] and lines.put(None), daemon=True).start()
ctx = s.Context(proc, lines, seen)
P = "rep"
try:
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    for c in ("gamerule spawn_mobs false", "difficulty peaceful", "time set 1000"):
        ctx.run(c, r"Set|set|Gamerule|now|difficulty|already|changed")
    assert vr.place(ctx, "heraldia:llanuras_castellana", 0, 0)
    ctx.ticks(40)
    ctx.run(f"player {P} spawn at 0 -59 0", r"joined the game|Unknown|Incorrect")
    ctx.until(f"execute if entity @a[name={P}]")
    ctx.run(f"gamemode survival {P}", r"Set|set|game mode")
    for lo in LADDERS:
        x, z, y0, y1 = lo["ladder"]
        gate = None
        for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if ctx.test(f"execute if block {x + dx} -59 {z + dz} #minecraft:fence_gates"):
                gate = (dx, dz)
        if not gate:
            print("NO GATE at ladder", lo["ladder"], flush=True)
            continue
        dx, dz = gate
        gx, gz = x + dx, z + dz
        # stand 1.5 blocks beyond the gate, on the line gate -> ladder, facing the ladder
        sx, sz = gx + dx * 1.5 + 0.5, gz + dz * 1.5 + 0.5
        yaw = {(0, -1): 0, (0, 1): 180, (1, 0): 90, (-1, 0): -90}[(dx, dz)]   # facing from the player toward the ladder
        ctx.run(f"tp {P} {sx} -59 {sz} {yaw} 0", r"Teleported|No entity")
        ctx.ticks(10)
        s.send(proc, f"player {P} look at {gx + 0.5} -58.5 {gz + 0.5}")
        ctx.ticks(2)
        s.send(proc, f"player {P} use once")
        ctx.ticks(5)
        opened = ctx.test(f"execute if block {gx} -59 {gz} #minecraft:fence_gates[open=true]")
        s.send(proc, f"player {P} look {yaw} 0")
        s.send(proc, f"player {P} move forward")
        ctx.ticks(12)                                     # through the open gate into the ladder's cell
        s.send(proc, f"player {P} stop")
        ctx.run(f"tp {P} {x + 0.5} -59 {z + 0.5}", r"Teleported|No entity")   # centred in it (steering, not access)
        face = next(f for f in ("north", "south", "east", "west")
                    if ctx.test(f"execute if block {x} -59 {z} minecraft:ladder[facing={f}]"))
        wall_yaw = {"north": 0, "south": 180, "east": 90, "west": -90}[face]  # toward the block it hangs from
        s.send(proc, f"player {P} look {wall_yaw} 0")
        s.send(proc, f"player {P} move forward")
        ctx.ticks(80)
        s.send(proc, f"player {P} stop")
        p = ctx.pos(f"@a[name={P}]")
        ctx.run(f"setblock {gx} -59 {gz} minecraft:air", r"Changed|Could not")   # out of the next ladder's way
        print(f"LADDER {lo['ladder']}: gate opened {opened}; player at {p} (ladder top y {y1}); "
              f"climbed {bool(p and p[1] > -57.5)}", flush=True)
finally:
    s.send(proc, "stop"); proc.wait(timeout=120)
