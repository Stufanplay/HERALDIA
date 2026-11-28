"""Configurable difficulty (dificultad.*) on a real 26.3 dedicated server, with restarts and simulated players (Carpet).

Usage: python3 tools/smoke/difficulty.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Summons (with NBT, without finalizeSpawn) anchored zombies (heraldia_anclado), a guardian (heraldia_guardian, base health 60),
a wounded one, a zombie without tags and an anchored wolf, and restarts the same world with each level:
  - heroic: the anchored one (and a boss reinforcement, heraldia_refuerzo) has health 40 and damage 4.5; with strength I (a boss
    phase effect) the damage is (3 + 3) x 1.5 and when removed it goes back to 4.5 (modifiers heraldia:dificultad_vida and _dano), the guardian 120, the
    wounded one keeps its proportion (10/20 -> 20/40), the zombie without tags and the wolf do not change; the loot of a Heraldia
    chest table (test datapack, 10 arrows) comes out x1.5 and a named item or a table from another folder, the same;
  - easy (after restarting: those already generated are recalculated on load): 15, 45 and the wounded one 7.5/15; 7 or 8 arrows;
  - normal: everything as usual (20, 60, wounded 10/20, no modifiers) and 10 arrows;
  - heroic with difficulty.escalar_por_jugadores: with 3 players nearby, on receiving a hit the anchored one goes to 60 max
    health (x2 x1.5); with 1, to 40.
"""
import argparse, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch

X, Y, Z = 0, 100, 0
PACK = "heraldia_prueba_dificultad"
TABLE, ANOTHER = "heraldia:cofres/prueba_dificultad", "heraldia:pruebas/prueba_dificultad"
MOBS = {   # test tag: (type, Heraldia tags, base health, initial health, dx)
    "p_anclado": ("zombie", ["heraldia_anclado", "heraldia_adulto"], 20, 20, 0),
    "p_guardian": ("zombie", ["heraldia_guardian", "heraldia_guardian.prueba", "heraldia_anclado", "heraldia_adulto"], 60, 60, 2),
    "p_herido": ("zombie", ["heraldia_anclado", "heraldia_adulto"], 20, 10, 4),
    "p_libre": ("zombie", [], 20, 20, 6),
    "p_refuerzo": ("zombie", ["heraldia_refuerzo", "heraldia_anclado", "heraldia_adulto"], 20, 20, 10),
    "p_lobo": ("wolf", ["heraldia_anclado"], 8, 8, 8),
}
NUM = r"(-?\d+(?:\.\d+)?)"


def datapack(work):
    root = os.path.join(work, "world", "datapacks", PACK)
    for d in ("cofres", "pruebas"):
        os.makedirs(os.path.join(root, "data", "heraldia", "loot_table", d), exist_ok=True)
    with open(os.path.join(root, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "Heraldia: prueba de la dificultad", "min_format": 121, "max_format": 121}}, f)
    # 26.3 format: "modifier" with "type" (not "functions"/"function", which are silently ignored)
    arrows = {"type": "minecraft:item", "name": "minecraft:arrow", "modifier": {"type": "minecraft:set_count", "count": 10}}
    masts = {"type": "minecraft:item", "name": "minecraft:stick", "modifier": [
        {"type": "minecraft:set_count", "count": 10},
        {"type": "minecraft:set_name", "target": "custom_name", "name": {"text": "Palo con nombre"}}]}
    tbl = {"type": "minecraft:chest", "pools": [{"rolls": 1, "entries": [arrows]}, {"rolls": 1, "entries": [masts]}]}
    for d in ("cofres", "pruebas"):
        with open(os.path.join(root, "data", "heraldia", "loot_table", d, "prueba_dificultad.json"), "w") as f:
            json.dump(tbl, f)


