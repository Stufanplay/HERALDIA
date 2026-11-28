"""Existing world: what is already generated does not change when updating Heraldia or its configuration (real 26.3 dedicated server).

Usage: python3 tools/smoke/existing_world.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-mundo-existente"
Three starts of the same world (server_smoke's seed), with the random tick rule at 0, no new mobs and, on
starts 2 and 3, the world frozen (/tick freeze: chunks are loaded and generated, but block, fluid and entity
ticks do not run), so the only thing that can change an already generated chunk is the mod:
1. "Previous version": configuration with everything new from the unreleased 0.1.0 turned off (roads, medium structures, mine entrances
   and vanilla mine multiplier 1, arena, replenishing loot; rejilla_compatible enabled) and the Guide not given.
   Area A (SIDE_A x SIDE_A chunks) is generated around the Heraldia village closest to 0,0 and more than 1,200
   ticks are let pass (tick sprint): for the arena, the world is no longer new.
2. config/heraldia.json is deleted (as when installing the new version: it is created with the default values). Area A is
   loaded and ring B is generated around it (roads, medium structures and mines may appear in it). The arena is not built
   by itself (log "mundo existente").
3. Configuration different in almost everything (another difficulty level, no medium structures, mines x5, wider roads, replenishing
   loot, bosses without phases, rejilla_compatible disabled...): A and B are loaded and ring C is generated.
After each start, the chunks of A (and, after the 3rd, also those of B) are compared with the saved copy by reading the
regions (.mca): the blocks of each section, the blocks with data (id and NBT, without the fields that change by themselves), the
heights, the biomes and the structure starts and references. Entities: each UUID in the area is still in the world
(mobs may walk around). Exit code 0 if everything passes.
"""
import argparse, glob, io, json, os, queue, re, shutil, struct, subprocess, sys, threading, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s           # noqa: E402
import nbtlib                      # noqa: E402

SIDE_A, RING_B, RING_C = 8, 4, 3          # chunks
# "Before": what did not exist in the version the world was generated with, turned off.
CONFIG_BEFORE = {"unicas": {"rejilla_compatible": True}, "aldeas": {"caminos": {"activado": False}},
                "medianas": {"activadas": False}, "minas": {"entradas": {"activado": False}, "vanilla": {"multiplicador": 1.0}},
                "faros": {"activado": False}, "naufragios": {"activado": False},
                "arena": {"activado": False}, "botin": {"reponer": {"activado": False}}, "guia": {"entregar_al_entrar": False},
                "casa_heraldo": {"activado": False}}
# Third start: almost everything different from the default.
CONFIG_OTHER = {"unicas": {"rejilla_compatible": False, "distancia_minima": {"bloques": 1500}},
               "aldeas": {"porcentaje_grandes": 60, "caminos": {"activado": True, "ancho": 5, "distancia_maxima_bloques": 4000},
                          "vida": {"tablon": False}},
               "medianas": {"activadas": False}, "minas": {"entradas": {"separacion_bloques": 1024}, "vanilla": {"multiplicador": 5.0}},
               "faros": {"separacion_bloques": 256}, "naufragios": {"separacion_bloques": 256},
               "golems": {"limpieza": False}, "jefes": {"fases": {"activado": False}, "refuerzos": {"activado": False}},
               "botin": {"reponer": {"activado": True, "dias": 1}},
               "dificultad": {"nivel": "heroica", "escalar_por_jugadores": True, "escalar_botin": False},
               "arena": {"activado": True, "generar_en_mundos_nuevos": True}, "guia": {"entregar_al_entrar": True}}
# Fields that change by themselves on saving or with the world clock (they are not part of the chunk's content).
VOLATILE_CHUNK = {"LastUpdate", "InhabitedTime", "block_ticks", "fluid_ticks", "PostProcessing", "isLightOn",
                   "blending_data", "Status", "DataVersion", "xPos", "zPos", "yPos"}
VOLATILE_BLOCK = {"keepPacked"}


# ------------------------------------------------------------------ regiones
def _region(world, folder, cx, cz):
    for base in (os.path.join(world, "dimensions", "minecraft", "overworld"), world):
        p = os.path.join(base, folder, f"r.{cx >> 5}.{cz >> 5}.mca")
        if os.path.isfile(p):
            return p
    return None


def read_chunk(world, cx, cz, folder="region"):
    """NBT of a chunk (or of the entities file, with carpeta="entities"), or None if it is not saved."""
    path = _region(world, folder, cx, cz)
    if not path:
        return None
    with open(path, "rb") as f:
        data = f.read()
    i = (cx & 31) + (cz & 31) * 32
    off = int.from_bytes(data[i * 4:i * 4 + 3], "big") * 4096
    if not off:
        return None
    length, comp = struct.unpack(">IB", data[off:off + 5])
    raw = data[off + 5:off + 4 + length]
    if comp == 2:
        raw = zlib.decompress(raw)
    elif comp == 1:
        import gzip
        raw = gzip.decompress(raw)
    elif comp != 3:
        raise SystemExit(f"region compression {comp} not supported (region-file-compression=deflate)")
    return nbtlib.File.parse(io.BytesIO(raw))


