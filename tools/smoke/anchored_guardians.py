"""Anchored mobs (heraldia_anclado) on a real 26.3 dedicated server, with a simulated player (complements server_smoke.py).

Usage: python3 tools/smoke/anchored_guardians.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke" [--times N]
A persistent mob with AI wanders up to 10 blocks in the first 100 ticks of each load (RandomStrollGoal requires
noActionTime < 100, which is not saved) and sometimes left its room; and the finalizeSpawn of zombies and skeletons rolls
CanPickUpLoot ignoring the NBT. The mod (comun/Anclaje.java) prevents this for those carrying core.ANCHORED_TAG. With each
distinct mob carrying the tag in the .jar templates (the guardians and the Atlantis drowned):
  1) it places it --times times as a pool piece (/place jigsaw: finalizeSpawn, as when generating) in its cell of a
     platform, at night and on hard; none may pick up items and, after 200 ticks, all are still in their cell
     (±1.8 blocks; the elder guardian, in a pool, within the 16-block home the game gives it). A control batch without the tag (the same skeleton and the same zombie) must wander and pick up
     items at least once: otherwise the test would check nothing;
  2) it unloads and reloads the chunks (noActionTime goes back to 0) and, after another 200 ticks, they are still in their cell;
  3) with a simulated player (Carpet) 8 blocks away, each one attacks it (takes its health): anchored does not mean dumb
     (except the medium structures' animals, PEACEFUL, which attack no one);
  4) it places each guardian's real template by day (/place template; at night again those of the drowned) and, after
     200 ticks, it is still where the template puts it.
"""
import argparse, gzip, io, json, os, queue, shutil, subprocess, sys, threading, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from terralith_biomes import fetch
from trophies import CARPET
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import nbtlib
from nbtlib.tag import Compound, List, String
import core

PACK, NS, ANCHOR_POINT = "heraldia_prueba_anclados", "heraldia_prueba", "heraldia_prueba:ancla"
AQUATIC_MOBS = {"minecraft:guardian", "minecraft:elder_guardian"}    # out of water they flop around: they go in a pool
# Animals of the medium structures (the fisherman's cat, the hunters' wolf): anchored so they do not leave, but they do not
# attack anyone who does not attack them; in phase 3 they are not expected to attack.
PEACEFUL = {"minecraft:cat", "minecraft:wolf"}
Y = 150
X1, Z1, STEP, COLS = 2000, 0, 4, 10                  # phases 1 and 2: a block of COLS x rows of cells per mob
X3, Z3 = 4000, 0                                     # phase 3: player and mob
X4, Z4, Y4 = 6000, 0, 120                            # phase 4: real templates
PLAYER, DIST = "Testigo", 8
CONTROL = "heraldia_prueba_control"


def mobs(jar):
    """[(name, nbt)]: one mob for each distinct NBT (without position) with core.ANCHORED_TAG in the .jar templates, and
    [(template, guardian tag, size, type, position in the template)] of those that have a final guardian."""
    out, seen, rooms = [], set(), []
    with zipfile.ZipFile(jar) as z:
        for n in sorted(z.namelist()):
            if not (n.startswith("data/heraldia/structure/") and n.endswith(".nbt")):
                continue
            t = nbtlib.File.parse(io.BytesIO(gzip.decompress(z.read(n))))
            name = n[len("data/heraldia/structure/"):-4]
            for e in t.get("entities", []):
                nbt = Compound(e["nbt"])
                tags = [str(x) for x in nbt.get("Tags", [])]
                if core.ANCHORED_TAG not in tags:
                    continue
                if "heraldia_guardian" in tags:
                    rooms.append((name, next(x for x in tags if x.startswith("heraldia_guardian.")),
                                  [int(v) for v in t["size"]], str(nbt["id"]), [float(v) for v in e["pos"]]))
                nbt.pop("Pos", None)
                nbt.pop("UUID", None)
                key = nbt.snbt()
                if key not in seen:
                    seen.add(key)
                    out.append((f"{name} ({str(nbt['id']).split(':')[-1]})", nbt))
    return out, rooms


def control(found, mob):
    """The first anchored mob of that type with no Heraldia tag and no name: it behaves like a vanilla one. Removing
    only heraldia_anclado is not enough: the fixes of update/MobFixes (T46) treat as a template mob any mob with
    heraldia_adulto or a persistent one with a heraldia.* name, put heraldia_anclado back on it ("marcas") and take away
    its CanPickUpLoot ("recoger") when it loads, so the control neither picked up items nor stayed vanilla."""
    for name, nbt in found:
        if str(nbt["id"]) == mob:
            c = Compound(nbt)
            c["Tags"] = List[String]([String(CONTROL)])
            c.pop("CustomName", None)
            return (f"control sin anclar ({mob.split(':')[-1]})", c)
    return None


