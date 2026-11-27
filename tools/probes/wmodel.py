"""wfarmers.py read twice: the same villagers, the same saved world, each night, with the model of the search before and
after it learnt to stand on the top of a wall, a fence or a shut gate and that a scaffold is air (mediums/_paths, Nov
2026: the game's search does both, 26.3 WalkNodeEvaluator). The 8 villages of village_routes on a flat world, N in-game days with
the clock running; every night (day time 14000) every villager's position, saved, and four readings of it:
  shut_old / shut_new     `village_routes.shut_in` (its search cannot get 12 blocks away), old model / new model;
  penned_old / penned_new `wfarmers.penned` (40 blocks), old model / new model.
The old model is the new one with those two put back: an open cell above a wall, a fence or a shut gate is not a place
to stand, and a scaffold is solid. Every villager whose reading differs between the models is printed with its position. Also, from the
saved world of the last night, the villagers standing inside a walled cemetery (`cemeteries`: a ring of wall or hedge
15 x 15 around them).

Usage: wmodel.py <work> <jar> <days>   (HERALDIA pointing at the repository; Java 25 on the PATH). ~6 min a day.
Not a test, not run by CI (tools/probes/README.md).
"""
import collections, json, math, os, queue, subprocess, sys, threading, time
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
sys.path.insert(0, os.path.join(ROOT, "tools", "probes"))
sys.path.insert(0, os.path.join(ROOT, "tools", "gen"))
import server_smoke as s
import village_routes as vr
import medium_structures as ms
import wfarmers
from mediums import _paths

_NEW_STAND, _NEW_SOLID = _paths.Ground._stand, _paths.Ground.solid


def _old_solid(self, st):
    """The model before Nov 2026: a scaffold is a solid block (the game's search reads it as air)."""
    return True if _paths._name(st) == "scaffolding" else _NEW_SOLID(self, st)


def _old_stand(self, x, y, z):
    """The model before Nov 2026: never on the top of a wall, a fence or a shut gate."""
    f, below = self.b.get((x, y, z)), self.b.get((x, y - 1, z))
    if not self.solid(f) and below is not None and self.solid(below) and \
            _paths._name(below).endswith(("_fence", "_wall", "_fence_gate")):
        return None
    return _NEW_STAND(self, x, y, z)


def readings(wd, p):
    out = {}
    for model, stand, solid in (("old", _old_stand, _old_solid), ("new", _NEW_STAND, _NEW_SOLID)):
        _paths.Ground._stand, _paths.Ground.solid = stand, solid
        try:
            out[f"shut_{model}"] = vr.shut_in(wd, p)
            out[f"penned_{model}"] = wfarmers.penned(wd, p)
        finally:
            _paths.Ground._stand, _paths.Ground.solid = _NEW_STAND, _NEW_SOLID
    return out


def in_cemetery(wd, p):
    """Is `p` inside a ring of wall or hedge at most 15 across, standing at its floor? (the cemetery's shape)"""
    import saved_world
    x, y, z = (int(math.floor(v)) for v in p)
    b = saved_world.blocks(wd, x - 15, x + 15, y, y, z - 15, z + 15)
    ring = lambda st: bool(st) and (st.split("[")[0].endswith(("_wall", "_leaves")))
    hit = 0
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for k in range(1, 15):
            st = b.get((x + dx * k, y, z + dz * k))
            if ring(st):
                hit += 1
                break
            if st and not st.split("[")[0].endswith(("air", "grass", "fern", "flower", "poppy", "dandelion", "torch")):
                break
    return hit == 4


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
            ctx.run(cmd, r"Set|set|Changed|changed|Gamerule|Game rule|now|weather|difficulty|already")
        for sid, x, z in vr.SITES:
            assert vr.place(ctx, sid, x, z), sid
        ctx.ticks(100)
        ms.sprint(ctx, 14000)
        for d in range(1, days + 1):
            pos = {}
            for sid, x, z in vr.SITES:
                for u in vr.villagers(ctx, x, z):
                    r = vr.read(ctx, u)
                    if r:
                        pos[u] = r[0]
            ctx.run("save-all flush", r"Saved the game|saved|Saving")
            time.sleep(3)
            wd = os.path.join(work, "world")
            rs = {u: readings(wd, p) for u, p in pos.items()}
            cem = sorted(u for u, p in pos.items() if in_cemetery(wd, p))
            tot = {k: sum(r[k] for r in rs.values()) for k in ("shut_old", "shut_new", "penned_old", "penned_new")}
            diff = {u: dict(rs[u], pos=[round(v, 1) for v in pos[u]]) for u in rs
                    if rs[u]["shut_old"] != rs[u]["shut_new"] or rs[u]["penned_old"] != rs[u]["penned_new"]}
            hist[d] = dict(n=len(pos), **tot, differ=diff, cemetery={u: [round(v, 1) for v in pos[u]] for u in cem})
            print(f"DAY {d}: {len(pos)} villagers; shut in old {tot['shut_old']} new {tot['shut_new']}; penned old "
                  f"{tot['penned_old']} new {tot['penned_new']}; {len(diff)} differ; {len(cem)} in a cemetery", flush=True)
            for u, r in diff.items():
                print(f"DAY {d}:   differs {u[:8]} {r}", flush=True)
            for u in cem:
                print(f"DAY {d}:   in a cemetery {u[:8]} {hist[d]['cemetery'][u]}", flush=True)
            json.dump(hist, open(os.path.join(work, "model.json"), "w"), indent=1)
            ms.sprint(ctx, 24000)
    finally:
        if proc.poll() is None:
            s.send(proc, "stop"); proc.wait(timeout=120)


if __name__ == "__main__":
    main()
