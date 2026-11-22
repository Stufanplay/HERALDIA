"""Chained treasure hunt (T40) on a real dedicated 26.3 server, with a simulated player (Carpet).

Usage: python3 tools/smoke/treasure.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Checks, with the test seed (heraldia) and the default configuration except tesoro.*:
  - loot: with treasure.probability = 100 a mine table and a medium-structure table give the fragment; after changing the file to 0
    and /heraldia reload (without restarting), they no longer do;
  - /heraldia treasure give gives the fragment (paper with the heraldia_busqueda mark) and the tesoro/fragmento advancement;
  - when used (player ... use once, one right click) the chain is chosen off the server thread and the fragment becomes
    a vanilla map (filled_map) with the whole chain; the destinations are real Heraldia structures (medium or
    mine), less than treasure.radio_max from each other, without repeats, and the search has not loaded their chunks;
  - far from the mark the map does not change; teleported to each mark (where /locate finds its structure within
    48 blocks: it is real), it moves on to the next;
  - RESTART halfway through the chain: the map keeps its step and its destinations and carries on from there;
  - at the treasure, with a planks "house" right on the mark, the chest is buried outside it and its margin, on ground,
    one block below the top, with the heraldia:tesoro/cofre table; when opened (digging the block above), its loot brings the
    Ysolda's Compass and the tesoro/cofre advancement is granted;
  - the chain is completed only once: using the map again does not bury another chest, not even after another restart.
Measures how long it takes to choose the chain and to search for the chest site (log lines).
"""
import argparse, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from terralith_biomes import fetch
from trophies import CARPET

P = "Buscador"
X, Y, Z = 0, 101, 0
RADIUS = 2500
CONFIG = {"tesoro": {"activado": True, "probabilidad": 100, "radio_max": RADIUS}}
MARK = "heraldia_busqueda"
CHOSEN = re.compile(r"tesoro: cadena de (\w+) elegida en (\d+) ms \((\d+) casillas")
INFO = re.compile(r"Heraldia: tesoro: info (\{.*\})")
SITE = re.compile(r"tesoro: sitio del cofre de \w+ en \((-?\d+), (-?\d+)\): (.*) en (\d+) µs")
CHEST_TABLE = re.compile(r"tesoro: cofre de \w+ enterrado en (-?\d+) (-?\d+) (-?\d+)")
HOUSE = 2   # half the side of the planks "house" placed on the treasure mark
MARGIN = 6   # Sitio.MARGIN


def write_config(work, extra):
    with open(os.path.join(work, "config", "heraldia.json"), "w", encoding="utf-8") as f:
        json.dump(extra, f)


def chain(srv):
    """The chain of the map in hand: {paso, destinos: [{tipo, estructura, x, z, generada}], cofre, movido} (from the
    "tesoro: info" log line left by /heraldia treasure info); None if it carries no map with a chain."""
    m = srv.ctx.run(f"execute as {P} run heraldia treasure info", INFO.pattern + r"|Undeciphered|sin descifrar|not holding|No llevas")
    return parse(m.group(1)) if m.group(1) else None


def parse(snbt):
    out = {"paso": int(re.search(r"\bpaso:(\d+)", snbt).group(1)), "destinos": [],
           "movido": int((re.search(r"\bmovido:(\d+)", snbt) or [0, 0])[1])}
    m = re.search(r"cofre:\[I;(-?\d+),(-?\d+),(-?\d+)\]", snbt)
    out["cofre"] = tuple(int(v) for v in m.groups()) if m else None
    lst = snbt[snbt.index("destinos:[") + len("destinos:["):]
    for obj in re.findall(r"\{([^{}]*)\}", lst):
        d = {"tipo": re.search(r'tipo:"(\w+)"', obj).group(1), "x": int(re.search(r"\bx:(-?\d+)", obj).group(1)),
             "z": int(re.search(r"\bz:(-?\d+)", obj).group(1)), "generada": "generada:1b" in obj}
        e = re.search(r'estructura:"([^"]+)"', obj)
        d["estructura"] = e.group(1) if e else ""
        out["destinos"].append(d)
    return out


