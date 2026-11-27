"""Caravans along the roads between villages on a real 26.3 dedicated server (T39; complements the JUnit tests of caravanas/).

Usage: python3 tools/smoke/caravans.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-caravanas"
Deterministic: the seed and the minimal grid of villages from roads.py (the same route on dry land), the caravan
roll turned off (caravans.frequency = 0: they only appear with the command) and a Carpet simulated player. The
chunks of the route's central stretch are generated (forceload) and the player is placed next to the road.
First start:
  1. /heraldia caravan spawn raid: a caravan appears (merchant, 1 to 3 llamas, maybe a guard) that advances along the
     road toward the destination village; /heraldia caravan raid forces the ambush: 2 to 4 bandits appear with the
     tags of the anchored mobs; the player kills them, the caravan continues and, moved from vertex to vertex to
     the end, arrives: the player collects the emeralds and the item, the reputation with the destination village rises by 15 (the
     quest API) and the advancement is granted; no caravan entity remains.
  2. Another caravan: the player kills the merchant; the caravan is lost, with no reward and nothing on the ground.
  3. Another: the player moves 400 blocks away; after 30 s it is dismissed and its entities are removed.
  4. The wayfarers on the same engine (tools/smoke/wayfarers.py, `scenario`): every kind, its endings and its switches.
  5. An entity with the caravan tag that belongs to no active one is removed on load (what happens to
     those from before a restart). And another caravan is left on the road when the server stops: it is removed on stopping.
Second start (same world, the corridor is still forceloaded): no caravan entity; a new one appears (just one,
no duplicates); /heraldia status counts it; with caravans.switched_on = false and /heraldia reload the existing one goes away, the
command says they are disabled and so does /heraldia status.
"""
import argparse, json, math, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import village_terrain as at
import importlib.util
from terralith_biomes import fetch
from trophies import CARPET

# the road test by its route: plain "caminos" is the generator module (tools/gen, in sys.path)
_spec = importlib.util.spec_from_file_location("roads_smoke", os.path.join(os.path.dirname(os.path.abspath(__file__)), "roads.py"))
cabin_adv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cabin_adv)

PLAYER = "Testigo"
TAG, MERCHANT, FLAME, SENTRY, BANDIT = ("heraldia_caravana", "heraldia_caravana.mercader", "heraldia_caravana.llama",
                                          "heraldia_caravana.guardia", "heraldia_caravana.bandido")
DEPARTS = re.compile(r"sale la caravana (\d+) de (.+?) hacia (.+?): (\d+) vértices \((\d+) bloques\) desde (-?\d+) (-?\d+) (-?\d+) "
                  r"hasta (-?\d+) (-?\d+), asalto (no|en el vértice \d+), (\d) llamas, (con|sin) guardia")
VERTICES = re.compile(r"vértices de la caravana (\d+): (.*)")
NO_ROAD = r"There is no Heraldia road|No hay ningún camino"
NO_RAID = r"There is no caravan on the road that can be ambushed|No hay ninguna caravana en camino que se pueda asaltar"
ITEM_LIST = re.compile(r"waypoint (\d+) of (\d+)|vértice (\d+) de (\d+)")
SEGMENT = (0.3, 0.7)          # central part of the route that is generated (the spawn looks 80 blocks from the player)


def configure(work, extra=None):
    cfg = {"aldeas": {"separacion_bloques": cabin_adv.GRID, "maximo": 100}, "caravanas": {"frecuencia": 0}, "viajeros": {"frecuencia": 0}}
    for k, v in (extra or {}).items():
        cfg.setdefault(k, {}).update(v)
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def wait(ctx, pattern, start):
    """The first line from `start` (index in ctx.seen) that matches `pattern`: already read (a later command moves
    whatever was in the queue into ctx.seen) or the one that arrives."""
    s.pending(ctx.lines, ctx.seen)
    for line in ctx.seen[start:]:
        m = re.search(pattern, line)
        if m:
            return m
    return s.wait_for(ctx.lines, pattern, s.COMMAND_TIMEOUT_S, ctx.seen)


def as_player(ctx, cmd, ok):
    """The command run by the simulated player (the reply goes to the console: "execute as" keeps the source)."""
    return ctx.run(f"execute as {PLAYER} at @s run {cmd}", ok)


