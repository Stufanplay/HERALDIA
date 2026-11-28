"""Heralds' guide on a real 26.3 dedicated server, with simulated players (Carpet, like trophies.py).

Usage: python3 tools/smoke/guide.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Reads from the .jar heraldia/guide.json, the unique structures and the en_us texts, and checks:
  - on first join, the player receives a single book (written_book with the heraldia_guia_libro mark = mod
    version), with the title, the author, its translatable pages with the English fallback (the simulated player's language),
    as many pages as guide.json says for 0 discovered unique structures, and the hint for each unique structure;
  - on leaving and rejoining (and after restarting the server) it is not given another: "already delivered" is stored on the player;
  - /heraldia guide gives an up-to-date copy: with one unique structure discovered (/advancement grant) its name appears in the journal and not
    its hint; when requested again, it replaces the one in the inventory instead of adding another;
  - with guide.entregar_al_entrar = false, a new player does not receive it on joining, but does when requesting it.
Measures how long it takes to assemble and deliver (the "Guía del Heraldo ... entregada a ... en N µs" log line).
"""
import argparse, json, math, os, queue, re, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from terralith_biomes import fetch
from trophies import CARPET

PLAYER, NEW_ITEM = "Testigo", "Aprendiz"
X, Y, Z = 0, 101, 0
DISCOVERED = "castillo"
DELIVERY = re.compile(r"Guía del Heraldo \(([^,]+), ([^)]+)\) entregada a (\w+) en (\d+) µs")


def jar_data(jar):
    with zipfile.ZipFile(jar) as z:
        dataset = json.loads(z.read("heraldia/guia.json"))
        lang = json.loads(z.read("assets/heraldia/lang/en_us.json"))
        pre = "data/heraldia/worldgen/structure/unicas/"
        uniques = sorted(n[len(pre):-5] for n in z.namelist() if n.startswith(pre) and n.endswith(".json"))
    return dataset, lang, uniques


class Server:
    def __init__(self, work, launcher):
        self.proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines, self.seen = queue.Queue(), []
        threading.Thread(target=s.reader, args=(self.proc, lines), daemon=True).start()
        self.ctx = s.Context(self.proc, lines, self.seen)
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, self.seen)

    def stop(self):
        if self.proc.poll() is None:
            s.send(self.proc, "stop")
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def spawn(self, name):
        s.require_carpet(self.ctx)
        self.ctx.run(f"player {name} spawn at {X} {Y} {Z}", r"joined the game|Player .* spawn")
        if not self.ctx.until(f"execute if entity @a[name={name}]"):
            raise SystemExit(f"simulated player {name} (Carpet) does not appear")

    def leave(self, name):
        self.ctx.run(f"player {name} kill", r"left the game")
        self.ctx.until(f"execute if entity @a[name={name}]", want=False)

    def books(self, name, version=None):
        """How many guides it carries (with the `version` mark, or any written book if None)."""
        pred = "minecraft:written_book" + (f'[minecraft:custom_data={{heraldia_guia_libro:"{version}"}}]' if version else "")
        m = self.ctx.run(f"execute if items entity {name} container.* {pred}", r"Test passed\. Count: (\d+)|Test failed")
        return int(m.group(1) or 0)

    def inventory(self, name):
        m = self.ctx.run(f"data get entity {name} Inventory", r"has the following entity data: (.*)|No entity")
        return (m.group(1) or "").replace("\\", "")


