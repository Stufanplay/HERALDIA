"""Guardian trophies on a real dedicated 26.3 server, with a simulated player (complements server_smoke.py).

Usage: python3 tools/smoke/trophies.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Without a client there are no players and the killed_by_player condition is never met from the console: this test adds
Carpet (pinned Modrinth version, checked against its sha512) and creates a simulated player with /player. For each
guardian (heraldia:guardianes/<id>/<mob> tables in the .jar) it summons its mob type with that DeathLootTable and:
  - kills it with /kill (no player): the trophy does not drop;
  - the player kills it (damage ... by <player>): a single trophy drops with its custom_data, its translatable name, its lore
    and its rarity;
  - the player picks it up: the heraldia:unicas/trofeos challenge progresses, and is only granted with all of them.
That the guardian placed with /place structure keeps that DeathLootTable is checked by server_smoke.py.
"""
import argparse, json, os, queue, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from modrinth import MODS, fetch

# Carpet (simulated player), pinned in modrinth.py: (file, url, sha512) for fetch()
CARPET = (MODS["carpet"].file, MODS["carpet"].url, MODS["carpet"].sha512)
PLAYER = "Testigo"
X, Y, Z = 0, 101, 0            # player on a platform; the mobs at MOB_DZ blocks (it does not pick up what drops)
MOB_DZ = 6
ADV = "heraldia:unicas/trofeos"
ITEMS = "@e[type=minecraft:item]"


