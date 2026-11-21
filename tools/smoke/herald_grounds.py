"""The Herald's House grounds (herald/Outskirts, herald/OutskirtsPlan, tools/gen/herald_grounds.py) on a real 26.3
dedicated server: in a world whose town came before them (only the command builds them) and in a new world (built on
their own right after the town and its roads).

Usage: python3 tools/smoke/herald_grounds.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-alrededores"
World A (the town placed with casa_heraldo.alrededores.activado off and the roads off, as in a world from before this
feature):
  1. the town is placed: no grounds are built ("grounds: disabled");
  2. the option is turned on (/heraldia reload) and the server restarted: still nothing is built on its own;
  3. /heraldia herald grounds builds them; a second /heraldia herald grounds says there is nothing left to do.
World B (a new world, the roads on): the town is placed; its roads are built, and then, on their own, its grounds.
After every build, the build's own audit of every column of the ring as it stands (in the log):
  4. no ramps: at most RAMP_SHARE of the columns' one-block steps in runs of four or more one after another (the "rice
     terraces" the owner saw at the spawn passed the old audit, which counted only steps of more than one block); no
     step of more than one block left bare (not a terrace's retaining wall) between side by side columns of natural
     ground further in than the outermost rows (where the ground meets the natural one beyond, which keeps its own), but
     where a road, a structure or a cliff the caps cannot soften forces one (at most STEP_SHARE of the columns); no loose
     column, no hole; no water standing in the air;
  5. the houses: at least MIN_HOUSES, every chest with its loot table, no door blocked; the cherry trees: at least
     MIN_TREES, none floating;
  6. its cost: no step over SLOW_MS ms on the server thread (ticks, total ms and the slowest step printed);
  7. world B: the roads were built first and their own audit stays clean (no column blocked, unpaved, a jump apart).
Exit code 0 if everything passes.
"""
import argparse, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from arena import Test

BUILDING = r"herald's house grounds: building \((\d+) chunks, up to (\d+) houses\)"
PLAN = (r"herald's house grounds: plan in (\d+) ms: (\d+) columns to level \(cut up to (\d+), filled up to (\d+)\), (\d+) too steep "
        r"to level within \d+ blocks, (\d+) narrow pits to cover; steps of more than one block: (\d+) before, (\d+) in the plan \((\d+) of them "
        r"terraces' walls\); one-block steps in ramps: (\d+) before, (\d+) in the plan; (\d+) houses, (\d+) cherry trees")
BUILT = (r"herald's house grounds: built in (\d+) ticks \((\d+) ms on the server thread, the slowest step (\d+) ms; the plan (\d+) ms "
         r"off it\): (\d+) columns levelled \((\d+) narrow pits covered with a lid\), (\d+) left, (\d+) too steep to level fully, (\d+) trees "
         r"felled, (\d+) houses, (\d+) cherry trees")
AUDIT = (r"herald's house grounds: audit: (\d+) columns on land, (\d+) steps of more than one block \((\d+) before; (\d+) of them in "
         r"the outermost \d+ rows, where the natural ground keeps its own; (\d+) faced with a retaining wall, (\d+) bare further in\), "
         r"(\d+) one-block steps in ramps \((\d+) before\), (\d+) loose columns, (\d+) holes \(further in\), (\d+) blocks of water standing "
         r"in the air; (\d+) houses, (\d+) of (\d+) chests with loot, (\d+) doors blocked; (\d+) cherry trees, (\d+) floating, "
         r"(\d+) left out by a fire source, (\d+) that did not fit")
SLOWEST = r"herald's house grounds: the slowest step: (.+)"
BY_KIND = r"herald's house grounds: by kind of step: .+"
HANDED = r"herald's house grounds: the plan handed to the background pool: .+"
SLOW_STEP = r"herald's house grounds: a slow step: .+"
ROADS_BUILT = r"herald's house roads: built in (\d+) ticks \((\d+) ms on the server thread, the slowest step (\d+) ms\)"
ROADS_AUDIT = (r"herald's house roads: audit: (\d+) road columns on land, (\d+) blocked \(.*?\), (\d+) not paved, (\d+) steps of more "
               r"than one block, (\d+) leaves no tree holds near the road")
PLACED = r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+)"
# the town itself (herald/Building), as the grounds and the roads report theirs: ticks, ms on the server thread, the
# slowest step with the thread's own CPU time in it, and which step it was
HOUSE_BUILT = (r"herald's house: built in (\d+) ticks \((\d+) ms on the server thread, the slowest step (\d+) ms, "
               r"([^,]+?) of it the server thread's own work: (.+?); one step a tick\)")
HOUSE_BY_KIND = r"herald's house: by kind of step: (.+)"
SLOW_MS = 100              # the orchestrator's cap for any step on the server thread
STEP_SHARE = 0.01          # bare steps a road, a structure or a cliff forces, of the columns further in
RAMP_SHARE = 0.04          # one-block steps in ramps (OutskirtsPlan.RAMP or more one after another), of the columns (14 % on this seed before terraces)
MIN_HOUSES, MIN_TREES = 4, 3
COSTS = []


