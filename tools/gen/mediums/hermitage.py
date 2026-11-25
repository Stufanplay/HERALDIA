"""Hermitage (heraldia:medianas/ermita/<estilo>): 7 x 11 chapel with a bell gable and bell, pews, altar with candles and the
hermit's cell (bed and chest with his diary), and a fenced garden with an irrigation ditch. Variant a: the garden to the east;
b: the garden to the west and a small graveyard to the east. In both, the hermit lives in his cell (a librarian with fixed
trades: his bed and the lectern beside it). No monsters."""
from core import Template
from loot import item, empty
from uniques._common import chest_loot
from . import _common as c
from . import _inhabitants as inh

MID = "ermita"
DISPLAY_NAME = {"es_es": "Ermita", "en_us": "Hermitage"}
SEPARATION = 768
ADVANCEMENT_ICON = "minecraft:bell"
_K = "heraldia.medianas.ermita."
LANG = chest_loot.lang(_K, {
    "diario": ("Diario del ermitaño", "The Hermit's Diary"),
    "ermitano": ("Ermitaño", "Hermit"),
    "diario.p1": ("Subí aquí para estar lejos de todo. El camino sigue pasando a lo lejos: torres, posadas, fogatas "
                  "de gente que no quiere ser vista.",
                  "I came up here to be far from everything. The road still passes in the distance: towers, inns, "
                  "campfires of people who do not wish to be seen."),
    "diario.p2": ("El huerto da lo justo. La campana la toco al alba y al ocaso; si alguien la oye, que sepa que aquí "
                  "hay techo y pan para quien llegue en paz.",
                  "The garden gives just enough. I ring the bell at dawn and dusk; whoever hears it should know there "
                  "is a roof and bread here for anyone who comes in peace."),
})
_DIARY = chest_loot.written_book([{"translate": _K + "diario.p1", "fallback": LANG["es_es"][_K + "diario.p1"]},
                       {"translate": _K + "diario.p2", "fallback": LANG["es_es"][_K + "diario.p2"]}],
                      {"translate": _K + "diario", "fallback": LANG["es_es"][_K + "diario"]},
                      LANG["es_es"][_K + "diario"], "Ermitaño")
LOOT = {
    "celda": chest_loot.table(
        chest_loot.pool(1, [_DIARY]),
        chest_loot.pool((2, 4), [item("bread", 8, 1, 3), item("candle", 6, 1, 3), item("paper", 5, 1, 4), item("book", 4),
                            item("golden_carrot", 2, 1, 2), item("glistering_melon_slice", 2), item("honey_bottle", 3),
                            item("experience_bottle", 2, 1, 2), item("book", 2, rand_ench=True), empty(4)]),
        chest_loot.pool((1, 1), [item("emerald", 3, 1, 2), item("lapis_lazuli", 3, 2, 5), empty(8)], extra=True)),
}

X0, Z0, X1, Z1 = 7, 3, 13, 13       # chapel walls (7 x 11), door to the north
CX = 10
WIDTH, DEPTH = 21, 17


def hermit_offers():
    em = lambda n: {"id": "minecraft:emerald", "count": n}
    return [c.offer({"id": "minecraft:paper", "count": 24}, em(1), 12),
            c.offer(em(1), {"id": "minecraft:bread", "count": 4}, 12),
            c.offer(em(1), {"id": "minecraft:candle", "count": 2}, 8),
            c.offer(em(2), {"id": "minecraft:book", "count": 1}, 6)]


def _floor(p):
    mats = p["patio"]
    return lambda x, z: "minecraft:dirt_path" if x == CX and z < Z0 else mats[(x * 7 + z * 3 + x * z) % len(mats)]


