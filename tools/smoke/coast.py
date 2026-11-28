"""Coastal lighthouses and shipwrecks (tools/gen/costa, T42) on a real 26.3 dedicated server (deterministic: the fixed seed
of server_smoke and fixed search origins).

Usage: python3 tools/smoke/coast.py --jar build/libs/heraldia-X.jar [--work build/smoke-costa]
Two starts of the same world (with -Dheraldia.depurar.costa=true: each chosen site goes to the log, with its anchor, its height
and which way the sea faces):
1. With the default configuration:
   - the log: the grid of both types (spacing, shifted origin, candidate on the beaches) and the coast rule;
   - /locate of each type from several origins, which really generates it (forceload) where /locate said, and checks it
     block by block against the generator's template rotated as in the game: the lighthouse on land (what is under the
     platform is not water), the top light on (redstone lamp on its redstone block, and still
     on 5 s later), the pier over water and the chest with its table; the shipwreck with the keel, the mast,
     the cabin chest and, depending on the variant, the bow on land (grounded) or the flooded hold with its anchored drowned
     (half-sunk); in both, no water above sea level in its box (nothing spills);
   - /heraldia info nearby from each one: no village or unique structure within mediums.distancia_aldeas_unicas_bloques,
     nor a medium structure, a mine or another coastal one of a different type within mediums.distancia_minima.bloques;
   - /place structure of the four variants (temperate style) next to beaches given by /locate biome: on the shore, with the
     same checks;
   - loot spawn of each table, and /heraldia info with its line and the 16 coastal structures.
2. With faros.activado = false and naufragios.separacion_bloques = 2048: /locate no longer gives any new lighthouse (only the one already
   generated, which stays as in an existing world), and the shipwreck
   grid comes out with the new spacing.
Exit code 0 if everything passes.
"""
import argparse, glob, json, math, os, queue, re, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
import shore as coast                                    # noqa: E402  (the generator: templates, loot and footprints)
from shore import constructions                         # noqa: E402

SEA = 63
ZONE, DISTANCE = 256, 192                      # options.py, by default
# /locate of each type from these origins (blocks); the variants come out depending on the coast and the cell's chance.
ORIGINS = {"faro": [(0, 0), (-3000, 2000)], "naufragio": [(0, 0), (3000, -2000)]}
LOCATE_MAX = 12000
# /place of each variant next to a beach (the one /locate biome gives from each origin, in order, until the shore
# suits the variant: not every beach has flat land for the lighthouse or a shoal for the shipwreck)
PLACE = [(20000, 20000), (-20000, 20000), (20000, -20000), (-20000, -20000), (24000, 0), (-24000, 0), (0, 24000),
         (0, -24000)]
VARIANTS = [("faro", "a"), ("faro", "b"), ("naufragio", "a"), ("naufragio", "b")]
DIRS = {"south": (0, 1), "north": (0, -1), "east": (1, 0), "west": (-1, 0)}
CCW = {"south": "east", "east": "north", "north": "west", "west": "south"}
SITE = re.compile(r"Heraldia: costa \((faro|encallado|hundido)\) en (-?\d+) (-?\d+) (-?\d+) hacia el (\w+) \(nota (\d+)(, sin orilla)?\)")
MODE_VARIANT = {"faro": None, "encallado": "a", "hundido": "b"}


