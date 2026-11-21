"""Mill (heraldia:medianas/molino/<estilo>): 19 x 19 courtyard with a mill and its field. Variant a: watermill,
7 x 9 house with the millstone (grindstone), the paddle wheel in a still-water millrace to the east and the miller (a villager
with fixed trades: buys wheat, sells bread and cake flour, who lives there: his bed and the composter by the door); b:
windmill, 7 x 7 three-floor tower with the sails to the south and a wheat field with its irrigation ditch to the east,
where the miller lives and farms. No monsters."""
from core import Template
from loot import item, empty
from uniques._common import chest_loot
from . import _common as c
from . import _inhabitants as inh

MID = "molino"
DISPLAY_NAME = {"es_es": "Molino", "en_us": "Mill"}
SEPARATION = 832
ADVANCEMENT_ICON = "minecraft:wheat"
LANG = chest_loot.lang("heraldia.medianas.molino.", {
    "molinero": ("Molinero", "Miller"),
})
ADVANCEMENTS = [dict(id="molienda", icono="minecraft:bread", tabla="molienda",
               titulo=("Grano y muela", "Grist for the Mill"),
               descripcion=("Abre los costales de un molino", "Open the sacks of a mill"))]
LOOT = {
    "molienda": chest_loot.place_chest(((3, 5), [item("wheat", 10, 3, 9), item("bread", 8, 1, 4), item("sugar", 5, 1, 4),
                                      item("egg", 4, 1, 3), item("wheat_seeds", 6, 2, 6), item("beetroot_seeds", 3, 1, 4),
                                      item("bone_meal", 4, 2, 5), item("hay_block", 2), item("pumpkin_pie", 2),
                                      empty(4)]),
                            ((1, 1), [item("cake", 1), item("emerald", 2), empty(8)])),
    "molinero": chest_loot.place_chest(((2, 4), [item("bread", 6, 1, 3), item("paper", 4, 1, 3), item("candle", 4, 1, 2),
                                      item("iron_nugget", 5, 2, 6), item("shears", 2, dmg=(0.3, 0.8)),
                                      item("iron_hoe", 2, dmg=(0.4, 0.9)), item("leather", 3, 1, 2), item("compass", 1),
                                      empty(6)]),
                            ((1, 1), [item("emerald", 3, 1, 2), empty(8)])),
}

L = 19
DOOR_COL = 6                         # door axis (both variants)


def offers():
    em = lambda n: {"id": "minecraft:emerald", "count": n}
    return [c.offer({"id": "minecraft:wheat", "count": 20}, em(1), 16),
            c.offer(em(1), {"id": "minecraft:bread", "count": 6}, 12),
            c.offer(em(1), {"id": "minecraft:sugar", "count": 8}, 8),
            c.offer(em(2), {"id": "minecraft:cake", "count": 1}, 4)]


def _floor(p):
    mats = p["patio"]
    return lambda x, z: "minecraft:dirt_path" if x == DOOR_COL and z < 5 else mats[(x * 5 + z * 9 + x * z) % len(mats)]


def _courtyard(t, p):
    c.courtyard(t, 0, 0, L - 1, L - 1, _floor(p), air_block=3)
    c.entrance(t, DOOR_COL, f"{p['peldano']}[facing=south,half=bottom,shape=straight,waterlogged=false]")
    inh.bell(t, DOOR_COL - 3, 2)                              # the call bell by the gate: the miller's meeting point


def _wheel(t, p, x, cy, cz, r=3):
    """Paddle wheel in the x plane (axis along x): plank rim, fence spokes and the log hub."""
    m = p["madera"]
    for dy in range(-r, r + 1):
        for dz in range(-r, r + 1):
            d = (dy * dy + dz * dz) ** 0.5
            if r - 0.5 <= d < r + 0.5:
                t.set(x, cy + dy, cz + dz, f"{m}_planks")
    for k in range(1, r):
        for dy, dz in ((k, 0), (-k, 0), (0, k), (0, -k)):
            t.set(x, cy + dy, cz + dz, f"{m}_fence")
    t.set(x, cy, cz, f"{p['tronco']}[axis=x]")