def _chapel(p, name):
    t = Template(name)
    m = p["madera"]
    c.courtyard(t, 0, 0, WIDTH - 1, DEPTH - 1, _floor(p))
    c.entrance(t, CX, f"{p['peldano']}[facing=south,half=bottom,shape=straight,waterlogged=false]")
    t.fill(X0, 0, Z0, X1, 0, Z1, p["zocalo"])
    t.fill(X0 + 1, 0, Z0 + 1, X1 - 1, 0, Z1 - 1, p["suelo"])
    # rotated walls: the ridge runs along z, so it is built in (z, x) with the common roof over x
    c.box(t, X0, 1, Z0, X1, 4, Z1, p["muro"], corner_block=p["esquina"])
    t.fill(X0, 5, Z0, X1, 5, Z1, p["muro"])
    t.fill(X0 + 1, 5, Z0 + 1, X1 - 1, 5, Z1 - 1, f"{m}_planks")
    summit = _roof_z(t, p, 5)
    c.door(t, CX, 1, Z0, "south", f"{m}_door")
    # bell gable over the north facade with the bell
    t.fill(CX - 1, summit, Z0, CX + 1, summit + 3, Z0, p["esquina"])
    t.set(CX, summit + 1, Z0, "air")
    t.set(CX, summit + 2, Z0, "bell[attachment=ceiling,facing=north,powered=false]")
    # high windows in the long walls, rose window over the door
    for z in (5, 8, 11):
        c.window(t, X0, 3, z, p["vidriera"])
        c.window(t, X1, 3, z, p["vidriera"])
    c.window(t, CX, 4, Z0, p["vidriera"])
    # pews facing the altar (south): backrest to the north
    for z in (5, 7):
        for x in (X0 + 1, X0 + 2, X1 - 2, X1 - 1):
            t.set(x, 1, z, f"{m}_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]")
    # chancel: step, altar with candles; the cell behind a partition with a door
    t.fill(X0 + 1, 1, 9, X1 - 1, 1, 9, f"{p['losa']}[type=bottom,waterlogged=false]")
    t.fill(X0 + 1, 1, 10, X1 - 1, 4, 10, p["muro"])
    t.set(CX, 1, 10, p["altar"])
    t.set(CX, 2, 10, "candle[candles=4,lit=true,waterlogged=false]")
    t.set(CX, 3, 10, p["muro"])
    c.door(t, X1 - 1, 1, 10, "south", f"{m}_door")
    t.set(X1 - 1, 1, 9, "air")
    # The cell's own door, in the south wall. With the north door alone a hermit coming home from the south stopped
    # against this wall, his bed two blocks away through it and some thirty on foot round the chapel: a villager's
    # search never finds a path of 16 blocks or more (26.3), and on a server he did not get home 5 times in 8.
    c.door(t, X1 - 2, 1, Z1, "north", f"{m}_door")
    c.bed(t, X0 + 1, 12, "west", p["cama"])
    c.place_chest(t, X1 - 1, 1, 12, "west", MID, "celda")
    t.set(CX, 1, 12, "lectern[facing=north,has_book=false,powered=false]")
    t.entity(CX + 1, 1, 11, inh.villager(MID, "ermitano", "Ermitaño", "librarian", p["aldeano"], hermit_offers(), rot=180.0))
    c.lantern(t, CX, 4, 7)
    c.lantern(t, CX, 4, 11)
    inh.bell(t, CX - 2, 1)       # the hand bell at the door (the gable's is out of reach): the hermit's meeting point
    return t


def _roof_z(t, p, y):
    """Gable roof with the ridge along z (the slopes to the east and west)."""
    xa, xb, yy = X0 - 1, X1 + 1, y
    while True:
        for z in range(Z0 - 1, Z1 + 2):
            if xa == xb:
                t.set(xa, yy, z, p["cumbrera"])
            else:
                t.set(xa, yy, z, f"{p['teja']}[facing=east,half=bottom,shape=straight,waterlogged=false]")
                t.set(xb, yy, z, f"{p['teja']}[facing=west,half=bottom,shape=straight,waterlogged=false]")
        if xa == xb:
            return yy
        for z in (Z0, Z1):
            for x in range(max(xa + 1, X0), min(xb - 1, X1) + 1):
                t.set(x, yy, z, p["muro"])
        xa, xb, yy = xa + 1, xb - 1, yy + 1