SURFACE_TP = "positioned over motion_blocking_no_leaves run tp"
# The three replies this teleport can give. All three are listed so the wait ends promptly on each, and only the first
# is accepted afterwards: `No entity was found` is NOT in `ERROR_PATTERN`, so leaving it out of `ok` would make the wait
# run its full COMMAND_TIMEOUT_S (300 s) instead of failing. `run()` now fails by default, but only on a reply `ok` does
# not accept: `not loaded` stays in `ok` because the retry needs it back, so the check below still has to reject it,
# and `No entity` too.
_TP_REPLIES = r"Teleported|No entity|not loaded"


def on_floor(ctx, sel, x, z):
    """Puts `sel` on the surface of the column (x, z), and **fails if it did not get there**.

    The reply used to be thrown away, so a column that was not loaded answered "That position is not loaded" and the
    test carried on with the entity where it already was. Measured, three times in one run, on the `away` check whose
    whole purpose is that the player moved 400 blocks off: it then printed "the player moves away", accepted the
    dismissal and passed, without the player having moved.

    `positioned over <heightmap>` needs the column loaded; an absolute `tp` does not, and for a **player** it makes the
    column usable afterwards even while `execute if loaded` still answers false (both measured on a dedicated server).
    A non-player entity cannot do that: teleported into an unloaded column it vanishes from the selectors and cannot
    even be fetched back (measured), and loading the column with `forceload` is not an option here -- holding chunks
    loaded changes what this test observes, since a caravan is dismissed for distance when the player leaves **or**
    when its chunk unloads. So for an entity there is nothing to retry and the honest thing is to say so.

    Deliberately minimal: the path that works today is untouched (same command, same coordinates), the retry only
    happens where the test used to do nothing at all, and nothing here waits for the entity to settle -- that would
    change what is observed, not just whether it is checked."""
    cmd = f"execute positioned {x} 300 {z} {SURFACE_TP} {sel} ~ ~ ~"
    m = ctx.run(cmd, _TP_REPLIES)
    if "not loaded" in m.string and not sel.startswith("@"):      # a player loads its own column; an entity cannot
        ctx.run(f"tp {sel} {x} 300 {z}", r"Teleported|No entity")
        m = ctx.run(cmd, _TP_REPLIES)
    if "Teleported" not in m.string:
        raise SystemExit(f"on_floor: {sel} did not reach the surface of ({x}, {z}): {m.string.strip()[-120:]}")


def point(a, b, t):
    return int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t)


def new_one(ctx, fails, route, mode):
    """Puts the player next to the road and spawns a caravan with /heraldia caravan spawn <mode>: its log line and its vertices."""
    a, b, _ = route
    for t in (0.5, 0.44, 0.56, 0.38, 0.62):
        x, z = point(a, b, t)
        on_floor(ctx, PLAYER, x, z)
        ctx.ticks(10)
        m = as_player(ctx, f"heraldia caravan spawn {mode}".strip(), rf"{DEPARTS.pattern}|{NO_ROAD}|already \d+ caravans|Ya hay \d+")
        if m.group(1):
            v = s.wait_for(ctx.lines, rf"vértices de la caravana {m.group(1)}: (.*)", s.COMMAND_TIMEOUT_S, ctx.seen)
            vert = [tuple(int(n) for n in p.split()) for p in v.group(1).strip().split("; ")]
            c = {"id": m.group(1), "origen": m.group(2), "destino": m.group(3), "n": int(m.group(4)), "largo": int(m.group(5)),
                 "salida": (int(m.group(6)), int(m.group(7)), int(m.group(8))), "asalto": m.group(11), "llamas": int(m.group(12)),
                 "guardia": m.group(13) == "con", "vertices": vert}
            print(f"caravan {c['id']}: from {c['origen']} to {c['destino']}, {c['n']} vertices ({c['largo']} blocks) from "
                  f"{c['salida']}, asalto {c['asalto']}, {c['llamas']} llamas, {'con' if c['guardia'] else 'sin'} guardia")
            return c
        print(f"no caravan near {x} {z} (t = {t}): {m.group(0).strip()[-90:]}")
    fails.append(f"/heraldia caravan spawn {mode}: no caravan appears next to the road")
    return None


def following(ctx):
    m = as_player(ctx, "heraldia caravan list", ITEM_LIST.pattern + r"|There are no caravans|No hay ninguna caravana")
    return (int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4))) if (m.group(1) or m.group(3)) else None


