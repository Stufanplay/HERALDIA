"""Hunters' outpost (heraldia:medianas/cazadores/<estilo>): 17 x 17 clearing with a 7 x 7 log cabin
(stone chimney, bunks and the furs chest), a fur drying rack, a chopping block for firewood and a hunting lookout
on four posts. Variant a: the hunter (a villager with fixed trades: buys rabbit hides, sells leather, arrows
and a leather chestplate), his partner the archer (fletcher: buys sticks and flint, sells arrows and a bow) and his wolf;
they live there (a bunk each, the hunter's cauldron for tanning and the archer's fletching table); b: the outpost with the
campfire out and a meat smokehouse, and the hunter alone. No monsters."""
from core import Template
from loot import item, empty
from uniques._common import chest_loot
from . import _common as c
from . import _inhabitants as inh

MID = "cazadores"
DISPLAY_NAME = {"es_es": "Puesto de cazadores", "en_us": "Hunters' Lodge"}
SEPARATION = 768
ADVANCEMENT_ICON = "minecraft:rabbit_hide"
LANG = chest_loot.lang("heraldia.medianas.cazadores.", {
    "cazador": ("Cazador", "Hunter"),
    "lobo": ("Colmillo", "Fang"),
    "arquero": ("Arquero", "Archer"),
})
ADVANCEMENTS = [dict(id="pieles", icono="minecraft:leather", tabla="pieles",
               titulo=("Piel de invierno", "Winter Pelts"),
               descripcion=("Abre el arcón de las pieles de un puesto de cazadores",
                            "Open the pelt chest of a hunters' lodge"))]
LOOT = {
    "pieles": chest_loot.place_chest(((3, 5), [item("leather", 10, 1, 4), item("rabbit_hide", 8, 1, 4), item("rabbit_foot", 2),
                                    item("feather", 5, 2, 6), item("cooked_rabbit", 5, 1, 3), item("cooked_mutton", 5, 1, 3),
                                    item("arrow", 6, 4, 12), item("lead", 3), item("leather_horse_armor", 1),
                                    item("bow", 2, dmg=(0.3, 0.8)), empty(4)]),
                          ((1, 1), [item("emerald", 3, 1, 2), item("name_tag", 1), empty(8)])),
    "despensa": chest_loot.place_chest(((2, 4), [item("cooked_beef", 5, 1, 3), item("cooked_porkchop", 4, 1, 2),
                                      item("rabbit_stew", 2), item("sweet_berries", 5, 2, 6), item("bread", 5, 1, 3),
                                      item("charcoal", 4, 2, 6), item("string", 4, 1, 3), item("iron_nugget", 4, 2, 5),
                                      empty(6)]),
                            ((1, 1), [item("emerald", 2), empty(8)])),
}

L = 17
X0, Z0, X1, Z1 = 2, 5, 8, 11       # cabin (7 x 7), door to the north
DOOR_COL = 5


def offers():
    em = lambda n: {"id": "minecraft:emerald", "count": n}
    return [c.offer({"id": "minecraft:rabbit_hide", "count": 9}, em(1), 12),
            c.offer(em(1), {"id": "minecraft:leather", "count": 3}, 12),
            c.offer(em(1), {"id": "minecraft:arrow", "count": 16}, 12),
            c.offer(em(4), {"id": "minecraft:leather_chestplate", "count": 1}, 3)]


def archer_offers():
    em = lambda n: {"id": "minecraft:emerald", "count": n}
    return [c.offer({"id": "minecraft:stick", "count": 32}, em(1), 16),
            c.offer({"id": "minecraft:flint", "count": 24}, em(1), 12),
            c.offer(em(1), {"id": "minecraft:arrow", "count": 12}, 12),
            c.offer(em(3), {"id": "minecraft:bow", "count": 1}, 3)]