def write_pack(work, batches):
    """Data pack in world/datapacks (the server enables it when creating the world): per batch, a template (jigsaw +
    the mob on top, with the heraldia_prueba_m<i> tag), its pool and a function with its placements."""
    root = os.path.join(work, "world", "datapacks", PACK)
    with open(os.path.join(os.makedirs(root, exist_ok=True) or root, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "Heraldia: prueba de mobs anclados", "min_format": 121, "max_format": 121}}, f)
    data = os.path.join(root, "data", NS)
    for d in ("structure", "worldgen/template_pool", "function"):
        os.makedirs(os.path.join(data, d), exist_ok=True)
    for i, batch in enumerate(batches):
        nbt = Compound(batch["nbt"])
        nbt["Tags"] = List[String]([String(t) for t in nbt.get("Tags", [])] + [String(f"heraldia_prueba_m{i}")])
        t = core.Template(f"m{i}")
        t.set(0, 0, 0, "minecraft:stone")
        t.jigsaw(0, 1, 0, "up_north", ANCHOR_POINT, "minecraft:empty", "minecraft:empty", joint="rollable")
        t.entity(0, 1, 0, nbt)
        nbtlib.File(t.to_nbt(), gzipped=True).save(os.path.join(data, "structure", f"m{i}.nbt"))
        with open(os.path.join(data, "worldgen", "template_pool", f"m{i}.json"), "w") as f:
            json.dump({"fallback": "minecraft:empty", "elements": [{"weight": 1, "element": {
                "element_type": "minecraft:single_pool_element", "location": f"{NS}:m{i}",
                "projection": "rigid", "processors": "minecraft:empty"}}]}, f)
        # /place jigsaw puts the piece's jigsaw (facing up) just below the given position: at Y + 1 the stone of the
        # piece is the platform's floor (Y - 1) and the mob stands on it at Y, in the open as in its template. At Y it
        # was in a one-block pit in the floor, and a shulker (it does not move) in that pit does not see the player 8
        # blocks away: its eye is below the floor's surface ("does not attack the player").
        with open(os.path.join(data, "function", f"m{i}.mcfunction"), "w") as f:
            for (x, z) in batch["celdas"]:
                f.write(f"place jigsaw {NS}:m{i} {ANCHOR_POINT} 1 {x} {Y + 1} {z}\n")
        with open(os.path.join(data, "function", f"j{i}.mcfunction"), "w") as f:
            f.write(f"place jigsaw {NS}:m{i} {ANCHOR_POINT} 1 {X3} {Y + 1} {Z3 + DIST}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke"))
    ap.add_argument("--times", type=int, default=30)
    ap.add_argument("--only", default="", help="only the mobs and templates whose name contains this (debugging)")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    found, rooms = mobs(a.jar)
    found = [f for f in found if a.only in f[0]]
    rooms = [r for r in rooms if a.only in r[0]]
    batches = [{"nombre": n, "nbt": nbt, "control": False} for n, nbt in found]
    for mob in ("minecraft:skeleton", "minecraft:zombie"):
        c = control(found, mob)
        if c:
            batches.append({"nombre": c[0], "nbt": c[1], "control": True})
    rows = -(-a.times // COLS)
    z = Z1
    for batch in batches:
        if str(batch["nbt"]["id"]) in AQUATIC_MOBS:
            # The elder guardian builds itself a 16-block home (ElderGuardian.customServerAiStep) and returns to
            # it (MoveTowardsRestrictionGoal); in one of four runs, 3 of 10 anchored drifted about 9 blocks on
            # spawning and then nothing, and a vanilla one 12. It is required to stay in its home. Cells 40 blocks apart and fewer
            # placements (water is costly).
            step, cols, times, batch["tol"] = 40, 5, min(a.times, 10), 16
        else:
            step, cols, times, batch["tol"] = STEP, COLS, a.times * (4 if batch["control"] else 1), 1
        batch["celdas"] = [(X1 + (k % cols) * step, z + (k // cols) * step) for k in range(times)]
        batch["caja"] = (X1 - 2, z - 2, X1 + cols * step + 2, z + (-(-times // cols)) * step + 2)
        z = batch["caja"][3] + 4
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    write_pack(a.work, batches)
    proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=a.work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=s.reader, args=(proc, lines), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    fails = []
    x_max = max(l["caja"][2] for l in batches)

    def forceload(x0, z0, x1, z1, add=True):
        ctx.run(f"forceload {'add' if add else 'remove'} {x0} {z0} {x1} {z1}", r"Marked|Added|Removed|force|already|Unmarked")

    def fill(x0, y0, z0, x1, y1, z1, block, mode=""):
        """/fill in z strips not exceeding 32,768 blocks; "outline" as floor, ceiling and four walls."""
        if mode == "outline":
            for c in ((x0, y0, z0, x1, y0, z1), (x0, y1, z0, x1, y1, z1), (x0, y0, z0, x0, y1, z1),
                      (x1, y0, z0, x1, y1, z1), (x0, y0, z0, x1, y1, z0), (x0, y0, z1, x1, y1, z1)):
                fill(*c, block)
            return
        step = max(1, 32768 // ((x1 - x0 + 1) * (y1 - y0 + 1)))
        for za in range(z0, z1 + 1, step):
            zb = min(z1, za + step - 1)
            for _ in range(s.PLACE_ATTEMPTS):   # forced chunks take a while to load
                m = ctx.run(f"fill {x0} {y0} {za} {x1} {y1} {zb} {block}", r"Successfully filled|No blocks|not loaded|Too many")
                if "not loaded" not in m.string:
                    break
                time.sleep(s.PLACE_RETRY_S)
            else:
                raise SystemExit(f"chunks at {x0} {za} do not load")
            if m.group(0).startswith("Too many"):
                raise SystemExit(f"/fill demasiado grande: {m.string.strip()}")

    def sel(i, extra=""):
        return f"@e[tag=heraldia_prueba_m{i}{extra}]"

    def blanks(i, batch):
        """Cells of the batch without their mob (more than tol + 0.8 blocks away horizontally: the selector looks at the collision box)."""
        t = batch["tol"]
        return [(x, z) for (x, z) in batch["celdas"]
                if ctx.count(sel(i, f",x={x - t},y={Y - 1},z={z - t},dx={2 * t},dy=6,dz={2 * t}")) < 1]

    def check(phase):
        for i, batch in enumerate(batches):
            v, total = blanks(i, batch), ctx.count(sel(i))
            outside = len(v)
            print(f"anchored: {phase}: {batch['nombre']}: {total} in the world, {outside} of {len(batch['celdas'])} outside their cell")
            for (x, z) in v[:3]:        # where the one closest to the empty cell is
                print(f"anchored:   cell ({x + 0.5}, {Y}, {z + 0.5}): the closest one at "
                      f"{ctx.pos(sel(i, f',x={x + 0.5},y={Y},z={z + 0.5},sort=nearest,limit=1'))}")
            if batch["control"]:
                batch.setdefault("fuera", []).append(outside)
            elif total != len(batch["celdas"]) or outside:
                fails.append(f"{phase}: {batch['nombre']}: {outside} of {len(batch['celdas'])} outside their cell ({total} in the world)")

    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        m = ctx.run("datapack list enabled", r"data pack\(s\) enabled: (.*)|no data packs")
        if PACK not in m.group(0):
            raise SystemExit(f"test pack {PACK} is not enabled: {m.string.strip()}")
        # At night, with time not advancing, no natural monsters and on hard (CanPickUpLoot comes out with higher
        # probability the harder it is: the control must get some).
        ctx.run("time set midnight", r"Set .*time")
        for rule in ("advance_time", "spawn_mobs"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        ctx.run("difficulty hard", r"difficulty|Difficulty")

        # 1) placement: in their cell after 200 ticks and without picking up items
        for batch in batches:
            x0, z0, x1, z1 = batch["caja"]
            forceload(x0 - 1, z0 - 1, x1 + 1, z1 + 1)
            fill(x0, Y - 1, z0, x1, Y - 1, z1, "minecraft:stone")
            fill(x0 - 1, Y - 1, z0 - 1, x1 + 1, Y + 6, z1 + 1, "minecraft:barrier", "outline")
            # the interior, empty: a box may fall inside a hill (with the test seed, at x = 2000 the terrain
            # exceeds y = 150 towards z = 500) and a mob that spawns in rock suffocates
            fill(x0, Y, z0, x1, Y + 5, z1, "minecraft:water" if str(batch["nbt"]["id"]) in AQUATIC_MOBS else "minecraft:air")
        print(f"anchored: {len(found)} distinct mobs with {core.ANCHORED_TAG}; {len(rooms)} templates with a guardian")
        for i, batch in enumerate(batches):
            ctx.run(f"function {NS}:m{i}", r"Running function|Ran \d+ command")
        for i, batch in enumerate(batches):
            end = time.monotonic() + s.UNTIL_S
            while ctx.count(sel(i)) < len(batch["celdas"]) and time.monotonic() < end:
                time.sleep(s.POLL_S)
            pick_up = ctx.count(sel(i, ",nbt={CanPickUpLoot:1b}"))
            print(f"anclados: {batch['nombre']}: {ctx.count(sel(i))} colocados, {pick_up} pueden recoger objetos")
            if batch["control"]:
                batch["recogen"] = pick_up
            elif pick_up:
                fails.append(f"{batch['nombre']}: {pick_up} de {len(batch['celdas'])} pueden recoger objetos")
        ctx.ticks(200)
        check("al colocarse")

        # 2) unload and reload the chunks: noActionTime goes back to 0 and the game would let them wander again
        ctx.run("forceload remove all", r"Unmarked|Removed|No force|force")
        if not ctx.until(f"execute if entity @e[tag={core.ANCHORED_TAG}]", want=False):
            fails.append("the test chunks do not unload")
        for batch in batches:
            x0, z0, x1, z1 = batch["caja"]
            forceload(x0 - 1, z0 - 1, x1 + 1, z1 + 1)
        for i, batch in enumerate(batches):
            if not ctx.until(f"execute if entity {sel(i)}"):
                fails.append(f"{batch['nombre']}: no vuelve a cargarse")
        ctx.ticks(200)
        check("tras recargar")
        for batch in batches:
            if batch["control"]:
                if not any(batch["fuera"]):
                    fails.append(f"{batch['nombre']}: none has wandered; the test does not check the anchoring")
                if batch["nombre"].endswith("(zombie)") and not batch["recogen"]:
                    fails.append(f"{batch['nombre']}: none can pick up items; the test does not check CanPickUpLoot")
        ctx.run(f"kill @e[type=!minecraft:player,x={X1 - 4},y={Y - 4},z={Z1 - 4},dx={x_max - X1 + 8},dy=14,dz={z - Z1 + 8}]",
                r"Killed|No entity was found")
        ctx.run("forceload remove all", r"Unmarked|Removed|No force|force")

        # 3) with a player at DIST blocks, it attacks
        forceload(X3 - 4, Z3 - 4, X3 + 4, Z3 + DIST + 4)
        fill(X3 - 4, Y - 1, Z3 - 4, X3 + 4, Y - 1, Z3 + DIST + 4, "minecraft:stone")
        fill(X3 - 5, Y - 1, Z3 - 5, X3 + 5, Y + 6, Z3 + DIST + 5, "minecraft:barrier", "outline")
        zone = f"x={X3 - 4},y={Y - 1},z={Z3 - 4},dx=8,dy=8,dz={DIST + 8}"
        healthy = f"execute if entity @a[name={PLAYER},nbt={{Health:20.0f}}]"

        def player():
            """The player, alive (if it died, again), in place and at full health."""
            for _ in range(3):
                if not ctx.test(f"execute if entity @a[name={PLAYER}]"):
                    s.require_carpet(ctx)
                    ctx.run(f"player {PLAYER} spawn at {X3 + 0.5} {Y} {Z3 + 0.5}", r"joined the game|Player .* spawn")
                    if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
                        raise SystemExit(f"simulated player {PLAYER} does not appear (Carpet)")
                    ctx.run(f"gamemode survival {PLAYER}", r"Set .* game mode|game mode")
                ctx.run(f"tp {PLAYER} {X3 + 0.5} {Y} {Z3 + 0.5}", r"Teleported|No entity")
                ctx.run(f"effect give {PLAYER} minecraft:instant_health 1 10", r"Applied|Gave|effect|Unable|No entity")
                ctx.run(f"effect clear {PLAYER}", r"Removed|effect|Unable|No entity")
                if ctx.until(healthy, timeout=15):
                    return True
            return False

        for i, batch in enumerate(batches):
            if batch["control"] or str(batch["nbt"]["id"]) in AQUATIC_MOBS | PEACEFUL:
                continue
            if not player():
                fails.append(f"attack: the player does not recover health before {batch['nombre']}")
                continue
            ctx.run(f"function {NS}:j{i}", r"Running function|Ran \d+ command")
            if not ctx.wait_entity(sel(i)):
                fails.append(f"ataque: {batch['nombre']}: no aparece")
                continue
            t0 = time.monotonic()
            ok = ctx.until(healthy, want=False)
            print(f"anclados: ataque: {batch['nombre']}: {'ataca' if ok else 'NO ataca'} ({time.monotonic() - t0:.1f} s)")
            if not ok:
                fails.append(f"attack: {batch['nombre']} does not attack the player at {DIST} blocks")
            # a magma cube (or slime) bigger than the smallest splits when it dies, 20 ticks after the kill: its
            # little cubes would attack the player during the next mob's turn; the smallest one does not split
            # (one by one: "execute as ... run data merge" prints nothing when there is no target)
            for t in ("magma_cube", "slime"):
                for _ in range(8):
                    m = ctx.run(f"data merge entity @e[type=minecraft:{t},{zone},nbt=!{{Size:0}},limit=1] {{Size:0}}",
                                r"Modified entity data|No entity was found|Nothing changed")
                    if not m.group(0).startswith("Modified"):
                        break
            ctx.run(f"kill @e[type=!minecraft:player,{zone}]", r"Killed|No entity was found")
            for t in ("vex", "evoker_fangs", "arrow", "trident", "item"):   # vexes pass through the barrier
                ctx.run(f"kill @e[type=minecraft:{t}]", r"Killed|No entity was found")
        ctx.run(f"player {PLAYER} kill", r"left the game|Killed|died|No player|Can only manipulate")
        ctx.run("forceload remove all", r"Unmarked|Removed|No force|force")

        # 4) each guardian's real template (all at once), by day, and again at night those of the drowned (their
        # goals of going to the water and the shore depend on the time): after 200 ticks it is still where the template puts it.
        def check_rooms(hour, which_ones, k0):
            ctx.run(f"time set {hour}", r"Set .*time")
            placed_items = []
            for k, (name, tag, size, mob, pos) in enumerate(which_ones):
                x4 = X4 + 320 * (k0 + k)                 # each template in its place: no remains of another
                sx, sy, sz = size
                forceload(x4 - 1, Z4 - 1, x4 + sx, Z4 + sz)
                for _ in range(s.PLACE_ATTEMPTS):
                    m = ctx.run(f"place template heraldia:{name} {x4} {Y4} {Z4}", r"Loaded template|placed|Failed|not loaded|Unknown|Invalid")
                    if "not loaded" not in m.string:
                        break
                    time.sleep(s.PLACE_RETRY_S)
                placed_items.append((name, tag, size, (x4 + pos[0], Y4 + pos[1], Z4 + pos[2]), x4))
            ctx.ticks(200)
            for name, tag, (sx, sy, sz), p0, x4 in placed_items:
                g = f"@e[tag={tag}]"
                if not ctx.wait_entity(g):
                    fails.append(f"room ({hour}): {name}: the guardian does not appear")
                    continue
                p1 = ctx.pos(g)
                d = ((p1[0] - p0[0]) ** 2 + (p1[2] - p0[2]) ** 2) ** 0.5
                print(f"anchored: room ({hour}): {name}: placed at {p0}, after 200 ticks at {p1} ({d:.2f} blocks)")
                if d > 1.5:
                    fails.append(f"room ({hour}): {name}: the guardian moved from {p0} to {p1}")
                ctx.run(f"kill @e[type=!minecraft:player,x={x4 - 2},y={Y4 - 2},z={Z4 - 2},dx={sx + 4},dy={sy + 4},dz={sz + 4}]",
                        r"Killed|No entity was found")
            ctx.run("forceload remove all", r"Unmarked|Removed|No force|force")

        for r in rooms:
            if r[3] in AQUATIC_MOBS:
                print(f"anchored: room: {r[0]}: {r[3]} (aquatic) is skipped; tested in the phase 1 pool")
        land = [r for r in rooms if r[3] not in AQUATIC_MOBS]
        check_rooms("noon", land, 0)
        check_rooms("midnight", [r for r in land if r[3] == "minecraft:drowned"], len(land))
    finally:
        try:
            s.send(proc, "stop")
            proc.wait(timeout=120)
        except Exception:
            proc.kill()
    if not found or not rooms:
        fails.append("there are no anchored mobs in the templates: the test checks nothing")
    if fails:
        print("FALLOS:\n- " + "\n- ".join(fails))
        sys.exit(1)
    print("anclados: OK")


if __name__ == "__main__":
    main()
