"""Heraldia play cost: the server tick time (MSPT) and the loaded entities while players are in Heraldia villages, with the
wave arena running and with a caravan on the road, against the same scenarios without the mod and a vanilla village.

Usage:
  python3 tools/smoke/runtime_cost.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-juego"
  python3 tools/smoke/runtime_cost.py ... --update-reference       # measures and saves the new reference
  python3 tools/smoke/runtime_cost.py --from-json build/juego/coste_juego.json [--update-reference]
      # rebuilds the summary (or the reference) from a measurement already taken, e.g. the CI artifact "coste-juego"

What generation_cost.py does not see: generating the world is paid once, playing it is paid every tick. Each pass starts a
fresh 26.3 dedicated server (world deleted, seed SEED, Fabric API, Carpet and Chunky; view and simulation distance VIEW,
the vanilla defaults), once with the Heraldia .jar (default configuration, except that the arena does not build itself
and caravans only leave with the command) and once without it, alternating. In each pass Chunky generates the areas first
(generation is not what is measured here), the day is frozen at TIME_OF_DAY (villagers at work: the busiest part of their
day), the weather is clear, autosave is off during the windows and natural mob spawning is on. Then, for each scenario of
SCENARIOS, Carpet's simulated players stand where the scenario says, the server settles for WARMUP_S seconds and then, for
MEASURE_S seconds, TickSampler.java reads the duration of every tick from the server's own JMX bean (outside the game:
nothing is measured differently with and without the mod). At the end of each window the loaded entities are counted by
type with /execute if entity.

Scenarios (the positions come from the seed and are found in the first pass with Heraldia: /locate, the road log, the arena
site; the passes without Heraldia use the same ones, where there is only terrain or, for the vanilla village, the same village):
  campo         one player in the open, at 0,0 (the control).
  aldea_vanilla one player in the vanilla village closest to 0,0.
  aldea         one player on the square of the Heraldia village closest to 0,0.
  dos_aldeas    two players, one in that village and one in the village at the other end of one of its roads.
  caravana      one player in the village and another on the road halfway to the neighbouring village, with a caravan
                (with the ambush) that sets off next to them at the start of the window.
  aldea_arena   one player in the village and another in the wave arena (placed next to spawn), with a game running:
                every WAVE_KILL_S seconds one of its enemies is killed in the player's name, so the waves advance.
  aldea_evento  "aldea" with a village event (EVENT_KIND, a wedding: the biggest, 15 figures and its fireworks) started in the
                player's village just before the warm-up (/heraldia event start; natural events are off: eventos.frecuencia 0).
  dos_aldeas_evento  "dos_aldeas" with one in each village: two events at once, the case the owner's caps were set for.
  mediana       one player at the roadside inn closest to 0,0 (#heraldia:medianas/posada: its inhabitants, the innkeeper
                with the gardener or with two pigs; the medium structure with the most of them), alone in the open.
  casa_heraldo  one player on the plaza of the Herald's House (its 18 residents, the bailiff, the watch's golems, the
                animals, and the roads' huts with their villagers, built right after the town: herald/SpawnRoads): the town
                does not build itself in these worlds, so an operator places it (/heraldia herald place here) at HOUSE_AT
                from 0,0 (far from every other scenario) before its window.
And, with Heraldia, the margin (ESCALATION): in the "aldea" scenario, villagers are added in steps (unemployed: they search
for a bed and a job site, the most expensive case) and each step is measured: from the line that fits the MSPT against
the villagers loaded, how many more the server takes before its tick gets close to the 50 ms it has.

Per scenario: MSPT mean, median, p95, p99, the worst tick and the share of ticks over 50 ms; the ticks seen against the
expected ones; the entities by type (villagers, golems, monsters, animals, merchants, items, the rest). Several passes (--sweeps N)
are combined with the median (the worst tick, with the maximum).

Limit (runtime_reference.json, "limites"): with Heraldia, in every scenario, the p99 must stay under a tick (50 ms) and the
p95 may not exceed the one without Heraldia (same scenario) by more than `p95_extra_ms`; and the Heraldia village may not cost
more than `aldea_vs_vanilla` times the vanilla village (p95, with `margen_ms` of noise allowance). If it fails, one more round of passes is
run and the median of all decides (CI noise). Writes <output>/coste_juego.json and <output>/coste_juego.md (and the Markdown to
$GITHUB_STEP_SUMMARY). Exit code 0 if it passes. The pure functions are tested in tools/gen/tests/test_runtime_cost.py.
"""
import argparse, json, math, os, queue, re, shutil, statistics, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import modrinth
from generation_cost import chunky, percentile
import cost_status                  # noqa: E402  (tools/cost_status.py, on sys.path through generation_cost)

