"""Phases, reinforcements and boss bar of the guardians on a real 26.3 dedicated server (Java: jefes/).

Usage: python3 tools/smoke/boss_phases.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
With a simulated player (Carpet, in creative: the reinforcements do not attack it and it does not die) 8 blocks from each guardian.
The guardians are summoned with /summon only with their tags (like one already generated in an existing world: the phase
state lives in their Tags) and NoAI (they do not move); they are damaged with /damage ... by <player> up to each threshold:
  1. castle (zombie, own reinforcements: 2 zombies with sword and helmet and a skeleton): at 80 % nothing; at 60 % phase 2
     (tag, speed/resistance/strength, its 3 reinforcements with heraldia_refuerzo, heraldia_anclado and heraldia_adulto,
     without the guardian's tag or table, adults and with their equipment); another hit in the band does not repeat it; at 25 % phase
     3 (speed II) with only 1 more reinforcement (cap of 4 alive); with the reinforcements dead, another hit calls no more.
     The bar: for 1 player at the first hit, removed when the player moves away, again on returning and removed on death.
  2. stray without a unique structure id (guardian from an old world): hurt with no one within 48 blocks it does not change phase or
     show the bar; with the player back, it does, with the family of its type (2 strays).
  3. lighthouse (drowned, default family): a single hit from 100 % to 10 % gives both phases and 4 drowned (2 + 2).
  4. With bosses.fases/refuerzos/barra disabled (the server restarts with that configuration): none of the above.
What is seen on the client (bar, action bar notice, particles, sound) cannot be read from the console:
the bar is checked through the log lines the mod writes when showing and removing it.
"""
import argparse, json, os, queue, re, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from modrinth import MODS, fetch

CARPET = (MODS["carpet"].file, MODS["carpet"].url, MODS["carpet"].sha512)
PLAYER = "Testigo"
X, Y, Z = 0, 101, 0
GZ = 8                       # the guardians, 8 blocks from the player (within the bar's radius of 32)
REF = "@e[tag=heraldia_refuerzo]"
HEALTH = 100


def reinforcements(jar):
    with zipfile.ZipFile(jar) as z:
        return json.loads(z.read("heraldia/jefes.json"))


def guardian(mob, tag, tags):
    return (f'summon minecraft:{mob} {X} {Y} {Z + GZ} {{NoAI:1b,PersistenceRequired:1b,Health:{HEALTH}f,'
            f'Tags:[{",".join(json.dumps(t) for t in ["heraldia_guardian", "heraldia_anclado", "heraldia_adulto", tag] + tags)}],'
            f'CustomName:"Jefe de prueba",attributes:[{{id:"minecraft:max_health",base:{HEALTH}.0d}},'
            f'{{id:"minecraft:armor",base:0.0d}}]}}')


class Test:
    def __init__(self, ctx, fails):
        self.ctx, self.fails = ctx, fails

    def check(self, ok, msg):
        if not ok:
            self.fails.append(msg)
        return ok

    def strike(self, sel, n):
        # invulnerability after a hit lasts 10 ticks (20 of hurtTime): wait before the next one
        self.ctx.ticks(25)
        self.ctx.run(f"damage {sel} {n} minecraft:player_attack by {PLAYER}", r"Applied|damage")
        self.ctx.ticks(5)

    def log(self, pattern, timeout=30):
        """Does `pattern` appear in the log? Reads what arrives using cheap commands up to `timeout` seconds."""
        end = time.monotonic() + timeout
        while True:
            if re.search(pattern, self.ctx.log()):
                return True
            if time.monotonic() > end:
                return False
            self.ctx.run("time query gametime", r"[Tt]ime is \d+")
            time.sleep(0.5)

    def times(self, pattern):
        return len(re.findall(pattern, self.ctx.log()))

    def tally(self, sel, n, msg):
        got = self.ctx.count(sel)
        return self.check(got == n, f"{msg}: {got} (debían ser {n}) [{sel}]")