def _blueprint(v):
    """nbtlib NBT to Python types comparable with == (long arrays, which nbtlib gives as numpy, to lists)."""
    if isinstance(v, dict):
        if len(v) == 1 and "" in v:               # element of a mixed list (26.3 wraps them like this)
            return _blueprint(v[""])
        return {str(k): _blueprint(x) for k, x in v.items()}
    if isinstance(v, (nbtlib.tag.ByteArray, nbtlib.tag.IntArray, nbtlib.tag.LongArray)):
        return [int(x) for x in v]
    if isinstance(v, (list, tuple)):
        return [_blueprint(x) for x in v]
    if isinstance(v, nbtlib.tag.String):
        return str(v)
    if isinstance(v, (nbtlib.tag.Float, nbtlib.tag.Double)):
        return float(v)
    if isinstance(v, int):
        return int(v)
    return v


def _stripped(d, remove):
    return {k: v for k, v in d.items() if k not in remove}


def footprint(n):
    """What must not change in a saved chunk: {section: comparable value}."""
    out = {}
    sections_list = {}
    for sec in n.get("sections", []):
        bs = sec.get("block_states")
        sections_list[int(sec["Y"])] = (_blueprint(bs) if bs is not None else None, _blueprint(sec.get("biomes")))
    out["secciones"] = sections_list
    be = {}
    for b in n.get("block_entities", []):
        d = _blueprint(b)
        be[(d.get("x"), d.get("y"), d.get("z"))] = _stripped(d, VOLATILE_BLOCK)
    out["bloques_con_datos"] = be
    out["alturas"] = _blueprint(n.get("Heightmaps"))
    out["estructuras"] = _blueprint(n.get("structures"))
    out["resto"] = _stripped({k: _blueprint(v) for k, v in n.items()}, VOLATILE_CHUNK | {"sections", "block_entities", "Heightmaps", "structures"})
    return out


def states(bs):
    """List of 4096 states (name + properties) of a section, to compare even if the palette order changes."""
    if bs is None:
        return None
    # 26.3: a state without properties is a string ("minecraft:stone"; in a mixed list, {"": ...}, which removes the
    # _plano) and one with properties, {id, properties} (before 26.3, {Name, Properties})
    pal = [(p, ()) if isinstance(p, str) else (p.get("Name", p.get("id")),
                                                tuple(sorted((p.get("Properties") or p.get("properties") or {}).items())))
           for p in bs["palette"]]
    if len(pal) == 1 or "data" not in bs:
        return [pal[0]] * 4096
    bits = max(4, (len(pal) - 1).bit_length())
    per, mask, out = 64 // bits, (1 << bits) - 1, []
    for v in bs["data"]:
        v &= (1 << 64) - 1
        for _ in range(per):
            out.append(pal[v & mask])
            v >>= bits
            if len(out) == 4096:
                return out
    return out


def differences(a, b):
    """Texts describing what changes between two fingerprints of the same chunk ([] if nothing)."""
    e = []
    sa, sb = a["secciones"], b["secciones"]
    for y in sorted(set(sa) | set(sb)):
        if y not in sa or y not in sb:
            e.append(f"sección {y} {'añadida' if y in sb else 'quitada'}")
            continue
        (ba, bioa), (bb, biob) = sa[y], sb[y]
        if ba != bb:
            ea, eb = states(ba), states(bb)
            if ea != eb:
                changes = [(i, ea[i][0], eb[i][0]) for i in range(4096) if ea[i] != eb[i]]
                i, dimension_of, a_ = changes[0]
                e.append(f"sección {y}: {len(changes)} bloques cambian (p. ej. x={i & 15} y={y * 16 + (i >> 8)} z={(i >> 4) & 15}: {dimension_of} -> {a_})")
        if bioa != biob:
            e.append(f"sección {y}: cambian los biomas")
    ba, bb = a["bloques_con_datos"], b["bloques_con_datos"]
    for p in sorted(set(ba) | set(bb), key=str):
        if ba.get(p) != bb.get(p):
            forward, idb = (ba.get(p) or {}).get("id"), (bb.get(p) or {}).get("id")
            keys = sorted(k for k in set(ba.get(p) or {}) | set(bb.get(p) or {}) if (ba.get(p) or {}).get(k) != (bb.get(p) or {}).get(k))
            e.append(f"bloque con datos {p} ({forward} -> {idb}) cambia: {keys}")
    for k in ("alturas", "estructuras", "resto"):
        if a[k] != b[k]:
            keys = sorted(set(a[k] or {}) | set(b[k] or {}))
            e.append(f"{k} cambia: {[c for c in keys if (a[k] or {}).get(c) != (b[k] or {}).get(c)]}")
    return e


