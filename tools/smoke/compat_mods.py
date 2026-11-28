"""Compatibility with popular Fabric 26.3 mods on a real dedicated server, by groups of mutually compatible mods.

Usage: python3 tools/smoke/compat_mods.py --group <group> --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
     python3 tools/smoke/compat_mods.py --list-only
The mods come from modrinth.py (version 26.3 + Fabric pinned, with sha512). In each group (plus Chunky, which does the generation):
  - the server starts without registration errors and with all of Heraldia's structures ("Heraldia: N structures
    registered") and with no exceptions passing through Heraldia code anywhere in the log;
  - /locate finds a village and the unique structures of LOCATE (biomes with a conventional tag, shared by the biome
    mods) and /place places PLACE with its guardian;
  - Chunky generates a square of RADIUS blocks around the village and the first two unique structures found (in the
    NO_CHUNKY groups, forceload of FORCELOAD_R): the time (chunks/s) and the "Can't keep up!" messages are measured, with generous
    limits (SLOW_CPS, LAG_MAX_MS);
  - with the server stopped, the structure starts saved in the regions are read: no piece of a Heraldia structure
    may intersect one from another mod (except underground ones, which are not visible: UNDERGROUND).
Exit code 0 if everything passes. The pure functions are tested in tools/gen/tests/test_compat_mods.py.
"""
import argparse, glob, io, json, os, queue, re, struct, subprocess, sys, threading, time, zipfile, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import modrinth

# Groups of mutually compatible mods (dependencies go in the group). "base" is the reference: only Heraldia and Chunky.
GROUPS = {
    "base": [],
    "terreno": ["terralith", "lithostitched"],
    # Tectonic 3 declares itself incompatible with Terralith ("Mod resolution failed"): it goes separately
    "tectonic": ["tectonic", "lithostitched"],
    "biomas": ["biomes-o-plenty", "glitchcore", "terrablender"],
    "wwoo": ["wwoo", "cristel-lib", "cloth-config"],
    "estructuras": ["dungeons-and-taverns", "towns-and-towers", "cristel-lib", "cloth-config", "structory",
                    "structory-towers", "explorify"],
    "rendimiento": ["lithium", "c2me-fabric", "ferrite-core", "scalablelux"],
    "servidor": ["lootr", "xaeros-minimap", "xaeros-world-map", "journeymap"],
    # Distant Horizons and Chunky together leave the server stuck while preparing the spawn (also without Heraldia): without Chunky,
    # the area is generated with forceload (FORCELOAD_R)
    "distanthorizons": ["distanthorizons"],
}
ALWAYS = ["chunky"]
NO_CHUNKY = {"distanthorizons"}
FORCELOAD_R = 64               # half side of the area generated with forceload if there is no Chunky (9 × 9 chunks)
LOCATE = ["castillo", "catedral", "santuario", "acueducto"]
PLACE, PLACE_AT, PLACE_R = "torre_mago", (4000, 4000), 64
RADIUS = 160                    # half side (blocks) of each area Chunky generates
SLOW_CPS = 3.0                # below this (average chunks/s) generation is considered broken
LAG_MAX_MS = 60000          # a "Can't keep up! ... N ms behind" of more than a minute: the server has got stuck
CHUNKY_TIMEOUT_S = 900
# Test configuration: the minimum spacing between villages, to have more villages near the generated areas.
CONFIG = {"aldeas": {"separacion_bloques": 1000}}
# Generation steps (Structure.step) of the structures that do not show: an overlap with them is not visible on the surface.
UNDERGROUND = {"underground_structures", "underground_ores", "underground_decoration", "strongholds"}
LOG_BAD = ("Registry loading errors", "Failed to load datapacks", "Couldn't load", "Failed to parse",
            "Mod resolution failed", "Mixin apply failed", "mixin.transformer.throwables")
