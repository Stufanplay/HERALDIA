"""Arena modes, weekly leaderboard and hall of fame (T41, Java: arena/Fama, Temporada, Semana, Modo) on a real
26.3 dedicated server, with a simulated player (Carpet).

Usage: python3 tools/smoke/arena_modes.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-arena-modos"
First start (new world with the arena disabled, like a world from before with records on the scoreboard):
  1. migration: with the arena disabled the vanilla heraldia_arena scoreboard is created with records (as the
     pre-T41 arena left it); when enabled with /heraldia reload, the best becomes the cooperative record;
  2. /heraldia arena place and confirm: the three hall of fame signs (crimson wood) in their place in the plan, with
     "sin campeón"; one is removed and stone is placed at another (like an arena placed before T41 and an occupied spot);
  3. the bell offers the three modes; short time attack (arena.modos.oleadas_contrarreloj = 2): ends by itself on clearing
     the second wave, records the mark (rank 1 and mode record, announced) and gives no advancement (it asks for 10 waves);
  4. short survival: the next wave starts without a pause; the player falls in the third and their mark (2 waves)
     is recorded;
  5. /heraldia arena leaderboard: each mode with its mark and the migrated record; a week that is not saved fails;
  6. /heraldia arena season reset: closes the week, announces the champions, gives them their advancement, the removed sign comes back,
     the occupied one is not touched and the others show the champion; last week is queried with leaderboard <mode> 1; the
     Guide includes the hall of fame; another time attack for the new week.
Second start (same world, with the reset day changed to today: the reset happened while the server was off):
  the week closes on startup with its champion, the history has both weeks, the migrated record remains, the sign
  shows the champion and the advancements remain.
What the server writes to the console is in English (the dedicated server loads the mod's en_us).
"""
import argparse, datetime, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch
from arena import Test, blueprint, rel, wait_count, ARENA

P = "Testigo"
DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
TWO_AGO = DAYS[(datetime.date.today() - datetime.timedelta(days=2)).weekday()]
TODAY = DAYS[datetime.date.today().weekday()]
SIGN = r"has the following block data: (.*)|is not a block entity|Found no elements|not a block"


def config(work, switched_on, day):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False, "activado": switched_on,
                    "modos": {"oleadas_contrarreloj": 2},
                    "temporada": {"dia_reinicio": day, "hora_reinicio": 0, "historico": 3}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-arena-modos"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    pl = blueprint(a.jar)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    config(a.work, False, TWO_AGO)
    fails, texts, box = [], [], None
    srv = Server(a.work, launcher)
    try:
        box = first_start(Test(srv.ctx, fails), pl, a.work)
    finally:
        srv.stop()
        texts.append(srv.ctx.log())
    if box:
        config(a.work, True, TODAY)              # the reset day becomes today: the reset "happened" while the server was off
        srv = Server(a.work, launcher)
        try:
            second_start(Test(srv.ctx, fails), pl, box)
        finally:
            srv.stop()
            texts.append(srv.ctx.log())
    for bad in ("Registry loading errors", "Failed to load datapacks", "at io.github.albertosa23", "arena: mob "):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    print("ARENA MODOS:", "OK" if not fails else fails)
    return 1 if fails else 0


def sign(ctx, pos, line):
    """The text (SNBT) of line `line` (0-3) of the sign at `pos`, or None if it is not a sign."""
    m = ctx.run(f"data get block {pos[0]} {pos[1]} {pos[2]} front_text.messages[{line}]", SIGN)
    return m.group(1) if m.lastindex and m.group(1) else None


def clean_up(p, n, times, timeout=180):
    """Kills (in the player's name) the enemies of wave n until it is cleared for the `times`-th time in the log."""
    ctx = p.ctx
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if p.times(rf"arena: oleada {n} superada") >= times:
            return True
        if ctx.count(ARENA):
            ctx.run(f"damage {ARENA[:-1]},limit=1,sort=random] 1000 minecraft:player_attack by {P}", r"Applied|damage|No entity")
        else:
            ctx.ticks(5)
    p.check(False, f"no se supera la oleada {n} (vez {times})")
    return False