def start_up(work, launcher, hour):
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
    ctx.run(f"forceload add {X - 16} {Z - 16} {X + 16} {Z + 16}", r"Marked|force|already")
    for _ in range(s.PLACE_ATTEMPTS):
        m = ctx.run(f"fill {X - 10} {Y} {Z - 6} {X + 10} {Y + 6} {Z + GZ + 10} minecraft:air", r"Successfully filled|No blocks|not loaded(?! yet)")
        if "not loaded" not in m.string:
            break
        time.sleep(s.PLACE_RETRY_S)
    ctx.run(f"fill {X - 10} {Y - 1} {Z - 6} {X + 10} {Y - 1} {Z + GZ + 10} minecraft:stone", r"Successfully filled|No blocks")
    # At night and with time not passing (zombies and skeletons do not burn), no natural monsters, normal difficulty
    # (on peaceful there are no reinforcements; on hard the zombies call their own, vanilla).
    for rule in ("spawn_mobs", "advance_time"):
        ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
    ctx.run(f"time set {hour}", rf"Set .*{hour}")     # at the same time it already has, /time set does not respond
    ctx.run("difficulty normal", r"difficulty|Difficulty")
    s.require_carpet(ctx)
    ctx.run(f"player {PLAYER} spawn at {X} {Y} {Z}", r"joined the game|Player .* spawn")
    if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
        raise SystemExit(f"simulated player {PLAYER} does not appear (Carpet)")
    # Carpet creates it in creative from the console, and /gamemode to the same mode does not respond: it goes through survival
    ctx.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
    ctx.run(f"gamemode creative {PLAYER}", r"Set .* game mode|game mode")
    return proc, ctx


def halt(proc):
    if proc.poll() is None:
        s.send(proc, "stop")
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()


