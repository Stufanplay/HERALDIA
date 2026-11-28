"""Mine entrances (tools/gen/mines) and multiplied vanilla mines on a real 26.3 dedicated server (deterministic: fixed
seed from server_smoke and zones chosen in advance).

Usage: python3 tools/smoke/mine_entrances.py --jar build/libs/heraldia-X.jar [--work build/smoke-entradas-mina]
Two starts of the same world:
1. mines.vanilla.multiplicador = 1 (exact vanilla placement):
   - the log: the grid of each size (spacing, biome search), the mines rule and the vanilla frequency;
   - /place structure of one style of each size: the mouth (track under the lintel and posts), the whole track from the yard to the
     last junction of the trunk (each rail of the template in place with the chosen rotation), the gallery junctions
     underground (air at head height and shell above, below the mouth's floor), each chest with its table
     heraldia:minas/<table>, the cargo minecart, the medium mine's spiders and the large one's spawner;
   - loot spawn of each table;
   - /locate of each size from 0,0, which really generates it (forceload) where /locate said, and /heraldia info nearby
     from there: no village or unique structure closer than mediums.distancia_aldeas_unicas_bloques, nor another mine of another size
     nor a medium structure closer than mediums.distancia_minima.bloques;
   - /locate far away (from 8000, -8000, like tools/smoke/generation_cost.py) of #heraldia:minas and of each size: how long it
     takes (the game says it in the log; with the shared height cache and T36's parallel look-ahead computation,
     below LOCATE_FAR_MS) and that it finds the same mines as 0.1.0 (LOCATE_FAR, measured with its .jar);
   - /heraldia info: the mines line and the 30 registered entrances;
   - generates zone A (12 x 12 chunks) and saves its vanilla mine starts: all of them are among those predicted by the
     vanilla draw (legacy_type_3) with the 26.3 frequency.
2. mines.vanilla.multiplicador = 5: zone A (already generated) keeps exactly its mines, and in zone B (new) mines
   appear that would not appear with the vanilla frequency (and none outside those predicted by x5).
Exit code 0 if everything passes.
"""
import argparse, glob, io, json, math, os, queue, re, struct, subprocess, sys, threading, time, zlib
import nbtlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s

sys.path.insert(0, os.path.join(s.ROOT, "tools", "gen"))
import mines                                    # noqa: E402  (the generator: templates, loot and its track)
from uniques.lost_mine.tracks import traverse  # noqa: E402

PLACE_X, PLACE_Z, STEP = 40000, 40000, 320      # /place of each size, far from everything
STYLE = "montana"
LOCATE_MAX = {"pequena": 6000, "mediana": 9000, "grande": 20000}   # blocks from 0,0 (every 768, 1,152 and 1,920, on hillsides)
ZONE, DISTANCE = 256, 192                       # options.py, default
SIDE = 12                                        # chunks per side of zones A and B
TURNS = {"NONE": lambda x, z: (x, z), "CLOCKWISE_90": lambda x, z: (-z, x), "CLOCKWISE_180": lambda x, z: (-x, -z),
         "COUNTERCLOCKWISE_90": lambda x, z: (z, -x)}
ENTRANCE = re.compile(r"entrada a mina en (-?\d+) (-?\d+) (-?\d+) \(giro (\w+)")
# far /locate: from where, what it finds with the test seed (the same result as 0.1.0, before T36: what
# changed is only how long it takes) and the cap on how long the first one may take (0.1.0 took about 5 s locally).
LOCATE_FROM = (8000, -8000)
LOCATE_FAR = {"#heraldia:minas": (14560, -5664), "#heraldia:minas/pequena": (3888, -7296),
                "#heraldia:minas/mediana": (-4080, -16512), "#heraldia:minas/grande": (14560, -5664)}
LOCATE_FAR_MS = 2500
_LOCATE_MS = re.compile(r"Locating element (\S+) .*?took (\d+) ms")


