"""Heraldia generation cost: the same area of the same world generated with the mod and without it, and its comparison with the
reference stored in the repository (tools/smoke/cost_reference.json).

Usage:
  python3 tools/smoke/generation_cost.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
  python3 tools/smoke/generation_cost.py ... --update-reference     # measures and saves the new reference
  python3 tools/smoke/generation_cost.py --from-json build/coste/generation_cost.json [--update-reference]
      # rebuilds the summary (or the reference) from a measurement already taken, e.g. the CI artifact "coste-generacion"
  python3 tools/smoke/generation_cost.py --jar ... --zones medianas \
      --variant medianas.frecuencia_porcentaje=100 --variant medianas.frecuencia_porcentaje=70
      # compares several Heraldia configurations against the same vanilla passes (one table, no threshold)

Each pass starts a fresh 26.3 dedicated server (world deleted, fixed seed SEED, Fabric API and Chunky), once
with the Heraldia .jar (default configuration and -Dheraldia.perfil=true) and once without it, alternating. In each
one: Chunky generates a warm-up area (not counted), then the ZONES with the Minecraft profiler active
(/jfr start ... /jfr stop) and finally /locate is timed for LOCATES. From the .jfr we get, per chunk of the zones, the sum of the
time of each generation step (minecraft.ChunkGeneration event): ms per chunk (mean, p50, p90, p99, max) and per
step; from the /jfr summary, the MSPT (ms per tick) and memory; from the log, the time of each /locate and Heraldia's own
profile (comun/Perfil.java: roads, hillside, shore, medium structures, mines, foreign-structure zone...).

Overhead = median of the passes with Heraldia / median without it - 1, in server-process CPU per chunk
(/proc/<pid>/stat while Chunky generates the zones: it does not grow with the wait between threads, which does inflate the duration of the
JFR steps, ±15 % between identical passes). Without /proc (outside Linux), with the sum of the JFR steps per chunk without
the light ones (which are mostly waiting in the light engine queue). The ratio removes the machine's speed.
Fails if it exceeds reference × (1 + umbral_relativo) + margen_absoluto (both in the reference). If it fails, it repeats
one round of passes and decides with all of them (CI noise). Writes <output>/generation_cost.json and
<output>/generation_cost.md, and the Markdown also to $GITHUB_STEP_SUMMARY if it exists. Exit code 0 if it passes.
The pure functions are tested in tools/gen/tests/test_generation_cost.py.
"""
import argparse, json, math, os, queue, re, shutil, statistics, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import modrinth
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/, last: it holds a test.py
import cost_status                  # noqa: E402  (tools/cost_status.py: estado.json and progreso.log in --output)

REFERENCE = os.path.join(s.ROOT, "tools", "smoke", "cost_reference.json")
SEED = "heraldia"
# (name, x, z, half side in blocks): squares of whole chunks that Chunky generates. Far from each other (more than
# MARGIN_CHUNKS chunks) so that each event falls in a single zone. "aldea": the village closest to 0,0 with the
# default configuration (swamp, 32 -1344) and the start of its roads; "origen": 0,0 (no Heraldia village).
ZONES = [("aldea", 32, -1344, 160), ("origen", 0, 0, 160)]
WARMUP = ("calentamiento", 6000, 6000, 64)
# Zones for comparing densities of medium structures (--zones medianas): the standard ones are centred on a village and
# next to a castle, where no medium spawns (the exclusion zone around villages and uniques), so they barely see the medium
# frequency. These are four large squares (51 x 51 chunks each, 4 x 0.67 km2) on open land at the four diagonals, with
# several mediums each at the default density. The strip is kept (the continuous flight).
MEDIUM_ZONES = [("m_ne", 2400, -2400, 400), ("m_se", 2400, 2400, 400), ("m_so", -2400, 2400, 400), ("m_no", -2400, -2400, 400)]
LAYOUTS = {"estandar": ZONES, "medianas": MEDIUM_ZONES}
# The continuous route ("like flying with elytra"): a long, narrow strip that Chunky generates column by column along x
# (shape rectangle, pattern loop), through the castle closest to the village (heraldia:unicas/castillo at -4496, -1088: the
# largest piece-by-piece structure, 100 x 100 blocks): (name, x, z, half length in x, half width in z), in blocks.
STRIP = ("franja", -4496, -1088, 768, 80)
# A stretch of the strip: this many chunk columns (128 blocks, about 4 s of elytra flight at 30 blocks/s) across its width.
STRETCH_CHUNKS = 8
# The run-up: the first columns of the strip are generated but not counted in its stretches and peaks (the first chunks
# of a new area wait hundreds of ms on the biome step, with or without Heraldia: measured, it is not generation work).
LEAD_IN_CHUNKS = 8
# What fits in a server tick (ms): a chunk whose generation steps add up to more is a "slow chunk".
TICK_MS = 50
# A slow chunk is blamed on the structures started in it or, if none, on the closest started within this many chunks
# (the pieces of a jigsaw structure reach up to 116 blocks from its start: 8 chunks).
NEAR_CHUNKS = 8
MARGIN_CHUNKS = 12         # chunks around a zone that it generates along the way (earlier steps of the neighbours)
# Light steps: their duration is mostly waiting in the light engine queue (a single thread), not generation
# work, and it is the noisiest (±15 % between identical passes). They do not count in ms per chunk; they are reported separately.
LIGHT_STEPS = {"minecraft:initialize_light", "minecraft:light"}
# Steps where the structure code works (placement rules, starts, pieces and features such as roads).
STRUCTURE_STEPS = {"minecraft:structure_starts", "minecraft:structure_references", "minecraft:features"}
# /locate timed at the end of each pass, from LOCATE_FROM: (name, target, only with Heraldia)
LOCATE_FROM = (8000, -8000)
LOCATES = [("aldea", "#heraldia:aldeas", True), ("unica", "heraldia:unicas/castillo", True),
           ("mediana", "#heraldia:medianas", True), ("mina", "#heraldia:minas", True),
           ("aldea_vanilla", "#minecraft:village", False)]
SWEEPS = 3
# Heraldia configuration: the default one (the real server's), except the wave arena, which in a new world
# builds itself next to spawn (one chunk of work per tick, on the server thread, right while it is
# being measured): it is not generation cost and in the server's existing world it is not generated.
CONFIG = {"arena": {"generar_en_mundos_nuevos": False},
          "casa_heraldo": {"generar_en_mundos_nuevos": False}}   # the Herald's House builds itself at spawn, likewise
XMX = "3G"
CHUNKY_TIMEOUT_S = 900
_CHUNKY_END = re.compile(r"Task finished for (\S+)\. Processed: (\d+) chunks")
_LOCATE = re.compile(r"Locating element (\S+) .*?took (\d+) ms")
_PROFILE = re.compile(r"Heraldia: perfil: (\{.*\})\s*$")
_JFR_END = re.compile(r"Dumped flight recorder profiling to (\S+\.jfr)")
_JFR_SUMMARY = re.compile(r"Dumped recording summary to (\S+\.json)")


# ---------------------------------------------------------------- funciones puras (tests en test_generation_cost.py)

def percentile(values, p):
    """Percentile p (0-100) with linear interpolation between ranks (like numpy "linear"); None if there are no values."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def duration_ms(text):
    """Duration from `jfr print --json` ("PT0.000610953S", "PT1M2.5S", "PT0S") in ms."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", text)
    if not m:
        raise ValueError(f"unrecognized JFR duration: {text!r}")
    h, mi, se = (float(g) if g else 0.0 for g in m.groups())
    return (h * 3600 + mi * 60 + se) * 1000