def snapshot(world, chunks):
    """{(cx, cz): fingerprint} of the fully saved chunks (Status full); those that are not are left out."""
    out = {}
    for c in chunks:
        n = read_chunk(world, *c)
        if n is not None and str(n.get("Status", "")) in ("minecraft:full", "full"):
            out[c] = footprint(n)
    return out


def uuids(world, chunks):
    """{uuid: id} of the entities saved in those chunks."""
    out = {}
    for c in chunks:
        n = read_chunk(world, *c, folder="entities")
        for ent in (n or {}).get("Entities", []):
            u = tuple(int(x) for x in ent.get("UUID", []))
            out[u] = str(ent.get("id"))
    return out


def compare(name, before, after):
    """Failures (texts) from comparing two snapshots of the same chunks."""
    failures = []
    for c in sorted(before):
        if c not in after:
            failures.append(f"{name}: chunk {c} is no longer fully saved")
            continue
        d = differences(before[c], after[c])
        if d:
            failures.append(f"{name}: chunk {c} changes: " + "; ".join(d[:4]) + (f" (and {len(d) - 4} more)" if len(d) > 4 else ""))
    return failures


# ------------------------------------------------------------------ servidor
def start_up(work, launcher, cfg):
    path = os.path.join(work, "config", "heraldia.json")
    if cfg is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, "w") as f:
            json.dump(cfg, f)
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    ctx = s.Context(proc, lines, seen)
    ctx.run("gamerule spawn_mobs false", r"Gamerule|set to")
    ctx.run("gamerule random_tick_speed 0", r"Gamerule|set to")
    return proc, ctx


def halt(proc, ctx):
    ctx.run("save-all flush", r"Saved the game|saved")
    if proc.poll() is None:
        s.send(proc, "stop")
        proc.wait(timeout=180)
    while True:          # what it wrote on stopping (the roads' cost line) also to ctx.seen
        try:
            line = ctx.lines.get(timeout=10)
        except queue.Empty:
            return
        if line is None:
            return
        ctx.seen.append(line)


def square(c0x, c0z, side):
    return {(x, z) for x in range(c0x, c0x + side) for z in range(c0z, c0z + side)}


FORCELOAD_MAX = 16          # /forceload accepts at most 256 chunks per command: pieces of 16 x 16


def fragments(chunks):
    """Rectangles (x0, z0, x1, z1) in blocks, of at most FORCELOAD_MAX x FORCELOAD_MAX chunks, that cover the chunks."""
    xs, zs = [c[0] for c in chunks], [c[1] for c in chunks]
    out = []
    for cx in range(min(xs), max(xs) + 1, FORCELOAD_MAX):
        for cz in range(min(zs), max(zs) + 1, FORCELOAD_MAX):
            ex, ez = min(cx + FORCELOAD_MAX - 1, max(xs)), min(cz + FORCELOAD_MAX - 1, max(zs))
            out.append((cx * 16, cz * 16, ex * 16 + 15, ez * 16 + 15))
    return out


def freeze(ctx):
    """/tick freeze: the world keeps loading and generating chunks (and loading their entities, which is when the mod touches them),
    but block, fluid and entity ticks do not run. Without this, the lava and water of the caves at the edges
    keep flowing, villagers open doors and the vaults of the trial chambers change their data: changes by the
    game, not the mod, that would hide what we want to see."""
    ctx.run("tick freeze", r"[Ff]rozen|freeze|[Gg]ame")