# ------------------------------------------------------------------ vanilla mine draw (legacy_type_3)
class Lcg:
    """java.util.Random (LegacyRandomSource de 26.3)."""
    M = (1 << 48) - 1

    def __init__(self, seed):
        self.set(seed)

    def set(self, seed):
        self.s = (seed ^ 0x5DEECE66D) & self.M

    def next(self, bits):
        self.s = (self.s * 0x5DEECE66D + 0xB) & self.M
        v = self.s >> (48 - bits)                    # Java (int): only with 32 bits can it come out negative
        return v - (1 << 32) if bits == 32 and v >= 1 << 31 else v

    def next_long(self):
        v = (self.next(32) << 32) + self.next(32)
        return (v + (1 << 63)) % (1 << 64) - (1 << 63)

    def next_double(self):
        return ((self.next(26) << 27) + self.next(27)) * 2.0 ** -53       # BitRandomSource.nextDouble


def s64(v):
    return (v + (1 << 63)) % (1 << 64) - (1 << 63)


def sale_vanilla(seed, x, z, frequency):
    """legacyProbabilityReducerWithDouble: setLargeFeatureSeed(seed, x, z) and nextDouble() < frequency (float)."""
    r = Lcg(seed)
    a, b = r.next_long(), r.next_long()
    r.set(s64(s64(x * a) ^ s64(z * b) ^ seed))
    return r.next_double() < frequency


def f32(v):
    return struct.unpack("f", struct.pack("f", v))[0]


def float_str(v):
    """Java's Float.toString: the fewest digits that give back the same float."""
    for d in range(1, 10):
        t = f"{v:.{d}g}"
        if f32(float(t)) == v:
            return t if "." in t or "e" in t else t + ".0"
    return repr(v)


def prediction(seed, cx0, cz0, frequency):
    return {(x, z) for x in range(cx0, cx0 + SIDE) for z in range(cz0, cz0 + SIDE) if sale_vanilla(seed, x, z, frequency)}


def choose_zones(seed):
    """Zone A (with some vanilla mine and some that would only appear with x5) and zone B (with at least 3 extra from x5)."""
    f1, f5 = f32(0.004), f32(f32(0.004) * 5.0)
    zones = []
    for k in range(60):
        cx0, cz0 = 1500 + k * (SIDE + 4), -1500
        p1, p5 = prediction(seed, cx0, cz0, f1), prediction(seed, cx0, cz0, f5)
        zones.append((cx0, cz0, p1, p5))
    a = next(z for z in zones if len(z[2]) >= 1 and len(z[3] - z[2]) >= 2)
    b = next(z for z in zones if z is not a and len(z[3] - z[2]) >= 3)
    return a, b


# ------------------------------------------------------------------ regiones guardadas
def chunk_nbt(world, cx, cz):
    rx, rz = cx >> 5, cz >> 5
    path = os.path.join(world, "dimensions", "minecraft", "overworld", "region", f"r.{rx}.{rz}.mca")
    if not os.path.isfile(path):
        path = os.path.join(world, "region", f"r.{rx}.{rz}.mca")
        if not os.path.isfile(path):
            return None
    with open(path, "rb") as f:
        data = f.read()
    i = (cx & 31) + (cz & 31) * 32
    off = int.from_bytes(data[i * 4:i * 4 + 3], "big") * 4096
    if not off:
        return None
    length, comp = struct.unpack(">IB", data[off:off + 5])
    raw = data[off + 5:off + 4 + length]
    return nbtlib.File.parse(io.BytesIO(zlib.decompress(raw) if comp == 2 else raw))