_CHUNKY_END = re.compile(r"Task finished for (\S+)\. Processed: (\d+) chunks")
_LAG = re.compile(r"Can't keep up! .*?Running (\d+)ms or (\d+) ticks behind")


def mods_of(group):
    """Modrinth projects of the group, together with those that always go (no repeats)."""
    return list(dict.fromkeys(GROUPS[group] + ([] if group in NO_CHUNKY else ALWAYS)))


def lags(text):
    """Milliseconds of each "Can't keep up!" in the log."""
    return [int(m.group(1)) for m in _LAG.finditer(text)]


def heraldia_errors(text):
    """Exception blocks in the log (the line and its "at ..." trace) that pass through Heraldia code (package or mixin)."""
    out, lines = [], text.splitlines()
    i = 0
    while i < len(lines):
        if re.search(r"(Exception|Error)\b", lines[i]) and not lines[i].startswith(("\tat ", "\t...")):
            j = i + 1
            while j < len(lines) and (lines[j].startswith(("\tat ", "\t... ", "Caused by:", "\tSuppressed:")) or lines[j].startswith("\t\tat ")):
                j += 1
            block = lines[i:j]
            if any("albertosa23.heraldia" in l or "heraldia$" in l for l in block):
                out.append("\n".join(block[:12]))
            i = j
        else:
            i += 1
    return out


def _boxes(start):
    """Boxes (x0, y0, z0, x1, y1, z1) of the pieces of a saved structure start."""
    out = []
    for child in start.get("Children", []):
        bb = child.get("BB")
        if bb is not None and len(bb) == 6:
            out.append(tuple(int(v) for v in bb))
    return out


def structure_starts(world):
    """[(id, (chunkX, chunkZ), [boxes])] of the structure starts saved in the Overworld regions."""
    paths = glob.glob(os.path.join(world, "dimensions", "minecraft", "overworld", "region", "r.*.mca")) or \
        glob.glob(os.path.join(world, "region", "r.*.mca"))
    import nbtlib
    out = []
    for path in sorted(paths):
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 8192:
            continue
        for i in range(1024):
            off = int.from_bytes(data[i * 4:i * 4 + 3], "big") * 4096
            if not off:
                continue
            length, comp = struct.unpack(">IB", data[off:off + 5])
            raw = data[off + 5:off + 4 + length]
            nbt = nbtlib.File.parse(io.BytesIO(zlib.decompress(raw) if comp == 2 else raw))
            starts = nbt.get("structures", {}).get("starts", {})
            for sid, st in starts.items():
                if str(st.get("id", sid)) == "INVALID":
                    continue
                boxes = _boxes(st)
                if boxes:
                    out.append((str(sid), (int(st.get("ChunkX", 0)), int(st.get("ChunkZ", 0))), boxes))
    return out


def _cross(a, b):
    return a[0] <= b[3] and b[0] <= a[3] and a[1] <= b[4] and b[1] <= a[4] and a[2] <= b[5] and b[2] <= a[5]


def overlaps(lst, steps=None):
    """Pairs (heraldia, foreign) whose pieces intersect. Foreign = from another mod (neither heraldia nor minecraft) and not
    underground according to `steps` (id -> generation step, if known). Each pair once."""
    steps = steps or {}
    our_items = [x for x in lst if x[0].startswith("heraldia:")]
    foreign = [x for x in lst if not x[0].startswith(("heraldia:", "minecraft:")) and steps.get(x[0]) not in UNDERGROUND]
    out = []
    for h in our_items:
        for o in foreign:
            if any(_cross(a, b) for a in h[2] for b in o[2]):
                out.append((h[0], h[1], o[0], o[1]))
    return out


def mod_steps(jars):
    """Structure id -> generation step ("step") reading worldgen/structure/*.json inside the .jar files."""
    out = {}
    for path in jars:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                m = re.match(r"data/([^/]+)/worldgen/structure/(.+)\.json$", n)
                if not m:
                    continue
                try:
                    step = json.loads(z.read(n)).get("step")
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(step, str):
                    out[f"{m.group(1)}:{m.group(2)}"] = step.split(":")[-1]
    return out