def water(p, name):
    """Watermill: 7 x 9 house (x 3..9, z 5..13), millrace to the east (x = 12) with the wheel and the miller inside."""
    t = Template(name)
    _courtyard(t, p)
    m = p["madera"]
    X0, Z0, X1, Z1 = 3, 5, 9, 13
    t.fill(X0, 0, Z0, X1, 0, Z1, p["zocalo"])
    t.fill(X0 + 1, 0, Z0 + 1, X1 - 1, 0, Z1 - 1, f"{m}_planks")
    c.box(t, X0, 1, Z0, X1, 4, Z1, p["muro"], corner_block=f"{p['tronco']}[axis=y]")
    t.fill(X0, 1, Z0, X1, 1, Z1, p["zocalo"])                      # hilada baja de piedra
    for x, z in ((X0, Z0), (X0, Z1), (X1, Z0), (X1, Z1)):
        t.set(x, 1, z, f"{p['tronco']}[axis=y]")
    t.fill(X0 + 1, 1, Z0 + 1, X1 - 1, 1, Z1 - 1, "air")
    t.fill(X0, 5, Z0, X1, 5, Z1, f"{m}_planks")
    c.roof_tiles(t, X0, Z0, X1, Z1, 5, p["teja"], p["cumbrera"], p["muro"])
    c.door(t, DOOR_COL, 1, Z0, "south", f"{m}_door")
    for z in (7, 11):
        c.window(t, X0, 2, z)
    c.window(t, X1, 2, 7)
    c.window(t, X1, 2, 11)
    # millrace: still water at y = 0 (all sources) between two parapets, with the wheel on top; the axle enters through the east wall
    for z in range(3, 16):
        t.set(11, 0, z, p["pretil"])
        t.set(13, 0, z, p["pretil"])
        t.set(12, 0, z, "water[level=0]")
    t.set(12, 0, 2, p["pretil"])
    t.set(12, 0, 16, p["pretil"])
    _wheel(t, p, 12, 4, 9)
    t.set(X1, 4, 9, f"{p['tronco']}[axis=x]")
    t.set(10, 4, 9, f"{p['tronco']}[axis=x]")
    t.set(11, 4, 9, f"{p['tronco']}[axis=x]")
    # inside: the millstone next to the axle, sacks (barrels and hay), the chest and the miller's bed
    t.set(X1 - 1, 1, 9, "grindstone[face=floor,facing=north]")
    t.set(X1 - 1, 4, 9, f"stripped_{p['tronco']}[axis=x]")
    t.fill(X1 - 1, 2, 9, X1 - 1, 3, 9, f"{m}_fence")
    c.place_chest(t, X1 - 1, 1, Z1 - 1, "west", MID, "molienda", kind="barrel")
    t.set(X1 - 1, 1, Z1 - 2, "barrel[facing=up,open=false]", {"id": "minecraft:barrel"})
    t.set(X1 - 1, 1, Z0 + 1, "hay_block[axis=y]")
    t.set(X1 - 1, 2, Z0 + 1, "hay_block[axis=y]")
    t.set(X1 - 2, 1, Z0 + 1, "hay_block[axis=y]")
    c.bed(t, X0 + 1, Z1 - 1, "west", p["cama"])
    c.place_chest(t, X0 + 1, 1, Z1 - 3, "east", MID, "molinero")
    t.set(X0 + 1, 1, Z0 + 1, "crafting_table")
    c.lantern(t, DOOR_COL, 4, 9)
    t.entity(DOOR_COL, 1, 11, inh.villager(MID, "molinero", "Molinero", "farmer", p["aldeano"], offers(), rot=0.0,
                                           still_before=True))
    # outside: stacked sacks next to the door and a hay cart
    t.set(DOOR_COL + 2, 1, 3, "hay_block[axis=x]")
    t.set(DOOR_COL + 3, 1, 3, "hay_block[axis=x]")
    t.set(DOOR_COL - 2, 1, 3, "composter[level=0]")
    return t


