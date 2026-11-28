"""The Herald's House roads (herald/SpawnRoads, tools/gen/spawn_roads.py) on a real 26.3 dedicated server, in both orders
the town and the arena can be placed in, and in a world whose town was there before the roads.

Usage: python3 tools/smoke/spawn_roads.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-caminos"
World A (the arena first; the town placed with casa_heraldo.caminos.activado off, as in a world from before this feature):
  1. the arena is placed, then the town: no roads are built ("roads: disabled");
  2. the option is turned on (/heraldia reload) and the server restarted: still nothing is built on its own;
  3. /heraldia herald roads builds them: the four gates' roads and the arena road (from the gate that points to it), the
     huts (the default cap: the guide and one per road, minus any site under water or too steep) and the guide; every
     road column outside the protected ring has light (the build's own check, in the log); a second /heraldia herald
     roads says there is nothing left to do and builds nothing;
  4. the guide's conversation opens in the choice window (a simulated player has no Heraldia on its client: the
     container menu), never in the chat: its first page offers [Tell me more] [Show me your wares] [Farewell], [Tell me
     more] shows the second page, [Farewell] the last one.
World B (a new world; the town first, the arena later):
  5. the town is placed and its roads built on their own: four roads, the huts without the guide (its place kept);
  6. the arena is placed: its road and the guide's hut are built then, on their own, once; /heraldia herald roads says
     there is nothing left.
After every build, the build's own audit of every road column on land, chunk by chunk, as the roads stand (in the log):
  7. no trunk, leaves, plant or bump of ground on the paving or in the 3 blocks over it; every column paved with the
     road's paving (one material and its kerb: BuiltRoads.deck); no two neighbouring columns more than a block apart; no
     leaves left hanging near the road with no tree to hold them (the felled trees go whole).
The build's cost (ticks, server-thread ms, the slowest step) is printed for each build. Exit code 0 if everything passes.
"""
import argparse, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch
from arena import Test

P = "Viajero"
HUTS = "@e[type=minecraft:villager,tag=heraldia_choza]"
GUIDE = "@e[type=minecraft:villager,tag=heraldia_guia]"
BUILT = (r"herald's house roads: built in (\d+) ticks \((\d+) ms on the server thread, the slowest step (\d+) ms\): (\d+) roads, "
         r"(\d+) columns paved, (\d+) on bridges, (\d+) left, (\d+) lamp posts, (\d+) signs, (\d+) new huts, (\d+) new villagers "
         r"\((\d+) huts in all\)")
LIGHT = r"herald's house roads: light: (\d+) of (\d+) road columns outside the protected ring are dark \((\d+) of (\d+) lamp"
AUDIT = (r"herald's house roads: audit: (\d+) road columns on land, (\d+) blocked \(.*?\), (\d+) not paved, (\d+) steps of more "
         r"than one block, (\d+) leaves no tree holds near the road; (\d+) trees felled, (\d+) hanging leaves taken away")
ARENA_ROAD = r"herald's house roads: arena road from the (\w+) gate, (\d+) blocks"
BUILDING = r"herald's house roads: building"
PLACED = r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+) \(box (-?\d+) (-?\d+) (-?\d+) to (-?\d+) (-?\d+) (-?\d+)\)"
SEES = r"choice: " + P + r" sees guide as (\w+) \(session (\d+): ([\w, ]*)\)"
DARK_SHARE = 0.02          # the light check's allowance: a column can sit 3+ blocks below its lamp on a hillside
COSTS = []


def config(work, roads):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False, "caminos": {"activado": roads}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def place_arena(p):
    ctx = p.ctx
    m = ctx.run("heraldia arena place", r"arena: sitio propuesto en (-?\d+) (-?\d+) (-?\d+)|sin sitio llano")
    if not p.check(m.group(1), "arena: no site"):
        return None
    ctx.run("heraldia arena place confirm", r"Colocando la arena en|Building the arena at")
    m = p.wait_log(r"arena: colocada en (-?\d+) (-?\d+) (-?\d+) \(caja (-?\d+) (-?\d+) (-?\d+) a (-?\d+) (-?\d+) (-?\d+)\)", 600)
    p.check(p.wait_log(r"arena: obra terminada", 600), "arena: the works do not finish")
    return [int(g) for g in m.groups()[3:]] if m else None