def check_book(data, lang, dataset, uniques, discovered, fails, when):
    """Checks the inventory book (SNBT from data get): title, author, pages and journal."""
    n = len(uniques) - len(discovered)
    pages = len(dataset["paginas"]) + 1 + math.ceil(len(discovered) / dataset["nombres_por_pagina"]) + \
        math.ceil(n / dataset["pistas_por_pagina"])
    want = ['id: "minecraft:written_book"', f'author: "{dataset["autor"]}"', lang["heraldia.guia.nombre"],
            '"heraldia.guia.pagina.bienvenida"', lang["heraldia.guia.pagina.bienvenida"][:40], '"heraldia.guia.resumen"']
    want += [f'"heraldia.historia.{sid}.pista"' for sid in uniques if sid not in discovered]
    want += [f'"heraldia.unicas.{sid}.nombre"' for sid in discovered]
    missing = [w for w in want if w not in data]
    if missing:
        fails.append(f"{when}: the book is missing {missing[:5]}: {data[:400]}")
    for sid in discovered:
        if f'"heraldia.historia.{sid}.pista"' in data:
            fails.append(f"{when}: the journal gives the hint for {sid}, which is already discovered")
    titles = {k: len(re.findall(rf'"heraldia\.guia\.{k}"', data)) for k in
              ("pistas", "descubiertas", "resumen.titulo")}
    got = len(dataset["paginas"]) + titles["resumen.titulo"] + titles["descubiertas"] + titles["pistas"]
    if got != pages:
        fails.append(f"{when}: {got} pages ({titles}), should be {pages}")
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-guia"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    dataset, lang, uniques = jar_data(a.jar)
    version = s.gradle_properties()["mod_version"]
    fails, timings = [], []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {X - 3} {Y - 1} {Z - 3} {X + 3} {Y - 1} {Z + 3} minecraft:stone", r"Successfully filled|No blocks|not loaded(?! yet)")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        # 1) first time: a single book, with the whole journal still to discover
        srv.spawn(PLAYER)
        ctx.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
        if not ctx.until(f"execute if items entity {PLAYER} container.* minecraft:written_book"):
            fails.append("on first join it does not receive the guide")
        elif srv.books(PLAYER, version) != 1:
            fails.append(f"on joining it receives {srv.books(PLAYER)} books, not 1 with the version mark {version}")
        else:
            pages = check_book(srv.inventory(PLAYER), lang, dataset, uniques, [], fails, "al entrar")
            print(f"guide on joining: {pages} pages, {len(uniques)} unique structures to discover")
        # 2) rejoin: no other is given
        ctx.run(f"clear {PLAYER} minecraft:written_book", r"Removed|No items")
        srv.leave(PLAYER)
        before = len(DELIVERY.findall("".join(srv.seen)))
        srv.spawn(PLAYER)
        if srv.books(PLAYER) or len(DELIVERY.findall("".join(srv.seen))) != before:
            fails.append("on rejoining it receives another guide")
        # 3) /heraldia guide with one unique structure discovered; requested twice, there is still one
        ctx.run(f"advancement grant {PLAYER} only heraldia:unicas/{DISCOVERED}/descubrir", r"Granted|granted|Couldn't")
        for _ in range(2):
            ctx.run(f"execute as {PLAYER} run heraldia guide", r"entregada a \w+ en \d+ µs")
        if srv.books(PLAYER, version) != 1:
            fails.append(f"after requesting it twice it carries {srv.books(PLAYER)} guides, not 1")
        else:
            check_book(srv.inventory(PLAYER), lang, dataset, uniques, [DISCOVERED], fails, "pedida")
        srv.leave(PLAYER)
    finally:
        srv.stop()
    timings += [int(m.group(4)) for m in DELIVERY.finditer("".join(srv.seen))]
    # 4) after restarting: what was delivered is still saved; with the option disabled, a new player does not receive it on joining
    cfg_path = os.path.join(a.work, "config", "heraldia.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("guia", {}).get("entregar_al_entrar") is not True:
        fails.append(f"config/heraldia.json no trae guia.entregar_al_entrar = true: {cfg.get('guia')}")
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        srv.spawn(PLAYER)
        if srv.books(PLAYER, version) != 1 or DELIVERY.search("".join(srv.seen)):
            fails.append(f"after restarting the server it receives another guide on joining (it was not saved that it already had it): "
                         f"{srv.books(PLAYER)} libros")
        srv.leave(PLAYER)
    finally:
        srv.stop()
    timings += [int(m.group(4)) for m in DELIVERY.finditer("".join(srv.seen))]
    cfg.setdefault("guia", {})["entregar_al_entrar"] = False
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        srv.spawn(NEW_ITEM)
        if srv.books(NEW_ITEM):
            fails.append("with guia.entregar_al_entrar = false, a new player receives it on joining")
        ctx.run(f"execute as {NEW_ITEM} run heraldia guide", r"entregada a \w+ en \d+ µs")
        if srv.books(NEW_ITEM, version) != 1:
            fails.append("with the option disabled, /heraldia guide does not give the guide")
        srv.leave(NEW_ITEM)
    finally:
        srv.stop()
    seen = "".join(srv.seen)
    timings += [int(m.group(4)) for m in DELIVERY.finditer(seen)]
    log = os.path.join(a.work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else seen
    for bad in ("Registry loading errors", "Failed to load datapacks", "Couldn't load", "Failed to parse",
                "Found validation problems"):
        if bad in text:
            fails.append(f"the log contains {bad!r}")
    if timings:
        print(f"guide assembled and delivered {len(timings)} times: {min(timings)}-{max(timings)} µs (median "
              f"{sorted(timings)[len(timings) // 2]} µs)")
    print("GUIDE:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
