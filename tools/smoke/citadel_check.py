"""Server test of the Dwarven Citadel: it is placed, the guardian carries its equipment and health, there are minecarts with chests and
equipped armor stands, and /locate responds. Reuses the smoke test server.

Usage: python3 tools/smoke/citadel_check.py --jar build/libs/heraldia-X.jar [--work build/smoke]
"""
import argparse, os, queue, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

X = Z = 4000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke"))
    a = ap.parse_args()
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen, fails = queue.Queue(), [], []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        s.send(proc, f"forceload add {X - 112} {Z - 112} {X + 111} {Z + 111}")
        s.wait_for(lines, r"Marked|Added|chunks? .*force", s.COMMAND_TIMEOUT_S, seen)
        for _ in range(s.PLACE_ATTEMPTS):
            m = s.run(proc, lines, seen, f"place structure heraldia:unicas/ciudadela {X} ~ {Z}", r"Generated structure|not loaded(?! yet)")
            if "not loaded" not in m.group(0):
                break
            time.sleep(s.PLACE_RETRY_S)
        if not m.group(0).startswith("Generated"):
            fails.append(f"place failed: {m.string.strip()}")
        # the structure's entities appear a few seconds after the blocks: wait for the guardian by its
        # tag before reading its data (reading it right away gave "No entity" on a slow server)
        g = "@e[type=minecraft:vindicator,tag=heraldia_guardian.ciudadela]"
        ctx.wait_entity(g)
        m = s.run(proc, lines, seen, f"data get entity {g[:-1]},limit=1]", r"has the following entity data: .*|No entity")
        d = m.group(0)
        for want in ("minecraft:iron_axe", "minecraft:iron_chestplate", "heraldia.ciudadela.guardian",
                     "max_health", "Health: 60.0f", "PersistenceRequired: 1b"):
            if want not in d:
                fails.append(f"guardian without {want}")
        checks = [("@e[type=minecraft:chest_minecart]", 2), ("@e[type=minecraft:minecart]", 1),
                  ('@e[type=minecraft:armor_stand,nbt={equipment:{head:{id:"minecraft:chainmail_helmet"}}}]', 2)]
        for sel, n in checks:
            end = time.monotonic() + s.UNTIL_S
            while (got := ctx.count(sel)) < n and time.monotonic() < end:
                time.sleep(s.POLL_S)
            if got < n:
                fails.append(f"faltan entidades {sel}: {got} de {n}")
        m = s.run(proc, lines, seen, "locate structure heraldia:unicas/ciudadela", r"is at \[.*|Could not find.*")
        print("locate:", m.group(0))
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            proc.wait(timeout=120)
    text = "".join(seen)
    for bad in ("Registry loading errors", "Failed to parse", "Couldn't load", "Exception"):
        if bad in text:
            fails.append(f"the log contains {bad!r}")
    print("CIUDADELA FALLIDA:\n  " + "\n  ".join(fails) if fails else "CIUDADELA OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
