"""Wave arena (T31, Java: arena/) on a real 26.3 dedicated server, with a simulated player (Carpet).

Usage: python3 tools/smoke/arena.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-arena"
First start (new world, with arena.generar_en_mundos_nuevos):
  1. the arena generates by itself 200-300 blocks from spawn; /heraldia arena remove (with confirmation) removes it; confirming
     without a proposal fails; /heraldia arena place proposes the site and "place confirm" places it (the bell, the open
     door and the glass, where arena.json says); "place" again says there is already one;
  2. protection: the simulated player (creative, not an operator) cannot break a block or place stone; as an operator it
     can break; TNT inside breaks nothing (and outside it does); a piston does not push its wall (and another outside does); a dispenser
     next to the arena does not empty its lava bucket (it drops it as an item) and another far away does;
  3. game: the player (survival, resistance 255) rings the bell (T41: it offers the modes and the
     cooperative one is chosen with /heraldia arena start coop on its behalf): countdown, door closed, wave 1 with 4
     enemies without a wave modifier and wave 2 with 6 and +10 % health (heraldia:arena_vida 0.1); it kills them
     (/damage ... by the player): they drop no items and give 15 % of the vanilla experience (log of each wave);
     in wave 5, the mini-boss (heraldia_guardian) changes phase and its reinforcements join the wave; on clearing it, record
     on the scoreboard, reward and advancement heraldia:arena/oleada_5;
  4. death in the ring (damage during the pause): it drops no items or experience, its saved data keeps the
     diamonds and the levels (Carpet disconnects the simulated player on death: the vanilla respawn, COPY_FROM and the
     teleport to the entrance cannot be tested here) and the game ends (no mobs, door open);
  What the server writes to the console is in English (the dedicated server loads the mod's en_us).
  5. another game (/heraldia arena start) with live mobs and the door closed; it saves and the process is killed (like a
     hard shutdown).
Second start (same world): the arena's mobs are removed on load, the door is open and there is no game.
The Herald's House (herald/) is folded into this test (same world, same simulated player): after the arena's game, an
operator places it from the console in this world, which is no longer new (/heraldia herald place, then confirm); it does
not step on the arena; its bell, portal frame and stalls are where casa_heraldo.json says; the player who is not an
operator cannot break or place a block, nor light the portal with flint and steel (an operator can); with the market on
(entry 2, rent 1 per day, no grace) the player claims stall 1 for 3 emeralds, a chest with diamonds is left in it,
the rent runs out (tick sprint) and the lazy check reclaims it: the diamonds and the chest end up in a return barrel
and the stall is free. A player dropped from 3 blocks onto the house's farmland does not trample it (onto farmland far
away, it does). On the second start the house is remembered. Not checked here: no monster spawning in the area (natural
spawning does not come back in this world once the test has turned it off; see LESSONS).
"""
import argparse, json, math, os, re, shutil, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch

P = "Testigo"
ARENA = "@e[tag=heraldia_arena]"
NUM = r"(-?\d+(?:\.\d+)?)"


def blueprint(jar):
    with zipfile.ZipFile(jar) as z:
        return json.loads(z.read("heraldia/arena.json"))


def config(work):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": True}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False,
                           "mercado": {"activado": True, "entrada_esmeraldas": 2, "alquiler_esmeraldas": 1,
                                       "periodo_dias": 1, "gracia_dias": 0}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


class Test:
    def __init__(self, ctx, fails):
        self.ctx, self.fails = ctx, fails

    def check(self, ok, msg):
        if not ok:
            self.fails.append(msg)
            print("FAIL:", msg)
        return ok

    def wait_log(self, pattern, timeout=120):
        """The first match of `pattern` in the log (reads what arrives using cheap commands), or None."""
        end = time.monotonic() + timeout
        while True:
            m = re.search(pattern, self.ctx.log())
            if m:
                return m
            if time.monotonic() > end:
                return None
            self.ctx.run("time query gametime", r"[Tt]ime is \d+")
            time.sleep(0.5)

    def times(self, pattern):
        return len(re.findall(pattern, self.ctx.log()))

    def wait_times(self, pattern, n, timeout=120):
        """Does `pattern` appear at least n times in the log before `timeout` seconds?"""
        end = time.monotonic() + timeout
        while self.times(pattern) < n:
            if time.monotonic() > end:
                return False
            self.ctx.run("time query gametime", r"[Tt]ime is \d+")
            time.sleep(0.5)
        return True

    def num(self, cmd):
        m = self.ctx.run(cmd, rf"(?:is|has|data:) {NUM}f?\b|No entity|[Nn]o modifier|has no|There is no|not found|Can't find|"
                              r"Can't get|none is set")
        return float(m.group(1)) if m.lastindex and m.group(1) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-arena"))
    ap.add_argument("--settle", action="store_true",
                    help="after placing the Herald's House, run three in-game days and count who holds a bed, a "
                         "workstation and a meeting point (slow; not in CI)")
    a = ap.parse_args()
    global SETTLE
    SETTLE = a.settle
    os.makedirs(a.work, exist_ok=True)
    pl = blueprint(a.jar)
    with zipfile.ZipFile(a.jar) as z:
        hp = json.loads(z.read("heraldia/casa_heraldo.json"))
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    config(a.work)
    fails, texts = [], []
    srv = Server(a.work, launcher)
    try:
        box = first_start(Test(srv.ctx, fails), pl)
        if box:
            herald_house(Test(srv.ctx, fails), hp, box)
        # 5. a game in progress: it saves and the process is killed
        if box:
            half_done(Test(srv.ctx, fails), pl, box)
        srv.proc.kill()
        srv.proc.wait(timeout=60)
    finally:
        srv.stop()
        texts.append(srv.ctx.log())
    if box:
        srv = Server(a.work, launcher)
        try:
            second_start(Test(srv.ctx, fails), pl, box)
            Test(srv.ctx, fails).check(Test(srv.ctx, fails).wait_log(r"herald's house: at -?\d+", timeout=60),
                                       "after restarting, the Herald's House is not remembered")
        finally:
            srv.stop()
            texts.append(srv.ctx.log())
    for bad in ("Registry loading errors", "Failed to load datapacks", "at io.github.albertosa23", "arena: mob ", "falta la plantilla"):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    print("ARENA:", "OK" if not fails else fails)
    return 1 if fails else 0