def emeralds(ctx):
    m = ctx.run(f"clear {PLAYER} minecraft:emerald 0", r"Found (\d+) matching|No items")
    return int(m.group(1) or 0)


def state(ctx, pattern):
    """The first line of /heraldia status (going through its pages) that matches `pattern`, or None."""
    pat = re.compile(pattern)
    for page in range(1, 8):
        m = as_player(ctx, f"heraldia status {page}", r"server status \(page (\d+) of (\d+)\)|estado del servidor \(página (\d+) de (\d+)\)")
        for line in s.drain(ctx):
            if pat.search(line):
                return pat.search(line)
        if (m.group(1) or m.group(3)) == (m.group(2) or m.group(4)):
            return None
    return None


def defended(ctx, fails, route):
    # `peaceful`, not `raid`: this caravan's ambush is the one forced below, and it must be the only one possible.
    # `spawn raid` plans an ambush at a vertex towards the middle of the segment, and on the corridor this test uses the
    # merchant is already at vertex 3 when the raid is forced (measured: the forced bandits appear at -1310 -435, vertex
    # 3 is -1309 -436). When the plan says vertex 3 the two ambushes race, and when the planned one wins the forced raid
    # is refused and the caravan ends on the ambush timeout, three minutes later (CI, Nov 2026). `caravanas.prob_asalto
    # = 0` would not have helped: it only applies when no mode is given, `raid` forces the plan regardless. With
    # `peaceful` the journey has no planned vertex, so only `/heraldia caravan raid` can start an ambush. `spawn raid`
    # itself is checked in `lost`.
    c = new_one(ctx, fails, route, "peaceful")
    if c is None:
        return
    if ctx.count(f"@e[tag={MERCHANT}]") != 1:
        fails.append(f"caravana {c['id']}: {ctx.count(f'@e[tag={MERCHANT}]')} mercaderes (debe haber 1)")
    if ctx.count(f"@e[tag={FLAME},type=minecraft:trader_llama]") != c["llamas"]:
        fails.append(f"caravana {c['id']}: {ctx.count(f'@e[tag={FLAME}]')} llamas (dice {c['llamas']})")
    if ctx.count(f"@e[tag={SENTRY}]") != (1 if c["guardia"] else 0):
        fails.append(f"caravan {c['id']}: guard count does not match")
    if c["asalto"] != "no":
        raise SystemExit(f"spawn peaceful: caravan {c['id']} plans an ambush ({c['asalto']}), so it can race the forced one")
    # advances along the road: it gets closer to the end
    finish = c["vertices"][-1]
    p0 = ctx.pos(f"@e[tag={MERCHANT}]")
    ctx.ticks(300)
    p1 = ctx.pos(f"@e[tag={MERCHANT}]")
    d0, d1 = math.dist((p0[0], p0[2]), finish), math.dist((p1[0], p1[2]), finish)
    print(f"the merchant advances: from {d0:.0f} to {d1:.0f} blocks from the end in 15 s; {following(ctx)}")
    if d1 > d0 - 4:
        fails.append(f"the merchant does not advance along the road: from {d0:.1f} to {d1:.1f} blocks from the end in 15 s")
    line = state(ctx, r"(?:Caravans on the road|Caravanas en camino): (\d+)")
    if line is None or line.group(1) != "1":
        fails.append(f"/heraldia status does not count the caravan on the road: {line and line.group(0)}")
    # forced ambush. Both replies are listed so the wait ends promptly on either (the refusal holds none of
    # ERROR_PATTERN's words: left out, the wait ran its full COMMAND_TIMEOUT_S), and only the ambush is accepted.
    # The ambush line is anchored on this caravan's id so that no other ambush can stand in for it. A refusal stops the
    # test here and says so: appended to `fails`, it was printed only at the end, or never, when a later step raised.
    m = as_player(ctx, "heraldia caravan raid", rf"asalto a la caravana {c['id']}: (\d+) bandidos|{NO_RAID}")
    if not m.group(1):
        raise SystemExit(f"/heraldia caravan raid did not ambush caravan {c['id']}: {m.string.strip()[-90:]}")
    n = int(m.group(1))
    print(f"asalto: {n} bandidos")
    if not 2 <= n <= 4:
        fails.append(f"ambush with {n} bandits (should be 2 to 4)")
    if ctx.count(f"@e[tag={BANDIT},tag=heraldia_anclado]") != n:
        fails.append("the bandits do not have the tags of the anchored mobs (and of the difficulty)")
    # a second raid on the same caravan is refused: the same three-way wait, the other way round
    m = as_player(ctx, "heraldia caravan raid", rf"asalto a la caravana (\d+): \d+ bandidos|{NO_RAID}")
    if m.group(1):
        fails.append(f"a second /heraldia caravan raid ambushed caravan {m.group(1)} again")
    mark = len(ctx.seen)
    ctx.run(f"execute as @e[tag={BANDIT}] run damage @s 1000 minecraft:player_attack by {PLAYER}", r"Applied|damage|No entity")
    wait(ctx, rf"la caravana {c['id']} supera el asalto", mark)
    # let it arrive: the merchant (and the player) from vertex to vertex to the end
    e0 = emeralds(ctx)
    next_unique = following(ctx)
    mark = len(ctx.seen)
    arrives = re.compile(rf"la caravana {c['id']} llega a (.+?)( tras superar el asalto)? con (\d+) jugadores")
    for k in range(next_unique[0] if next_unique else 1, len(c["vertices"])):
        x, z = c["vertices"][k]
        on_floor(ctx, f"@e[tag={MERCHANT}]", x, z)
        on_floor(ctx, PLAYER, x + 3, z)
        ctx.ticks(30)
        if arrives.search("".join(ctx.seen[mark:])):
            break
    m = wait(ctx, arrives.pattern, mark)
    if m.group(1) != c["destino"] or not m.group(2) or m.group(3) != "1":
        fails.append(f"llegada: {m.group(0)}")
    payout = re.search(rf"{PLAYER} cobra (\d+) esmeraldas(?: y (\d+) × (\S+))? y \+(\d+) de reputación con (.+?) \(ahora (-?\d+)\)", ctx.log())
    rep = re.search(rf"Heraldia: encargos: {PLAYER} defiende la caravana de (.+?): reputación (-?\d+)", ctx.log())
    if not payout:
        fails.append("on arrival, the player is not paid")
        return
    paid = emeralds(ctx) - e0
    print(f"arrives at {m.group(1)}: {payout.group(0)}; {paid} emeralds in the inventory; {rep and rep.group(0)}")
    if paid != int(payout.group(1)) or paid != 2 + c["n"] // 4 + 4:
        fails.append(f"emeralds: {paid} in the inventory, {payout.group(1)} in the log, should be {2 + c['n'] // 4 + 4}")
    if not payout.group(3) or ctx.count(f"@a[name={PLAYER},nbt={{Inventory:[{{id:\"{payout.group(3)}\"}}]}}]") != 1:
        fails.append(f"the defended caravan's item is not in the inventory ({payout.group(3)})")
    if payout.group(4) != "15" or payout.group(5) != c["destino"] or not rep or rep.group(1) != c["destino"] or rep.group(2) != "15":
        fails.append(f"reputation with the destination village {c['destino']}: {payout.group(0)} / {rep and rep.group(0)} (should rise by 15)")
    if not ctx.test(f"execute if entity @a[name={PLAYER},advancements={{heraldia:caravanas/defensa=true}}]"):
        fails.append("advancement caravanas/defensa not granted")
    ctx.ticks(10)
    if ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"after arriving, {ctx.count(f'@e[tag={TAG}]')} caravan entities remain")


