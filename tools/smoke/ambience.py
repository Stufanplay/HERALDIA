"""Ambient effects (ambience/Ambience.java) on a real 26.3 dedicated server, with a Carpet simulated player.

Usage: python3 tools/smoke/ambience.py --jar build/libs/heraldia-X.jar [--work build/smoke-ambiente]
The server runs with -Dheraldia.ambiente.registro=true (each effect played is written to the log) and
-Dheraldia.perfil=true (the cost of the 5-second check, written when it stops). The structures are natural ones, found with
/locate (a /place'd structure leaves no start in its chunk, and the effects look for the starts, like the advancements):
  1. Village bell: the player stands in the nearest Heraldia village; the clock is set just before sunrise: one peal
     ("alba", for 1 player). Right after, nightfall: no peal (the player has just heard it). After 5 min of game time
     (/tick sprint), nightfall again: the evening peal.
  2. Lighthouse siren: the player stands in the open next to the nearest coastal lighthouse; with clear weather nothing,
     with rain the horn (for 1 player); a minute later in the same rain, nothing (3 min cooldown).
  3. Mine galleries: the player stands in a gallery of the nearest mine adit (a dug-out cell with rock above, found with
     a location predicate on the structure tag, the same test the mod does); in 90 s of game time at least one drip or echo and at most one every 20 s; with ambiente.minas off
     (/heraldia reload), none.
  4. With every effect played: no error in the log, and the cost of the check (count, mean and max in microseconds).
Exit code 0 if everything passes.
"""
import argparse, json, os, re, shutil, sys, time
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import village_terrain as at
from terralith_biomes import fetch
from trophies import CARPET

PLAYER = "Testigo"
PROPS = ["-Dheraldia.ambiente.registro=true", "-Dheraldia.perfil=true"]
BELL = re.compile(r"ambiente: campana de (alba|anochecer) en (-?\d+) (-?\d+) (-?\d+) para (\d+) jugador")
SIREN = re.compile(r"ambiente: sirena del faro de (-?\d+) (-?\d+) (-?\d+) para (\d+) jugador")
MINE = re.compile(r"ambiente: (gota|eco) en (-?\d+) (-?\d+) (-?\d+) para " + PLAYER)
PROFILE = re.compile(r"Heraldia: perfil: (\{.*\})\s*$", re.M)
LOCATED = r"is at \[(-?\d+), (~|-?\d+), (-?\d+)\]|Could not find"
SPRINT = r"The game is sprinting|Sprint completed|[Ss]print"
SPRINT_DONE = re.compile(r"Sprint completed")
CLOCK = r"Set minecraft:overworld to (\d+) tick"
TIME_SET = r"Set the time|Set minecraft:overworld to|[Aa]dded"   # 26.3: "Set minecraft:overworld to 6000 tick(s)"
WAIT_S = 45
SCAN = 36                                       # blocks around the located chunk where the gallery is looked for
HIT = re.compile(r"HIT (-?\d+) (-?\d+) (-?\d+)")
TELEPORTED = r"Teleported \S+ to (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)"


def pump(ctx):
    """Reads what the server has written (any quick command makes ctx collect the pending lines)."""
    ctx.run("time query gametime", r"[Tt]ime is (\d+)")


def wait_log(ctx, pattern, since, timeout=WAIT_S):
    """The first match of `pattern` written after line `since`, waiting up to `timeout` seconds; None if it does not come."""
    end = time.monotonic() + timeout
    while True:
        pump(ctx)
        m = pattern.search("".join(ctx.seen[since:]))
        if m or time.monotonic() > end:
            return m
        time.sleep(1)


def sprint(ctx, ticks):
    """Runs `ticks` game ticks as fast as the server can and waits until they are done."""
    since = len(ctx.seen)
    ctx.run(f"tick sprint {ticks}", SPRINT)
    if not wait_log(ctx, SPRINT_DONE, since, timeout=600):
        raise SystemExit(f"/tick sprint {ticks} does not finish")


def clock(ctx):
    """The world clock now (26.3 answers /time add with the new value)."""
    return int(ctx.run("time add 0", CLOCK).group(1))


def to_time_of_day(ctx, target):
    """Moves the clock forward (never back) to the next `target` time of day (0-23,999)."""
    now = clock(ctx)
    ctx.run(f"time add {(target - now) % 24000}", CLOCK)


def locate(ctx, what):
    m = ctx.run(f"execute positioned 0 100 0 run locate structure {what}", LOCATED)
    if not m.group(1):
        raise SystemExit(f"/locate {what}: nothing near 0,0 with the test seed")
    return int(m.group(1)), int(m.group(3))


