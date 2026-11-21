"""Pieces specific to medium structures (the unique-structure ones are in unicas/_comun: chests, signs, doors...).

All of them work on a core.Template with y = 0 at ground level and the entrance on the north face (z = 0)."""
from core import B, F, NS, anchored
from uniques._common import pieces

STAIR_FACING = {"north", "south", "east", "west"}


def put(t):
    """Adapter for the common pieces (pieces.chest, pieces.sign, pieces.door...): put(x, y, z, state, nbt)."""
    return lambda x, y, z, st, nbt=None: t.set(x, y, z, st, nbt)


def courtyard(t, x0, z0, x1, z1, floor, air_block=2, edge_block=None, inside=None):
    """Floor of the enclosure at y = 0 (no fertile soil: no trees grow inside) and explicit air above (whatever was
    in the terrain, grass or snow, does not poke through). `floor` is a state or a function (x, z) -> state; `edge_block` that of the
    outer ring, if you want it different; `inside` (x, z) -> bool gives another shape (a round clearing): outside, the natural
    terrain remains."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if inside and not inside(x, z):
                continue
            edge = x in (x0, x1) or z in (z0, z1)
            st = edge_block if edge and edge_block else floor(x, z) if callable(floor) else floor
            t.set(x, 0, z, st)
            for y in range(1, air_block + 1):
                t.set(x, y, z, "air", keep=True)


def entrance(t, x, stair_step):
    """Entrance of the medium structure at (x, 0, 0): the jigsaw heraldia:entrance (which the audit uses for the walkthrough and
    which on generation becomes `stair_step`, the step from the terrain) on the north face of the box."""
    t.jigsaw(x, 0, 0, "north_up", "heraldia:entrance", "minecraft:empty", "minecraft:empty", final_state=stair_step)


def box(t, x0, y0, z0, x1, y1, z1, wall, corner_block=None, floor=None, air_block=True):
    """Walls from x0..x1 by z0..z1 from y0 to y1 (inclusive), with corners of `corner_block`, floor at y0 - 1 and explicit
    air inside."""
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                edge_block = x in (x0, x1) or z in (z0, z1)
                if edge_block:
                    corner = x in (x0, x1) and z in (z0, z1)
                    t.set(x, y, z, corner_block if corner and corner_block else wall)
                elif air_block:
                    t.set(x, y, z, "air")
    if floor:
        t.fill(x0, y0 - 1, z0, x1, y0 - 1, z1, floor)


def roof_tiles(t, x0, z0, x1, z1, y, stairs, ridge, gable_end, overhang=1):
    """Gable roof with the ridge along x over the walls x0..x1, z0..z1 (whose last row is y - 1):
    courses of steps from the eave (overhanging `overhang` blocks beyond the walls, at height y) to the ridge, and the
    gables (the faces at x0 and x1) filled with `gable_end`. Returns the ridge height."""
    xs = range(x0 - overhang, x1 + overhang + 1)
    za, zb, yy = z0 - overhang, z1 + overhang, y
    while True:
        if za == zb:                     # odd width: one ridge row
            for x in xs:
                t.set(x, yy, za, ridge)
            return yy
        for x in xs:
            t.set(x, yy, za, f"{stairs}[facing=south,half=bottom,shape=straight,waterlogged=false]")
            t.set(x, yy, zb, f"{stairs}[facing=north,half=bottom,shape=straight,waterlogged=false]")
        for x in (x0, x1):
            for z in range(max(za + 1, z0), min(zb - 1, z1) + 1):
                t.set(x, yy, z, gable_end)
        if za + 1 == zb:                 # even width: the two slopes meet and the ridge goes on top
            for x in xs:
                t.set(x, yy + 1, za, ridge)
                t.set(x, yy + 1, zb, ridge)
            return yy + 1
        za, zb, yy = za + 1, zb - 1, yy + 1


def door(t, x, y, z, facing, kind):
    pieces.door(put(t), x, y, z, facing, kind)


def window(t, x, y, z, glass="glass_pane"):
    t.set(x, y, z, glass)


def lantern(t, x, y, z, hanging=True):
    """Lantern hanging from the ceiling (Registry.add gives it a chain up to the ceiling if needed) or standing."""
    t.set(x, y, z, f"lantern[hanging={'true' if hanging else 'false'},waterlogged=false]")


def table_top(t, x, z, wood, chairs=("east", "west")):
    """Table (fence post and pressure plate) with stair chairs at the sides, with the backrest facing outward."""
    t.set(x, 1, z, f"{wood}_fence")
    t.set(x, 2, z, f"{wood}_pressure_plate[powered=false]")
    for side in chairs:
        dx, dz = pieces.DIRV[side]
        t.set(x + dx, 1, z + dz, f"{wood}_stairs[facing={side},half=bottom,shape=straight,waterlogged=false]")


def bed(t, x, z, facing, color="white", y=1):
    """Bed with the head at (x, y, z) facing `facing` and the foot behind."""
    dx, dz = pieces.DIRV[facing]
    t.set(x, y, z, f"{color}_bed[facing={facing},occupied=false,part=head]")
    t.set(x - dx, y, z - dz, f"{color}_bed[facing={facing},occupied=false,part=foot]")


def ladder(t, x, z, y0, y1, facing):
    for y in range(y0, y1 + 1):
        t.set(x, y, z, f"ladder[facing={facing},waterlogged=false]")


def text(mid, key, fallback):
    return pieces.text(f"{NS}.medianas.{mid}.{key}", fallback)


def mob(kind, mid, key=None, fallback=None, rot=0.0, **extra):
    """NBT of a medium-structure mob: persistent (otherwise it despawns before anyone arrives), anchored in place
    until attacked and without picking up items (core.anclado) and, with `key`, with a translatable name."""
    n = {"id": f"minecraft:{kind}", "PersistenceRequired": B(1), "Rotation": [F(rot), F(0.0)]}
    if key:
        n["CustomName"] = text(mid, key, fallback)
    n.update(extra)
    return anchored(n, always=True)


def offer(buy, sell, uses, buy_b=None):
    """Fixed trade of a template villager (the same format as the board's constable)."""
    from board import _offer
    return _offer(buy, sell, uses, buy_b)


def villager(mid, key, fallback, profession, kind, offers, rot=0.0):
    """Stationary villager with fixed trades (like the board's constable): no AI, invulnerable, with a name."""
    return {"id": "minecraft:villager", "PersistenceRequired": B(1), "NoAI": B(1), "Invulnerable": B(1),
            "CustomName": text(mid, key, fallback), "CustomNameVisible": B(1),
            "VillagerData": {"profession": f"minecraft:{profession}", "level": 2, "type": f"minecraft:{kind}"},
            "Xp": 10, "Rotation": [F(rot), F(0.0)], "Offers": {"Recipes": offers}}


def place_chest(t, x, y, z, facing, mid, tbl, kind="chest"):
    pieces.chest(put(t), x, y, z, facing, f"{NS}:medianas/{mid}/{tbl}", kind=kind)


def ladder_closet(t, x, y, z, wood, post, sides):
    """Shut the foot of a ladder at (x, y, z) behind a fence gate, so that a villager cannot walk into it: villagers climb
    a ladder by just walking into it, their path search never uses ladders, and from an upper floor they have no way
    down (mediums/_paths.stranded). Villagers do not open fence gates; players do. `sides` maps each open side of the
    foot, (dx, dz), to "gate" (one, closed) or "post" (a log two blocks high: a block of one a villager steps onto and
    walks into the ladder from)."""
    for (dx, dz), what in sides.items():
        if what == "gate":
            facing = {(0, -1): "north", (0, 1): "south", (1, 0): "east", (-1, 0): "west"}[(dx, dz)]
            t.set(x + dx, y, z + dz, f"{wood}_fence_gate[facing={facing},in_wall=false,open=false,powered=false]")
        else:
            t.fill(x + dx, y, z + dz, x + dx, y + 1, z + dz, f"{post}[axis=y]")
