"""Look, do not take (herald/HeraldHouse.opened, mixin/HeraldOpenMenuMixin, mixin/HeraldLookPacketMixin): the containers
of the Herald's House area open for a player who is not an operator, who sees what they hold and takes nothing, on a
real 26.3 dedicated server with simulated players (Carpet).

Usage: python3 tools/smoke/herald_look.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-mirar"
One world (roads and grounds off, the market on); an operator places the town from the console, then:
  1. a town chest (one of the template's, with its heraldia:relleno loot table) opened by "Miron" (survival, not an
     operator): the loot rolls, the window is look-only and shows stacks;
  2. every way a client has to take or put something, each sent as a real packet through Miron's own connection
     (/heraldia choice click and choice send): left and right click on a slot, shift-click out and in, a drag (left,
     right), double click, a hotbar key swap and the offhand swap, Q and Ctrl+Q over a slot, a click outside the
     window, carrying an item of the inventory into the chest, a menu button and a bundle's selection; after each one
     the chest, Miron's inventory and the ground around are exactly as before;
  3. the same chest in creative mode: middle click (clone), a middle drag and a pick-block with data (Ctrl), which
     copies the chest without its contents; closed, the chest is identical;
  4. a furnace and a crafter in the area: the recipe book's placement (it would move the furnace's input back to the
     player) and a crafter slot toggle are dropped;
  5. a chest minecart in the area is look-only too; the ender chest is not (Miron puts an item in it);
  6. the option off (/heraldia config set): the chest does not open at all, as before it;
  7. the market: Miron rents stall 1 and puts in and takes out of the chest in its box; "vecino" (not an operator) cannot
     open it; evicted, its things go to a return barrel that Miron opens and empties;
  8. Miron as an operator: takes from a town chest, places a recipe in the furnace and toggles the crafter's slot (the
     same packets as above do change them: the test's packets are not inert).
Exit code 0 if everything passes.
"""
import argparse, gzip, io, json, os, re, shutil, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server
from arena import Test
from trophies import CARPET
from modrinth import fetch

P, Q = "Miron", "vecino"   # Carpet spawns this one lowercase (its cached profile)
PLACED = r"herald's house: placed at (-?\d+) (-?\d+) (-?\d+) \(box (-?\d+) (-?\d+) (-?\d+) to"
DATA = r"has the following (?:block|entity) data: ([^\n]*)|Found no elements matching [^\n]*|is not a block entity|No entity was found"
STATUS = r"choice: [^\n]*"
RAW_IRON, RAW_GOLD = "minecraft:iron_ingot_from_smelting_raw_iron", "minecraft:gold_ingot_from_smelting_raw_gold"


def config(work):
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False, "caminos": {"activado": False}, "alrededores": {"activado": False},
                           "mercado": {"activado": True, "entrada_esmeraldas": 1, "alquiler_esmeraldas": 1, "periodo_dias": 7,
                                       "gracia_dias": 0}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def town_chests(jar):
    """The template's chests with a loot table (positions relative to its origin), single or double."""
    import nbtlib
    with zipfile.ZipFile(jar) as z:
        f = nbtlib.File.parse(io.BytesIO(gzip.decompress(z.read("data/heraldia/structure/casa_heraldo/casa.nbt"))))
    pal = f["palette"]
    out = []
    for b in f["blocks"]:
        st = pal[int(b["state"])]
        name = str(st.get("Name", st.get("id", "")))
        if name == "minecraft:chest" and "nbt" in b and "LootTable" in b["nbt"]:
            out.append(tuple(int(v) for v in b["pos"]))
    return out