def place_house(p):
    ctx = p.ctx
    ctx.run("heraldia herald place", r"Looking for a site|Buscando sitio")
    if not p.check(p.wait_log(r"herald's house: site at", 180), "herald: no site"):
        return None
    ctx.run("heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
    m = p.wait_log(PLACED, 900)
    if not p.check(m, "herald: the house is not built"):
        return None
    return [int(g) for g in m.groups()[3:]]


def built(p, n, what):
    """The n-th build's summary line (its numbers), printed with its cost."""
    if not p.check(p.wait_times(BUILT, n, 900), f"{what}: the roads' build does not finish"):
        return None
    m = list(re.finditer(BUILT, p.ctx.log()))[n - 1]
    g = [int(x) for x in m.groups()]
    COSTS.append((what, g[0], g[1], g[2]))
    print(f"ROADS {what}: {m.group(0)}", flush=True)
    return {"ticks": g[0], "ms": g[1], "slowest": g[2], "roads": g[3], "paved": g[4], "bridged": g[5], "left": g[6],
            "lamps": g[7], "signs": g[8], "huts": g[9], "villagers": g[10], "all": g[11]}


def audit(p, n, what):
    """The n-th build's audit of its road columns: none blocked, unpaved or a jump apart, and no leaves left hanging."""
    m = list(re.finditer(AUDIT, p.ctx.log()))
    if not p.check(len(m) >= n, f"{what}: no road audit in the log"):
        return
    cols, blocked, unpaved, steps, orphans, trees, tidied = (int(g) for g in m[n - 1].groups())
    print(f"ROADS {what}: audit: {cols} columns, {blocked} blocked, {unpaved} not paved, {steps} steps over one block, "
          f"{orphans} hanging leaves, {trees} trees felled, {tidied} hanging leaves taken away", flush=True)
    p.check(cols > 0, f"{what}: no road column audited")
    p.check(blocked == 0, f"{what}: {blocked} of {cols} road columns have a trunk, leaves, a plant or ground on the paving")
    p.check(unpaved == 0, f"{what}: {unpaved} of {cols} road columns are not the road's paving (loose patches, grass)")
    p.check(steps == 0, f"{what}: {steps} pairs of road columns more than a block apart")
    p.check(orphans == 0, f"{what}: {orphans} leaves near the road hang with no tree")


def light(p, n, what):
    if not p.wait_times(LIGHT, n, 120):
        p.check(False, f"{what}: no light check in the log")
        return
    m = list(re.finditer(LIGHT, p.ctx.log()))[n - 1]
    dark, checked = int(m.group(1)), int(m.group(2))
    print(f"ROADS {what}: light: {dark} dark of {checked}; {m.group(3)} of {m.group(4)} lamp posts", flush=True)
    p.check(checked > 0, f"{what}: no road column checked for light")
    p.check(dark <= DARK_SHARE * checked, f"{what}: {dark} of {checked} road columns are dark")


def load_ring(p, box):
    """The town and its ring loaded (the huts' villagers counted), then given a moment to load their entities."""
    x0, z0, x1, z1 = box[0] - 60, box[2] - 60, box[3] + 60, box[5] + 60
    p.ctx.run(f"forceload add {x0} {z0} {x1} {z1}", r"Marked|force|already|Too many")
    p.ctx.ticks(60)


def count(p, sel, want, what):
    """Waits (entities load after their chunks) until the selector gives `want`."""
    end = time.monotonic() + 30
    n = p.ctx.count(sel)
    while n != want and time.monotonic() < end:
        time.sleep(1)
        n = p.ctx.count(sel)
    p.check(n == want, f"{what}: {n} (should be {want})")
    return n


def nothing_left(p, what):
    before = p.times(BUILDING)
    # the refusal is the expected reply: a second order finds the roads built (or still being built) and must not build again
    p.ctx.run("heraldia herald roads", r"already built|ya están construidos|being built|se están construyendo")
    p.ctx.ticks(40)
    p.check(p.times(BUILDING) == before, f"{what}: /heraldia herald roads built something again")


def guide_talk(srv, p):
    ctx = p.ctx
    g = ctx.pos(GUIDE)
    if not p.check(g, "guide: no guide to talk to"):
        return
    s.require_carpet(srv.ctx)
    srv.ctx.run(f"player {P} spawn at {g[0]:.1f} {g[1]:.1f} {g[2] + 1.5:.1f}", r"joined the game")
    ctx.until(f"execute if entity @a[name={P}]")
    ctx.run(f"execute as {P} run heraldia talk with {GUIDE[:-1]},limit=1]", SEES + "|no longer|cannot open")
    m = re.findall(SEES, ctx.log())
    if not p.check(m, "guide: the conversation does not open in a window"):
        return
    how, session, ids = m[-1]
    p.check(how == "menu", f"guide: shown as {how} (a client without Heraldia gets the menu)")
    p.check(ids == "more, trade, bye", f"guide: the first page offers {ids}")
    ctx.run(f"execute as {P} run heraldia choice click 11", r"choice click: slot")      # [Tell me more]: slots 11, 13, 15
    p.check(p.wait_times(SEES, 2, 20), "guide: [Tell me more] shows no second page")
    m = re.findall(SEES, ctx.log())
    p.check(m[-1][2] == "trade, bye", f"guide: the second page offers {m[-1][2]}")
    ctx.run(f"execute as {P} run heraldia choice click 14", r"choice click: slot")      # [Farewell]: slots 12, 14
    p.check(p.wait_times(SEES, 3, 20), "guide: [Farewell] shows no last page")
    p.check(re.findall(SEES, ctx.log())[-1][2] == "close", "guide: the last page is not just [Close]")
    p.check("<" + P + ">" not in ctx.log(), "guide: something went to the chat")
    srv.ctx.run(f"player {P} kill", r"left the game")


def world_a(work, launcher, fails, texts):
    """The arena first; the town with the roads off; restarted with them on; then the command."""
    config(work, False)
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    box = None
    try:
        place_arena(p)
        box = place_house(p)
        if box:
            p.check(p.wait_log(r"herald's house roads: disabled", 60), "A: no 'roads disabled' with the option off")
            config(work, True)
            srv.ctx.run("heraldia reload", r"reload|recarg|Reload")
            srv.ctx.ticks(100)
            p.check(p.times(BUILDING) == 0, "A: the roads were built on their own in a world whose town was already there")
    finally:
        srv.stop()
        texts.append(srv.ctx.log())
    if not box:
        return
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    try:
        srv.ctx.ticks(200)
        p.check(p.times(BUILDING) == 0, "A: after restarting, the roads were built on their own")
        srv.ctx.run("heraldia herald roads", r"Building the roads|Construyendo los caminos")
        r = built(p, 1, "A (command, arena first)")
        if r:
            p.check(r["roads"] == 5, f"A: {r['roads']} roads (the four gates' and the arena's)")
            p.check(p.wait_log(ARENA_ROAD, 5), "A: no arena road")
            p.check(r["paved"] > 300, f"A: only {r['paved']} columns paved")
            p.check(r["lamps"] >= 20, f"A: only {r['lamps']} lamp posts")
            p.check(1 <= r["villagers"] <= 5 and r["huts"] == r["villagers"], f"A: {r['huts']} huts, {r['villagers']} villagers")
            load_ring(p, box)
            count(p, HUTS, r["villagers"], "A: hut villagers")
            count(p, GUIDE, 1, "A: guides")
            light(p, 1, "A")
            audit(p, 1, "A")
            nothing_left(p, "A")
            count(p, HUTS, r["villagers"], "A: hut villagers after the second command")
            guide_talk(srv, p)
    finally:
        srv.stop()
        texts.append(srv.ctx.log())


def world_b(work, launcher, fails, texts):
    """A new world: the town first (its roads on their own), the arena later (its road then)."""
    shutil.rmtree(os.path.join(work, "world"), ignore_errors=True)
    config(work, True)
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    try:
        box = place_house(p)
        if not box:
            return
        r = built(p, 1, "B (town first)")
        if not r:
            return
        p.check(r["roads"] == 4, f"B: {r['roads']} roads before the arena (four)")
        audit(p, 1, "B (town first)")
        p.check(1 <= r["villagers"] <= 4, f"B: {r['villagers']} villagers before the arena (one per road at most, the guide's place kept)")
        load_ring(p, box)
        count(p, GUIDE, 0, "B: guides before the arena")
        place_arena(p)
        p.check(p.wait_log(r"herald's house roads: the arena was placed: building its road", 120), "B: the arena road does not start")
        r2 = built(p, 2, "B (arena later)")
        if r2:
            p.check(r2["roads"] == 1 and r2["huts"] == 1, f"B: {r2['roads']} roads and {r2['huts']} huts for the arena (1 and 1)")
            p.check(p.wait_log(ARENA_ROAD, 5), "B: no arena road")
            count(p, GUIDE, 1, "B: guides after the arena")
            count(p, HUTS, r["villagers"] + 1, "B: hut villagers after the arena")
            light(p, 2, "B")
            audit(p, 2, "B (arena later)")
            nothing_left(p, "B")
    finally:
        srv.stop()
        texts.append(srv.ctx.log())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-caminos"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    shutil.rmtree(os.path.join(a.work, "world"), ignore_errors=True)
    fails, texts = [], []
    t0 = time.monotonic()
    world_a(a.work, launcher, fails, texts)
    world_b(a.work, launcher, fails, texts)
    for bad in ("Registry loading errors", "at io.github.albertosa23", "roads: step", "missing template"):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    for what, ticks, ms, slowest in COSTS:
        print(f"COST {what}: {ticks} ticks, {ms} ms on the server thread, the slowest step {slowest} ms")
    print(f"SPAWN ROADS: {time.monotonic() - t0:.0f} s;", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
