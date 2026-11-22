"""Chronicle of the Heralds on a real 26.3 dedicated server, with a simulated player (complements server_smoke.py).

Usage: python3 tools/smoke/story.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Reads from the .jar (in CI there is no build/generated) the sheet of each unique structure (heraldia:historia/<id>), the table of the
chest that holds it (heraldia:unicas/<id>/<chest>) and the heraldia:unicas/cronista challenge, and checks:
  - without a server: the chain is a single cycle that goes through all the unique structures, the final unique structure closes it (it points to the first)
    and each sheet comes with the treasure map of the unique structure it points to;
  - on the server: `/loot spawn` of each unique structure's chest table drops a single sheet with its custom_data, its translatable
    pages (those of its tale and the one that points to the next) and its translatable name; the simulated player
    (Carpet, like trophies.py) picks it up and the challenge progresses, and is only granted with the last one.
"""
import argparse, json, os, queue, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from terralith_biomes import fetch
from trophies import CARPET

PLAYER = "Testigo"          # the one from trophies.py (Carpet takes the spelling from the Mojang profile)
X, Y, Z = 0, 101, 0            # player on a platform; the items ITEM_DZ blocks away (it does not pick them up by itself)
ITEM_DZ = 6
ADV = "heraldia:unicas/cronista"
MARK = "heraldia_historia"


def chronicle(jar):
    """{id: {"cofre": chest table, "libro": sheet components, "mapa": map entry, "siguiente": id}},
    en_us texts and the advancement, read from the .jar."""
    out = {}
    with zipfile.ZipFile(jar) as z:
        names = z.namelist()
        lang = json.loads(z.read("assets/heraldia/lang/en_us.json"))
        pre = "data/heraldia/loot_table/historia/"
        for n in names:
            if n.startswith(pre) and n.endswith(".json"):
                sid = n[len(pre):-5]
                t = json.loads(z.read(n))
                book = t["pools"][0]["entries"][0]["modifier"][0]["components"]
                last = book["minecraft:written_book_content"]["pages"][-1]["raw"]
                nxt = last["with"][2]["translate"].split(".")[2]
                chest = [c for c in names if c.startswith(f"data/heraldia/loot_table/unicas/{sid}/") and
                         f'"heraldia:historia/{sid}"' in z.read(c).decode()]
                out[sid] = {"cofre": [c[len("data/heraldia/loot_table/"):-5] for c in chest], "libro": book,
                            "mapa": t["pools"][1]["entries"][0] if len(t["pools"]) > 1 else None, "siguiente": nxt,
                            "final": last["translate"] == "heraldia.historia.final"}
        adv = json.loads(z.read("data/heraldia/advancement/unicas/cronista.json"))
        for sid in out:   # Nether and End uniques (T44) are placed by heraldia:dimension
            st = f"data/heraldia/worldgen/structure/unicas/{sid}.json"
            out[sid]["overworld"] = st not in names or json.loads(z.read(st)).get("type") != "heraldia:dimension"
    return dict(sorted(out.items())), lang, adv