def config(work, level, players=False):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["dificultad"] = {"nivel": level, "escalar_por_jugadores": players}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-dificultad"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    datapack(a.work)
    fails, ok = [], 0
    srv = None

    def check(cond, msg):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fails.append(msg)
            print("FAIL:", msg)

    def start_up(level, players=False):
        nonlocal srv
        if srv:
            srv.stop()
        config(a.work, level, players)
        srv = Server(a.work, launcher)
        return srv.ctx

    def sel(tag):
        return f"@e[tag={tag},limit=1]"

    def num(ctx, cmd):
        m = ctx.run(cmd, rf"(?:is|data:) {NUM}f?\b|No entity|[Nn]o modifier|has no|There is no|not found|Unknown|Can't find")
        return float(m.group(1)) if m.lastindex and m.group(1) else None

    def max_health(ctx, tag):
        return num(ctx, f"attribute {sel(tag)} minecraft:max_health get")

    def health(ctx, tag):
        return num(ctx, f"data get entity {sel(tag)} Health")

    def modifier(ctx, tag, attr, mod):
        return num(ctx, f"attribute {sel(tag)} minecraft:{attr} modifier value get heraldia:{mod}")

    def wait_mobs(ctx):
        for tag in MOBS:
            if not ctx.until(f"execute if entity {sel(tag)}"):
                raise SystemExit(f"mob {tag} does not appear after starting")

    def mobs(ctx, level, expected):
        """expected: {tag: (max health, health)}"""
        for tag, (vm, v) in expected.items():
            got_vm, got_v = max_health(ctx, tag), health(ctx, tag)
            check(got_vm is not None and abs(got_vm - vm) < 1e-3, f"{level}: {tag} con vida máxima {got_vm} (debe ser {vm})")
            check(got_v is not None and abs(got_v - v) < 1e-3, f"{level}: {tag} con vida {got_v} (debe ser {v})")

    def tally(ctx, item):
        """Amount of the item `item` on the ground (a single stack), or None."""
        e = f'@e[type=minecraft:item,x={X},y={Y + 1},z={Z + 6},distance=..4,nbt={{Item:{{id:"{item}"}}}},limit=1]'
        m = ctx.run(f"data get entity {e} Item.count", r"has the following entity data: (\d+)|No entity")
        return int(m.group(1)) if m.lastindex and m.group(1) else None

    def chest_loot(ctx, level, arrows):
        """The Heraldia chest table gives `arrows` (set of valid values); the other one and the named stick, 10.
        It waits on a condition (not on each command's reply): the empty floor before and the two stacks after."""
        zone = f"@e[type=minecraft:item,x={X},y={Y + 1},z={Z + 6},distance=..4]"
        for tbl, want in ((TABLE, arrows), (ANOTHER, {10})):
            ctx.run(f"kill {zone}", r"Killed|No entity was found")
            check(ctx.until(f"execute if entity {zone}", want=False), f"{level}: no se vacía el suelo antes de {tbl}")
            ctx.run(f"loot spawn {X} {Y + 3} {Z + 6} loot {tbl}", r"Dropped|No items")
            ctx.until(f'execute if entity {zone[:-1]},nbt={{Item:{{id:"minecraft:stick"}}}}]')
            ctx.until(f'execute if entity {zone[:-1]},nbt={{Item:{{id:"minecraft:arrow"}}}}]')
            arrows_n = tally(ctx, "minecraft:arrow")
            check(arrows_n in want, f"{level}: {tbl} da {arrows_n} flechas (debe ser {sorted(want)})")
            sticks_n = tally(ctx, "minecraft:stick")
            check(sticks_n == 10, f"{level}: {tbl}: el palo con nombre sale con {sticks_n} (debe ser 10)")
        ctx.run(f"kill {zone}", r"Killed|No entity was found")

    try:
        # heroic: the mobs are summoned (ENTITY_LOAD when added to the world)
        ctx = start_up("heroica")
        ctx.run(f"forceload add {X - 16} {Z - 16} {X + 16} {Z + 16}", r"Marked|force|already|[Aa]dded")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {X - 2} {Y - 1} {Z - 2} {X + 12} {Y - 1} {Z + 8} minecraft:stone", r"Successfully filled|No blocks|not loaded")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        ctx.run(f"fill {X - 2} {Y} {Z - 2} {X + 12} {Y + 3} {Z + 8} minecraft:air", r"Successfully filled|No blocks")
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        ctx.run("time set midnight", r"[Tt]ime|[Ss]et")      # at night and with a roof: zombies do not burn
        ctx.run(f"fill {X - 2} {Y + 4} {Z - 2} {X + 12} {Y + 4} {Z + 8} minecraft:stone", r"Successfully filled|No blocks")
        for tag, (kind, tags, base, v, dx) in MOBS.items():
            tag_list = ",".join(f'"{t}"' for t in tags + [tag])
            ctx.run(f'summon minecraft:{kind} {X + dx} {Y} {Z} {{NoAI:1b,PersistenceRequired:1b,Silent:1b,Tags:[{tag_list}],'
                    f'Health:{v}f,attributes:[{{id:"minecraft:max_health",base:{base}}}]}}', r"Summoned|Unable")
        wait_mobs(ctx)
        mobs(ctx, "heroica", {"p_anclado": (40, 40), "p_guardian": (120, 120), "p_herido": (40, 20), "p_libre": (20, 20), "p_lobo": (8, 8), "p_refuerzo": (40, 40)})
        damage = num(ctx, f"attribute {sel('p_anclado')} minecraft:attack_damage get")
        check(damage is not None and abs(damage - 4.5) < 1e-3, f"heroica: daño del anclado {damage} (debe ser 4,5)")
        check(modifier(ctx, "p_anclado", "max_health", "dificultad_vida") == 1.0, "heroica: sin modificador heraldia:dificultad_vida = 1")
        check(modifier(ctx, "p_anclado", "attack_damage", "dificultad_dano") == 0.5, "heroica: sin modificador heraldia:dificultad_dano = 0,5")
        check(modifier(ctx, "p_libre", "max_health", "dificultad_vida") is None, "heroica: el zombi sin etiquetas tiene modificador")
        # with a boss phase effect (strength I: +3 damage, its own modifier): they add up, without overriding each other
        ctx.run(f"effect give {sel('p_anclado')} minecraft:strength 60 0", r"Applied effect|Gave")
        damage = num(ctx, f"attribute {sel('p_anclado')} minecraft:attack_damage get")
        check(damage is not None and abs(damage - 9) < 1e-3, f"heroica con fuerza: daño {damage} (debe ser (3 + 3) x 1,5 = 9)")
        check(modifier(ctx, "p_anclado", "attack_damage", "dificultad_dano") == 0.5, "con fuerza: se pierde heraldia:dificultad_dano")
        ctx.run(f"effect clear {sel('p_anclado')}", r"Removed|effect")
        damage = num(ctx, f"attribute {sel('p_anclado')} minecraft:attack_damage get")
        check(damage is not None and abs(damage - 4.5) < 1e-3, f"heroica tras quitar la fuerza: daño {damage} (debe ser 4,5)")
        chest_loot(ctx, "heroica", {15})

        # easy, after restarting: the already generated mobs are recalculated on load
        ctx = start_up("facil")
        wait_mobs(ctx)
        mobs(ctx, "fácil", {"p_anclado": (15, 15), "p_guardian": (45, 45), "p_herido": (15, 7.5), "p_libre": (20, 20), "p_lobo": (8, 8), "p_refuerzo": (15, 15)})
        check(modifier(ctx, "p_anclado", "max_health", "dificultad_vida") == -0.25, "fácil: el modificador no es -0,25")
        chest_loot(ctx, "fácil", {7, 8})

        # normal: exactly as always
        ctx = start_up("normal")
        wait_mobs(ctx)
        mobs(ctx, "normal", {"p_anclado": (20, 20), "p_guardian": (60, 60), "p_herido": (20, 10), "p_libre": (20, 20), "p_lobo": (8, 8), "p_refuerzo": (20, 20)})
        damage = num(ctx, f"attribute {sel('p_anclado')} minecraft:attack_damage get")
        check(damage is not None and abs(damage - 3) < 1e-3, f"normal: daño del anclado {damage} (debe ser 3)")
        for mod, attr in (("dificultad_vida", "max_health"), ("dificultad_dano", "attack_damage"), ("dificultad_jugadores", "max_health")):
            check(modifier(ctx, "p_anclado", attr, mod) is None, f"normal: queda el modificador {mod}")
        chest_loot(ctx, "normal", {10})

        # heroic with more health for nearby players (on receiving a hit)
        ctx = start_up("heroica", players=True)
        wait_mobs(ctx)
        names = ["Testigo", "Aprendiz", "Escudero"]
        for i, n in enumerate(names):
            s.require_carpet(ctx)
            ctx.run(f"player {n} spawn at {X + i} {Y} {Z + 4}", r"joined the game|Player .* spawn")
            check(ctx.until(f"execute if entity @a[name={n}]"), f"no aparece el jugador simulado {n}")
            s.send(srv.proc, f"gamemode creative {n}")  # no reply in the console if it already had it
        ctx.run(f"damage {sel('p_anclado')} 1 minecraft:player_attack by Testigo", r"Applied|damage")
        ctx.ticks(2)
        vm = max_health(ctx, "p_anclado")
        check(vm is not None and abs(vm - 60) < 1e-3, f"con 3 jugadores: vida máxima {vm} (debe ser 60)")
        check(modifier(ctx, "p_anclado", "max_health", "dificultad_jugadores") == 0.5, "con 3 jugadores: el modificador no es 0,5")
        for n in names[1:]:
            ctx.run(f"player {n} kill", r"left the game")
            ctx.until(f"execute if entity @a[name={n}]", want=False)
        ctx.ticks(20)       # after the previous hit's invulnerability (10 ticks): otherwise there is no AFTER_DAMAGE
        ctx.run(f"damage {sel('p_anclado')} 1 minecraft:player_attack by Testigo", r"Applied|damage")
        ctx.ticks(2)
        vm = max_health(ctx, "p_anclado")
        check(vm is not None and abs(vm - 40) < 1e-3, f"con 1 jugador: vida máxima {vm} (debe ser 40)")
        vm = max_health(ctx, "p_libre")
        check(vm == 20, f"el zombi sin etiquetas cambia: {vm}")
        log = ctx.log()
        bad = [b for b in ("Registry loading errors", "Failed to load datapacks") if b in log]
        bad += [l.strip() for l in log.splitlines() if "Exception" in l and "heraldia" in l.lower()]
        check(not bad, f"errores en el log: {bad}")
    finally:
        if srv:
            srv.stop()
    print(f"dificultad: {ok} comprobaciones bien, {len(fails)} mal")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
