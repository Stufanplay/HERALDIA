"""Medium structures (tools/gen/mediums) on a real 26.3 dedicated server, with the default configuration.

Usage: python3 tools/smoke/medium_structures.py --jar build/libs/heraldia-X.jar [--work build/smoke-estructuras-medianas]
Checks:
- the log: the medium structures rule and the grid of each type with its default spacing, its biome search and, in
  the strip-biome ones (fisherman), the neighbours it asks for (bioma_vecinos);
- /locate of each type (#heraldia:medianas/<type>) from several points, at a reasonable distance, and from each one
  /heraldia info nearby: no village or unique structure closer than mediums.distancia_aldeas_unicas_bloques nor another medium structure of
  another type closer than mediums.distancia_minima.bloques (info nearby gives the closest one of each grid with the generation
  rules); then it is really generated (forceload) and the structure is where /locate said;
- /place template of each variant (on a slab): each container with its table (also the templete's vessels), the
  expected entities (tag heraldia_mediana.<type>), still water (the mill's channel, irrigation ditches, the templete's well:
  it is still a source and does not flow) and the villagers: the inhabitants with AI, the wizard still, all with their trades;
- the inhabitants settle on the seed's real terrain: every structure of an inhabited kind that /locate finds is generated
  and its villagers take their workstation in the morning and their bed at night and sleep (check_settled; summary line
  HABITANTES);
- /place structure of each style (the pool and the structure load) and its time;
- loot spawn of each table (the hermitage's journal is a written book) and /heraldia info with its summary.
Exit code 0 if everything passes.
"""
import argparse, json, math, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
import mediums                      # noqa: E402  (the generator: types, templates and loot)
from pack import Registry           # noqa: E402

POINTS = [(0, 0), (3000, -2000), (-4000, 3500)]
LOCATE_MAX = 4000                    # blocks: with the default spacing (700-900 per type) it is more than enough
ZONE, DISTANCE = 256, 192           # default values (options.py)
PLACE_X, PLACE_Z, STEP = 30000, 30000, 48


def templates():
    reg = Registry()
    for mid, _ in mediums.modules():
        mediums.build(reg, mid)
    assert not reg.warnings, reg.warnings
    return {n: t for n, t in reg.templates.items() if n.startswith("medianas/")}


SHULKER_SETTLE_S = 4       # a shulker with nothing to hold on to has let go well within this


def forceload(ctx, x0, z0, x1, z1, remove=False):
    ctx.run(f"forceload {'remove' if remove else 'add'} {x0} {z0} {x1} {z1}", r"Marked|[Aa]dded|[Rr]emoved|force|already|[Uu]nmarked")


def info_near(ctx, x, z, radius):
    """{id: (distance, x, z)} from /heraldia info nearby at x, z."""
    m = ctx.run(f"execute positioned {x} 64 {z} run heraldia info nearby {radius}",
                r"info nearby \d+ en [^:]+: \d+ estructuras en (\d+) ms")
    if not m.lastindex:
        return None
    return {g[0]: (int(g[1]), int(g[2]), int(g[3])) for g in s.INFO_LINE.findall("".join(s.drain(ctx)))}