REFERENCE = os.path.join(s.ROOT, "tools", "smoke", "runtime_reference.json")
SAMPLER = os.path.join(s.ROOT, "tools", "smoke", "TickSampler.java")
SEED = "heraldia"
VIEW = 10                   # view and simulation distance (chunks): the vanilla defaults
TICK_MS = 50
TIME_OF_DAY = 2000          # morning: villagers go to their job sites (2000-9000)
WARMUP_S, MEASURE_S, SWEEPS = 30, 60, 1
WAVE_KILL_S = 8
PREGEN_R = VIEW * 16 + 48   # blocks around each position that Chunky generates first (the player's view plus a margin)
PLAYERS = ("Medidor1", "Medidor2")
SCENARIOS = ["campo", "aldea_vanilla", "aldea", "dos_aldeas", "caravana", "aldea_arena"]
# Village events (events/VillageEvents): the same as "aldea" and "dos_aldeas" with a wedding (the biggest event: 15 figures
# and its fireworks) started in each player's village just before the window (without Heraldia: the same positions).
SCENARIOS += ["aldea_evento", "dos_aldeas_evento"]
# Scenarios where Heraldia has something of its own (the others are the control and the vanilla village).
OWN = ["aldea", "dos_aldeas", "caravana", "aldea_arena"]
OWN += ["aldea_evento", "dos_aldeas_evento"]
EVENT_KIND = "wedding"
EVENT_STARTS = r"Heraldia: events: event \d+ starts: \w+ in .*?, (\d+) figures|Heraldia: events: \w+ not started: (\w+)"
SCENARIOS += ["mediana"]           # the medium structures' inhabitants (mediums/_inhabitants.py)
SCENARIOS += ["casa_heraldo"]      # the Herald's House (herald/, tools/gen/herald_house.py)
SINGLE = ("campo", "aldea_vanilla", "aldea", "aldea_evento", "mediana", "casa_heraldo")    # one player
OWN += ["mediana", "casa_heraldo"]
HOUSE_AT = 700                     # blocks from 0,0 (and from every other position) where the town is placed
HOUSE_PLACED = re.compile(r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+)")
ROADS_BUILT = re.compile(r"herald's house roads: built in (\d+) ticks .*?(\d+) new villagers")
GROUNDS_BUILT = re.compile(r"herald's house grounds: built in (\d+) ticks")
ESCALATION = [0, 25, 50, 100, 150]          # villagers added (cumulative) in the margin steps
ESCALATION_WARMUP_S, ESCALATION_MEASURE_S = 40, 60
ESCALATION_RADIUS = 24                      # around the square
XMX = "3G"
# Entities counted by type (an unknown type in this version just counts 0).
GROUPS = {
    "aldeanos": ["villager"],
    "golems": ["iron_golem", "snow_golem"],
    "monstruos": ["zombie", "zombie_villager", "husk", "drowned", "skeleton", "stray", "bogged", "creeper", "spider",
                  "cave_spider", "enderman", "witch", "slime", "phantom", "pillager", "vindicator", "evoker", "ravager", "vex",
                  "guardian", "silverfish", "breeze", "parched", "zombie_horse", "skeleton_horse", "zombie_nautilus"],
    "animales": ["cow", "sheep", "pig", "chicken", "horse", "donkey", "mule", "llama", "cat", "wolf", "fox", "rabbit", "frog",
                 "tadpole", "bee", "parrot", "panda", "ocelot", "goat", "axolotl", "turtle", "mooshroom", "polar_bear", "camel",
                 "armadillo", "sniffer", "bat", "squid", "glow_squid", "cod", "salmon", "tropical_fish", "pufferfish", "dolphin",
                 "allay", "nautilus", "happy_ghast"],
    "comerciantes": ["wandering_trader", "trader_llama"],
    "objetos": ["item", "experience_orb"],
}
ROUTE = re.compile(r"camino entre las aldeas de (-?\d+) (-?\d+) y (-?\d+) (-?\d+): (\d+) bloques")
SITE = re.compile(r"arena: sitio propuesto en (-?\d+) (-?\d+) (-?\d+)")
PLACED = re.compile(r"arena: colocada en (-?\d+) (-?\d+) (-?\d+) \(caja (-?\d+) (-?\d+) (-?\d+) a (-?\d+) (-?\d+) (-?\d+)\)")
DEPARTS = re.compile(r"sale la caravana (\d+) de")
NO_ROAD = r"There is no Heraldia road|No hay ningún camino"
LOCATED = r"is at \[(-?\d+), ~, (-?\d+)\]|Could not find"


# ---------------------------------------------------------------- pure functions (tests in test_runtime_cost.py)

def tick_stats(ticks_ns, seconds=None):
    """Statistics of the tick durations (ns): mean, p50, p95, p99, max in ms, the share over a tick and, with `seconds`,
    the ticks per second seen."""
    v = [t / 1e6 for t in ticks_ns]
    if not v:
        return {"ticks": 0}
    out = {"ticks": len(v), "media": statistics.fmean(v), "p50": percentile(v, 50), "p95": percentile(v, 95),
           "p99": percentile(v, 99), "max": max(v), "lentos": sum(1 for x in v if x > TICK_MS)}
    out["lentos_pct"] = out["lentos"] / len(v)
    if seconds:
        out["tps"] = len(v) / seconds
    return out


def parse_sampler(text):
    """(tick durations in ns, polls, lost) from TickSampler's output."""
    ticks, polls, lost = [], 0, 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# polls"):
            parts = line.split()
            polls, lost = int(parts[2]), int(parts[4])
        elif line.isdigit():
            ticks.append(int(line))
    return ticks, polls, lost


def group_counts(by_type, total, players=0):
    """{group: count} from {type: count}, with "otros" = the rest of the loaded entities (without the players) and "total"."""
    out = {g: sum(by_type.get(t, 0) for t in types) for g, types in GROUPS.items()}
    out["otros"] = max(0, total - players - sum(out.values()))
    out["total"] = max(0, total - players)
    return out


def fit(points):
    """Least squares line y = a + b x of [(x, y)]: (a, b), or None with fewer than two distinct x."""
    pts = [(x, y) for x, y in points if x is not None and y is not None]
    if len({x for x, _ in pts}) < 2:
        return None
    mx = statistics.fmean(x for x, _ in pts)
    my = statistics.fmean(y for _, y in pts)
    b = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    return my - b * mx, b


def margin(points, target):
    """How many more x (villagers) the fitted line takes, from the smallest measured x (the village as it generates), until
    it reaches `target` ms; None if the line does not grow (the cost of the added villagers is not visible over the noise)."""
    f = fit(points)
    if f is None or f[1] <= 0:
        return None
    a, b = f
    x0 = min(x for x, _ in points if x is not None)
    return max(0.0, (target - (a + b * x0)) / b)


def combine(passes):
    """The passes of one scenario (dicts with "mspt" and "entidades") combined: median of each measurement, the worst tick
    is the maximum of the passes."""
    if not passes:
        return None
    out = {"pasadas": len(passes), "mspt": {}, "entidades": {}}
    for k in ("media", "p50", "p95", "p99", "lentos_pct", "tps", "ticks"):
        v = [p["mspt"].get(k) for p in passes if p["mspt"].get(k) is not None]
        out["mspt"][k] = statistics.median(v) if v else None
    v = [p["mspt"].get("max") for p in passes if p["mspt"].get("max") is not None]
    out["mspt"]["max"] = max(v) if v else None
    for g in list(GROUPS) + ["otros", "total"]:
        v = [p["entidades"].get(g) for p in passes if p.get("entidades") and p["entidades"].get(g) is not None]
        out["entidades"][g] = statistics.median(v) if v else None
    for k in ("heraldia_arena", "heraldia_caravana", "heraldia_habitantes"):
        v = [p.get(k) for p in passes if p.get(k) is not None]
        if v:
            out[k] = statistics.median(v)
    return out