def start_up(work, jar, cfg, clean_up):
    launcher = s.prepare(work, jar, s.gradle_properties()) if clean_up else os.path.join(work, glob.glob(
        os.path.join(work, "fabric-server-*.jar"))[0])
    cfg = dict(cfg, arena={"generar_en_mundos_nuevos": False}, update_check={"activado": False},
               casa_heraldo={"generar_en_mundos_nuevos": False})
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)
    proc = subprocess.Popen(["java", "-Xmx2G", "-Dheraldia.depurar.costa=true", "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    ctx = s.Context(proc, lines, seen)
    ctx.run("gamerule spawn_mobs false", r"Gamerule|set to")
    return proc, ctx


def halt(proc):
    if proc.poll() is None:
        s.send(proc, "stop")
        proc.wait(timeout=180)


def forceload(ctx, x0, z0, x1, z1, remove=False):
    ctx.run(f"forceload {'remove' if remove else 'add'} {x0} {z0} {x1} {z1}", r"Marked|[Aa]dded|[Rr]emoved|force|already|[Uu]nmarked")


def load_data(ctx, x, z, r=64):
    forceload(ctx, x - r, z - r, x + r - 1, z + r - 1)
    for px, pz in ((x - r, z - r), (x + r - 1, z + r - 1), (x - r, z + r - 1), (x + r - 1, z - r)):
        if not ctx.until(f"execute if loaded {px} 64 {pz}", timeout=300):
            return False
    ctx.ticks(20)
    return True


class Site:
    """A placed lighthouse or shipwreck: its anchor, the height of its row 0 and which way the sea faces; maps the template."""

    def __init__(self, m):
        self.mode, self.x, self.y, self.z, self.sea = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        self.no_shore = bool(m.group(7))

    def world(self, p):
        """Design point (x across, y, z toward the sea; the anchor at 0, 0) in the world."""
        dx, dz = DIRS[self.sea]
        ex, ez = DIRS[CCW[self.sea]]
        x, y, z = p
        return self.x + dx * z + ex * x, self.y + y, self.z + dz * z + ez * x

    def __repr__(self):
        return f"{self.mode} en {self.x} {self.y} {self.z} hacia el {self.sea}"


def sites(ctx, start=0):
    return [Site(m) for m in SITE.finditer("".join(ctx.seen[start:]))]


def water_above(ctx, a, b):
    """Water blocks above sea level in the box from a to b (water fill over water: it changes nothing)."""
    x0, x1 = sorted((a[0], b[0]))
    z0, z1 = sorted((a[2], b[2]))
    y1 = max(a[1], b[1])
    m = ctx.run(f"fill {x0} {SEA} {z0} {x1} {y1} {z1} minecraft:water replace minecraft:water",
                r"Successfully filled (\d+)|No blocks were filled|[Tt]oo many blocks")
    return int(m.group(1)) if m.lastindex else 0


def check_lighthouse(ctx, st, v):
    """The lighthouse of variant v (or whichever, with v None) placed at st; returns the failures."""
    o, _, _ = coast.construction("faro", "templada", v or "a")
    fails = []
    lx, ly, lz = st.world(o.light)
    if not ctx.until(f"execute if block {lx} {ly} {lz} minecraft:redstone_lamp[lit=true]", timeout=60):
        return [f"{st}: sin la lámpara encendida en {lx} {ly} {lz}"]
    if not ctx.block((lx, ly - 1, lz), "minecraft:redstone_block"):
        fails.append(f"{st}: the lamp is not on its redstone block")
    ctx.ticks(100)
    if not ctx.block((lx, ly, lz), "minecraft:redstone_lamp[lit=true]"):
        fails.append(f"{st}: the lamp goes out")
    if ly < SEA + 20:
        fails.append(f"{st}: the light at y = {ly} is not visible from afar")
    for p in ((0, -1, -12), (-5, -1, -18), (5, -1, -3)):       # under the platform: land or foundations, never water
        w = st.world(p)
        if ctx.block(w, "minecraft:water") or ctx.block(w, "minecraft:air"):
            fails.append(f"{st}: under the platform at {w} there is water or air")
    cx, _, cz = st.world((0, -1, constructions.DOCK))              # under the end of the pier, the sea
    if not ctx.block((cx, SEA - 1, cz), "minecraft:water") and not st.no_shore:
        fails.append(f"{st}: the pier does not end over water ({cx} {SEA - 1} {cz})")
    if not ctx.block(st.world((0, 0, constructions.DOCK)), "#minecraft:planks"):
        fails.append(f"{st}: the pier is missing")
    place_chest = st.world((-2, 12, constructions.TOWER_Z))
    if not ctx.block(place_chest, 'minecraft:chest{LootTable:"heraldia:costa/faro"}'):
        fails.append(f"{st}: the lighthouse chest is missing at {place_chest}")
    n = water_above(ctx, st.world((-8, 0, -21)), st.world((8, 27, constructions.DOCK + 1)))
    if n:
        fails.append(f"{st}: {n} water blocks above sea level in its box")
    return fails


def check_shipwreck(ctx, st):
    v = MODE_VARIANT[st.mode]
    o, _, _ = coast.construction("naufragio", "templada", v)
    z0, fails = o.bow, []
    keel = st.world((0, 0, z0 + 10))
    if not ctx.until(f"execute if block {' '.join(map(str, keel))} #minecraft:logs", timeout=60):
        return [f"{st}: sin la quilla en {keel}"]
    if not ctx.block(st.world((0, 17, z0 + 12)), "#minecraft:logs"):
        fails.append(f"{st}: no main mast")
    cabin_adv = st.world((-2, 6, z0 + 28))
    if not ctx.block(cabin_adv, 'minecraft:chest{LootTable:"heraldia:costa/camarote"}'):
        fails.append(f"{st}: the cabin chest is missing at {cabin_adv}")
    if v == "b":
        hold = st.world((0, 3, z0 + 5))
        if not ctx.block(hold, "minecraft:water"):
            fails.append(f"{st}: the hold is not flooded ({hold})")
        bx, by, bz = st.world((-2, 2, z0 + 4))
        if not ctx.until(f"execute if entity @e[type=minecraft:drowned,tag=heraldia_anclado,x={bx},y={by},z={bz},distance=..6]", timeout=30):
            fails.append(f"{st}: no anchored drowned in the hold")
        if not ctx.block(st.world((0, -1, z0 + 20)), "minecraft:water") and \
                not ctx.block(st.world((0, -1, z0 + 20)), "#minecraft:logs"):
            pass                                               # under the keel: the sea floor or the extended keel
    else:
        bow = st.world((0, -1, z0 + 3))
        if ctx.block(bow, "minecraft:water") or ctx.block(bow, "minecraft:air"):
            fails.append(f"{st}: the grounded ship's bow is not on land ({bow})")
    n = water_above(ctx, st.world((-5, 0, z0 - 4)), st.world((5, 17, z0 + constructions.HULL_LENGTH)))
    if n:
        fails.append(f"{st}: {n} water blocks above sea level in its box")
    return fails


def info_near(ctx, x, z, radius):
    m = ctx.run(f"execute positioned {x} 64 {z} run heraldia info nearby {radius}", r"info nearby \d+ en [^:]+: \d+ estructuras en (\d+) ms")
    if not m.lastindex:
        return {}
    return {g[0]: (int(g[1]), int(g[2]), int(g[3])) for g in s.INFO_LINE.findall("".join(s.drain(ctx)))}


def check_separation(ctx, kind, x, z):
    fails = []
    for sid, (dist, *_) in info_near(ctx, x, z, 600).items():
        if ":costa/" in sid:
            if f"costa/{kind}" not in sid and dist < DISTANCE:
                fails.append(f"{kind} at {x}, {z} {dist} blocks from {sid} (< {DISTANCE})")
        elif ":medianas/" in sid or ":minas/" in sid:
            if dist < DISTANCE:
                fails.append(f"{kind} at {x}, {z} {dist} blocks from {sid} (< {DISTANCE})")
        elif dist < ZONE:
            fails.append(f"{kind} at {x}, {z} {dist} blocks from {sid} (< {ZONE})")
    return fails


def check_locate(ctx):
    fails, seen_all = [], {}
    for kind, origins in ORIGINS.items():
        for ox, oz in origins:
            t0 = time.monotonic()
            m = ctx.run(f"execute positioned {ox} 64 {oz} run locate structure #heraldia:costa/{kind}",
                        r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
            if not m.group(1):
                fails.append(f"/locate from {ox}, {oz} finds no {kind}")
                continue
            x, z = int(m.group(1)), int(m.group(2))
            d = math.hypot(x - ox, z - oz)
            print(f"{kind}: /locate from {ox}, {oz} at {x}, {z} {d:.0f} blocks away ({time.monotonic() - t0:.1f} s)")
            if d > LOCATE_MAX:
                fails.append(f"{kind} {d:.0f} blocks from {ox}, {oz} (> {LOCATE_MAX})")
            fails += check_separation(ctx, kind, x, z)
            before = len(ctx.seen)
            if not load_data(ctx, x + 8, z + 8, 80):
                fails.append(f"{kind} at {x}, {z}: does not load")
                continue
            cand = [st for st in sites(ctx) if (st.mode == "faro") == (kind == "faro")
                    and abs(st.x - x - 8) <= 64 and abs(st.z - z - 8) <= 64]
            if not cand:
                fails.append(f"{kind} at {x}, {z}: the log does not say where it ended up")
            else:
                st = min(cand, key=lambda c: abs(c.x - x - 8) + abs(c.z - z - 8))
                if any((v.x, v.z) == (st.x, st.z) for v in seen_all.get(kind, [])):
                    print(f"  {st}: same as before")
                    forceload(ctx, x + 8 - 80, z + 8 - 80, x + 8 + 79, z + 8 + 79, remove=True)
                    continue
                seen_all.setdefault(kind, []).append(st)
                f = check_lighthouse(ctx, st, None) if kind == "faro" else check_shipwreck(ctx, st)
                print(f"  {st}: {'bien' if not f else f}")
                fails += f
            forceload(ctx, x + 8 - 80, z + 8 - 80, x + 8 + 79, z + 8 + 79, remove=True)
            del before
    return fails, seen_all


def check_placed(ctx):
    fails, beaches = [], {}
    for kind, v in VARIANTS:
        sid = f"heraldia:{coast.template(kind, 'templada', v)}"
        done = False
        for ox, oz in PLACE:
            if (ox, oz) not in beaches:
                m = ctx.run(f"execute positioned {ox} 64 {oz} run locate biome minecraft:beach",
                            r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
                beaches[(ox, oz)] = (int(m.group(1)), int(m.group(2))) if m.group(1) else None
            if beaches[(ox, oz)] is None:
                continue
            bx, bz = beaches[(ox, oz)]
            if not load_data(ctx, bx, bz, 96):
                fails.append(f"/place {sid} at {bx}, {bz}: does not load")
                continue
            before = len(ctx.seen)
            r = ctx.run(f"place structure {sid} {bx} 64 {bz}", r"Generated structure|Failed to place")
            st = next(iter(sites(ctx, before)), None)
            forceload(ctx, bx - 96, bz - 96, bx + 95, bz + 95, remove=True)
            if not r.group(0).startswith("Generated") or st is None:
                fails.append(f"{sid}: /place: {r.string.strip()}")
                break
            if st.no_shore:
                print(f"/place {sid} next to the beach at {bx}, {bz}: no suitable shore; another beach")
                continue
            load_data(ctx, bx, bz, 96)
            f = check_lighthouse(ctx, st, v) if kind == "faro" else check_shipwreck(ctx, st)
            forceload(ctx, bx - 96, bz - 96, bx + 95, bz + 95, remove=True)
            print(f"/place {sid} next to the beach at {bx}, {bz}: {st}: {'bien' if not f else f}")
            fails += [f"/place {x}" for x in f]
            done = True
            break
        if not done and not any(sid in f for f in fails):
            fails.append(f"{sid}: none of the {len(PLACE)} beaches has a suitable shore")
    return fails


def check_loot(ctx):
    fails = []
    forceload(ctx, 30000, 30000, 30000, 30000)
    for tbl in coast.LOOT:
        m = ctx.run(f"loot spawn 30000 120 30000 loot heraldia:costa/{tbl}", r"Dropped \d+|No items")
        if not m.group(0).startswith("Dropped"):
            fails.append(f"loot heraldia:costa/{tbl}: {m.string.strip()}")
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    forceload(ctx, 30000, 30000, 30000, 30000, remove=True)
    return fails


def check_log(ctx, lighthouses=True, sep_shipwreck=768):
    fails, log = [], ctx.log()
    for kind, sep in (("faro", 1024), ("naufragio", sep_shipwreck)):
        active = lighthouses or kind != "faro"
        sp = round(sep / 16)
        if not re.search(rf"rejilla costa/{kind}: {'activada' if active else 'desactivada'}, cada {sp} chunks "
                         rf"\(separación mínima {(DISTANCE + 15) // 16}, origen desplazado\)[^\n]*candidata en el bioma #heraldia:litoral", log):
            fails.append(f"the costa/{kind} grid is missing from the log (every {sp} chunks)")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-costa"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    jar = os.path.abspath(a.jar)
    fails = []
    t0 = time.monotonic()
    proc, ctx = start_up(a.work, jar, {}, True)
    try:
        fails += check_log(ctx)
        f, seen_all = check_locate(ctx)
        fails += f
        if not re.search(r"costa: faros activados cada 1024 bloques, naufragios activados cada 768 bloques; 2 tipos, a 256 bloques",
                         ctx.log()):
            fails.append("the coast rule is missing from the log")
        fails += check_placed(ctx)
        fails += check_loot(ctx)
        ctx.run("heraldia info", r"Registered structures|Estructuras registradas")
        m = re.search(r"(?:Coast|Costa): (?:lighthouses|faros) (\w+), (?:every|cada) 1024 [^\n]*?; (\d+) (?:structures|estructuras)", ctx.log())
        if not m or int(m.group(2)) != len(coast.structures()):
            fails.append(f"/heraldia info does not summarize the coast with its {len(coast.structures())} structures")
        modes = {st.mode for sts in seen_all.values() for st in sts}
        print(f"seen with /locate: {sorted(modes)}")
    finally:
        halt(proc)
    proc, ctx = start_up(a.work, jar, {"faros": {"activado": False}, "naufragios": {"separacion_bloques": 2048}}, False)
    try:
        fails += check_log(ctx, lighthouses=False, sep_shipwreck=2048)
        # what is already generated stays and /locate still finds it (as in an existing world): only a new one must not appear
        m = ctx.run("execute positioned -40000 64 40000 run locate structure #heraldia:costa/faro",
                    r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
        generated_many = {(st.x // 16, st.z // 16) for st in seen_all.get("faro", [])}
        if m.group(1) and not any(abs(int(m.group(1)) // 16 - cx) <= 6 and abs(int(m.group(2)) // 16 - cz) <= 6
                                  for cx, cz in generated_many):
            fails.append(f"lighthouses disabled and /locate gives a new one at {m.group(1)}, {m.group(2)}")
        print(f"lighthouses disabled: /locate gives {m.group(1) and (m.group(1), m.group(2))} (already generated: {sorted(generated_many)})")
    finally:
        halt(proc)
    print(f"costa: {time.monotonic() - t0:.0f} s")
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("COSTA OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