def chunks_of_zone(x, z, r):
    """(cx0, cz0, cx1, cz1) of the chunks that Chunky generates in the square of half side r centered on (x, z): those from
    x - r to x + r, both included (center 0,0 and radius 128: 17 × 17 = 289 chunks, what "Processed" says)."""
    return ((x - r) >> 4, (z - r) >> 4, (x + r) >> 4, (z + r) >> 4)


def side(c, r):
    return ((c + r) >> 4) - ((c - r) >> 4) + 1


def inside(c, box, margin=0):
    cx, cz = c
    return box[0] - margin <= cx <= box[2] + margin and box[1] - margin <= cz <= box[3] + margin


def chunks_of_rect(x, z, rx, rz):
    """Like chunks_of_zone for Chunky's rectangle shape (half sides rx along x and rz along z)."""
    return ((x - rx) >> 4, (z - rz) >> 4, (x + rx) >> 4, (z + rz) >> 4)


def box_chunks(box):
    return (box[2] - box[0] + 1) * (box[3] - box[1] + 1)


def per_chunk_ms(events, boxes):
    """{(cx, cz): sum of its generation steps without the light ones} of the chunks inside any of the boxes."""
    out = {}
    for cx, cz, step, ms in events:
        if step not in LIGHT_STEPS and any(inside((cx, cz), b) for b in boxes):
            out[(cx, cz)] = out.get((cx, cz), 0.0) + ms
    return out


def peaks(per_chunk, tick_ms=TICK_MS):
    """The tail of the time per chunk (what a player notices, not the median): p50, p95, p99, the worst chunk (ms and
    position) and how many chunks need more than a tick (`lentos`, and their share of the chunks)."""
    v = list(per_chunk.values())
    worst = max(per_chunk, key=per_chunk.get) if per_chunk else None
    slow = sum(1 for x in v if x > tick_ms)
    return {"chunks": len(v), "p50_ms": percentile(v, 50), "p95_ms": percentile(v, 95), "p99_ms": percentile(v, 99),
            "max_ms": per_chunk[worst] if worst else None, "peor_chunk": list(worst) if worst else None,
            "lentos": slow, "lentos_fraccion": slow / len(v) if v else None}


def jfr_structure_events(dataset):
    """[(cx, cz, structure, ms, success)] from the minecraft.StructureGeneration events of `jfr print --json` (the
    attempt to start a structure in a chunk: the placement rules, the jigsaw assembly and its pieces)."""
    out = []
    for e in dataset["recording"]["events"]:
        v = e["values"]
        if e.get("type", "minecraft.StructureGeneration") == "minecraft.StructureGeneration" and v.get("level", "minecraft:overworld") == "minecraft:overworld":
            out.append((v["chunkPosX"], v["chunkPosZ"], v["structure"], duration_ms(v["duration"]), bool(v.get("success"))))
    return out


def structures_summary(structure_events, boxes, margin=MARGIN_CHUNKS):
    """Per structure (those tried in the boxes and their margin): attempts, successes, total ms and the slowest attempt
    (ms and chunk), sorted by that maximum."""
    out = {}
    for cx, cz, sid, ms, ok in structure_events:
        if not any(inside((cx, cz), b, margin) for b in boxes):
            continue
        r = out.setdefault(sid, {"intentos": 0, "generadas": 0, "total_ms": 0.0, "max_ms": 0.0, "max_chunk": None})
        r["intentos"] += 1
        r["generadas"] += ok
        r["total_ms"] += ms
        if ms >= r["max_ms"]:
            r["max_ms"], r["max_chunk"] = ms, [cx, cz]
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["max_ms"]))


def blame(chunk, events, structure_events, near=NEAR_CHUNKS):
    """Why a chunk is slow: its steps (without light, slowest first), the structures started in it (ms) and, if none,
    the closest one started within `near` chunks (whose pieces it may be placing)."""
    cx, cz = chunk
    steps = {}
    for x, z, step, ms in events:
        if (x, z) == (cx, cz) and step not in LIGHT_STEPS:
            steps[step] = steps.get(step, 0.0) + ms
    started = sorted(((sid, ms) for x, z, sid, ms, ok in structure_events if ok and (x, z) == (cx, cz)), key=lambda t: -t[1])
    closest = None
    for x, z, sid, ms, ok in structure_events:
        d = max(abs(x - cx), abs(z - cz))
        if ok and 0 < d <= near and (closest is None or d < closest["distancia_chunks"]):
            closest = {"estructura": sid, "chunk": [x, z], "distancia_chunks": d, "ms": ms}
    return {"chunk": [cx, cz], "bloque": [cx * 16 + 8, cz * 16 + 8],
            "pasos_ms": dict(sorted(steps.items(), key=lambda kv: -kv[1])),
            "iniciadas": [{"estructura": sid, "ms": ms} for sid, ms in started], "cercana": closest}


def stretches(events, box, width=STRETCH_CHUNKS, margin=MARGIN_CHUNKS):
    """The strip in stretches of `width` chunk columns (sliding one column at a time): the generation work of each one
    (sum of the steps without light of its chunks and of the neighbours within `margin` across the strip, which generate
    earlier steps for it), per chunk of the stretch. The worst one is what a player flying over it notices most."""
    cols = {}
    for cx, cz, step, ms in events:
        if step not in LIGHT_STEPS and box[0] <= cx <= box[2] and box[1] - margin <= cz <= box[3] + margin:
            cols[cx] = cols.get(cx, 0.0) + ms
    height = box[3] - box[1] + 1
    n = width * height
    sums = [(c, sum(cols.get(x, 0.0) for x in range(c, c + width))) for c in range(box[0], box[2] - width + 2)]
    if not sums:
        return None
    c, worst = max(sums, key=lambda t: t[1])
    return {"chunks_por_tramo": n, "bloques_por_tramo": width * 16, "tramos": len(sums),
            "media_ms_por_chunk": sum(v for _, v in sums) / len(sums) / n,
            "peor_ms": worst, "peor_ms_por_chunk": worst / n, "peor_desde_x": c * 16, "peor_hasta_x": (c + width) * 16 - 1,
            "peor_columnas": [c, c + width - 1]}


def chunks_summary(events, box, margin=MARGIN_CHUNKS):
    """From the events [(cx, cz, step, ms)], those of the zone (chunk box and its margin), without the LIGHT_STEPS: per chunk of
    the box, the sum of its steps (p50, p90, p99, max); the mean spreads over the chunks of the box everything in the zone and
    its margin (the neighbours generate earlier steps for it). `pasos_ms`, the same per step (with the light ones);
    `estructuras_ms`, the STRUCTURE_STEPS part; `con_luz_ms`, the mean counting light."""
    per_chunk, steps = {}, {}
    for cx, cz, step, ms in events:
        if not inside((cx, cz), box, margin):
            continue
        steps[step] = steps.get(step, 0.0) + ms
        if step not in LIGHT_STEPS and inside((cx, cz), box):
            per_chunk[(cx, cz)] = per_chunk.get((cx, cz), 0.0) + ms
    n = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    v = list(per_chunk.values())
    return {"chunks": n, "chunks_medidos": len(v), "media_ms": sum(ms for k, ms in steps.items() if k not in LIGHT_STEPS) / n,
            "p50_ms": percentile(v, 50), "p90_ms": percentile(v, 90), "p99_ms": percentile(v, 99), "max_ms": max(v, default=None),
            "estructuras_ms": sum(ms for k, ms in steps.items() if k in STRUCTURE_STEPS) / n,
            "con_luz_ms": sum(steps.values()) / n, "pasos_ms": {k: steps[k] / n for k in sorted(steps)}}


