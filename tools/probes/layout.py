"""Place the 8 villages of village_routes with the world frozen and save it: to compare two jars block by block."""
import os, queue, subprocess, sys, threading, time
sys.path.insert(0, "/home/user/HERALDIA/tools/smoke")
import server_smoke as s
import village_routes as vr
work, jar = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
launcher = s.prepare(work, jar, s.gradle_properties())
with open(os.path.join(work, "server.properties"), "a") as f:
    f.write("level-type=minecraft:flat\n")
proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines, seen = queue.Queue(), []
threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout] and lines.put(None), daemon=True).start()
ctx = s.Context(proc, lines, seen)
try:
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    ctx.run("tick freeze", r"frozen|Frozen|freeze")
    for sid, x, z in vr.SITES:
        print(sid, vr.place(ctx, sid, x, z), flush=True)
    time.sleep(5)
    ctx.run("save-all flush", r"Saved the game|saved")
    time.sleep(3)
finally:
    s.send(proc, "stop"); proc.wait(timeout=120)