def creative(srv):
    """Creative mode (no fall damage when teleporting); if it already is, the command gives no response."""
    s.send(srv.proc, f"gamemode creative {P}")
    if not srv.ctx.until(f"execute if entity @a[name={P},gamemode=creative]", timeout=20):
        raise SystemExit("the simulated player does not switch to creative")


def use(srv):
    s.send(srv.proc, f"player {P} use once")   # nothing is answered on the console
    srv.ctx.ticks(10)


def tp(srv, x, z, y=200):
    srv.ctx.run(f"tp {P} {x} {y} {z}", r"Teleported|Teletransportado")
    srv.ctx.ticks(5)


def real_structure(srv, d, fails):
    """With the player already on the mark (chunks loaded): /locate of its structure from there finds it within 48 blocks."""
    srv.ctx.ticks(20)
    m = srv.ctx.run(f"execute positioned {d['x']} 64 {d['z']} run locate structure {d['estructura']}",
                    r"is at \[(-?\d+), ~, (-?\d+)\] \((\d+) blocks? away\)|Could not find|Unknown|Incorrect")
    if not m.group(3) or int(m.group(3)) > 48:
        fails.append(f"at mark {d} there is no {d['estructura']}: {m.group(0)}")
    else:
        print(f"{d['estructura']} at {m.group(1)}, {m.group(2)} ({m.group(3)} blocks from the mark)")


def in_hand(srv, pred):
    return srv.ctx.test(f"execute if items entity {P} weapon.mainhand {pred}")


def advancement(srv, path):
    return srv.ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:{path}=true}}]")


def wait_loaded(srv, x, z, timeout=60):
    return srv.ctx.until(f"execute if loaded {x} 64 {z}", timeout=timeout)