class Look:
    def __init__(self, p, origin):
        self.p, self.ctx, self.o = p, p.ctx, origin

    def w(self, rel):
        return tuple(self.o[i] + rel[i] for i in range(3))

    def data(self, what):
        m = self.ctx.run(f"data get {what}", DATA)
        return m.group(1) if m.group(1) is not None else ""

    def items(self, pos):
        return self.data(f"block {pos[0]} {pos[1]} {pos[2]} Items")

    def inv(self, who):
        return self.data(f"entity {who} Inventory")

    def ground(self, pos):
        return self.ctx.count(f"@e[type=minecraft:item,x={pos[0]},y={pos[1]},z={pos[2]},distance=..10]")

    def status(self, who):
        return self.ctx.run(f"execute as {who} run heraldia choice", STATUS).group(0)

    def air(self, pos):
        return self.ctx.block(pos, "minecraft:air")

    def stands(self, pos):
        """Where a player can stand to reach the block: on top of it, or on a side with two blocks of air."""
        x, y, z = pos
        out = []
        if self.air((x, y + 1, z)) and self.air((x, y + 2, z)):
            out.append((x + 0.5, y + 1, z + 0.5))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if self.air((x + dx, y, z + dz)) and self.air((x + dx, y + 1, z + dz)) and not self.air((x + dx, y - 1, z + dz)):
                out.append((x + dx + 0.5, y, z + dz + 0.5))
        return out

    def stand(self, pos):
        st = self.stands(pos)
        return st[0] if st else None

    @staticmethod
    def aim(pos, at):
        """The centre of the face turned to the player (a block stacked above, as the return barrels are, is not hit)."""
        x, y, z = pos
        if at[1] > y:
            return (x + 0.5, y + 0.5, z + 0.5)
        return (x + 0.5 + (at[0] - x - 0.5) * 0.4, y + 0.2, z + 0.5 + (at[2] - z - 0.5) * 0.4)   # low, just inside the face

    def open(self, who, pos):
        """The player walks up to the block and uses it (Carpet: the real use, through UseBlockCallback and vanilla), from
        each place it can stand until a window opens."""
        for at in self.stands(pos):
            self.close(who)
            self.ctx.run(f"tp {who} {at[0]} {at[1]} {at[2]}", r"Teleported")
            t = self.aim(pos, at)
            s.send(self.ctx.proc, f"player {who} look at {t[0]} {t[1]} {t[2]}")
            self.ctx.ticks(3)
            s.send(self.ctx.proc, f"player {who} use once")
            self.ctx.ticks(5)
            if "no window" not in self.status(who):
                return True
        return False

    def close(self, who):
        """Walking away closes the window (stillValid), as a client's Escape would; the cursor goes back to the inventory.
        Always: a player left standing where the next one stands would take its click (Carpet aims at entities too)."""
        self.ctx.run(f"execute as {who} at @s run tp @s ~40 ~ ~", r"Teleported")
        self.ctx.ticks(3)
        self.p.check("no window" in self.status(who), f"{who}'s window does not close when walking away")

    def click(self, who, slot, kind="pickup", button=0):
        self.ctx.run(f"execute as {who} run heraldia choice click {slot} {kind} {button}", r"choice click: slot|unknown input")

    def send(self, who, what):
        self.ctx.run(f"execute as {who} run heraldia choice send {what}", r"choice send: [^\n]*|Unknown|Incorrect")


def give(ctx, who, item, n=1):
    ctx.run(f"give {who} {item} {n}", r"Gave|No player")