def static_checks(found, adv):
    fails = []
    if sorted(adv["criteria"]) != sorted(found) or len(adv["requirements"]) != len(found):
        fails.append(f"the challenge {ADV} does not ask for exactly the {len(found)} sheets: {sorted(adv['criteria'])}")
    finals = [sid for sid, d in found.items() if d["final"]]
    if len(finals) != 1:
        fails.append(f"there must be a single final sheet: {finals}")
    seen, sid = [], next(iter(found))
    while sid in found and sid not in seen:   # walks the chain from any sheet
        seen.append(sid)
        sid = found[sid]["siguiente"]
    if sorted(seen) != sorted(found):
        fails.append(f"the chain does not go through all the unique structures: {seen}")
    for sid, d in found.items():
        if len(d["cofre"]) != 1:
            fails.append(f"{sid}: the sheet must go in the table of a chest of the unique structure, not in {d['cofre']}")
        dest = ((d["mapa"] or {}).get("modifier") or [{}])[0].get("destination")
        nxt = found.get(d["siguiente"], {})
        if not d["overworld"] or not nxt.get("overworld", True):
            # an exploration map only searches its own dimension: no map to or from the Nether and the End (writer.py)
            if d["mapa"] is not None:
                fails.append(f"{sid}: the sheet carries a map although {sid} or {d['siguiente']} is not in the Overworld ({dest})")
        elif dest != f"#heraldia:unicas/{d['siguiente']}":
            fails.append(f"{sid}: the sheet's map does not lead to {d['siguiente']} ({dest})")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-historia"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    found, lang, adv = chronicle(a.jar)
    fails = static_checks(found, adv)
    ok = 0
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

    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {X - 3} {Y - 1} {Z - 3} {X + 3} {Y - 1} {Z + ITEM_DZ + 3} minecraft:stone", r"Successfully filled|No blocks|not loaded(?! yet)")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        ctx.run(f"player {PLAYER} spawn at {X} {Y} {Z}", r"joined the game|Player .* spawn|Unknown|Incorrect")
        if not until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"simulated player {PLAYER} (Carpet) does not appear")
        ctx.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
        # No natural monsters or night: the simulated player (in survival) must not depend on the time of day.
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        iz = Z + ITEM_DZ
        for i, (sid, d) in enumerate(found.items()):
            mark = f'{{"minecraft:custom_data":{{{MARK}:"{sid}"}}}}'
            near = f"@e[type=minecraft:item,x={X},y={Y},z={iz},distance=..3,nbt={{Item:{{components:{mark}}}}}]"
            # 1) the unique structure's chest (its real table) drops a single sheet
            ctx.run("kill @e[type=minecraft:item]", r"Killed|No entity was found")
            ctx.run(f"loot spawn {X} {Y} {iz} loot heraldia:{d['cofre'][0]}", r"Dropped|No ")
            if not until(f"execute if entity {near}"):
                fails.append(f"{sid}: the chest heraldia:{d['cofre'][0]} does not drop its sheet")
                continue
            m = ctx.run(f"execute if entity {near}", r"Test passed\. Count: (\d+)|Test failed")
            if m.group(1) != "1":
                fails.append(f"{sid}: {m.group(1)} pliegos (debe ser 1)")
            # 2) its translatable pages: those of the tale and the one that points to the next, with its hint
            m = ctx.run(f"data get entity {near.replace(']', ',limit=1]')} Item", r"has the following entity data: (.*)|No entity")
            data = (m.group(1) or "").replace("\\", "")
            k = f"heraldia.historia.{sid}"
            want = ['id: "minecraft:written_book"', f'"{k}.pagina1"', f'"heraldia.historia.{d["siguiente"]}.pista"',
                    '"heraldia.historia.nombre"', 'author: "Ysolda"', f'{MARK}: "{sid}"']
            missing = [w for w in want if w not in data] + [t for t in (f"{k}.pagina1", f"{k}.pista") if t not in lang]
            if missing:
                fails.append(f"{sid}: sheet without {missing}: {data[:300]}")
            else:
                ok += 1
            # 3) the player picks it up: it shows with its translated name (the mod's en_us on the server) and counts toward the
            #    challenge, which is only granted with the last one
            name = lang["heraldia.historia.nombre"] % lang[f"heraldia.unicas.{sid}.nombre"]
            m = ctx.run(f"tp {near} {PLAYER}", r"Teleported (.+) to |No entity")
            if m.group(1) != name:
                fails.append(f"{sid}: the sheet shows as '{m.group(1)}', not '{name}'")
            if not until(f"execute if entity @a[name={PLAYER},advancements={{{ADV}={{{sid}=true}}}}]"):
                fails.append(f"{sid}: picked up, does not count toward {ADV}")
            elif test(f"execute if entity @a[name={PLAYER},advancements={{{ADV}=true}}]") != (i == len(found) - 1):
                fails.append(f"{sid}: {ADV} granted too early or not granted at the end")
            else:
                ok += 1
            print(f"sheet {sid} (chest {d['cofre'][0]}) -> {d['siguiente']}")
        ctx.run(f"player {PLAYER} kill", r"left the game|Unknown|Incorrect|.")
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
    print("CHRONICLE:", f"OK ({len(found)} pliegos, {ok} comprobaciones)" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