def chest_loot(srv, fails, with_it):
    """A mine table and a medium-structure table give (or not) the fragment with the probability at 100 % (or at 0 %)."""
    ctx = srv.ctx
    for tbl in ("heraldia:minas/boca", "heraldia:medianas/posada/cuarto"):
        ctx.run(f"clear {P} minecraft:paper", r"Removed|No items")
        ctx.run(f"loot give {P} loot {tbl}", r"Dropped|Gave|No items|Unknown")
        has = ctx.test(f"execute if items entity {P} container.* minecraft:paper[minecraft:custom_data~{{{MARK}:{{}}}}]")
        if has != with_it:
            fails.append(f"loot: {tbl} {'does not give' if with_it else 'gives'} the fragment with tesoro.probabilidad = {100 if with_it else 0}")
    ctx.run(f"clear {P}", r"Removed|No items")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-tesoro"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    write_config(a.work, CONFIG)
    srv = Server(a.work, launcher)
    c = None
    try:
        ctx = srv.ctx
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {X - 3} {Y - 1} {Z - 3} {X + 3} {Y - 1} {Z + 3} minecraft:stone", r"Successfully filled|No blocks|not loaded(?! yet)")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        for rule in ("spawn_mobs", "advance_time", "advance_weather"):
            ctx.must(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}.*false")
        srv.spawn(P)
        creative(srv)
        # 1) loot with the probability at 100 % and, after reloading, at 0 %
        chest_loot(srv, fails, True)
        write_config(a.work, dict(CONFIG, tesoro=dict(CONFIG["tesoro"], probabilidad=0)))
        ctx.run("heraldia reload", r"(?:Configuration reloaded from|Configuración recargada de) heraldia\.json")
        chest_loot(srv, fails, False)
        write_config(a.work, CONFIG)
        ctx.run("heraldia reload", r"(?:Configuration reloaded from|Configuración recargada de) heraldia\.json")
        # 2) the first clue
        ctx.run(f"heraldia treasure give {P}", r"given to|dado a|Unknown|Incorrect")
        if not in_hand(srv, f"minecraft:paper[minecraft:custom_data~{{{MARK}:{{v:1}}}}]"):
            m = ctx.run(f"data get entity {P} SelectedItem", r"has the following entity data: (.*)|No entity|found no")
            fails.append(f"/heraldia treasure give does not put the fragment in hand: {m.group(0)[:300]}")
        if not ctx.until(f"execute if entity @a[name={P},advancements={{heraldia:tesoro/fragmento=true}}]", timeout=10):
            fails.append("no tesoro/fragmento advancement on receiving the fragment")
        # 3) decipher it: a map with the chain
        use(srv)
        if not ctx.until(f"execute if items entity {P} weapon.mainhand minecraft:filled_map[minecraft:custom_data~{{{MARK}:{{paso:0}}}}]",
                         timeout=120):
            raise SystemExit(f"the fragment is not deciphered into a map; log: {ctx.log()[-1500:]}")
        m = CHOSEN.search(ctx.log())
        print(f"chain chosen in {m.group(2)} ms ({m.group(3)} cells), off the server thread" if m else "no timing line")
        c = chain(srv)
        print("cadena:", c)
        if not c or len(c["destinos"]) not in (2, 3) or c["destinos"][-1]["tipo"] != "tesoro":
            raise SystemExit(f"invalid chain: {c}")
        prev_pos = (X, Z)
        for i, d in enumerate(c["destinos"][:-1]):
            if d["tipo"] not in ("mediana", "mina") or not d["estructura"].startswith(("heraldia:medianas/", "heraldia:minas/")):
                fails.append(f"mark {i + 1}: not a Heraldia medium structure or mine: {d}")
            dist = ((d["x"] - prev_pos[0]) ** 2 + (d["z"] - prev_pos[1]) ** 2) ** 0.5
            if not 96 <= dist <= RADIUS:
                fails.append(f"mark {i + 1} is {dist:.0f} blocks from the previous one (96-{RADIUS})")
            prev_pos = (d["x"], d["z"])
        if len({(d["x"], d["z"]) for d in c["destinos"]}) != len(c["destinos"]):
            fails.append(f"destinos repetidos: {c['destinos']}")
        first = c["destinos"][0]
        if abs(first["x"]) > 128 or abs(first["z"]) > 128:
            if ctx.test(f"execute if loaded {first['x']} 64 {first['z']}"):
                fails.append("the search loaded the chunk of the first destination (it must not load or generate anything)")
        # 4) far away: the map does not change
        use(srv)
        if chain(srv)["paso"] != 0:
            fails.append("used far from the mark, the map advances")
        # 5) primera marca
        tp(srv, first["x"], first["z"])
        wait_loaded(srv, first["x"], first["z"])
        real_structure(srv, first, fails)
        use(srv)
        c1 = chain(srv)
        if c1["paso"] != 1:
            fails.append(f"at the first mark the map does not move on to the next: {c1}")
    finally:
        srv.stop()
    # 6) restart halfway through the chain: the map keeps the step and the destinations
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        srv.spawn(P)
        creative(srv)
        if not ctx.until(f"execute if items entity {P} weapon.mainhand minecraft:filled_map", timeout=20):
            raise SystemExit("after restarting, the player does not carry the map")
        c2 = chain(srv)
        if not c2 or c2["paso"] != 1 or c2["destinos"] != c["destinos"]:
            fails.append(f"after restarting the map does not keep the chain: {c2} (before {c})")
        c = c2 or c
        while c["destinos"][c["paso"]]["tipo"] != "tesoro":
            d = c["destinos"][c["paso"]]
            tp(srv, d["x"], d["z"])
            wait_loaded(srv, d["x"], d["z"])
            real_structure(srv, d, fails)
            use(srv)
            n = chain(srv)
            if n["paso"] != c["paso"] + 1:
                raise SystemExit(f"at mark {c['paso'] + 1} the map does not advance: {n}")
            c = n
        # 7) the treasure: a "house" on the mark; the chest goes outside it and its margin
        for attempt in range(5):
            t = c["destinos"][-1]
            tp(srv, t["x"], t["z"])
            for dx in (-48, 48):
                for dz in (-48, 48):
                    wait_loaded(srv, t["x"] + dx, t["z"] + dz)
            if attempt == 0:
                ctx.run(f"execute positioned {t['x']} 0 {t['z']} positioned over motion_blocking_no_leaves run "
                        f"fill ~-{HOUSE} ~ ~-{HOUSE} ~{HOUSE} ~2 ~{HOUSE} minecraft:oak_planks hollow", r"Successfully filled|No blocks|Unknown|Incorrect")
            before = len(CHEST_TABLE.findall(ctx.log()))
            use(srv)
            n = chain(srv)
            if n["cofre"]:
                c = n
                break
            if n["movido"] > c["movido"]:
                print(f"the treasure site was not safe: the mark has moved ({n['destinos'][-1]})")
                c = n
                continue
            m = SITE.findall(ctx.log())
            raise SystemExit(f"the chest is not buried at the treasure: {n}; site: {m[-1] if m else '?'}")
        else:
            raise SystemExit("the treasure moved 5 times without finding a site")
        m = SITE.findall(ctx.log())
        if m:
            print(f"chest site searched in {m[-1][3]} µs ({m[-1][2]})")
        cx, cy, cz = c["cofre"]
        t = c["destinos"][-1]
        if not ctx.block((cx, cy, cz), "minecraft:chest"):
            fails.append(f"no chest at {c['cofre']}")
        if max(abs(cx - t["x"]), abs(cz - t["z"])) <= HOUSE + MARGIN and c["movido"] == 0:
            fails.append(f"the chest ({cx}, {cz}) is in the planks house or its margin (mark {t['x']}, {t['z']})")
        if ctx.block((cx, cy + 1, cz), "minecraft:air") or ctx.block((cx, cy + 1, cz), "minecraft:oak_planks"):
            fails.append("the chest is not buried (in the air or under planks)")
        if not ctx.test(f'execute if data block {cx} {cy} {cz} {{LootTable:"heraldia:tesoro/cofre"}}'):
            fails.append("the chest does not have the heraldia:tesoro/cofre table")
        # 8) dig and open it: loot, keepsake and advancement
        ctx.run(f"setblock {cx} {cy + 1} {cz} minecraft:air", r"Changed the block|Could not set")
        ctx.run(f"tp {P} {cx + 0.5} {cy + 1} {cz + 0.5}", r"Teleported|Teletransportado")
        ctx.ticks(5)
        s.send(srv.proc, f"player {P} look at {cx + 0.5} {cy + 0.5} {cz + 0.5}")
        ctx.ticks(2)
        for _ in range(3):
            use(srv)
            if advancement(srv, "tesoro/cofre"):
                break
        if not advancement(srv, "tesoro/cofre"):
            fails.append("opening the chest does not grant the tesoro/cofre advancement")
        if not ctx.test(f"execute if items block {cx} {cy} {cz} container.* minecraft:compass[minecraft:custom_data~{{heraldia_recuerdo_tesoro:1b}}]"):
            fails.append("the chest does not bring Ysolda's Compass")
        # 9) only once: the map no longer buries another
        ctx.run(f"tp {P} {t['x']} 200 {t['z']}", r"Teleported|Teletransportado")
        ctx.ticks(5)
        use(srv)
        if len(CHEST_TABLE.findall(ctx.log())) != 1:
            fails.append(f"more than one chest was buried: {CHEST_TABLE.findall(ctx.log())}")
    finally:
        srv.stop()
    # 10) another restart: the chain stays completed and gives no other chest
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        srv.spawn(P)
        creative(srv)
        ctx.until(f"execute if items entity {P} weapon.mainhand minecraft:filled_map", timeout=20)
        c3 = chain(srv)
        if not c3 or c3["cofre"] != c["cofre"]:
            fails.append(f"after restarting, the map does not remember the chest: {c3}")
        t = c["destinos"][-1]
        tp(srv, t["x"], t["z"])
        wait_loaded(srv, t["x"], t["z"])
        use(srv)
        if CHEST_TABLE.search(ctx.log()):
            fails.append("after restarting, the completed map buries another chest")
    finally:
        srv.stop()
    log = os.path.join(a.work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
    for bad in ("Registry loading errors", "Failed to load datapacks", "Couldn't load", "Failed to parse",
                "Found validation problems", "no se pudo descifrar"):
        if bad in text:
            fails.append(f"the log contains {bad!r}")
    print("TESORO:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