def ways(L, who, chest, size):
    """Every way of taking or putting, one by one; after each: the chest, the inventory and the ground as before."""
    p, ctx = L.p, L.ctx
    hot = size + 27                                   # the first hotbar slot in a chest window
    attempts = [
        ("left click", [(0, "pickup", 0)]),
        ("right click", [(0, "pickup", 1)]),
        ("shift-click out", [(0, "quick_move", 0)]),
        ("shift-click in", [(hot, "quick_move", 0)]),
        ("hotbar key swap", [(0, "swap", 0)]),
        ("offhand swap", [(0, "swap", 40)]),
        ("Q over a slot", [(0, "throw", 0)]),
        ("Ctrl+Q over a slot", [(0, "throw", 1)]),
        ("double click", [(0, "pickup_all", 0)]),
        ("click outside the window", [(-999, "pickup", 0), (-999, "pickup", 1)]),
        ("carry an item in", [(hot, "pickup", 0), (1, "pickup", 0)]),
        ("carry an item in, right click", [(hot, "pickup", 1), (2, "pickup", 1)]),
        ("left drag", [(-999, "quick_craft", 0), (1, "quick_craft", 1), (2, "quick_craft", 1), (-999, "quick_craft", 2)]),
        ("right drag", [(-999, "quick_craft", 4), (1, "quick_craft", 5), (2, "quick_craft", 5), (-999, "quick_craft", 6)]),
        ("drag out of the chest", [(0, "pickup", 0), (-999, "quick_craft", 0), (hot + 1, "quick_craft", 1),
                                   (-999, "quick_craft", 2)]),
    ]
    before, inv0 = L.items(chest), L.inv(who)
    for name, clicks in attempts:
        for slot, kind, button in clicks:
            L.click(who, slot, kind, button)
        ctx.ticks(1)
        p.check(L.items(chest) == before, f"look-only: {name} changed the chest")
        p.check(L.inv(who) == inv0, f"look-only: {name} changed {who}'s inventory")
        p.check(L.ground(chest) == 0, f"look-only: {name} dropped an item")
        p.check("look-only" in L.status(who), f"look-only: after {name} the window is no longer look-only")
    L.send(who, "button 0")
    L.send(who, "bundle 0 0")
    L.send(who, f"bundle {hot} 0")
    ctx.ticks(1)
    p.check(L.items(chest) == before and L.inv(who) == inv0, "look-only: a menu button or a bundle selection changed something")
    return before, inv0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-mirar"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    jar = os.path.abspath(a.jar)
    with zipfile.ZipFile(jar) as z:
        hp = json.loads(z.read("heraldia/casa_heraldo.json"))
    chests = town_chests(jar)
    launcher = s.prepare(a.work, jar, s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    shutil.rmtree(os.path.join(a.work, "world"), ignore_errors=True)
    config(a.work)
    fails, texts = [], []
    t0 = time.monotonic()
    srv = Server(a.work, launcher)
    p = Test(srv.ctx, fails)
    ctx = srv.ctx
    try:
        run(p, ctx, hp, chests)
    finally:
        srv.stop()
        texts.append(ctx.log())
    for bad in ("Registry loading errors", "at io.github.albertosa23", "Mixin apply failed", "InvalidInjectionException"):
        if any(bad in t for t in texts):
            fails.append(f"the log contains {bad!r}")
    print(f"HERALD LOOK: {time.monotonic() - t0:.0f} s;", "OK" if not fails else fails)
    return 1 if fails else 0


def run(p, ctx, hp, chests):
    p.check(len(chests) >= 2, f"the town template has {len(chests)} chests with a loot table")
    ctx.run("heraldia herald place", r"Looking for a site|Buscando sitio")
    if not p.check(p.wait_log(r"herald's house: site at", 180), "herald: no site"):
        return
    ctx.run("heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
    m = p.wait_log(PLACED, 900)
    if not p.check(m, "herald: the house is not built"):
        return
    b = [int(g) for g in m.groups()[3:]]
    side = hp["tamano"][0]
    ctx.run(f"forceload add {b[0] - 10} {b[2] - 10} {b[0] + side + 10} {b[2] + side + 10}", r"Marked|force|already")
    L = Look(p, b)
    spawn = L.w(hp["aparicion"])
    for who in (P, Q):
        s.require_carpet(ctx)
        ctx.run(f"player {who} spawn at {spawn[0] + 0.5} {spawn[1]} {spawn[2] + 0.5}", r"joined the game|Player .* spawn")
        if not ctx.until(f"execute if entity @a[name={who}]"):
            raise SystemExit(f"simulated player {who} (Carpet) does not appear")
    ctx.ticks(20)                                       # Carpet loads a fake player's data after its JOIN
    for who in (P, Q):
        ctx.run(f"deop {who}", r"no longer|Nothing changed|not an operator")
        s.send(ctx.proc, f"gamemode survival {who}")
        ctx.run(f"clear {who}", r"Removed|No items")
    ctx.ticks(2)
    # 1. a town chest: the one that can be reached, a double one first (both halves are checked)
    world = [L.w(c) for c in chests]
    pairs = [c for c in world if any(d != c and abs(d[0] - c[0]) + abs(d[2] - c[2]) == 1 and d[1] == c[1] for d in world)]
    chest = next((c for c in pairs + world if L.stand(c)), None)
    if not p.check(chest, "no town chest can be reached"):
        return
    other = next((c for c in world if c != chest and c not in pairs and L.stand(c)), None)
    print(f"LOOK: town chest at {chest} ({'double' if chest in pairs else 'single'}), the operator's at {other}", flush=True)
    p.check(L.data(f"block {chest[0]} {chest[1]} {chest[2]} LootTable") != "", "the town chest has no loot table before opening")
    give(ctx, P, "minecraft:apple", 3)
    give(ctx, P, "minecraft:bundle", 1)
    ctx.ticks(2)
    if not p.check(L.open(P, chest), f"{P} cannot open the town chest"):
        return
    st = L.status(P)
    print("LOOK:", st, flush=True)
    m = re.search(r"look-only, (\d+) stacks shown", st)
    p.check(m and int(m.group(1)) > 0, f"the town chest is not look-only with something to see: {st}")
    p.check(L.data(f"block {chest[0]} {chest[1]} {chest[2]} LootTable") == "", "the loot table did not roll")
    p.check(L.items(chest) != "", "the town chest is empty after its loot rolled")
    size = 54 if chest in pairs else 27
    # 2. every way out (and in)
    before, inv0 = ways(L, P, chest, size)
    L.close(P)
    p.check(L.items(chest) == before, "the town chest changed once closed")
    p.check(L.inv(P) == inv0, f"{P}'s inventory changed once the window closed (the cursor held something)")
    p.check(L.ground(chest) == 0 and L.ground(L.w(hp["aparicion"])) == 0, "an item was dropped")
    # 3. creative: clone, middle drag, pick-block with data
    s.send(ctx.proc, f"gamemode creative {P}")
    ctx.ticks(2)
    p.check(L.open(P, chest) and "look-only" in L.status(P), "creative: the town chest is not look-only")
    inv1 = L.inv(P)
    for slot, kind, button in [(0, "clone", 2), (-999, "quick_craft", 8), (1, "quick_craft", 9), (-999, "quick_craft", 10),
                               (0, "pickup", 0)]:
        L.click(P, slot, kind, button)
    ctx.ticks(1)
    p.check(L.items(chest) == before and L.inv(P) == inv1, "creative: a middle click or drag changed something")
    L.close(P)
    p.check(L.inv(P) == inv1, "creative: the cursor held a clone")
    at = L.stand(chest)
    ctx.run(f"tp {P} {at[0]} {at[1]} {at[2]}", r"Teleported")
    L.send(P, f"pick {chest[0]} {chest[1]} {chest[2]} true")
    ctx.ticks(2)
    inv2 = L.inv(P)
    p.check("chest" in inv2, f"creative: the pick-block gave no chest at all ({inv2[:200]})")
    p.check("container" not in inv2 and "loot" not in inv2, f"creative: the pick-block with data copied the contents ({inv2[:300]})")
    p.check(L.items(chest) == before, "creative: the pick-block changed the chest")
    ctx.run(f"clear {P}", r"Removed|No items")
    s.send(ctx.proc, f"gamemode survival {P}")
    ctx.ticks(2)
    # 4. a furnace and a crafter in the area
    sx, sy, sz = spawn
    furnace, crafter, ender = (sx + 3, sy, sz + 3), (sx - 3, sy, sz + 3), (sx + 3, sy, sz - 3)
    for pos in (furnace, crafter, ender, (furnace[0], sy + 1, furnace[2]), (crafter[0], sy + 1, crafter[2]),
                (ender[0], sy + 1, ender[2]), (furnace[0], sy + 2, furnace[2]), (crafter[0], sy + 2, crafter[2]),
                (ender[0], sy + 2, ender[2])):
        ctx.run(f"setblock {pos[0]} {pos[1]} {pos[2]} minecraft:air", r"Changed the block|Could not set")
    ctx.run(f'setblock {furnace[0]} {furnace[1]} {furnace[2]} minecraft:furnace{{Items:[{{Slot:0b,id:"minecraft:raw_iron",count:3}}]}}',
            r"Changed the block|Could not set")
    ctx.run(f'setblock {crafter[0]} {crafter[1]} {crafter[2]} minecraft:crafter{{Items:[{{Slot:0b,id:"minecraft:stick",count:2}}]}}',
            r"Changed the block|Could not set")
    ctx.run(f"setblock {ender[0]} {ender[1]} {ender[2]} minecraft:ender_chest", r"Changed the block|Could not set")
    ctx.run(f"recipe give {P} *", r"Unlocked|recipe|Recipe")
    give(ctx, P, "minecraft:raw_gold", 2)
    ctx.ticks(2)
    inv3 = L.inv(P)
    f0, c0 = L.items(furnace), L.data(f"block {crafter[0]} {crafter[1]} {crafter[2]}")
    if p.check(L.open(P, furnace) and "look-only" in L.status(P), "the furnace in the area is not look-only"):
        L.send(P, f"recipe {RAW_GOLD}")
        L.click(P, 0, "quick_move", 0)
        ctx.ticks(2)
        p.check(L.items(furnace) == f0 and L.inv(P) == inv3, "look-only: the recipe book's placement moved the furnace's items")
    if p.check(L.open(P, crafter) and "look-only" in L.status(P), "the crafter in the area is not look-only"):
        L.send(P, "slot-state 1 false")
        L.click(P, 0, "pickup", 0)
        ctx.ticks(2)
        p.check(L.data(f"block {crafter[0]} {crafter[1]} {crafter[2]}") == c0, "look-only: the crafter's slot was toggled")
    L.close(P)
    p.check(L.inv(P) == inv3, f"{P}'s inventory changed at the furnace or the crafter")
    # 5. a chest minecart (look-only) and the ender chest (the player's own)
    cart = (sx - 3, sy, sz - 3)
    ctx.run(f'summon minecraft:chest_minecart {cart[0] + 0.5} {cart[1]} {cart[2] + 0.5} {{Tags:["heraldia_mirar"],'
            f'Items:[{{Slot:0b,id:"minecraft:emerald",count:4}}]}}', r"Summoned")
    ctx.ticks(5)
    ctx.run(f"tp {P} {cart[0] + 2.5} {cart[1]} {cart[2] + 0.5}", r"Teleported")
    s.send(ctx.proc, f"player {P} look at {cart[0] + 0.5} {cart[1] + 0.4} {cart[2] + 0.5}")
    ctx.ticks(3)
    s.send(ctx.proc, f"player {P} use once")
    ctx.ticks(5)
    st = L.status(P)
    if p.check("look-only" in st, f"the chest minecart in the area is not look-only: {st}"):
        L.click(P, 0, "quick_move", 0)
        ctx.ticks(1)
        p.check("count: 4" in L.data("entity @e[tag=heraldia_mirar,limit=1] Items") and L.inv(P) == inv3,
                "look-only: an item left the chest minecart")
    L.close(P)
    if p.check(L.open(P, ender) and "look-only" not in L.status(P), "the ender chest is look-only (it is the player's own)"):
        L.click(P, 27 + 27, "quick_move", 0)           # the first hotbar slot (raw gold) into the ender chest
        ctx.ticks(1)
        p.check("raw_gold" in L.data(f"entity {P} EnderItems"), "the ender chest does not take the player's item")
    L.close(P)
    # 6. the option off: the chest stays shut, as before
    ctx.run("heraldia config set casa_heraldo.contenedores_solo_ver false", r"guardadas por|Valor no válido|Invalid|Unknown|Incorrect")
    p.check(not L.open(P, chest), "with the option off the town chest still opens")
    ctx.run("heraldia config set casa_heraldo.contenedores_solo_ver true", r"guardadas por|Valor no válido|Invalid|Unknown|Incorrect")
    p.check(L.open(P, chest) and "look-only" in L.status(P), "with the option on again the town chest is not look-only")
    L.close(P)
    p.check(L.items(chest) == before, "the town chest changed")
    # 7. the market: a stall of one's own, someone else's, the return barrel
    ctx.run(f"clear {P}", r"Removed|No items")
    give(ctx, P, "minecraft:emerald", 5)
    ctx.run(f"execute as {P} run heraldia herald stall claim 1", r"Stall 1 is yours|El puesto 1 es tuyo|need|Hacen falta")
    p.check(p.wait_log(rf"stall 1 claimed by {P}", timeout=30), "stall 1 is not claimed")
    box = L.w(hp["puestos"][0]["caja"][0])
    ctx.run(f'setblock {box[0]} {box[1]} {box[2]} minecraft:chest{{Items:[{{Slot:0b,id:"minecraft:diamond",count:5}}]}}',
            r"Changed the block|Could not set")
    if p.check(L.open(P, box) and "look-only" not in L.status(P), "the tenant's chest in their stall is look-only or shut"):
        L.click(P, 0, "quick_move", 0)
        ctx.ticks(1)
        p.check(L.items(box) in ("", "[]") and "diamond" in L.inv(P), "the tenant cannot take from their stall's chest")
        for slot in range(27, 63):                     # back in, from wherever they went in the inventory
            L.click(P, slot, "quick_move", 0)
        ctx.ticks(1)
        p.check("diamond" in L.items(box) and "diamond" not in L.inv(P), "the tenant cannot put into their stall's chest")
    L.close(P)
    p.check(not L.open(Q, box), f"{Q} opens the chest in {P}'s stall")
    L.close(Q)
    ctx.run("heraldia herald stall evict 1", r"[^\n]*(?:evict|desaloj|[Ss]tall|[Pp]uesto)[^\n]*")
    m = p.wait_log(rf"stall 1 of {P} reclaimed: (\d+) stacks into (\d+) return barrel", timeout=60)
    if p.check(m, "the evicted stall is not reclaimed into a return barrel"):
        barrels = [L.w(r) for r in hp["devolucion"]]
        full = next((r for r in barrels if "diamond" in L.items(r)), None)
        if p.check(full, "no return barrel holds the diamonds"):
            p.check(not L.open(Q, full), f"{Q} opens {P}'s return barrel")
            L.close(Q)
            opened = L.open(P, full)
            if p.check(opened and "look-only" not in L.status(P), "the owner's return barrel is look-only or shut"):
                for slot in range(27):
                    L.click(P, slot, "quick_move", 0)
                ctx.ticks(1)
                p.check("diamond" in L.inv(P) and L.items(full) in ("", "[]"), "the owner cannot empty their return barrel")
            L.close(P)
    # 8. an operator: everything as before
    ctx.run(f"op {P}", r"Made .* operator|already|Nothing changed")
    ctx.run(f"clear {P}", r"Removed|No items")
    give(ctx, P, "minecraft:raw_gold", 2)
    ctx.ticks(2)
    if other and p.check(L.open(P, other) and "look-only" not in L.status(P), "an operator's town chest is look-only"):
        L.click(P, 0, "quick_move", 0)
        for slot in range(1, 27):
            L.click(P, slot, "quick_move", 0)
        ctx.ticks(1)
        p.check(L.items(other) in ("", "[]"), "an operator cannot take from a town chest")
    if p.check(L.open(P, furnace) and "look-only" not in L.status(P), "an operator's furnace is look-only"):
        L.send(P, f"recipe {RAW_GOLD}")
        ctx.ticks(2)
        p.check(L.items(furnace) != f0, "an operator's recipe book placement does nothing (the test's packet is inert)")
    if p.check(L.open(P, crafter), "an operator cannot open the crafter"):
        L.send(P, "slot-state 1 false")
        ctx.ticks(2)
        p.check(L.data(f"block {crafter[0]} {crafter[1]} {crafter[2]}") != c0,
                "an operator's crafter slot toggle does nothing (the test's packet is inert)")
    L.close(P)
    ctx.run(f"deop {P}", r"no longer|Nothing changed|not an operator")


if __name__ == "__main__":
    sys.exit(main())