def load(ctx, x, z, r):
    ctx.run(f"forceload add {x - r} {z - r} {x + r} {z + r}", r"Marked|[Aa]dded|force|already")
    for px, pz in ((x - r, z - r), (x + r, z + r), (x, z)):
        if not ctx.until(f"execute if loaded {px} 64 {pz}", timeout=300):
            raise SystemExit(f"the chunks around {x} {z} do not load")
    ctx.ticks(20)


def surface(ctx, x, z):
    """Puts the player on the surface at x, z (on top of whatever is there: out in the open)."""
    ctx.run(f"execute positioned {x} 0 {z} positioned over motion_blocking run tp {PLAYER} ~ ~ ~", r"Teleported|[Tt]eleport")


def player(ctx):
    ctx.run("forceload add -8 -8 8 8", r"Marked|[Aa]dded|force|already")
    ctx.run(f"player {PLAYER} spawn at 0 120 0", r"joined the game")
    if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
        raise SystemExit(f"the simulated player {PLAYER} does not appear (Carpet)")
    s.send(ctx.proc, f"gamemode creative {PLAYER}")
    ctx.until(f"execute if entity @a[name={PLAYER},gamemode=creative]")


def bell(ctx, fails):
    vx, vz = locate(ctx, "#heraldia:aldeas")
    load(ctx, vx, vz, 48)
    surface(ctx, vx, vz)
    ctx.run("time set 6000", TIME_SET)
    since = len(ctx.seen)
    ctx.ticks(2 * 100)
    if BELL.search("".join(ctx.seen[since:])):
        fails.append("bell: it rings at noon")
    # from here the clock only moves forward: each step reaches a new sunrise or nightfall
    since = len(ctx.seen)
    to_time_of_day(ctx, 23950)                     # sunrise in 50 ticks
    m = wait_log(ctx, BELL, since)
    print(f"bell at sunrise in the village of {vx} {vz}: {m.group(0) if m else 'nothing'}")
    if not m or m.group(1) != "alba" or m.group(5) != "1":
        fails.append(f"bell: no morning peal for the player in the village ({m.group(0) if m else 'nothing'})")
    since = len(ctx.seen)
    to_time_of_day(ctx, 11950)                     # nightfall, within the player's 5 min cooldown
    ctx.ticks(300)
    pump(ctx)
    if BELL.search("".join(ctx.seen[since:])):
        fails.append("bell: it rings again for a player who has just heard it")
    to_time_of_day(ctx, 14000)                     # past nightfall: nothing to ring during the sprint
    sprint(ctx, 6200)                              # the cooldown is over
    since = len(ctx.seen)
    to_time_of_day(ctx, 11950)                     # the next nightfall
    m = wait_log(ctx, BELL, since)
    print(f"bell at nightfall once the cooldown is over: {m.group(0) if m else 'nothing'}")
    if not m or m.group(1) != "anochecer":
        fails.append("bell: no evening peal once the cooldown is over")
    to_time_of_day(ctx, 6000)


def siren(ctx, fails):
    ctx.run("weather clear", r"[Cc]hanging the weather|clear")
    lx, lz = locate(ctx, "#heraldia:costa/faro")
    load(ctx, lx, lz, 48)
    surface(ctx, lx + 40, lz)
    # firm footing: next to a lighthouse it may be the sea, and a creative player sinks (under water: rightly no siren)
    ctx.run(f"execute at {PLAYER} run setblock ~ ~-1 ~ minecraft:stone", r"Changed the block|Could not set")
    since = len(ctx.seen)
    ctx.ticks(300)
    pump(ctx)
    if SIREN.search("".join(ctx.seen[since:])):
        fails.append("siren: it sounds in clear weather")
    since = len(ctx.seen)
    ctx.run("weather rain", r"[Cc]hanging the weather|rain")
    m = wait_log(ctx, SIREN, since)
    print(f"siren of the lighthouse at {lx} {lz} in the rain: {m.group(0) if m else 'nothing'}")
    if not m or m.group(4) != "1":
        fails.append(f"siren: no horn for the player next to the lighthouse in the rain ({m.group(0) if m else 'nothing'})")
    since = len(ctx.seen)
    sprint(ctx, 1200)
    pump(ctx)
    again = SIREN.findall("".join(ctx.seen[since:]))
    if again:
        fails.append(f"siren: it sounds again within its 3 min ({len(again)} more in 1 min)")
    ctx.run("weather clear", r"[Cc]hanging the weather|clear")