def locate(ctx, target, x=0, z=0):
    m = ctx.run(f"execute positioned {x} 64 {z} run locate structure {target}",
                r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
    return (int(m.group(1)), int(m.group(2))) if m.group(1) else None


def place(ctx, sid, x, z, r):
    ctx.run(f"forceload add {x - r} {z - r} {x + r} {z + r}", r"Marked|Added|force|already")
    for _ in range(s.PLACE_ATTEMPTS):
        m = ctx.run(f"place structure heraldia:unicas/{sid} {x} ~ {z}", r"Generated structure|not loaded(?! yet)")
        if "not loaded" not in m.group(0):
            return "Generated" in m.group(0)
        time.sleep(s.PLACE_RETRY_S)
    return False


def chunky(ctx, x, z, r):
    """Generates with Chunky the square of half side r at (x, z): (chunks, seconds)."""
    ctx.run(f"chunky center {x} {z}", r"[Cc]enter|Chunky")
    ctx.run(f"chunky radius {r}", r"[Rr]adius|Chunky")
    t0 = time.monotonic()
    s.send(ctx.proc, "chunky start")
    m = s.wait_for(ctx.lines, _CHUNKY_END.pattern + r"|Task (?:already|not) |[Cc]onfirm", CHUNKY_TIMEOUT_S, ctx.seen)
    if "onfirm" in m.group(0):
        s.send(ctx.proc, "chunky confirm")
        m = s.wait_for(ctx.lines, _CHUNKY_END.pattern, CHUNKY_TIMEOUT_S, ctx.seen)
    if not m.group(2):
        raise SystemExit(f"Chunky did not start: {m.string.strip()}")
    return int(m.group(2)), time.monotonic() - t0


def force(ctx, x, z, r):
    """Without Chunky: generates the square of half side r at (x, z) with forceload and waits for its corners to be
    loaded. (chunks, seconds)."""
    t0 = time.monotonic()
    ctx.run(f"forceload add {x - r} {z - r} {x + r} {z + r}", r"Marked|Added|force|already")
    corners = [(x - r, z - r), (x + r, z - r), (x - r, z + r), (x + r, z + r), (x, z)]
    for ex, ez in corners:
        if not ctx.until(f"execute if loaded {ex} 64 {ez}", timeout=CHUNKY_TIMEOUT_S):
            raise SystemExit(f"forceload no carga {ex}, {ez}")
    t = time.monotonic() - t0
    ctx.run(f"forceload remove {x - r} {z - r} {x + r} {z + r}", r"Unmarked|force")
    side = (x + r) // 16 - (x - r) // 16 + 1
    return side * side, t


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=sorted(GROUPS))
    ap.add_argument("--list-only", action="store_true", help="groups and mods (with version), without running anything")
    ap.add_argument("--mods", nargs="+", metavar="SLUG", help="with --group: these mods instead of the group's (to isolate a failure)")
    ap.add_argument("--jar")
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-compat"))
    a = ap.parse_args(argv)
    if a.list_only:
        for g in GROUPS:
            print(f"{g}: " + ", ".join(f"{p} {modrinth.MODS[p].version}" for p in mods_of(g)))
        return 0
    if not a.group or not a.jar:
        ap.error("--group and --jar are required (or --list-only)")
    os.makedirs(a.work, exist_ok=True)
    with zipfile.ZipFile(a.jar) as z:   # in CI this job only has the .jar
        expected = sum(n.startswith("data/heraldia/worldgen/structure/") and n.endswith(".json") for n in z.namelist())
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump(CONFIG, f)
    slugs = list(dict.fromkeys(a.mods + ([] if a.group in NO_CHUNKY else ALWAYS))) if a.mods else mods_of(a.group)
    modrinth.install(a.work, slugs)
    steps = mod_steps([modrinth.jar(a.work, p) for p in slugs])
    t_start = time.monotonic()
    proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen, fails, info = queue.Queue(), [], [], []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        m = s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        info.append(f"arranque {time.monotonic() - t_start:.0f} s")
        if int(m.group(1)) != expected:
            fails.append(f"estructuras registradas {m.group(1)}, esperadas {expected}")
        lootr = ctx.run("heraldia info", r"Lootr: (\S+)")
        if ("lootr" in slugs) != (lootr.group(1).rstrip(".") in ("installed", "instalado")):
            fails.append(f"/heraldia info no detecta bien Lootr: {lootr.string.strip()}")
        zones = []
        village = locate(ctx, "#heraldia:aldeas")
        if village is None:
            fails.append("/locate finds no Heraldia village")
        else:
            zones.append(("aldea", village))
        for sid in LOCATE:
            p = locate(ctx, f"heraldia:unicas/{sid}")
            if p is None:
                fails.append(f"/locate no encuentra heraldia:unicas/{sid}")
            elif len(zones) < 3:
                zones.append((sid, p))
        if not place(ctx, PLACE, *PLACE_AT, PLACE_R):
            fails.append(f"/place structure heraldia:unicas/{PLACE} failed")
        elif not s.guardian_placed(ctx, PLACE):
            fails.append(f"{PLACE}: its guardian does not appear")
        ctx.run(f"forceload remove {PLACE_AT[0] - PLACE_R} {PLACE_AT[1] - PLACE_R} {PLACE_AT[0] + PLACE_R} {PLACE_AT[1] + PLACE_R}",
                r"Unmarked|force")
        before = len("".join(seen))
        total_chunks, total_s = 0, 0.0
        for name, (x, z) in zones:
            n, t = force(ctx, x, z, FORCELOAD_R) if "chunky" not in slugs else chunky(ctx, x, z, RADIUS)
            total_chunks, total_s = total_chunks + n, total_s + t
            info.append(f"{'Chunky' if 'chunky' in slugs else 'forceload'} {name} ({x}, {z}): {n} chunks en {t:.0f} s")
        during = lags("".join(seen)[before:])
        cps = total_chunks / total_s if total_s else 0
        info.append(f"generación: {total_chunks} chunks en {total_s:.0f} s ({cps:.1f} chunks/s); "
                    f"{len(during)} «Can't keep up!» (máx. {max(during, default=0)} ms)")
        if total_chunks and cps < SLOW_CPS:
            fails.append(f"generation too slow: {cps:.1f} chunks/s (< {SLOW_CPS})")
        if max(during, default=0) > LAG_MAX_MS:
            fails.append(f"\"Can't keep up!\" of {max(during)} ms during generation (> {LAG_MAX_MS})")
    finally:
        if proc.poll() is None:
            try:
                s.send(proc, "stop")
                proc.wait(timeout=180)
            except (subprocess.TimeoutExpired, BrokenPipeError):
                proc.kill()
    log = os.path.join(a.work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else "".join(seen)
    for bad in LOG_BAD:
        if bad in text:
            fails.append(f"the log contains {bad!r}")
    for e in heraldia_errors(text):
        fails.append("exception with Heraldia code:\n      " + e.replace("\n", "\n      "))
    lst = structure_starts(os.path.join(a.work, "world"))
    our_items = sum(x[0].startswith("heraldia:") for x in lst)
    foreign = sum(not x[0].startswith(("heraldia:", "minecraft:")) for x in lst)
    info.append(f"inicios guardados: {len(lst)} ({our_items} de Heraldia, {foreign} de otros mods)")
    for h, hp, o, op in overlaps(lst, steps):
        fails.append(f"visible overlap: {h} (chunk {hp[0]}, {hp[1]}) with {o} (chunk {op[0]}, {op[1]})")
    print(f"COMPAT {a.group}: " + "; ".join(info))
    print(f"COMPAT {a.group}:", "OK" if not fails else "FAIL\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
