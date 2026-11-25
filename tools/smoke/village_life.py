"""Village life on a real dedicated 26.3 server: style trades, quest board and feats (T11).

Usage: python3 tools/smoke/village_life.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
With Carpet (simulated player, like trophies.py). The style trades and the feats check whether the villager or mob is
inside a village (location predicate with structures), and /place structure does not store the start in the chunk: that
is why a truly generated village is used (/locate structure #heraldia:aldeas from 0,0 and forceload around it).
First round (smoke-test configuration with sieges enabled):
  - board: next to the sheriff (NoAI, invulnerable, named) there is a lectern with the quest book (6 translatable
    pages) and the sheriff has its 3 fixed trades (the family's harvest, style logs, rotten flesh and
    bones for the "Cape of the Watch");
  - style trades: N Heraldia villagers of the profession and level of each trade specific to that village's style (and to the map
    of its family), placed in the square: the player touches them (that rolls their trades) and at least one offers it; N
    identical villagers without the "heraldia" tag never offer it;
  - feat "Night Watch": a zombie killed by the player outside the village does not grant it; inside, it does, with its reward
    (3 emeralds in the inventory).
Second round (same world, aldeas.vida.tratos_estilo and aldeas.vida.tablon disabled): no Heraldia villager
in the square offers the style trade and a village placed with /place structure comes out without a sheriff.
It also compares trades.VANILLA_LEVEL with the trade tags of the game's .jar (how many vanilla trades there are at each
level used by the style trades; the probability of them appearing depends on that).
"""
import argparse, glob, io, json, os, queue, re, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import server_smoke as s
from terralith_biomes import fetch
from trophies import CARPET

PLAYER = "Testigo"
N = 12                      # villagers per trade (with probability >= 1/2 per villager, failing all 12 is 1 in 4,096)
RADIUS = 80                 # forceload around the village start
ATTEMPTS, RETRY_S = 40, 0.5
# Positions of the square template (streets.plaza, board.SLOT): center marker, sheriff, test villager's spot
# and the player's (in the free passage to the north, between the exit and the fountain), relative to the marker.
MARK, SHERIFF = (1, 1), (14, 18)
SPOT, BOT = (11, 4), (11, 2)
ROUND = "heraldia:aldeas/encargos/ronda"
HEALTH_ON = {"vida": {"asedios": True}}
HEALTH_OFF = {"vida": {"tratos_estilo": False, "tablon": False}}


def jar_data(jar):
    """{style: [(id, profession, level, item, name key)]}, {family: (profession, level, key)} and en_us texts."""
    styles, fams = {}, {}
    with zipfile.ZipFile(jar) as z:
        lang = json.loads(z.read("assets/heraldia/lang/en_us.json"))
        tags = {}
        for n in z.namelist():
            m = re.match(r"data/minecraft/tags/villager_trade/(\w+)/level_(\d)\.json", n)
            if m:
                for v in json.loads(z.read(n))["values"]:
                    tags[v] = (m.group(1), int(m.group(2)))
        for n in z.namelist():
            m = re.match(r"data/heraldia/villager_trade/(estilos|familias)/(\w+)/(\w+)\.json", n)
            if not m:
                continue
            t = json.loads(z.read(n))
            tid = f"heraldia:{m.group(1)}/{m.group(2)}/{m.group(3)}"
            depth, lvl = tags[tid]
            g = t["gives"]
            if m.group(1) == "estilos":
                key = (g.get("components") or {}).get("minecraft:item_name", {}).get("translate")
                styles.setdefault(m.group(2), []).append((tid, depth, lvl, g["id"], key))
            else:
                key = next(f["name"]["translate"] for f in t["given_item_modifier"] if f["type"].endswith("set_name"))
                fams[m.group(2)] = (depth, lvl, key)
    return styles, fams, lang


def vanilla_counts(work):
    """How many vanilla trades there are in each #minecraft:<profession>/level_N, read from the .jar of the server's game (the
    Fabric launcher leaves the "bundler" in .fabric/server; the game is inside, in META-INF/versions)."""
    pat = re.compile(r"data/minecraft/tags/villager_trade/(\w+)/level_(\d)\.json$")
    for j in glob.glob(os.path.join(work, ".fabric", "server", "*-server.jar")):
        with zipfile.ZipFile(j) as bundler:
            for inner in [n for n in bundler.namelist() if n.startswith("META-INF/versions/") and n.endswith(".jar")]:
                with zipfile.ZipFile(io.BytesIO(bundler.read(inner))) as z:
                    found = [(pat.match(n), n) for n in z.namelist()]
                    if any(m for m, _ in found):
                        return {(m.group(1), int(m.group(2))): len(json.loads(z.read(n))["values"]) for m, n in found if m}
    return None


def write_config(work, health):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg.setdefault("aldeas", {}).update(health)
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