def check_locate(ctx, kinds):
    fails, timings = [], []
    for mid in kinds:
        found_count = 0
        for x, z in POINTS:
            t0 = time.monotonic()
            m = ctx.run(f"execute positioned {x} 64 {z} run locate structure #heraldia:medianas/{mid}",
                        r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
            timings.append(time.monotonic() - t0)
            if not m.group(1):
                fails.append(f"/locate does not find {mid} from {x}, {z}")
                continue
            px, pz = int(m.group(1)), int(m.group(2))
            d = math.dist((x, z), (px, pz))
            print(f"{mid} from {x}, {z}: at {px}, {pz} {d:.0f} blocks away ({timings[-1]:.2f} s)")
            if d > LOCATE_MAX:
                fails.append(f"{mid} from {x}, {z} at {d:.0f} blocks (> {LOCATE_MAX})")
            found_count += 1
            nearby_flag = info_near(ctx, px, pz, 600)
            if nearby_flag is None:
                fails.append(f"/heraldia info nearby from {mid} at {px}, {pz} does not respond")
                continue
            for sid, (dist, *_) in nearby_flag.items():
                if ":minas/" in sid:                          # mine entrances: they yield to medium structures at this distance
                    if dist < DISTANCE:
                        fails.append(f"{mid} at {px}, {pz} {dist} blocks from the mine {sid} (< {DISTANCE})")
                elif ":costa/" in sid:                        # lighthouses and wrecks: they yield to mediums at this distance
                    if dist < DISTANCE:
                        fails.append(f"{mid} at {px}, {pz} {dist} blocks from the coast structure {sid} (< {DISTANCE})")
                elif ":medianas/" not in sid:                 # villages (heraldia:aldeas or their style) and unique structures
                    if dist < ZONE:
                        fails.append(f"{mid} at {px}, {pz} {dist} blocks from {sid} (< {ZONE})")
                elif f"medianas/{mid}" not in sid and dist < DISTANCE:
                    fails.append(f"{mid} at {px}, {pz} {dist} blocks from {sid} (< {DISTANCE})")
            # the first one is really generated: the start is where /locate said, and for the kinds with inhabitants it is
            # a sample, on the seed's real terrain, of whether its villagers settle; with --stay, the other points too (and
            # the three-day stay at the first): 18 samples instead of 6, and about 10 more minutes, not in CI
            if (x, z) == POINTS[0] or (STAY and mid in INHABITED):
                r = ROAM if mid in INHABITED else 32      # inhabitants stroll by day: their area keeps ticking
                forceload(ctx, px - r, pz - r, px + r - 1, pz + r - 1)
                if not wait_generated(ctx, px, pz, mid):
                    fails.append(f"{mid}: /locate gives {px}, {pz} but nothing has been generated there")
                elif mid in INHABITED:
                    fails += check_settled(ctx, mid, px, pz, long_stay=STAY and (x, z) == POINTS[0])
                forceload(ctx, px - r, pz - r, px + r - 1, pz + r - 1, remove=True)
        if not found_count:
            fails.append(f"no {mid}")
    if timings:
        print(f"/locate of medium structures: {len(timings)} searches, mean {sum(timings) / len(timings):.2f} s, max {max(timings):.2f} s")
    return fails


def wait_generated(ctx, x, z, mid):
    """/heraldia info here next to the start (the piece goes toward one quadrant or another depending on its rotation), at the height of the
    terrain (inside the piece's box), says that you are in the medium structure. Only looks at chunks that are already loaded."""
    end = time.monotonic() + s.UNTIL_S
    while time.monotonic() < end:
        for dx, dz in ((6, 6), (-6, 6), (6, -6), (-6, -6)):
            m = ctx.run(f"execute positioned {x + dx} 0 {z + dz} positioned over world_surface positioned ~ ~-2 ~ "
                        f"run heraldia info here",
                        r"\((heraldia:[^)]+)\)|no hay ninguna|no Heraldia|not loaded|no está cargada")
            if m.group(1) and f"medianas/{mid}/" in m.group(1):
                return True
        time.sleep(2)
    return False


def inhabited():
    """Kinds whose templates hold inhabitants (mediums/_inhabitants.py)."""
    from mediums import _inhabitants as inh
    out = set()
    for name, t in templates().items():
        if any(inh.is_inhabitant(n) for *_, n in t.entities):
            out.add(name.split("/")[1])
    return out


INHABITED = inhabited()
STAY = False                         # --stay: every located structure settle-checked and the three-day stay (slow; not in CI)
SETTLED = []                         # (kind, x, z, villagers, with job site, with home, slept): the summary
STAYED = []                          # (kind, x, z, villagers, alive, at home, with job site, with home, days)


def check_settled(ctx, mid, px, pz, long_stay=False):
    """On the seed's real terrain: every inhabitant villager of the structure /locate found takes its workstation in the
    working hours and its bed at night, and sleeps in it (Brain memories job_site, home and last_slept, which the game
    saves). A variant without inhabitants (the watchtower with the archer) counts 0 and does not fail."""
    sel = (f"@e[type=minecraft:villager,tag=heraldia_habitante,tag=heraldia_mediana.{mid},"
           f"x={px - 48},y=-64,z={pz - 48},dx=96,dy=420,dz=96]")
    if not ctx.until(f"execute if entity {sel}", timeout=20):
        SETTLED.append((mid, px, pz, 0, 0, 0, 0))
        print(f"{mid} at {px}, {pz}: variant without inhabitant villagers")
        return []
    wait_loaded(ctx, px, pz, ROAM)
    n = ctx.count(sel)
    with_mem = lambda mem: ctx.count(f"{sel[:-1]},nbt={{Brain:{{memories:{{\"minecraft:{mem}\":{{}}}}}}}}]")
    ctx.run("time set 2000", r"Set the time|time to|Set minecraft:\w+ to")            # morning: off to work
    end = time.monotonic() + 120
    while with_mem("job_site") < n and time.monotonic() < end:
        time.sleep(3)
    job = with_mem("job_site")
    # to nightfall by running the day, not by jumping the clock: a jump wakes a sleeping villager abruptly
    sprint(ctx, 11000)
    nights = 1
    while True:
        end = time.monotonic() + 150
        while (with_mem("home") < n or with_mem("last_slept") < n) and time.monotonic() < end:
            time.sleep(3)
        home, slept = with_mem("home"), with_mem("last_slept")
        if (home == n and slept == n) or nights == 2:
            break
        sprint(ctx, 24000)              # two villagers wanting the same bed: the one who loses tries again later
        nights += 1
    SETTLED.append((mid, px, pz, n, job, home, slept))
    print(f"{mid} at {px}, {pz}: {n} inhabitants, {job} with their workstation, {home} with their bed, {slept} asleep "
          f"(night {nights})")
    fails = []
    if job < n or home < n or slept < n:
        fails.append(f"{mid} at {px}, {pz}: of {n} inhabitants, {job} took a workstation, {home} a bed and {slept} slept")
        diagnose_settled(ctx, sel, n)
    if long_stay:
        fails += check_stay(ctx, mid, px, pz, sel, n, with_mem)
    return fails


_HOME = r"entity data: \[I; (-?\d+), (-?\d+), (-?\d+)\]|Found no elements|No entity was found|not found"


def diagnose_settled(ctx, sel, n):
    """On a settle failure, where each inhabitant is and which bed it remembers (none: it never claimed one or gave it
    up), so that a red run says whether it was stuck outside a wall (docs/LESSONS.md, "Pending bugs": the hunters'
    lodge failed twice in CI and could not be reproduced)."""
    for k in range(n):
        one = f"{sel[:-1]},tag=!heraldia_diag,limit=1]"
        ctx.run(f"tag {one} add heraldia_diag{k}", r"Added tag|Could not|No entity")
        ctx.run(f"tag @e[tag=heraldia_diag{k}] add heraldia_diag", r"Added tag|Could not|No entity")
        me = f"@e[tag=heraldia_diag{k},limit=1]"
        name = ctx.run(f"data get entity {me} VillagerData.profession", r"entity data: \"([^\"]+)\"|No entity|not found")
        home = ctx.run(f"data get entity {me} Brain.memories.\"minecraft:home\".value.pos", _HOME)
        job = ctx.run(f"data get entity {me} Brain.memories.\"minecraft:job_site\".value.pos", _HOME)
        print(f"DIAG inhabitant {name.group(1) if name.lastindex and name.group(1) else '?'} at {ctx.pos(me)}: home "
              f"{home.group(1, 2, 3) if home.group(1) else None}, workstation {job.group(1, 2, 3) if job.group(1) else None}")
    for k in range(n):
        ctx.run(f"tag @e[tag=heraldia_diag{k}] remove heraldia_diag{k}", r"Removed tag|Could not|No entity")
    ctx.run("tag @e[tag=heraldia_diag] remove heraldia_diag", r"Removed tag|Could not|No entity")


STAY_TICKS = 3 * 24000               # three more in-game days with /tick sprint, from one nightfall to another


def wait_loaded(ctx, px, pz, r, timeout=180):
    """Waits until the forceloaded area around the structure is really loaded (corners and center). Running the clock
    (/tick sprint) while it still loads is not what a player sees: the villagers' paths fail in the chunks that are not
    there yet, and after a while unreachable (SetWalkTargetFromBlockMemory, 26.3) they release their bed and workstation."""
    pts = [(px + 8, pz + 8), (px - r + 8, pz - r + 8), (px + r - 8, pz - r + 8), (px - r + 8, pz + r - 8), (px + r - 8, pz + r - 8)]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if all(ctx.test(f"execute if loaded {x} 64 {z}") for x, z in pts):
            time.sleep(5)                 # and a moment for the entities of the last ones
            return True
        time.sleep(3)
    return False


SPRINT_STEP = 6000


def sprint(ctx, ticks):
    """Runs `ticks` game ticks at full speed (/tick sprint; its reply only comes at the end: the game time says when).
    Returns the ticks really run."""
    t0 = ctx.gametime()
    end = time.monotonic() + 900
    while ctx.gametime() < t0 + ticks and time.monotonic() < end:
        # in steps of SPRINT_STEP: right after one 72,000-tick sprint the hermit read as having an empty brain (no
        # bed, workstation or bell; back after a restart, so nothing was lost); in steps it never happened (4 days)
        step = min(SPRINT_STEP, t0 + ticks - ctx.gametime())
        t1 = ctx.gametime()
        s.send(ctx.proc, f"tick sprint {step}")
        while ctx.gametime() < t1 + step and time.monotonic() < end:
            time.sleep(2)
    return ctx.gametime() - t0
ROAM = 80                             # blocks forceloaded around an inhabited structure (by day they stroll 20-35 blocks
                                      # from it, as any villager; in a smaller area they stop ticking at its edge)
STAY_BOX = 24                         # blocks around the located chunk: the piece (at most 21 x 21) plus a few


def check_stay(ctx, mid, px, pz, sel, n, with_mem):
    """Invulnerable villagers with AI stay home: after STAY_TICKS run at full speed, ending at nightfall, they are all
    still alive, back inside the structure's box within a few minutes (not wandered off, fallen or stuck) and still
    remember their bed and workstation. By day they stroll about like any villager; at night they must be home."""
    t_start = time.monotonic()
    days = sprint(ctx, STAY_TICKS) / 24000
    near = (f"@e[type=minecraft:villager,tag=heraldia_habitante,tag=heraldia_mediana.{mid},"
            f"x={px + 8 - STAY_BOX},y=-64,z={pz + 8 - STAY_BOX},dx={2 * STAY_BOX},dy=420,dz={2 * STAY_BOX}]")
    # at nightfall they head home; a villager that released its bed or workstation (a path that failed for too long,
    # 26.3) takes it again: a few real minutes for both
    end = time.monotonic() + 240
    while (ctx.count(near) < n or with_mem("home") < n or with_mem("job_site") < n) and time.monotonic() < end:
        time.sleep(3)
    alive, home_now, job, home = ctx.count(sel), ctx.count(near), with_mem("job_site"), with_mem("home")
    STAYED.append((mid, px, pz, n, alive, home_now, job, home, days))
    print(f"{mid} at {px}, {pz}: after {days:.1f} days, {alive} of {n} inhabitants alive, {home_now} inside the structure, "
          f"{job} with their workstation and {home} with their bed ({time.monotonic() - t_start:.0f} s)")
    if days < 2.9 or alive < n or home_now < n or job < n or home < n:
        return [f"{mid} at {px}, {pz}: after {days:.1f} days, {alive}/{n} alive, {home_now}/{n} at home, {job}/{n} with a "
                f"workstation, {home}/{n} with a bed"]
    return []


def check_templates(ctx, ts):
    fails = []
    for k, (name, t) in enumerate(sorted(ts.items())):
        x, z = PLACE_X + (k % 5) * STEP, PLACE_Z + (k // 5) * STEP
        y = 100
        forceload(ctx, x - 8, z - 8, x + 47, z + 47)
        sx, _, sz = t.size()       # slab underneath: the water of row y = 0 (channels, ditches, wells) rests as on the ground
        ctx.run(f"fill {x} {y - 1} {z} {x + sx - 1} {y - 1} {z + sz - 1} minecraft:stone", r"Successfully filled|No blocks")
        m = ctx.run(f"place template heraldia:{name} {x} {y} {z}", r"Loaded template|Failed")
        if "Loaded" not in m.group(0):
            fails.append(f"{name}: place template: {m.string.strip()}")
            continue
        for (bx, by, bz), (st, nbt) in t.blocks.items():
            lt = nbt and nbt.get("LootTable")
            if lt and not ctx.block((x + bx, y + by, z + bz), f"{st.split('[')[0]}{{LootTable:\"{lt}\"}}"):
                fails.append(f"{name}: container {lt} is missing at {bx, by, bz}")
        n = len(t.entities)
        if n:
            sel = f"@e[tag=heraldia_mediana.{name.split('/')[1]},x={x},y={y},z={z},dx=40,dy=30,dz=40]"
            if not ctx.until(f"execute if entity {sel}"):
                fails.append(f"{name}: its entities do not appear")
            else:
                end = time.monotonic() + 10          # the last ones of the template may join a moment later
                while ctx.count(sel) != n and time.monotonic() < end:
                    time.sleep(1)
                if ctx.count(sel) != n:
                    fails.append(f"{name}: {ctx.count(sel)} entidades, esperadas {n}")
            # a shulker stays where the template puts it: one attached to a block whose face is not full lets go as it
            # loads and teleports within eight blocks (the midlands wharf guard did, every time, sometimes out of the
            # box above: that was this test's intermittent failure, and a mob that was never where it was placed)
            posts = [(ex, ey, ez) for ex, ey, ez, e in t.entities if e.get("id") == "minecraft:shulker"]
            if posts:
                time.sleep(SHULKER_SETTLE_S)
            for ex, ey, ez in posts:
                at = f"x={x + int(ex) + 0.5},y={y + int(ey)},z={z + int(ez) + 0.5},distance=..0.8"
                if ctx.count(f"@e[type=minecraft:shulker,{at}]") != 1:
                    fails.append(f"{name}: the shulker placed at {int(ex), int(ey), int(ez)} is not at its post")
        fails += check_water(ctx, name, t, (x, y, z))
        fails += check_villagers(ctx, name, t, (x, y, z))
        forceload(ctx, x - 8, z - 8, x + 47, z + 47, remove=True)
    return fails


def check_water(ctx, name, t, origin):
    """The template's water (all sources, between blocks) does not flow: a few ticks later, each water cell is still
    a source and the surrounding air ones are still empty."""
    water = [p for p, (st, _) in t.blocks.items() if st.split("[")[0] == "minecraft:water"]   # not the cauldrons
    if not water:
        return []
    time.sleep(2)                         # water spreads every 5 ticks
    x0, y0, z0 = origin
    fails = []
    for (x, y, z) in water:
        if not ctx.block((x0 + x, y0 + y, z0 + z), "minecraft:water[level=0]"):
            fails.append(f"{name}: the water at {x, y, z} is no longer a source")
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, 1, 0)):
            v = t.get(x + dx, y + dy, z + dz)
            if v in (None, "minecraft:air") and not ctx.block((x0 + x + dx, y0 + y + dy, z0 + z + dz), "minecraft:air"):
                fails.append(f"{name}: the water at {x, y, z} flows toward {x + dx, y + dy, z + dz}")
    return fails


