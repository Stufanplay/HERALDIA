"""Traces of work in progress (aldeas.vida.rastros): signs that someone lives in the village, placed when it generates and
made of blocks only (no entity, no block that ticks more than a vanilla village already has).

A village draws, among its houses and fillers, a few "plots" (`<style>/fillers/plot`): a flat plot of the style's
ground with a slot. On the slot the game places one trace (`<style>/traces/<kind>`), drawn with the weights of the
style: a house half built with scaffolding, laundry hanging out, a meal left half eaten, a work yard with the tools lying
where someone was working, a cart loaded with goods, fish drying on racks, a cooking fire with the pot on.

- Each style draws only the traces that suit it (TRACES_BY_FAMILY, with STYLE_CHANGES): no laundry or picnic in the snow,
  no picnic in the gloomy dark forest, fish racks only on the coast, in the swamp and in the Norse taiga...
- Nothing functional: no bed, no workstation (the villagers' job sites: barrel, composter, cauldron, smoker,
  grindstone, stonecutter...), no bell, no chest with loot. Moving or adding those is the job of the village layout.
- With the option off, the Java side (villages/VillageStructure) removes the trace pieces when the village is created and the
  plot stays as an empty plot of grass or sand. Villages already generated do not change.
- Determinism: each trace uses its own random source (`<seed>/<style>/traces/<kind>`), not the style's shared one, so the
  rest of the style's templates do not change.
"""
import random
from core import Template, nsid
from build import log, stairs, lantern, potted, table, chair

# Footprint of a plot (like the fillers: 7 wide, the entrance on the north face) and of its trace (7 x 7, from z = 1).
W, D, H = 7, 7, 8
PLOT_WEIGHT = 2            # weight of the plot in the houses pool (each filler has 1, the houses 2-3 each)
KINDS = ("building_site", "laundry", "meal", "workyard", "cart", "fish_rack", "cookfire")

# Weights of each trace per family (0 or missing: never in that family). "Con medida": the traces are a few plots of the
# village, and each family only gets what makes sense in its climate.
TRACES_BY_FAMILY = {
    "llanuras": dict(building_site=3, laundry=3, meal=2, workyard=2, cart=3, cookfire=1),
    "bosque": dict(building_site=3, laundry=2, meal=2, workyard=3, cart=2, cookfire=2),
    "oscuro": dict(building_site=2, laundry=1, workyard=2, cart=2, cookfire=2),
    "taiga": dict(building_site=2, laundry=1, workyard=3, cart=2, cookfire=3),
    "nieve": dict(building_site=2, workyard=3, cart=2, cookfire=3),
    "desierto": dict(building_site=3, laundry=3, meal=1, workyard=2, cart=3, cookfire=2),
    "sabana": dict(building_site=2, laundry=2, meal=1, workyard=2, cart=2, cookfire=3),
    "jungla": dict(building_site=2, laundry=2, meal=1, workyard=2, cart=1, cookfire=3, fish_rack=1),
    "pantano": dict(building_site=2, laundry=2, workyard=1, cart=1, cookfire=3, fish_rack=3),
    "cerezos": dict(building_site=2, laundry=2, meal=3, workyard=2, cart=1, cookfire=1),
    "badlands": dict(building_site=2, laundry=1, workyard=3, cart=3, cookfire=2),
    "costa": dict(building_site=2, laundry=3, meal=2, workyard=1, cart=2, cookfire=2, fish_rack=4),
}
# Per-style changes on top of the family (kind: weight; 0 removes it).
STYLE_CHANGES = {
    "oscuro_gotica": dict(laundry=0),             # a gloomy stone town: washing on a line looks out of place
    "oscuro_fortificada": dict(cart=3, cookfire=3),
    "taiga_nordica": dict(fish_rack=3),
    "taiga_cazadores": dict(cookfire=4),
    "desierto_caravanera": dict(cart=4),
    "desierto_obelisco": dict(laundry=1),
    "bosque_abadia": dict(laundry=1, meal=0),      # monks: their meals are in the refectory
    "pantano_brujas": dict(laundry=1),
    "cerezos_templo": dict(laundry=0, cart=0),     # a temple town: tea in the garden, not carts
    "badlands_minera": dict(cart=4),
    "costa_mediterranea": dict(laundry=4),
}
# Workstations and functional blocks that a trace must never place (the village layout owns them).
FUNCTIONAL = ("barrel", "composter", "cauldron", "smoker", "blast_furnace", "brewing_stand", "cartography_table",
              "fletching_table", "grindstone", "lectern", "loom", "smithing_table", "stonecutter", "_bed", "bell", "chest")
