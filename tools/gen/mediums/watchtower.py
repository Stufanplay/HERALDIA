"""Watchtower (heraldia:medianas/torre_vigia/<estilo>): 7 x 7 square tower in a 15 x 15 courtyard with its
beacon fire on top. Variant a: three floors and a covered lookout with a skeleton archer (the challenge); b: two floors, open
terrace and an attached firewood shed, and the lookout who lives there (a fletcher with fixed trades: his bed and his
fletching table on the ground floor, which he reaches without the ladder)."""
from core import Template, F
from loot import item, empty
from uniques._common import chest_loot
from . import _common as c
from . import _inhabitants as inh

MID = "torre_vigia"
DISPLAY_NAME = {"es_es": "Torre de vigía", "en_us": "Watchtower"}
SEPARATION = 640
ADVANCEMENT_ICON = "minecraft:spyglass"
LANG = chest_loot.lang("heraldia.medianas.torre_vigia.", {
    "arquero": ("Vigía del camino", "Road Watcher"),
    "vigilante": ("Vigía", "Lookout"),
})
LOOT = {
    "vigia": chest_loot.place_chest(((2, 4), [item("arrow", 10, 4, 12), item("bread", 8, 1, 3), item("torch", 6, 2, 6),
                                   item("iron_nugget", 6, 2, 6), item("coal", 6, 1, 4), item("string", 4, 1, 3),
                                   item("spyglass", 1), item("map", 2), item("bow", 2, dmg=(0.3, 0.8)), empty(4)]),
                         ((1, 2), [item("emerald", 3), item("iron_ingot", 2), item("arrow", 4, 2, 6), empty(8)])),
    "provisiones": chest_loot.place_chest(((2, 4), [item("bread", 8, 1, 4), item("apple", 6, 1, 3), item("cooked_mutton", 4, 1, 2),
                                         item("wheat", 6, 2, 5), item("leather", 3), item("candle", 3, 1, 2), empty(6)]),
                               ((1, 1), [item("emerald", 2), empty(8)])),
}

L = 15                # patio de 15 x 15
X0, Z0, X1, Z1 = 4, 5, 10, 11   # tower walls (7 x 7)
CX = 7                # axis of the door and the ladder


def lookout_offers():
    em = lambda n: {"id": "minecraft:emerald", "count": n}
    return [c.offer({"id": "minecraft:stick", "count": 32}, em(1), 16),
            c.offer(em(1), {"id": "minecraft:arrow", "count": 12}, 12),
            c.offer(em(1), {"id": "minecraft:torch", "count": 8}, 12),
            c.offer(em(4), {"id": "minecraft:spyglass", "count": 1}, 2)]


def _floor(p):
    mats = p["patio"]
    return lambda x, z: "minecraft:dirt_path" if x == CX and z < Z0 else mats[(x * 7 + z * 13 + x * z) % len(mats)]


def _tower(t, p, floors, deck):
    """Tower of `floors` floors 4 high (floors at y = 0, 5, 9...), terrace with battlements and a beacon fire."""
    m = p["madera"]
    roof = 5 + 4 * (floors - 1)                          # terrace floor
    t.fill(X0, 0, Z0, X1, 0, Z1, p["zocalo"])
    t.fill(X0 + 1, 0, Z0 + 1, X1 - 1, 0, Z1 - 1, f"{m}_planks")
    c.box(t, X0, 1, Z0, X1, roof - 1, Z1, p["muro"], corner_block=p["esquina"])
    for y in range(5, roof + 1, 4):                      # floors (the last one is the terrace)
        t.fill(X0 + 1, y, Z0 + 1, X1 - 1, y, Z1 - 1, f"{m}_planks")
        t.fill(X0, y, Z0, X1, y, Z1, p["muro"], keep=True)
        for x, z in ((X0, Z0), (X0, Z1), (X1, Z0), (X1, Z1)):
            t.set(x, y, z, p["esquina"])
    c.ladder(t, CX, Z1 - 1, 1, roof, "north")      # against the south wall, passes through the floors
    c.door(t, CX, 1, Z0, "south", f"{m}_door")
    # arrow slits: in the center of the east and west walls of each floor and on the north of the upper ones
    for k in range(floors):
        y = 2 + 4 * k + (1 if k else 0)
        c.window(t, X0, y, 8)
        c.window(t, X1, y, 8)
        if k:
            c.window(t, CX, y, Z0)
        t.set(X1 - 1, 3 + 4 * k, Z0 + 1, "wall_torch[facing=south]")
        t.set(X0 + 1, 3 + 4 * k, Z0 + 1, "wall_torch[facing=south]")
    # battlements: merlon on the even cells of the ring; at the corners, pillars (which hold up the roof)
    y = roof + 1
    for x in range(X0, X1 + 1):
        for z in range(Z0, Z1 + 1):
            if x in (X0, X1) or z in (Z0, Z1):
                corner = x in (X0, X1) and z in (Z0, Z1)
                if corner:
                    for yy in range(y, y + (3 if deck else 1)):
                        t.set(x, yy, z, p["esquina"])
                elif (x + z) % 2 == 0:
                    t.set(x, y, z, p["muro"])
            else:
                for yy in range(y, y + 3):
                    t.set(x, yy, z, "air")
    t.set(CX, y, 8, "campfire[facing=north,lit=true,signal_fire=false,waterlogged=false]")
    if deck:
        t.fill(X0 - 1, y + 3, Z0 - 1, X1 + 1, y + 3, Z1 + 1, f"{m}_slab[type=bottom,waterlogged=false]")
        c.lantern(t, CX, y + 2, 8)
    return roof