def saved_mines(world, cx0, cz0):
    """Chunks of the zone with a saved vanilla mine start, and those that are not fully generated."""
    out, missing = set(), []
    for x in range(cx0, cx0 + SIDE):
        for z in range(cz0, cz0 + SIDE):
            n = chunk_nbt(world, x, z)
            if n is None or str(n.get("Status", "")) not in ("minecraft:full", "full"):
                missing.append((x, z))
                continue
            starts = (n.get("structures") or {}).get("starts") or {}
            for sid in ("minecraft:mineshaft", "minecraft:mineshaft_mesa"):
                st = starts.get(sid)
                if st is not None and str(st.get("id", "INVALID")) != "INVALID":
                    out.add((x, z))
    return out, missing


# ------------------------------------------------------------------ servidor
def start_up(work, jar, cfg, clean_up):
    launcher = s.prepare(work, jar, s.gradle_properties()) if clean_up else os.path.join(work, glob.glob(
        os.path.join(work, "fabric-server-*.jar"))[0])
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
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


def generate_zone(ctx, cx0, cz0):
    x0, z0, x1, z1 = cx0 * 16, cz0 * 16, (cx0 + SIDE) * 16 - 1, (cz0 + SIDE) * 16 - 1
    forceload(ctx, x0, z0, x1, z1)
    for x, z in ((x0, z0), (x1, z1), (x0, z1), (x1, z0)):
        if not ctx.until(f"execute if loaded {x} 64 {z}", timeout=300):
            return False
    ctx.ticks(40)
    forceload(ctx, x0, z0, x1, z1, remove=True)
    ctx.run("save-all flush", r"Saved the game|saved")
    return True


# ------------------------------------------------------------------ entradas colocadas
def check_placed(ctx):
    fails, timings = [], []
    for k, size in enumerate(mines.SIZES):
        o, _, _ = mines.construction(size, STYLE, "a")
        sid = mines.template(size, STYLE, "a")
        px, pz = PLACE_X + k * STEP, PLACE_Z
        forceload(ctx, px - 112, pz - 112, px + 111, pz + 111)
        before = len(ctx.seen)
        t0 = time.monotonic()
        m = ctx.run(f"place structure heraldia:{sid} {px} 100 {pz}", r"Generated structure|Failed to place")
        timings.append(time.monotonic() - t0)
        if not m.group(0).startswith("Generated"):
            fails.append(f"{sid}: /place: {m.string.strip()}")
            continue
        e = ENTRANCE.search("".join(ctx.seen[before:]))
        if not e:
            fails.append(f"{sid}: the log does not say where the mouth ended up")
            continue
        bx, feet, bz, turn = int(e.group(1)), int(e.group(2)), int(e.group(3)), e.group(4)
        rot = TURNS[turn]

        def world(p):
            dx, dz = rot(p[0], p[2])
            return bx + dx, feet - 1 + p[1], bz + dz
        print(f"{sid}: boca en {bx} {feet} {bz}, giro {turn}, /place en {timings[-1]:.1f} s")
        if not ctx.until(f"execute if block {' '.join(map(str, world((0, 1, 0))))} #minecraft:rails", timeout=60):
            fails.append(f"{sid}: no track under the lintel")
            continue
        for p in ((2, 1, 0), (-2, 1, 0)):
            if not ctx.block(world(p), "#minecraft:logs"):
                fails.append(f"{sid}: the mouth post {p} is missing")
        # the track, rail by rail, from the yard to the end of the trunk
        get = lambda x, y, z: o.t.get(x, y, z)
        for ini, direction, _ in o.tracks:
            _, road = traverse(get, ini, direction, steps=2000)
            bad_many = [p for p in road if not ctx.block(world(p), "#minecraft:rails")]
            if bad_many:
                fails.append(f"{sid}: {len(bad_many)} of {len(road)} rails are missing, e.g. {bad_many[0]}")
            back = min(p[1] for p in road)
            print(f"{sid}: track of {len(road)} rails, from the yard to {back - 1} below the mouth's floor")
        # the gallery: air at head height, shell above and below the mouth's floor
        for (x, y, z) in o.nodes:
            head, shell = world((x, y + 2, z)), world((x, y + 6, z))
            if not ctx.block(head, "minecraft:air") or ctx.block(shell, "minecraft:air") or head[1] > feet - 8:
                fails.append(f"{sid}: the junction {x, y, z} is not dug out underground ({head})")
                break
        for (x, y, z), tbl in o.chest_list:
            st = o.t.get(x, y, z).split("[")[0]
            if not ctx.block(world((x, y, z)), f"{st}{{LootTable:\"heraldia:minas/{tbl}\"}}"):
                if not ctx.test(f"execute if entity @e[type=minecraft:chest_minecart,x={world((x, y, z))[0]},"
                                f"y={world((x, y, z))[1]},z={world((x, y, z))[2]},distance=..2]"):
                    fails.append(f"{sid}: the chest {tbl} is missing at {(x, y, z)}")
        box = f"x={bx - 110},y={feet - 50},z={bz - 110},dx=220,dy=80,dz=220"
        expected_counts = {"minecraft:minecart": 0, "minecraft:chest_minecart": 0, "minecraft:cave_spider": 0}
        for *_, n in o.t.entities:
            expected_counts[n["id"]] += 1
        for kind, n in expected_counts.items():
            if n and not ctx.until(f"execute if entity @e[type={kind},{box}]", timeout=30):
                fails.append(f"{sid}: no aparece {kind}")
            elif n and ctx.count(f"@e[type={kind},{box}]") < n:
                fails.append(f"{sid}: {ctx.count(f'@e[type={kind},{box}]')} {kind}, esperadas {n}")
        for g in o.generators:
            if not ctx.block(world(g), "minecraft:spawner"):
                fails.append(f"{sid}: the spider spawner is missing at {g}")
        forceload(ctx, px - 112, pz - 112, px + 111, pz + 111, remove=True)
    print(f"/place of the entrances: {', '.join(f'{t:.1f} s' for t in timings)}")
    return fails