def join_zones(events, zones):
    """ms per chunk of all the zones together: means weighted by chunks and percentiles over all chunks (without light)."""
    total = sum(v["chunks"] for v in zones.values())
    def pond(field):
        return sum(z[field] * z["chunks"] for z in zones.values()) / total
    steps = {}
    for z in zones.values():
        for k, ms in z["pasos_ms"].items():
            steps[k] = steps.get(k, 0.0) + ms * z["chunks"] / total
    boxes = [chunks_of_zone(x, zz, r) for n, x, zz, r in ZONES if n in zones]
    per_chunk = {}
    for cx, cz, step, ms in events:
        if step not in LIGHT_STEPS and any(inside((cx, cz), c) for c in boxes):
            per_chunk[(cx, cz)] = per_chunk.get((cx, cz), 0.0) + ms
    pc = list(per_chunk.values())
    return {"media_ms": pond("media_ms"), "p50_ms": percentile(pc, 50), "p90_ms": percentile(pc, 90), "p99_ms": percentile(pc, 99),
            "max_ms": max(pc, default=None), "estructuras_ms": pond("estructuras_ms"), "con_luz_ms": pond("con_luz_ms"),
            "pasos_ms": steps}


def parse_variant(text):
    """"a.b=1,c=true" -> {"a.b": 1, "c": True} (each value read as JSON if it can be: numbers, true/false; otherwise text)."""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        k, sep, v = part.partition("=")
        if not sep or not k.strip():
            raise ValueError(f"expected KEY=VALUE: {part!r}")
        try:
            out[k.strip()] = json.loads(v.strip())
        except ValueError:
            out[k.strip()] = v.strip()
    return out


def config_of(profile=None, options=None):
    """The config/heraldia.json of the passes with Heraldia: CONFIG, the profile and the `options` ({"a.b": v}) nested."""
    out = json.loads(json.dumps(CONFIG))
    if profile:
        out["perfil"] = profile
    for k, v in (options or {}).items():
        node = out
        *parents, leaf = k.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = v
    return out


def medium_starts(structures):
    """(medium structures started, their total ms) in a `estructuras` summary (those of heraldia:medianas/...)."""
    rows = [v for k, v in structures.items() if k.startswith("heraldia:medianas/")]
    return sum(r.get("generadas") or 0 for r in rows), sum(r.get("total_ms") or 0.0 for r in rows)


def variant_label(options):
    return ", ".join(f"{k}={v}" for k, v in options.items()) or "por defecto"


def variants_markdown(results):
    """One table for several Heraldia configurations measured against the same vanilla passes: [(options, result_of)]."""
    lines = ["## Coste por configuración", "",
             "| Configuración | Sobrecoste CPU | CPU ms/chunk | p95 ms | p99 ms | Chunks > 50 ms | Peor tramo ms/chunk | MSPT p99 | "
             "Medianas iniciadas | ms en iniciarlas | /locate mediana ms |", "|---" * 11 + "|"]
    if results:
        sin = results[0][1]["sin"]
        pk = sin.get("picos") or {}
        lines.append(f"| sin Heraldia | — | {_f(sin.get('cpu_ms_por_chunk'))} | {_f(pk.get('p95_ms'))} | {_f(pk.get('p99_ms'))} | "
                     f"{_f(_pct(pk.get('lentos_fraccion')))} % | {_f(((sin.get('franja') or {}).get('tramos') or {}).get('peor_ms_por_chunk'))} | "
                     f"{_f(sin['mspt'].get('p99'))} | — | — | — |")
    for options, r in results:
        con = r["con"]
        pk = con.get("picos") or {}
        n, ms = medium_starts(con.get("estructuras") or {})
        over = r.get("sobrecoste")
        lines.append(f"| {variant_label(options)} | {'—' if over is None else f'{over:+.1%}'} | {_f(con.get('cpu_ms_por_chunk'))} | "
                     f"{_f(pk.get('p95_ms'))} | {_f(pk.get('p99_ms'))} | {_f(_pct(pk.get('lentos_fraccion')))} % | "
                     f"{_f(((con.get('franja') or {}).get('tramos') or {}).get('peor_ms_por_chunk'))} | {_f(con['mspt'].get('p99'))} | "
                     f"{n:g} | {_f(ms)} | {_f(con['locate_ms'].get('mediana'))} |")
    return "\n".join(lines) + "\n"


def cpu_of_stat(line, hz=100):
    """CPU seconds (user + system) from a /proc/<pid>/stat line (the process name is in parentheses
    and may contain spaces: it is cut after the last ")")."""
    fields = line.rpartition(")")[2].split()
    return (int(fields[11]) + int(fields[12])) / hz


