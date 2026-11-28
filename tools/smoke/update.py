"""Safe updates (T46) on a real dedicated 26.3 server: /heraldia update analyze and apply with a hand-placed "house",
the per-version fixes and the configuration panel in dialogs.

Usage: python3 tools/smoke/update.py --jar build/libs/heraldia-X.jar [--work build/smoke-actualizar]
Two starts of the same world (smoke-test seed, no new mobs or random ticks and, when comparing, with the world
frozen: /tick freeze), with Carpet for a simulated player:
1. A SIDE x SIDE chunk zone is generated far from spawn, a hand-built "house" is placed (planks floor, bed, chest and
   crafting table) and some marker gold blocks underground: some less than 50 blocks from the house and others far away. A
   baby zombie is summoned with the name of a 0.1.0 guardian (no tags): the fix turns it into an adult and anchored
   when loaded, once.
   - analyze changes nothing: the chunks of the zone, read from the regions, are the same before and after, and it leaves the
     report, the text map and the image; it protects the house and proposes regenerating pristine chunks;
   - the zombie is turned back into a baby by hand (data merge);
   - apply (from the console): asks for confirmation with its id; on confirming with a backup, the server stops by itself.
2. On starting by hand: backup, pristine chunks deleted and report. With the world frozen:
   - no chunk within 50 blocks of the house has changed and the nearby gold markers are still there;
   - some far marker has disappeared (its pristine chunk has been regenerated);
   - the zombie is still a baby (the fix is not repeated: it carries the mark) until /heraldia update repair, which fixes it
     (repair dry-run beforehand changes nothing);
   - /heraldia config opens the dialog (simulated player, operator) and its submenu, config set writes the file and
     /heraldia language sets the player's language.
Exit code 0 if everything passes.
"""
import argparse, glob, json, math, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s                       # noqa: E402
import existing_world as me                   # noqa: E402
from terralith_biomes import fetch             # noqa: E402
from trophies import CARPET                     # noqa: E402

SIDE, C0 = 20, 15                              # chunk zone C0..C0+SIDE-1 (blocks 240..559)
HOUSE = (396, 150, 396, 404, 150, 404)          # house floor (minX, y, minZ, maxX, y, maxZ), in the air
MARGIN = 50
Y_MARK = -50
NEARBY = [(440, 400), (400, 440), (360, 360)]   # less than 50 blocks from the house (in protected chunks)
FAR = [(520, 400), (520, 300), (300, 520), (280, 280), (540, 540)]   # more than 100 blocks away
ZOMBIE = "prueba_arreglo"
PLAYER = "Panel"


def near_house(cx, cz):
    dx = max(0, HOUSE[0] - (cx * 16 + 15), cx * 16 - HOUSE[3])
    dz = max(0, HOUSE[2] - (cz * 16 + 15), cz * 16 - HOUSE[5])
    return math.hypot(dx, dz) <= MARGIN


def block(ctx, x, y, z, b):
    return ctx.test(f"execute if block {x} {y} {z} {b}")


def with_chunk(ctx, x, z, f):
    """Loads the block's chunk (forceload), runs f() and releases it."""
    ctx.run(f"forceload add {x} {z}", r"Marked|[Aa]dded|force|already")
    ctx.until(f"execute if loaded {x} 64 {z}", timeout=120)
    try:
        return f()
    finally:
        ctx.run(f"forceload remove {x} {z}", r"[Rr]emoved|[Uu]nmarked|force")


def snapshot(world, chunks):
    """Like existing_world.snapshot, with the structure references unordered: the game stores them in a set and, when
    saving the chunk again, they can come out in another order (seen here: the same two references of a mine, reversed)."""
    out = me.snapshot(world, chunks)
    for h in out.values():
        refs = (h.get("estructuras") or {}).get("References")
        if isinstance(refs, dict):
            h["estructuras"]["References"] = {k: sorted(v) if isinstance(v, list) else v for k, v in refs.items()}
    return out


def wait(ctx, pattern, timeout):
    """Like server_smoke.wait_for, but also valid if the line has already appeared (e.g. during startup)."""
    m = re.search(pattern, ctx.log())
    return m or s.wait_for(ctx.lines, pattern, timeout, ctx.seen)