def check_villagers(ctx, name, t, origin):
    """The villagers of the medium structures: the inhabitants (innkeeper, gardener, miller, fisherman, hunters, lookout,
    hermit) with AI, the rest (the wizard) still; all invulnerable and with their trades."""
    fails = []
    x0, y0, z0 = origin
    mid = name.split("/")[1]
    for *_, n in t.entities:
        if n["id"] != "minecraft:villager":
            continue
        depth = n["VillagerData"]["profession"]
        lives = "heraldia_habitante" in n.get("Tags", [])
        sel = (f"@e[type=minecraft:villager,tag=heraldia_mediana.{mid},x={x0},y={y0},z={z0},dx=40,dy=30,dz=40,"
               + ("tag=heraldia_habitante,nbt=!{NoAI:1b}," if lives else "")
               + f"nbt={{{'' if lives else 'NoAI:1b,'}Invulnerable:1b,VillagerData:{{profession:\"{depth}\"}}}}]")
        if not ctx.until(f"execute if entity {sel}"):
            fails.append(f"{name}: the {'living' if lives else 'still'}, invulnerable villager {depth} is missing")
            continue
        first_item = n["Offers"]["Recipes"][0]["sell"]["id"]
        if not ctx.test(f"execute if entity {sel[:-1]},nbt={{Offers:{{Recipes:[{{sell:{{id:\"{first_item}\"}}}}]}}}}]"):
            fails.append(f"{name}: the villager {depth} does not have its trades (sells {first_item})")
    return fails


