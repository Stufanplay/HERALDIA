"""Template mobs that could spawn as babies, on a real 26.3 dedicated server (complements server_smoke.py).

Usage: python3 tools/smoke/adult_guardians.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke" [--times N]
Template mobs go through finalizeSpawn when placed as a structure piece, and the zombie one (zombie,
husk, drowned, zombie villager, zombified piglin) rolls for a baby (5 %, sometimes on a chicken) ignoring the NBT's IsBaby,
sometimes changes the weapon (drowned: trident or fishing rod 10 %) and mounts a zombie nautilus on half of the drowned with a
trident. The mod prevents this for those carrying the heraldia_adulto tag (core.ADULT_TAG; validate.py requires that
every mob of that type carries it). For each distinct mob of that type in the .jar templates (the castle guardians,
the Jarl's Hall, the galleon, the pyramid, the colosseum, the lighthouse, the aqueduct and the Atlantis drowned)
it writes a data pack with a minimal template (a stone block with a jigsaw on top that gets removed) with that mob
as is and its pool, places it --times times with /place jigsaw (pool piece: same path as when generating, with
finalizeSpawn; /place template does not call it) and checks that all of them appear, that none is a baby, that there are no mounts
or other new entities and that all keep their template's weapon.
"""
import argparse, gzip, io, json, os, queue, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import nbtlib
from nbtlib.tag import Compound
import core

BABIES = ("zombie", "husk", "drowned", "zombie_villager", "zombified_piglin")
PACK, NS, ANCHOR_POINT = "heraldia_prueba_adultos", "heraldia_prueba", "heraldia_prueba:ancla"
X0, Y, Z0 = 0, 150, 0           # grid of placements on a platform in the air (forced chunks)
COLS, STEP = 20, 3


def mobs(jar):
    """[(name, nbt)]: one mob for each distinct NBT (without position) of the types that can be babies in the .jar templates."""
    out, seen = [], set()
    with zipfile.ZipFile(jar) as z:
        for n in sorted(z.namelist()):
            if not (n.startswith("data/heraldia/structure/") and n.endswith(".nbt")):
                continue
            t = nbtlib.File.parse(io.BytesIO(gzip.decompress(z.read(n))))
            for e in t.get("entities", []):
                nbt = Compound(e["nbt"])
                mob = str(nbt["id"]).split(":")[-1]
                if mob not in BABIES:
                    continue
                nbt.pop("Pos", None)
                nbt.pop("UUID", None)
                key = nbt.snbt()
                if key not in seen:
                    seen.add(key)
                    out.append((f"{n[len('data/heraldia/structure/'):-4]} ({mob})", nbt))
    return out