def lost(ctx, fails, route):
    # `raid`, so that `spawn raid` is still checked to plan an ambush (see `defended`). Here the plan cannot race
    # anything: the merchant is killed at the start of the segment, and an ambush that did come first would not change
    # how a caravan with a dead merchant ends, nor leave anything behind (bandits are removed with the rest).
    c = new_one(ctx, fails, route, "raid")
    if c is None:
        return
    if c["asalto"] == "no":
        fails.append("spawn raid: the caravan appears with no ambush planned")
    p = ctx.pos(f"@e[tag={MERCHANT}]")
    before = len(re.findall(r" cobra \d+ esmeraldas", ctx.log()))
    mark = len(ctx.seen)
    ctx.run(f"damage @e[tag={MERCHANT},limit=1] 1000 minecraft:player_attack by {PLAYER}", r"Applied|damage")
    m = wait(ctx, rf"termina la caravana {c['id']}: (\w+)", mark)
    ctx.ticks(40)
    floor = ctx.count(f"@e[type=minecraft:item,x={p[0]:.0f},y={p[1]:.0f},z={p[2]:.0f},distance=..24]")
    print(f"merchant dead: {m.group(0)}; {floor} items on the ground; {ctx.count(f'@e[tag={TAG}]')} caravan entities")
    if m.group(1) != "perdida":
        fails.append(f"when the merchant is killed the caravan ends as '{m.group(1)}' (it should be lost)")
    if floor:
        fails.append(f"when the caravan is lost, {floor} items remain on the ground (no exploitation loot): "
                     + "; ".join(ground_items(ctx, p, floor)))
    if ctx.count(f"@e[tag={TAG}]"):
        fails.append("when lost, caravan entities remain")
    if len(re.findall(r" cobra \d+ esmeraldas", ctx.log())) != before:
        fails.append("a lost caravan has paid out")


