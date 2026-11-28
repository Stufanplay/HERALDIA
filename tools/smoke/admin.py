"""Administration tools on a real 26.3 dedicated server with a simulated player (Carpet):
/heraldia review, /heraldia status and /heraldia reload.

Usage: python3 tools/smoke/admin.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
  - review list: all the stops, in order (villages by family without the disabled one, unique structures with Atlantis,
    medium structures, small-medium-large mines, lighthouse and shipwreck, the arena and the road);
  - review goto arena: with no arena placed it says so and does not move the player;
  - review goto unica/atlantida: planned (not generated), warns that going there generates terrain and does not move the player; the
    search runs off the server thread (it is timed);
  - review goto <mediana> (and "generate" if planned): teleport to a safe spot (feet and head free, ground
    below) that matches what the log says;
  - review mark problem <note>, next, skip: progress is saved (heraldia_revision.json and .md in the
    world folder) and survives a restart;
  - status (and its other pages): version, discovered by type, loot replenishment, Lootr and, as operator, the mods;
  - reload: changing difficulty.level from heroic to easy, the already loaded anchored zombie goes from 40 to 15 max
    health without restarting; aldeas.separacion_bloques is listed as pending and /heraldia info keeps the value in use.
"""
import argparse, copy, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch

PLAYER = "Revisor"
X, Y, Z = 0, 120, 0                       # the zombie for the reload test (NoAI: it does not fall)
NUM = r"(-?\d+(?:\.\d+)?)"
TITLE = r"(?:Review|Revisión) (\d+)/(\d+): "
LOG_SEARCH = r"Heraldia: /heraldia review ([a-z_/]+): (.+) en (\d+) ms"
LOG_TP = rf"Heraldia: /heraldia review: {PLAYER} a (-?\d+) (-?\d+) (-?\d+)"
NOTE = "la puerta del patio no abre"


def config(work, **difficulty):
    cfg = copy.deepcopy(s.TEST_CONFIG)
    cfg["dificultad"] = {"nivel": "heroica", **difficulty}
    return cfg