def wind(p, name):
    """Windmill: 7 x 7 tower (x 3..9, z 5..11), three floors with a ladder, sails on the south face and a
    wheat field with an irrigation ditch to the east; the miller lives on the ground floor (his bed by the millstone, no
    ladder on the way) and tends the field (the composter at its corner)."""
    t = Template(name)
    _courtyard(t, p)
    m = p["madera"]
    X0, Z0, X1, Z1 = 3, 5, 9, 11
    CX = 6
    roof = 13
    t.fill(X0, 0, Z0, X1, 0, Z1, p["zocalo"])
    t.fill(X0 + 1, 0, Z0 + 1, X1 - 1, 0, Z1 - 1, f"{m}_planks")
    c.box(t, X0, 1, Z0, X1, roof - 1, Z1, p["muro"], corner_block=f"{p['tronco']}[axis=y]")
    t.fill(X0, 1, Z0, X1, 4, Z1, p["zocalo"])                       # the first floor, of stone
    for x, z in ((X0, Z0), (X0, Z1), (X1, Z0), (X1, Z1)):
        t.fill(x, 1, z, x, roof - 1, z, f"{p['tronco']}[axis=y]")
    t.fill(X0 + 1, 1, Z0 + 1, X1 - 1, roof - 1, Z1 - 1, "air")
    for y in (5, 9):
        t.fill(X0 + 1, y, Z0 + 1, X1 - 1, y, Z1 - 1, f"{m}_planks")
    t.fill(X0, roof, Z0, X1, roof, Z1, f"{m}_planks")
    # hipped roof: rings of steps that close up to a ridge
    for k in range(4):
        y = roof + 1 + k
        xa, xb, za, zb = X0 - 1 + k, X1 + 1 - k, Z0 - 1 + k, Z1 + 1 - k
        if xa >= xb or za >= zb:
            break
        for x in range(xa, xb + 1):
            t.set(x, y, za, f"{p['teja']}[facing=south,half=bottom,shape=straight,waterlogged=false]")
            t.set(x, y, zb, f"{p['teja']}[facing=north,half=bottom,shape=straight,waterlogged=false]")
        for z in range(za + 1, zb):
            t.set(xa, y, z, f"{p['teja']}[facing=east,half=bottom,shape=straight,waterlogged=false]")
            t.set(xb, y, z, f"{p['teja']}[facing=west,half=bottom,shape=straight,waterlogged=false]")
        for x in range(xa + 1, xb):
            for z in range(za + 1, zb):
                t.set(x, y, z, p["cumbrera"])
    c.door(t, CX, 1, Z0, "south", f"{m}_door")
    c.ladder(t, X0 + 1, Z1 - 1, 1, 9, "north")               # against the south wall; passes through both floors
    # its foot shut behind a fence gate: a miller who climbed it had no way down (mediums/_paths.stranded)
    c.ladder_closet(t, X0 + 1, 1, Z1 - 1, m, p["tronco"], {(0, -1): "gate", (1, 0): "post"})
    for y in (2, 7, 11):
        c.window(t, X0, y, 8)
        c.window(t, X1, y, 8)
    c.window(t, CX, 7, Z0)
    c.window(t, CX, 11, Z0)
    # sails: log axle that sticks out of the south wall (y = 10) and four arms with their canvas
    hy, hz = 10, Z1 + 1
    t.set(CX, hy, Z1, f"{p['tronco']}[axis=z]")
    t.set(CX, hy, hz, f"{p['tronco']}[axis=z]")
    for k in range(1, 6):
        t.set(CX, hy + k, hz, f"stripped_{p['tronco']}[axis=y]")
        t.set(CX, hy - k, hz, f"stripped_{p['tronco']}[axis=y]")
        t.set(CX + k, hy, hz, f"stripped_{p['tronco']}[axis=x]")
        t.set(CX - k, hy, hz, f"stripped_{p['tronco']}[axis=x]")
        if k >= 2:
            t.set(CX + 1, hy + k, hz, p["lona"])
            t.set(CX - 1, hy - k, hz, p["lona"])
            t.set(CX + k, hy - 1, hz, p["lona"])
            t.set(CX - k, hy + 1, hz, p["lona"])
    # ground floor: the millstone and the sacks; first: grain; second: the axle with its cog wheel
    t.set(X1 - 1, 1, Z0 + 2, "grindstone[face=floor,facing=north]")
    c.place_chest(t, X1 - 1, 1, Z1 - 1, "west", MID, "molienda", kind="barrel")
    t.set(X1 - 1, 1, Z0 + 1, "hay_block[axis=y]")
    c.bed(t, CX, Z1 - 1, "west", p["cama"])
    t.entity(CX, 1, 8, inh.villager(MID, "molinero", "Molinero", "farmer", p["aldeano"], offers(), rot=0.0))
    c.lantern(t, CX, 4, 8)
    t.set(X1 - 1, 6, Z0 + 1, "hay_block[axis=y]")
    t.set(X1 - 1, 6, Z0 + 2, "hay_block[axis=y]")
    t.set(X1 - 1, 7, Z0 + 1, "hay_block[axis=y]")
    c.place_chest(t, X1 - 1, 6, Z1 - 1, "west", MID, "molinero")
    c.lantern(t, CX, 8, 8)
    t.fill(CX, hy, Z0 + 2, CX, hy, Z1 - 1, f"stripped_{p['tronco']}[axis=z]")
    t.set(CX, 10, Z0 + 1, f"{m}_planks")                            # axle bearing in the north wall
    c.lantern(t, X1 - 1, 12, Z0 + 1)
    # wheat field to the east with its irrigation ditch (a fountain in the center) and a scarecrow
    x0, x1, z0, z1 = 12, 16, 4, 14
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if (x, z) == ((x0 + x1) // 2, (z0 + z1) // 2):
                t.set(x, 0, z, "water[level=0]")
            else:
                t.set(x, 0, z, "farmland[moisture=7]")
                t.set(x, 1, z, p["cultivos"][(x + z) % len(p["cultivos"])])
    t.set(x1 + 1, 1, 9, f"{m}_fence")
    t.set(x1 + 1, 2, 9, "carved_pumpkin[facing=west]")
    t.set(x0 - 1, 1, z0, "composter[level=0]")
    return t


_CROPS_SHORT = ["wheat[age=7]", "wheat[age=7]", "beetroots[age=3]"]
STYLES = {
    "llanura": dict(biomas=["plains", "sunflower_plains"], convencionales=["c:is_plains"],
                    paleta=dict(madera="oak", tronco="oak_log", muro="white_terracotta", zocalo="cobblestone",
                                pretil="stone_bricks", teja="spruce_stairs", cumbrera="spruce_planks",
                                peldano="cobblestone_stairs", lona="white_wool", cama="yellow", aldeano="plains",
                                cultivos=_CROPS_SHORT,
                                patio=["minecraft:dirt_path", "minecraft:packed_mud", "minecraft:dirt_path",
                                       "minecraft:gravel"]),
                    variantes={"a": water, "b": wind}),
    "pantano": dict(biomas=["swamp"],
                    paleta=dict(madera="mangrove", tronco="mangrove_log", muro="mud_bricks", zocalo="cobblestone",
                                pretil="mud_bricks", teja="dark_oak_stairs", cumbrera="dark_oak_planks",
                                peldano="mud_brick_stairs", lona="light_gray_wool", cama="green", aldeano="swamp",
                                cultivos=["wheat[age=7]", "potatoes[age=7]", "carrots[age=7]"],
                                patio=["minecraft:packed_mud", "minecraft:dirt_path", "minecraft:mud_bricks"]),
                    variantes={"a": water, "b": wind}),
}