def _fields(snbt, names):
    """`name: value` for each of `names` found at the top level of an entity's SNBT, the value taken whole (balanced
    brackets), so a long `Item` with components does not push `Thrower` out of a truncated message."""
    out = []
    for name in names:
        i = snbt.find(f"{name}: ")
        if i < 0:
            continue
        j = k = i + len(name) + 2
        depth = 0
        while k < len(snbt):
            ch = snbt[k]
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            k += 1
        out.append(f"{name}: {snbt[j:k]}")
    return ", ".join(out) or snbt.strip()[:400]


def ground_items(ctx, p, n, radius=24):
    """What the items on the ground near `p` are, not just how many: each one's `Item`, where it lies, its `Age` and,
    when the game records it, who dropped it (`Thrower`), so that a red names what was left behind. Seen
    once in a full local pass (1 of 71 tests, 3 of 3 green on repeating it) as a bare "1 items remain", with nothing to
    tell what it was. Each item read is tagged so the next read takes another one."""
    seen_tag, out = "caravans_leido", []
    for _ in range(min(n, 5)):
        sel = (f"@e[type=minecraft:item,x={p[0]:.0f},y={p[1]:.0f},z={p[2]:.0f},distance=..{radius},"
               f"tag=!{seen_tag},sort=nearest,limit=1]")
        m = ctx.run(f"data get entity {sel}", r"has the following entity data: (.*)|No entity was found")
        if not m.group(1):
            break
        out.append(_fields(m.group(1), ("Item", "Pos", "Thrower", "Age")))
        ctx.run(f"tag {sel} add {seen_tag}", r"Added tag|No entity was found")
    return out or ["(none could be read)"]


def far(ctx, fails, route):
    c = new_one(ctx, fails, route, "peaceful")
    if c is None:
        return
    x, _, z = c["salida"]
    mark = len(ctx.seen)
    on_floor(ctx, PLAYER, x + 400, z)
    m = wait(ctx, rf"termina la caravana {c['id']}: (\w+) \((\d+) entidades quitadas", mark)
    print(f"the player moves away: {m.group(0)}")
    if m.group(1) != "lejos":
        fails.append(f"when the player moves away, the caravan ends as '{m.group(1)}' (it should be dismissed)")
    if int(m.group(2)) != 1 + c["llamas"] + c["guardia"]:
        fails.append(f"on dismissal it removes {m.group(2)} entities (should be {1 + c['llamas'] + c['guardia']})")
    if ctx.count(f"@e[tag={TAG}]"):
        fails.append("after dismissal, caravan entities remain")