def gallery(ctx):
    """A dug-out cell (solid floor, air at the feet and head, rock above) inside the nearest mine adit, found with the same structure
    test the mod uses (a location predicate with the structure tag), all positions sent in one go: only the hits answer."""
    mx, mz = locate(ctx, "#heraldia:minas/pequena")
    load(ctx, mx + 8, mz + 8, 64)
    m = ctx.run(f"execute positioned {mx + 8} 0 {mz + 8} positioned over motion_blocking run tp {PLAYER} ~ ~ ~", TELEPORTED)
    top = int(float(m.group(2)))
    pred = '{type:"minecraft:location_check",predicate:{structures:"#heraldia:minas/pequena"}}'
    since = len(ctx.seen)
    n = 0
    for y in range(top - 40, top + 8, 2):
        for x in range(mx + 8 - SCAN, mx + 8 + SCAN + 1, 3):
            for z in range(mz + 8 - SCAN, mz + 8 + SCAN + 1, 3):
                s.send(ctx.proc, f"execute positioned {x} {y} {z} if predicate {pred} if block ~ ~ ~ minecraft:air "
                                 f"if block ~ ~1 ~ minecraft:air unless block ~ ~-1 ~ minecraft:air unless block ~ ~5 ~ minecraft:air "
                                 f"run say HIT {x} {y} {z}")
                n += 1
    pump(ctx)
    ctx.ticks(40)
    pump(ctx)
    hits = [tuple(map(int, h)) for h in HIT.findall("".join(ctx.seen[since:]))]
    print(f"mine at {mx} {mz}: {len(hits)} gallery cells among {n} positions tested")
    if not hits:
        raise SystemExit(f"mine: no gallery cell found around {mx} {mz}")
    # the gallery's floor is the height most cells share (the descent and a stray cave pocket are a few)
    floor = Counter(h[1] for h in hits).most_common(1)[0][0]
    return min((h for h in hits if h[1] == floor), key=lambda h: (h[0], h[2]))


def mine(ctx, fails, work):
    x, y, z = gallery(ctx)
    ctx.run(f"tp {PLAYER} {x + 0.5} {y} {z + 0.5}", r"Teleported|[Tt]eleport")
    since = len(ctx.seen)
    sprint(ctx, 1800)
    pump(ctx)
    cues = MINE.findall("".join(ctx.seen[since:]))
    print(f"mine gallery at {x} {y} {z}: {len(cues)} cues in 90 s ({', '.join(c[0] for c in cues)})")
    if not cues:
        fails.append("mine: no drip or echo in 90 s in the gallery")
    if len(cues) > 1800 // (20 * 20) + 1:
        fails.append(f"mine: {len(cues)} cues in 90 s, more than one every 20 s")
    path = os.path.join(work, "config", "heraldia.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("ambiente", {})["minas"] = False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    ctx.run("heraldia reload", r"Heraldia: configuración recargada")
    since = len(ctx.seen)
    sprint(ctx, 1800)
    pump(ctx)
    if MINE.search("".join(ctx.seen[since:])):
        fails.append("mine: cues with ambiente.minas off")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-ambiente"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    proc, ctx = at.start_server(a.work, launcher, PROPS)
    try:
        ctx.run("gamerule spawn_mobs false", r"Gamerule|set to")
        player(ctx)
        bell(ctx, fails)
        siren(ctx, fails)
        mine(ctx, fails, a.work)
        ctx.run(f"player {PLAYER} kill", r"left the game")
    finally:
        at.stop(proc)
        while True:
            try:
                line = ctx.lines.get(timeout=30)
            except Exception:
                break
            if line is None:
                break
            ctx.seen.append(line)
    log = ctx.log()
    errors = [l for l in log.splitlines() if "heraldia" in l.lower() and ("Exception" in l or "/ERROR]" in l)]
    if errors:
        fails.append(f"errors in the log: {errors[:3]}")
    prof = PROFILE.search(log)
    amb = json.loads(prof.group(1)).get("ambiente") if prof else None
    if amb:
        print(f"cost of the ambience check (every 100 ticks, 1 player): n={amb['n']}, mean {amb['media_us']} µs, "
              f"max {amb['max_us']} µs, total {amb['total_ms']} ms")
    else:
        fails.append("the profile has no 'ambiente' entry")
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: village bell at sunrise and nightfall with its cooldown, lighthouse siren only in the rain and with its cooldown, "
          "drips and echoes in the mine gallery (and none with ambiente.minas off)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