def config(work, grounds, roads):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False, "caminos": {"activado": roads}, "alrededores": {"activado": grounds}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def place_house(p):
    ctx = p.ctx
    ctx.run("heraldia herald place", r"Looking for a site|Buscando sitio")
    if not p.check(p.wait_log(r"herald's house: site at", 180), "herald: no site"):
        return False
    ctx.run("heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
    return p.check(p.wait_log(PLACED, 900), "herald: the house is not built")


def nth(p, pattern, n):
    m = list(re.finditer(pattern, p.ctx.log()))
    return m[n - 1] if len(m) >= n else None


def check_build(p, n, what):
    """The n-th grounds build: its plan, cost and audit, printed and checked."""
    if not p.check(p.wait_times(BUILT, n, 900), f"{what}: the grounds' build does not finish"):
        return
    plan, built, audit = nth(p, PLAN, n), nth(p, BUILT, n), nth(p, AUDIT, n)
    slowest = nth(p, SLOWEST, n)
    print(f"GROUNDS {what}: {plan.group(0) if plan else 'no plan line'}", flush=True)
    print(f"GROUNDS {what}: {built.group(0)}", flush=True)
    print(f"GROUNDS {what}: {audit.group(0) if audit else 'no audit line'}", flush=True)
    print(f"GROUNDS {what}: the slowest step: {slowest.group(1) if slowest else '?'}", flush=True)
    for pattern in (BY_KIND, HANDED):                   # where the server thread's time went, and whether it was work
        m = nth(p, pattern, n)
        print(f"GROUNDS {what}: {m.group(0) if m else 'no line for ' + pattern}", flush=True)
    b = [int(x) for x in built.groups()]
    COSTS.append((what, b[0], b[1], b[2], b[3]))
    p.check(b[2] <= SLOW_MS, f"{what}: a step of {b[2]} ms on the server thread (at most {SLOW_MS})")
    p.check(b[4] > 0, f"{what}: no column levelled")
    if not p.check(audit, f"{what}: no audit line"):
        return
    a = [int(x) for x in audit.groups()]
    cols, steps, before, edge, faced, bare, ramps, ramps0, pillars, holes, wet, houses, looted, chests, blocked, trees, floating, fire, \
        unfit = a
    p.check(cols > 20000, f"{what}: only {cols} columns audited")
    p.check(bare <= STEP_SHARE * cols, f"{what}: {bare} bare steps further in than the edge (of {cols} columns; {before} before)")
    p.check(ramps <= RAMP_SHARE * cols, f"{what}: {ramps} one-block steps in ramps (of {cols} columns; {ramps0} before)")
    p.check(pillars == 0 and holes == 0, f"{what}: {pillars} loose columns and {holes} holes")
    p.check(wet == 0, f"{what}: {wet} blocks of water standing in the air")
    p.check(houses >= MIN_HOUSES, f"{what}: only {houses} houses")
    p.check(chests >= houses and looted == chests, f"{what}: {looted} of {chests} chests with loot ({houses} houses)")
    p.check(blocked == 0, f"{what}: {blocked} doors blocked")
    p.check(trees >= MIN_TREES, f"{what}: only {trees} cherry trees")
    p.check(floating == 0, f"{what}: {floating} cherry trees floating")


def world_a(work, launcher, fails, texts):
    config(work, False, False)
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    placed = False
    try:
        placed = place_house(p)
        if placed:
            p.check(p.wait_log(r"herald's house grounds: disabled", 60), "A: no 'grounds disabled' with the option off")
            config(work, True, False)
            srv.ctx.run("heraldia reload", r"reload|recarg|Reload")
            srv.ctx.ticks(100)
            p.check(p.times(BUILDING) == 0, "A: the grounds were built on their own in a world whose town was already there")
    finally:
        srv.stop()
        texts.append(srv.ctx.log())
    if not placed:
        return
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    try:
        srv.ctx.ticks(200)
        p.check(p.times(BUILDING) == 0, "A: after restarting, the grounds were built on their own")
        srv.ctx.run("heraldia herald grounds", r"Preparing the Herald's House grounds|Preparando los alrededores|disabled|desactivados")
        check_build(p, 1, "A (command, roads off)")
        before = p.times(BUILDING)
        srv.ctx.run("heraldia herald grounds", r"already prepared|ya están preparados|being built|construyendo algo")
        srv.ctx.ticks(40)
        p.check(p.times(BUILDING) == before, "A: a second /heraldia herald grounds built something again")
    finally:
        srv.stop()
        texts.append(srv.ctx.log())


def world_b(work, launcher, fails, texts):
    shutil.rmtree(os.path.join(work, "world"), ignore_errors=True)
    config(work, True, True)
    srv = Server(work, launcher)
    p = Test(srv.ctx, fails)
    try:
        if not place_house(p):
            return
        check_build(p, 1, "B (new world, after the roads)")
        log = srv.ctx.log()
        r, g = re.search(ROADS_BUILT, log), re.search(BUILDING, log)
        p.check(r and g and r.start() < g.start(), "B: the grounds did not wait for the roads")
        ra = re.search(ROADS_AUDIT, log)
        if p.check(ra, "B: no roads' audit"):
            cols, blocked, unpaved, steps, orphans = (int(x) for x in ra.groups())
            p.check(blocked == unpaved == steps == orphans == 0,
                    f"B: the roads' audit: {blocked} blocked, {unpaved} not paved, {steps} steps, {orphans} hanging leaves")
    finally:
        srv.stop()
        texts.append(srv.ctx.log())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-alrededores"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.rmtree(os.path.join(a.work, "world"), ignore_errors=True)
    fails, texts = [], []
    t0 = time.monotonic()
    world_a(a.work, launcher, fails, texts)
    world_b(a.work, launcher, fails, texts)
    for bad in ("Registry loading errors", "at io.github.albertosa23", "grounds: step", "missing template", "the plan failed"):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    for text in texts:                                  # every step over the mod's own "slow" mark, with its clock and work times
        for m in re.finditer(SLOW_STEP, text):
            print(f"SLOW STEP: {m.group(0)}", flush=True)
    for what, ticks, ms, slowest, plan in COSTS:
        print(f"COST {what}: {ticks} ticks, {ms} ms on the server thread, the slowest step {slowest} ms (the plan {plan} ms off it)")
    print(f"HERALD GROUNDS: {time.monotonic() - t0:.0f} s;", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