def check_loot(ctx):
    fails = []
    forceload(ctx, PLACE_X, PLACE_Z - 600, PLACE_X, PLACE_Z - 600)
    for tbl in mines.LOOT:
        m = ctx.run(f"loot spawn {PLACE_X} 120 {PLACE_Z - 600} loot heraldia:minas/{tbl}", r"Dropped \d+|No items")
        if not m.group(0).startswith("Dropped"):
            fails.append(f"loot heraldia:minas/{tbl}: {m.string.strip()}")
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    forceload(ctx, PLACE_X, PLACE_Z - 600, PLACE_X, PLACE_Z - 600, remove=True)
    return fails


def info_near(ctx, x, z, radius):
    m = ctx.run(f"execute positioned {x} 64 {z} run heraldia info nearby {radius}", r"info nearby \d+ en [^:]+: \d+ estructuras en (\d+) ms")
    if not m.lastindex:
        return None
    return {g[0]: (int(g[1]), int(g[2]), int(g[3])) for g in s.INFO_LINE.findall("".join(s.drain(ctx)))}


def generated(ctx, x, z, size):
    end = time.monotonic() + s.UNTIL_S
    while time.monotonic() < end:
        for dx, dz in ((0, 0), (8, 8), (-8, 8), (8, -8), (-8, -8)):
            for dy in (-2, -8, -14):
                m = ctx.run(f"execute positioned {x + dx} 0 {z + dz} positioned over world_surface positioned ~ ~{dy} ~ "
                            f"run heraldia info here", r"\((heraldia:[^)]+)\)|no hay ninguna|no Heraldia|not loaded|no está cargada")
                if m.group(1) and f"minas/{size}/" in m.group(1):
                    return m.group(1)
        time.sleep(2)
    return None


