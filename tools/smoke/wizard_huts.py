"""Wizard huts (T43) on a real dedicated 26.3 server (complements DecisionTest and ChozasOpcionesTest).

Usage: python3 tools/smoke/wizard_huts.py --jar build/libs/heraldia-X.jar [--work build/smoke-chozas-mago]
Deterministic: each hut is placed with /place template (on a slab, in forceloaded chunks) and the probabilities
are set in the configuration (wizard_huts.prob_malvado and prob_botin_premium at 0 or 100, with /heraldia reload in
between); a Carpet simulated player (in survival, with resistance V so it does not die).
First start (evil 0 %, prize 0 %):
  1. Hut A (kindly): the wizard has its generated name, the kindly tag and its trades (vials, lapis lazuli,
     potions, book, pearl); the player approaches and even tries to trade: it is not revealed. /heraldia wizard lists it.
  2. Hut B: /heraldia wizard reveal (forced): the villager disappears, the Evil Wizard appears (an evoker with its name, the
     boss tags and its normal loot table) with 3 vexes; the player defeats it with /damage: it drops loot (without the
     vanilla totem), its vexes dissolve, the advancement is granted and the log reports it. A second command reveals nothing.
  3. Prize at 100 % (reload) and hut C forced: its table is the prize one; on defeating it the log says "premio: sí".
  4. Evil at 100 % (reload): hut A stays kindly (the decision already made does not change); hut D is born evil
     unrevealed and reveals itself when the player approaches.
Second start (same world, nothing touched): D's Evil Wizard is still just one, A is still kindly with its
villager and nobody is revealed again; /heraldia status gives the huts line.
"""
import argparse, json, os, queue, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import village_terrain as at
from terralith_biomes import fetch
from trophies import CARPET

PLAYER = "Testigo"
WIZARD, EVIL, VEX = "heraldia_mago", "heraldia_mago_malvado", "heraldia_mago_vex"
Y = 100
SITES = {"A": (30000, 30000), "B": (30200, 30000), "C": (30400, 30000), "D": (30600, 30000)}
TEMPLATE = {"A": "oscuro/a", "B": "pantano/b", "C": "taiga/a", "D": "desierto/b"}
FAR = (30300, 30400)            # where the player waits between tests (more than 100 blocks from all of them)
DEFEATED = re.compile(r"Mago Malvado vencido en (-?\d+) (-?\d+) (-?\d+) \(premio: (sí|no)\)")
REVEALS = re.compile(r"el mago de (-?\d+) (-?\d+) (-?\d+) se revela \((forzado|malvado); premio: (sí|no); (\d) vexes\)")


def halt(proc, ctx):
    """Stops the server and moves to ctx.seen what it wrote when stopping."""
    at.stop(proc)
    while True:
        try:
            line = ctx.lines.get(timeout=30)
        except queue.Empty:
            return
        if line is None:
            return
        ctx.seen.append(line)


def state(ctx, pattern):
    """The first line of /heraldia status (going through its pages) that matches `pattern`, or None."""
    pat = re.compile(pattern)
    for page in range(1, 8):
        m = ctx.run(f"execute as {PLAYER} at @s run heraldia status {page}",
                    r"server status \(page (\d+) of (\d+)\)|estado del servidor \(página (\d+) de (\d+)\)")
        for line in s.drain(ctx):
            if pat.search(line):
                return pat.search(line)
        if (m.group(1) or m.group(3)) == (m.group(2) or m.group(4)):
            return None
    return None


def configure(work, evil, prize):
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump({"chozas_mago": {"prob_malvado": evil, "prob_botin_premium": prize}}, f)


def box(c, extra=0):
    x, z = SITES[c]
    return f"x={x - extra},y={Y - 4},z={z - extra},dx={17 + 2 * extra},dy=24,dz={17 + 2 * extra}"


def place(ctx, c):
    x, z = SITES[c]
    ctx.run(f"forceload add {x - 16} {z - 16} {x + 32} {z + 32}", r"Marked|[Aa]dded|force|already")
    ctx.until(f"execute if loaded {x} {Y} {z}")
    ctx.run(f"fill {x} {Y - 1} {z} {x + 16} {Y - 1} {z + 16} minecraft:stone", r"Successfully filled|No blocks")
    ctx.run(f"place template heraldia:medianas/choza_mago/{TEMPLATE[c]} {x} {Y} {z}", r"Loaded template")
    return ctx.wait_entity(f"@e[tag={WIZARD},{box(c)}]")


def go(ctx, x, y, z):
    ctx.run(f"tp {PLAYER} {x} {y} {z}", r"Teleported")