def wait_since(ctx, n0, pattern, timeout):
    """The first line that matches from line n0 of the log (including those that have already moved to ctx.seen), or waits for it."""
    m = re.search(pattern, "".join(ctx.seen[n0:]))
    return m or s.wait_for(ctx.lines, pattern, timeout, ctx.seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-actualizar"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    world = os.path.join(a.work, "world")
    folder = os.path.join(world, "heraldia", "actualizar")
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    zone = me.square(C0, C0, SIDE)
    nearby = {c for c in zone if near_house(*c)}
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print("FAIL:", msg)
        return cond

    # ------------------------------------------------------------------ arranque 1
    proc, ctx = me.start_up(a.work, launcher, cfg)
    try:
        ctx.run("gamerule advance_time false", r"Gamerule|set to")
        t0 = time.time()
        me.load_data(ctx, zone)
        print(f"zona de {len(zone)} chunks generada en {time.time() - t0:.0f} s")
        for x0, z0, x1, z1 in me.fragments(nearby):
            ctx.run(f"forceload add {x0} {z0} {x1} {z1}", r"Marked|[Aa]dded|force|already")
        x0, y, z0, x1, _, z1 = HOUSE
        ctx.run(f"fill {x0} {y} {z0} {x1} {y} {z1} minecraft:oak_planks", r"Successfully filled|No blocks")
        ctx.run(f"setblock {x0 + 1} {y + 1} {z0 + 1} minecraft:red_bed[facing=south,part=foot]", r"Changed the block|Could not")
        ctx.run(f"setblock {x0 + 1} {y + 1} {z0 + 2} minecraft:red_bed[facing=south,part=head]", r"Changed the block|Could not")
        ctx.run(f"setblock {x1 - 1} {y + 1} {z0 + 1} minecraft:chest", r"Changed the block|Could not")
        ctx.run(f"setblock {x1 - 1} {y + 1} {z1 - 1} minecraft:crafting_table", r"Changed the block|Could not")
        for x, z in NEARBY + FAR:
            with_chunk(ctx, x, z, lambda: ctx.run(f"setblock {x} {Y_MARK} {z} minecraft:gold_block", r"Changed the block|Could not"))
        # a 0.1.0 guardian: translatable Heraldia name, persistent, no tags and baby (/summon with NBT does not
        # call finalizeSpawn, so it comes out as is)
        ctx.run(f'summon minecraft:zombie 400 {y + 1} 400 {{IsBaby:1b,PersistenceRequired:1b,NoAI:1b,Tags:["{ZOMBIE}"],'
                f'CustomName:{{translate:"heraldia.unicas.castillo.guardian",fallback:"Sir Aldric"}}}}',
                r"Summoned|Unable|Invalid")
        check(ctx.until(f"execute if entity @e[tag={ZOMBIE},tag=heraldia_anclado,tag=heraldia_guardian,tag=heraldia_adulto]"),
              "el arreglo «marcas» no ha puesto las etiquetas al guardián antiguo")
        check(ctx.test(f"execute if entity @e[tag={ZOMBIE},nbt={{IsBaby:0b}}]"), "el arreglo «bebes» no ha hecho adulto al guardián")
        fixes_1 = len(re.findall(r"Heraldia: arreglos \{marcas=CHANGES, bebes=CHANGES", "".join(ctx.seen)))
        check(fixes_1 == 1, f"el arreglo se ha aplicado {fixes_1} veces al invocarlo (debía ser 1)")
        me.freeze(ctx)
        ctx.run("save-all flush", r"Saved the game|saved")
        before = snapshot(world, zone)
        check(len(before) == len(zone), f"solo {len(before)} de {len(zone)} chunks guardados enteros")
        # analyze no cambia nada
        n0 = len(ctx.seen)
        ctx.run("heraldia update analyze", r"Analizando|Analysing")
        m = wait_since(ctx, n0, r"update analyze: (\d+) chunks, (\d+) construcciones, (\d+) protegidos, (\d+) vírgenes \((\d+) se "
                       r"regenerarían\), (\d+) estructuras nuevas", 600)
        total, built, prot, virg, regen = (int(m.group(i)) for i in range(1, 6))
        print(f"analyze: {total} chunks, {built} structures, {prot} protected, {virg} pristine, {regen} to regenerate")
        check(total >= len(zone), f"analyze solo ha visto {total} chunks")
        check(built >= 3, f"analyze no ve la casa ({built} construcciones)")
        check(prot >= len(nearby), f"analyze protege {prot} chunks, menos que los {len(nearby)} a 50 bloques de la casa")
        check(regen > 0, "analyze no propone regenerar ningún chunk virgen")
        ctx.run("save-all flush", r"Saved the game|saved")
        check(not me.compare("analyze", before, snapshot(world, zone)), "analyze ha cambiado chunks: "
              + "; ".join(me.compare("analyze", before, snapshot(world, zone))[:3]))
        for pattern in ("analisis-*.txt", "mapa-*.txt", "mapa-*.png"):
            check(glob.glob(os.path.join(folder, pattern)), f"analyze no ha dejado {pattern} en {folder}")
        maps = glob.glob(os.path.join(folder, "mapa-*.txt"))
        if maps:
            text = open(maps[0], encoding="utf-8").read()
            check("#" in text and "R" in text, "el mapa en texto no marca la casa (#) y lo que se regenera (R)")
        check(not os.path.exists(os.path.join(folder, "plan.json")), "analyze ha dejado un plan")
        # the guardian is made a baby again (by hand): the fix must not repeat when it is reloaded
        ctx.run(f"data merge entity @e[tag={ZOMBIE},limit=1] {{IsBaby:1b}}", r"Modified|Unable|Nothing")
        # without forced chunks on restart: otherwise their fluids run before freezing the world (game changes)
        for x0, z0, x1, z1 in me.fragments(nearby):
            ctx.run(f"forceload remove {x0} {z0} {x1} {z1}", r"[Rr]emoved|[Uu]nmarked|force")
        # apply: confirmation with id, with backup
        n0 = len(ctx.seen)
        ctx.run("heraldia update apply", r"Analizando|Analysing")
        m = wait_since(ctx, n0, r"update apply confirm (\w+) backup", 600)
        ident = m.group(1)
        check(not os.path.exists(os.path.join(folder, "plan.json")), "apply sin confirmar ya ha dejado el plan")
        s.send(proc, f"heraldia update apply confirm {ident} backup")
        wait_since(ctx, n0, r"update apply confirmado .*el servidor se para", 60)
        check(os.path.exists(os.path.join(folder, "plan.json")), "al confirmar no queda el plan")
        proc.wait(timeout=180)
        print("the server stopped by itself after confirming")
    finally:
        if proc.poll() is None:
            proc.kill()
    log1 = "".join(ctx.seen)

    # ------------------------------------------------------------------ arranque 2 (a mano)
    proc, ctx = me.start_up(a.work, launcher, cfg)
    try:
        wait(ctx, r"update apply terminado", 300)
        log2 = "".join(ctx.seen)
        m = re.search(r"update apply: (\d+) chunks vírgenes borrados", log2)
        deleted = int(m.group(1)) if m else 0
        check(deleted > 0, "al arrancar no se ha borrado ningún chunk virgen")
        check(re.search(r"copia de seguridad de [1-9]\d* ficheros", log2), "no se ha hecho la copia de seguridad")
        check(glob.glob(os.path.join(folder, "copia-*", "region", "r.*.mca")), "no está la copia de las regiones")
        check(glob.glob(os.path.join(folder, "informe-*.txt")), "no está el informe de apply")
        check(glob.glob(os.path.join(folder, "hecho-*.json")) and not os.path.exists(os.path.join(folder, "plan.json")),
              "el plan no ha quedado como hecho")
        i_cs = log2.index("chunks vírgenes borrados") if "chunks vírgenes borrados" in log2 else -1
        i_prep = log2.find("Preparing")
        check(i_cs >= 0 and (i_prep < 0 or i_cs < i_prep), "los chunks se borraron después de cargar el mundo")
        me.freeze(ctx)
        me.load_data(ctx, zone, frozen=True)
        ctx.run("save-all flush", r"Saved the game|saved")
        after = snapshot(world, nearby)
        diff = me.compare("apply", {c: before[c] for c in nearby if c in before}, after)
        check(not diff, f"apply ha cambiado chunks a menos de {MARGIN} bloques de la casa: " + "; ".join(diff[:3]))
        for x, z in NEARBY:
            check(with_chunk(ctx, x, z, lambda: block(ctx, x, Y_MARK, z, "minecraft:gold_block")),
                  f"la marca de oro de {x}, {z} (a menos de 50 bloques de la casa) ha desaparecido")
        removed = [(x, z) for x, z in FAR if not with_chunk(ctx, x, z, lambda: block(ctx, x, Y_MARK, z, "minecraft:gold_block"))]
        print(f"marcas lejanas regeneradas: {removed} de {FAR}")
        check(removed, "ninguna marca lejana ha desaparecido: no se ha regenerado ningún chunk virgen")
        check(with_chunk(ctx, *HOUSE[:1], HOUSE[2], lambda: block(ctx, HOUSE[0] + 1, HOUSE[1] + 1, HOUSE[2] + 1, "minecraft:red_bed")),
              "la cama de la casa ha desaparecido")
        # the fixes are not repeated: the guardian stays a baby until repair
        ctx.run(f"forceload add 400 400", r"Marked|[Aa]dded|force|already")
        ctx.until("execute if loaded 400 64 400", timeout=120)
        check(ctx.until(f"execute if entity @e[tag={ZOMBIE}]"), "no está el guardián de prueba")
        check(ctx.test(f"execute if entity @e[tag={ZOMBIE},nbt={{IsBaby:1b}}]"), "el arreglo se ha vuelto a aplicar al recargar")
        times = len(re.findall(r"Heraldia: arreglos \{marcas=CHANGES", log1 + "".join(ctx.seen)))
        check(times == 1, f"el arreglo de marcas se ha aplicado {times} veces (debía ser 1)")
        n0 = len(ctx.seen)
        ctx.run("heraldia update repair dry-run", r"Prueba|Dry run")
        m = wait_since(ctx, n0, r"update repair dry-run: (\d+) mobs de plantilla revisados, (\d+) cambios (\{.*\})", 30)
        check("bebes=1/0" in m.group(3), f"repair dry-run no ve el bebé: {m.group(3)}")
        check(ctx.test(f"execute if entity @e[tag={ZOMBIE},nbt={{IsBaby:1b}}]"), "repair dry-run ha cambiado el guardián")
        n0 = len(ctx.seen)
        ctx.run("heraldia update repair", r"Arreglos|Fixes")
        wait_since(ctx, n0, r"update repair: \d+ mobs de plantilla revisados, [1-9]\d* cambios", 30)
        check(ctx.test(f"execute if entity @e[tag={ZOMBIE},nbt={{IsBaby:0b}}]"), "repair no ha hecho adulto al guardián")
        n0 = len(ctx.seen)
        ctx.run("heraldia update repair dry-run", r"Prueba|Dry run")
        m = wait_since(ctx, n0, r"update repair dry-run: (\d+) mobs de plantilla revisados, (\d+) cambios", 30)
        check(m.group(2) == "0", f"tras repair aún quedan {m.group(2)} cambios (no es idempotente)")
        # configuration panel and preferences
        s.require_carpet(ctx)
        ctx.run(f"player {PLAYER} spawn at 0 100 0", r"joined the game|Player .* spawn")
        check(ctx.until(f"execute if entity @a[name={PLAYER}]"), "no aparece el jugador simulado (Carpet)")
        ctx.run(f"op {PLAYER}", r"Made .* operator|Nothing changed")
        ctx.run(f"execute as {PLAYER} run heraldia config", rf"panel de configuración abierto \({PLAYER}, principal\)|Unknown|Incorrect")
        check(re.search(rf"panel de configuración abierto \({PLAYER}, principal\)", "".join(ctx.seen)), "/heraldia config no abre el diálogo")
        ctx.run(f"execute as {PLAYER} run heraldia config menu combate", rf"abierto \({PLAYER}, combate\)|Unknown|Incorrect")
        check(re.search(rf"abierto \({PLAYER}, combate\)", "".join(ctx.seen)), "/heraldia config menu combate no abre el submenú")
        ctx.run("heraldia config set arena.max_mobs_vivos 30", r"guardadas por|Valor no válido")
        with open(os.path.join(a.work, "config", "heraldia.json"), encoding="utf-8") as f:
            check(json.load(f).get("arena", {}).get("max_mobs_vivos") == 30, "config set no ha escrito el fichero")
        ctx.run(f"execute as {PLAYER} run heraldia language fr_fr", rf"idioma de {PLAYER}: fr_fr|Unknown|Incorrect")
        check(re.search(rf"idioma de {PLAYER}: fr_fr", "".join(ctx.seen)), "/heraldia language no fija el idioma")
        check(re.search(r"mundo generado con la versión", "".join(ctx.seen)), "no se dice con qué versión se generó el mundo")
        me.halt(proc, ctx)
    finally:
        if proc.poll() is None:
            proc.kill()
    if fails:
        print(f"{len(fails)} fallos")
        return 1
    print("update: all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