def hour(log, pattern, times=1):
    """Seconds of the day of the `times`-th log line with `pattern` ([HH:MM:SS] at its start), or None."""
    ls = [l for l in log.splitlines() if re.search(pattern, l)]
    if len(ls) < times:
        return None
    m = re.match(r"\[(\d+):(\d+):(\d+)", ls[times - 1])
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def begin(p, mode, in_ring):
    ctx = p.ctx
    ctx.run(f"tp {P} {in_ring[0] + 0.5} {in_ring[1]} {in_ring[2] + 0.5}", r"Teleported")
    ctx.run(f"effect give {P} minecraft:resistance infinite 255 true", r"Applied effect|Gave|Unable to apply")
    ctx.run(f"execute as {P} run heraldia arena start {mode}", r"Prepárate|Get ready")
    return p.wait_log(rf"arena: cuenta atrás \(la empieza {P}, modo {mode}", timeout=60)


MENU = rf"Heraldia: choice: {P} sees arena as (\w+) \(session (\d+): ([\w, ]*)\)"


def menu_choice(p, work, center, bell):
    """The bell's mode menu as a client without Heraldia gets it (a Carpet bot: no channel), see choice/Choices: a
    container menu with one slot per mode (2-row window: modes at 11, 13 and 15). Replies a modified client could send are
    refused (an earlier session, a mode that is not on offer); a mode disabled with /heraldia reload after the menu
    opened is refused when clicked; the click on time attack starts it. The player's inventory does not change."""
    ctx = p.ctx
    m = p.wait_log(MENU, timeout=30)
    if not p.check(m is not None and m.group(1) == "menu", f"la campana no abre el menú de contenedor ({m.group(0) if m else 'nada'})"):
        return False
    session, ids = int(m.group(2)), m.group(3).split(", ")
    p.check(ids == ["coop", "timeattack", "survival"], f"el menú ofrece {ids}")
    before = ctx.run(f"data get entity {P} Inventory", r"has the following entity data: (.*)|Found no elements").group(0)
    ctx.run(f"tp {P} {center[0] + 0.5} {center[1]} {center[2] + 0.5}", r"Teleported")      # in the ring, as begin() does
    for sess, opt in ((session - 1, "coop"), (session, "reward"), (session + 1, "coop")):
        r = ctx.run(f"execute as {P} run heraldia choice reply {sess} {opt}", r"choice reply (accepted|refused)")
        p.check(r.group(1) == "refused", f"menú de la arena: se acepta la respuesta {sess} {opt}")
    # survival disabled while the menu is open: it is still in the window, but picking it is refused
    cfg = json.load(open(os.path.join(work, "config", "heraldia.json")))
    cfg["arena"]["modos"]["supervivencia"] = False
    json.dump(cfg, open(os.path.join(work, "config", "heraldia.json"), "w"))
    ctx.run("heraldia reload", r"Configuration reloaded|Configuración recargada")
    ctx.run(f"execute as {P} run heraldia choice click 15", r"choice click: slot")
    p.check(p.wait_log(rf"arena: {P} elige survival en el menú: rechazado", timeout=10), "se acepta un modo desactivado")
    p.check(not re.search(r"arena: cuenta atrás", ctx.log()), "un modo desactivado empieza una partida")
    cfg["arena"]["modos"].pop("supervivencia")
    json.dump(cfg, open(os.path.join(work, "config", "heraldia.json"), "w"))
    ctx.run("heraldia reload", r"Configuration reloaded|Configuración recargada")
    # the refusal closed nothing it should not: the bell again (a new menu), and time attack picked with a click
    p.check("choice: none (no window" in ctx.run(f"execute as {P} run heraldia choice", r"choice: [^\n]*").group(0),
            "el menú de la arena sigue abierto tras rechazar un modo")
    ctx.run(f"tp {P} {bell[0] + 0.5} {bell[1]} {bell[2] - 1.5}", r"Teleported")      # the bell again: a new menu
    s.send(ctx.proc, f"player {P} look at {bell[0] + 0.5} {bell[1] + 0.4} {bell[2] + 0.5}")
    ctx.ticks(5)
    s.send(ctx.proc, f"player {P} use once")
    m = p.wait_log(MENU.replace("(\\d+)", f"({session + 1}|{session + 2}|{session + 3})", 1), timeout=10)
    if not p.check(m is not None, "sin menú de la arena por segunda vez"):
        return False
    ctx.run(f"tp {P} {center[0] + 0.5} {center[1]} {center[2] + 0.5}", r"Teleported")
    ctx.run(f"execute as {P} run heraldia choice click 13", r"choice click: slot")
    ok = p.wait_log(rf"arena: cuenta atrás \(la empieza {P}, modo timeattack, 2 oleadas\)", timeout=30)
    after = ctx.run(f"data get entity {P} Inventory", r"has the following entity data: (.*)|Found no elements").group(0)
    p.check(after == before, "el menú de la arena cambia el inventario")
    return ok is not None