def far(ctx):
    ctx.run(f"forceload add {FAR[0] - 8} {FAR[1] - 8} {FAR[0] + 8} {FAR[1] + 8}", r"Marked|[Aa]dded|force|already")
    ctx.run(f"fill {FAR[0] - 2} {Y - 1} {FAR[1] - 2} {FAR[0] + 2} {Y - 1} {FAR[1] + 2} minecraft:stone", r"Successfully filled|No blocks")
    go(ctx, FAR[0], Y, FAR[1])


def beside_wizard(ctx, c):
    """The player enters through the hut's door (3 blocks from the wizard, in the middle of the ground floor)."""
    x, z = SITES[c]
    h = 3 if TEMPLATE[c].startswith("pantano") else 0
    go(ctx, x + 6.5, Y + h + 1, z + 6.5)


def inventory(ctx, item="*"):
    """How many items (or of which one) the player carries."""
    m = ctx.run(f"clear {PLAYER} {item} 0", r"Found (\d+) matching|No items")
    return int(m.group(1) or 0)


def tag_of(ctx, c, tag):
    return ctx.count(f"@e[tag={WIZARD},tag={tag},{box(c)}]")


def offer(ctx, c, i, field):
    m = ctx.run(f"data get entity @e[tag={WIZARD},{box(c)},limit=1] Offers.Recipes[{i}].{field}",
                r'has the following entity data: "([^"]+)"|Found no elements|No entity')
    return m.group(1)


def benign(ctx, fails):
    if not place(ctx, "A"):
        fails.append("hut A: the wizard does not appear")
        return
    ctx.ticks(5)
    if tag_of(ctx, "A", "heraldia_mago.benigno") != 1 or tag_of(ctx, "A", "heraldia_mago.nombrado") != 1:
        fails.append("hut A: the wizard is not decided (kindly) and named on loading")
    name = ctx.run(f"data get entity @e[tag={WIZARD},{box('A')},limit=1] CustomName", r"entity data: (.*)").group(1)
    print(f"mago de A: {name.strip()[:160]}")
    if "heraldia.chozas_mago.nombre" not in name or "heraldia.chozas_mago.apodo." not in name:
        fails.append(f"hut A: the wizard does not carry its generated name: {name[:120]}")
    trades = [offer(ctx, "A", i, "sell.id") for i in range(8)]
    print(f"tratos de A: {trades}")
    expected_items = ["minecraft:glass_bottle", "minecraft:lapis_lazuli", "minecraft:potion", "minecraft:potion",
                 "minecraft:potion", "minecraft:enchanted_book", "minecraft:ender_pearl", "minecraft:emerald"]
    if trades != expected_items:
        fails.append(f"choza A: tratos {trades} (esperados {expected_items})")
    beside_wizard(ctx, "A")
    x, z = SITES["A"]
    s.send(ctx.proc, f"player {PLAYER} look at {x + 6.5} {Y + 1.6} {z + 8.5}")
    s.send(ctx.proc, f"player {PLAYER} use once")      # does not answer on the console
    ctx.ticks(60)
    if ctx.count(f"@e[tag={WIZARD},{box('A')}]") != 1 or ctx.count(f"@e[tag={EVIL}]"):
        fails.append("hut A (kindly): the wizard has been revealed or has disappeared with the player next to it")
    m = ctx.run(f"execute positioned {x + 6} {Y} {z + 8} run heraldia wizard", r"(?:Wizards within|Magos a menos de) 32 (?:blocks|bloques): (\d+)")
    lst = "".join(s.drain(ctx))
    if m.group(1) != "1" or not re.search(r"benign|bondadoso", lst):
        fails.append(f"/heraldia wizard junto a A: {m.group(0)} {lst[-200:]}")
    far(ctx)