def load_data(ctx, chunks, frozen=False):
    """Forces and loads the chunks (generating them if they are not), waits for all of them to be there, then releases them."""
    for x0, z0, x1, z1 in fragments(chunks):
        ctx.run(f"forceload add {x0} {z0} {x1} {z1}", r"Marked|[Aa]dded|force|already")
    for cx, cz in sorted(chunks):
        if not ctx.until(f"execute if loaded {cx * 16} 64 {cz * 16}", timeout=600):
            raise SystemExit(f"chunk {cx}, {cz} does not load")
    if frozen:
        time.sleep(5)                 # with the world frozen the clock does not advance: whatever remains is allowed to finish
    else:
        ctx.ticks(60)
    for x0, z0, x1, z1 in fragments(chunks):
        ctx.run(f"forceload remove {x0} {z0} {x1} {z1}", r"[Rr]emoved|[Uu]nmarked|force")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-mundo-existente"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    world = os.path.join(a.work, "world")
    failures = []

    # 1. previous version
    proc, ctx = start_up(a.work, launcher, CONFIG_BEFORE)
    try:
        m = ctx.run("locate structure #heraldia:aldeas", r"is at \[(-?\d+), ~, (-?\d+)\]|Could not find")
        if not m.lastindex:
            raise SystemExit("no Heraldia village is located")
        ax, az = int(m.group(1)) >> 4, int(m.group(2)) >> 4
        print(f"Area A: {SIDE_A} x {SIDE_A} chunks around the village at chunk {ax}, {az}")
        A = square(ax - SIDE_A // 2, az - SIDE_A // 2, SIDE_A)
        load_data(ctx, A)
        ctx.run("tick sprint 1300", r"[Ss]print|ticks")
        s.wait_for(ctx.lines, r"[Ss]print completed|[Ss]print .*(finished|ended)|ticks per second", 300, ctx.seen)
        if ctx.gametime() < 1300:
            failures.append(f"the world does not reach 1,300 ticks ({ctx.gametime()})")
    finally:
        halt(proc, ctx)
    snapshot_a, ents_a = snapshot(world, A), uuids(world, A)
    print(f"Zona A: {len(snapshot_a)} de {len(A)} chunks guardados enteros, {len(ents_a)} entidades")
    if len(snapshot_a) < len(A) * 3 // 4:
        failures.append(f"only {len(snapshot_a)} chunks of A fully saved")
    backup = os.path.join(a.work, "world-tras-1")         # to look by hand at what changed if it fails
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(world, backup)

    # 2. new version with the default configuration
    B = square(ax - SIDE_A // 2 - RING_B, az - SIDE_A // 2 - RING_B, SIDE_A + 2 * RING_B)
    proc, ctx = start_up(a.work, launcher, None)
    try:
        if not re.search(r"arena: mundo existente", ctx.log()):
            failures.append("the arena does not recognize the existing world (line 'arena: mundo existente' in the log)")
        freeze(ctx)
        load_data(ctx, B, frozen=True)
    finally:
        halt(proc, ctx)
    with open(os.path.join(a.work, "config", "heraldia.json"), encoding="utf-8") as f:
        by_default = json.load(f)
    print("Default configuration created:", json.dumps({k: v for k, v in by_default.items() if not k.startswith("_")}, ensure_ascii=False)[:400])
    failures += compare("arranque 2 (por defecto)", snapshot_a, snapshot(world, A))
    ents = uuids(world, B)
    losses = {u: t for u, t in ents_a.items() if u not in ents}
    if losses:
        failures.append(f"start 2: {len(losses)} entities of area A are no longer there: {sorted(set(losses.values()))}")
    snapshot_b = snapshot(world, B - A)
    print(f"Anillo B: {len(snapshot_b)} chunks nuevos guardados enteros")
    if re.search(r"arena: (mundo nuevo|colocada|sitio propuesto)", ctx.log()):
        failures.append("start 2: the arena builds itself in an existing world")
    # the Herald's House (new in this version, on by default): never on its own in a world that already exists
    if not re.search(r"herald's house: existing world", ctx.log()):
        failures.append("start 2: the Herald's House does not recognize the existing world")
    if re.search(r"herald's house: (new world|placed at|site at)", ctx.log()):
        failures.append("start 2: the Herald's House builds itself in an existing world")
    m = re.search(r"caminos: \d+ chunks, (\d+) junto a una ruta \((\d+) columnas", ctx.log())
    if not m or int(m.group(2)) == 0:
        failures.append("start 2: no road appears in the new ring (the test could not see whether it touches the old)")
    else:
        print(f"Ring B: {m.group(1)} chunks next to a route, {m.group(2)} road columns placed")

    # 3. another configuration
    C = square(ax - SIDE_A // 2 - RING_B - RING_C, az - SIDE_A // 2 - RING_B - RING_C,
                 SIDE_A + 2 * (RING_B + RING_C))
    proc, ctx = start_up(a.work, launcher, CONFIG_OTHER)
    try:
        freeze(ctx)
        load_data(ctx, C, frozen=True)
        if re.search(r"arena: (mundo nuevo|colocada|sitio propuesto)", ctx.log()):
            failures.append("start 3: the arena builds itself in an existing world")
    finally:
        halt(proc, ctx)
    failures += compare("arranque 3 (otra configuración), zona A", snapshot_a, snapshot(world, A))
    failures += compare("arranque 3 (otra configuración), anillo B", snapshot_b, snapshot(world, B - A))
    ents = uuids(world, C)
    losses = {u: t for u, t in ents_a.items() if u not in ents}
    if losses:
        failures.append(f"start 3: {len(losses)} entities of area A are no longer there: {sorted(set(losses.values()))}")

    for f_ in failures:
        print("[FALLO]", f_)
    print("EXISTING WORLD TEST " + ("OK" if not failures else f"FALLIDA ({len(failures)} fallos)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