def _garden(t, p, x0, x1):
    """Fenced garden from x0..x1 (z 4..12) with terraces, an irrigation ditch with a fountain in the center and a composter."""
    m = p["madera"]
    z0, z1 = 4, 12
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if x in (x0, x1) or z in (z0, z1):
                t.set(x, 1, z, f"{m}_fence")
            elif (x, z) == ((x0 + x1) // 2, (z0 + z1) // 2):
                t.set(x, 0, z, "water[level=0]")
            else:
                t.set(x, 0, z, "farmland[moisture=7]")
                t.set(x, 1, z, p["cultivos"][(z // 2) % len(p["cultivos"])])
    t.set((x0 + x1) // 2, 1, z0, f"{m}_fence_gate[facing=north,in_wall=false,open=false,powered=false]")
    # one block clear of the fence: against it, the hermit hopped onto the composter, over the fence and into the
    # garden, and with the gate shut he could not get out (nor reach his bed: the game made him give it up)
    t.set(x0 + 1, 1, z0 - 2, "composter[level=0]")


def orchard_east(p, name):
    t = _chapel(p, name)
    _garden(t, p, X1 + 2, WIDTH - 2)
    return t


def churchyard(p, name):
    """Garden to the west and, to the east, three graves with their headstones and a candle."""
    t = _chapel(p, name)
    _garden(t, p, 1, X0 - 2)
    for z in (5, 8, 11):
        t.set(X1 + 4, 1, z, p["lapida"])
        t.set(X1 + 4, 2, z, "candle[candles=1,lit=false,waterlogged=false]")
        for dx in (1, 2):
            t.set(X1 + 4 + dx, 0, z, "packed_mud")
    return t


_CROPS_SHORT = ["wheat[age=7]", "carrots[age=7]", "potatoes[age=7]", "beetroots[age=3]"]
STYLES = {
    "montana": dict(biomas=["grove", "snowy_slopes"],
                    paleta=dict(madera="spruce", muro="stone_bricks", esquina="chiseled_stone_bricks", zocalo="cobblestone",
                                suelo="polished_andesite", losa="stone_brick_slab", altar="chiseled_stone_bricks",
                                teja="spruce_stairs", cumbrera="spruce_planks", peldano="stone_brick_stairs",
                                vidriera="light_blue_stained_glass_pane", cama="blue", lapida="cobblestone_wall",
                                cultivos=_CROPS_SHORT, aldeano="snow", patio=["minecraft:cobblestone", "minecraft:dirt_path"]),
                    variantes={"a": orchard_east, "b": churchyard}),
    "oscuro": dict(biomas=["dark_forest", "pale_garden"], convencionales=["c:is_dark_forest"],
                   paleta=dict(madera="dark_oak", muro="mossy_cobblestone", esquina="dark_oak_log[axis=y]",
                               zocalo="cobblestone", suelo="spruce_planks", losa="cobblestone_slab",
                               altar="polished_deepslate", teja="dark_oak_stairs", cumbrera="dark_oak_planks",
                               peldano="cobblestone_stairs", vidriera="purple_stained_glass_pane", cama="black",
                               lapida="mossy_cobblestone_wall", cultivos=_CROPS_SHORT, aldeano="plains",
                               patio=["minecraft:dirt_path", "minecraft:packed_mud", "minecraft:mossy_cobblestone"]),
                   variantes={"a": orchard_east, "b": churchyard}),
    "cerezo": dict(biomas=["cherry_grove"],
                   paleta=dict(madera="cherry", muro="white_terracotta", esquina="stripped_cherry_log[axis=y]",
                               zocalo="stone_bricks", suelo="cherry_planks", losa="smooth_stone_slab",
                               altar="calcite", teja="cherry_stairs", cumbrera="cherry_planks",
                               peldano="stone_brick_stairs", vidriera="pink_stained_glass_pane", cama="pink",
                               lapida="stone_brick_wall", cultivos=_CROPS_SHORT, aldeano="plains",
                               patio=["minecraft:dirt_path", "minecraft:stone_bricks"]),
                   variantes={"a": orchard_east, "b": churchyard}),
}