def castle(p, dataset):
    ctx = p.ctx
    lst = dataset["unicas"]["castillo"]
    g = "@e[tag=prueba_castillo,limit=1]"
    ctx.run(guardian("zombie", "heraldia_guardian.castillo", ["prueba_castillo"]), r"Summoned")
    if not ctx.wait_entity(g):
        p.fails.append("castle: the summoned guardian does not appear")
        return
    # 80 %: still phase 1, no reinforcements; combat starts (bar)
    p.strike(g, 20)
    p.check(not ctx.test(f"execute if entity @e[tag=prueba_castillo,tag=heraldia_fase.2]"), "castillo: fase 2 al 80 %")
    p.tally(REF, 0, "castillo: refuerzos al 80 %")
    p.check(p.log(r"jefes: barra de castillo/\w+ para 1 jugadores"), "castillo: sin barra para el jugador al primer golpe")
    # 60 %: phase 2, effects and its reinforcements
    p.strike(g, 20)
    p.check(p.log(rf"jefes: castillo/\w+ pasa a la fase 2 \({len(lst)} refuerzos\)"), "castillo: no pasa a la fase 2")
    p.check(ctx.test("execute if entity @e[tag=prueba_castillo,tag=heraldia_fase.2]"), "castillo: sin la etiqueta de la fase 2")
    # (level I, amplifier 0, is not saved: it is the codec's default value)
    for ef in ("speed", "resistance", "strength"):
        p.check(ctx.test(f'execute if entity @e[tag=prueba_castillo,nbt={{active_effects:[{{id:"minecraft:{ef}"}}]}}]'),
                f"castillo: fase 2 sin {ef}")
    p.tally(REF, len(lst), "castillo: refuerzos de la fase 2")
    for t in ("heraldia_anclado", "heraldia_adulto"):
        p.tally(f"@e[tag=heraldia_refuerzo,tag={t}]", len(lst), f"castillo: refuerzos con {t}")
    p.tally("@e[tag=heraldia_refuerzo,tag=heraldia_guardian]", 0, "castillo: refuerzos con la etiqueta de guardián")
    p.tally("@e[tag=heraldia_refuerzo,nbt={DeathLootTable:\"heraldia:guardianes/castillo/minecraft:zombie\"}]", 0,
             "castillo: refuerzos con la tabla del guardián")
    p.tally("@e[tag=heraldia_refuerzo,type=minecraft:zombie,nbt={IsBaby:1b}]", 0, "castillo: refuerzos bebés")
    for mob in sorted({r["mob"] for r in lst}):
        n = sum(r["mob"] == mob for r in lst)
        p.tally(f"@e[tag=heraldia_refuerzo,type={mob}]", n, f"castillo: refuerzos {mob}")
        hand = next((r.get("equipo", {}).get("mainhand") for r in lst if r["mob"] == mob and r.get("equipo")), None)
        if hand:
            p.tally(f'@e[tag=heraldia_refuerzo,type={mob},nbt={{equipment:{{mainhand:{{id:"{hand}"}}}}}}]',
                     sum(r["mob"] == mob and r.get("equipo", {}).get("mainhand") == hand for r in lst),
                     f"castillo: refuerzos {mob} con {hand}")
    # 50 %: still in phase 2, not repeated
    p.strike(g, 10)
    p.tally(REF, len(lst), "castillo: otro golpe en la fase 2 llama más refuerzos")
    # 25 %: phase 3, with the cap on live ones
    p.strike(g, 25)
    third = min(len(lst), 4 - len(lst))
    p.check(p.log(rf"jefes: castillo/\w+ pasa a la fase 3 \({third} refuerzos\)"), "castillo: no pasa a la fase 3")
    p.check(ctx.test('execute if entity @e[tag=prueba_castillo,nbt={active_effects:[{id:"minecraft:speed",amplifier:1b}]}]'),
            "castillo: fase 3 sin velocidad II")
    p.tally(REF, len(lst) + third, "castillo: refuerzos vivos tras la fase 3 (tope 4)")
    # with no reinforcements alive, another hit (20 %) calls no one: each phase once
    ctx.run(f"kill {REF}", r"Killed|No entity was found")
    p.strike(g, 5)
    p.tally(REF, 0, "castillo: un golpe en la fase 3 vuelve a llamar refuerzos")
    p.check(p.times(r"jefes: castillo/\w+ pasa a la fase") == 2, "castillo: más de un cambio por fase en el log")
    # the bar is removed when the player leaves and comes back with the next hit
    ctx.run(f"tp {PLAYER} {X} {Y} {Z - 70}", r"Teleported")
    p.check(p.log(r"jefes: barra de castillo/\w+ quitada \(sin jugadores cerca\)"), "castillo: la barra no se quita al alejarse")
    ctx.run(f"tp {PLAYER} {X} {Y} {Z}", r"Teleported")
    p.strike(g, 1)
    p.check(p.times(r"jefes: barra de castillo/\w+ para 1 jugadores") >= 2, "castillo: la barra no vuelve al volver el jugador")
    p.strike(g, 1000)
    p.check(p.log(r"jefes: barra de castillo/\w+ quitada \(muerto\)"), "castillo: la barra no se quita al morir")
    ctx.run(f"kill {REF}", r"Killed|No entity was found")


def stray_without_id(p, dataset):
    ctx = p.ctx
    fam = dataset["familias"][dataset["mob_familia"]["minecraft:stray"]]
    g = "@e[tag=prueba_stray,limit=1]"
    ctx.run(guardian("stray", "prueba_stray", []), r"Summoned")
    if not ctx.wait_entity(g):
        p.fails.append("stray: the summoned guardian does not appear")
        return
    # with no one within 48 blocks (damage from sun, lava...): it does not change phase or show the bar
    ctx.run(f"tp {PLAYER} {X} {Y} {Z - 70}", r"Teleported")
    p.strike(g, 50)
    p.check(not ctx.test("execute if entity @e[tag=prueba_stray,tag=heraldia_fase.2]"), "stray: pasa de fase sin jugadores cerca")
    p.tally(REF, 0, "stray: refuerzos sin jugadores cerca")
    ctx.run(f"tp {PLAYER} {X} {Y} {Z}", r"Teleported")
    p.strike(g, 1)
    p.check(p.log(rf"jefes: stray/\w+ pasa a la fase 2 \({len(fam)} refuerzos\)"), "stray sin id: no pasa a la fase 2")
    p.check(p.times(r"jefes: barra de stray/") == 1, "stray: barra sin jugadores cerca")
    for mob in {r["mob"] for r in fam}:
        p.tally(f"@e[tag=heraldia_refuerzo,type={mob}]", sum(r["mob"] == mob for r in fam), f"stray sin id: refuerzos {mob}")
    ctx.run(f"kill {g}", r"Killed|No entity was found")
    ctx.run(f"kill {REF}", r"Killed|No entity was found")