def first_start(p, pl, work):
    ctx = p.ctx
    # 1. migration of the pre-T41 vanilla scoreboard
    p.check(p.wait_log(r"arena: desactivada", timeout=60), "la arena no arranca desactivada")
    ctx.run("scoreboard objectives add heraldia_arena dummy", r"Created new objective|already exists")
    for name, n in (("Veterano", 7), ("Otra", 3), ("-servidor-", 7)):
        ctx.run(f"scoreboard players set {name} heraldia_arena {n}", r"Set \[heraldia_arena\]|Set score")
    config(work, True, TWO_AGO)
    ctx.run("heraldia reload", r"Configuration reloaded|Configuración recargada")
    p.check(p.wait_log(r"arena: récords migrados del marcador \(3 jugadores; cooperativo: Veterano 7\)", timeout=60),
            "no se migra el récord del marcador vanilla")
    for rule in ("spawn_mobs", "advance_time"):
        ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
    ctx.run("difficulty normal", r"difficulty|Difficulty")
    # 2. the arena with its signs
    ctx.run("heraldia arena place", r"arena: sitio propuesto en")
    ctx.run("heraldia arena place confirm", r"Colocando la arena en|Building the arena at")
    m = p.wait_log(r"arena: colocada en (-?\d+) (-?\d+) (-?\d+) \(caja (-?\d+) (-?\d+) (-?\d+) a (-?\d+) (-?\d+) (-?\d+)\)")
    if not p.check(m, "no se coloca la arena"):
        return None
    box = tuple(int(g) for g in m.groups())[3:]
    minx, miny, minz, maxx, maxy, maxz = box
    ctx.run(f"forceload add {minx - 16} {minz - 16} {maxx + 16} {maxz + 16}", r"Marked|force|already")
    fame = [tuple(box[i] + f[i] for i in range(3)) for f in pl["fama"]]
    p.check(len(fame) == 3, f"el plano trae {len(fame)} carteles del salón de la fama")
    p.check(p.wait_log(r"arena: carteles del salón de la fama al día \(0 campeones\)"), "no se escriben los carteles")
    for f in fame:
        p.check(ctx.block(f, "minecraft:crimson_sign"), f"no hay cartel del salón de la fama en {f}")
    p.check("heraldia.arena.cartel.nadie" in (sign(ctx, fame[0], 2) or ""), "el cartel no dice «sin campeón»")
    p.check("heraldia.arena.modo.coop" in (sign(ctx, fame[0], 1) or ""), "el primer cartel no es el del cooperativo")
    p.check("heraldia.arena.modo.timeattack" in (sign(ctx, fame[1], 1) or ""), "el segundo cartel no es el del contrarreloj")
    # like a pre-T41 arena (without its sign) and an occupied spot
    ctx.run(f"setblock {fame[0][0]} {fame[0][1]} {fame[0][2]} minecraft:air", r"Changed the block")
    ctx.run(f"setblock {fame[2][0]} {fame[2][1]} {fame[2][2]} minecraft:stone", r"Changed the block")
    m = ctx.run("heraldia arena leaderboard", r"Arena leaderboard, week of ([\d/]+) \(current\)|Clasificación de la arena")
    p.check(p.wait_log(r"Record: Veterano, wave 7"), "la clasificación no enseña el récord migrado")
    p.check(p.wait_log(r"No results yet"), "la clasificación vacía no lo dice")

    # 3. short time attack: the bell offers the modes
    reap, bell = rel(box, pl, "reaparicion"), rel(box, pl, "campana")
    s.require_carpet(ctx)
    ctx.run(f"player {P} spawn at {reap[0] + 0.5} {reap[1]} {reap[2] + 0.5}", r"joined the game|Player .* spawn")
    if not ctx.until(f"execute if entity @a[name={P}]"):
        raise SystemExit(f"simulated player {P} does not appear (Carpet)")
    ctx.run(f"gamemode survival {P}", r"Set .* game mode|game mode")
    ctx.run(f"tp {P} {bell[0] + 0.5} {bell[1]} {bell[2] - 1.5}", r"Teleported")
    s.send(ctx.proc, f"player {P} look at {bell[0] + 0.5} {bell[1] + 0.4} {bell[2] + 0.5}")
    ctx.ticks(5)
    s.send(ctx.proc, f"player {P} use once")
    p.check(p.wait_log(rf"arena: {P} elige modo \(coop, timeattack, survival\)", timeout=60), "la campana no ofrece los modos")
    p.check(not re.search(r"arena: cuenta atrás", ctx.log()), "la campana empieza una partida sin elegir modo")
    center = (box[0] + pl["centro"][0], box[1] + pl["centro"][1], box[2] + pl["centro"][2] - 3)
    if not p.check(menu_choice(p, work, center, bell), "no empieza el contrarreloj de 2 oleadas desde el menú de la campana"):
        return box
    door = tuple(box[i] + pl["puerta"][0][i] for i in range(3))
    p.check(p.wait_log(r"partida empieza con 1 participantes \(modo timeattack\)"), "el contrarreloj no empieza con el jugador")
    clean_up(p, 1, 1)
    p.check(p.wait_log(r"arena: oleada 2: 6 enemigos", timeout=60), "el contrarreloj no pasa a la oleada 2")
    clean_up(p, 2, 1)
    m = p.wait_log(r"arena: contrarreloj completado: 2 oleadas en (\d+) ticks")
    p.check(m, "el contrarreloj no se completa tras la última oleada")
    p.check(p.wait_log(r"partida terminada \(contrarreloj completado\) con 2 oleadas superadas \(modo timeattack"),
            "el contrarreloj no acaba solo")
    p.check(p.wait_log(rf"arena: marca de {P} en timeattack: 2 oleadas en \d+ ticks \(puesto 1 de la semana, récord\)"),
            "sin marca del contrarreloj")
    p.check(p.wait_log(r"has set a new arena record in Time attack|bate el récord de la arena en Contrarreloj"),
            "sin anuncio del récord del contrarreloj")
    p.check(not p.times(r"arena: oleada 3:"), "el contrarreloj sigue tras su última oleada")
    p.check(ctx.until(f"execute if entity {ARENA}", want=False, timeout=30), "quedan mobs tras el contrarreloj")
    p.check(ctx.block(door, "minecraft:air"), "la puerta no se abre tras el contrarreloj")
    p.check(ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:arena/contrarreloj=false}}]"),
            "un contrarreloj de 2 oleadas da el logro (pide 10)")

    # 4. short survival: no pause between waves; it falls in the third
    if not p.check(begin(p, "survival", center), "no empieza la supervivencia"):
        return box
    p.check(p.wait_times(r"arena: oleada 1: 4 enemigos", 2, timeout=60), "la supervivencia no empieza")
    clean_up(p, 1, 2)
    p.check(p.wait_times(r"arena: oleada 2: 6 enemigos", 2, timeout=60), "la supervivencia no pasa a la oleada 2")
    clean_up(p, 2, 2)
    p.check(p.wait_log(r"arena: oleada 3: \d+ enemigos", timeout=60), "la supervivencia no pasa a la oleada 3")
    log = ctx.log()
    t0, t1 = hour(log, r"arena: oleada 1 superada", 2), hour(log, r"arena: oleada 2: 6 enemigos", 2)
    p.check(t0 is not None and t1 is not None and 0 <= t1 - t0 <= 3,
            f"supervivencia: la oleada 2 no empieza sin pausa ({t0} -> {t1}; el cooperativo espera 10 s)")
    ctx.run(f"effect clear {P}", r"Removed|effect")
    ctx.run(f"damage {P} 1000 minecraft:generic", r"Applied|damage")
    p.check(p.wait_log(r"partida terminada \(sin participantes\) con 2 oleadas superadas \(modo survival", timeout=60),
            "la supervivencia no acaba al caer el jugador")
    p.check(p.wait_log(rf"arena: marca de {P} en survival: 2 oleadas en \d+ ticks \(puesto 1"), "sin marca de la supervivencia")
    ctx.until(f"execute if entity @a[name={P}]", want=False, timeout=30)
    s.require_carpet(ctx)
    ctx.run(f"player {P} spawn at {reap[0] + 0.5} {reap[1]} {reap[2] + 0.5}", r"joined the game|Player .* spawn")
    ctx.until(f"execute if entity @a[name={P}]")

    # 5. the leaderboard
    before = len(ctx.log())
    ctx.run("heraldia arena leaderboard timeattack", r"Arena leaderboard, week of")
    ctx.run("heraldia arena leaderboard survival", r"Arena leaderboard, week of")
    ctx.ticks(5)
    new_item = ctx.log()[before:]
    p.check(re.search(rf"1\. {P}: \d+:\d\d \(2 waves\)", new_item), "la clasificación del contrarreloj no da el tiempo")
    p.check(re.search(rf"1\. {P}: wave 2", new_item), "la clasificación de la supervivencia no da la oleada")
    p.check(re.search(rf"Record: {P}, wave 2", new_item), "sin el récord de la supervivencia")
    # the refusal is the expected reply: no week has been archived yet
    ctx.run("heraldia arena leaderboard coop 1", r"That week is not kept: the history has 0|No se guarda esa semana")

    # 6. reinicio de semana forzado
    ctx.run("heraldia arena season reset", r"Arena week of .* closed by hand|cerrada a mano")
    p.check(p.wait_log(rf"arena: semana del [\d/]+ cerrada; campeones: timeattack={P}, survival={P}"),
            "el reinicio no cierra la semana con sus campeones")
    p.check(p.wait_log(rf"(?:Time attack|Contrarreloj) champion: {P}|Campeón de Contrarreloj: {P}"), "sin anuncio de los campeones")
    for advancement in ("campeon_timeattack", "campeon_survival"):
        p.check(p.wait_log(rf"arena: logro arena/{advancement} para {P}"), f"sin el logro {advancement}")
        p.check(ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:arena/{advancement}=true}}]"), f"no tiene {advancement}")
    p.check(ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:arena/campeon_coop=false}}]"),
            "tiene el logro del cooperativo sin haberlo ganado")
    p.check(p.wait_log(r"arena: cartel del salón de la fama puesto en"), "no vuelve el cartel quitado")
    p.check(ctx.block(fame[0], "minecraft:crimson_sign"), "no vuelve el cartel quitado (bloque)")
    p.check(p.wait_log(r"el sitio del cartel del salón de la fama \(.*\) está ocupado: no se toca"), "no avisa del sitio ocupado")
    p.check(ctx.block(fame[2], "minecraft:stone"), "el cartel pisa lo que ocupaba su sitio")
    p.check(P in (sign(ctx, fame[1], 2) or ""), "el cartel del contrarreloj no dice el campeón")
    p.check("heraldia.arena.cartel.nadie" in (sign(ctx, fame[0], 2) or ""), "el cartel del cooperativo no dice «sin campeón»")
    before = len(ctx.log())
    ctx.run("heraldia arena leaderboard timeattack 1", r"Arena leaderboard, week of")
    ctx.run("heraldia arena leaderboard timeattack", r"Arena leaderboard, week of")
    ctx.ticks(5)
    new_item = ctx.log()[before:]
    p.check(re.search(rf"1\. {P}: \d+:\d\d", new_item) and "No results yet" in new_item,
            "la semana cerrada no tiene la marca o la nueva no está vacía")
    # the Guide with the hall of fame
    ctx.run(f"execute as {P} run heraldia guide", r"Guide|Guía|guide")
    inv = ctx.run(f"data get entity {P} Inventory", r"has the following entity data: (.*)|No entity").group(1) or ""
    p.check("heraldia.guia.fama.titulo" in inv and "heraldia.guia.fama.semana" in inv and P in inv,
            "la Guía no trae el salón de la fama con el campeón")
    # another time attack for the new week (the one the second start will close)
    if p.check(begin(p, "timeattack", center), "no empieza el segundo contrarreloj"):
        p.check(p.wait_times(r"arena: oleada 1: 4 enemigos", 3, timeout=60), "el segundo contrarreloj no empieza")
        clean_up(p, 1, 3)
        clean_up(p, 2, 3)
        p.check(p.wait_times(rf"arena: marca de {P} en timeattack: 2 oleadas en \d+ ticks \(puesto 1 de la semana", 2),
                "sin marca del segundo contrarreloj")
    ctx.run("heraldia arena season", r"Arena week of .*next reset|Semana de la arena del")
    ctx.run("save-all flush", r"Saved the game")
    return box