def defeat(ctx, fails, c, prize):
    """Reveals (forced) the wizard of hut c, checks the Evil Wizard and the player defeats it."""
    if not place(ctx, c):
        fails.append(f"hut {c}: the wizard does not appear")
        return
    x, z = SITES[c]
    beside_wizard(ctx, c)      # with the player nearby: the vexes are not persistent (far from everyone, they disappear)
    ctx.run(f"clear {PLAYER}", r"Removed|No items")
    ctx.ticks(5)
    mark = len(ctx.seen)
    ctx.run(f"execute positioned {x + 6} {Y} {z + 8} run heraldia wizard reveal",
            r"Wizard revealed at|Mago revelado en|no unrevealed wizard|ningún mago sin revelar")
    m = s.wait_for(ctx.lines, REVEALS.pattern, s.COMMAND_TIMEOUT_S, ctx.seen) if not REVEALS.search("".join(ctx.seen[mark:])) \
        else REVEALS.search("".join(ctx.seen[mark:]))
    print(f"choza {c}: {m.group(0)}")
    if m.group(4) != "forzado" or m.group(5) != ("sí" if prize else "no") or m.group(6) != "3":
        fails.append(f"hut {c}: reveal {m.group(0)}")
    sel = f"@e[type=minecraft:evoker,tag={EVIL},{box(c, 4)}]"
    if ctx.count(sel) != 1:
        fails.append(f"choza {c}: {ctx.count(sel)} Magos Malvados (debe haber 1)")
    if ctx.count(f"@e[tag={WIZARD},{box(c)}]"):
        fails.append(f"hut {c}: the villager is still there after being revealed")
    for t in ("heraldia_guardian", "heraldia_anclado"):
        if ctx.count(f"@e[type=minecraft:evoker,tag={EVIL},tag={t}]") != 1:
            fails.append(f"hut {c}: the Evil Wizard lacks the {t} tag (phases and boss bar)")
    vexes = ctx.count(f"@e[type=minecraft:vex,tag={VEX}]")
    if vexes != 3:
        fails.append(f"choza {c}: {vexes} vexes de entrada (deben ser 3)")
    tbl = ctx.run(f"data get entity {sel[:-1]},limit=1] DeathLootTable", r'entity data: "([^"]+)"|No entity').group(1)
    if tbl != ("heraldia:chozas_mago/malvado_premium" if prize else "heraldia:chozas_mago/malvado"):
        fails.append(f"hut {c}: Evil Wizard loot table {tbl}")
    name = ctx.run(f"data get entity {sel[:-1]},limit=1] CustomName", r"entity data: (.*)|No entity").group(1) or ""
    if "heraldia.chozas_mago.malvado" not in name:
        fails.append(f"hut {c}: the Evil Wizard is not named that: {name[:100]}")
    # another command reveals nothing more (no unrevealed wizard left within 32 blocks)
    ctx.run(f"execute positioned {x + 6} {Y} {z + 8} run heraldia wizard reveal",
            r"no unrevealed wizard|ningún mago sin revelar|Wizard revealed at|Mago revelado en")
    if ctx.count(f"@e[type=minecraft:evoker,tag={EVIL}]") != 1:
        fails.append(f"hut {c}: a second reveal duplicates the Evil Wizard")
    # the player defeats it
    p = ctx.pos(sel)
    ctx.ticks(20)
    mark = len(ctx.seen)
    ctx.run(f"damage {sel[:-1]},limit=1] 2000 minecraft:player_attack by {PLAYER}", r"Applied|damage|No entity")
    v = s.wait_for(ctx.lines, DEFEATED.pattern, s.COMMAND_TIMEOUT_S, ctx.seen) if not DEFEATED.search("".join(ctx.seen[mark:])) \
        else DEFEATED.search("".join(ctx.seen[mark:]))
    ctx.ticks(20)
    nearby_flag = f"x={p[0]:.0f},y={p[1]:.0f},z={p[2]:.0f},distance=..10"
    # what drops and what the player has already picked up
    items = ctx.count(f"@e[type=minecraft:item,{nearby_flag}]") + inventory(ctx)
    totems = ctx.count(f"@e[type=minecraft:item,{nearby_flag},nbt={{Item:{{id:\"minecraft:totem_of_undying\"}}}}]") \
        + inventory(ctx, "minecraft:totem_of_undying")
    print(f"hut {c}: {v.group(0)}; {items} items on the ground ({totems} totems)")
    if v.group(4) != ("sí" if prize else "no"):
        fails.append(f"hut {c}: {v.group(0)} (prize {'sí' if prize else 'no'})")
    if items < 2:
        fails.append(f"hut {c}: the Evil Wizard drops {items} items")
    if not prize and totems:
        fails.append(f"hut {c}: without a prize it drops a totem (the vanilla evoker's must not appear)")
    if ctx.count(f"@e[type=minecraft:vex,tag={VEX}]"):
        fails.append(f"hut {c}: wizard's vexes remain after defeating it")
    if not ctx.test(f"execute if entity @a[name={PLAYER},advancements={{heraldia:medianas/choza_mago/malvado=true}}]"):
        fails.append("advancement medianas/choza_mago/malvado not granted")
    ctx.run(f"kill @e[type=minecraft:item,{nearby_flag}]", r"Killed|No entity")
    far(ctx)