def hit_lighthouse(p, dataset):
    ctx = p.ctx
    lst = dataset["unicas"]["faro"]
    g = "@e[tag=prueba_faro,limit=1]"
    ctx.run(guardian("drowned", "heraldia_guardian.faro", ["prueba_faro"]), r"Summoned")
    if not ctx.wait_entity(g):
        p.fails.append("lighthouse: the summoned guardian does not appear")
        return
    p.strike(g, 90)
    second, third = min(len(lst), 4), min(len(lst), 4 - min(len(lst), 4))
    p.check(p.log(rf"jefes: faro/\w+ pasa a la fase 3 \({second + third} refuerzos\)"), "faro: un golpe grande no da las dos fases")
    p.check(ctx.test("execute if entity @e[tag=prueba_faro,tag=heraldia_fase.2,tag=heraldia_fase.3]"), "faro: sin las dos etiquetas")
    p.tally(REF, second + third, "faro: refuerzos de las dos fases")
    p.tally("@e[tag=heraldia_refuerzo,type=minecraft:drowned,nbt={IsBaby:1b}]", 0, "faro: ahogados bebés")
    ctx.run(f"kill {g}", r"Killed|No entity was found")
    ctx.run(f"kill {REF}", r"Killed|No entity was found")


def disabled(p):
    ctx = p.ctx
    g = "@e[tag=prueba_off,limit=1]"
    ctx.run(guardian("zombie", "heraldia_guardian.castillo", ["prueba_off"]), r"Summoned")
    if not ctx.wait_entity(g):
        p.fails.append("disabled: the summoned guardian does not appear")
        return
    p.strike(g, 50)
    p.strike(g, 30)
    p.check(not ctx.test("execute if entity @e[tag=prueba_off,tag=heraldia_fase.2]"), "desactivado: pasa de fase")
    p.tally(REF, 0, "desactivado: llama refuerzos")
    p.check(not ctx.test('execute if entity @e[tag=prueba_off,nbt={active_effects:[{id:"minecraft:speed"}]}]'), "desactivado: efectos")
    ctx.ticks(40)
    p.check(not re.search(r"jefes: (barra|castillo)", ctx.log()), "desactivado: barra o fases en el log")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-jefes"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    dataset = reinforcements(a.jar)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    texts = []
    proc, ctx = start_up(a.work, launcher, 18000)
    try:
        p = Test(ctx, fails)
        castle(p, dataset)
        stray_without_id(p, dataset)
        hit_lighthouse(p, dataset)
    finally:
        halt(proc)
        texts.append(ctx.log())
    # Second start, with the three options disabled
    cfg = os.path.join(a.work, "config", "heraldia.json")
    with open(cfg, encoding="utf-8") as f:
        conf = json.load(f)
    conf["jefes"] = {"fases": {"activado": False}, "refuerzos": {"activado": False}, "barra": {"activado": False}}
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump(conf, f)
    proc, ctx = start_up(a.work, launcher, 18100)
    try:
        disabled(Test(ctx, fails))
    finally:
        halt(proc)
        texts.append(ctx.log())
    for bad in ("Registry loading errors", "Failed to load datapacks", "jefes: refuerzo", "jefes: objeto"):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    print("JEFES:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