def _courtyard(t, p):
    c.courtyard(t, 0, 0, L - 1, L - 1, _floor(p))
    c.entrance(t, CX, f"{p['peldano']}[facing=south,half=bottom,shape=straight,waterlogged=false]")
    m = p["madera"]
    for x in (CX - 2, CX + 2):                             # lanterns at the sides of the path
        t.set(x, 1, 2, f"{m}_fence")
        c.lantern(t, x, 2, 2, hanging=False)


def upper(p, name):
    """Three floors (storeroom, bedroom, armory) and a covered lookout with the archer."""
    t = Template(name)
    _courtyard(t, p)
    m = p["madera"]
    roof = _tower(t, p, 3, deck=True)
    c.place_chest(t, X0 + 1, 1, Z0 + 2, "east", MID, "vigia")
    c.place_chest(t, X0 + 1, 1, Z0 + 3, "east", MID, "provisiones", kind="barrel")
    t.set(X1 - 1, 1, Z1 - 1, "crafting_table")
    c.bed(t, X0 + 1, Z1 - 2, "west", "red", y=6)
    c.lantern(t, X1 - 1, 8, Z0 + 2)
    t.set(X1 - 1, 10, Z0 + 2, "fletching_table")
    t.set(X1 - 1, 10, Z0 + 3, f"{m}_slab[type=bottom,waterlogged=false]")
    t.entity(X0 + 1, roof + 1, Z0 + 1, c.mob(
        "skeleton", MID, "arquero", LANG["es_es"]["heraldia.medianas.torre_vigia.arquero"], rot=180.0,
        equipment={"mainhand": {"id": "minecraft:bow", "count": 1}, "head": {"id": "minecraft:chainmail_helmet", "count": 1}},
        drop_chances={"head": F(0.0)}))
    return t


def lower(p, name):
    """Two floors, open terrace and a firewood shed attached to the east; the lookout sleeps and works on the ground floor."""
    t = Template(name)
    _courtyard(t, p)
    m = p["madera"]
    _tower(t, p, 2, deck=False)
    # the bed along the east wall, its foot clear of the ladder, and the ladder's foot shut behind a fence gate: a lookout
    # who climbed it had no way down to his bed and workstation (mediums/_paths.stranded)
    c.bed(t, X1 - 1, Z1 - 1, "south", "brown")
    c.ladder_closet(t, CX, 1, Z1 - 1, m, p["tronco"], {(0, -1): "gate", (-1, 0): "post", (1, 0): "post"})
    t.set(X1 - 1, 1, Z0 + 1, "fletching_table")
    inh.bell(t, CX - 4, 2)                                    # the alarm bell by the gate: the lookout's meeting point
    t.entity(X0 + 2, 1, 8, inh.villager(MID, "vigilante", "Vigía", "fletcher", p["aldeano"], lookout_offers(), rot=180.0))
    c.place_chest(t, X0 + 1, 1, Z0 + 2, "east", MID, "vigia")
    c.bed(t, X0 + 1, Z1 - 2, "west", "blue", y=6)
    t.set(X1 - 1, 6, Z0 + 1, "crafting_table")
    # shed: posts at x = 13, small slab roof at y = 4, firewood and hay inside, open to the north
    for z in (Z0 + 1, Z1 - 1):
        for y in (1, 2, 3):
            t.set(X1 + 3, y, z, f"{m}_fence")
    t.fill(X1 + 1, 4, Z0 + 1, X1 + 3, 4, Z1 - 1, f"{m}_slab[type=bottom,waterlogged=false]")
    for z in range(Z0 + 2, Z1 - 1):
        t.set(X1 + 1, 1, z, f"{p['tronco']}[axis=z]")
    t.set(X1 + 1, 2, Z0 + 3, f"{p['tronco']}[axis=z]")
    t.set(X1 + 2, 1, Z1 - 1, "hay_block[axis=y]")
    c.place_chest(t, X1 + 2, 1, Z1 - 2, "west", MID, "provisiones", kind="barrel")
    c.lantern(t, X1 + 2, 3, 8)
    return t


STYLES = {
    "colinas": dict(biomas=["windswept_hills", "windswept_gravelly_hills", "windswept_forest", "windswept_savanna",
                            "meadow"],
                    convencionales=["c:is_windswept"],
                    paleta=dict(muro="stone_bricks", esquina="polished_andesite", zocalo="cobblestone", madera="spruce",
                                tronco="spruce_log", peldano="cobblestone_stairs", aldeano="plains",
                                patio=["minecraft:cobblestone", "minecraft:dirt_path", "minecraft:mossy_cobblestone",
                                       "minecraft:dirt_path"]),
                    variantes={"a": upper, "b": lower}),
    "taiga": dict(biomas=["taiga", "old_growth_pine_taiga", "old_growth_spruce_taiga", "snowy_taiga"],
                  convencionales=["minecraft:is_taiga", "c:is_taiga"],
                  paleta=dict(muro="cobblestone", esquina="stripped_spruce_log[axis=y]", zocalo="mossy_cobblestone",
                              madera="spruce", tronco="spruce_log", peldano="spruce_stairs", aldeano="taiga",
                              patio=["minecraft:dirt_path", "minecraft:packed_mud", "minecraft:dirt_path",
                                     "minecraft:cobblestone"]),
                  variantes={"a": upper, "b": lower}),
}