def trophies(jar):
    """{id: (mob, death table, item, rarity)} and en_us texts, read from the .jar (in CI there is no build/generated)."""
    out = {}
    with zipfile.ZipFile(jar) as z:
        names = z.namelist()
        lang = json.loads(z.read("assets/heraldia/lang/en_us.json"))
        for n in names:
            pre = "data/heraldia/loot_table/guardianes/"
            if n.startswith(pre) and n.endswith(".json"):
                sid, mob = n[len(pre):-5].split("/")
                trophy = json.loads(z.read(f"data/heraldia/loot_table/trofeos/{sid}.json"))
                entry = trophy["pools"][0]["entries"][0]
                rarity = next(m["components"]["minecraft:rarity"] for m in entry["modifier"] if m["type"].endswith("set_components"))
                out[sid] = (mob, f"heraldia:guardianes/{sid}/{mob}", entry["name"], rarity)
        adv = json.loads(z.read("data/heraldia/advancement/unicas/trofeos.json"))
    return dict(sorted(out.items())), lang, adv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-trofeos"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    found, lang, adv = trophies(a.jar)
    fails, ok = [], 0
    if sorted(adv["criteria"]) != sorted(found) or len(adv["requirements"]) != len(found):
        fails.append(f"the challenge {ADV} does not require exactly the {len(found)} trophies: {sorted(adv['criteria'])}")
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)

    test = ctx.test

    def until(cmd, want=True):
        return ctx.until(cmd, want)     # generous limit (s.UNTIL_S): CI is slow

    def settle():
        """The player, on the ground, with no recent hit and back at (X, Y, Z): no longer sliding or flying."""
        quiet = f"execute if entity @a[name={PLAYER},nbt={{OnGround:1b,HurtTime:0s}}]"
        if not until(quiet):
            return False
        ctx.run(f"tp {PLAYER} {X + 0.5} {Y} {Z + 0.5}", r"Teleported")
        return until(f"execute if entity @a[name={PLAYER},x={X + 0.5},y={Y},z={Z + 0.5},distance=..0.01]") and until(quiet)

    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {X - 3} {Y - 1} {Z - 3} {X + 3} {Y - 1} {Z + MOB_DZ + 3} minecraft:stone", r"Successfully filled|No blocks|not loaded(?! yet)")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        s.require_carpet(ctx)
        ctx.run(f"player {PLAYER} spawn at {X} {Y} {Z}", r"joined the game|Player .* spawn")
        if not until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"the simulated player {PLAYER} does not appear (Carpet)")
        ctx.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
        # No natural monsters or night: the simulated player (in survival) must not depend on the time of day.
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        mz = Z + MOB_DZ
        for i, (sid, (mob, table, item, rarity)) in enumerate(found.items()):
            mark = f'{{"minecraft:custom_data":{{heraldia_trofeo:"{sid}"}}}}'
            near = f"@e[type=minecraft:item,x={X},y={Y},z={mz},distance=..3,nbt={{Item:{{components:{mark}}}}}]"
            summon = (f'summon minecraft:{mob} {X} {Y} {mz} {{NoAI:1b,PersistenceRequired:1b,Tags:["heraldia_prueba"],'
                      f'DeathLootTable:"{table}"}}')
            # 1) no player: /kill does not drop the trophy
            ctx.run(f"kill {ITEMS}", r"Killed|No entity was found")
            ctx.run(summon, r"Summoned")
            ctx.run("kill @e[tag=heraldia_prueba]", r"Killed|No entity was found")
            ctx.ticks(20)           # the loot drops on death: one second of play is enough to see it (in ticks, not wall-clock)
            if test(f"execute if entity {near}"):
                fails.append(f"{sid}: /kill (no player) drops the trophy")
            else:
                ok += 1
            # 2) the player kills it: a single trophy with its name, lore, rarity and custom_data
            ctx.run(f"kill {ITEMS}", r"Killed|No entity was found")
            ctx.run(summon, r"Summoned")
            ctx.run(f"damage @e[tag=heraldia_prueba,limit=1] 2000 minecraft:player_attack by {PLAYER}", r"Applied|damage")
            if not until(f"execute if entity {near}"):
                fails.append(f"{sid}: killed by the player it does not drop the trophy")
                continue
            m = ctx.run(f"execute if entity {near}", r"Test passed\. Count: (\d+)|Test failed")
            if m.group(1) != "1":
                fails.append(f"{sid}: {m.group(1)} trophies on the ground (must be 1)")
            m = ctx.run(f"data get entity {near.replace(']', ',limit=1]')} Item", r"has the following entity data: (.*)|No entity")
            data = (m.group(1) or "").replace("\\", "")
            key = f"heraldia.trofeo.{sid}"
            want = [f'id: "{item}"', f'"{key}"', f'"{key}.lore1"', 'heraldia_trofeo: "' + sid]
            missing = [w for w in want if w not in data]
            # the rarity is read from the effective components (if it is the item's default it does not show in the data)
            if not test(f'execute if items entity {near.replace("]", ",limit=1]")} contents {item}[minecraft:rarity="{rarity}"]'):
                missing.append(f"rareza {rarity}")
            if missing or key not in lang:
                fails.append(f"{sid}: trophy without {missing or 'en_us text'}: {data[:300]}")
            else:
                ok += 1
            # 3) the player picks it up (the /tp message shows the name the player sees: item_name in en_us) and the
            #    challenge is only granted with the last trophy
            # The elder guardian's thorns (Guardian.hurtServer: 2 damage to the melee attacker if it does not
            # move, always with NoAI) push the player ~2 blocks: before bringing the trophy close, wait for it to
            # land and its invulnerability to pass (HurtTime 0) and put it back in place, still.
            if not settle():
                fails.append(f"{sid}: the player does not stand still after the hit")
                continue
            m = ctx.run(f"tp {near} {PLAYER}", r"Teleported (.+) to |No entity")
            if m.group(1) != lang.get(key):
                fails.append(f"{sid}: the trophy shows as '{m.group(1)}', not '{lang.get(key)}'")
            if not until(f"execute if entity @a[name={PLAYER},advancements={{{ADV}={{{sid}=true}}}}]"):
                fails.append(f"{sid}: picked up, does not count for {ADV}")
                mark_sel = f"@e[type=minecraft:item,nbt={{Item:{{components:{mark}}}}},limit=1]"
                for q in (f"data get entity {mark_sel}", f"data get entity {PLAYER} Pos", f"data get entity {PLAYER} Inventory",
                          f"data get entity {PLAYER} Health"):
                    print("DIAG", ctx.run(q, r"entity data: .*|No entity").group(0)[:300])
            elif test(f"execute if entity @a[name={PLAYER},advancements={{{ADV}=true}}]") != (i == len(found) - 1):
                fails.append(f"{sid}: {ADV} granted too early or not granted at the end")
            else:
                ok += 1
            print(f"trofeo {sid}: {lang.get(f'heraldia.trofeo.{sid}')} ({item}, {mob})")
        # clean-up before stopping: a player already gone ("Can only manipulate existing players") is as good as one
        # that leaves; the `.` this pattern used to end in accepted any line at all, so it waited for nothing
        ctx.run(f"player {PLAYER} kill", r"left the game|Can only manipulate existing players")
    finally:
        if proc.poll() is None:
            s.send(proc, "stop")
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
    log = os.path.join(a.work, "logs", "latest.log")
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else "".join(seen)
    for bad in ("Registry loading errors", "Failed to load datapacks", "Couldn't load", "Failed to parse",
                "Found validation problems"):
        if bad in text:
            fails.append(f"the log contains {bad!r}")
    print("TROFEOS:", f"OK ({len(found)} trofeos, {ok} comprobaciones)" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