# Families whose work yard is a carpenter's (logs, planks); the rest work stone.
WOOD_FAMILIES = {"bosque", "taiga", "oscuro", "jungla", "pantano", "cerezos", "nieve"}


def weights(th):
    """{kind: weight} of the style (only those with weight > 0), in KINDS order."""
    w = dict(TRACES_BY_FAMILY[th["family"]])
    w.update(STYLE_CHANGES.get(th["id"], {}))
    return {k: w[k] for k in KINDS if w.get(k, 0) > 0}


def soil_of(th):
    return {"desierto": "sand", "badlands": "red_sand"}.get(th["family"], "grass_block")


def _ground(t, th, rng, paths=0.35):
    """The trace's own floor (y = 0): the style's ground with worn patches of path."""
    soil = soil_of(th)
    for x in range(W):
        for z in range(D):
            t.set(x, 0, z, th["path2"] if rng.random() < paths else soil)


def _fence_line(t, th, x0, x1, y, z):
    for x in range(x0, x1 + 1):
        t.set(x, y, z, th["fence"])


def _posts(t, th, xs, z, h):
    for x in xs:
        for y in range(1, h + 1):
            t.set(x, y, z, th["fence"])


def building_site(t, th, rng):
    """A house half built: the foundation laid, the walls rising unevenly, scaffolding, the floor half laid and the
    materials piled up next to it."""
    _ground(t, th, rng, 0.5)
    wall = log(th["wall"], "y")
    t.fill(1, 0, 1, 5, 0, 5, log(th["found"], "y"))
    for x in range(2, 5):
        for z in range(2, 5):
            t.set(x, 0, z, th["floor"] if (x + z) % 3 else th["path2"])
    back = [3, 3, 2, 2, 1]                   # the back wall, highest where the work started
    for i, x in enumerate(range(1, 6)):
        for y in range(1, back[i] + 1):
            t.set(x, y, 5, wall)
    for z, h in ((4, 2), (3, 1), (2, 1)):     # the west wall, lower towards the front
        for y in range(1, h + 1):
            t.set(1, y, z, wall)
    t.set(5, 1, 4, wall)
    t.set(5, 1, 1, wall); t.set(1, 1, 1, wall)  # the front corners; the doorway is left open
    for y in range(1, 5):                     # scaffolding against the back wall, standing on the ground
        t.set(6, y, 5, "scaffolding[bottom=false,distance=0,waterlogged=false]")
        t.set(0, y, 5, "scaffolding[bottom=false,distance=0,waterlogged=false]")
    t.set(6, 1, 1, wall); t.set(6, 1, 2, wall); t.set(6, 2, 1, wall)       # stacked building blocks
    t.set(0, 1, 2, f"{th['wslab']}[type=bottom]"); t.set(0, 1, 3, f"{th['wslab']}[type=bottom]")   # planks waiting
    t.set(3, 1, 4, log(th["log"], "x"))       # a beam lying inside
    t.set(6, 1, 3, lantern(th, False))


def laundry(t, th, rng):
    """Washing hanging out to dry: two posts with a line between them and the clothes (banners) on both sides."""
    _ground(t, th, rng, 0.25)
    _posts(t, th, (1, 5), 3, 3)
    _fence_line(t, th, 2, 4, 3, 3)
    cols = ["white"] + list(th["carpet"])
    for i, x in enumerate((2, 3, 4)):
        side, facing = (4, "south") if i % 2 == 0 else (2, "north")
        t.set(x, 3, side, f"{cols[i % len(cols)]}_wall_banner[facing={facing}]")
    t.set(5, 1, 5, "decorated_pot[facing=north]")            # the basket
    t.set(4, 1, 5, f"{cols[0]}_carpet")                      # folded clothes on the ground


