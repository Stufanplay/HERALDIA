"""Loot that is restocked (chest_loot.reponer.*) on a real 26.3 dedicated server, with simulated players (Carpet).

Usage: python3 tools/smoke/loot_restock.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
With chest_loot.reponer.activado = true and chest_loot.reponer.dias = 1, the clock stopped (advance_time false) and the days simulated
with /time add 24000, a simulated player opens the chests (player ... use once, like a right click) and it checks:
  - a chest with a Heraldia table (heraldia:cofres/prueba_reponer, from a test datapack with 7 fixed arrows): when
    opened it fills up and is marked (custom_data heraldia_botin with its table); once emptied, it is not restocked before a day has passed, and is
    once the day passes;
  - with 4 slots occupied it is not restocked and nothing is touched; with 3 (almost empty) it is, and what was there (a diamond in
    slot 0) is still there;
  - with another player 8 blocks away it is not restocked; with them 100 blocks away, it is;
  - the fixed-content chest (heraldia_cofre_unico), one with a trophy table and one with a vanilla table are not marked;
  - a chest already generated and looted before enabling the option (the one in the cell of a really generated hermitage, the one
    /locate gives, without its LootTable and empty): when opened its original table is recognized from the structure template and a day later it is restocked;
  - after restarting with the option disabled (the default), opening a Heraldia chest marks nothing.
Without Lootr (which disables all this) it is not tested here.
"""
import argparse, json, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
import server_smoke as s
from guide import Server
from trophies import CARPET
from modrinth import fetch
import mediums                      # noqa: E402  (medium structure templates: where the hermitage chest is)
from pack import Registry           # noqa: E402
from medium_structures import forceload, wait_generated   # noqa: E402

PLAYER, OTHER_ONE = "Testigo", "Aprendiz"     # those from guide.py (Carpet may change the capitalization of other names)
DAY = 24000
TABLE = "heraldia:cofres/prueba_reponer"
ARROWS = 7
C = (0, 100, 0)                       # test chest, on a slab; the player 2 blocks away
PACK = "heraldia_prueba_botin"
HERMITAGE, HERMITAGE_TABLE = "medianas/ermita", "heraldia:medianas/ermita/celda"
# StructureTemplate.transform (no mirror, pivot 0): local (x, z) -> offset in the world, per rotation
TURNS = {"none": lambda x, z: (x, z), "cw90": lambda x, z: (-z, x), "cw180": lambda x, z: (-x, -z), "ccw90": lambda x, z: (z, -x)}


def datapack(work):
    root = os.path.join(work, "world", "datapacks", PACK)
    os.makedirs(os.path.join(root, "data", "heraldia", "loot_table", "cofres"), exist_ok=True)
    with open(os.path.join(root, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "Heraldia: prueba del botín que se repone", "min_format": 121, "max_format": 121}}, f)
    with open(os.path.join(root, "data", "heraldia", "loot_table", "cofres", "prueba_reponer.json"), "w") as f:
        json.dump({"type": "minecraft:chest", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": "minecraft:arrow",
                   "modifier": {"type": "minecraft:set_count", "count": ARROWS}}]}]}, f)


def config(work, switched_on):
    path = os.path.join(work, "config", "heraldia.json")
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["botin"] = {"reponer": {"activado": switched_on, "dias": 1}}
    with open(path, "w") as f:
        json.dump(cfg, f)