def write_pack(work, found, times):
    """Data pack in world/datapacks (the server enables it when creating the world): per mob, a template
    (jigsaw + the mob on top), its pool and a function with the placements."""
    root = os.path.join(work, "world", "datapacks", PACK)
    with open(os.path.join(os.makedirs(root, exist_ok=True) or root, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "Heraldia: prueba de mobs adultos", "min_format": 121, "max_format": 121}}, f)
    data = os.path.join(root, "data", NS)
    for d in ("structure", "worldgen/template_pool", "function"):
        os.makedirs(os.path.join(data, d), exist_ok=True)
    for i, (_, nbt) in enumerate(found):
        t = core.Template(f"m{i}")
        t.set(0, 0, 0, "minecraft:stone")       # its own floor: it does not depend on the platform
        t.jigsaw(0, 1, 0, "up_north", ANCHOR_POINT, "minecraft:empty", "minecraft:empty", joint="rollable")
        t.entity(0, 1, 0, nbt)
        nbtlib.File(t.to_nbt(), gzipped=True).save(os.path.join(data, "structure", f"m{i}.nbt"))
        with open(os.path.join(data, "worldgen", "template_pool", f"m{i}.json"), "w") as f:
            json.dump({"fallback": "minecraft:empty", "elements": [{"weight": 1, "element": {
                "element_type": "minecraft:single_pool_element", "location": f"{NS}:m{i}",
                "projection": "rigid", "processors": "minecraft:empty"}}]}, f)
        with open(os.path.join(data, "function", f"m{i}.mcfunction"), "w") as f:
            for k in range(times):
                f.write(f"place jigsaw {NS}:m{i} {ANCHOR_POINT} 1 {X0 + (k % COLS) * STEP} {Y} {Z0 + (k // COLS) * STEP}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke"))
    ap.add_argument("--times", type=int, default=200)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    found = mobs(a.jar)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    write_pack(a.work, found, a.times)
    proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    fails = []
    x1, z1 = X0 + COLS * STEP, Z0 + (a.times // COLS + 1) * STEP
    area = f"x={X0 - 2},y={Y - 4},z={Z0 - 2},dx={x1 - X0 + 4},dy=12,dz={z1 - Z0 + 4}"

    def count(sel):
        m = ctx.run(f"execute if entity {sel}", r"Test passed\. Count: (\d+)|Test failed")
        return int(m.group(1) or 0)

    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        m = ctx.run("datapack list enabled", r"data pack\(s\) enabled: (.*)|no data packs")
        if PACK not in m.group(0):
            raise SystemExit(f"test pack {PACK} is not enabled: {m.string.strip()}")
        ctx.run(f"forceload add {X0 - 2} {Z0 - 2} {x1 + 2} {z1 + 2}", r"Marked|Added|force|already")
        for _ in range(s.PLACE_ATTEMPTS):   # forced chunks take a while to load
            m = ctx.run(f"fill {X0 - 2} {Y - 1} {Z0 - 2} {x1 + 2} {Y - 1} {z1 + 2} minecraft:stone", r"Successfully filled|No blocks|not loaded(?! yet)")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        # Barrier fence around the platform (and a ceiling at 5): the mobs have AI and, without it, some could fall
        # over the edge between two counts and be missing from the area ("N of 200 placed" or "with another weapon" without being so).
        ctx.run(f"fill {X0 - 3} {Y - 1} {Z0 - 3} {x1 + 3} {Y + 5} {z1 + 3} minecraft:barrier outline",
                r"Successfully filled|No blocks")
        # At night and with time not advancing: in sunlight they burn, and the test (one mob after another) can outlast the night.
        ctx.run("time set midnight", r"Set .*time")
        ctx.run("gamerule advance_time false", r"[Gg]ame ?rule .*advance_time")
        print(f"adults: {len(found)} distinct mobs with a possible baby in the templates")
        for i, (name, nbt) in enumerate(found):
            mob = str(nbt["id"])
            adult = "heraldia_adulto" in [str(t) for t in nbt.get("Tags", [])]
            t0 = time.monotonic()
            ctx.run(f"function {NS}:m{i}", r"Running function|Ran \d+ command")
            sel = f"@e[type={mob},{area}]"
            total = 0
            end = time.monotonic() + s.UNTIL_S
            while True:                     # the piece's entities take a bit longer than the blocks
                total = count(sel)
                if total >= a.times or time.monotonic() > end:
                    break
                time.sleep(s.POLL_S)
            babies = count(f"@e[type={mob},{area},nbt={{IsBaby:1b}}]")
            mounts = count(f"@e[type=!{mob},type=!minecraft:item,{area}]")     # gallinas, nautilos zombis...
            hand = str(nbt.get("equipment", {}).get("mainhand", {}).get("id", ""))
            swapped = total - count(f'@e[type={mob},{area},nbt={{equipment:{{mainhand:{{id:"{hand}"}}}}}}]') if hand else 0
            print(f"adults: {name}: {total} placed, {babies} babies, {mounts} mounts, {swapped} with another weapon "
                  f"(heraldia_adulto: {'sí' if adult else 'no'}, {time.monotonic() - t0:.1f} s)")
            if total != a.times:
                fails.append(f"{name}: {total} de {a.times} colocados")
            if babies or mounts or swapped:
                fails.append(f"{name}: {babies} babies, {mounts} mounts and {swapped} without their weapon ({hand}) out of {total}")
            ctx.run(f"kill @e[type=!minecraft:player,{area}]", r"Killed|No entity was found")
            ctx.run(f"kill @e[type=minecraft:item,{area}]", r"Killed|No entity was found")
    finally:
        try:
            s.send(proc, "stop")
            proc.wait(timeout=120)
        except Exception:
            proc.kill()
    if not found:
        fails.append("there are no mobs with a possible baby in the templates: the test checks nothing")
    if fails:
        print("FALLOS:\n- " + "\n- ".join(fails))
        sys.exit(1)
    print("adultos: OK")


if __name__ == "__main__":
    main()
