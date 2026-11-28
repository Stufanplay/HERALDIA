"""Smoke test: starts a real Fabric 26.3 dedicated server with the mod's .jar and checks loading.

Usage: python3 tools/smoke/server_smoke.py --jar build/libs/heraldia-X.jar --work build/smoke
Checks: the server starts without registry errors, the mod's 72 structures are present,
/place structure places a village with villagers, all loot tables are read, the treasure maps
respond in under 30 s (with or without a destination), the cartographer trade filter works and the functions exist.
Also the configuration (config/heraldia.json): a file with no version is migrated, an out-of-range value is corrected to the
default, valid values reach the grid and the golems, and /locate only finds villages in the allowed cells.
Unique structures that share a biome, located with /locate, end up at the configured minimum distance.
/heraldia info: the summary counts the registered structures and reflects the per-player chest option; "nearby" gives for
each unique structure a position equal to or closer than /locate (and within the radius), with its measured time.
Exit code 0 if everything passes.
"""
import argparse, json, math, os, queue, re, shutil, socket, subprocess, sys, threading, time, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENERATED_DATA = os.path.join(ROOT, "build", "generated", "heraldia", "data", "heraldia")
START_TIMEOUT_S, COMMAND_TIMEOUT_S = 600, 300
PLACE_ATTEMPTS, PLACE_RETRY_S = 30, 5
PLACE_TARGET = "heraldia:llanuras_castellana"
# /place structure requires all the chunks of the village's box to be loaded (radius <= 116): 16 x 16 chunks are forced.
FORCELOAD = "forceload add -128 -128 127 127"
LOOT_TABLES = sorted(
    "heraldia:" + os.path.relpath(os.path.join(r, f), os.path.join(GENERATED_DATA, "loot_table"))[:-5].replace(os.sep, "/")
    for r, _, fs in os.walk(os.path.join(GENERATED_DATA, "loot_table")) for f in fs if f.endswith(".json"))
UNIQUE_STRUCTURES = sorted(
    "heraldia:unicas/" + f[:-5] for f in (os.listdir(os.path.join(GENERATED_DATA, "worldgen", "structure", "unicas"))
                                          if os.path.isdir(os.path.join(GENERATED_DATA, "worldgen", "structure", "unicas")) else [])
    if f.endswith(".json"))
# A treasure map looks for its structure when the loot is generated, on the server thread: it must respond quickly.
MAP_TIMEOUT_S, EPIC_ROLLS = 30, 20
# Test configuration: no version (migration), out-of-range spacing, maximum of 12 cells, swamp family
# disabled (without it, the village closest to the test seed is heraldia:pantano_brujas) and unknown option.
# The pairs of unique structures that share a biome go on the minimum grid (1,000 blocks) so that they really
# compete for the spot, with a minimum distance different from the default one.
SEPARATION_PAIRS = [("castillo", "monasterio"), ("faro", "galeon")]
UNIQUE_MIN_DISTANCE = 1200
LOCATE_POINTS = [(0, 0), (6000, 0), (0, -6000), (-6000, 6000)]
TEST_CONFIG = {"aldeas": {"separacion_bloques": 50, "maximo": 12, "familias": {"pantano": False}}, "golems": {"limite_estandar": 7},
               "unicas": {"distancia_minima": {"bloques": UNIQUE_MIN_DISTANCE},
                          "atlantida": {"cofre_unico_por_jugador": True},
                          **{sid: {"separacion_bloques": 1000} for pair in SEPARATION_PAIRS for sid in pair}},
               # the wave arena does not generate by itself in the tests' new worlds (tools/smoke/arena.py tests it)
               "arena": {"generar_en_mundos_nuevos": False},
               # without asking GitHub for new versions: the tests do not depend on the network (update_check.py tests it)
               "update_check": {"activado": False},
               # nor the Herald's House at spawn (tools/smoke/arena.py tests it)
               "casa_heraldo": {"generar_en_mundos_nuevos": False},
               "inventada": 1}
CONFIG_LOG = [
    r"configuración migrada de la versión 0 a la 3",
    r"Heraldia: perfil estandar\r?\n",
    r"valor no válido aldeas\.separacion_bloques=50 .*se usa el valor por defecto 1500",
    r"opción desconocida inventada",
    r"rejilla aldeas: activada, cada 94 chunks \(separación mínima 62\), máximo 12 casillas, exclusión 10 chunks",
    r"aldeas: 33 estilos activados, 25 % grandes; gólems: limpieza true, límites 7/9",
    # light profile: the file does not say which profile, so the mod looks at the machine and suggests (never imposes) one
    r"Heraldia: perfil: no está elegido en config/heraldia\.json; la JVM tiene [\d.]+ GB y \d+ núcleos",
]
# With 12 cells (the 4 touching 0,0 and their 8 cross neighbours, of 94 chunks), every village ends up within 2 x 94 x 16 blocks.
LOCATE_LIMIT = 2 * 94 * 16
DOWNLOAD_ATTEMPTS = 4         # a download cut off by the network (seen with Fabric API) is repeated
# Incomplete in both directions, and knowing which matters when writing an `ok` pattern: a success text holding one
# of these words ends the wait too soon (see LESSONS), and an error text holding none of them does not end it at all --
# `data get entity` with a selector that could match more than one answers `Only one entity is allowed, but the
# provided selector allows more than one`, so the wait ran its full COMMAND_TIMEOUT_S. Measured on a dedicated server.
# `errors?\b(?!=)` and not a bare `error`: the word has to stand on its own. A bare `error` matched `error=null` inside
# the Mojang profile lookup the server logs for every Carpet fake player -- so `run` handed that log line back as the
# reply to a `player <name> spawn` that had worked -- and it also matched a test's own success line ("sin errores de
# los mapas web en el log"), which is the hazard the older lesson warns about, happening unnoticed. Measured over the
# whole battery (64,101 log lines): with the bare word, 13 lines matched it and none of the others, all of them that
# same Mojang noise; with this pattern, 0. It still has to match `Registry loading errors`, a real 26.3 failure, which
# is why the word is not simply removed and why `error:` would have been wrong.
ERROR_PATTERN = r"Unknown|Incorrect|Failed|Invalid|errors?\b(?!=)|not loaded"
# Real failure replies of the dedicated server, verbatim, keyed by the fragment a caller greps a reply for. The ONE list
# the two static checks of the harness judge `ok` patterns against -- tools/gen/tests/test_run_ok_patterns.py (a reply
# that is read must be accepted) and test_discarded_ok_patterns.py (a reply that is thrown away must not be) -- so a new
# real failure goes in here and nowhere else. Read on a 26.3 server: "Unknown or incomplete command. See below for
# error" (`notacommand`), "Incorrect argument for command" (`gamerule no_such_rule true`), "Invalid NBT path element"
# (`data get entity @e[limit=1] Foo..Bar`), "That position is not loaded", "No entity was found" (`tp NoSuchPlayer ...`).
FAILURE_REPLIES = {
    "not loaded": "That position is not loaded",
    "no está cargada": "esa posición no está cargada",
    "failed": "Test failed",
    "Failed": "Failed to place",
    "No items": "No items were found",
    "No entity": "No entity was found",
    "Unknown": "Unknown or incomplete command. See below for error",
    "Incorrect": "Incorrect argument for command",
    "Invalid": "Invalid NBT path element",
}
# /heraldia info nearby: (point, radius); the last one, with the maximum radius, measures the worst case. The search runs off the
# server thread; on it only the confirmation (INFO_MAIN_MS at most). INFO_MAX_MS is the cap for the full response.
INFO_POINTS = [((0, 0), None), ((6000, 0), 6000), ((0, -6000), 10000)]
INFO_DEFAULT_RADIUS, INFO_MAX_MS, INFO_MAIN_MS = 3000, 20000, 20
INFO_LINE = re.compile(r" - .+? \((heraldia:[^)]+)\): (\d+) (?:blocks|bloques) .*?\[(-?\d+), ~, (-?\d+)\]")