def meal(t, th, rng):
    """A meal left half eaten in the open: a table with chairs, the cake half finished, a candle and a flower pot."""
    _ground(t, th, rng, 0.2)
    for x in range(2, 5):
        table(t, th, x, 1, 3)
    for x in (2, 4):
        chair(t, th, x, 1, 2, "north")
        chair(t, th, x, 1, 4, "south")
    t.set(3, 2, 3, f"cake[bites={rng.choice((2, 3, 4))}]")
    t.set(2, 2, 3, "candle[candles=2,lit=false]")
    t.set(4, 2, 3, potted(rng.choice(th["plants"])))
    t.set(5, 1, 4, f"{th['wslab']}[type=bottom]")             # a bench to one side


def workyard(t, th, rng):
    """A work yard with the tools lying where someone was working: a carpenter's (sawhorse, logs, planks) or a stonemason's
    (blocks, slabs, the anvil), depending on the family."""
    _ground(t, th, rng, 0.45)
    if th["family"] in WOOD_FAMILIES:
        _posts(t, th, (2,), 2, 1); _posts(t, th, (2,), 4, 1)          # sawhorse
        for z in (2, 3, 4):
            t.set(2, 2, z, log(th["stripped"], "z"))
        t.set(2, 1, 3, "air")
        for x in (4, 5):                                             # logs waiting to be cut
            t.set(x, 1, 5, log(th["log"], "x"))
        t.set(5, 2, 5, log(th["log"], "x"))
        t.set(4, 1, 2, log(th["stripped"], "y"))                     # the chopping block
        t.set(5, 1, 1, f"{th['wslab']}[type=bottom]"); t.set(5, 1, 2, f"{th['wslab']}[type=bottom]")
        t.set(3, 1, 3, "lever[face=floor,facing=east,powered=false]")   # the saw, left on the ground
    else:
        stone = log(th["wall"], "y") if "log" not in th["wall"] and "planks" not in th["wall"] else th["found"]
        for (x, y, z) in ((1, 1, 4), (2, 1, 4), (1, 2, 4), (1, 1, 5), (2, 1, 5)):
            t.set(x, y, z, stone)
        t.set(4, 1, 5, "stone_brick_slab[type=bottom]"); t.set(5, 1, 5, "stone_brick_slab[type=bottom]")
        t.set(4, 1, 2, "chipped_anvil[facing=east]")
        t.set(3, 1, 3, "lever[face=floor,facing=east,powered=false]")   # the mallet
        t.set(5, 0, 3, "cobblestone"); t.set(4, 0, 3, "cobblestone")          # stone chips


def cart(t, th, rng):
    """A cart loaded with goods next to the stores, and what was left to unload on the ground."""
    _ground(t, th, rng, 0.6)
    for x in (2, 3, 4):
        t.set(x, 1, 3, f"{th['wslab']}[type=top]")
    for x in (2, 4):
        t.set(x, 1, 2, f"{th['trapdoor']}[facing=north,half=bottom,open=true]")
        t.set(x, 1, 4, f"{th['trapdoor']}[facing=south,half=bottom,open=true]")
    t.set(1, 1, 3, th["fence"])                                      # the shaft
    goods = {"desierto": "decorated_pot[facing=north]", "badlands": "cobblestone", "costa": "dried_kelp_block",
             "pantano": "dried_kelp_block", "nieve": log(th["log"], "x"), "jungla": "melon",
             "sabana": "hay_block[axis=x]"}.get(th["family"], "pumpkin")
    t.set(2, 2, 3, "hay_block[axis=x]"); t.set(3, 2, 3, goods); t.set(4, 2, 3, "decorated_pot[facing=north]")
    t.set(5, 1, 5, "hay_block[axis=y]"); t.set(4, 1, 5, goods)      # unloaded
    t.set(5, 1, 1, lantern(th, False))