def check_structures(ctx):
    fails, timings = [], {}
    k = 0
    for mid, mod in mediums.modules():
        if mediums.dimension(mod) != "overworld":
            continue                                       # in their dimension: tools/smoke/nether_end.py
        for style in mod.STYLES:
            x, z = PLACE_X + k * STEP, PLACE_Z - 400
            k += 1
            forceload(ctx, x - 8, z - 8, x + 47, z + 47)
            for _ in range(s.PLACE_ATTEMPTS):
                t0 = time.monotonic()
                m = ctx.run(f"place structure heraldia:medianas/{mid}/{style} {x} ~ {z}", r"Generated structure|not loaded(?! yet)")
                timings[f"{mid}/{style}"] = time.monotonic() - t0
                if "not loaded" not in m.group(0):
                    break
                time.sleep(s.PLACE_RETRY_S)
            if "Generated" not in m.group(0):
                fails.append(f"place structure {mid}/{style}: {m.string.strip()}")
            forceload(ctx, x - 8, z - 8, x + 47, z + 47, remove=True)
    if timings:
        print("/place structure de medianas (s): " + ", ".join(f"{k} {v:.2f}" for k, v in timings.items()))
    return fails


def check_loot(ctx):
    fails = []
    forceload(ctx, PLACE_X, PLACE_Z, PLACE_X, PLACE_Z)      # loose items are only seen in a loaded chunk
    for mid, mod in mediums.modules():
        for tbl in mod.LOOT:
            m = ctx.run(f"loot spawn {PLACE_X} 120 {PLACE_Z} loot heraldia:medianas/{mid}/{tbl}", r"Dropped \d+|No items")
            if not m.group(0).startswith("Dropped"):
                fails.append(f"loot heraldia:medianas/{mid}/{tbl}: {m.string.strip()}")
    if not ctx.until(f"execute if entity @e[type=minecraft:item,nbt={{Item:{{id:\"minecraft:written_book\"}}}}]") \
            and not _diary(ctx):
        fails.append("the hermitage cell chest does not give the journal (written book)")
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    forceload(ctx, PLACE_X, PLACE_Z, PLACE_X, PLACE_Z, remove=True)
    return fails