class Server:
    def __init__(self, work, launcher):
        self.proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines, self.seen = queue.Queue(), []
        threading.Thread(target=s.reader, args=(self.proc, lines), daemon=True).start()
        self.ctx = s.Context(self.proc, lines, self.seen)
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, self.seen)

    def run(self, cmd, ok):
        return self.ctx.run(cmd, ok)

    def test(self, cmd):
        return "passed" in self.run(cmd, r"Test passed|Test failed").group(0)

    def until(self, cmd, want=True, attempts=ATTEMPTS):
        for _ in range(attempts):
            if self.test(cmd) == want:
                return True
            time.sleep(RETRY_S)
        return False

    def data(self, cmd):
        m = self.run(cmd, r"has the following (?:entity|block) data: (.*)|No entity|not a block entity|Found no elements")
        return (m.group(1) or "").replace("\\", "")

    def stop(self):
        if self.proc.poll() is None:
            s.send(self.proc, "stop")
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def rotations():
    """The four rotations of the template on the (x, z) plane."""
    return [lambda x, z: (x, z), lambda x, z: (-z, x), lambda x, z: (-x, -z), lambda x, z: (z, -x)]


def plaza(srv, fails):
    """Generated village closest to 0,0: (style, template -> world function, ground y, sheriff position)."""
    m = srv.run("execute positioned 0 100 0 run locate structure #heraldia:aldeas",
                r"nearest #heraldia:aldeas \((heraldia:\w+)\) is at \[(-?\d+), ~?(-?\d+|~), (-?\d+)\]|Could not find")
    if not m.group(1):
        raise SystemExit("no Heraldia village within reach of /locate")
    sid, x, z = m.group(1).split(":")[1], int(m.group(2)), int(m.group(4))
    style = sid[:-len("_grande")] if sid.endswith("_grande") else sid
    print(f"aldea {sid} en {x}, {z}")
    srv.run(f"forceload add {x - RADIUS} {z - RADIUS} {x + RADIUS} {z + RADIUS}", r"Marked|Added|force|already")
    near = f"positioned {x} 100 {z}"
    sheriff_pos = f"@e[type=minecraft:villager,tag=heraldia_alguacil,sort=nearest,limit=1]"
    if not srv.until(f"execute {near} if entity {sheriff_pos.replace(']', ',distance=..160]')}", attempts=240):
        fails.append(f"{sid}: the board's sheriff does not appear in the square")
        return None
    pos = lambda sel: [float(v) for v in re.findall(r"(-?[\d.]+)d", srv.data(f"execute {near} run data get entity {sel} Pos"))]
    a = pos(sheriff_pos)
    mk = pos("@e[type=minecraft:armor_stand,tag=heraldia_centro,sort=nearest,limit=1]")
    dx, dz = a[0] - mk[0], a[2] - mk[2]
    rot = next((r for r in rotations() if r(SHERIFF[0] - MARK[0], SHERIFF[1] - MARK[1]) == (round(dx), round(dz))), None)
    if rot is None:
        fails.append(f"{sid}: the sheriff is not in its place in the square relative to the marker ({dx}, {dz})")
        return None
    to_world = lambda p: (mk[0] + rot(p[0] - MARK[0], p[1] - MARK[1])[0], mk[2] + rot(p[0] - MARK[0], p[1] - MARK[1])[1])
    return style, to_world, mk[1], a