def check_locate(ctx):
    fails, timings = [], []
    for size in mines.SIZES:
        t0 = time.monotonic()
        m = ctx.run(f"execute positioned 0 64 0 run locate structure #heraldia:minas/{size}",
                    r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
        timings.append(time.monotonic() - t0)
        if not m.group(1):
            fails.append(f"/locate finds no {size} mine")
            continue
        x, z = int(m.group(1)), int(m.group(2))
        d = math.hypot(x, z)
        print(f"{size} mine: /locate at {x}, {z} {d:.0f} blocks away ({timings[-1]:.1f} s)")
        if d > LOCATE_MAX[size]:
            fails.append(f"{size} mine at {d:.0f} blocks (> {LOCATE_MAX[size]})")
        nearby_flag = info_near(ctx, x, z, 600) or {}
        for sid, (dist, *_) in nearby_flag.items():
            if ":minas/" in sid:                       # expected: heraldia:minas/<size>; generated, with its style
                if not (sid.endswith(f"minas/{size}") or f"minas/{size}/" in sid) and dist < DISTANCE:
                    fails.append(f"{size} mine at {x}, {z} {dist} blocks from {sid} (< {DISTANCE})")
            elif ":medianas/" in sid or ":costa/" in sid:    # lighthouses and wrecks yield to mines at this distance
                if dist < DISTANCE:
                    fails.append(f"{size} mine at {x}, {z} {dist} blocks from the medium structure {sid} (< {DISTANCE})")
            elif dist < ZONE:
                fails.append(f"{size} mine at {x}, {z} {dist} blocks from {sid} (< {ZONE})")
        forceload(ctx, x - 48, z - 48, x + 47, z + 47)
        sid = generated(ctx, x, z, size)
        if not sid:
            fails.append(f"{size} mine: /locate gives {x}, {z} but nothing has been generated there")
        else:
            print(f"mina {size}: generada de verdad ({sid})")
        forceload(ctx, x - 48, z - 48, x + 47, z + 47, remove=True)
    if timings:
        print(f"/locate of mines: mean {sum(timings) / len(timings):.1f} s, max {max(timings):.1f} s")
    return fails


def check_locate_far(ctx):
    """/locate from LOCATE_FROM: the time the game reports and that it finds the same as 0.1.0."""
    fails, (x0, z0) = [], LOCATE_FROM
    for target, expected in LOCATE_FAR.items():
        s.pending(ctx.lines, ctx.seen)
        s.send(ctx.proc, f"execute positioned {x0} 64 {z0} run locate structure {target}")
        ms, pos = None, None
        while ms is None or pos is None:
            m = s.wait_for(ctx.lines, _LOCATE_MS.pattern + r"|is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find|" + s.ERROR_PATTERN,
                           s.COMMAND_TIMEOUT_S, ctx.seen)
            if m.group(0).startswith("Locating element"):
                ms = int(m.group(2))
            elif m.group(0).startswith("is at"):
                pos = (int(m.group(3)), int(m.group(4)))
            else:
                pos, ms = "nada", ms if ms is not None else -1
        print(f"/locate {target} from {x0}, {z0}: {ms} ms -> {pos}")
        if pos != expected:
            fails.append(f"/locate {target} from {x0}, {z0}: {pos}, 0.1.0 gave {expected}")
        if target == "#heraldia:minas" and ms > LOCATE_FAR_MS:
            fails.append(f"/locate {target} from {x0}, {z0} takes {ms} ms (> {LOCATE_FAR_MS})")
    return fails


def check_log(ctx, multiplier):
    fails, log = [], ctx.log()
    for size in mines.SIZES:
        sp = round(mines.SEPARATION[size] / 16)
        if not re.search(rf"rejilla minas/{size}: activada, cada {sp} chunks \(separación mínima {(DISTANCE + 15) // 16}, "
                         r"origen desplazado\)[^\n]*candidata en el bioma #heraldia:minas", log):
            fails.append(f"the log is missing the grid of minas/{size} (every {sp} chunks)")
    freq = float_str(f32(f32(0.004) * multiplier) if multiplier != 1 else f32(0.004))
    if not re.search(rf"minas abandonadas vanilla: frecuencia {re.escape(freq)} ", log):
        fails.append(f"the log is missing the vanilla mines frequency ({freq})")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-minas"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    jar, world = os.path.abspath(a.jar), os.path.join(a.work, "world")
    fails = []
    proc, ctx = start_up(a.work, jar, {"minas": {"vanilla": {"multiplicador": 1}}}, True)
    try:
        seed = int(ctx.run("seed", r"Seed: \[(-?\d+)\]").group(1))
        (ax, az, a1, a5), (bx, bz, b1, b5) = choose_zones(seed)
        print(f"seed {seed}; zone A at chunk {ax}, {az} ({len(a1)} vanilla mines, {len(a5)} with x5); "
              f"zona B en {bx}, {bz} ({len(b1)} y {len(b5)})")
        fails += check_log(ctx, 1)
        fails += check_locate_far(ctx)          # first thing: /locate with the server just started
        fails += check_placed(ctx)
        fails += check_loot(ctx)
        fails += check_locate(ctx)
        if not re.search(r"entradas a mina: activadas, 3 tamaños, cada 768 bloques las pequeñas, a 256 bloques de aldeas y "
                         r"únicas y a 192 de las medianas y entre ellas", ctx.log()):
            fails.append("the log is missing the mine entrances rule")
        m = ctx.run("heraldia info", r"Registered structures: \d+ \(\d+ villages, \d+ unique, \d+ medium and (\d+) mine|"
                                     r"Estructuras registradas: \d+ \(\d+ de aldeas, \d+ únicas, \d+ medianas y (\d+) ")
        n = (m.group(1) or m.group(2)) if m.lastindex else None
        if n is None or int(n) != len(mines.structures()):
            fails.append(f"/heraldia info: {n} entradas a mina registradas, esperadas {len(mines.structures())}")
        if not re.search(r"Mine entrances: enabled, every 768 blocks|Entradas a mina: activada, cada 768", "".join(ctx.seen[-40:])):
            fails.append("/heraldia info does not summarize the mines")
        t0 = time.monotonic()
        if not generate_zone(ctx, ax, az):
            fails.append("zone A is not generated")
        print(f"zona A generada en {time.monotonic() - t0:.0f} s")
    finally:
        halt(proc)
    saved_to, missing = saved_mines(world, ax, az)
    if missing:
        fails.append(f"zone A: {len(missing)} chunks not fully generated")
    if not saved_to <= a1:
        fails.append(f"zone A with x1: mines outside the vanilla draw: {sorted(saved_to - a1)}")
    if not saved_to:
        fails.append("zone A has no vanilla mine (those of the draw were expected)")
    print(f"zona A (x1): {len(saved_to)} minas {sorted(saved_to)}")
    # second start, x5: what was generated does not change; the new part, with more mines
    proc, ctx = start_up(a.work, jar, {"minas": {"vanilla": {"multiplicador": 5}}}, False)
    try:
        fails += check_log(ctx, 5)
        t0 = time.monotonic()
        if not generate_zone(ctx, bx, bz):
            fails.append("zone B is not generated")
        print(f"zona B generada en {time.monotonic() - t0:.0f} s")
    finally:
        halt(proc)
    saved_to2, _ = saved_mines(world, ax, az)
    if saved_to2 != saved_to:
        fails.append(f"the already generated zone A changed with x5: {sorted(saved_to)} -> {sorted(saved_to2)}")
    saved_to_b, missing = saved_mines(world, bx, bz)
    if missing:
        fails.append(f"zone B: {len(missing)} chunks not fully generated")
    new_ones = saved_to_b - b1
    print(f"zone B (x5): {len(saved_to_b)} mines, {len(new_ones)} that would not appear with x1")
    if not saved_to_b <= b5:
        fails.append(f"zone B with x5: mines outside the draw: {sorted(saved_to_b - b5)}")
    if not new_ones:
        fails.append("zone B with x5: no extra mine")
    print("MINAS:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