def _diary(ctx):
    ctx.run(f"loot spawn {PLACE_X} 120 {PLACE_Z} loot heraldia:medianas/ermita/celda", r"Dropped \d+|No items")
    return ctx.until(f"execute if entity @e[type=minecraft:item,nbt={{Item:{{id:\"minecraft:written_book\"}}}}]", timeout=10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-estructuras-medianas"))
    ap.add_argument("--stay", action="store_true",
                    help="settle-check every located inhabited structure (not only the first of each kind) and run each kind three "
                         "in-game days to check its villagers stay home (slow; not in CI)")
    a = ap.parse_args()
    global STAY
    STAY = a.stay
    os.makedirs(a.work, exist_ok=True)
    ts = templates()
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump({}, f)                 # default configuration
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen, fails = queue.Queue(), [], []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        log = ctx.log()
        kinds = [mid for mid, _ in mediums.modules()]
        overworld_ids = [mid for mid, mod in mediums.modules() if mediums.dimension(mod) == "overworld"]
        for mid, mod in mediums.modules():
            if mid not in overworld_ids:
                continue                                   # those of the Nether and the End: tools/smoke/nether_end.py
            sp = round(mod.SEPARATION / 16)
            vec = getattr(mod, "BIOME_NEIGHBORS", None)    # strip biomes (beaches): the search asks for fewer neighbours
            m = re.search(rf"rejilla medianas/{mid}: activada, cada {sp} chunks \(separación mínima {(DISTANCE + 15) // 16}, "
                          r"origen desplazado\)([^\n]*)", log)
            remainder = m.group(1) if m else ""
            neighbors = re.search(r", (\d) de 9 vecinos", remainder)
            if not m or f"candidata en el bioma #heraldia:medianas/{mid}" not in remainder \
                    or (int(neighbors.group(1)) if neighbors else None) != (vec if vec and vec != 6 else None):
                fails.append(f"the log is missing the grid of medianas/{mid} (every {sp} chunks, bioma_vecinos {vec}): {remainder}")
        ctx.run("gamerule spawn_mobs false", r"Gamerule|set to|now")
        fails += check_templates(ctx, ts)
        fails += check_structures(ctx)
        fails += check_loot(ctx)
        fails += check_locate(ctx, overworld_ids)
        if SETTLED:
            n, job, home, slept = (sum(r[k] for r in SETTLED) for k in (3, 4, 5, 6))
            print(f"HABITANTES: {len(SETTLED)} structures on the seed's terrain, {n} inhabitant villagers: {job} with "
                  f"their workstation, {home} with their bed, {slept} asleep")
            if STAYED:
                n, alive, home_now = (sum(r[k] for r in STAYED) for k in (3, 4, 5))
                print(f"HABITANTES tras {min(r[8] for r in STAYED):.1f} días: {len(STAYED)} structures, {n} inhabitants, "
                      f"{alive} alive, {home_now} still inside their structure")
            if not re.search(r"Heraldia: habitantes de las medianas: activados", ctx.log()):
                fails.append("the log does not say the medium structures' inhabitants are on")
        if not re.search(rf"estructuras medianas: activadas, {len(kinds)} tipos, frecuencia 100 %, a {ZONE} bloques de aldeas "
                         rf"y únicas y a {DISTANCE} entre ellas", ctx.log()):
            fails.append("the log is missing the medium structures rule with its default configuration")
        m = ctx.run("heraldia info", r"Registered structures: \d+ \(\d+ villages, \d+ unique, (\d+) medium and \d+ mine|"
                                     r"Estructuras registradas: \d+ \(\d+ de aldeas, \d+ únicas, (\d+) medianas y \d+ ")
        n = m.group(1) or m.group(2) if m.lastindex else None
        expected_counts = sum(len(mod.STYLES) for _, mod in mediums.modules())
        if n is None or int(n) != expected_counts:
            fails.append(f"/heraldia info: {n} medianas registradas, esperadas {expected_counts}: {m.string.strip()}")
        text = "".join(ctx.seen[-40:])
        n = len(kinds)
        if not re.search(rf"Medium structures: enabled; {n} of {n} types enabled|Estructuras medianas: activada; {n} de {n} tipos", text):
            fails.append("/heraldia info does not summarize the medium structures")
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            proc.wait(timeout=120)
    print("MEDIANAS:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