# Measured (local, 4 cores, 2 passes, 18-11-2026): p95 with minus without Heraldia +2.4 (one village), +7.1 (two), +3.1 (caravan),
# +3.2 (arena) ms; p99 at most 34 ms; the Heraldia village 1.3 times the vanilla one at p95. The limits catch a real
# regression (a village that costs half as much again, a scenario over a tick) without failing on noise.
LIMITS = {"mspt_p99_ms": TICK_MS, "p95_extra_ms": 10.0, "aldea_vs_vanilla": 2.0, "margen_ms": 3.0}


def compare(result, reference=None):
    """(ok, text) of the limits: with Heraldia, every scenario under a tick at p99 and its p95 at most `p95_extra_ms` above
    the same scenario without Heraldia; the Heraldia village (p95) at most `aldea_vs_vanilla` times the vanilla one plus
    `margen_ms`."""
    lim = dict(LIMITS, **((reference or {}).get("limites") or {}))
    bad, parts = [], []
    con, sin = result["con"], result["sin"]
    for sc in SCENARIOS:
        c, n = (con.get(sc) or {}).get("mspt") or {}, (sin.get(sc) or {}).get("mspt") or {}
        if c.get("p99") is not None and c["p99"] > lim["mspt_p99_ms"]:
            bad.append(f"{sc}: p99 {c['p99']:.1f} ms > {lim['mspt_p99_ms']:.0f}")
        if sc in OWN and c.get("p95") is not None and n.get("p95") is not None:
            extra = c["p95"] - n["p95"]
            parts.append(f"{sc} p95 {n['p95']:.1f} → {c['p95']:.1f} ms ({extra:+.1f})")
            if extra > lim["p95_extra_ms"]:
                bad.append(f"{sc}: p95 {extra:+.1f} ms over the same scenario without Heraldia (limit {lim['p95_extra_ms']:+.1f})")
    va, al = ((con.get("aldea_vanilla") or {}).get("mspt") or {}).get("p95"), ((con.get("aldea") or {}).get("mspt") or {}).get("p95")
    if va is not None and al is not None:
        parts.append(f"aldea Heraldia/vanilla p95 {al:.1f}/{va:.1f} ms")
        if al > va * lim["aldea_vs_vanilla"] + lim["margen_ms"]:
            bad.append(f"the Heraldia village costs {al:.1f} ms at p95, more than {lim['aldea_vs_vanilla']:.1f} × the vanilla one "
                       f"({va:.1f}) + {lim['margen_ms']:.0f} ms")
    text = "; ".join(parts) + (("; FALLA: " + "; ".join(bad)) if bad else "; dentro de los límites")
    return not bad, text


def escalation_summary(steps, targets=(40.0, 50.0)):
    """The margin from the escalation steps [{"aldeanos": n, "mspt": {...}}]: ms per villager (mean, p95, p99) and how many
    more villagers until each target."""
    if not steps:
        return None
    out = {"pasos": [{"aldeanos": st["entidades"].get("aldeanos"), "total": st["entidades"].get("total"),
                      **{k: st["mspt"].get(k) for k in ("media", "p50", "p95", "p99", "max")}} for st in steps]}
    for k in ("media", "p95", "p99"):
        pts = [(p["aldeanos"], p[k]) for p in out["pasos"]]
        f = fit(pts)
        out[f"ms_por_aldeano_{k}"] = f[1] if f else None
        for tg in targets:
            out[f"margen_{k}_{int(tg)}ms"] = margin(pts, tg)
    return out


def _f(v, fmt="{:.1f}"):
    return "—" if v is None else fmt.format(v)