def process_cpu(pid):
    """CPU (s) the process has used so far, or None if there is no /proc (outside Linux)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as f:
            return cpu_of_stat(f.read(), os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, IndexError):
        return None


def jfr_chunk_events(dataset):
    """[(cx, cz, step, ms)] from the minecraft.ChunkGeneration events of `jfr print --json` (already read)."""
    out = []
    for e in dataset["recording"]["events"]:
        v = e["values"]
        if e.get("type", "minecraft.ChunkGeneration") == "minecraft.ChunkGeneration" and v.get("level", "minecraft:overworld") == "minecraft:overworld":
            out.append((v["chunkPosX"], v["chunkPosZ"], v["status"], duration_ms(v["duration"])))
    return out


def medium(values):
    v = [x for x in values if x is not None]
    return statistics.median(v) if v else None


def add_entry(sweeps):
    """Median of the passes of a configuration (each one a dict of pasada() measurements), field by field."""
    if not sweeps:
        return None
    def median(f):
        return medium([f(p) for p in sweeps])
    out = {"pasadas": len(sweeps),
           "ms_por_chunk": {k: median(lambda p, k=k: p["ms_por_chunk"].get(k)) for k in
                            ("media_ms", "p50_ms", "p90_ms", "p99_ms", "max_ms", "estructuras_ms", "con_luz_ms")},
           "segundos": median(lambda p: p["segundos"]), "chunks": sweeps[0]["chunks"],
           "cpu_ms_por_chunk": median(lambda p: p.get("cpu_ms_por_chunk")),
           "chunks_por_s": median(lambda p: p["chunks"] / p["segundos"] if p["segundos"] else None),
           "mspt": {k: median(lambda p, k=k: (p.get("mspt") or {}).get(k)) for k in ("media", "p50", "p90", "p99", "max")},
           "memoria_mb": median(lambda p: p.get("memoria_mb")),
           "locate_ms": {k: median(lambda p, k=k: p["locate_ms"].get(k)) for k in sorted({k for p in sweeps for k in p["locate_ms"]})}}
    steps = sorted({k for p in sweeps for k in p["ms_por_chunk"]["pasos_ms"]})
    out["pasos_ms"] = {k: median(lambda p, k=k: p["ms_por_chunk"]["pasos_ms"].get(k, 0.0)) for k in steps}
    zones = sorted({k for p in sweeps for k in p["zonas"]})
    out["zonas_ms"] = {k: median(lambda p, k=k: p["zonas"][k]["media_ms"] if k in p["zonas"] else None) for k in zones}
    out.update(add_tail([p for p in sweeps if p.get("picos")]))
    return out


PEAK_FIELDS = ("p50_ms", "p95_ms", "p99_ms", "max_ms", "lentos", "lentos_fraccion")


def add_tail(sweeps):
    """The peak measurements of several passes: the median of each figure, and the worst chunk (and stretch) of the pass
    where it was worst, with its cause (the world is the same in every pass: it is usually the same chunk)."""
    if not sweeps:
        return {}
    def median(f):
        return medium([f(p) for p in sweeps])
    def worst(f):
        return max(sweeps, key=lambda p: f(p) if f(p) is not None else float("-inf"))
    w = worst(lambda p: p["picos"]["max_ms"])
    out = {"picos": {k: median(lambda p, k=k: p["picos"].get(k)) for k in PEAK_FIELDS},
           "peor_chunk": dict(w.get("peor_chunk") or {}, max_ms=w["picos"]["max_ms"],
                              mismo_en_todas=len({tuple(p["picos"]["peor_chunk"] or ()) for p in sweeps}) == 1)}
    sids = {k for p in sweeps for k in p.get("estructuras", {})}
    st = {k: {f: median(lambda p, k=k, f=f: p.get("estructuras", {}).get(k, {}).get(f)) for f in ("intentos", "generadas", "total_ms", "max_ms")}
          for k in sids}
    out["estructuras"] = dict(sorted(st.items(), key=lambda kv: -(kv[1]["max_ms"] or 0)))
    strips = [p["franja"] for p in sweeps if p.get("franja")]
    if strips:
        def smed(f):
            return medium([f(x) for x in strips])
        ws = max(strips, key=lambda x: (x.get("tramos") or {}).get("peor_ms_por_chunk") or float("-inf"))
        wc = max(strips, key=lambda x: x["picos"]["max_ms"] if x["picos"]["max_ms"] is not None else float("-inf"))
        out["franja"] = {"chunks": strips[0]["chunks"], "segundos": smed(lambda x: x["segundos"]),
                         "chunks_por_s": smed(lambda x: x.get("chunks_por_s")), "cpu_ms_por_chunk": smed(lambda x: x.get("cpu_ms_por_chunk")),
                         "picos": {k: smed(lambda x, k=k: x["picos"].get(k)) for k in PEAK_FIELDS},
                         "peor_chunk": dict(wc.get("peor_chunk") or {}, max_ms=wc["picos"]["max_ms"]),
                         "tramos": {"media_ms_por_chunk": smed(lambda x: (x.get("tramos") or {}).get("media_ms_por_chunk")),
                                    "peor_ms_por_chunk": smed(lambda x: (x.get("tramos") or {}).get("peor_ms_por_chunk")),
                                    "peor_ms": smed(lambda x: (x.get("tramos") or {}).get("peor_ms")),
                                    "chunks_por_tramo": (ws.get("tramos") or {}).get("chunks_por_tramo"),
                                    "bloques_por_tramo": (ws.get("tramos") or {}).get("bloques_por_tramo"),
                                    "peor_desde_x": (ws.get("tramos") or {}).get("peor_desde_x"),
                                    "peor_hasta_x": (ws.get("tramos") or {}).get("peor_hasta_x")}}
    return out


def metric(aggregate):
    """The deciding measurement: process CPU per chunk if it could be read (the most stable: it does not grow with the wait between
    threads), otherwise the sum of the JFR steps per chunk (without light)."""
    return aggregate.get("cpu_ms_por_chunk") or aggregate["ms_por_chunk"]["media_ms"]


def overcost(with_it, sin):
    """Relative overhead of Heraldia (0.12 = 12 % more than without it) in the same measurement for both (metrica());
    None if something is missing."""
    if not with_it or not sin:
        return None
    if with_it.get("cpu_ms_por_chunk") and sin.get("cpu_ms_por_chunk"):
        return with_it["cpu_ms_por_chunk"] / sin["cpu_ms_por_chunk"] - 1
    if not sin["ms_por_chunk"]["media_ms"]:
        return None
    return with_it["ms_por_chunk"]["media_ms"] / sin["ms_por_chunk"]["media_ms"] - 1


def compare(current, reference):
    """(ok, limit, text) of the current overhead against the reference: fails if it exceeds
    ref × (1 + umbral_relativo) + margen_absoluto. With no reference (or no measurement) it passes, and says so."""
    if current is None:
        return False, None, "no se pudo medir el sobrecoste"
    if not reference or reference.get("sobrecoste") is None:
        return True, None, f"sobrecoste {current:+.1%} (sin referencia guardada: no se compara)"
    ref = reference["sobrecoste"]
    limit = max(ref, 0.0) * (1 + reference.get("umbral_relativo", 0.25)) + reference.get("margen_absoluto", 0.08)
    ok = current <= limit
    return ok, limit, (f"sobrecoste {current:+.1%} frente a la referencia {ref:+.1%} (límite {limit:+.1%}): "
                        + ("dentro del margen" if ok else "REGRESIÓN"))


# Peak limits (the "picos" block of the reference, these values if it has none). What a player notices is not the median
# but the chunks that do not fit in a tick and the stretch that is slowest to fly over; a slow chunk is generated on a
# worker thread, so the server thread only stalls if many pile up. Chosen from the measurements (docs/DEVELOPMENT.md,
# "Generation cost"): with Heraldia, at most `lentos_pp` more of the chunks over TICK_MS than without it (measured in two
# rounds on 4 cores: +1.1 and +3.3 points over vanilla's 23.5-25.7 %, that is the noise; a real regression, one more slow chunk
# in every 15, goes over); the worst stretch of the strip at most `peor_tramo` slower than without it (measured -13 % before
# the run-up was left out, -0 % after); and the server tick (MSPT p99) during generation within one tick (measured 10.5-17.7 ms).
PEAK_LIMITS = {"lentos_pp": 0.06, "peor_tramo": 0.30, "mspt_p99_ms": TICK_MS}


def compare_peaks(result, reference=None):
    """(ok, text) of the peaks of a measurement against the limits (`picos` of the reference, otherwise PEAK_LIMITS).
    A measurement from before (without peaks) passes and says so."""
    lim = dict(PEAK_LIMITS, **((reference or {}).get("picos") or {}))
    with_it, sin = result.get("con") or {}, result.get("sin") or {}
    if not with_it.get("picos") or not sin.get("picos"):
        return True, "picos: sin medir (medición de antes)"
    bad, parts = [], []
    a, b = sin["picos"].get("lentos_fraccion"), with_it["picos"].get("lentos_fraccion")
    if a is not None and b is not None:
        parts.append(f"chunks de más de {TICK_MS} ms {a:.1%} → {b:.1%} ({(b - a) * 100:+.1f} puntos, límite {lim['lentos_pp'] * 100:+.0f})")
        if b - a > lim["lentos_pp"]:
            bad.append("chunks lentos")
    ta = ((sin.get("franja") or {}).get("tramos") or {}).get("peor_ms_por_chunk")
    tb = ((with_it.get("franja") or {}).get("tramos") or {}).get("peor_ms_por_chunk")
    if ta and tb:
        parts.append(f"peor tramo {ta:.0f} → {tb:.0f} ms por chunk ({tb / ta - 1:+.0%}, límite {lim['peor_tramo']:+.0%})")
        if tb / ta - 1 > lim["peor_tramo"]:
            bad.append("peor tramo")
    m = (with_it.get("mspt") or {}).get("p99")
    if m is not None:
        parts.append(f"MSPT p99 {m:.1f} ms (límite {lim['mspt_p99_ms']:.0f})")
        if m > lim["mspt_p99_ms"]:
            bad.append("MSPT")
    ok = not bad
    return ok, "picos: " + "; ".join(parts) + (": dentro del límite" if ok else ": REGRESIÓN en " + ", ".join(bad))


def new_reference(result, previous=None):
    """The reference that is saved from a measurement (keeps the threshold and margin of the previous one)."""
    previous = previous or {}
    return {"sobrecoste": round(result["sobrecoste"], 4),
            "umbral_relativo": previous.get("umbral_relativo", 0.25), "margen_absoluto": previous.get("margen_absoluto", 0.08),
            "ms_por_chunk_con": round(metric(result["con"]), 2), "ms_por_chunk_sin": round(metric(result["sin"]), 2),
            "medida": "cpu" if result["con"].get("cpu_ms_por_chunk") and result["sin"].get("cpu_ms_por_chunk") else "jfr",
            "picos": dict(PEAK_LIMITS, **(previous.get("picos") or {})),
            "pasadas": result["con"]["pasadas"], "maquina": result.get("maquina", ""), "fecha": result.get("fecha", ""),
            "commit": result.get("commit", "")}


def _f(v, fmt="{:.1f}"):
    return "—" if v is None else fmt.format(v)


def markdown(result, comparison):
    """Markdown summary (for the CI job and the artifact)."""
    with_it, sin = result["con"], result["sin"]
    ok, limit, text = comparison[:3]
    peaks_ok, peaks_text = comparison[3:5] if len(comparison) > 3 else (True, None)
    L = [f"## Coste de generación de Heraldia {'✅' if ok and peaks_ok else '❌'}", "", f"**{text}**", ""]
    if peaks_text:
        L += [f"**{peaks_text}**", ""]
    L += [
         f"Semilla `{result['semilla']}`, {with_it['chunks']} chunks por pasada ({', '.join(result['zonas'])}), "
         f"mediana de {with_it['pasadas']} pasadas por configuración; {result.get('maquina', '')}.", "",
         "| | sin Heraldia | con Heraldia | diferencia |", "|---|---:|---:|---:|"]
    def row(name, a, b, fmt="{:.1f}"):
        d = "—" if a is None or b is None or not a else f"{b / a - 1:+.0%}"
        L.append(f"| {name} | {_f(a, fmt)} | {_f(b, fmt)} | {d} |")
    row("CPU del servidor, ms por chunk", sin.get("cpu_ms_por_chunk"), with_it.get("cpu_ms_por_chunk"))
    for k, n in (("media_ms", "ms por chunk (media, sin luz)"), ("p50_ms", "ms por chunk p50"), ("p90_ms", "ms por chunk p90"),
                 ("p99_ms", "ms por chunk p99"), ("max_ms", "ms por chunk máx.")):
        row(n, sin["ms_por_chunk"][k], with_it["ms_por_chunk"][k])
    row("pasos de estructuras, ms por chunk", sin["ms_por_chunk"].get("estructuras_ms"), with_it["ms_por_chunk"].get("estructuras_ms"), "{:.2f}")
    row("contando la luz, ms por chunk", sin["ms_por_chunk"].get("con_luz_ms"), with_it["ms_por_chunk"].get("con_luz_ms"))
    row("tiempo de generación (s)", sin["segundos"], with_it["segundos"])
    row("chunks/s", sin["chunks_por_s"], with_it["chunks_por_s"])
    for k in ("media", "p90", "p99", "max"):
        row(f"MSPT {k} (ms)", sin["mspt"].get(k), with_it["mspt"].get(k))
    row("memoria tras GC, máx. (MB)", sin["memoria_mb"], with_it["memoria_mb"], "{:.0f}")
    L += peaks_markdown(result)
    L += ["", "**Por paso de generación** (ms por chunk)", "", "| paso | sin | con | diferencia |", "|---|---:|---:|---:|"]
    for k in sorted(set(sin["pasos_ms"]) | set(with_it["pasos_ms"]), key=lambda k: -(with_it["pasos_ms"].get(k) or 0)):
        row(k.replace("minecraft:", ""), sin["pasos_ms"].get(k), with_it["pasos_ms"].get(k), "{:.2f}")
    L += ["", "**Por zona** (ms por chunk, media)", "", "| zona | sin | con | diferencia |", "|---|---:|---:|---:|"]
    for k in with_it["zonas_ms"]:
        row(k, sin["zonas_ms"].get(k), with_it["zonas_ms"].get(k))
    L += ["", "**/locate** (ms, desde " + ", ".join(map(str, result.get("locate_desde", LOCATE_FROM))) + ")", "",
          "| estructura | sin | con |", "|---|---:|---:|"]
    for k in sorted(set(sin["locate_ms"]) | set(with_it["locate_ms"])):
        L.append(f"| {k} | {_f(sin['locate_ms'].get(k), '{:.0f}')} | {_f(with_it['locate_ms'].get(k), '{:.0f}')} |")
    profile = result.get("perfil") or {}
    if profile:
        L += ["", "**Perfil de Heraldia** (`-Dheraldia.perfil=true`, mediana de las pasadas; incluye las búsquedas de /locate). "
              "Los tramos se solapan: `reglas` y `reglas_locate` contienen `medianas`, `minas`, `zona_ajenas` y "
              "`separacion_unicas`, y la regla de las minas mira si salen las vecinas (con su `ladera`).", "",
              "| tramo | veces | total (ms) | media (µs) | máx. (µs) |", "|---|---:|---:|---:|---:|"]
        for k, v in sorted(profile.items(), key=lambda kv: -kv[1]["total_ms"]):
            L.append(f"| {k} | {v['n']:.0f} | {v['total_ms']:.1f} | {v['media_us']:.1f} | {v['max_us']:.0f} |")
    L += ["", "Referencia: `tools/smoke/cost_reference.json` (cómo actualizarla: docs/DEVELOPMENT.md, «Coste de generación»)."]
    return "\n".join(L) + "\n"


def _blame_text(b):
    """One line on why a chunk is slow (from blame())."""
    if not b or not b.get("chunk"):
        return "—"
    steps = ", ".join(f"{k.replace('minecraft:', '')} {v:.0f}" for k, v in list(b.get("pasos_ms", {}).items())[:3])
    t = f"chunk {b['chunk'][0]}, {b['chunk'][1]} (bloque {b['bloque'][0]}, {b['bloque'][1]}): {_f(b.get('max_ms'), '{:.0f}')} ms ({steps})"
    if b.get("iniciadas"):
        t += "; empieza ahí: " + ", ".join(f"`{x['estructura']}` ({x['ms']:.0f} ms)" for x in b["iniciadas"])
    elif b.get("cercana"):
        c = b["cercana"]
        t += f"; la estructura más cercana: `{c['estructura']}`, a {c['distancia_chunks']} chunks ({c['ms']:.0f} ms al empezar)"
    else:
        t += "; ninguna estructura empieza a menos de " + str(NEAR_CHUNKS) + " chunks"
    return t


def peaks_markdown(result):
    """The peak section of the summary: the tail of the time per chunk, the worst chunk and its cause, the strip and its worst
    stretch, and the structures slowest to start. Empty for a measurement from before (without peaks)."""
    with_it, sin = result["con"], result["sin"]
    if not with_it.get("picos") or not sin.get("picos"):
        return []
    a, b = sin["picos"], with_it["picos"]
    def row(name, x, y, fmt="{:.1f}"):
        d = "—" if x is None or y is None or not x else f"{y / x - 1:+.0%}"
        L.append(f"| {name} | {_f(x, fmt)} | {_f(y, fmt)} | {d} |")
    L = ["", f"**Picos: la cola del tiempo por chunk** (suma de los pasos sin luz; un tick son {TICK_MS} ms)", "",
         "| | sin Heraldia | con Heraldia | diferencia |", "|---|---:|---:|---:|"]
    for k, n in (("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99"), ("max_ms", "peor chunk")):
        row(f"{n} (ms)", a.get(k), b.get(k))
    row(f"chunks de más de {TICK_MS} ms (%)", _pct(a.get("lentos_fraccion")), _pct(b.get("lentos_fraccion")), "{:.2f}")
    L += ["", f"- Peor chunk con Heraldia: {_blame_text(with_it.get('peor_chunk'))}.",
          f"- Peor chunk sin Heraldia: {_blame_text(sin.get('peor_chunk'))}."]
    fa, fb = sin.get("franja"), with_it.get("franja")
    if fa and fb:
        name, x, z, rx, rz = STRIP
        t = fb["tramos"]
        L += ["", f"**Recorrido continuo** ({name}: x de {x - rx} a {x + rx}, z de {z - rz} a {z + rz}, {fb['chunks']} chunks "
              f"generados columna a columna, como volando; tramos de {t.get('bloques_por_tramo')} bloques, {t.get('chunks_por_tramo')} chunks)", "",
              "| | sin Heraldia | con Heraldia | diferencia |", "|---|---:|---:|---:|"]
        row("chunks/s", fa.get("chunks_por_s"), fb.get("chunks_por_s"))
        row("CPU del servidor, ms por chunk", fa.get("cpu_ms_por_chunk"), fb.get("cpu_ms_por_chunk"))
        row("tramo medio, ms por chunk", fa["tramos"].get("media_ms_por_chunk"), t.get("media_ms_por_chunk"))
        row("peor tramo, ms por chunk", fa["tramos"].get("peor_ms_por_chunk"), t.get("peor_ms_por_chunk"))
        row("peor tramo, s de trabajo", _sec(fa["tramos"].get("peor_ms")), _sec(t.get("peor_ms")), "{:.2f}")
        row("p99 (ms)", fa["picos"].get("p99_ms"), fb["picos"].get("p99_ms"))
        row("peor chunk (ms)", fa["picos"].get("max_ms"), fb["picos"].get("max_ms"))
        row(f"chunks de más de {TICK_MS} ms (%)", _pct(fa["picos"].get("lentos_fraccion")), _pct(fb["picos"].get("lentos_fraccion")), "{:.2f}")
        L += ["", f"- Peor tramo con Heraldia: x de {t.get('peor_desde_x')} a {t.get('peor_hasta_x')}; sin: x de "
                  f"{fa['tramos'].get('peor_desde_x')} a {fa['tramos'].get('peor_hasta_x')}.",
              f"- Peor chunk de la franja con Heraldia: {_blame_text(fb.get('peor_chunk'))}.",
              f"- Peor chunk de la franja sin Heraldia: {_blame_text(fa.get('peor_chunk'))}."]
    est = with_it.get("estructuras") or {}
    if est:
        L += ["", "**Estructuras más lentas de empezar** (con Heraldia; `minecraft.StructureGeneration`: reglas de colocación, "
                  "montaje y piezas; mediana de las pasadas)", "", "| estructura | intentos | generadas | total (ms) | máx. (ms) |",
              "|---|---:|---:|---:|---:|"]
        for k, v in list(est.items())[:12]:
            L.append(f"| {k} | {_f(v['intentos'], '{:.0f}')} | {_f(v['generadas'], '{:.0f}')} | {_f(v['total_ms'])} | {_f(v['max_ms'])} |")
    return L


def _pct(v):
    return None if v is None else v * 100


def _sec(ms):
    return None if ms is None else ms / 1000


def medium_profile(profiles):
    """Field-by-field median of the Heraldia profiles from several passes ({section: {n, total_ms, media_us, max_us}})."""
    out = {}
    for t in sorted({t for p in profiles for t in p}):
        vs = [p[t] for p in profiles if t in p]
        out[t] = {k: medium([v[k] for v in vs]) for k in ("n", "total_ms", "media_us", "max_us")}
    return out


def last_profile(text):
    m = None
    for line in text.splitlines():
        m = _PROFILE.search(line) or m
    return json.loads(m.group(1)) if m else None


def mspt_of(summary):
    """MSPT from the /jfr summary (serverTick): mean, p50, p90, p99 and max in ms."""
    t = (summary or {}).get("serverTick") or {}
    return {"media": t.get("averageMs"), "p50": t.get("p50"), "p90": t.get("p90"), "p99": t.get("p99"), "max": t.get("maxMs")}


def memory_of(heap_events):
    """Maximum heapUsed (MB) after each GC from the jdk.GCHeapSummary events of `jfr print --json`."""
    v = [e["values"]["heapUsed"] for e in heap_events if e["values"].get("when") == "After GC"]
    return max(v) / 2 ** 20 if v else None


# ---------------------------------------------------------------- servidor

def jfr_cli():
    home = os.environ.get("JAVA_HOME")
    for c in ([os.path.join(home, "bin", "jfr")] if home else []) + [shutil.which("jfr")]:
        if c and os.path.isfile(c):
            return c
    java = shutil.which("java")
    c = os.path.join(os.path.dirname(os.path.realpath(java)), "jfr") if java else None
    if c and os.path.isfile(c):
        return c
    raise SystemExit("could not find the JDK's jfr tool (JAVA_HOME/bin/jfr)")


def read_jfr_events(fname, kind):
    out = subprocess.run([jfr_cli(), "print", "--json", "--events", kind, fname], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def chunky(ctx, name, x, z, r, rz=None):
    """Generates with Chunky the square of half side r at (x, z) (concentric, Chunky's default) or, with `rz`, the
    rectangle of half sides r and rz column by column along x (pattern loop: like flying over it): (chunks reported
    by Chunky, wall-clock seconds)."""
    ctx.run(f"chunky shape {'square' if rz is None else 'rectangle'}", r"[Ss]hape|Chunky")
    ctx.run(f"chunky pattern {'concentric' if rz is None else 'loop'}", r"[Pp]attern|Chunky")
    ctx.run(f"chunky center {x} {z}", r"[Cc]enter|Chunky")
    ctx.run(f"chunky radius {r}" + ("" if rz is None else f" {rz}"), r"[Rr]adius|Chunky")
    s.pending(ctx.lines, ctx.seen)
    t0 = time.monotonic()
    s.send(ctx.proc, "chunky start")
    m = s.wait_for(ctx.lines, _CHUNKY_END.pattern + r"|Task (?:already|not) |[Cc]onfirm", CHUNKY_TIMEOUT_S, ctx.seen)
    if not m.group(0).startswith("Task finished"):
        if "onfirm" in m.group(0):
            s.send(ctx.proc, "chunky confirm")
            m = s.wait_for(ctx.lines, _CHUNKY_END.pattern, CHUNKY_TIMEOUT_S, ctx.seen)
        else:
            raise SystemExit(f"Chunky did not start at {name}: {m.string.strip()}")
    return int(m.group(2)), time.monotonic() - t0


def locate(ctx, target):
    """ms that /locate takes (as reported by the game itself: "Locating element ... took N ms"), or None if it finds nothing.
    The timing line and the reply may arrive in either order."""
    s.pending(ctx.lines, ctx.seen)
    s.send(ctx.proc, f"execute positioned {LOCATE_FROM[0]} 64 {LOCATE_FROM[1]} run locate structure {target}")
    ms, answer = None, None
    while ms is None or answer is None:
        m = s.wait_for(ctx.lines, _LOCATE.pattern + r"|is at \[|Could not find|" + s.ERROR_PATTERN, s.COMMAND_TIMEOUT_S, ctx.seen)
        if m.group(0).startswith("Locating element"):
            ms = int(m.group(2))
        elif m.group(0).startswith("is at"):
            answer = True
        else:
            return None
    return ms


def sweep(work, jar, with_it, launcher):
    """One pass in a new world (with or without Heraldia): dict with the measurements."""
    for d in ("world", "logs", "debug"):
        shutil.rmtree(os.path.join(work, d), ignore_errors=True)
    mods = os.path.join(work, "mods")
    own_item = os.path.join(mods, os.path.basename(jar))
    if with_it and not os.path.isfile(own_item):
        shutil.copy(jar, mods)
    if not with_it and os.path.isfile(own_item):
        os.remove(own_item)
    jvm = ["java", f"-Xmx{XMX}", f"-Xms{XMX}"] + (["-Dheraldia.perfil=true"] if with_it else [])
    proc = subprocess.Popen(jvm + ["-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    measurements = {"con": with_it}
    label = "with" if with_it else "without"
    try:
        cost_status.phase(f"pass {label} Heraldia: starting the server")
        s.wait_for(lines, r"Done \([\d.,]+s\)!", s.START_TIMEOUT_S, seen)
        if with_it and "Heraldia: perfil de la generación activado" not in ctx.log():
            raise SystemExit("with Heraldia but without its profile: was the mod not loaded?")
        if not with_it and re.search(r"Heraldia: \d+ estructuras registradas", ctx.log()):
            raise SystemExit("the pass without Heraldia loaded Heraldia")
        cost_status.phase(f"pass {label} Heraldia: warm-up")
        chunky(ctx, *WARMUP)
        ctx.run("jfr start", r"[Ss]tarted flight recorder|JFR profiling started|already")
        seconds, cpu = 0.0, 0.0
        for name, x, z, r in ZONES:
            cost_status.phase(f"pass {label} Heraldia: zone {name}")
            c0 = process_cpu(proc.pid)
            n, t = chunky(ctx, name, x, z, r)
            c1 = process_cpu(proc.pid)
            cpu = None if c0 is None or c1 is None or cpu is None else cpu + c1 - c0
            c = chunks_of_zone(x, z, r)
            if n != (c[2] - c[0] + 1) * (c[3] - c[1] + 1):
                raise SystemExit(f"Chunky generated {n} chunks at {name}; the measured zone has {(c[2] - c[0] + 1) * (c[3] - c[1] + 1)}")
            seconds += t
        name, x, z, rx, rz = STRIP
        cost_status.phase(f"pass {label} Heraldia: strip {name}")
        c0 = process_cpu(proc.pid)
        n, strip_s = chunky(ctx, name, x, z, rx, rz)
        c1 = process_cpu(proc.pid)
        if n != box_chunks(chunks_of_rect(x, z, rx, rz)):
            raise SystemExit(f"Chunky generated {n} chunks in the strip; it has {box_chunks(chunks_of_rect(x, z, rx, rz))}")
        strip_cpu = None if c0 is None or c1 is None else c1 - c0
        cost_status.phase(f"pass {label} Heraldia: jfr stop and /locate")
        m = ctx.run("jfr stop", _JFR_END.pattern)
        fname = os.path.join(work, m.group(1))
        summary = s.wait_for(lines, _JFR_SUMMARY.pattern, 120, seen)
        with open(os.path.join(work, summary.group(1)), encoding="utf-8") as f:
            measurements["mspt"] = mspt_of(json.load(f))
        measurements["locate_ms"] = {}
        for name, target, only_with in LOCATES:
            if only_with and not with_it:
                continue
            ms = locate(ctx, target)
            if ms is None:
                print(f"WARNING: /locate {target} finds nothing from {LOCATE_FROM}")
            else:
                measurements["locate_ms"][name] = ms
    finally:
        if proc.poll() is None:
            cost_status.note("stopping the server")
            try:
                s.send(proc, "stop")
                proc.wait(timeout=180)
            except (subprocess.TimeoutExpired, BrokenPipeError):
                proc.kill()
    s.pending(lines, seen)       # what the server wrote when stopping (Heraldia's profile is in there)
    cost_status.phase(f"pass {label} Heraldia: reading the .jfr")
    log = os.path.join(work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else "".join(seen)
    measurements["perfil"] = last_profile(text) if with_it else None
    if with_it and measurements["perfil"] is None:
        raise SystemExit("with Heraldia, 'Heraldia: perfil: {...}' does not appear in the log on stop")
    events = jfr_chunk_events(read_jfr_events(fname, "minecraft.ChunkGeneration"))
    structure_events = jfr_structure_events(read_jfr_events(fname, "minecraft.StructureGeneration"))
    measurements["memoria_mb"] = memory_of(read_jfr_events(fname, "jdk.GCHeapSummary")["recording"]["events"])
    measurements.update(tail(events, structure_events, strip_s, strip_cpu))
    zones = {n: chunks_summary(events, chunks_of_zone(x, z, r)) for n, x, z, r in ZONES}
    # the keys are those of generation_cost.json and cost_reference.json: they stay as they are
    measurements.update(chunks=sum(v["chunks"] for v in zones.values()), segundos=seconds, zonas=zones,
                        ms_por_chunk=join_zones(events, zones))
    total, v = measurements["chunks"], [measurements["ms_por_chunk"]["media_ms"]]
    measurements["cpu_ms_por_chunk"] = cpu * 1000 / total if cpu is not None else None
    print(f"PASADA {'con' if with_it else 'sin'} Heraldia: {total} chunks en {seconds:.1f} s, "
          f"CPU {_f(measurements['cpu_ms_por_chunk'])} ms por chunk, {v[0]:.1f} ms por chunk en los pasos "
          f"(p50 {_f(measurements['ms_por_chunk']['p50_ms'])}, p99 {_f(measurements['ms_por_chunk']['p99_ms'])}), "
          f"MSPT medio {_f(measurements['mspt']['media'])}, locate {measurements['locate_ms']}", flush=True)
    pk, st = measurements["picos"], measurements["franja"]
    print(f"PICOS {'con' if with_it else 'sin'} Heraldia: p95 {_f(pk['p95_ms'])}, p99 {_f(pk['p99_ms'])}, peor chunk {_f(pk['max_ms'])} ms "
          f"en {pk['peor_chunk']} ({measurements['peor_chunk']}), {pk['lentos']} chunks de más de {TICK_MS} ms; franja: "
          f"{st['chunks']} chunks en {st['segundos']:.1f} s, peor tramo {_f((st['tramos'] or {}).get('peor_ms_por_chunk'))} ms por chunk "
          f"(media {_f((st['tramos'] or {}).get('media_ms_por_chunk'))})", flush=True)
    return measurements


def tail(events, structure_events, strip_seconds, strip_cpu):
    """The peak measurements of one pass: the tail of the time per chunk in the zones (`picos`, with the worst chunk
    and what caused it), the structures slowest to start, and the continuous strip (its own tail, its stretches)."""
    zone_boxes = [chunks_of_zone(x, z, r) for _, x, z, r in ZONES]
    name, x, z, rx, rz = STRIP
    strip_box = chunks_of_rect(x, z, rx, rz)
    measured = (strip_box[0] + LEAD_IN_CHUNKS,) + strip_box[1:]       # without the run-up
    pc = per_chunk_ms(events, zone_boxes)
    pk = peaks(pc)
    spc = per_chunk_ms(events, [measured])
    spk = peaks(spc)
    n = box_chunks(strip_box)
    return {"picos": pk, "peor_chunk": blame(tuple(pk["peor_chunk"]), events, structure_events) if pk["peor_chunk"] else None,
            "estructuras": structures_summary(structure_events, zone_boxes + [strip_box]),
            "franja": {"chunks": n, "segundos": strip_seconds, "chunks_por_s": n / strip_seconds if strip_seconds else None,
                       "cpu_ms_por_chunk": strip_cpu * 1000 / n if strip_cpu is not None else None,
                       "picos": spk, "peor_chunk": blame(tuple(spk["peor_chunk"]), events, structure_events) if spk["peor_chunk"] else None,
                       "tramos": stretches(events, measured)}}


def measure(jar, work, sweeps, profile=None, variants=None):
    """Alternating passes (without, with, without, with...) in `work`: (list without, list with). With `profile`, the
    passes with Heraldia use that gameplay profile (e.g. "ligero") instead of the default one. With `variants` (a list of
    {"key": value}), each round has one pass without Heraldia and one with each variant: (list without, [list per variant])."""
    os.makedirs(work, exist_ok=True)
    launcher = s.prepare(work, jar, s.gradle_properties())
    with open(os.path.join(work, "server.properties"), encoding="utf-8") as f:
        props = re.sub(r"level-seed=.*", f"level-seed={SEED}", f.read())
    with open(os.path.join(work, "server.properties"), "w", encoding="utf-8") as f:
        f.write(props)
    modrinth.install(work, ["chunky"])
    sin, with_it = [], [[] for _ in (variants or [None])]
    for i in range(sweeps):
        sin.append(kept_sweep(work, jar, False, launcher))
        for j, v in enumerate(variants or [None]):
            with open(os.path.join(work, "config", "heraldia.json"), "w") as f:   # the server rewrites it at every start
                json.dump(config_of(profile, v), f)
            with_it[j].append(kept_sweep(work, jar, True, launcher))
    return sin, (with_it if variants else with_it[0])


OUTPUT = None        # --output: where each pass's server log and the passes measured so far are kept as they finish
_passes = 0
_measured = {"sin": [], "con": []}   # every pass of this run, both rounds (measure() starts its lists afresh on a retry)


def kept_sweep(work, jar, with_it, launcher):
    """sweep(), keeping in OUTPUT what a run that dies later would otherwise lose: this pass's server log (the next pass
    deletes it), logs/pasada-NN-<con|sin>.log, and every pass measured so far in either round, coste_generacion.parcial.json."""
    global _passes
    _passes += 1
    n, label = _passes, "con" if with_it else "sin"
    cost_status.phase(f"pass {n} ({label} Heraldia)")
    try:
        m = sweep(work, jar, with_it, launcher)
    finally:
        if OUTPUT:
            log = os.path.join(work, "logs", "latest.log")
            if os.path.isfile(log):
                os.makedirs(os.path.join(OUTPUT, "logs"), exist_ok=True)
                shutil.copy(log, os.path.join(OUTPUT, "logs", f"pasada-{n:02d}-{label}.log"))
    _measured[label].append(m)
    if OUTPUT:
        with open(os.path.join(OUTPUT, "coste_generacion.parcial.json"), "w", encoding="utf-8") as f:
            json.dump(_measured, f, ensure_ascii=False, indent=1, default=list)
    cost_status.phase(f"pass {n} ({label} Heraldia) measured",
                      f"CPU {_f(m.get('cpu_ms_por_chunk'))} ms per chunk, {m['chunks']} chunks in {m['segundos']:.1f} s")
    return m


def result_of(sin, with_it):
    import platform
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=s.ROOT, capture_output=True, text=True).stdout.strip()
    r = {"semilla": SEED, "zonas": [f"{n} ({x}, {z}) {side(x, r)}×{side(z, r)} chunks" for n, x, z, r in ZONES],
         "locate_desde": list(LOCATE_FROM), "fecha": time.strftime("%Y-%m-%d"), "commit": commit,
         "maquina": f"{os.cpu_count()} núcleos, {platform.system()}" + (" (CI)" if os.environ.get("GITHUB_ACTIONS") else ""),
         "sin": add_entry(sin), "con": add_entry(with_it), "perfil": medium_profile([p["perfil"] for p in with_it if p.get("perfil")]),
         "crudo": {"sin": sin, "con": with_it}}
    r["sobrecoste"] = overcost(r["con"], r["sin"])
    return r


def read_reference(route=REFERENCE):
    if not os.path.isfile(route):
        return None
    with open(route, encoding="utf-8") as f:
        return json.load(f)


def write(result, comparison, output):
    os.makedirs(output, exist_ok=True)
    result = dict(result, comparacion={"ok": comparison[0], "limite": comparison[1], "texto": comparison[2]})
    if len(comparison) > 3:
        result["comparacion_picos"] = {"ok": comparison[3], "texto": comparison[4]}
    with open(os.path.join(output, "coste_generacion.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=list)
    md = markdown(result, comparison)
    with open(os.path.join(output, "coste_generacion.md"), "w", encoding="utf-8") as f:
        f.write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    return md


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jar")
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-coste"))
    ap.add_argument("--sweeps", type=int, default=SWEEPS, help=f"passes per configuration (default {SWEEPS})")
    ap.add_argument("--output", default=os.path.join(s.ROOT, "build", "coste"), help="folder for the JSON and the Markdown")
    ap.add_argument("--reference", default=REFERENCE)
    ap.add_argument("--update-reference", action="store_true", help="saves the measurement as the new reference")
    ap.add_argument("--no-threshold", action="store_true", help="measures and reports, but does not fail on the threshold")
    ap.add_argument("--no-retry", action="store_true", help="if it exceeds the threshold, does not repeat another round of passes")
    ap.add_argument("--from-json", help="does not measure: uses this coste_generacion.json (e.g. the CI artifact)")
    ap.add_argument("--profile", help="the passes with Heraldia use this gameplay profile (e.g. ligero); implies --no-threshold")
    ap.add_argument("--variant", action="append", type=parse_variant, metavar="KEY=VALUE[,KEY=VALUE]",
                    help="a Heraldia configuration to measure (repeatable): each round, one pass without Heraldia and one with each "
                         "variant; writes coste_variantes.json/.md with one table; implies --no-threshold")
    ap.add_argument("--zones", choices=sorted(LAYOUTS), default="estandar",
                    help="measured zones: estandar (the reference's) or medianas (four large squares on open land, to compare "
                         "medium-structure densities)")
    a = ap.parse_args(argv)
    global ZONES, OUTPUT
    if not a.from_json:
        OUTPUT = os.path.abspath(a.output)
        cost_status.start(OUTPUT, "coste")
    ref = read_reference(a.reference)
    ZONES = LAYOUTS[a.zones]
    if a.variant:
        if not a.jar:
            ap.error("--variant needs --jar")
        sin, per_variant = measure(os.path.abspath(a.jar), os.path.abspath(a.work), a.sweeps, a.profile, a.variant)
        results = [(v, result_of(sin, w)) for v, w in zip(a.variant, per_variant)]
        os.makedirs(a.output, exist_ok=True)
        with open(os.path.join(a.output, "coste_variantes.json"), "w", encoding="utf-8") as f:
            json.dump({"zonas": a.zones, "perfil": a.profile or "estandar",
                       "variantes": [{"opciones": v, "resultado": r} for v, r in results]}, f, ensure_ascii=False, indent=1, default=list)
        md = variants_markdown(results)
        with open(os.path.join(a.output, "coste_variantes.md"), "w", encoding="utf-8") as f:
            f.write(md)
        print(md)
        cost_status.finish(True, f"{len(results)} variants measured (no threshold)")
        return 0

    def decide(res, ref):
        return compare(res["sobrecoste"], ref) + compare_peaks(res, ref)
    if a.from_json:
        with open(a.from_json, encoding="utf-8") as f:
            res = json.load(f)
    else:
        if not a.jar:
            ap.error("--jar is required (or --from-json)")
        jar, work = os.path.abspath(a.jar), os.path.abspath(a.work)
        if a.profile:
            a.no_threshold = True
        sin, with_it = measure(jar, work, a.sweeps, a.profile)
        res = result_of(sin, with_it)
        res["perfil_medido"] = a.profile or "estandar"
        comp = decide(res, ref)
        cost_status.phase(f"first round compared: {comp[2]}; {comp[4]}")
        if not (comp[0] and comp[3]) and ref and not a.no_retry and not a.update_reference:
            cost_status.phase("over the limit: a second round of passes")
            print(f"{comp[2]}; {comp[4]}: a round of {a.sweeps} passes is repeated and the decision is made with all of them", flush=True)
            without_it2, with_it2 = measure(jar, work, a.sweeps, a.profile)
            res = result_of(sin + without_it2, with_it + with_it2)
    comp = decide(res, ref)
    if a.update_reference:
        new_one = new_reference(res, ref)
        with open(a.reference, "w", encoding="utf-8") as f:
            json.dump(new_one, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"referencia guardada en {a.reference}: sobrecoste {new_one['sobrecoste']:+.1%}")
        comp = decide(res, new_one)
    md = write(res, comp, a.output)
    print(md)
    print("COSTE:", comp[2])
    print("PICOS:", comp[4])
    cost_status.finish(comp[0] and comp[3], f"{comp[2]}; {comp[4]}")
    return 0 if (comp[0] and comp[3]) or a.no_threshold else 1


if __name__ == "__main__":
    sys.exit(cost_status.guard(main))