def check_board(srv, fails, style, a, lang):
    sheriff_pos = "@e[type=minecraft:villager,tag=heraldia_alguacil,sort=nearest,limit=1]"
    at = f"positioned {a[0]} {a[1]} {a[2]}"
    d = srv.data(f"execute {at} run data get entity {sheriff_pos}")
    for want in ("NoAI: 1b", "Invulnerable: 1b", "heraldia.tablon.alguacil", "minecraft:weaponsmith", "minecraft:rotten_flesh",
                 "minecraft:bone", "minecraft:leather_chestplate", "heraldia.tablon.capa", "minecraft:emerald"):
        if want not in d:
            fails.append(f"{style}: the sheriff is missing {want}")
    if d.count("buy: {") != 3:   # maxUses 4 is the default value and is not stored: the "buy" entries are counted
        fails.append(f"{style}: the sheriff has {d.count('buy: {')} trades (must be 3)")
    bx, by, bz = int(a[0] // 1), int(a[1] // 1), int(a[2] // 1)
    lectern = [(bx + ex, by, bz + ez) for ex, ez in ((1, 0), (-1, 0), (0, 1), (0, -1))
               if srv.test(f"execute if block {bx + ex} {by} {bz + ez} minecraft:lectern[has_book=true]")]
    if len(lectern) != 1:
        fails.append(f"{style}: {len(lectern)} lecterns with a book next to the sheriff (must be 1)")
        return
    book = srv.data("data get block %d %d %d Book" % lectern[0])
    pages = [p for p in re.findall(r"heraldia\.tablon\.(p\d)", book)]
    if sorted(set(pages)) != [f"p{i}" for i in range(1, 7)] or "heraldia.tablon.libro" not in book:
        fails.append(f"{style}: the lectern's book does not have its 6 pages: {book[:300]}")
    missing = [k for k in [f"heraldia.tablon.p{i}" for i in range(1, 7)] + ["heraldia.tablon.libro", "entity.heraldia.alguacil"]
               if k not in lang]
    if missing:
        fails.append(f"no en_us text: {missing}")
    print(f"board: sheriff at {bx} {by} {bz}, lectern at {lectern[0]}")


def offers_of(srv, spot, y, floor_bottom, depth, lvl, tagged, vtype="plains"):
    """Summons a villager in the square, the player touches it (its trades are rolled) and returns its Offers."""
    tags = '"heraldia","heraldia_prueba"' if tagged else '"heraldia_prueba"'
    srv.run("kill @e[tag=heraldia_prueba]", r"Killed|No entity was found")
    srv.run(f'summon minecraft:villager {spot[0]} {y} {spot[1]} {{NoAI:1b,PersistenceRequired:1b,Tags:[{tags}],'
            f'VillagerData:{{profession:"minecraft:{depth}",level:{lvl},type:"minecraft:{vtype}"}},Xp:1}}', r"Summoned")
    srv.run(f"tp {PLAYER} {floor_bottom[0]} {y} {floor_bottom[1]}", r"Teleported")
    # tp ... facing points from the feet (the ray would pass above the villager); Carpet looks from the eyes
    s.send(srv.proc, f"player {PLAYER} look at {spot[0]} {y + 1.2} {spot[1]}")
    for _ in range(10):
        s.send(srv.proc, f"player {PLAYER} use once")   # nothing is answered on the console
        time.sleep(0.3)
        d = srv.data("data get entity @e[tag=heraldia_prueba,limit=1] Offers")
        if d:
            return d
    return ""


def check_trades(srv, fails, style, to_world, y, styles, fams, family, enabled=True):
    spot, floor_bottom = to_world(SPOT), to_world(BOT)
    checks = [(depth, lvl, key, tid) for tid, depth, lvl, item, key in styles.get(style, []) if not tid.endswith("/asedio")]
    if enabled and family in fams:
        depth, lvl, key = fams[family]
        checks.append((depth, lvl, key, f"heraldia:familias/{family}/mapa"))
    for depth, lvl, key, tid in checks:
        got = sum(key in offers_of(srv, spot, y, floor_bottom, depth, lvl, True) for _ in range(N))
        if enabled and not got:
            fails.append(f"{tid}: none of {N} Heraldia villagers ({depth}, level {lvl}) in the {style} square offers it")
        if not enabled and got:
            fails.append(f"{tid}: with aldeas.vida.tratos_estilo disabled, {got} of {N} villagers offer it")
        print(f"trade {tid} ({depth} {lvl}): {got} of {N} Heraldia villagers offer it" + ("" if enabled else " (desactivado)"))
        if enabled:
            bad = sum(key in offers_of(srv, spot, y, floor_bottom, depth, lvl, False) for _ in range(N))
            if bad:
                fails.append(f"{tid}: {bad} of {N} villagers without the heraldia tag offer it")
    srv.run("kill @e[tag=heraldia_prueba]", r"Killed|No entity was found")


def check_patrol(srv, fails, to_world, y):
    """Zombie killed by the player: outside the village it does not grant the feat; in the square it does, with 3 emeralds."""
    spot = to_world(SPOT)
    srv.run(f"clear {PLAYER}", r"Removed|No items")
    far = (spot[0] + 600, spot[1])
    srv.run(f"forceload add {int(far[0])} {int(far[1])}", r"Marked|force|already")
    if not srv.until(f"execute if loaded {int(far[0])} 64 {int(far[1])}", attempts=120):   # entidades accesibles
        fails.append("watch: the chunk outside the village never loads")
    for where, (x, z), want in (("fuera", far, False), ("dentro", spot, True)):
        for _ in range(ATTEMPTS):   # the far chunk takes a while to load: "Invalid position" until then
            m = srv.run(f'summon minecraft:zombie {x} {y if want else 200} {z} {{NoAI:1b,PersistenceRequired:1b,'
                        f'Tags:["heraldia_prueba","heraldia_adulto"]}}', r"Summoned")
            if "Summoned" in m.group(0):
                break
            time.sleep(RETRY_S)
        else:
            fails.append(f"watch: could not summon the zombie ({where}) the village")
            continue
        srv.run(f"damage @e[tag=heraldia_prueba,type=minecraft:zombie,limit=1] 2000 minecraft:player_attack by {PLAYER}",
                r"Applied|No entity")
        got = srv.until(f"execute if entity @a[name={PLAYER},advancements={{{ROUND}=true}}]", attempts=10 if not want else ATTEMPTS)
        if got != want:
            fails.append(f"watch: zombie killed ({where}) the village {'does not ' if want else ''}grant the feat")
    m = srv.run(f"clear {PLAYER} minecraft:emerald 0", r"Found (\d+) matching|No items")
    if m.group(1) != "3":
        fails.append(f"watch: the reward leaves {m.group(1) or 0} emeralds in the inventory (must be 3)")
    print(f"watch: feat and {m.group(1) or 0} emeralds")


def check_place_without_board(srv, fails, style, x, z):
    r = 112   # /place requires all the chunks the village covers to be loaded (like village_terrain.py; forceload: <= 256 chunks)
    srv.run(f"forceload add {x - r} {z - r} {x + r} {z + r}", r"Marked|Added|force|already")
    corners = [(x + ex, z + ez) for ex in (-r, r) for ez in (-r, r)] + [(x, z)]
    if not all(srv.until(f"execute if loaded {cx} 64 {cz}", attempts=480) for cx, cz in corners):
        fails.append(f"/place of {style}: the zone never loads")
        return
    for _ in range(s.PLACE_ATTEMPTS):
        m = srv.run(f"place structure heraldia:{style} {x} ~ {z}", r"Generated structure|not loaded(?! yet)")
        if "not loaded" not in m.group(0):
            break
        time.sleep(s.PLACE_RETRY_S)
    if "Generated" not in m.group(0):
        fails.append(f"/place structure heraldia:{style} failed")
        return
    time.sleep(5)
    if not srv.until(f"execute positioned {x} 100 {z} if entity @e[type=minecraft:armor_stand,tag=heraldia_centro,distance=..160]"):
        fails.append(f"/place of {style}: the square does not appear")
    elif srv.test(f"execute positioned {x} 100 {z} if entity @e[tag=heraldia_alguacil,distance=..160]"):
        fails.append(f"/place of {style} with aldeas.vida.tablon disabled: there is a sheriff")
    else:
        print(f"/place of {style} without board: no sheriff")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-vida"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    styles, fams, lang = jar_data(a.jar)
    import trades, themes
    family = {th["id"]: th["family"] for th in themes.THEMES}
    fails = []
    if len(styles) != len(themes.THEMES):
        fails.append(f"{len(styles)} styles with their own trades in the .jar (must be {len(themes.THEMES)})")
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    write_config(a.work, HEALTH_ON)
    srv = Server(a.work, launcher)
    try:
        counts = vanilla_counts(a.work)
        if counts is None:
            print("WARNING: cannot find the game .jar to compare NIVEL_VANILLA")
        else:
            bad = {k: (v, counts.get(k)) for k, v in trades.VANILLA_LEVEL.items() if counts.get(k) != v}
            if bad:
                fails.append(f"tratos.NIVEL_VANILLA does not match the game (written, actual): {bad}")
        found = plaza(srv, fails)
        if found:
            style, to_world, y, sheriff_pos = found
            check_board(srv, fails, style, sheriff_pos, lang)
            srv.run(f"player {PLAYER} spawn at {to_world(BOT)[0]} {y} {to_world(BOT)[1]}", r"joined the game")
            if not srv.until(f"execute if entity @a[name={PLAYER}]"):
                raise SystemExit(f"the simulated player {PLAYER} does not appear (Carpet)")
            srv.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
            t0 = time.monotonic()
            check_trades(srv, fails, style, to_world, y, styles, fams, family[style])
            print(f"tratos sorteados en {time.monotonic() - t0:.1f} s")
            check_patrol(srv, fails, to_world, y)
            srv.run(f"player {PLAYER} kill", r"left the game")
        srv.stop()
        if found:
            write_config(a.work, HEALTH_OFF)
            srv = Server(a.work, launcher)
            srv.run(f"forceload add {int(sheriff_pos[0]) - RADIUS} {int(sheriff_pos[2]) - RADIUS} {int(sheriff_pos[0]) + RADIUS} {int(sheriff_pos[2]) + RADIUS}",
                    r"Marked|Added|force|already")
            srv.run(f"player {PLAYER} spawn at {to_world(BOT)[0]} {y} {to_world(BOT)[1]}", r"joined the game")
            srv.until(f"execute if entity @a[name={PLAYER}]")
            check_trades(srv, fails, style, to_world, y, styles, fams, family[style], enabled=False)
            check_place_without_board(srv, fails, style, int(sheriff_pos[0]) + 400, int(sheriff_pos[2]))
            srv.run(f"player {PLAYER} kill", r"left the game")
    finally:
        srv.stop()
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: board, style trades, feat with reward and disabled options")
    return 0


if __name__ == "__main__":
    sys.exit(main())