def rel(box, pl, key):
    o = box[:3]
    return tuple(o[i] + pl[key][i] for i in range(3))


def first_start(p, pl):
    ctx = p.ctx
    # 1. generated by itself in a new world, 200-300 blocks from spawn
    m = p.wait_log(r"arena: sitio propuesto en (-?\d+) (-?\d+) (-?\d+) \(a (\d+) bloques del spawn")
    if not p.check(m, "mundo nuevo: no se busca sitio para la arena"):
        return None
    p.check(200 <= int(m.group(4)) <= 300, f"arena a {m.group(4)} bloques del spawn (200-300)")
    m = p.wait_log(r"arena: colocada en (-?\d+) (-?\d+) (-?\d+) \(caja (-?\d+) (-?\d+) (-?\d+) a (-?\d+) (-?\d+) (-?\d+)\)")
    if not p.check(m, "mundo nuevo: la arena no se coloca sola"):
        return None
    alone = tuple(int(g) for g in m.groups())
    for rule in ("spawn_mobs", "advance_time"):
        ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
    ctx.run("difficulty normal", r"difficulty|Difficulty")
    # remove, with confirmation
    ctx.run("heraldia arena remove", r"Se quitará la arena|will be removed")
    ctx.run("heraldia arena remove confirm", r"arena: quitada de|arena: obra terminada")
    p.check(p.wait_log(r"arena: quitada de"), "no se quita la arena")
    ctx.run("heraldia arena place confirm", r"Primero pide un sitio|First ask for a site")
    # place: proposal and confirmation
    m = ctx.run("heraldia arena place", r"arena: sitio propuesto en (-?\d+) (-?\d+) (-?\d+) \(a (\d+) bloques")
    p.check(200 <= int(m.group(4)) <= 300, f"propuesta a {m.group(4)} bloques del spawn")
    ctx.run("heraldia arena place confirm", r"Colocando la arena en|Building the arena at")
    if not p.check(p.wait_times(r"arena: colocada en", 2), "«place confirm» no coloca la arena"):
        return None
    box = alone[3:]
    p.check(re.findall(r"arena: colocada en .*\(caja ([-\d ]+) a", ctx.log())[-1].split() == [str(c) for c in box[:3]],
            "la arena colocada a mano no está donde la generada (la búsqueda es determinista)")
    ctx.run("heraldia arena place", r"Ya hay una arena en|There is already an arena")
    minx, miny, minz, maxx, maxy, maxz = box
    ctx.run(f"forceload add {minx - 16} {minz - 16} {maxx + 16} {maxz + 16}", r"Marked|force|already")
    bell, reap = rel(box, pl, "campana"), rel(box, pl, "reaparicion")
    p.check(ctx.block(bell, "minecraft:bell"), f"sin campana en {bell}")
    door = tuple(box[i] + pl["puerta"][0][i] for i in range(3))
    p.check(ctx.block(door, "minecraft:air"), "la puerta no está abierta")
    cx, cz = box[0] + pl["centro"][0], box[2] + pl["centro"][2]
    p.check(ctx.block((cx + 15, miny + 6, cz), "minecraft:glass"), "sin cristal sobre el muro del ruedo")
    p.check(ctx.block((cx, miny + 11, cz), "minecraft:barrier"), "sin techo de barreras sobre el ruedo")
    ctx.run("heraldia arena", r"Arena de oleadas en|Wave arena at")

    # 2. protection
    ctx.run(f"player {P} spawn at {reap[0] + 0.5} {reap[1]} {reap[2] + 0.5}", r"joined the game|Player .* spawn|Unknown|Incorrect")
    if not ctx.until(f"execute if entity @a[name={P}]"):
        raise SystemExit(f"simulated player {P} does not appear (Carpet)")
    ctx.run(f"gamemode survival {P}", r"Set .* game mode|game mode")
    ctx.run(f"gamemode creative {P}", r"Set .* game mode|game mode")
    floor = (reap[0], reap[1] - 1, reap[2] + 1)
    state = "minecraft:polished_andesite"
    p.check(ctx.block(floor, state), f"no hay {state} en {floor} (plano de la arena)")
    s.send(ctx.proc, f"player {P} look at {floor[0] + 0.5} {floor[1] + 1} {floor[2] + 0.5}")
    ctx.ticks(5)
    smash(ctx)
    p.check(ctx.block(floor, state), "un jugador que no es operador rompe un bloque de la arena")
    ctx.run(f"item replace entity {P} weapon.mainhand with minecraft:stone", r"Replaced|replaced")
    s.send(ctx.proc, f"player {P} use once")
    ctx.ticks(10)
    p.check(ctx.block((floor[0], floor[1] + 1, floor[2]), "minecraft:air"), "un jugador que no es operador coloca un bloque")
    ctx.run(f"item replace entity {P} weapon.mainhand with minecraft:air", r"Replaced|replaced")
    ctx.run(f"op {P}", r"Made .* operator|already|Nothing changed")
    smash(ctx)
    p.check(ctx.block(floor, "minecraft:air"), "un operador no puede romper un bloque de la arena")
    ctx.run(f"deop {P}", r"no longer|Nothing changed|not an operator")
    ctx.run(f"setblock {' '.join(map(str, floor))} {state}", r"Changed the block|Could not set")
    # explosion inside (on the walkway, to the north) and outside (control)
    tx, ty, tz = cx, miny + pl["suelo"] + 1, minz + 3
    neighbors = [(tx + dx, ty - 1, tz + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
    ctx.run(f"summon minecraft:tnt {tx} {ty} {tz} {{fuse:1}}", r"Summoned")
    fx, fy, fz = maxx + 20, miny + pl["suelo"] + 6, cz
    ctx.run(f"fill {fx - 2} {fy - 1} {fz - 2} {fx + 2} {fy + 3} {fz + 2} minecraft:air", r"Successfully filled|No blocks")
    ctx.run(f"fill {fx - 1} {fy - 1} {fz - 1} {fx + 1} {fy - 1} {fz + 1} minecraft:stone", r"Successfully filled|No blocks")
    ctx.run(f"summon minecraft:tnt {fx} {fy} {fz} {{fuse:1}}", r"Summoned")
    ctx.ticks(30)
    p.check(all(not ctx.block(v, "minecraft:air") for v in neighbors), "una TNT rompe bloques de la arena")
    p.check(ctx.block((fx, fy - 1, fz), "minecraft:air"), "control: la TNT de fuera no rompe nada (¿no explotó?)")
    # piston against a facade pillar (east) and another outside (control)
    py = miny + pl["suelo"] + 3
    pillar = (maxx, py, cz)
    p.check(not ctx.block(pillar, "minecraft:air"), f"no hay pilar en {pillar}")
    ctx.run(f"setblock {maxx + 1} {py} {cz} minecraft:piston[facing=west]", r"Changed the block|Could not set")
    ctx.run(f"setblock {maxx + 2} {py} {cz} minecraft:redstone_block", r"Changed the block|Could not set")
    gx = maxx + 12
    ctx.run(f"fill {gx - 3} {py - 1} {cz - 1} {gx + 2} {py + 1} {cz + 1} minecraft:air", r"Successfully filled|No blocks")
    ctx.run(f"setblock {gx - 1} {py} {cz} minecraft:stone", r"Changed the block|Could not set")
    ctx.run(f"setblock {gx} {py} {cz} minecraft:piston[facing=west]", r"Changed the block|Could not set")
    ctx.run(f"setblock {gx + 1} {py} {cz} minecraft:redstone_block", r"Changed the block|Could not set")
    ctx.ticks(10)
    p.check(ctx.block((maxx + 1, py, cz), "minecraft:piston[extended=false]"), "un pistón empuja el muro de la arena")
    p.check(not ctx.block(pillar, "minecraft:air"), "el pilar de la arena se movió")
    p.check(ctx.block((gx, py, cz), "minecraft:piston[extended=true]"), "control: el pistón de fuera no se mueve")
    # dispenser with a lava bucket next to the facade (west) and another far away (control): ArenaCuboMixin
    for x0, desc in ((minx - 2, "junto a la arena"), (maxx + 30, "lejos (control)")):
        ctx.run(f"fill {x0 - 2} {py - 1} {cz - 1} {x0 + 1} {py + 1} {cz + 1} minecraft:air", r"Successfully filled|No blocks")
        ctx.run(f"fill {x0 - 2} {py - 2} {cz - 1} {x0 + 1} {py - 2} {cz + 1} minecraft:stone", r"Successfully filled|No blocks")
        ctx.run(f'setblock {x0} {py} {cz} minecraft:dispenser[facing=east]{{Items:[{{Slot:0b,id:"minecraft:lava_bucket",count:1}}]}}',
                r"Changed the block|Could not set")
        ctx.run(f"setblock {x0 - 1} {py} {cz} minecraft:redstone_block", r"Changed the block|Could not set")
    ctx.ticks(10)
    p.check(not ctx.block((minx - 1, py, cz), "minecraft:lava"), "un dispensador vacía un cubo de lava junto a la arena")
    p.check(ctx.until(f"execute if entity @e[type=minecraft:item,x={minx - 1},y={py},z={cz},distance=..3,"
                      f"nbt={{Item:{{id:\"minecraft:lava_bucket\"}}}}]"),
            "el dispensador junto a la arena no suelta el cubo de lava como objeto")
    p.check(ctx.block((maxx + 31, py, cz), "minecraft:lava"), "control: el dispensador lejos de la arena no vacía su cubo")
    ctx.run(f"fill {maxx + 27} {py - 1} {cz - 1} {maxx + 33} {py + 1} {cz + 1} minecraft:air", r"Successfully filled|No blocks")
    ctx.run(f"fill {minx - 4} {py - 1} {cz - 1} {minx - 1} {py + 1} {cz + 1} minecraft:air", r"Successfully filled|No blocks")
    ctx.run(f"kill @e[type=minecraft:item,x={minx - 1},y={py},z={cz},distance=..6]", r"Killed|No entity")

    # 3. game with the bell
    ctx.run(f"gamemode survival {P}", r"Set .* game mode|game mode")
    ctx.run(f"effect give {P} minecraft:resistance infinite 255 true", r"Applied effect|Gave")
    ctx.run(f"give {P} minecraft:diamond 7", r"Gave")
    ctx.run(f"experience add {P} 10 levels", r"Gave|experience")
    ctx.run(f"tp {P} {bell[0] + 0.5} {bell[1]} {bell[2] - 1.5}", r"Teleported")
    s.send(ctx.proc, f"player {P} look at {bell[0] + 0.5} {bell[1] + 0.4} {bell[2] + 0.5}")
    ctx.ticks(5)
    s.send(ctx.proc, f"player {P} use once")
    # T41: with the three modes enabled, the bell offers one button per mode (/heraldia arena start <mode>); the simulated
    # player cannot press it: the command is sent on its behalf
    if not p.check(p.wait_log(rf"arena: {P} elige modo \(coop, timeattack, survival\)", timeout=60),
                   "la campana no ofrece los modos"):
        return box
    ctx.run(f"execute as {P} run heraldia arena start coop", r"Prepárate|Get ready")
    if not p.check(p.wait_log(rf"arena: cuenta atrás \(la empieza {P}, modo coop\)", timeout=60), "la campana no empieza la partida"):
        return box
    p.check(ctx.block(door, "minecraft:iron_bars"), "la puerta no se cierra al empezar")
    p.check(p.wait_log(r"arena: partida empieza con 1 participantes"), "la partida no empieza con el jugador")
    p.check(p.wait_log(r"arena: oleada 1: 4 enemigos"), "la oleada 1 no trae 4 enemigos")
    p.check(ctx.until(f"execute if entity {ARENA}") and wait_count(ctx, ARENA, 4), "no salen 4 enemigos en la oleada 1")
    p.check(p.num(f"attribute {ARENA[:-1]},limit=1] minecraft:max_health modifier value get heraldia:arena_vida") in (None, 0.0),
            "oleada 1 con modificador de vida")
    clean_up(p, 1)
    items = ctx.count(f"@e[type=item,x={minx},y={miny},z={minz},dx={maxx - minx},dy={maxy - miny},dz={maxz - minz}]")
    if not p.check(items == 0, f"los mobs de la arena sueltan objetos ({items})"):
        print("DIAG:", ctx.run(f"data get entity @e[type=item,limit=1,x={minx},y={miny},z={minz},dx={maxx - minx},dy={maxy - miny},"
                               f"dz={maxz - minz}]", r"entity data|No entity").string)
    experience(p, 1)
    p.check(p.wait_log(r"arena: oleada 2: 6 enemigos", timeout=60), "la oleada 2 no trae 6 enemigos")
    p.check(wait_count(ctx, ARENA, 6), "no salen 6 enemigos en la oleada 2")
    v = p.num(f"attribute {ARENA[:-1]},limit=1] minecraft:max_health modifier value get heraldia:arena_vida")
    p.check(v is not None and abs(v - 0.1) < 1e-6, f"oleada 2: heraldia:arena_vida {v} (debía ser 0,1)")
    v = p.num(f"attribute {ARENA[:-1]},limit=1] minecraft:attack_damage modifier value get heraldia:arena_dano")
    p.check(v is not None and abs(v - 0.1) < 1e-6, f"oleada 2: heraldia:arena_dano {v} (debía ser 0,1)")
    clean_up(p, 2)
    experience(p, 2)
    for n in (3, 4):
        p.check(p.wait_log(rf"arena: oleada {n}: \d+ enemigos", timeout=60), f"no empieza la oleada {n}")
        clean_up(p, n)
    # wave 5: the mini-boss
    p.check(p.wait_log(r"arena: oleada 5: 13 enemigos", timeout=60), "la oleada 5 no trae 12 enemigos y el mini-jefe")
    boss = "@e[tag=heraldia_arena,tag=heraldia_guardian,limit=1]"
    if p.check(p.wait_log(r"arena: mini-jefe minecraft:zombie en la oleada 5"), "no sale el mini-jefe en la oleada 5"):
        ctx.wait_entity(boss)
        ctx.ticks(25)
        ctx.run(f"damage {boss} 70 minecraft:player_attack by {P}", r"Applied|damage")
        p.check(p.wait_log(r"jefes: zombie/\w+ pasa a la fase 2", timeout=30), "el mini-jefe no pasa a la fase 2")
        p.check(p.wait_log(r"arena: un refuerzo del mini-jefe entra en la oleada", timeout=30),
                "los refuerzos del mini-jefe no entran en la oleada")
    clean_up(p, 5)
    p.check(p.wait_log(rf"arena: recompensa 1 \(\d+ objetos\) para {P} en la oleada 5"), "sin recompensa en la oleada 5")
    p.check(ctx.test(f"execute if entity @a[name={P},advancements={{heraldia:arena/oleada_5=true}}]"), "sin el logro de la oleada 5")
    p.check(p.num(f"scoreboard players get {P} heraldia_arena") == 5, "el marcador no tiene el récord 5 del jugador")
    p.check(p.num("scoreboard players get -servidor- heraldia_arena") == 5, "el marcador no tiene el récord 5 del servidor")
    p.check(p.wait_log(rf"arena: récord del servidor: {P} en la oleada 5"), "sin anuncio del récord")

    # 4. death in the ring, during the pause. Carpet disconnects the simulated player on death (it does not go through the vanilla
    # respawn): it is checked that it drops nothing and that, when it is created again, its saved data keeps what it was carrying.
    level_before = p.num(f"experience query {P} levels")
    death = ctx.pos(f"@a[name={P}]")
    nearby_flag = f"x={death[0]:.1f},y={death[1]:.1f},z={death[2]:.1f},distance=..4" if death else "distance=..0"
    ctx.run("kill @e[type=experience_orb]", r"Killed|No entity")       # those of the mobs (no more come out during the pause)
    orbs_before = ctx.count(f"@e[type=experience_orb,{nearby_flag}]")
    ctx.run(f"effect clear {P}", r"Removed|effect")
    ctx.run(f"damage {P} 1000 minecraft:generic", r"Applied|damage")
    p.check(p.wait_log(rf"arena: {P} cae en el ruedo y conserva", timeout=30), "al caer en el ruedo no conserva el inventario")
    ctx.ticks(10)
    p.check(ctx.count('@e[type=item,nbt={Item:{id:"minecraft:diamond"}}]') == 0, "suelta sus diamantes al caer en el ruedo")
    p.check(ctx.count(f"@e[type=experience_orb,{nearby_flag}]") <= orbs_before, "suelta experiencia al caer en el ruedo")
    ctx.until(f"execute if entity @a[name={P}]", want=False, timeout=30)
    ctx.run(f"player {P} spawn at {reap[0] + 0.5} {reap[1]} {reap[2] + 0.5}", r"joined the game|Player .* spawn|Unknown|Incorrect")
    ctx.until(f"execute if entity @a[name={P}]")
    p.check(ctx.test(f'execute if entity @a[name={P},nbt={{Inventory:[{{id:"minecraft:diamond",count:7}}]}}]'),
            "pierde los diamantes al caer en el ruedo")
    level = p.num(f"experience query {P} levels")
    p.check(level is not None and level_before is not None and level >= level_before and level >= 10,
            f"pierde la experiencia al caer en el ruedo ({level_before} -> {level})")
    p.check(p.wait_log(r"arena: partida terminada \(sin participantes\) con 5 oleadas superadas"), "la partida no acaba sin participantes")
    p.check(ctx.count(ARENA) == 0, "quedan mobs de la arena al acabar")
    p.check(ctx.block(door, "minecraft:air"), "la puerta no se abre al acabar")
    return box


def half_done(p, pl, box):
    ctx = p.ctx
    cx, cz = box[0] + pl["centro"][0], box[2] + pl["centro"][2]
    ctx.run(f"tp {P} {cx + 0.5} {box[1] + 1} {cz + 0.5}", r"Teleported")
    ctx.run("heraldia arena start", r"Prepárate|Get ready")
    ctx.run(f"effect give {P} minecraft:resistance infinite 255 true", r"Applied effect|Gave")
    p.check(p.wait_times(r"arena: oleada 1: 4 enemigos", 2, timeout=60), "la segunda partida no empieza")
    p.check(wait_count(ctx, ARENA, 4), "la segunda partida no saca sus mobs")
    door = tuple(box[i] + pl["puerta"][0][i] for i in range(3))
    p.check(ctx.block(door, "minecraft:iron_bars"), "segunda partida: la puerta no se cierra")
    ctx.run("save-all flush", r"Saved the game")


def second_start(p, pl, box):
    ctx = p.ctx
    m = p.wait_log(r"arena: en (-?\d+) (-?\d+) (-?\d+)", timeout=60)
    p.check(m, "tras reiniciar no se recuerda la arena")
    p.check(p.wait_log(r"arena: quitado un mob de arena de una partida anterior", timeout=120),
            "tras reiniciar no se quitan los mobs de la partida anterior")
    p.check(ctx.until(f"execute if entity {ARENA}", want=False, timeout=60), "tras reiniciar quedan mobs de la arena")
    door = tuple(box[i] + pl["puerta"][0][i] for i in range(3))
    p.check(ctx.block(door, "minecraft:air"), "tras reiniciar la puerta sigue cerrada")
    ctx.run("heraldia arena", r"Arena de oleadas en|Wave arena at")
    p.check(p.wait_log(r"Sin partida|No match", timeout=30), "tras reiniciar hay una partida")
    p.check(ctx.block(tuple(box[i] + pl["campana"][i] for i in range(3)), "minecraft:bell"), "tras reiniciar no está la campana")


def herald_house(p, hp, arena_box):
    """The Herald's House in this (no longer new) world: placed by an operator, protected, its portal, its market."""
    ctx = p.ctx
    ctx.run("heraldia herald", r"no Herald's House yet|aún no tiene Casa del Heraldo")
    ctx.run("heraldia herald place confirm", r"There is no proposal|No hay ninguna propuesta")
    ctx.run("heraldia herald place", r"Looking for a site|Buscando sitio")
    m = p.wait_log(r"herald's house: site at (-?\d+) (-?\d+) (-?\d+) \((\d+) blocks from spawn", timeout=120)
    if not p.check(m, "herald: no site proposed near spawn"):
        return
    # Siting.RADIUS (48) is per axis: a candidate on the ring's corner is up to 48 * sqrt(2) = 68 blocks away
    p.check(int(m.group(4)) <= 68, f"herald: site {m.group(4)} blocks from spawn (at most 48 along each axis)")
    ctx.run("heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
    m = p.wait_log(r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+) \(box (-?\d+) (-?\d+) (-?\d+) to (-?\d+) (-?\d+) (-?\d+)\)",
                   timeout=400)
    if not p.check(m, "herald: the house is not built"):
        return
    b = [int(g) for g in m.groups()[3:]]
    print("HERALD: build:", re.search(r"herald's house: built in .*", ctx.log()).group(0))
    side = hp["tamano"][0]
    p.check(b[3] - b[0] == side - 1 and b[5] - b[2] == side - 1, f"herald: box {b} is not {side} x {side}")
    m2 = re.search(r"herald's house: built in (\d+) ticks \((\d+) ms", ctx.log())
    if m2:
        BUILD.append((int(m2.group(1)), int(m2.group(2))))
    ax0, az0, ax1, az1 = arena_box[0], arena_box[2], arena_box[3], arena_box[5]
    p.check(ax1 < b[0] - 50 or ax0 > b[3] + 50 or az1 < b[2] - 50 or az0 > b[5] + 50,
            "herald: the protected ring touches the arena")
    o = b[:3]
    w = lambda rel: tuple(o[i] + rel[i] for i in range(3))
    ctx.run(f"forceload add {b[0]} {b[2]} {b[3]} {b[5]}", r"Marked|force|already")
    p.check(ctx.block(w(hp["campana"]), "minecraft:bell"), "herald: no bell")
    (pa, pb) = hp["portal"]
    ax, ay, az = w(pa)
    p.check(ctx.block((ax + 1, ay, az), "minecraft:obsidian"), "herald: no portal frame")
    p.check(ctx.block((ax + 1, ay + 1, az), "minecraft:air"), "herald: the portal is not empty")
    sign = w(hp["puestos"][0]["cartel"])
    p.check(ctx.block(sign, "#minecraft:all_signs"), "herald: stall 1 has no sign")
    ctx.run("heraldia herald", r"The Herald's House is at|La Casa del Heraldo está en")
    # its villagers: the 18 residents and the bailiff, all where the template put them
    res = f"@e[type=minecraft:villager,tag=heraldia_casa,tag=!heraldia_alguacil,x={b[0]},y={b[1]},z={b[2]},dx={side},dy=40,dz={side}]"
    p.check(ctx.count(res) == 18, f"herald: {ctx.count(res)} resident villagers (18)")
    # a village event on the plaza (version 2: its middle is a village square)
    sq = hp.get("plaza_eventos")
    if sq:
        cx, cy, cz = o[0] + sq[0] + sq[3] // 2, o[1] + sq[1] + 1, o[2] + sq[2] + sq[3] // 2
        ctx.run(f"execute positioned {cx} {cy} {cz} run heraldia event start market",
                r"starts in|Empieza el evento|not started|no cabe|No hay|There is no|room|no hay sitio")
        p.check(p.wait_log(r"events: event \d+ starts: market in", timeout=30), "herald: no market day on the plaza")
        ctx.run("heraldia event stop all", r"stopped|parad|[Ee]vent")
    if SETTLE:
        settle(p, b, res)
    # protection: a creative player who is not an operator
    sx, sy, sz = w(hp["aparicion"])
    ctx.run(f"deop {P}", r"no longer|Nothing changed|not an operator")
    s.send(ctx.proc, f"gamemode creative {P}")          # no reply when the mode does not change
    ctx.ticks(2)
    ctx.run(f"tp {P} {sx + 0.5} {sy} {sz + 0.5}", r"Teleported")
    floor = (sx + 2, sy - 1, sz)
    s.send(ctx.proc, f"player {P} look at {floor[0] + 0.5} {floor[1] + 1} {floor[2] + 0.5}")
    ctx.ticks(5)
    before = ctx.run(f"execute if block {floor[0]} {floor[1]} {floor[2]} minecraft:air", r"Test passed|Test failed").group(0)
    p.check(before.startswith("Test failed"), f"herald: no floor at {floor}")
    smash(ctx)
    p.check(not ctx.block(floor, "minecraft:air"), "herald: a player who is not an operator breaks a block")
    ctx.run(f"item replace entity {P} weapon.mainhand with minecraft:stone", r"Replaced|replaced")
    s.send(ctx.proc, f"player {P} use once")
    ctx.ticks(10)
    p.check(ctx.block((floor[0], floor[1] + 1, floor[2]), "minecraft:air"), "herald: a player who is not an operator places a block")
    # the portal: refused to a player, lit by an operator
    ctx.run(f"tp {P} {ax + 1.5} {ay} {az + 2.5}", r"Teleported")
    ctx.run(f"item replace entity {P} weapon.mainhand with minecraft:flint_and_steel", r"Replaced|replaced")
    s.send(ctx.proc, f"player {P} look at {ax + 1.5} {ay + 1} {az + 0.5}")
    ctx.ticks(5)
    s.send(ctx.proc, f"player {P} use once")
    ctx.ticks(10)
    p.check(ctx.block((ax + 1, ay + 1, az), "minecraft:air"), "herald: a player who is not an operator lights the portal")
    ctx.run(f"op {P}", r"Made .* operator|already|Nothing changed")
    s.send(ctx.proc, f"player {P} use once")
    ctx.ticks(10)
    p.check(ctx.block((ax + 1, ay + 1, az), "minecraft:nether_portal"), "herald: an operator cannot light the portal")
    ctx.run(f"deop {P}", r"no longer|Nothing changed|not an operator")
    # the market: claim stall 1, leave a chest with diamonds in it, let the rent run out
    s.send(ctx.proc, f"gamemode survival {P}")
    ctx.ticks(2)
    ctx.run(f"clear {P}", r"Removed|No items")
    ctx.run(f"give {P} minecraft:emerald 10", r"Gave")
    ctx.run(f"execute as {P} run heraldia herald stall claim 1", r"Stall 1 is yours|El puesto 1 es tuyo|need|Hacen falta")
    p.check(p.wait_log(rf"stall 1 claimed by {P} for 3 emeralds", timeout=30), "herald: stall 1 is not claimed")
    p.check(ctx.test(f'execute if entity @a[name={P},nbt={{Inventory:[{{id:"minecraft:emerald",count:7}}]}}]'),
            "herald: claiming does not take entry fee + first rent (3 emeralds)")
    ctx.run(f"execute as {P} run heraldia herald stall claim 2", r"already have stall 1|Ya tienes el puesto 1")
    box = w(hp["puestos"][0]["caja"][0])
    ctx.run(f'setblock {box[0]} {box[1]} {box[2]} minecraft:chest{{Items:[{{Slot:0b,id:"minecraft:diamond",count:5}}]}}',
            r"Changed the block|Could not set")
    ctx.run("tick sprint 30000", r"[Ss]print|sprint")
    m = p.wait_log(rf"stall 1 of {P} reclaimed: (\d+) stacks into (\d+) return barrel", timeout=300)
    if p.check(m, "herald: the expired stall is not reclaimed"):
        barrel = w(hp["devolucion"][0])
        p.check(ctx.block(barrel, 'minecraft:barrel{Items:[{id:"minecraft:diamond",count:5}]}'),
                "herald: the diamonds are not in the return barrel")
        p.check(ctx.block(barrel, 'minecraft:barrel{Items:[{id:"minecraft:chest"}]}'),
                "herald: the tenant's chest is not in the return barrel")
        p.check(ctx.block(box, "minecraft:air"), "herald: the stall is not emptied")
    ctx.run("tick sprint stop", r"[Ss]print|sprint|No")
    ctx.run("heraldia herald stall", r"Market stalls|Puestos del mercado")
    # trampling: a 3-block drop onto the house's farmland (HeraldFarmlandMixin), and onto farmland far away (control)
    s.send(ctx.proc, f"gamemode survival {P}")
    ctx.ticks(2)
    far = (b[3] + 300, b[5] + 300)
    farm = w(hp["huerto"])
    p.check(ctx.block(farm, "minecraft:farmland"), f"herald: no farmland at {farm}")
    ctx.run(f"tp {P} {farm[0] + 0.5} {farm[1] + 4} {farm[2] + 0.5}", r"Teleported")
    ctx.ticks(30)
    p.check(ctx.block(farm, "minecraft:farmland"), "herald: a player tramples the house's farmland")
    ctx.run(f"spreadplayers {far[0]} {far[1]} 0 1 false {P}", r"Spread|spread")
    fp = ctx.pos(f"@a[name={P}]")
    if p.check(fp, "herald: the player is not at the control spot"):
        fx, fy, fz = int(math.floor(fp[0])), int(round(fp[1])) + 6, int(math.floor(fp[2]))
        ctx.run(f"fill {fx - 1} {fy - 1} {fz - 1} {fx + 1} {fy + 4} {fz + 1} minecraft:air", r"Successfully filled|No blocks")
        ctx.run(f"setblock {fx} {fy - 1} {fz} minecraft:farmland", r"Changed the block|Could not set")
        ctx.run(f"tp {P} {fx + 0.5} {fy + 3} {fz + 0.5}", r"Teleported")
        ctx.ticks(30)
        p.check(ctx.block((fx, fy - 1, fz), "minecraft:dirt"), "herald: control: far away the farmland is not trampled (test broken?)")
    # monsters not spawning in the area (HeraldSpawnMixin) is not checked here: in this world spawn_mobs and advance_time
    # were turned off at the start and turning them back on does not bring natural spawning back (see LESSONS)
    ctx.run(f"tp {P} {sx + 0.5} {sy} {sz + 0.5}", r"Teleported")


SETTLE = False          # --settle: three in-game days, counting who holds a bed, a workstation and a meeting point
BUILD = []


def settle(p, b, res):
    """On the seed's real terrain (wherever the site search put the town): at the end of each of three in-game days,
    how many residents hold a bed, a workstation and a meeting point (their Brain memories, which the game saves).
    Forceloads the town and 48 blocks around (they stroll by day; /forceload takes at most 256 chunks), waits for it to load and runs the clock in steps
    (see LESSONS on testing villagers over several days)."""
    import medium_structures as ms
    ctx = p.ctx
    m = 48
    ctx.run(f"forceload add {b[0] - m} {b[2] - m} {b[3] + m} {b[5] + m}", r"Marked|force|already|[Tt]oo many")
    cx, cz = (b[0] + b[3]) // 2, (b[2] + b[5]) // 2
    ms.wait_loaded(ctx, cx - 8, cz - 8, (b[3] - b[0]) // 2 + m - 16)
    ctx.run("gamerule advance_time true", r"[Gg]ame ?rule")
    ctx.run("time set 1000", r"Set the time|time to|Set minecraft:\w+ to|already")
    n = ctx.count(res)
    mem = lambda k: ctx.count(f"{res[:-1]},nbt={{Brain:{{memories:{{\"minecraft:{k}\":{{}}}}}}}}]")
    out = []
    for day in (1, 2, 3):
        ms.sprint(ctx, 12000 if day == 1 else 24000)            # to the night of that day
        time.sleep(20)
        row = (day, n, mem("home"), mem("job_site"), mem("meeting_point"), ctx.count(res))
        out.append(row)
        print(f"HERALD: settle: day {day}: of {n} residents, {row[2]} with a bed, {row[3]} with a workstation, "
              f"{row[4]} with a meeting point ({row[5]} alive)")
    nohome = f"{res[:-1]},nbt=!{{Brain:{{memories:{{\"minecraft:home\":{{}}}}}}}}]"
    if ctx.count(nohome):
        s.send(ctx.proc, f"execute as {nohome} run data get entity @s VillagerData.profession")
        s.send(ctx.proc, f"execute as {nohome} run data get entity @s Pos")
        ctx.ticks(5)
        print("HERALD: settle: without a bed:", "; ".join(re.findall(r"Villager has the following entity data: (.*)", ctx.log())[-2 * ctx.count(nohome):]))
    ctx.run("gamerule advance_time false", r"[Gg]ame ?rule")
    last = out[-1]
    p.check(last[2] >= n - 1 and last[3] >= n - 1 and last[4] >= n - 1,
            f"herald: after three days only {last[2]}/{n} beds, {last[3]}/{n} workstations, {last[4]}/{n} meeting points")


def wait_count(ctx, sel, n, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if ctx.count(sel) == n:
            return True
        ctx.ticks(5)
    print(f"DIAG: {sel}: {ctx.count(sel)} (esperados {n})")
    return False


def clean_up(p, n, timeout=180):
    """Kills (in the player's name) the enemies of wave n until it is cleared."""
    ctx = p.ctx
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if re.search(rf"arena: oleada {n} superada", ctx.log()):
            return True
        if ctx.count(ARENA):
            ctx.run(f"damage {ARENA[:-1]},limit=1,sort=random] 1000 minecraft:player_attack by {P}", r"Applied|damage|No entity")
        else:
            ctx.ticks(5)
    p.check(False, f"no se supera la oleada {n}")
    return False


def experience(p, n):
    m = re.search(rf"arena: oleada {n} superada \(experiencia: (\d+) de vanilla, (\d+) dada, al (\d+) %\)", p.ctx.log())
    if not p.check(m, f"oleada {n}: sin el resumen de experiencia"):
        return
    vanilla, given, pct = (int(g) for g in m.groups())
    mobs = 4 if n == 1 else 6
    p.check(pct == 15 and vanilla > 0, f"oleada {n}: experiencia vanilla {vanilla} al {pct} %")
    p.check(abs(given - vanilla * 0.15) <= mobs, f"oleada {n}: {given} de experiencia de {vanilla} (debía ser el 15 %)")


def smash(ctx):
    """The simulated player mines the block it is looking at (in creative, instantly): Carpet's "attack once" breaks nothing."""
    s.send(ctx.proc, f"player {P} attack continuous")
    ctx.ticks(20)
    s.send(ctx.proc, f"player {P} stop")
    ctx.ticks(5)


if __name__ == "__main__":
    sys.exit(main())