def markdown(result, comparison=None):
    con, sin = result["con"], result["sin"]
    L = ["## Coste de jugar (tiempo por tick con y sin Heraldia)", "",
         f"Semilla `{result['semilla']}`, distancia de visión y simulación {result['vista']}, {result['maquina']}, "
         f"{result['pasadas']} pasada(s) de {result['segundos']} s por escenario, commit {result['commit']}.", "",
         "| Escenario | Sin: media / p50 / p95 / p99 / peor (ms) | Con: media / p50 / p95 / p99 / peor (ms) | Ticks > 50 ms (con) | "
         "Entidades sin → con (aldeanos, gólems, monstruos, animales) |", "| --- | --- | --- | --- | --- |"]
    for sc in SCENARIOS:
        a, b = sin.get(sc) or {}, con.get(sc) or {}
        ma, mb = a.get("mspt") or {}, b.get("mspt") or {}
        ea, eb = a.get("entidades") or {}, b.get("entidades") or {}

        def five(m):
            return " / ".join(_f(m.get(k)) for k in ("media", "p50", "p95", "p99", "max"))

        def ents(e):
            return f"{_f(e.get('total'), '{:.0f}')} ({', '.join(_f(e.get(g), '{:.0f}') for g in ('aldeanos', 'golems', 'monstruos', 'animales'))})"
        extra = []
        if b.get("heraldia_arena"):
            extra.append(f"arena {b['heraldia_arena']:.0f}")
        if b.get("heraldia_caravana"):
            extra.append(f"caravana {b['heraldia_caravana']:.0f}")
        L.append(f"| {sc} | {five(ma)} | {five(mb)} | {_f(mb.get('lentos_pct'), '{:.1%}')} | {ents(ea)} → {ents(eb)}"
                 f"{' [' + ', '.join(extra) + ']' if extra else ''} |")
    esc = result.get("escalada")
    if esc:
        L += ["", "**Margen: aldeanos añadidos en la aldea (con Heraldia)**", "",
              "| Aldeanos cargados | Entidades | media | p50 | p95 | p99 | peor (ms) |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for p in esc["pasos"]:
            L.append(f"| {_f(p['aldeanos'], '{:.0f}')} | {_f(p['total'], '{:.0f}')} | {_f(p['media'])} | {_f(p['p50'])} | "
                     f"{_f(p['p95'])} | {_f(p['p99'])} | {_f(p['max'])} |")
        L += ["", f"Coste por aldeano: {_f(esc.get('ms_por_aldeano_media'), '{:.3f}')} ms de media, "
                  f"{_f(esc.get('ms_por_aldeano_p95'), '{:.3f}')} ms en el p95. Margen desde la aldea tal como se genera, hasta 40 ms de p95: "
                  f"{_f(esc.get('margen_p95_40ms'), '{:.0f}')} aldeanos más; hasta 50 ms: {_f(esc.get('margen_p95_50ms'), '{:.0f}')} "
                  f"(media: {_f(esc.get('margen_media_40ms'), '{:.0f}')} / {_f(esc.get('margen_media_50ms'), '{:.0f}')})."]
    if comparison:
        L += ["", ("✅ " if comparison[0] else "❌ ") + comparison[1]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- server

def config():
    return {"arena": {"generar_en_mundos_nuevos": False}, "caravanas": {"frecuencia": 0},
            "update_check": {"activado": False},
            "casa_heraldo": {"generar_en_mundos_nuevos": False},
            "eventos": {"frecuencia": 0}}     # village events only with the command (the *_evento scenarios)


def properties(work, jmx_port):
    path = os.path.join(work, "server.properties")
    with open(path, encoding="utf-8") as f:
        p = f.read()
    for k, v in (("view-distance", VIEW), ("simulation-distance", VIEW), ("level-seed", SEED), ("difficulty", "normal")):
        p = re.sub(rf"(?m)^{k}=.*\n?", "", p)
        p += f"{k}={v}\n"
    p = re.sub(r"(?m)^enable-jmx-monitoring=.*\n?", "", p) + "enable-jmx-monitoring=true\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(p)


class Pass:
    """One server (with or without Heraldia) and its measurements."""

    def __init__(self, work, jar, with_it, launcher, fresh=True):
        self.work, self.with_it, self.jar = work, with_it, jar
        for d in (("world", "logs") if fresh else ("logs",)):
            shutil.rmtree(os.path.join(work, d), ignore_errors=True)
        own = os.path.join(work, "mods", os.path.basename(jar))
        if with_it and not os.path.isfile(own):
            shutil.copy(jar, os.path.join(work, "mods"))
        if not with_it and os.path.isfile(own):
            os.remove(own)
        with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
            json.dump(config(), f)
        self.jmx = s.free_port()
        properties(work, self.jmx)
        jvm = ["java", f"-Xmx{XMX}", f"-Xms{XMX}", f"-Dcom.sun.management.jmxremote.port={self.jmx}",
               f"-Dcom.sun.management.jmxremote.rmi.port={self.jmx}", "-Dcom.sun.management.jmxremote.authenticate=false",
               "-Dcom.sun.management.jmxremote.ssl=false", "-Dcom.sun.management.jmxremote.host=127.0.0.1",
               "-Djava.rmi.server.hostname=127.0.0.1"]
        self.proc = subprocess.Popen(jvm + ["-jar", launcher, "nogui"], cwd=work, text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.lines, self.seen = queue.Queue(), []
        threading.Thread(target=s.reader, args=(self.proc, self.lines), daemon=True).start()
        self.ctx = s.Context(self.proc, self.lines, self.seen)
        try:
            self._ready(with_it)
        except BaseException:
            self.stop()          # a server that fails to start must not stay running (and loading the machine)
            raise

    def _ready(self, with_it):
        s.wait_for(self.lines, r"Done \([\d.,]+s\)!", s.START_TIMEOUT_S, self.seen)
        loaded = "Heraldia: configuración leída" in self.ctx.log()
        if loaded != with_it:
            raise SystemExit(f"the pass {'with' if with_it else 'without'} Heraldia {'did not load' if with_it else 'loaded'} it")
        c = self.ctx
        for rule, v in (("advance_time", "false"), ("advance_weather", "false"), ("keep_inventory", "true")):
            # `must`, and no failure words in the pattern: these three rules keep a 60 s measurement from depending on
            # the time of day or the weather, so a `gamerule` that did not take has to stop the run, not be waited on.
            c.must(f"gamerule {rule} {v}", rf"[Gg]ame ?rule .*{rule}.*{v}")
        s.send(c.proc, f"time set {TIME_OF_DAY}")      # neither answers if nothing changes (on the restart)
        s.send(c.proc, "weather clear")
        c.run("time query gametime", r"[Tt]ime is \d+")

    def stop(self):
        if self.proc.poll() is None:
            try:
                s.send(self.proc, "stop")
                self.proc.wait(timeout=180)
            except (subprocess.TimeoutExpired, BrokenPipeError):
                self.proc.kill()

    # --- positions (found with Heraldia)
    def locate(self, target, x=0, z=0):
        m = self.ctx.run(f"execute positioned {x} 100 {z} run locate structure {target}", LOCATED)
        return (int(m.group(1)), int(m.group(2))) if m.group(1) else None

    def pregen(self, name, pos):
        n, t = chunky(self.ctx, name, pos[0], pos[1], PREGEN_R)
        print(f"generated {n} chunks around {name} {pos} in {t:.0f} s", flush=True)

    def find_positions(self):
        """The positions of the scenarios (in the world of the seed): the villages, the road point, the arena site."""
        c = self.ctx
        pos = {"campo": (0, 0)}
        v = self.locate("#minecraft:village")
        a = self.locate("#heraldia:aldeas")
        if not v or not a:
            raise SystemExit(f"/locate does not find the villages ({v}, {a})")
        pos["aldea_vanilla"], pos["aldea"] = (v[0] + 8, v[1] + 8), (a[0] + 8, a[1] + 8)
        m = self.locate("#heraldia:medianas/posada")
        if not m:
            raise SystemExit("/locate does not find a roadside inn (the medium structure scenario)")
        pos["mediana"] = (m[0] + 8, m[1] + 8)
        others = [pos["aldea"], pos["aldea_vanilla"], pos["mediana"], (0, 0)]
        for cand in ((HOUSE_AT, HOUSE_AT), (-HOUSE_AT, HOUSE_AT), (HOUSE_AT, -HOUSE_AT), (-HOUSE_AT, -HOUSE_AT)):
            if all(math.dist(cand, o) >= HOUSE_AT for o in others):
                pos["casa_heraldo"] = cand
                break
        else:
            raise SystemExit("no spot for the Herald's House far from the other scenarios")
        self.pregen("aldea", pos["aldea"])
        routes = []
        for r in ROUTE.finditer(c.log()):
            p, q, L = (int(r.group(1)), int(r.group(2))), (int(r.group(3)), int(r.group(4))), int(r.group(5))
            if math.dist(p, pos["aldea"]) < 24 or math.dist(q, pos["aldea"]) < 24:
                routes.append((p, q, L) if math.dist(p, pos["aldea"]) < 24 else (q, p, L))
        if not routes:
            raise SystemExit(f"no road from the village at {pos['aldea']} in the log")
        a, b, L = min(routes, key=lambda r: r[2])
        pos["aldea_b"] = b
        pos["ruta"] = [list(a), list(b)]
        m = c.run("heraldia arena place", SITE.pattern + r"|Ya hay una arena|There is already")
        if not m.group(1):
            raise SystemExit(f"the arena proposes no site: {m.string.strip()}")
        pos["arena"] = (int(m.group(1)), int(m.group(3)))
        pos["arena_y"] = int(m.group(2))
        return {k: list(v) if isinstance(v, tuple) else v for k, v in pos.items()}

    # --- players
    def player(self, name, x, z, mode="creative"):
        c = self.ctx
        s.require_carpet(c)
        c.run(f"player {name} spawn at {x + 0.5} 200 {z + 0.5}", r"joined the game")
        c.until(f"execute if entity @a[name={name}]")
        s.send(c.proc, f"gamemode {mode} {name}")          # no reply if it already is in that mode
        if not c.until(f"execute if entity @a[name={name},gamemode={mode}]", timeout=30):
            raise SystemExit(f"{name} is not in {mode} mode")
        # the player has just logged in 200 blocks up: its column may not be loaded for a moment yet, and then there is
        # no ground to be put on ("That position is not loaded"). Left up there, it is in no village, and what the
        # scenario starts next has nobody to start for
        for _ in range(60):
            m = c.run(f"execute positioned {x} 320 {z} positioned over motion_blocking_no_leaves run tp {name} ~ ~ ~",
                      r"Teleported|No entity|not loaded")
            if "not loaded" not in m.string:            # the whole reply, not only the part of it that matched
                break
            time.sleep(0.5)
        else:
            raise SystemExit(f"{name}: the column at {x} {z} did not load in 30 s")
        if mode == "survival":
            for e in ("resistance", "saturation"):      # "Unable": it still has it from an earlier scenario (saved player data)
                c.run(f"effect give {name} minecraft:{e} infinite 255 true", r"Applied effect|Gave|Unable")

    def nobody(self):
        for p in PLAYERS:
            if self.ctx.test(f"execute if entity @a[name={p}]"):
                self.ctx.run(f"player {p} kill", r"left the game")

    # --- measurement
    def window(self, seconds, during=None):
        """Tick durations of `seconds` (TickSampler, from outside) while `during()` is called every WAVE_KILL_S."""
        java = os.path.join(os.environ["JAVA_HOME"], "bin", "java") if os.environ.get("JAVA_HOME") else "java"
        self.ctx.run("save-off", r"[Aa]utomatic saving|already")
        sampler = subprocess.Popen([java, SAMPLER, str(self.jmx), str(seconds)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        t0 = time.monotonic()
        while sampler.poll() is None:
            time.sleep(min(WAVE_KILL_S, 1.0) if during else 1.0)
            if during and time.monotonic() - t0 >= WAVE_KILL_S:
                during()
                t0 = time.monotonic()
        out, err = sampler.communicate()
        self.ctx.run("save-on", r"[Aa]utomatic saving|already")
        ticks, polls, lost = parse_sampler(out)
        if not ticks:
            raise SystemExit(f"TickSampler read no ticks: {err.strip()[-400:]}")
        st = tick_stats(ticks, seconds)
        st["perdidos"] = lost
        return st

    def entities(self, names):
        """The entities within the simulation distance of each of these players (they stand far apart: no overlap). The
        selector is anchored at the player's position (an `execute at` would fork and might not answer)."""
        r = VIEW * 16
        by_type, total, players = {}, 0, 0
        for n in names:
            p = self.ctx.pos(f"@a[name={n}]")
            if p is None:
                continue
            near = f"x={p[0]:.1f},y={p[1]:.1f},z={p[2]:.1f},distance=..{r}"
            for types in GROUPS.values():
                for t in types:
                    by_type[t] = by_type.get(t, 0) + self.ctx.count(f"@e[type=minecraft:{t},{near}]")
            total += self.ctx.count(f"@e[{near}]")
            players += self.ctx.count(f"@a[{near}]")
        return group_counts(by_type, total, players)

    def scenario(self, sc, pos, seconds, warmup):
        c = self.ctx
        self.nobody()
        x, z = pos["aldea"]
        during = None
        if sc in ("campo", "aldea_vanilla", "aldea", "mediana"):      # one player at the scenario's own position
            self.player(PLAYERS[0], *pos[sc])
        elif sc == "casa_heraldo":
            hx, hz = pos[sc]
            if self.with_it:
                hx, hz = self.place_house(hx, hz)
                self.nobody()                       # the operator who placed it, out: the window starts clean
            self.player(PLAYERS[0], hx, hz)
        elif sc == "aldea_evento":
            self.player(PLAYERS[0], x, z)
            self.start_events(PLAYERS[:1])
        elif sc == "dos_aldeas_evento":
            self.player(PLAYERS[0], x, z); self.player(PLAYERS[1], *pos["aldea_b"])
            self.start_events(PLAYERS)
        elif sc == "dos_aldeas":
            self.player(PLAYERS[0], x, z); self.player(PLAYERS[1], *pos["aldea_b"])
        elif sc == "caravana":
            self.player(PLAYERS[0], x, z); self.player(PLAYERS[1], *pos["camino"], mode="survival")
        elif sc == "aldea_arena":
            self.player(PLAYERS[0], x, z)
            ax, az = pos["arena"]
            if self.with_it:
                box = self.place_arena()
                bp = pos.get("arena_plano") or {}
                cx, cz = box[0] + bp.get("centro", [28, 1, 28])[0], box[2] + bp.get("centro", [28, 1, 28])[2]
                self.player(PLAYERS[1], cx, cz, mode="survival")
                c.run(f"tp {PLAYERS[1]} {cx + 0.5} {box[1] + 1} {cz + 0.5}", r"Teleported")
                c.run("heraldia arena start", r"Prepárate|Get ready|already|ya hay")

                def during():
                    c.run(f"damage @e[tag=heraldia_arena,limit=1,sort=random] 1000 minecraft:player_attack by {PLAYERS[1]}",
                          r"Applied|damage|No entity")
            else:
                self.player(PLAYERS[1], ax, az, mode="survival")
        time.sleep(warmup)
        if sc == "caravana" and self.with_it:
            m = c.run(f"execute as {PLAYERS[1]} at @s run heraldia caravan spawn raid", DEPARTS.pattern + "|" + NO_ROAD +
                      r"|already \d+ caravans|Ya hay \d+")
            if not m.group(1):
                print(f"WARNING: no caravan leaves next to {pos['camino']}: {m.string.strip()[-120:]}", flush=True)
        st = self.window(seconds, during)
        present = [PLAYERS[0]] if sc in SINGLE else list(PLAYERS)
        out = {"mspt": st, "entidades": self.entities(present)}
        if self.with_it:
            out["heraldia_arena"] = c.count("@e[tag=heraldia_arena]")
            out["heraldia_caravana"] = c.count("@e[tag=heraldia_caravana]")
            out["heraldia_habitantes"] = c.count("@e[tag=heraldia_habitante]")
            if sc == "aldea_arena":
                c.run("heraldia arena stop", r"arena|Arena|No hay|There is no")
            if sc == "caravana":
                c.run("kill @e[tag=heraldia_caravana]", r"Killed|No entity")
            if sc in ("aldea_evento", "dos_aldeas_evento"):
                out["heraldia_evento"] = c.count("@e[tag=heraldia_evento]")
                c.run("heraldia event stop all", r"Events stopped|Eventos parados")
        print(f"{'CON' if self.with_it else 'SIN'} {sc}: media {_f(st.get('media'))}, p50 {_f(st.get('p50'))}, p95 {_f(st.get('p95'))}, "
              f"p99 {_f(st.get('p99'))}, peor {_f(st.get('max'))} ms, {st['ticks']} ticks ({_f(st.get('tps'))} TPS); "
              f"entidades {out['entidades']}", flush=True)
        return out

    def start_events(self, names):
        """A wedding in each player's village (with Heraldia; without it there is nothing to start)."""
        if not self.with_it:
            return
        for n in names:
            m = self.ctx.run(f"execute as {n} at @s run heraldia event start {EVENT_KIND}", EVENT_STARTS)
            if not m.group(1):
                print(f"WARNING: no {EVENT_KIND} next to {n}: {m.group(0)}", flush=True)

    def place_arena(self):
        c = self.ctx
        if not hasattr(self, "_arena_box"):
            m = c.run("heraldia arena place", SITE.pattern + r"|Ya hay una arena|There is already")
            c.run("heraldia arena place confirm", r"Colocando la arena en|Building the arena at|Primero|First")
            m = s.wait_for(self.lines, PLACED.pattern, 600, self.seen)
            self._arena_box = tuple(int(g) for g in m.groups()[3:])
            s.wait_for(self.lines, r"arena: obra terminada", 600, self.seen)
        return self._arena_box

    def place_house(self, x, z):
        """The Herald's House placed by an operator (a simulated player) at (x, z); returns its spawn (the plaza)."""
        c = self.ctx
        if not hasattr(self, "_house"):
            self.player(PLAYERS[0], x, z)
            # `player` puts it on the surface but does not check that it stayed there, and `place here` builds at the
            # bot's block: one tick of gravity first and the house that is then measured is one block off (see
            # `server_smoke.land`). This is the one scenario whose figures depend on where the house landed.
            s.land(c, PLAYERS[0], x, z)
            c.run(f"op {PLAYERS[0]}", r"Made .* operator|already|Nothing changed")
            # its reply goes to the player's chat, which a Carpet bot's does not reach the console (see LESSONS)
            s.send(c.proc, f"execute as {PLAYERS[0]} at @s run heraldia herald place here")
            c.ticks(5)
            s.send(c.proc, f"execute as {PLAYERS[0]} run heraldia herald place confirm")
            m = s.wait_for(self.lines, HOUSE_PLACED.pattern, 900, self.seen)
            self._house = (int(m.group(1)), int(m.group(3)) + 13)
            if self.has_roads():           # its roads and huts (herald/SpawnRoads) are built right after: measured with it
                m = s.wait_for(self.lines, ROADS_BUILT.pattern + r"|herald's house roads: disabled", 900, self.seen)
                print("casa_heraldo:", m.group(0), flush=True)
            if self.has("heraldia/alrededores_casa.json"):   # and then its grounds (herald/Outskirts): not measured while built
                m = s.wait_for(self.lines, GROUNDS_BUILT.pattern + r"|herald's house grounds: disabled", 900, self.seen)
                print("casa_heraldo:", m.group(0), flush=True)
            time.sleep(5)
        return self._house

    def has_roads(self):
        """Does this .jar build the Herald's House roads (herald/SpawnRoads)? The reference .jar of a measurement may not."""
        import zipfile
        with zipfile.ZipFile(self.jar) as z:
            return "heraldia/caminos_casa.json" in z.namelist()

    def has(self, resource):
        """Does this .jar hold that resource (a feature the reference .jar of a measurement may not have)?"""
        import zipfile
        with zipfile.ZipFile(self.jar) as z:
            return resource in z.namelist()

    def find_road_point(self, pos):
        """A point of the road halfway between the two villages where a caravan really leaves (with Heraldia): tried at the
        same fractions as tools/smoke/caravans.py; the first one that works is used by every pass."""
        a, b = pos["ruta"]
        for t in (0.5, 0.44, 0.56, 0.38, 0.62):
            p = (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t))
            self.pregen("camino", p)
            self.player(PLAYERS[1], *p, mode="survival")
            time.sleep(3)
            m = self.ctx.run(f"execute as {PLAYERS[1]} at @s run heraldia caravan spawn", DEPARTS.pattern + "|" + NO_ROAD +
                             r"|already \d+ caravans|Ya hay \d+")
            self.ctx.run("kill @e[tag=heraldia_caravana]", r"Killed|No entity")
            self.nobody()
            if m.group(1):
                return list(p)
        raise SystemExit("no point of the road where a caravan leaves")


def sweep(work, jar, with_it, launcher, pos, seconds, warmup, escalation):
    """One pass: {"escenarios": {...}, "escalada": [...]} and the positions (found here if `pos` is None)."""
    label = "with" if with_it else "without"
    cost_status.phase(f"pass {label} Heraldia: starting the server")
    p = Pass(work, jar, with_it, launcher)
    try:
        if pos is None:
            cost_status.phase(f"pass {label} Heraldia: finding the positions")
            if not with_it:
                raise SystemExit("the first pass must be with Heraldia (it finds the positions)")
            pos = p.find_positions()
            pos["camino"] = p.find_road_point(pos)
            pos["arena_plano"] = arena_blueprint(jar)
        cost_status.phase(f"pass {label} Heraldia: generating the scenarios' areas")
        for name in ("aldea", "aldea_b", "campo", "aldea_vanilla", "camino", "arena", "mediana", "casa_heraldo"):
            p.pregen(name, pos[name])
        # a clean start: what Chunky generated is unloaded and saved, and the scenarios start from the saved world
        p.stop()
        keep_log(work, f"{label}-pregen")         # the restart below deletes logs/
        cost_status.phase(f"pass {label} Heraldia: restarting on the saved world")
        p = Pass(work, jar, with_it, launcher, fresh=False)
        out = {"escenarios": {}}
        for sc in SCENARIOS:
            cost_status.phase(f"pass {label} Heraldia: scenario {sc}")
            out["escenarios"][sc] = p.scenario(sc, pos, seconds, warmup)
        if escalation and with_it:
            cost_status.phase(f"pass {label} Heraldia: escalation")
            out["escalada"] = escalate(p, pos)
        return out, pos
    finally:
        cost_status.note("stopping the server")
        p.stop()
        keep_log(work, label)


OUTPUT = None        # --output: where each server's log and the passes measured so far are kept as they finish
_logs = 0
_measured = []       # every pass of this run, both rounds (measure() starts its lists afresh on a retry)


def keep_log(work, label):
    """Copies the server log to OUTPUT/logs/NN-<label>.log before the next start deletes it (a run that dies later
    keeps it)."""
    global _logs
    log = os.path.join(work, "logs", "latest.log")
    if OUTPUT and os.path.isfile(log):
        _logs += 1
        os.makedirs(os.path.join(OUTPUT, "logs"), exist_ok=True)
        shutil.copy(log, os.path.join(OUTPUT, "logs", f"{_logs:02d}-{label}.log"))


def keep_partial(with_it, r, pos):
    """Adds one measured pass to OUTPUT/coste_juego.parcial.json (rewritten after each pass, both rounds kept)."""
    _measured.append({"con": with_it, **r})
    if OUTPUT:
        with open(os.path.join(OUTPUT, "coste_juego.parcial.json"), "w", encoding="utf-8") as f:
            json.dump({"pasadas": _measured, "posiciones": pos}, f, ensure_ascii=False, indent=1)


def escalate(p, pos):
    """Villagers added around the square in ESCALATION steps; each step measured."""
    c = p.ctx
    p.nobody()
    x, z = pos["aldea"]
    p.player(PLAYERS[0], x, z)
    time.sleep(ESCALATION_WARMUP_S)
    steps, added, k = [], 0, 0
    for n in ESCALATION:
        while added < n:
            dx = int(ESCALATION_RADIUS * math.cos(k * 2.399963)) * ((k % 7) + 3) // 9
            dz = int(ESCALATION_RADIUS * math.sin(k * 2.399963)) * ((k % 7) + 3) // 9
            c.run(f"execute positioned {x + dx} 320 {z + dz} positioned over motion_blocking_no_leaves run summon minecraft:villager "
                  f"~ ~ ~ {{VillagerData:{{profession:\"minecraft:none\",level:1,type:\"minecraft:plains\"}},PersistenceRequired:1b}}",
                  r"Summoned|Unable")
            added += 1
            k += 1
        time.sleep(ESCALATION_WARMUP_S)
        st = p.window(ESCALATION_MEASURE_S)
        e = p.entities([PLAYERS[0]])
        steps.append({"añadidos": n, "mspt": st, "entidades": e})
        print(f"ESCALADA +{n}: {e['aldeanos']} aldeanos, {e['total']} entidades: media {_f(st.get('media'))}, p95 {_f(st.get('p95'))}, "
              f"p99 {_f(st.get('p99'))}, peor {_f(st.get('max'))} ms", flush=True)
    return steps


def arena_blueprint(jar):
    import zipfile
    with zipfile.ZipFile(jar) as z:
        d = json.loads(z.read("heraldia/arena.json"))
    return {k: d[k] for k in ("centro", "tamano")}


def measure(jar, work, sweeps, seconds, warmup, escalation, pos=None):
    os.makedirs(work, exist_ok=True)
    launcher = s.prepare(work, jar, s.gradle_properties())
    modrinth.install(work, ["chunky", "carpet"])
    con, sin, esc = [], [], []
    for i in range(sweeps):
        r, pos = sweep(work, jar, True, launcher, pos, seconds, warmup, escalation and i == 0)
        con.append(r["escenarios"])
        esc += r.get("escalada") or []
        keep_partial(True, r, pos)
        cost_status.phase(f"pass {i + 1} with Heraldia measured")
        r, _ = sweep(work, jar, False, launcher, pos, seconds, warmup, False)
        sin.append(r["escenarios"])
        keep_partial(False, r, pos)
        cost_status.phase(f"pass {i + 1} without Heraldia measured")
    return con, sin, esc, pos


def result_of(con, sin, esc, pos, seconds):
    import platform
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=s.ROOT, capture_output=True, text=True).stdout.strip()
    return {"semilla": SEED, "vista": VIEW, "segundos": seconds, "pasadas": len(con), "fecha": time.strftime("%Y-%m-%d"),
            "commit": commit, "posiciones": pos,
            "maquina": f"{os.cpu_count()} núcleos, {platform.system()}" + (" (CI)" if os.environ.get("GITHUB_ACTIONS") else ""),
            "con": {sc: combine([p[sc] for p in con]) for sc in SCENARIOS},
            "sin": {sc: combine([p[sc] for p in sin]) for sc in SCENARIOS},
            "escalada": escalation_summary(esc), "crudo": {"con": con, "sin": sin, "escalada": esc}}


def read_reference(route=REFERENCE):
    if not os.path.isfile(route):
        return None
    with open(route, encoding="utf-8") as f:
        return json.load(f)


def new_reference(result, previous=None):
    ref = {"limites": dict(LIMITS, **((previous or {}).get("limites") or {})), "fecha": result["fecha"],
           "commit": result["commit"], "maquina": result["maquina"], "pasadas": result["pasadas"],
           "medido": {sc: {"sin_p95": (result["sin"].get(sc) or {}).get("mspt", {}).get("p95"),
                           "con_p95": (result["con"].get(sc) or {}).get("mspt", {}).get("p95"),
                           "con_p99": (result["con"].get(sc) or {}).get("mspt", {}).get("p99")} for sc in SCENARIOS}}
    esc = result.get("escalada") or {}
    ref["margen"] = {k: esc.get(k) for k in ("ms_por_aldeano_media", "ms_por_aldeano_p95", "margen_p95_40ms", "margen_p95_50ms")}
    return _rounded(ref)


def _rounded(v):
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, dict):
        return {k: _rounded(x) for k, x in v.items()}
    return v


def write(result, comparison, output):
    os.makedirs(output, exist_ok=True)
    result = dict(result, comparacion={"ok": comparison[0], "texto": comparison[1]})
    with open(os.path.join(output, "coste_juego.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    md = markdown(result, comparison)
    with open(os.path.join(output, "coste_juego.md"), "w", encoding="utf-8") as f:
        f.write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    return md


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jar")
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-juego"))
    ap.add_argument("--output", default=os.path.join(s.ROOT, "build", "juego"))
    ap.add_argument("--sweeps", type=int, default=SWEEPS, help=f"passes with and without Heraldia (default {SWEEPS})")
    ap.add_argument("--seconds", type=int, default=MEASURE_S, help=f"measured seconds per scenario (default {MEASURE_S})")
    ap.add_argument("--warmup", type=int, default=WARMUP_S, help=f"seconds to settle before each window (default {WARMUP_S})")
    ap.add_argument("--no-escalation", action="store_true", help="without the margin steps (villagers added)")
    ap.add_argument("--scenarios", help="comma-separated: measure only these scenarios (e.g. casa_heraldo)")
    ap.add_argument("--reference", default=REFERENCE)
    ap.add_argument("--update-reference", action="store_true")
    ap.add_argument("--no-threshold", action="store_true")
    ap.add_argument("--no-retry", action="store_true")
    ap.add_argument("--from-json", help="does not measure: uses this coste_juego.json (e.g. the CI artifact)")
    a = ap.parse_args(argv)
    global OUTPUT
    if not a.from_json:
        OUTPUT = os.path.abspath(a.output)
        cost_status.start(OUTPUT, "juego")
    if a.scenarios:
        SCENARIOS[:] = [sc for sc in SCENARIOS if sc in a.scenarios.split(",")]
    ref = read_reference(a.reference)
    if a.from_json:
        with open(a.from_json, encoding="utf-8") as f:
            result = json.load(f)
    else:
        if not a.jar:
            ap.error("--jar is needed to measure")
        jar, work = os.path.abspath(a.jar), os.path.abspath(a.work)
        con, sin, esc, pos = measure(jar, work, a.sweeps, a.seconds, a.warmup, not a.no_escalation)
        result = result_of(con, sin, esc, pos, a.seconds)
        comparison = compare(result, ref)
        cost_status.phase(f"first round compared: {comparison[1]}")
        if not comparison[0] and not a.no_threshold and not a.no_retry and not a.update_reference:
            cost_status.phase("over the limit: one more round of passes")
            print("over the limit: one more round of passes", flush=True)
            c2, s2, _, _ = measure(jar, work, 1, a.seconds, a.warmup, False, pos)
            raw = result["crudo"]
            result = result_of(raw["con"] + c2, raw["sin"] + s2, raw["escalada"], pos, a.seconds)
    comparison = compare(result, ref)
    print(write(result, comparison, a.output))
    cost_status.finish(comparison[0], comparison[1])
    if a.update_reference:
        with open(a.reference, "w", encoding="utf-8") as f:
            json.dump(new_reference(result, ref), f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"reference saved to {a.reference}")
        return 0
    return 0 if comparison[0] or a.no_threshold else 1


if __name__ == "__main__":
    sys.exit(cost_status.guard(main))