def fish_rack(t, th, rng):
    """Fish drying in the sun: drying tables with bundles and a rack with the boards hung up."""
    _ground(t, th, rng, 0.3)
    for x in (1, 2, 4, 5):
        t.set(x, 1, 2, f"{th['wslab']}[type=top]")
        if rng.random() < 0.75:
            t.set(x, 2, 2, "dried_kelp_block")
    _posts(t, th, (1, 5), 5, 2)
    _fence_line(t, th, 2, 4, 2, 5)
    for x in (2, 3, 4):
        t.set(x, 1, 4, f"{th['trapdoor']}[facing=north,half=top,open=true]")
    t.set(3, 1, 2, "decorated_pot[facing=north]")                    # the salt jar


def cookfire(t, th, rng):
    """A cooking fire with the pot on: the pot hangs from a beam over the lit fire, with log seats and firewood."""
    _ground(t, th, rng, 0.5)
    t.set(3, 1, 3, "campfire[lit=true,signal_fire=false]")
    _posts(t, th, (1, 5), 3, 4)
    _fence_line(t, th, 2, 4, 4, 3)
    t.set(3, 3, 3, "iron_chain[axis=y]")
    t.set(3, 2, 3, "decorated_pot[facing=north]")
    t.set(3, 1, 5, log(th["stripped"], "x")); t.set(3, 1, 1, log(th["stripped"], "x"))
    t.set(5, 1, 5, log(th["log"], "x")); t.set(5, 2, 5, log(th["log"], "x")); t.set(4, 1, 5, log(th["log"], "x"))


BUILDERS = dict(building_site=building_site, laundry=laundry, meal=meal, workyard=workyard, cart=cart,
                fish_rack=fish_rack, cookfire=cookfire)


def trace(th, seed, kind):
    """Template of one trace (its own floor at y = 0, its slot jigsaw at the origin, the ground block as final state)."""
    t = Template(f"{th['id']}/traces/{kind}")
    BUILDERS[kind](t, th, random.Random(f"{seed}/{th['id']}/traces/{kind}"))
    ground = t.get(0, 0, 0) or soil_of(th)
    t.jigsaw(0, 0, 0, "down_south", "heraldia:bottom", "heraldia:slot", "minecraft:empty",
             final_state=ground if ground.startswith("minecraft:") else f"minecraft:{ground}", joint="aligned")
    t.min_size = (W, H - 1, D)
    return t


def plot(th):
    """The plot: flat ground of the style, cleared above, with the slot of its trace. Without the trace (option off) it is an
    empty plot."""
    t = Template(f"{th['id']}/fillers/plot")
    t.jigsaw(3, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty", final_state=th["path"])
    soil = soil_of(th)
    for x in range(W):
        for z in range(1, D + 1):
            t.set(x, 0, z, soil)
            for y in range(1, H):
                t.set(x, y, z, "air")
    # the slot goes UNDER the plot's floor: a jigsaw facing up places its child's jigsaw in the cell above it, so the
    # trace's own floor (its y = 0, where its jigsaw is) takes the place of the plot's. With the slot at y = 0 the
    # trace stood a block above the plot, and from its floor a neighbour's 1.5-high wall was half a block up: a step
    # the game's path search takes (docs/LESSONS.md, "A villager gets into a walled cemetery").
    t.jigsaw(0, -1, 1, "up_south", "heraldia:slot", "heraldia:bottom", nsid(f"{th['id']}/traces"),
             final_state=f"minecraft:{soil}", joint="aligned")
    t.min_size = (W, H, D + 1)
    return t


def build(reg, th, seed):
    """Adds the plot and the style's traces to the registry; returns the plot's name (for the houses pool) or None if the
    style has no trace."""
    w = weights(th)
    if not w:
        return None
    els = [(reg.add(trace(th, seed, k), "trace"), n, "rigid", None) for k, n in w.items()]
    reg.pool(f"{th['id']}/traces", els, fallback=f"{th['id']}/traces")
    return reg.add(plot(th), "filler")