def _clearing(x, z):
    """Round clearing: the natural terrain remains outside."""
    return (x - L // 2) ** 2 + (z - L // 2) ** 2 <= (L // 2 + 0.5) ** 2


def _floor(p):
    mats = p["suelo"]
    return lambda x, z: "minecraft:dirt_path" if x == DOOR_COL and z < Z0 else mats[(x * 3 + z * 11 + x * z) % len(mats)]


def _outpost(p, name, lit):
    t = Template(name)
    m, tr = p["madera"], p["tronco"]
    c.courtyard(t, 0, 0, L - 1, L - 1, _floor(p), air_block=3, inside=_clearing)
    for x in range(DOOR_COL - 1, DOOR_COL + 2):          # the clearing is round: the north edge of the path, explicit
        t.set(x, 0, 0, "minecraft:dirt_path")
        for y in (1, 2, 3):
            t.set(x, y, 0, "air")
    c.entrance(t, DOOR_COL, "minecraft:dirt_path")
    # log cabin: horizontal logs that cross at the corners
    t.fill(X0, 0, Z0, X1, 0, Z1, p["zocalo"])
    t.fill(X0 + 1, 0, Z0 + 1, X1 - 1, 0, Z1 - 1, f"{m}_planks")
    for y in range(1, 4):
        for x in range(X0, X1 + 1):
            for z in range(Z0, Z1 + 1):
                if x in (X0, X1) or z in (Z0, Z1):
                    corner_block = x in (X0, X1) and z in (Z0, Z1)
                    axis = "y" if corner_block else ("x" if z in (Z0, Z1) else "z")
                    t.set(x, y, z, f"{tr}[axis={axis}]")
                else:
                    t.set(x, y, z, "air")
    t.fill(X0, 4, Z0, X1, 4, Z1, f"{m}_planks")
    summit = c.roof_tiles(t, X0, Z0, X1, Z1, 4, p["teja"], p["cumbrera"], f"{m}_planks")
    c.door(t, DOOR_COL, 1, Z0, "south", f"{m}_door")
    c.window(t, X0, 2, 8)
    c.window(t, X1, 2, 7)
    # stone chimney in the east wall with the hearth inside
    t.set(X1, 1, 9, p["piedra"])
    t.set(X1 - 1, 1, 9, f"campfire[facing=west,lit={'true' if lit else 'false'},signal_fire=false,waterlogged=false]")
    for y in range(2, 4):
        t.set(X1 - 1, y, 9, p["piedra"])
    t.set(X1, 2, 9, p["piedra"])
    t.set(X1, 3, 9, p["piedra"])
    t.fill(X1 - 1, 4, 9, X1 - 1, summit + 1, 9, p["piedra"])
    # bunks to the west, furs chest and pantry
    c.bed(t, X0 + 1, Z1 - 1, "west", p["cama"])
    c.bed(t, X0 + 1, Z1 - 3, "west", p["cama"])
    c.place_chest(t, X0 + 1, 1, Z0 + 1, "east", MID, "pieles")
    c.place_chest(t, X1 - 1, 1, Z1 - 1, "west", MID, "despensa", kind="barrel")
    t.set(X1 - 1, 1, Z0 + 1, "crafting_table")
    t.set(X1 - 1, 1, Z0 + 2, "cauldron")                       # the hunter's: tanning (leatherworker)
    c.lantern(t, DOOR_COL, 3, 8)
    # fur drying rack to the east: two posts with a crossbar and leather (brown carpets) on the ground
    for z in (6, 10):
        t.fill(14, 1, z, 14, 2, z, f"{m}_fence")
    t.fill(14, 2, 7, 14, 2, 9, f"{m}_fence")
    for z in range(7, 10):
        t.set(13, 1, z, f"{p['piel']}_carpet")
    # chopping block with the axe stuck in (a log and a stacked log)
    t.set(13, 1, 12, f"stripped_{tr}[axis=y]")
    t.set(12, 1, 13, f"{tr}[axis=x]")
    t.set(13, 1, 13, f"{tr}[axis=x]")
    inh.bell(t, DOOR_COL - 2, 3)                              # the camp bell: the hunters' meeting point
    return t


def _lookout(t, p, x0, z0):
    """Hunting lookout: 3 x 3 platform at y = 3 on four posts, with its ladder (against a post to the
    south) and a lantern at each corner of the railing. No higher: a villager walks into the ladder and climbs it, and
    its path search never uses ladders, so from the top it gets down only by a drop of 3 at most. With the platform at
    y = 4 (a drop of 4) the hunters' lodge's two inhabitants ended up stranded up there in CI, without bed or
    workstation (mediums/_paths.stranded)."""
    m, tr = p["madera"], p["tronco"]
    for x in (x0, x0 + 2):
        for z in (z0, z0 + 2):
            t.fill(x, 1, z, x, 2, z, f"{tr}[axis=y]")
    t.fill(x0, 3, z0, x0 + 2, 3, z0 + 2, f"{m}_planks")
    t.fill(x0 + 1, 1, z0 + 3, x0 + 1, 3, z0 + 3, f"{tr}[axis=y]")
    c.ladder(t, x0 + 1, z0 + 2, 1, 3, "north")
    for x, z in ((x0, z0), (x0 + 2, z0), (x0, z0 + 2), (x0 + 2, z0 + 2)):
        t.set(x, 4, z, f"{m}_fence")
    c.lantern(t, x0, 5, z0, hanging=False)
    c.lantern(t, x0 + 2, 5, z0, hanging=False)


def with_hunter(p, name):
    t = _outpost(p, name, lit=True)
    _lookout(t, p, 10, 1)
    t.set(X1 - 1, 1, Z0 + 3, "fletching_table")                # the archer's
    t.entity(DOOR_COL + 1, 1, 8, inh.villager(MID, "cazador", "Cazador", "leatherworker", p["aldeano"], offers(), rot=0.0,
                                              still_before=True))
    t.entity(DOOR_COL, 1, 9, inh.villager(MID, "arquero", "Arquero", "fletcher", p["aldeano"], archer_offers(), rot=90.0))
    t.entity(DOOR_COL, 1, 3, c.mob("wolf", MID, "lobo", "Colmillo", rot=0.0, variant=p["lobo"]))
    return t


def smokehouse(p, name):
    """With nobody there: the campfire out and, outside, a meat smokehouse (campfire with a small roof) next to the lookout."""
    t = _outpost(p, name, lit=False)
    _lookout(t, p, 10, 1)
    t.entity(DOOR_COL + 1, 1, 8, inh.villager(MID, "cazador", "Cazador", "leatherworker", p["aldeano"], offers(), rot=0.0))
    m = p["madera"]
    t.set(3, 1, 13, "campfire[facing=north,lit=true,signal_fire=false,waterlogged=false]")
    for x in (2, 4):
        t.fill(x, 1, 13, x, 2, 13, f"{m}_fence")
    t.fill(2, 3, 13, 4, 3, 13, f"{m}_slab[type=bottom,waterlogged=false]")
    t.set(5, 1, 13, "smoker[facing=west,lit=false]")
    return t


STYLES = {
    "nieve": dict(biomas=["snowy_plains", "ice_spikes"], convencionales=["c:is_snowy_plains"],
                  paleta=dict(madera="spruce", tronco="spruce_log", zocalo="cobblestone", piedra="cobblestone",
                              teja="spruce_stairs", cumbrera="spruce_planks", cama="white", piel="white",
                              aldeano="snow", lobo="minecraft:snowy",
                              suelo=["minecraft:dirt_path", "minecraft:packed_mud", "minecraft:dirt_path",
                                     "minecraft:gravel"]),
                  variantes={"a": with_hunter, "b": smokehouse}),
    "sabana": dict(biomas=["savanna", "savanna_plateau", "windswept_savanna"],
                   convencionales=["minecraft:is_savanna", "c:is_savanna"],
                   paleta=dict(madera="acacia", tronco="acacia_log", zocalo="smooth_sandstone", piedra="terracotta",
                               teja="acacia_stairs", cumbrera="acacia_planks", cama="orange", piel="brown",
                               aldeano="savanna", lobo="minecraft:spotted",
                               suelo=["minecraft:dirt_path", "minecraft:packed_mud", "minecraft:smooth_sandstone"]),
                   variantes={"a": with_hunter, "b": smokehouse}),
}