def hermitage_chests():
    """Local positions (x, y, z) of the chests with the cell table in the hermitage's styles and variants."""
    reg = Registry()
    mediums.build(reg, "ermita")
    out = set()
    for n, t in reg.templates.items():
        if n.startswith(HERMITAGE + "/"):
            out |= {p for p, (st, nbt) in t.blocks.items() if nbt and nbt.get("LootTable") == HERMITAGE_TABLE}
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-botin"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    local_coords = hermitage_chests()
    if len(local_coords) != 1:
        raise SystemExit(f"the hermitage should have a single cell chest (in all its styles and variants): {local_coords}")
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    datapack(a.work)
    config(a.work, True)
    fails, ok = [], 0
    srv = Server(a.work, launcher)
    ctx = srv.ctx

    def check(cond, msg):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fails.append(msg)
            print("FAIL:", msg)

    def at(p):
        return " ".join(str(v) for v in p)

    def use(p, who=PLAYER):
        x, y, z = p
        # Carpet actions print nothing to the console: they are sent and we wait with a command that does respond
        s.send(srv.proc, f"player {who} look at {x + 0.5} {y + 0.5} {z + 0.5}")
        s.send(srv.proc, f"player {who} use once")
        ctx.ticks(4)

    def items(p, extra=""):
        return ctx.test(f"execute if data block {at(p)} Items[{extra}]")

    def arrows(p):
        """Are there arrows from the datapack? (chest loot spreads a stack over several free slots at random)"""
        return ctx.test(f'execute if data block {at(p)} Items[{{id:"minecraft:arrow"}}]')

    def record(p, tbl=None):
        sel = f'{{tabla:"{tbl}"}}' if tbl else ""
        return ctx.test(f'execute if data block {at(p)} components."minecraft:custom_data".heraldia_botin{sel}')

    def empty(p):
        ctx.run(f"data modify block {at(p)} Items set value []", r"Modified block data|[Nn]othing changed")

    def day():
        ctx.run(f"time add {DAY}", r"[Tt]ime|[Ss]et")

    try:
        x, y, z = C
        ctx.run(f"forceload add {x - 16} {z - 16} {x + 16} {z + 16}", r"Marked|force|already|[Aa]dded")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f"fill {x - 4} {y - 1} {z - 4} {x + 12} {y - 1} {z + 4} minecraft:stone", r"Successfully filled|No blocks|not loaded")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        ctx.run(f"fill {x - 4} {y} {z - 4} {x + 12} {y + 4} {z + 4} minecraft:air", r"Successfully filled|No blocks")
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        s.require_carpet(ctx)
        ctx.run(f"player {PLAYER} spawn at {x + 2} {y} {z}", r"joined the game|Player .* spawn")
        if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"simulated player {PLAYER} (Carpet) does not appear")
        s.send(srv.proc, f"gamemode survival {PLAYER}")  # no console response if it already had it
        check("botín que se repone activado: cada 1 días" in ctx.log(), "no sale en el log que la opción está activada")

        # 1) new chest with a Heraldia table: it fills up and is marked; once emptied, it waits a day
        ctx.run(f'setblock {at(C)} minecraft:chest{{LootTable:"{TABLE}"}}', r"Changed the block|Could not set")
        use(C)
        check(arrows(C), "el cofre nuevo no se llena con su tabla al abrirlo")
        check(record(C, TABLE), "el cofre nuevo no queda apuntado (heraldia_botin con su tabla)")
        check(not ctx.test(f"execute if data block {at(C)} LootTable"), "el cofre conserva la LootTable tras abrirlo")
        empty(C)
        use(C)
        check(not items(C), "se repone sin que pase el día")
        ctx.run(f"time add {DAY - 1}", r"[Tt]ime|[Ss]et")
        use(C)
        check(not items(C), "se repone un tick antes del día")
        ctx.run("time add 1", r"[Tt]ime|[Ss]et")
        use(C)
        check(arrows(C), "vacío y pasado el día, no se repone")
        use(C)
        nearby_flag = f"@e[type=minecraft:item,x={x},y={y},z={z},distance=..8]"     # (not the leaves that the terrain drops)
        n = ctx.count(nearby_flag)
        if n:
            m = ctx.run(f"data get entity {nearby_flag[:-1]},limit=1] Item", r"has the following entity data: (.*)|No entity")
            print("DIAG: item on the ground:", m.group(1), ctx.pos(nearby_flag))
        check(n == 0, f"{n} objetos han caído al suelo")

        # 2) with things inside: 4 slots no; 3 (almost empty) yes, without touching what was there
        ctx.run(f'data modify block {at(C)} Items set value [{{Slot:0b,id:"minecraft:diamond",count:1}},'
                f'{{Slot:1b,id:"minecraft:dirt",count:5}},{{Slot:2b,id:"minecraft:dirt",count:5}},{{Slot:3b,id:"minecraft:dirt",count:5}}]',
                r"Modified block data")
        day()
        use(C)
        check(not arrows(C) and items(C, "{Slot:3b}"), "con 4 casillas ocupadas se repone o se toca")
        ctx.run(f"data remove block {at(C)} Items[{{Slot:3b}}]", r"Modified block data")
        use(C)
        check(arrows(C), "casi vacío (3 casillas) y pasado el día, no se repone")
        check(items(C, '{Slot:0b,id:"minecraft:diamond",count:1}') and items(C, '{Slot:1b,id:"minecraft:dirt",count:5}')
              and items(C, '{Slot:2b,id:"minecraft:dirt",count:5}'), "al reponer se ha tocado lo que había")

        # 3) another player nearby prevents it
        empty(C)
        day()
        s.require_carpet(ctx)
        ctx.run(f"player {OTHER_ONE} spawn at {x + 8} {y} {z}", r"joined the game|Player .* spawn")
        check(ctx.until(f"execute if entity @a[name={OTHER_ONE}]"), f"no aparece {OTHER_ONE}")
        s.send(srv.proc, f"gamemode survival {OTHER_ONE}")  # no console response if it already had it
        use(C)
        check(not items(C), "se repone con otro jugador a 8 bloques")
        ctx.run(f"tp {OTHER_ONE} {x + 100} {y + 20} {z}", r"Teleported")
        ctx.ticks(4)
        use(C)
        check(arrows(C), "con el otro jugador a 100 bloques no se repone")
        ctx.run(f"player {OTHER_ONE} kill", r"left the game")

        # 4) what is not restocked: fixed content, trophy, vanilla
        others = {"fijo": ((x + 4, y, z), 'minecraft:chest{components:{"minecraft:custom_data":{heraldia_cofre_unico:"atlantida"}},'
                          f'LootTable:"{TABLE}"}}'),
                 "trofeo": ((x + 6, y, z), 'minecraft:chest{LootTable:"heraldia:trofeos/castillo"}'),
                 "vanilla": ((x + 8, y, z), 'minecraft:chest{LootTable:"minecraft:chests/simple_dungeon"}')}
        for name, (p, block) in others.items():
            ctx.run(f"setblock {at(p)} {block}", r"Changed the block|Could not set")
            ctx.run(f"tp {PLAYER} {p[0] - 2} {y} {z}", r"Teleported")
            ctx.ticks(2)
            use(p)
            check(not record(p), f"el cofre {name} queda apuntado para reponerse")
        ctx.run(f"tp {PLAYER} {x + 2} {y} {z}", r"Teleported")

        # 5) chest already generated and looted before enabling the option: recognized by the template. A really generated
        #    hermitage (/place structure does not save the start in the chunks: getStructureWithPieceAt would not see it)
        m = ctx.run("execute positioned 0 64 0 run locate structure #heraldia:medianas/ermita",
                    r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
        check(bool(m.lastindex and m.group(1)), "/locate no encuentra ninguna ermita")
        place_chest = None
        if m.lastindex and m.group(1):
            px, pz = int(m.group(1)), int(m.group(2))
            ex, ez = px >> 4 << 4, pz >> 4 << 4         # the piece's origin is the corner of the start chunk
            forceload(ctx, ex - 32, ez - 32, ex + 31, ez + 31)
            check(wait_generated(ctx, ex, ez, "ermita"), f"la ermita de {px}, {pz} no se genera")
            lx, ly, lz = local_coords[0]
            for turn, f in TURNS.items():
                dx, dz = f(lx, lz)
                for cy in range(-20, 260):
                    p = (ex + dx, cy + ly, ez + dz)
                    if ctx.test(f'execute if block {at(p)} minecraft:chest{{LootTable:"{HERMITAGE_TABLE}"}}'):
                        place_chest = p
                        break
                if place_chest:
                    print(f"hermitage chest at {px}, {pz} in {place_chest} (rotation {turn})")
                    break
            check(place_chest is not None, f"no se encuentra el cofre de la celda de la ermita de {px}, {pz}")
        if place_chest:
            # "looted before": without its table or anything inside, and not marked
            ctx.run(f"data remove block {at(place_chest)} LootTable", r"Modified block data")
            empty(place_chest)
            cx, cy, cz = place_chest
            ctx.run(f"fill {cx} {cy + 1} {cz} {cx} {cy + 2} {cz} minecraft:air", r"Successfully filled|No blocks")
            ctx.run(f"tp {PLAYER} {cx + 0.5} {cy + 1} {cz + 0.5}", r"Teleported")
            ctx.ticks(10)
            use(place_chest)
            check(record(place_chest, HERMITAGE_TABLE), "el cofre saqueado de la ermita no se reconoce por su plantilla")
            check(not items(place_chest), "el cofre saqueado de la ermita se llena sin esperar")
            day()
            use(place_chest)
            check(items(place_chest), "el cofre de la ermita no se repone pasado el día")
        srv.stop()

        # 6) with the option disabled (default), nothing is marked
        config(a.work, False)
        srv = Server(a.work, launcher)
        ctx = srv.ctx
        p = (x, y, z + 2)
        ctx.run(f"forceload add {x - 16} {z - 16} {x + 16} {z + 16}", r"Marked|force|already|[Aa]dded")
        s.require_carpet(ctx)
        ctx.run(f"player {PLAYER} spawn at {x + 2} {y} {z + 2}", r"joined the game|Player .* spawn")
        ctx.until(f"execute if entity @a[name={PLAYER}]")
        for _ in range(s.PLACE_ATTEMPTS):
            m = ctx.run(f'setblock {at(p)} minecraft:chest{{LootTable:"{TABLE}"}}', r"Changed the block|Could not set|not loaded")
            if "not loaded" not in m.string:
                break
            time.sleep(s.PLACE_RETRY_S)
        use(p)
        check(arrows(p), "con la opción desactivada el cofre no se abre con su tabla")
        check(not record(p), "con la opción desactivada el cofre queda apuntado")
        bad = [b for b in ("Registry loading errors", "Failed to load datapacks") if b in ctx.log()]
        bad += [l.strip() for l in ctx.log().splitlines() if "Exception" in l and "heraldia" in l.lower()]
        check(not bad, f"errores en el log: {bad}")
    finally:
        srv.stop()
    print(f"botin_reponer: {ok} comprobaciones bien, {len(fails)} mal")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