def write(work, cfg):
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-admin"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    write(a.work, config(a.work))
    world = os.path.join(a.work, "world")
    fails, ok = [], 0
    srv = None

    def check(cond, msg):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fails.append(msg)
            print("FAIL:", msg)

    def as_player(cmd):
        return f"execute as {PLAYER} run heraldia review {cmd}"

    def search(ctx, stop):
        """Waits for a stop's search (off the server thread) to finish: (result, ms)."""
        while True:
            m = s.wait_for(ctx.lines, LOG_SEARCH, s.COMMAND_TIMEOUT_S, ctx.seen)
            if m.group(1) == stop:
                return m.group(2), int(m.group(3))

    def pos(ctx):
        return ctx.pos(f"@a[name={PLAYER}]")

    def num(ctx, cmd):
        m = ctx.run(cmd, rf"(?:is|data:) {NUM}f?\b|No entity|[Nn]o modifier|has no|There is no|not found|Can't find")
        return float(m.group(1)) if m.lastindex and m.group(1) else None

    def player(ctx):
        s.require_carpet(ctx)
        ctx.run(f"player {PLAYER} spawn at 0 100 0", r"joined the game|Player .* spawn")
        if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"simulated player {PLAYER} does not appear (Carpet)")

    def arrives(ctx, stop, idx):
        """After going to a stop with a destination: the teleport log, the title and a safe spot (feet and head
        free, ground below, never lava) where the player really is."""
        m = s.wait_for(ctx.lines, LOG_TP + "|" + r"no safe spot|ningún sitio seguro", s.COMMAND_TIMEOUT_S, ctx.seen)
        check(m.lastindex, f"{stop}: no hay sitio seguro: {m.string.strip()}")
        if not m.lastindex:
            return
        x, y, z = (int(v) for v in m.groups()[:3])
        text = "".join(s.drain(ctx))
        t = re.search(TITLE, text)
        check(t and int(t.group(1)) == idx + 1, f"{stop}: título {t and t.group(0)} (debe ser la parada {idx + 1})")
        p = pos(ctx)
        check(p and abs(p[0] - (x + 0.5)) < 0.01 and abs(p[1] - y) < 0.01 and abs(p[2] - (z + 0.5)) < 0.01,
              f"{stop}: el jugador está en {p}, el log dice {x} {y} {z}")
        # in the player's dimension (the Nether and End stops of T44 take it there; from the console the
        # blocks would be read in the Overworld, "That position is not loaded")
        d = ctx.run(f"data get entity {PLAYER} Dimension", r'has the following entity data: "([a-z0-9_:./-]+)"|No entity')
        here = f"execute in {d.group(1) or 'minecraft:overworld'} "
        check(ctx.test(f"{here}if block {x} {y} {z} #minecraft:replaceable")
              and ctx.test(f"{here}if block {x} {y + 1} {z} #minecraft:replaceable"),
              f"{stop}: pies o cabeza dentro de un bloque en {x} {y} {z}")
        check(ctx.test(f"{here}unless block {x} {y - 1} {z} #minecraft:air"), f"{stop}: sin suelo bajo {x} {y} {z}")
        check(ctx.test(f"{here}unless block {x} {y - 1} {z} minecraft:lava"), f"{stop}: encima de lava")
        print(f"{stop}: at {x} {y} {z}")

    try:
        srv = Server(a.work, launcher)
        ctx = srv.ctx
        player(ctx)

        # --- lista: paradas en orden ---
        m = ctx.run(as_player("list"), r"(?:Review route|Ruta de revisión) \((\d+)")
        total = int(m.group(1)) if m.lastindex else 0
        lines = "".join(s.drain(ctx))
        ids = re.findall(r"\d+\. .+? \(([a-z_]+(?:/[a-z_]+)?)\): ", lines)
        print(f"review list: {total} paradas: {ids}")
        check(total > 20 and len(ids) == total, f"lista: {total} paradas, {len(ids)} leídas")
        kinds = [i.split("/")[0] for i in ids]
        order = ["aldea", "unica", "mediana", "mina", "costa", "arena", "camino"]
        check(kinds == sorted(kinds, key=order.index), f"lista: tipos fuera de orden: {kinds}")
        check(set(kinds) == set(order), f"lista: faltan tipos: {set(order) - set(kinds)}")
        check("aldea/pantano" not in ids, "lista: sale la familia pantano, desactivada en la configuración de prueba")
        check("unica/atlantida" in ids and "unica/isla_corsario" in ids, "lista: faltan la Atlántida o la isla")
        check([i for i in ids if i.startswith("mina/")] == ["mina/pequena", "mina/mediana", "mina/grande"], "lista: minas fuera de orden")
        check([i for i in ids if i.startswith("costa/")] == ["costa/faro", "costa/naufragio"], "lista: faro y naufragio fuera de orden")

        # --- the arena, not placed ---
        before = pos(ctx)
        m = ctx.run(as_player("goto arena"), r"has not been placed|no está colocada")
        check(m.lastindex is None and m.group(0) in ("has not been placed", "no está colocada"), f"ir arena: {m.string.strip()}")

        # --- Atlantis: planned, a warning is shown and the player does not move ---
        ctx.run(as_player("goto unica/atlantida"), r"(?:Looking for|Buscando) ")
        res, ms = search(ctx, "unica/atlantida")
        print(f"review goto unica/atlantida: {res} in {ms} ms (off the server thread)")
        text = "".join(s.drain(ctx))
        check("generated=false" in res, f"atlántida: debería estar prevista: {res}")
        check(re.search(r"has not been generated yet|aún no se ha generado", text), "atlántida: no avisa de que se generaría terreno")
        check(re.search(r"Go and generate|Ir y generar", text), "atlántida: falta el botón «Ir y generar»")
        check(re.search(r"(?:What to check|Qué mirar):", text) and re.search(r"water breathing|respiración acuática", text),
              "atlántida: falta la lista de qué mirar (con su punto propio)")
        after = pos(ctx)
        check(before and after and abs(before[0] - after[0]) < 1 and abs(before[2] - after[2]) < 1,
              f"atlántida prevista: el jugador se ha movido de {before} a {after}")

        # --- a medium structure: safe teleport ---
        medium = next(i for i in ids if i.startswith("mediana/"))
        idx = ids.index(medium)
        ctx.run(as_player(f"goto {medium}"), r"(?:Looking for|Buscando) ")
        res, ms = search(ctx, medium)
        print(f"review goto {medium}: {res} en {ms} ms")
        check("Destination" in res, f"{medium}: no se encuentra ninguna: {res}")
        if "generated=false" in res:
            s.drain(ctx)
            ctx.run(as_player(f"goto {medium} generate"), r"(?:Looking for|Buscando) ")
            search(ctx, medium)
        arrives(ctx, medium, idx)

        # --- mark, next and skip ---
        m = ctx.run(as_player(f"mark problem {NOTE}"), r"with a problem|con problema")
        check(m.lastindex is None and NOTE in m.string, f"marcar: {m.string.strip()}")
        for order_, expected in (("next", idx + 2), ("skip", idx + 3)):
            ctx.run(as_player(order_), r"(?:Looking for|Buscando) ")
            search(ctx, ids[expected - 1])
            text = "".join(s.drain(ctx, 3))
            if re.search(r"(?:Loading the area|Cargando la zona)", text) and not re.search(LOG_TP, text):
                s.wait_for(ctx.lines, LOG_TP, s.COMMAND_TIMEOUT_S, ctx.seen)
                text += "".join(s.drain(ctx))
            t = re.search(TITLE, text)
            check(t and int(t.group(1)) == expected, f"{order_}: debería ir a la parada {expected}: {t and t.group(0)}")

        def summary(ctx, when):
            m = ctx.run("heraldia review status", rf"(?:Review by|Revisión de) {PLAYER}: (\d+) \D+ (\d+) \D+, (\d+) \D+, (\d+) \D+, (\d+)")
            check(m.lastindex and (int(m.group(3)), int(m.group(4))) == (1, 1) and int(m.group(2)) == total,
                  f"{when}: resumen {m.group(0) if m else None} (debe tener 1 con problema y 1 saltada de {total})")
            text = "".join(s.drain(ctx))
            check(NOTE in text, f"{when}: el resumen no lista el problema")

        summary(ctx, "review status")
        md, js = os.path.join(world, "heraldia_revision.md"), os.path.join(world, "heraldia_revision.json")
        finish = time.monotonic() + 30
        while time.monotonic() < finish and not (os.path.exists(md) and NOTE in open(md, encoding="utf-8").read()):
            time.sleep(0.5)
        check(os.path.exists(md) and NOTE in open(md, encoding="utf-8").read(), "no se escribe heraldia_revision.md con la nota")
        if os.path.exists(md):
            text = open(md, encoding="utf-8").read()
            check("**problema**" in text and "saltada" in text and f"## {PLAYER}" in text, "heraldia_revision.md incompleto")
            check(text.index(f"`{medium}`") < text.index(f"`{ids[0]}`"), "heraldia_revision.md: el problema no va primero")
        if os.path.exists(js):
            d = json.load(open(js, encoding="utf-8"))
            prog = next(iter(d["jugadores"].values()), {})
            check(prog.get("paradas", {}).get(medium, {}).get("marca") == "problema", f"json: {prog}")
            check(prog.get("actual") == idx + 2, f"json: parada actual {prog.get('actual')} (debe ser {idx + 2})")

        # --- a planned one with "Ir y generar": the terrain is generated and a safe spot is reached ---
        planned = None
        for i in ids[idx + 1:]:
            if not i.startswith("mediana/"):
                break
            ctx.run(as_player(f"goto {i}"), r"(?:Looking for|Buscando) ")
            res, _ = search(ctx, i)
            if "generated=false" in res:
                s.drain(ctx)
                planned = i
                break
            if "generated=true" in res:      # already generated: wait for the teleport (otherwise the next command is "busy")
                s.wait_for(ctx.lines, LOG_TP + "|no safe spot|ningún sitio seguro", s.COMMAND_TIMEOUT_S, ctx.seen)
            s.drain(ctx)
        check(planned, "no hay ninguna mediana prevista para probar «Ir y generar»")
        if planned:
            ctx.run(as_player(f"goto {planned} generate"), r"(?:Looking for|Buscando) ")
            res, ms = search(ctx, planned)
            print(f"review goto {planned} generate: {res} en {ms} ms")
            arrives(ctx, planned, ids.index(planned))

        # --- /heraldia status ---
        m = ctx.run("heraldia status", r"Heraldia (\S+): (?:server status|estado del servidor) \((?:page|página) 1 (?:of|de) (\d+)\)")
        pages = int(m.group(2)) if m.lastindex else 0
        text = "".join(s.drain(ctx))
        check(pages >= 2, f"estado: {m.string.strip()}")
        check(re.search(r"Discovered by some player|Descubiertas por algún jugador", text), "estado: falta lo descubierto")
        check(re.search(r"(?:Unique structures|Estructuras únicas): 0 (?:of|de) \d+", text), "estado: falta el recuento de únicas")
        check(re.search(r"(?:Difficulty|Dificultad): ", text), "estado (operador): falta la dificultad")
        for n in range(2, pages + 1):
            m = ctx.run(f"heraldia status {n}", rf"\((?:page|página) {n} (?:of|de) {pages}\)")
            check(m.lastindex is None and f"{n} " in m.group(0), f"estado {n}: {m.string.strip()}")
            text += "".join(s.drain(ctx))
        m = ctx.run("heraldia status 99", rf"\((?:page|página) {pages} (?:of|de) {pages}\)")
        check(m.lastindex is None and str(pages) in m.group(0), f"estado 99: debería dar la última página: {m.string.strip()}")
        s.drain(ctx)
        check(re.search(r"(?:Guardians defeated|Guardianes vencidos): 0 (?:of|de) \d+", text), "estado: faltan los guardianes")
        check(re.search(r"(?:Restocking loot|Botín que se repone): (?:disabled|desactivado)", text), "estado: falta la reposición")
        check(re.search(r"(?:Other mods|Otros mods) \(\d+\): .*Carpet", text), "estado (operador): no lista Carpet entre los mods")

        # --- /heraldia reload: difficulty without restarting ---
        ctx.run(f"forceload add {X - 16} {Z - 16} {X + 16} {Z + 16}", r"Marked|force|already|[Aa]dded")
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        ctx.run("time set midnight", r"[Tt]ime|[Ss]et")
        ctx.run(f'summon minecraft:zombie {X} {Y} {Z} {{NoAI:1b,PersistenceRequired:1b,Silent:1b,Tags:["heraldia_anclado",'
                f'"heraldia_adulto","p_recarga"],Health:20f,attributes:[{{id:"minecraft:max_health",base:20}}]}}', r"Summoned|Unable")
        zombie = "@e[tag=p_recarga,limit=1]"
        check(ctx.until(f"execute if entity {zombie}"), "no aparece el zombi de la recarga")
        vm = num(ctx, f"attribute {zombie} minecraft:max_health get")
        check(vm is not None and abs(vm - 40) < 1e-3, f"heroica: vida máxima {vm} (debe ser 40)")
        cfg = config(a.work)
        cfg["dificultad"]["nivel"] = "facil"
        cfg["aldeas"]["separacion_bloques"] = 3000
        write(a.work, cfg)
        m = ctx.run("heraldia reload", r"(?:Configuration reloaded from|Configuración recargada de) heraldia\.json")
        text = "".join(s.drain(ctx))
        check(m.lastindex is None and "heraldia.json" in m.group(0), f"recargar: {m.string.strip()}")
        check("dificultad.nivel = facil" in text, "recargar: no lista dificultad.nivel como aplicada")
        check(re.search(r"aldeas\.separacion_bloques: 1500 \S+ \S+, 3000", text), "recargar: no lista aldeas.separacion_bloques como pendiente")
        n = re.search(r"(?:recalculated for|recalculada en) (\d+)", text)
        check(n and int(n.group(1)) >= 1, f"recargar: mobs recalculados {n and n.group(1)}")
        vm = num(ctx, f"attribute {zombie} minecraft:max_health get")
        check(vm is not None and abs(vm - 15) < 1e-3, f"fácil sin reiniciar: vida máxima {vm} (debe ser 15)")
        mod = num(ctx, f"attribute {zombie} minecraft:max_health modifier value get heraldia:dificultad_vida")
        check(mod == -0.25, f"fácil sin reiniciar: modificador {mod} (debe ser -0,25)")
        m = ctx.run("heraldia info", r"(?:Villages: every|Aldeas: cada) (\d+)")
        check(m.lastindex and m.group(1) == "1500", f"recargar aplicó la separación de las aldeas: {m.group(0)}")
        s.drain(ctx)
        m = ctx.run("heraldia reload", r"(?:No option that can be applied live|No ha cambiado ninguna opción)")
        check(m.lastindex is None, f"segunda recarga: {m.string.strip()}")
        s.drain(ctx)

        # --- restart: the review progress is kept ---
        srv.stop()
        srv = Server(a.work, launcher)
        ctx = srv.ctx
        summary(ctx, "tras reiniciar")
        log = ctx.log()
        bad = [l.strip() for l in log.splitlines() if "Exception" in l and "heraldia" in l.lower()]
        check(not bad, f"errores en el log: {bad}")
    finally:
        if srv:
            srv.stop()
    print(f"admin: {ok} comprobaciones bien, {len(fails)} mal")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