def orphan(ctx, fails, route):
    x, z = point(route[0], route[1], 0.5)
    on_floor(ctx, PLAYER, x, z)
    ctx.ticks(10)
    mark = len(ctx.seen)
    ctx.run(f'execute at {PLAYER} run summon minecraft:trader_llama ~2 ~ ~ {{Tags:["{TAG}","{FLAME}"]}}', r"Summoned|Unable")
    m = wait(ctx, r"quitada una entidad de una caravana que ya no está en camino \((\w+)", mark)
    ctx.ticks(5)
    if m.group(1) != "trader_llama" or ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"a stray caravan llama is not removed on load: {m.group(0)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-caravanas"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    configure(a.work)
    proc, ctx = at.start_server(a.work, launcher)
    route = c = None
    try:
        route = cabin_adv.find_path(ctx)
        if route is None:
            raise SystemExit("no overland route from the located villages")
        va, vb, L = route
        print(f"route from {va} to {vb}: {L} blocks")
        corridor = [c for c in cabin_adv.chunks_of(va, vb) if SEGMENT[0] <= c[0] <= SEGMENT[1]]
        cabin_adv.generate(ctx, corridor)
        print(f"pasillo generado: {len(corridor)} chunks")
        x, z = point(va, vb, 0.5)
        ctx.run(f"player {PLAYER} spawn at {x} 200 {z}", r"joined the game")
        if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"simulated player {PLAYER} does not appear (Carpet)")
        s.send(ctx.proc, f"gamemode creative {PLAYER}")   # it does not respond in the console
        ctx.run(f"clear {PLAYER}", r"Removed|No items")
        defended(ctx, fails, route)
        lost(ctx, fails, route)
        far(ctx, fails, route)
        orphan(ctx, fails, route)
        # the wayfarers (same engine) on this same server and corridor: tools/smoke/wayfarers.py; it leaves them switched off
        _wspec = importlib.util.spec_from_file_location("wayfarers_smoke", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wayfarers.py"))
        wayfarers = importlib.util.module_from_spec(_wspec)
        _wspec.loader.exec_module(wayfarers)
        wayfarers.scenario(ctx, fails, route, a.work)
        c = new_one(ctx, fails, route, "peaceful")      # it stays on the road when stopping
    finally:
        cabin_adv.halt(proc, ctx)
    if c is not None:
        m = re.search(rf"termina la caravana {c['id']}: (\w+) \((\d+) entidades quitadas", ctx.log())
        print(f"on stopping: {m and m.group(0)}")
        if not m or m.group(1) != "limpieza" or int(m.group(2)) != 1 + c["llamas"] + c["guardia"]:
            fails.append(f"when the server stops, the caravan on the road is not removed: {m and m.group(0)}")
    # segundo arranque
    proc, ctx = at.start_server(a.work, launcher)
    try:
        va, vb, _ = route
        x, z = point(va, vb, 0.5)
        ctx.run(f"player {PLAYER} spawn at {x} 200 {z}", r"joined the game")
        ctx.until(f"execute if entity @a[name={PLAYER}]")
        s.send(ctx.proc, f"gamemode creative {PLAYER}")   # it does not respond in the console
        ctx.ticks(40)
        surplus = ctx.count(f"@e[tag={TAG}]")
        loaded = len(re.findall(r"quitada una entidad de una caravana", ctx.log()))
        print(f"after restarting: {surplus} caravan entities ({loaded} removed on load)")
        if surplus:
            fails.append(f"tras reiniciar quedan {surplus} entidades de caravana")
        c = new_one(ctx, fails, route, "peaceful")
        if c is not None:
            if c["id"] != "1" or ctx.count(f"@e[tag={MERCHANT}]") != 1:
                fails.append(f"after restarting: caravan {c['id']} with {ctx.count(f'@e[tag={MERCHANT}]')} merchants (should be number 1, with 1)")
            as_player(ctx, "heraldia caravan spawn", r"already 1 caravans|Ya hay 1 caravanas")
        # disabled and reloaded without restarting
        configure(a.work, {"caravanas": {"activado": False}})
        mark = len(ctx.seen)
        ctx.run("heraldia reload", r"Heraldia: configuración recargada")
        if c is not None:
            m = wait(ctx, rf"termina la caravana {c['id']}: (\w+)", mark)
            if m.group(1) != "limpieza":
                fails.append(f"when disabled, the caravan on the road ends as '{m.group(1)}'")
        ctx.ticks(10)
        if ctx.count(f"@e[tag={TAG}]"):
            fails.append("desactivadas, quedan entidades de caravana")
        as_player(ctx, "heraldia caravan spawn", r"Caravans are disabled|caravanas están desactivadas")
        if state(ctx, r"Caravans: disabled|Caravanas: desactivadas") is None:
            fails.append("/heraldia status does not say the caravans are disabled")
        ctx.run(f"player {PLAYER} kill", r"left the game")
    finally:
        cabin_adv.halt(proc, ctx)
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: caravan that advances, defended ambush with reward, reputation and advancement, dead merchant, dismissal on "
          "alejarse, entidades sueltas quitadas, reinicio limpio y caravanas desactivadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