def gradle_properties():
    props = {}
    with open(os.path.join(ROOT, "gradle.properties"), encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
    return props


def valid_jar(path):
    """Is it a whole .jar (zip)? A download cut off by the network lacks the central directory at the end."""
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def download(url, dest, attempts=DOWNLOAD_ATTEMPTS):
    """Downloads `url` to `dest` if it is not already there (whole). A cut-off download (fewer bytes than Content-Length or a .jar
    without its end) is repeated up to `attempts` times instead of staying in the cache and breaking the following tests."""
    if os.path.isfile(dest) and (not dest.endswith(".jar") or valid_jar(dest)):
        return
    for i in range(1, attempts + 1):
        print("descargando", url, f"(intento {i})" if i > 1 else "")
        try:
            with urllib.request.urlopen(url) as r, open(dest + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
                expected = r.headers.get("Content-Length")
            ok = (expected is None or os.path.getsize(dest + ".part") == int(expected)) and \
                (not dest.endswith(".jar") or valid_jar(dest + ".part"))
        except OSError as e:
            print("descarga fallida:", e)
            ok = False
        if ok:
            os.replace(dest + ".part", dest)
            return
        time.sleep(2 * i)
    raise SystemExit(f"could not download {url} whole in {attempts} attempts")


def latest_installer():
    with urllib.request.urlopen("https://meta.fabricmc.net/v2/versions/installer") as r:
        return next(v["version"] for v in json.load(r) if v["stable"])


_given_ports = set()


def ephemeral_range():
    """The kernel's ephemeral port range (Linux: /proc/sys/net/ipv4/ip_local_port_range; 32768-60999 by default)."""
    try:
        with open("/proc/sys/net/ipv4/ip_local_port_range") as f:
            lo, hi = (int(x) for x in f.read().split())
        return lo, hi
    except (OSError, ValueError):
        return 32768, 60999


def free_port(low=20000):
    """A TCP port that is free now, BELOW the kernel's ephemeral range, and not one this process has handed out before.
    The test binds it later (the server, after starting; runtime_cost.py up to four times over ~47 min), so there is
    always a gap; a port from bind(("", 0)) is ephemeral, the range every outgoing connection of the machine draws its
    local port from (downloads, the server's own HTTPS at start, JMX clients, the runner's agent), and one of them can be
    holding it when the server binds: "FAILED TO BIND TO PORT ... Address already in use", juego dead in 18 s in CI run
    44965032309. Below the range the kernel never assigns a port on its own, so only another explicit bind can take it."""
    import random
    lo, _ = ephemeral_range()
    if lo - 1 > low:
        for _ in range(500):
            p = random.randrange(low, lo)
            if p in _given_ports:
                continue
            with socket.socket() as so:
                try:
                    so.bind(("", p))
                except OSError:
                    continue
            _given_ports.add(p)
            return p
    with socket.socket() as so:          # no room below the ephemeral range: the old way
        so.bind(("", 0))
        p = so.getsockname()[1]
    _given_ports.add(p)
    return p


def prepare(work, jar, p):
    mods = os.path.join(work, "mods")
    shutil.rmtree(mods, ignore_errors=True)
    for d in ("world", "logs"):
        shutil.rmtree(os.path.join(work, d), ignore_errors=True)
    os.makedirs(mods)
    mc, loader, fapi = p["minecraft_version"], p["loader_version"], p["fabric_api_version"]
    launcher = os.path.join(work, f"fabric-server-{mc}-{loader}.jar")
    download(f"https://meta.fabricmc.net/v2/versions/loader/{mc}/{loader}/{latest_installer()}/server/jar", launcher)
    cache = os.path.join(work, f"fabric-api-{fapi}.jar")
    download(f"https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/{fapi}/fabric-api-{fapi}.jar", cache)
    shutil.copy(cache, mods)
    shutil.copy(jar, mods)
    with open(os.path.join(work, "eula.txt"), "w") as f:
        f.write("eula=true\n")
    os.makedirs(os.path.join(work, "config"), exist_ok=True)
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(TEST_CONFIG, f)
    with open(os.path.join(work, "server.properties"), "w") as f:
        # Free port (not the fixed 25565): this way several tests can be launched at once on the same machine. Without a tick
        # watchdog (max-tick-time=-1): on a very loaded machine, forcing 256 chunks can take a tick longer than 60 s and
        # the watchdog shut the server down ("A single server tick took 60 s"); the test already has its own limits.
        f.write("online-mode=false\nview-distance=4\nsimulation-distance=4\nspawn-protection=0\npause-when-empty-seconds=0\n"
                f"level-seed=heraldia\nserver-port={free_port()}\nmax-tick-time=-1\n")
    return launcher


def reader(proc, lines):
    for line in proc.stdout:
        sys.stdout.write(line)
        lines.put(line)
    lines.put(None)


def wait_for(lines, pattern, timeout, seen):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            line = lines.get(timeout=max(0.1, end - time.monotonic()))
        except queue.Empty:
            break
        if line is None:
            raise SystemExit("the server shut down early")
        seen.append(line)
        m = re.search(pattern, line)
        if m:
            return m
    raise SystemExit(f"tiempo agotado esperando: {pattern}")


def send(proc, cmd):
    proc.stdin.write(cmd + "\n")
    proc.stdin.flush()


def pending(lines, seen):
    """Passes to `seen` the lines already in the queue without waiting for any (replies from more than one earlier command)."""
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            return
        if line is None:
            lines.put(None)
            return
        seen.append(line)


_LOGGED = re.compile(r"^\[[^\]]*\] \[[^\]]*/(?:WARN|ERROR|FATAL)\]: ")


def run(proc, lines, seen, cmd, ok):
    """Sends a command and returns its success reply, the first line that matches `ok`. First discards (to `seen`)
    whatever was left in the queue: the line from more than one earlier command (e.g. two "Test passed") is not taken
    as this one's reply.

    **It fails by default**: the wait is `ok` OR `ERROR_PATTERN` (so a failure ends it promptly instead of running out
    COMMAND_TIMEOUT_S), and a reply that matches `ERROR_PATTERN` and not `ok` raises SystemExit naming the command and
    the reply. It used to hand that reply back and raise nothing, so a caller that did not look at it accepted the
    failure and carried on as if the command had worked (docs/LESSONS.md). A caller that has to tell a failure apart
    -- a retry on `not loaded`, a "No entity" that means "none" -- lists it in its own `ok` and reads the reply;
    tools/gen/tests/test_run_ok_patterns.py checks that every reply inspected for a failure accepts it. When a red
    shows up here in a test nobody changed, the fix is to make that call robust, never to widen a pattern until the
    failure matches it."""
    pending(lines, seen)
    send(proc, cmd)
    end = time.monotonic() + COMMAND_TIMEOUT_S
    while True:
        m = wait_for(lines, f"{ok}|{ERROR_PATTERN}", max(0.1, end - time.monotonic()), seen)
        # The mod's own log lines ("[...]: Heraldia: ...") are no command's error reply: "Heraldia: village look: ... (some
        # chunks not loaded yet)" (welcome/Welcome), logged while /time query gametime was awaited, was taken as its reply
        # and caravans.py died with a TypeError (CI, Nov 2026). Such a line still counts if `ok` itself matches it.
        if "]: Heraldia: " in m.string and not re.search(ok, m.string):
            continue
        # Nor is a line the server logs at WARN or ERROR level: a command's reply, failure included, reaches the
        # console as INFO. Carpet's fake player looks its profile up on api.mojang.com from another thread, and when
        # that is refused (HTTP 429 in CI) it logs "[Server thread/ERROR]: Got an error with a html body ..." while
        # the spawn is being awaited -- the spawn works all the same, on a local profile, and the switch stopped
        # admin.py on that line (#155). Measured before narrowing: in ~127,000 lines of local runs, no WARN or ERROR
        # line matched ERROR_PATTERN at all, and all 92 that matched it were INFO replies. Counts if `ok` matches it.
        if _LOGGED.search(m.string) and not re.search(ok, m.string):
            continue
        if not re.search(ok, m.string):
            raise SystemExit(f"{cmd}: the server replied {m.string.strip()!r}")
        return m


def must(proc, lines, seen, cmd, ok):
    """The same as `run`, which now fails by default; kept for the callers that say so explicitly.

    A pattern passed here (or to `run`) must not match the failure the caller wants refused: with the failure's words
    in `ok`, the error reply *is* the accepted reply and there is nothing left to tell apart."""
    return run(proc, lines, seen, cmd, ok)


# Carpet's simulated players are what 31 waits of the server tests spawn and kill. Whether Carpet is there is asked once,
# by the command those waits use, not by the mod list: "- carpet <version>" under "Loading N mods" says the jar was
# loaded, while this says `/player` exists and answers -- which is also false when Carpet is loaded with the command
# turned off in its own settings. Read on a 26.3 server with and without Carpet, same .jar: a `player` command on a name
# that is not online answers "Can only manipulate existing players" with Carpet, and "Unknown or incomplete command. See
# below for error" without it; it spawns, kills and moves nothing.
CARPET_PROBE = "player heraldia_no_such_bot kill"
CARPET_HERE = "Can only manipulate existing players"
CARPET_ABSENT = "Unknown or incomplete command"


def require_carpet(ctx):
    """Stops the test, saying where Carpet is missing, unless this server knows Carpet's `/player` command.

    Called just before each `player ... spawn`; it sends its probe once per server (it remembers on `ctx`), so a test
    that spawns in a loop or after a restart pays one command per start. Both replies are listed so the wait ends at
    once on either, and only Carpet's is accepted: the three-way wait of docs/LESSONS.md. Before it, 31 waits listed
    `Unknown|Incorrect` in their own `ok` so that a missing Carpet passed for a spawn that worked."""
    if getattr(ctx, "_carpet_checked", False):
        return
    m = ctx.run(CARPET_PROBE, f"{CARPET_HERE}|{CARPET_ABSENT}")
    if CARPET_HERE not in m.string:
        test = os.path.basename(sys.argv[0]) or "this test"
        raise SystemExit(f"{test}: Carpet is not loaded on this server -- `player` is not a command here (it answered "
                         f"{m.string.strip()!r}). Copy Carpet into the mods/ folder of this test's --work before the "
                         f"server starts (trophies.CARPET, fetched with terralith_biomes.fetch), and check that Carpet's "
                         f"settings do not turn `/player` off.")
    ctx._carpet_checked = True


# Condition waits of the server tests: the check is repeated for up to UNTIL_S seconds (generous: CI is
# slow and writes "Can't keep up!") and passes as soon as it is met. The "wait for time to pass" waits (a circuit
# must NOT react, a trap has already fired) are counted in game ticks with /time query gametime, not in seconds:
# with the server lagging, 2 s of clock can be very few ticks.
UNTIL_S, POLL_S, TICK_TIMEOUT_S = 120, 1, 300
_TEST = r"Test passed(?:\. Count: (\d+))?|Test failed"
_NUM = r"(-?[\d.]+(?:E-?\d+)?)d"
_POS = rf"has the following entity data: \[{_NUM}, {_NUM}, {_NUM}\]|No entity was found"


def _top_tokens(cmd):
    """The words of a command outside brackets, braces and quotes (those of a selector or an NBT do not count)."""
    toks, cur, depth, quote = [], "", 0, None
    for ch in cmd:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{(":
            depth += 1
        elif ch in "]})":
            depth -= 1
        if ch == " " and depth == 0:
            if cur:
                toks.append(cur)
            cur = ""
        else:
            cur += ch
    return toks + ([cur] if cur else [])


def silent_reason(cmd):
    """Why an `execute ...` check might not respond with anything in the console (and hang the test until
    COMMAND_TIMEOUT_S), or None if it always responds "Test passed|Test failed". See docs/LESSONS.md: `as`/`at`
    (and `positioned as`, `facing entity`...) fork the command and the "Test failed" of one branch does not arrive; with nobody in the
    selector there is not even a branch; in an `if A if B` chain the intermediate condition that fails does not respond."""
    toks = _top_tokens(cmd)
    if not toks or toks[0] != "execute":
        return None
    if "run" in toks:
        return "lleva «run»: la respuesta es la de la orden de después"
    if {"as", "at", "on"} & set(toks[1:]) or any(a == "facing" and b == "entity" for a, b in zip(toks, toks[1:])):
        return "bifurca por entidades (as/at/on/facing entity): si no hay nadie o falla en una rama, no responde"
    if sum(t in ("if", "unless") for t in toks) != 1:
        return "más de una condición: si falla una intermedia, no responde"
    return None


class Context:
    """What a unique structure module needs for its own checks (tools/gen/uniques/<id>/smoke.py),
    and the common utilities of the server tests: checking, waiting on a condition, counting ticks, reading `Pos`."""

    def __init__(self, proc, lines, seen):
        self.proc, self.lines, self.seen = proc, lines, seen

    def run(self, cmd, ok):
        return run(self.proc, self.lines, self.seen, cmd, ok)

    def must(self, cmd, ok):
        """`run`, which fails if the reply is not the success reply (see `must`)."""
        return must(self.proc, self.lines, self.seen, cmd, ok)

    def log(self):
        return "".join(self.seen)

    def test(self, cmd):
        """True/False from a single-condition check without forking (it always responds; otherwise, ValueError)."""
        why = silent_reason(cmd)
        if why:
            raise ValueError(f"check that may not respond ({why}): {cmd}")
        return self.run(cmd, _TEST).group(0).startswith("Test passed")

    def count(self, sel):
        """How many entities the selector gives (0 if none)."""
        m = self.run(f"execute if entity {sel}", _TEST)
        return int(m.group(1) or 0) if m.group(0).startswith("Test passed") else 0

    def block(self, pos, state):
        """Is there `state` at the coordinates `pos` ("x y z" or tuple)?"""
        p = pos if isinstance(pos, str) else " ".join(str(c) for c in pos)
        return self.test(f"execute if block {p} {state}")

    def until(self, cmd, want=True, timeout=UNTIL_S):
        """Repeats the check until it gives `want` (True) or `timeout` seconds pass (False)."""
        end = time.monotonic() + timeout
        while True:
            if self.test(cmd) == want:
                return True
            if time.monotonic() > end:
                return False
            time.sleep(POLL_S)

    def gametime(self):
        return int(self.run("time query gametime", r"[Tt]ime is (\d+)").group(1))

    def ticks(self, n):
        """Waits until the server has run `n` more ticks (however long that takes on the clock, up to TICK_TIMEOUT_S)."""
        end, target = time.monotonic() + TICK_TIMEOUT_S, self.gametime() + n
        time.sleep(n / 20)
        while self.gametime() < target:
            if time.monotonic() > end:
                raise SystemExit(f"the server does not advance {n} ticks in {TICK_TIMEOUT_S} s")
            time.sleep(0.25)

    def pos(self, sel):
        """(x, y, z) of the first entity of the selector, with `data get entity ... Pos`; None if there is none."""
        one = sel if "limit=" in sel else (sel[:-1] + ",limit=1]" if sel.endswith("]") else sel + "[limit=1]")
        m = self.run(f"data get entity {one} Pos", _POS)
        return tuple(float(v) for v in m.groups()) if m.group(1) else None

    def wait_entity(self, sel, timeout=UNTIL_S):
        """Waits until the selector gives some entity (those of a template appear a few seconds after the
        blocks). If it does not arrive, prints a diagnostic (how many of the same type or tag there are in the whole world and where)."""
        if self.until(f"execute if entity {sel}", timeout=timeout):
            return True
        print(f"DIAG: no entity {sel} in {timeout} s; {self.diagnose(sel)}")
        return False

    def diagnose(self, sel):
        """Text with the entities of the same type/tag as `sel`, without its zone limits, and their position."""
        inner = sel[sel.index("[") + 1:-1] if "[" in sel else ""
        keep = [f for f in _top_tokens(inner.replace(",", " ")) if f.split("=")[0] in ("type", "tag")]
        wide = f"@e[{','.join(keep)}]"
        return f"{wide}: {self.count(wide)} en el mundo, la primera en {self.pos(wide)}"


# Standing a player where a test then builds at it.
# Waiting for the state to be ready is not the same as checking that it is the state you asked for: `OnGround` turns
# true wherever the entity happens to land, so a bot that drops a block first is "settled" at the wrong place and what
# is built at it comes out one block off (it cost a confound in #137: the town at ground 90 instead of 91, once in nine
# runs). Hence both halves below -- `OnGround`, which is a property of the entity, and the position, which is a
# property of the world -- and the aimed spot taken from the teleport's own reply, which the game writes inside the
# teleport before any tick can move anything, instead of a second read that the fall can get in front of.
# Measured on a dedicated server, 26.3: a teleport answers `Teleported <Bot> to 0.500000, 63.000000, 48.500000`
# (integer x and z in a position argument are centred on the block, y is not) and `That position is not loaded` while
# the column is still loading. Do NOT read the aimed spot from a marker or armor stand summoned there instead: in a
# chunk that is not loaded yet the summon answers `Summoned new Marker` and the entity then does not exist at all
# (`@e` finds nothing, `data get` says `No entity was found`) -- which is how this was found.
SURFACE = "positioned over motion_blocking_no_leaves"    # the heightmap a test stands something on
SETTLE_S = 30
_FLAG = r"has the following entity data: (\d)b|No entity was found"
_TELEPORTED = r"Teleported .+? to (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)|No entity|not loaded"


def _one(who):
    """`who` as a selector for exactly **one** entity.

    Two traps, both measured on a dedicated server: a bare player name cannot take the `[limit=1]` that `Context.pos`
    appends (`data get entity rep[limit=1]` never answers), and `data get entity` refuses at parse time a selector that
    could match more than one -- with `Only one entity is allowed, but the provided selector allows more than one`,
    which holds none of `ERROR_PATTERN`'s words, so the test waits the full `COMMAND_TIMEOUT_S` for it."""
    if not who.startswith("@"):
        return f"@a[name={who},limit=1]"
    if "limit=" in who:
        return who
    return who[:-1] + ",limit=1]" if who.endswith("]") else who + "[limit=1]"


def on_ground(ctx, who):
    """Is `who` resting on a block? The game's own answer (entity NBT `OnGround`). A whole-number Y is no proof of it
    and a fractional one is no proof against: a player rests at y 69.9375 on a path block, measured on a server."""
    return ctx.run(f"data get entity {_one(who)} OnGround", _FLAG).group(1) == "1"


def _resting(at, want):
    """Is `at` (a read `Pos`) standing where the teleport aimed, `want` (the destination it reported)?

    The aimed y is a **feet level**: a teleport leaves the entity with its feet there. So the column has to be the same
    one and the feet have to be inside that single block of height. Not `floor(y)` equal: a block shorter than a full
    cube holds the feet just below the level (measured on a dedicated server, a player resting on a path block sits at
    y 69.9375, floor 69, aimed 70), and that is resting, not falling. A whole block down -- the fault this guards
    against -- fails either way."""
    return (at is not None and (math.floor(at[0]), math.floor(at[2])) == (math.floor(want[0]), math.floor(want[2]))
            and want[1] - 1 < at[1] <= want[1])


def _settle(ctx, who, tp, where, timeout):
    """Repeats the teleport `tp` until `who` is resting where it reported aiming. Returns that spot's block."""
    end, want, at, m = time.monotonic() + timeout, None, None, None
    while True:
        m = ctx.run(tp, _TELEPORTED)
        if m.group(1):                      # it did teleport, and the reply says where
            want = tuple(float(v) for v in m.groups())
            ctx.ticks(2)                    # let gravity have its say before believing the answer
            at = ctx.pos(_one(who))
            if _resting(at, want) and on_ground(ctx, who):
                return tuple(math.floor(v) for v in want)
        if time.monotonic() > end:
            raise SystemExit(f"the player did not settle at {where}: {who} is at {at}, aimed at {want}, last reply "
                             f"{m.string.strip()[-120:]!r}")
        time.sleep(POLL_S)


def land(ctx, who, x, z, timeout=SETTLE_S):
    """Puts `who` on the **surface** of the column (x, z) and does not return until it is resting there. Returns that
    spot's block as (x, y, z); also waits out a column that is not loaded yet.

    For a test that builds at wherever the ground happens to be. Where the test picked the height itself, use `stand`.
    Raises SystemExit naming the spot it never settled at."""
    return _settle(ctx, who, f"execute positioned {x} 320 {z} {SURFACE} run tp {who} ~ ~ ~",
                   f"the surface of ({x}, {z})", timeout)


def stand(ctx, who, x, y, z, timeout=SETTLE_S):
    """Puts `who` on the block (x, y, z) that the **caller** chose, and does not return until it is resting there.
    Returns (x, y, z).

    For a test that picked the height for its own reasons -- `herald_steep.py` hovers its bot 21 blocks over the
    natural ground, because the town levels its own footprint -- so the surface is not what it is aiming for. Something
    has to hold the entity up there, or it falls and this fails. Raises SystemExit naming the block."""
    return _settle(ctx, who, f"tp {who} {x} {y} {z}", f"({x}, {y}, {z})", timeout)


def unique_hook(sid):
    """Function comprobar(ctx) -> list of failures of the unicas.<id>.humo module, if it exists."""
    import importlib, importlib.util
    gen = os.path.join(ROOT, "tools", "gen")
    if gen not in sys.path:
        sys.path.insert(0, gen)
    import uniques
    name = f"uniques.{uniques.module_name(sid.split('/')[-1])}.smoke"
    try:
        if importlib.util.find_spec(name) is None:
            return None
    except ModuleNotFoundError:
        return None
    return importlib.import_module(name).check


def locate(ctx, sid, x, z):
    """(x, z, seconds) of the structure sid closest to x, z, or None if /locate does not find it."""
    t0 = time.monotonic()
    m = ctx.run(f"execute positioned {x} 64 {z} run locate structure heraldia:unicas/{sid}",
                r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
    return (int(m.group(1)), int(m.group(2)), time.monotonic() - t0) if m.group(1) else None


def check_separation(ctx):
    """The pairs that share a biome, located from several points and one from the other, end up at >= N blocks."""
    failures, found, took = [], {sid: set() for pair in SEPARATION_PAIRS for sid in pair}, []
    for a, b in SEPARATION_PAIRS:
        measured = 0
        for first, second in ((a, b), (b, a)):
            for x, z in LOCATE_POINTS:
                p = locate(ctx, first, x, z)
                if not p:
                    continue
                q = locate(ctx, second, p[0], p[1])
                took += [p[2]] + ([q[2]] if q else [])
                found[first].add(p[:2])
                if q:
                    found[second].add(q[:2])
                    measured += 1
        pairs = [(p, q) for p in found[a] for q in found[b]]
        close = [(p, q) for p, q in pairs if math.dist(p, q) < UNIQUE_MIN_DISTANCE]
        if measured == 0:
            failures.append(f"/locate did not find any {a}/{b} pair to measure the separation")
        for p, q in close:
            failures.append(f"{a} at {p} and {b} at {q} {math.dist(p, q):.0f} blocks apart (< {UNIQUE_MIN_DISTANCE})")
        print(f"separation {a}/{b}: {len(pairs)} pairs measured, minimum "
              f"{min((math.dist(p, q) for p, q in pairs), default=0):.0f} bloques")
    if took:
        print(f"/locate of unique structures: {len(took)} searches, mean {sum(took) / len(took):.2f} s, max {max(took):.2f} s")
    if not re.search(rf"distancia mínima entre estructuras únicas: activada, {UNIQUE_MIN_DISTANCE} bloques", ctx.log()):
        failures.append("the log is missing the configured minimum distance between unique structures")
    return failures


def drain(ctx, wait=1.5):
    """The lines the server has written in the next few seconds (those of a command that responds with several)."""
    time.sleep(wait)
    out = []
    while True:
        try:
            line = ctx.lines.get_nowait()
        except queue.Empty:
            return out
        if line is None:
            raise SystemExit("the server shut down early")
        ctx.seen.append(line)
        out.append(line)


def check_info(ctx, expected):
    """/heraldia info: summary (registered structures, per-player chest option) and "nearby" compared with /locate."""
    fails = []
    m = ctx.run("heraldia info", r"Registered structures: (\d+)|Estructuras registradas: (\d+)")
    n = m.group(1) or m.group(2) if m.lastindex else None
    if n is None or int(n) != expected:
        fails.append(f"/heraldia info: estructuras registradas {n}, esperadas {expected}: {m.string.strip()}")
    text = "".join(ctx.seen[-40:])
    if not re.search(r"Per-player Atlantis premium chest: yes|Cofre premium de la Atlántida por jugador: sí", text):
        fails.append("/heraldia info no refleja unicas.atlantida.cofre_unico_por_jugador = true")
    for (x, z), radius in INFO_POINTS:
        r = radius or INFO_DEFAULT_RADIUS
        cmd = f"execute positioned {x} 64 {z} run heraldia info nearby" + (f" {radius}" if radius else "")
        m = ctx.run(cmd, r"info nearby \d+ en [^:]+: \d+ estructuras en (\d+) ms \((\d+) ms en el hilo del servidor\)")
        if not m.lastindex:
            fails.append(f"{cmd}: {m.string.strip()}")
            continue
        ms, main_ms = int(m.group(1)), int(m.group(2))
        found = {g[0]: (int(g[1]), int(g[2]), int(g[3])) for g in INFO_LINE.findall("".join(drain(ctx)))}
        print(f"/heraldia info nearby {r} from {x}, {z}: {len(found)} structures in {ms} ms ({main_ms} ms on the server thread)")
        if ms > INFO_MAX_MS or main_ms > INFO_MAIN_MS:
            fails.append(f"{cmd}: {ms} ms, {main_ms} ms on the server thread (maximum {INFO_MAX_MS} and {INFO_MAIN_MS})")
        if any(d > r for d, _, _ in found.values()):
            fails.append(f"{cmd}: gives structures outside the radius: {found}")
        for sid in sorted({sid for pair in SEPARATION_PAIRS for sid in pair} | {"atlantida"}):
            p = locate(ctx, sid, x, z)
            if not p or math.dist(p[:2], (x, z)) > r:
                continue
            ours = found.get(f"heraldia:unicas/{sid}")
            if ours is None or ours[0] > math.dist(p[:2], (x, z)) + 1:
                fails.append(f"{cmd}: /locate gives {sid} at {p[:2]}, but info nearby gives {ours}")
        if (x, z) == (0, 0) and "heraldia:aldeas" not in found and not any(":unicas/" not in k and ":medianas/" not in k and ":minas/" not in k for k in found):
            fails.append(f"{cmd}: gives no village near 0,0 (12 allowed cells): {found}")
    m = ctx.run("execute positioned 5000 64 5000 run heraldia info here", r"not loaded|no está cargada")
    if m.group(0) not in ("not loaded", "no está cargada"):
        fails.append(f"/heraldia info here in an unloaded chunk: {m.string.strip()}")
    return fails


def guardian_placed(ctx, sid):
    """The unique structure's guardian keeps in the world the heraldia_guardian.<id> tag by which its advancement recognizes it
    (advancements.py). A template's entities take a few seconds longer than the blocks: it retries."""
    return ctx.wait_entity(f"@e[tag=heraldia_guardian.{sid.split('/')[-1]}]")


def guardian_trophy(ctx, sid):
    """The placed guardian keeps its DeathLootTable (the trophy one, heraldia:guardianes/<id>/<mob>) and, killed without a
    player (/loot ... kill from the console), does not drop the trophy (killed_by_player condition). That it does drop it when
    a player kills it is tested by tools/smoke/trophies.py with a simulated player."""
    sid = sid.split("/")[-1]
    g = f"@e[tag=heraldia_guardian.{sid},limit=1]"
    m = ctx.run(f"data get entity {g} DeathLootTable", r'has the following entity data: "([^"]+)"|No entity')
    if not (m.group(1) or "").startswith(f"heraldia:guardianes/{sid}/"):
        return [f"el guardián no tiene la tabla del trofeo: {m.string.strip()}"]
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    # Without "execute at <guardian>": if the guardian were gone, the command would not respond at all (hung for 5 min). Its
    # position is read and the loot is dropped there.
    p = ctx.pos(g)
    if p is None:
        return [f"el guardián ha desaparecido antes de soltar su botín; {ctx.diagnose(g)}"]
    m = ctx.run(f"loot spawn {p[0]:.2f} {p[1] + 1:.2f} {p[2]:.2f} kill {g}", r"Dropped \d+|No items|No entity was found")
    if not m.group(0).startswith(("Dropped", "No items")):
        return [f"/loot kill del guardián falló: {m.string.strip()}"]
    m = ctx.run(f'execute if entity @e[type=minecraft:item,nbt={{Item:{{components:{{"minecraft:custom_data":{{heraldia_trofeo:"{sid}"}}}}}}}}]',
                r"Test passed|Test failed")
    return [] if "failed" in m.group(0) else ["suelta el trofeo sin que lo mate un jugador"]


def snbt(v):
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{snbt(x)}" for k, x in v.items()) + "}"
    return json.dumps(v) if isinstance(v, str) else str(v)


def check_keys(ctx):
    """/heraldia key: registered (asks for players and rejects an invented key) and each key table gives an item that
    satisfies the lock of its chests. Without a client there are no players: delivery to the inventory is not tested here."""
    fails = []
    with open(os.path.join(ROOT, "build", "generated", "heraldia", "heraldia", "llaves.json"), encoding="utf-8") as f:
        keys = json.load(f)["llaves"]
    if not keys:
        return ["heraldia/llaves.json sin llaves"]
    m = ctx.run("heraldia key @a inventada", r"No hay ninguna llave|There is no key")   # the server translates (en_us)
    if not m.group(0).startswith(("No hay", "There is no")):
        fails.append(f"/heraldia key does not reject an invented key: {m.string.strip()}")
    m = ctx.run("heraldia key @a all", r"No player was found")
    if not m.group(0).startswith("No player"):
        fails.append(f"/heraldia key @a all without players: {m.string.strip()}")
    for kid, d in keys.items():
        lock = d["cerradura"]
        pred = lock["items"] + "[" + ",".join(f"{k}~{snbt(v)}" for k, v in lock["predicates"].items()) + "]"
        ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
        m = ctx.run(f"loot spawn 0 200 0 loot {d['tabla']}", r"Dropped \d+")
        if not m.group(0).startswith("Dropped 1"):
            fails.append(f"llave {kid}: {m.string.strip()}")
            continue
        m = ctx.run(f"execute positioned 0 200 0 if items entity @e[type=minecraft:item,distance=..4] contents {pred}",
                    r"Test passed|Test failed")
        if "passed" not in m.group(0):
            fails.append(f"key {kid}: the item does not open its lock ({pred}): {m.string.strip()}")
    ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
    print(f"keys: {len(keys)} checked against their lock")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(ROOT, "build", "smoke"))
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    expected = sum(f.endswith(".json") for _, _, fs in os.walk(os.path.join(GENERATED_DATA, "worldgen", "structure")) for f in fs)
    expected_advancements = sum(f.endswith(".json") for _, _, fs in os.walk(os.path.join(GENERATED_DATA, "advancement")) for f in fs)
    launcher = prepare(args.work, os.path.abspath(args.jar), gradle_properties())

    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=args.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=reader, args=(proc, lines), daemon=True).start()
    failures, villagers, located, maps_found = [], 0, "/locate sin comprobar", []
    try:
        # The mod writes it on SERVER_STARTED, after "Done": the server already accepts commands.
        m = wait_for(lines, r"Heraldia: (\d+) estructuras registradas", START_TIMEOUT_S, seen)
        if int(m.group(1)) != expected:
            failures.append(f"estructuras registradas {m.group(1)}, esperadas {expected}")
        # Advancements (advancements.py): in 26.3 they are a registry; all the generated ones are loaded and without validation warnings.
        m = wait_for(lines, r"Heraldia: (\d+) logros cargados", COMMAND_TIMEOUT_S, seen)
        if int(m.group(1)) != expected_advancements:
            failures.append(f"logros cargados {m.group(1)}, esperados {expected_advancements}")
        with open(os.path.join(args.work, "config", "heraldia.json"), encoding="utf-8") as f:
            written = json.load(f)
        if (written.get("version"), written["aldeas"]["separacion_bloques"], written["aldeas"]["maximo"]) != (3, 1500, 12):
            failures.append(f"config/heraldia.json reescrito mal: {written.get('version')} {written['aldeas']}")
        if "inventada" in written or "es_es" not in written.get("_ayuda", {}):
            failures.append("config/heraldia.json without help or with the unknown option")
        # profiles (T36): the default one, without the options the profile provides (nobody set them by hand)
        if written.get("perfil") != "estandar" or "nivel" in written.get("dificultad", {}) or \
                "activado" in written["aldeas"].get("caminos", {}) or written.get("_perfil", {}).get("efectivo") != "estandar":
            failures.append(f"config/heraldia.json: perfil mal escrito: {written.get('perfil')} {written.get('dificultad')} "
                            f"{written.get('_perfil', {}).get('efectivo')}")
        if written["unicas"]["atlantida"].get("cofre_unico_por_jugador") is not True or not all(
                "unicas.atlantida.cofre_unico_por_jugador" in written["_ayuda"][lang] for lang in ("es_es", "en_us")):
            failures.append("config/heraldia.json: unicas.atlantida.cofre_unico_por_jugador not kept or without help")
        m = run(proc, lines, seen, "scoreboard players get #limite_estandar heraldia_cfg", r"has (\d+)")
        log_so_far = "".join(seen)   # the golem line is written on SERVER_STARTED, already before this reply
        for pat in CONFIG_LOG:
            if not re.search(pat, log_so_far):
                failures.append(f"the configuration log is missing: {pat}")
        if not m.group(0).startswith("has") or m.group(1) != "7":
            failures.append(f"#limite_estandar heraldia_cfg is not 7: {m.string.strip()}")
        m = run(proc, lines, seen, "execute positioned 20000 64 20000 run locate structure #heraldia:aldeas",
                r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
        if m.group(1) is None:
            failures.append(f"/locate did not find villages in the 12 allowed cells: {m.string.strip()}")
        elif "pantano" in m.group(0):
            failures.append(f"/locate found a village of a disabled family: {m.string.strip()}")
        elif max(abs(int(m.group(1))), abs(int(m.group(2)))) > LOCATE_LIMIT:
            failures.append(f"/locate found a village outside the allowed cells: {m.string.strip()}")
        else:
            located = f"/locate en {m.group(1)}, {m.group(2)}"
        failures += check_separation(Context(proc, lines, seen))
        failures += check_info(Context(proc, lines, seen), expected)
        send(proc, FORCELOAD)
        wait_for(lines, r"Marked|Added|chunks? .*force", COMMAND_TIMEOUT_S, seen)
        for _ in range(PLACE_ATTEMPTS):
            m = run(proc, lines, seen, f"place structure {PLACE_TARGET} 0 ~ 0", r"Generated structure|not loaded(?! yet)")
            if "not loaded" not in m.group(0):
                break
            time.sleep(PLACE_RETRY_S)   # the forced chunks load in the following ticks
        if "Generated structure" not in m.group(0):
            failures.append(f"place structure failed: {m.string.strip()}")
        # If jigsaw assembly works there are houses with villagers, not just the plaza.
        m = run(proc, lines, seen, "execute if entity @e[type=minecraft:villager]", r"Test passed\. Count: (\d+)|Test failed")
        villagers = int(m.group(1)) if m.group(1) else 0
        if villagers == 0:
            failures.append("the placed village has no villagers")
        # Each unique structure is placed (they overlap on the same spot: all that matters is that they generate).
        for sid in UNIQUE_STRUCTURES:
            hook = unique_hook(sid)
            if hook:    # structures that are not placed with /place (own type): their module brings its own checks
                failures += [f"{sid}: {f}" for f in hook(Context(proc, lines, seen))]
                continue
            m = run(proc, lines, seen, f"place structure {sid} 0 ~ 0", r"Generated structure")
            if not m.group(0).startswith("Generated"):
                failures.append(f"place structure {sid} failed: {m.string.strip()}")
            elif not guardian_placed(Context(proc, lines, seen), sid):
                failures.append(f"{sid}: its guardian with the advancement tag does not appear")
            else:
                failures += [f"{sid}: {f}" for f in guardian_trophy(Context(proc, lines, seen), sid)]
        # The loot tables are read (and the heraldia:sin_lootr condition is registered if any uses it).
        for table in LOOT_TABLES:
            t0 = time.monotonic()
            m = run(proc, lines, seen, f"loot spawn 0 200 0 loot {table}", r"Dropped \d+|No items")
            found = bool(re.match(r"Dropped [1-9]", m.group(0)))
            took = time.monotonic() - t0
            # maps without a destination and guardian death tables (without the mob, their vanilla loot may come out empty)
            if not m.group(0).startswith(("Dropped", "No items")) or ("No items" in m.group(0) and not
                                                                   re.search(":(mapas|guardianes)/", table)):
                failures.append(f"loot {table} failed: {m.string.strip()}")
            if ":mapas/" in table:
                # With no reachable structure the map is discarded ("No items"), but it must never hang the server.
                print(f"mapa {table}: {'con destino' if found else 'sin destino'} en {took:.1f} s")
                if found:
                    maps_found.append(table)
                if took > MAP_TIMEOUT_S:
                    failures.append(f"map {table} took {took:.0f} s (> {MAP_TIMEOUT_S} s)")
        failures += check_keys(Context(proc, lines, seen))
        # The epic chest (with its group of maps) is rolled several times in a row.
        t0 = time.monotonic()
        for _ in range(EPIC_ROLLS):
            m = run(proc, lines, seen, "loot spawn 0 200 0 loot heraldia:cofres/epico", r"Dropped \d+")
            if not m.group(0).startswith("Dropped"):
                failures.append(f"epic chest failed: {m.string.strip()}")
                break
        if time.monotonic() - t0 > MAP_TIMEOUT_S:
            failures.append(f"{EPIC_ROLLS} epic chests took {time.monotonic() - t0:.0f} s")
        # Map trades: the villager_trade registry loads (or the log shows errors) and the cartographer filter
        # of Heraldia recognizes the villagers of the placed village and rejects a vanilla one.
        m = run(proc, lines, seen, "execute if entity @e[type=minecraft:villager,tag=heraldia,predicate=heraldia:aldeano_heraldia]",
                r"Test passed|Test failed")
        if "passed" not in m.group(0):
            failures.append("Heraldia's villagers do not satisfy heraldia:aldeano_heraldia")
        run(proc, lines, seen, "summon minecraft:villager 0 200 0 {Tags:[\"heraldia_vanilla\"],NoAI:1b}", r"Summoned")
        m = run(proc, lines, seen, "execute if entity @e[type=minecraft:villager,tag=heraldia_vanilla,predicate=heraldia:aldeano_heraldia]",
                r"Test passed|Test failed")
        if "failed" not in m.group(0):
            failures.append("un aldeano vanilla cumple heraldia:aldeano_heraldia")
        m = run(proc, lines, seen, "function heraldia:golems", r"Running function|Ran \d+ command")
        if not m.group(0).startswith(("Running", "Ran")):
            failures.append(f"function heraldia:golems failed: {m.string.strip()}")
    finally:
        if proc.poll() is None:
            send(proc, "stop")
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
    log = os.path.join(args.work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else "".join(seen)
    for bad in ("Registry loading errors", "Failed to load datapacks", "Couldn't load", "Failed to parse",
                "Found validation problems in advancement heraldia:"):
        if bad in text:
            failures.append(f"the log contains {bad!r}")
    if failures:
        print("SMOKE TEST FAILED:\n  " + "\n  ".join(failures))
        return 1
    sys.stdout.flush()
    print(f"SMOKE TEST OK: {expected} registered structures, {expected_advancements} advancements, {PLACE_TARGET} placed with {villagers} villagers, loot, {len(maps_found)} maps with destination, functions and configuration correct ({located})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