def second_start(p, pl, box):
    ctx = p.ctx
    p.check(p.wait_log(r"arena: en (-?\d+) (-?\d+) (-?\d+)", timeout=60), "tras reiniciar no se recuerda la arena")
    p.check(p.wait_log(rf"arena: semana del [\d/]+ cerrada; campeones: timeattack={P}", timeout=60),
            "el reinicio que pasó con el servidor apagado no cierra la semana al arrancar")
    p.check(not re.search(r"récords migrados", ctx.log()), "la migración se repite")
    # the refusal is the expected reply: only two weeks are kept
    ctx.run("heraldia arena leaderboard coop 3", r"That week is not kept: the history has 2|No se guarda esa semana")
    before = len(ctx.log())
    ctx.run("heraldia arena leaderboard timeattack 2", r"Arena leaderboard, week of")
    ctx.run("heraldia arena leaderboard coop", r"Arena leaderboard, week of")
    ctx.ticks(5)
    new_item = ctx.log()[before:]
    p.check(re.search(rf"1\. {P}: \d+:\d\d", new_item), "tras reiniciar no se guarda la primera semana")
    p.check("Record: Veterano, wave 7" in new_item, "tras reiniciar no sigue el récord migrado")
    fame = [tuple(box[i] + f[i] for i in range(3)) for f in pl["fama"]]
    ctx.run(f"forceload add {fame[1][0]} {fame[1][2]}", r"Marked|force|already")
    p.check(ctx.until(f"execute if block {fame[1][0]} {fame[1][1]} {fame[1][2]} minecraft:crimson_sign", timeout=60),
            "tras reiniciar no está el cartel")
    ok = False
    for _ in range(90):                           # the signs are updated when their chunk is loaded (every minute)
        if P in (sign(ctx, fame[1], 2) or ""):
            ok = True
            break
        ctx.ticks(20)
    p.check(ok, "tras reiniciar el cartel del contrarreloj no dice el campeón")
    reap = rel(box, pl, "reaparicion")
    s.require_carpet(ctx)
    ctx.run(f"player {P} spawn at {reap[0] + 0.5} {reap[1]} {reap[2] + 0.5}", r"joined the game|Player .* spawn")
    if ctx.until(f"execute if entity @a[name={P}]"):
        p.check(ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:arena/campeon_timeattack=true}}]"),
                "tras reiniciar no conserva el logro de campeón")


if __name__ == "__main__":
    sys.exit(main())