def natural(ctx, fails):
    """Evil at 100 %: A stays kindly; D is born evil and reveals itself when the player arrives."""
    beside_wizard(ctx, "A")
    ctx.ticks(60)
    if ctx.count(f"@e[tag={WIZARD},tag=heraldia_mago.benigno,{box('A')}]") != 1 or ctx.count(f"@e[tag={EVIL},{box('A', 4)}]"):
        fails.append("hut A: with evil at 100 % the already decided hut changes")
    far(ctx)
    if not place(ctx, "D"):
        fails.append("hut D: the wizard does not appear")
        return
    ctx.ticks(5)
    if tag_of(ctx, "D", "heraldia_mago.malvado") != 1 or ctx.count(f"@e[tag={EVIL},{box('D', 4)}]"):
        fails.append("hut D: is not born evil and unrevealed")
    mark = len(ctx.seen)
    beside_wizard(ctx, "D")
    m = s.wait_for(ctx.lines, REVEALS.pattern, s.COMMAND_TIMEOUT_S, ctx.seen) if not REVEALS.search("".join(ctx.seen[mark:])) \
        else REVEALS.search("".join(ctx.seen[mark:]))
    print(f"choza D: {m.group(0)}")
    if m.group(4) != "malvado":
        fails.append(f"choza D: {m.group(0)}")
    ctx.ticks(10)
    if ctx.count(f"@e[type=minecraft:evoker,tag={EVIL},{box('D', 4)}]") != 1 or ctx.count(f"@e[tag={WIZARD},{box('D')}]"):
        fails.append("hut D: when the player approaches it does not turn into the Evil Wizard")
    far(ctx)


def player(ctx):
    far_x, far_z = FAR
    ctx.run(f"forceload add {far_x - 8} {far_z - 8} {far_x + 8} {far_z + 8}", r"Marked|[Aa]dded|force|already")
    ctx.run(f"player {PLAYER} spawn at {far_x} {Y + 2} {far_z}", r"joined the game")
    if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
        raise SystemExit(f"the simulated player {PLAYER} does not appear (Carpet)")
    s.send(ctx.proc, f"gamemode survival {PLAYER}")      # may not answer if it already is
    ctx.until(f"execute if entity @a[name={PLAYER},gamemode=survival]")
    ctx.run(f"effect give {PLAYER} minecraft:resistance infinite 4 true", r"Applied effect|Gave|Unable to apply")
    ctx.run(f"effect give {PLAYER} minecraft:regeneration infinite 4 true", r"Applied effect|Gave|Unable to apply")
    far(ctx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-chozas-mago"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    configure(a.work, 0, 0)
    proc, ctx = at.start_server(a.work, launcher)
    try:
        player(ctx)
        benign(ctx, fails)
        defeat(ctx, fails, "B", prize=False)
        configure(a.work, 0, 100)
        ctx.run("heraldia reload", r"Heraldia: configuración recargada")
        defeat(ctx, fails, "C", prize=True)
        configure(a.work, 100, 100)
        ctx.run("heraldia reload", r"Heraldia: configuración recargada")
        natural(ctx, fails)
        ctx.run(f"player {PLAYER} kill", r"left the game")
    finally:
        halt(proc, ctx)
    revealed = len(REVEALS.findall(ctx.log()))
    # second start: nothing is revealed again or duplicated
    proc, ctx = at.start_server(a.work, launcher)
    try:
        player(ctx)
        ctx.until(f"execute if entity @e[type=minecraft:evoker,tag={EVIL}]")
        ctx.ticks(20)
        bad_many = ctx.count(f"@e[type=minecraft:evoker,tag={EVIL}]")
        enD = ctx.count(f"@e[type=minecraft:evoker,tag={EVIL},{box('D', 8)}]")
        print(f"after restarting: {bad_many} Evil Wizards ({enD} at D); reveals in the first start: {revealed}")
        if bad_many != 1 or enD != 1:
            fails.append(f"after restarting: {bad_many} Evil Wizards, {enD} at D (only D's must remain)")
        if ctx.count(f"@e[tag={WIZARD},tag=heraldia_mago.benigno,{box('A')}]") != 1:
            fails.append("after restarting: A's kindly wizard is missing")
        beside_wizard(ctx, "A")
        ctx.ticks(60)
        if REVEALS.search(ctx.log()) or ctx.count(f"@e[tag={WIZARD},{box('A')}]") != 1:
            fails.append("after restarting: a wizard reveals itself again")
        if state(ctx, r"Wizard's huts: evil wizards 100 %, premium loot 100 %|Chozas de mago: magos malvados 100 %") is None:
            fails.append("/heraldia status without the wizard huts line")
        ctx.run(f"player {PLAYER} kill", r"left the game")
    finally:
        halt(proc, ctx)
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: kindly wizard with trades that does not reveal itself, Evil Wizard forced with vexes and defeated (loot without totem, "
          "logro), premio al 100 %, decisión guardada, revelación al acercarse y reinicio sin duplicados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
