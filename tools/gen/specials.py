"""Special buildings: church/temple, cemetery, town hall, market, smithy, tavern,
inn, library, farm, mill, port."""
import math
from core import Template, nsid, villager, animal
from themes import roofset
from build import *
from houses import bed_slot, room_pool, Room, LOOT
from streets import golem_slot, P

L = lambda k: f"heraldia:cofres/{k}"


def entrance(t, th, x):
    t.jigsaw(x, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty",
             final_state=stairs(th["trim"], "south"))


def staff(t, th, x, y, z, depth, final=None):
    """Villager with a profession standing at their workstation (no bed): the jigsaw goes in the floor block."""
    t.jigsaw(x, y, z, "up_south", "heraldia:slot", "heraldia:bottom", nsid(f"villagers/{th['vtype']}/nobed_{depth}"),
             final_state=final or th["floor"], joint="aligned")
    t.set(x, y + 1, z, "air"); t.set(x, y + 2, z, "air")


def pallet(t, th, x, y, z):
    """Where a bed went in a workplace: a rug on the floor. A bed there would be claimed by the worker himself (the closest
    free bed), who would then never leave the building; this way he sleeps in a house of the village."""
    t.set(x, y + 1, z, f"{th['carpet'][0]}_carpet")


def shell(t, th, x0, z0, x1, z1, fy, H, roof=None, style=None, along=None, gable_fill=None, ceiling=True):
    """Box with walls, floor, interior air and roof. Returns the top height of the roof."""
    t.fill(x0, fy, z0, x1, fy, z1, log(th["found"], "y"))
    t.fill(x0 + 1, fy, z0 + 1, x1 - 1, fy, z1 - 1, th["floor"])
    rect_walls(t, th, x0, z0, x1, z1, fy, H, style=style)
    t.air(x0 + 1, fy + 1, z0 + 1, x1 - 1, fy + H, z1 - 1)
    kind = roof or th["roof_type"]
    if kind == "cone":
        kind = "hip"
    if kind == "none":
        return fy + H
    if kind not in ("flat",) and ceiling:
        t.fill(x0 + 1, fy + H + 1, z0 + 1, x1 - 1, fy + H + 1, z1 - 1, th["planks"])
    if kind in ("gable", "steep"):
        top = gable_roof(t, th, x0, z0, x1, z1, fy + H + 1, along=along or ("x" if x1 - x0 >= z1 - z0 else "z"),
                         steep=(kind == "steep"), gable_fill=gable_fill)
    else:
        top = roof_for(t, th, x0, z0, x1, z1, fy + H + 1, kind=kind)
    t.fill(x0 + 1, fy + H + 1, z0 + 1, x1 - 1, top, z1 - 1, "air", keep=True)
    return top


def all_windows(t, th, x0, z0, x1, z1, y, rng, skip=(), tall=False, pane=None, spacing=3):
    for side in ("north", "south", "west", "east"):
        windows_on_wall(t, th, x0, z0, x1, z1, side, y, rng, skip=skip, tall=tall, pane=pane, spacing=spacing)


def chandelier(t, th, x, y, z):
    t.set(x, y, z, "iron_chain[axis=y]")
    t.set(x, y - 1, z, lantern(th, True))


def stone_of(th):
    f = th["found"]
    return f if ("log" not in f and "bamboo" not in f) else "stone_bricks"


# ======================================================================= IGLESIA / TEMPLO
def bell_tower(t, th, nth, stone, tx0, tz0, tw, th_h):
    """Bell tower of tw x tw from y=0: walls, floor slab, openings, bell on a beam, ladder and finial."""
    cx = tx0 + tw // 2
    twall = (nth["wall"] if th["church"] == "domed" else nth["wall2"]) if stone else th["log"]
    for y in range(0, th_h + 1):
        for x in range(tx0, tx0 + tw):
            for z in range(tz0, tz0 + tw):
                edge = x in (tx0, tx0 + tw - 1) or z in (tz0, tz0 + tw - 1)
                if y == 0:
                    t.set(x, y, z, stone_of(th))
                elif edge:
                    t.set(x, y, z, twall if stone else log(twall, "y"))
                else:
                    t.set(x, y, z, "air")
    return twall


def bell_tower_top(t, th, tx0, tz0, tw, th_h, ladder_y0=1):
    cx = tx0 + tw // 2
    by = th_h - 2
    t.fill(tx0 + 1, by - 2, tz0 + 1, tx0 + 3, by - 2, tz0 + 3, th["planks"])
    for (x, z) in ((cx, tz0), (cx, tz0 + tw - 1), (tx0, tz0 + 2), (tx0 + tw - 1, tz0 + 2)):
        t.set(x, by, z, "air"); t.set(x, by - 1, z, "air")
    for x in range(tx0 + 1, tx0 + 4):
        t.set(x, by + 1, tz0 + 2, log(th["log"], "x"))
    t.set(cx, by, tz0 + 2, "bell[attachment=ceiling,facing=north]")
    for y in range(ladder_y0, by - 1):
        t.set(tx0 + 1, y, tz0 + 3, "ladder[facing=north]")
    # remate
    cap = th["tower_cap"]
    ty = th_h + 1
    if cap == "spire":
        t.fill(tx0, ty - 1, tz0, tx0 + tw - 1, ty - 1, tz0 + tw - 1, th["roof_full"])
        sy = spire(t, cx, tz0 + 2, ty, 2, th["roof_stairs"], th["roof_full"])
        t.set(cx, sy, tz0 + 2, "lightning_rod[facing=up]")
    elif cap == "pyramid":
        hip_roof(t, th, tx0, tz0, tx0 + tw - 1, tz0 + tw - 1, ty - 1, overhang=1)
    elif cap == "dome":
        dm = roofset(th["dome"] or "copper")[2]
        t.fill(tx0, ty - 1, tz0, tx0 + tw - 1, ty - 1, tz0 + tw - 1, th["roof_full"])
        dome(t, cx, ty, tz0 + 2, 2, dm, finial="lightning_rod[facing=up]")
    elif cap == "onion":
        dm = roofset(th["dome"] or "copper")[2]
        t.fill(tx0, ty - 1, tz0, tx0 + tw - 1, ty - 1, tz0 + tw - 1, th["roof_full"])
        onion(t, cx, ty, tz0 + 2, 2, dm)
    elif cap == "pagoda":
        hip_roof(t, th, tx0, tz0, tx0 + tw - 1, tz0 + tw - 1, ty - 1, overhang=1, upturn=True)
    else:
        cone_roof(t, th, cx, tz0 + 2, 2, ty)


def bell_gable(t, th, nth, cx, z, y, stone):
    """Bell gable: facade wall that projects above the gable, with an opening and the bell hung from its lintel."""
    m = nth["wall2"] if stone else th["wall2"]
    for x in range(cx - 1, cx + 2):
        for yy in range(y, y + 5):
            t.set(x, yy, z, m)
    t.set(cx, y + 1, z, "air")
    t.set(cx, y + 2, z, "bell[attachment=ceiling,facing=north]")
    for x, f in ((cx - 1, "east"), (cx + 1, "west")):
        t.set(x, y + 5, z, stairs(th["trim"], f))
    t.set(cx, y + 5, z, slab(th["roof_slab"]))


# How a chapel carries its bell, by the land it stands in. The twelve styles that share the chapel had one silhouette, a
# tower in front of a nave; three of them now, and no ladder in any (a villager climbs a ladder by walking into it and
# cannot plan the way down).
BELL_CARRIER = {"bosque": "bellcote", "taiga": "bellcote", "costa": "bellcote", "pantano": "bellcote",
                "sabana": "frame", "jungla": "frame", "oscuro": "stub", "badlands": "stub"}


def chapel_porch(t, th, nth, cx, z0, z1, stone):
    """An open porch in front of a door: posts, a gable over them, the ground paved."""
    for z in range(z0, z1 + 1):
        for x in range(cx - 2, cx + 3):
            t.set(x, 0, z, stone_of(th))
        for x in (cx - 2, cx + 2):
            for y in range(1, 4):
                t.set(x, y, z, log(th["log"], "y") if not stone else nth["wall2"])
    gable_roof(t, th, cx - 2, z0, cx + 2, z1, 4, along="z", overhang=0, gable_fill=nth["wall"])
    for x in range(cx - 1, cx + 2):
        for z in range(z0, z1 + 1):
            for y in range(1, 4):
                t.set(x, y, z, "air")


def bell_frame(t, th, x, z, tall=8):
    """A bell hung in the open from a timber frame as tall as the chapel's ridge: two posts three blocks apart along x,
    braced half way up, a beam, a little roof over the bell. Nothing to climb: posts and a brace, no rungs."""
    for px in (x, x + 2):
        t.set(px, 0, z, stone_of(th))
        for y in range(1, tall + 1):
            t.set(px, y, z, log(th["log"], "y"))
    t.set(x + 1, 0, z, stone_of(th))
    t.set(x + 1, tall // 2, z, log(th["log"], "x"))                        # the brace, well over a villager's head
    for px in range(x - 1, x + 4):
        for dz in (-1, 0, 1):
            t.set(px, tall + 2, z + dz, slab(th["roof_slab"]))
    for px in range(x, x + 3):
        t.set(px, tall + 1, z, log(th["log"], "x"))
    t.set(x + 1, tall, z, "bell[attachment=ceiling,facing=north]")


def stub_tower(t, th, nth, stone, tx0, tz0, tw, top):
    """A squat tower that just clears the nave's ridge: thick walls, the bell in an opening under a battlement, no way up."""
    bell_tower(t, th, nth, stone, tx0, tz0, tw, top)
    cx = tx0 + tw // 2
    t.fill(tx0 + 1, top - 2, tz0 + 1, tx0 + tw - 2, top - 2, tz0 + tw - 2, th["planks"])       # the belfry's floor
    for (x, z) in ((cx, tz0), (cx, tz0 + tw - 1), (tx0, tz0 + tw // 2), (tx0 + tw - 1, tz0 + tw // 2)):
        t.set(x, top - 1, z, "air")
    t.fill(tx0, top, tz0, tx0 + tw - 1, top, tz0 + tw - 1, stone_of(th) if stone else th["planks"])
    t.set(cx, top - 1, tz0 + tw // 2, "bell[attachment=ceiling,facing=north]")
    wall = t.get(tx0, 1, tz0)
    for x in range(tx0, tx0 + tw):
        for z in range(tz0, tz0 + tw):
            if (x in (tx0, tx0 + tw - 1) or z in (tz0, tz0 + tw - 1)) and (x + z) % 2 == 0:
                t.set(x, top + 1, z, wall)


def church(th, rng, name, v=0):
    """v: 0 front tower (the original), 1 transept with bell gable on the facade, 2 porch and tower at the head."""
    style = th["church"]
    if style == "pyramid":
        return pyramid_temple(th, rng, name, v)
    if style == "pagoda":
        return pagoda_temple(th, rng, name, v)
    t = Template(name)
    stone = style in ("romanesque", "gothic", "domed")
    carrier = BELL_CARRIER.get(th["family"]) if style == "chapel" else None
    W = 11 if style != "chapel" else 9
    D = 21 if style != "chapel" else 17
    if v == 2:
        D -= 4 if style != "chapel" else 2
    H = {"romanesque": 8, "gothic": 10, "chapel": 6, "domed": 8, "stave": 7, "onion": 7}[style]
    cx = W // 2
    tz0, tw = 2, 5                         # torre delantera
    nz0 = tz0 + 3 if v != 1 else tz0
    nz1 = nz0 + D - 1
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    nave_style = "stone_base" if stone else th["wall_style"]
    nth = dict(th)
    if stone:
        w = th["wall"]
        ok = any(k in w for k in ("stone", "brick", "terracotta", "calcite", "concrete", "mud", "tuff"))
        nth["wall"] = w if ok else "stone_bricks"
        nth["wall2"] = stone_of(th)
    roofk = "flat" if style == "domed" else ("steep" if style in ("gothic", "stave") else "gable")
    ta0 = ta1 = None
    if v == 1:                             # transept: arms of 2 on each side in front of the chancel
        ta0, ta1 = nz1 - 9, nz1 - 5
        shell(t, nth, -2, ta0, W + 1, ta1, 0, H, roof=roofk, style=nave_style, along="x", ceiling=False)
        for x in range(1, W - 1):          # the nave roof covers the crossing
            for y in range(H + 1, H + 12):
                for z in range(ta0 - 1, ta1 + 2):
                    t.clear(x, y, z)
    top = shell(t, nth, 0, nz0, W - 1, nz1, 0, H, roof=roofk, style=nave_style, along="z", ceiling=False)
    if v == 1:                             # opens the nave walls towards the arms
        for x in (0, W - 1):
            for z in range(ta0 + 1, ta1):
                for y in range(1, H + 1):
                    t.set(x, y, z, "air")
            for y in range(1, H + 1):      # crossing pillars
                t.set(x, y, ta0, nth["wall2"]); t.set(x, y, ta1, nth["wall2"])
    if style == "gothic":
        for z in range(nz0 + 2, nz1, 4):
            if ta0 is not None and ta0 - 1 <= z <= ta1 + 1:
                continue
            for x, f in ((-1, "east"), (W, "west")):
                for y in range(0, H - 1):
                    t.set(x, y, z, nth["wall2"])
                t.set(x, H - 1, z, stairs(th["trim"], f))
    # tall stained-glass windows, symmetrical, and rose window behind the altar
    gl = f"{th['church_glass']}_stained_glass_pane"
    for z in range(nz0 + 4, nz1 - 2, 3):
        if ta0 is not None and ta0 <= z <= ta1:
            continue
        for x in (0, W - 1):
            for y in range(3, 3 + (4 if style == "gothic" else 3)):
                t.set(x, y, z, gl)
    for y in range(4, H - 1):
        t.set(cx, y, nz1, gl)
    t.set(cx - 1, H - 3, nz1, gl); t.set(cx + 1, H - 3, nz1, gl)
    if v == 1:                             # stained-glass windows in the transept ends
        for x in (-2, W + 1):
            for y in range(3, H - 1):
                t.set(x, y, ta0 + 2, gl)
    if v == 0 and carrier in ("bellcote", "frame"):
        # no tower: a porch before the door, and the bell on the gable or on a frame in the open beside the porch
        chapel_porch(t, th, nth, cx, 2, nz0 - 1, stone)
        door(t, cx, 1, nz0, th["door"], "north")
        if carrier == "bellcote":
            ridge = max(y for (x, y, z) in t.blocks if x == cx and z == nz0)
            bell_gable(t, th, nth, cx, nz0, ridge + 1, stone)
        else:
            bell_frame(t, th, cx + 3, 3)
    elif v == 0 and carrier == "stub":
        tx0 = cx - 2
        stub_tower(t, th, nth, stone, tx0, tz0, tw, H + 6)
        for y in range(1, 4):
            t.set(cx, y, tz0 + tw - 1, "air")
        door(t, cx, 1, tz0, th["door"], "north")
    elif v == 0:
        # torre
        tx0 = cx - 2
        th_h = H + 11
        bell_tower(t, th, nth, stone, tx0, tz0, tw, th_h)
        # arco de paso torre -> nave (3 de alto)
        for y in range(1, 4):
            t.set(cx, y, tz0 + tw - 1, "air")
        door(t, cx, 1, tz0, th["door"], "north")
        bell_tower_top(t, th, tx0, tz0, tw, th_h)
    elif v == 1:
        door(t, cx, 1, nz0, th["door"], "north")
        for y in range(3, H - 1):
            t.set(cx, y + 1, nz0, gl)
        ridge = max(y for (x, y, z) in t.blocks if x == cx and z == nz0)
        bell_gable(t, th, nth, cx, nz0, ridge + 1, stone)
    else:
        # porch in front of the door and tower attached to the head, with a door from the chancel
        for z in range(2, nz0):
            for x in range(cx - 1, cx + 2):
                t.set(x, 0, z, stone_of(th))
            for x in (cx - 2, cx + 2):
                t.set(x, 0, z, stone_of(th))
                for y in range(1, 4):
                    t.set(x, y, z, log(th["log"], "y") if not stone else nth["wall2"])
        gable_roof(t, th, cx - 2, 2, cx + 2, nz0 - 1, 4, along="z", overhang=0, gable_fill=nth["wall"])
        for x in range(cx - 1, cx + 2):
            for z in range(2, nz0):
                for y in range(1, 4):
                    t.set(x, y, z, "air")
        door(t, cx, 1, nz0, th["door"], "north")
        tx0, th_h = cx - 2, H + 12
        if carrier == "bellcote":                     # the bell over the chancel's gable, nothing behind the head
            ridge = max(y for (x, y, z) in t.blocks if x == cx and z == nz1)
            bell_gable(t, th, nth, cx, nz1, ridge + 1, stone)
        elif carrier == "frame":                      # the bell on its frame behind the head
            bell_frame(t, th, cx - 5, 3)              # before the chapel too, on the other side of the porch
        elif carrier == "stub":
            stub_tower(t, th, nth, stone, tx0, nz1, tw, H + 6)
            t.fill(tx0 + 1, 1, nz1 + 1, tx0 + 3, 1, nz1 + 3, stone_of(th))
            door(t, cx + 1, 2, nz1, th["door"], "south")
        else:
            bell_tower(t, th, nth, stone, tx0, nz1, tw, th_h)
            t.fill(tx0 + 1, 1, nz1 + 1, tx0 + 3, 1, nz1 + 3, stone_of(th))
            door(t, cx + 1, 2, nz1, th["door"], "south")
            bell_tower_top(t, th, tx0, nz1, tw, th_h, ladder_y0=2)
    if style == "domed":
        dm = roofset(th["dome"] or "copper")[2]
        dome(t, cx, top, (ta0 + 2) if v == 1 else nz0 + D // 2, 4, dm, finial="lightning_rod[facing=up]")
    if style == "onion":
        dm = roofset(th["dome"] or "copper")[2]
        onion(t, cx, top + 1, nz1 - 4, 2, dm)
    # --- interior
    # pews on both sides of the aisle, facing the altar
    pz1 = nz1 - 6 if v != 1 else ta0 - 1
    for z in range(nz0 + 4 if v != 1 else nz0 + 2, pz1, 2):
        for x in list(range(1, cx - 1)) + list(range(cx + 2, W - 1)):
            t.set(x, 1, z, stairs(th["wstairs"], "north"))
    for z in range(nz0 + 2 if v != 1 else nz0 + 1, nz1 - 4):
        t.set(cx, 1, z, f"{th['carpet'][0]}_carpet")
    # chancel: a continuous step and platform
    plat = stone_of(th)
    az = nz1 - 4
    for x in range(1, W - 1):
        t.set(x, 1, az, stairs(th["trim"], "south"))
        for z in range(az + 1, nz1):
            t.set(x, 1, z, plat)
    t.set(cx, 2, az + 1, f"{th['carpet'][0]}_carpet")
    # altar centred with candles; the cleric behind
    t.set(cx, 2, nz1 - 2, "chiseled_stone_bricks" if stone else th["planks"])
    for dxx, f in ((-1, "west"), (1, "east")):
        t.set(cx + dxx, 2, nz1 - 2, stairs(th["trim"], f, half="top"))
        t.set(cx + dxx, 3, nz1 - 2, "candle[candles=3,lit=true]")
    staff(t, th, cx, 1, nz1 - 1, "cleric", final=plat)
    if v == 1:                             # font and chest in the transept arms
        t.set(-1, 1, ta0 + 2, "brewing_stand")
        t.chest(W, 1, ta0 + 2, "west", L("iglesia"))
    else:
        t.set(1, 2, nz1 - 1, "brewing_stand")
        t.chest(W - 2, 2, nz1 - 1, "north", L("iglesia"))
    # lamps hung from wooden tie beams (or from the flat ceiling)
    for z in range(nz0 + 5, nz1 - 4, 5):
        if ta0 is not None and ta0 - 1 <= z <= ta1 + 1:
            z = ta0 + 2
        if roofk != "flat":
            for x in range(-2, W + 2) if ta0 is not None and ta0 < z < ta1 else range(0, W):
                if t.get(x, H + 1, z) is None or t.get(x, H + 1, z) == "minecraft:air":
                    t.set(x, H + 1, z, log(th["log"], "x"))
        chandelier(t, th, cx, H, z)
    if v == 1:
        t.edge_jigsaw("east", ta0 + 2, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"), sel=8, place=8)
    else:
        t.edge_jigsaw("east", nz1 - 8, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"), sel=8, place=8)
    return t


def pyramid_temple(th, rng, name, v=0):
    """Stepped temple: full front staircase up to a sanctuary at the top.
    v: 0 three wide tiers (the original); 1 four steeper tiers, carved staircase and cresting;
    2 pylon temple (pylon_temple)."""
    if v == 2:
        return pylon_temple(th, rng, name)
    t = Template(name)
    N, z0 = (19, 2) if v == 0 else (17, 2)
    lv_n, inset = (3, 2) if v == 0 else (4, 1)
    c = N // 2
    entrance(t, th, c)
    t.fill(c - 1, 0, 1, c + 1, 0, 1, th["wall2"])
    for lv in range(lv_n):
        for y in (2 * lv, 2 * lv + 1):
            t.fill(inset * lv, y, z0 + inset * lv, N - 1 - inset * lv, y, z0 + N - 1 - inset * lv,
                   th["wall2"] if y == 2 * lv else th["wall"])
    py = 2 * lv_n                            # height of the upper platform (feet)
    # staircase 3 wide, clear above
    for k in range(py):
        for x in range(c - 1, c + 2):
            t.set(x, k, z0 + k, stairs(th["trim"], "south"))
            for y in range(k + 1, k + 4):
                t.set(x, y, z0 + k, "air")
    if v == 1:                               # stringer on the sides of the carved staircase
        for k in range(py):
            for x in (c - 2, c + 2):
                for y in range(0, k + 1):
                    if t.get(x, y, z0 + k) is None:
                        t.set(x, y, z0 + k, th["wall"])
    # braziers on the sides of the staircase
    for x in (c - 3, c + 3):
        t.set(x, py, z0 + py - 1 if v == 0 else z0 + py, "campfire[lit=true,signal_fire=false]")
    # sanctuary 7x7 (5x5 in the tall pyramid)
    r = 3 if v == 0 else 2
    sz0 = z0 + py + 1
    sx0, sx1, sz1 = c - r, c + r, sz0 + 2 * r
    for y in range(py, py + 4):
        for x in range(sx0, sx1 + 1):
            for z in range(sz0, sz1 + 1):
                edge = x in (sx0, sx1) or z in (sz0, sz1)
                corner = x in (sx0, sx1) and z in (sz0, sz1)
                t.set(x, y, z, (th["wall2"] if corner else th["wall"]) if edge else "air")
    door(t, c, py, sz0, th["door"], "north")
    if v == 0:
        t.fill(sx0 + 1, py + 4, sz0 + 1, sx1 - 1, py + 4, sz1 - 1, th["planks"])
        hip_roof(t, th, sx0, sz0, sx1, sz1, py + 4, overhang=1)
        gl = f"{th['church_glass']}_stained_glass_pane"
        for x in (sx0, sx1):
            t.set(x, py + 1, sz0 + 3, gl); t.set(x, py + 2, sz0 + 3, gl)
    else:                                    # flat roof with openwork cresting
        t.fill(sx0, py + 4, sz0, sx1, py + 4, sz1, th["wall2"])
        for x in range(sx0, sx1 + 1):
            for y in (py + 5, py + 6, py + 7):
                t.set(x, y, sz0 + 2, th["wall"] if (x - c) % 2 == 0 or y != py + 6 else "air")
            t.set(x, py + 8, sz0 + 2, slab(th["roof_slab"]))
        for x in (sx0, sx1):
            t.set(x, py + 2, sz0 + 2, f"{th['church_glass']}_stained_glass_pane")
    # interior: altar at the back, candles, cleric's station and chest
    t.set(c, py, sz1 - 1, "chiseled_sandstone" if "sandstone" in th["wall"] else "chiseled_stone_bricks")
    t.set(c, py + 1, sz1 - 1, "candle[candles=3,lit=true]")
    t.set(sx0 + 1, py, sz1 - 1, "brewing_stand")
    t.chest(sx1 - 1, py, sz1 - 1, "north", L("iglesia"))
    for z in range(sz0 + 1, sz0 + (3 if v == 0 else 2)):
        t.set(c, py, z, f"{th['carpet'][0]}_carpet")
    staff(t, th, c, py - 1, sz0 + (4 if v == 0 else 2), "cleric", final=th["wall"])
    t.set(c, py + 3, sz0 + 3 if v == 0 else sz0 + 1, lantern(th, True))
    t.edge_jigsaw("east", z0 + N - 3, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"),
                  final_state=th["wall2"], sel=8, place=8)
    return t


def pylon_temple(th, rng, name):
    """Pylon temple: two battered towers on the sides of the door, courtyard with porticoes and a hall of columns."""
    t = Template(name)
    W, c = 17, 8
    entrance(t, th, c)
    t.fill(c - 1, 0, 1, c + 1, 0, 1, th["wall2"])
    # pylons (z 2..4), battered: they lose one block on the outside every 3 of height
    for y in range(0, 10):
        k = y // 3
        for z in range(2, 5):
            for x in list(range(k, 7)) + list(range(10, W - k)):
                t.set(x, y, z, th["wall2"] if y in (0, 9) else th["wall"])
    for z in range(2, 5):                    # door between the pylons with its lintel
        for x in range(7, 10):
            t.set(x, 0, z, th["wall2"])
            for y in range(1, 5):
                t.set(x, y, z, "air")
            for y in (5, 6):
                t.set(x, y, z, th["wall"])
            t.set(x, 7, z, th["wall2"])
    for x in (5, 11):                        # banners on the pylons
        t.set(x, 6, 1, f"{th['banner']}_wall_banner[facing=north]")
    for x in (4, 12):                        # obeliscos delante
        t.set(x, 0, 1, th["wall2"])
        for y in range(1, 6):
            t.set(x, y, 1, th["wall"])
        t.set(x, 6, 1, slab(th["roof_slab"]))
    # courtyard (z 5..12) with porticoes on the sides
    for z in range(5, 13):
        for x in range(W):
            t.set(x, 0, z, th["path"] if 7 <= x <= 9 else th["wall2"])
            for y in range(1, 6):
                t.set(x, y, z, "air")
        for x in (0, W - 1):
            for y in range(1, 5):
                t.set(x, y, z, th["wall"])
        for x in (0, 1, 2, W - 3, W - 2, W - 1):
            t.set(x, 5, z, slab(th["roof_slab"], "top") if x not in (0, W - 1) else th["wall2"])
    for z in (6, 9, 12):
        for x in (2, W - 3):
            for y in range(1, 5):
                t.set(x, y, z, log(th["log"], "y") if "log" in th["log"] else th["wall2"])
    for x in (1, W - 2):
        t.set(x, 4, 8, lantern(th, True))
    # sala de columnas (z 13..21), cubierta plana
    hz0, hz1 = 13, 21
    shell(t, th, 1, hz0, W - 2, hz1, 0, 6, roof="flat", style="plain")
    door(t, c, 1, hz0, th["door"], "north")
    for x in (c - 1, c + 1):
        for y in range(1, 4):
            t.set(x, y, hz0, th["wall2"])
    for z in (15, 18):
        for x in (4, W - 5):
            for y in range(1, 7):
                t.set(x, y, z, th["wall2"])
    t.set(c, 1, hz1 - 1, "chiseled_sandstone" if "sandstone" in th["wall"] else "chiseled_stone_bricks")
    t.set(c, 2, hz1 - 1, "candle[candles=3,lit=true]")
    for x in (c - 1, c + 1):
        t.set(x, 1, hz1 - 1, stairs(th["trim"], "west" if x < c else "east", half="top"))
    t.set(2, 1, hz1 - 1, "brewing_stand")
    t.chest(W - 3, 1, hz1 - 1, "north", L("iglesia"))
    for z in range(hz0 + 1, hz1 - 2):
        t.set(c, 1, z, f"{th['carpet'][0]}_carpet")
    staff(t, th, c, 0, hz1 - 2, "cleric")
    for z in (15, 18):
        chandelier(t, th, c, 6, z)
    t.edge_jigsaw("east", 17, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"),
                  final_state=th["wall2"], sel=8, place=8)
    return t


def torii(t, th, cx, z, red):
    post = "red_concrete" if red else log(th["log"], "y")
    for x in (cx - 3, cx + 3):
        t.set(x, 0, z, th["found"])
        for y in range(1, 6):
            t.set(x, y, z, post)
    for x in range(cx - 2, cx + 3):
        t.set(x, 4, z, "red_concrete" if red else log(th["log"], "x"))
    for x in range(cx - 4, cx + 5):
        t.set(x, 6, z, f"{th['roof_slab']}[type=bottom]")


def pagoda_hall(t, th, x0, zf, x1, zb):
    """Hall with two curved roofs: low body, wide roof, tall body and finishing roof."""
    shell(t, th, x0, zf, x1, zb, 1, 6, roof="none")
    t.fill(x0 + 1, 8, zf + 1, x1 - 1, 8, zb - 1, th["planks"])
    hip_roof(t, th, x0, zf, x1, zb, 8, overhang=2, upturn=True, max_rings=3)
    for y in range(9, 13):                                    # tall body between the two roofs
        for x in range(x0 + 1, x1):
            for z in range(zf + 1, zb):
                if x in (x0 + 1, x1 - 1) or z in (zf + 1, zb - 1):
                    corner = x in (x0 + 1, x1 - 1) and z in (zf + 1, zb - 1)
                    t.set(x, y, z, log(th["log"], "y") if corner else th["wall"])
    hip_roof(t, th, x0 + 1, zf + 1, x1 - 1, zb - 1, 13, overhang=1, upturn=True)


def pagoda_tower(t, th, px0, pz0, tiers=4):
    """Pagoda of 5 x 5 with `tiers` bodies 4 tall, door to the north and a ladder up to the last."""
    pc = (px0 + 2, pz0 + 2)
    for k in range(tiers):
        y0 = k * 4
        if k:
            t.fill(px0, y0, pz0, px0 + 4, y0, pz0 + 4, th["planks"])
        for y in range(y0 + 1, y0 + 4):
            for x in range(px0, px0 + 5):
                for z in range(pz0, pz0 + 5):
                    edge = x in (px0, px0 + 4) or z in (pz0, pz0 + 4)
                    corner = x in (px0, px0 + 4) and z in (pz0, pz0 + 4)
                    if edge:
                        t.set(x, y, z, log(th["log"], "y") if corner else th["wall"])
                    else:
                        t.set(x, y, z, "air" if y < y0 + 3 else th["planks"])
        for (x, z) in ((px0, pz0 + 2), (px0 + 4, pz0 + 2), (px0 + 2, pz0 + 4)):
            t.set(x, y0 + 2, z, th["window"])
        if k < tiers - 1:
            hip_roof(t, th, px0, pz0, px0 + 4, pz0 + 4, y0 + 3, overhang=1, upturn=True, max_rings=1)
    fy_ = hip_roof(t, th, px0, pz0, px0 + 4, pz0 + 4, tiers * 4 - 1, overhang=1, upturn=True)
    t.set(pc[0], fy_ + 1, pc[1], "lightning_rod[facing=up]")
    door(t, px0 + 2, 1, pz0, th["door"], "north")
    for y in range(1, tiers * 4 - 3):
        t.set(px0 + 1, y, pz0 + 3, "ladder[facing=north]")
    t.set(pc[0], tiers * 4 - 2, pc[1], lantern(th, True))


def shrine_interior(t, th, x0, x1, zf, zb, y, cushions=True):
    """Altar at the back with candles, font, chest, aisle and cushions; the cleric in front of the altar."""
    cx = (x0 + x1) // 2
    t.set(cx, y, zb - 1, "chiseled_stone_bricks")
    t.set(cx, y + 1, zb - 1, "candle[candles=4,lit=true]")
    for x in (cx - 1, cx + 1):
        t.set(x, y, zb - 1, f"{th['wslab']}[type=top]")
        t.set(x, y + 1, zb - 1, "candle[candles=1,lit=true]")
    t.set(x0 + 1, y, zb - 1, "brewing_stand")
    t.chest(x1 - 1, y, zb - 1, "north", L("iglesia"))
    for z in range(zf + 1, zb - 2):
        t.set(cx, y, z, f"{th['carpet'][1]}_carpet")
    if cushions:
        for x in (cx - 4, cx - 2, cx + 2, cx + 4):
            if x0 < x < x1:
                for z in range(zf + 4, zb - 3, 2):
                    t.set(x, y, z, f"{th['carpet'][0]}_carpet")
    staff(t, th, cx, y - 1, zb - 2, "cleric")


def pagoda_temple(th, rng, name, v=0):
    """v: 0 hall and four-tier pagoda beside it (the original); 1 five-tier pagoda in the courtyard and hall at the
    back; 2 hall with two wings and lantern pavilion in front."""
    t = Template(name)
    red = th["id"] != "cerezos_templo"
    if v == 1:
        W, cx = 15, 7
        entrance(t, th, cx)
        t.fill(0, 0, 1, W - 1, 0, 21, th["found"])
        torii(t, th, cx, 1, red)
        for z in range(2, 22):                   # low enclosure wall
            for x in (0, W - 1):
                t.set(x, 1, z, th["wall"] if z % 4 else log(th["log"], "y"))
        for x in range(W):
            t.set(x, 1, 21, th["wall"] if x % 4 else log(th["log"], "y"))
        for z in range(2, 13):
            t.set(cx, 0, z, th["path"])
        pagoda_tower(t, th, cx - 2, 5, tiers=5)
        for x in range(cx - 4, cx + 5):         # the road goes around the pagoda
            t.set(x, 0, 10 if abs(x - cx) > 2 else 11, th["path"])
        for x in (cx - 3, cx + 3):
            for z in range(5, 11):
                t.set(x, 0, z, th["path"])
        zf, zb = 13, 20
        shell(t, th, 2, zf, W - 3, zb, 1, 5, roof="none")
        t.fill(3, 7, zf + 1, W - 4, 7, zb - 1, th["planks"])
        hip_roof(t, th, 2, zf, W - 3, zb, 7, overhang=2, upturn=True)
        for x in range(cx - 1, cx + 2):
            t.set(x, 1, zf - 1, stairs(th["trim"], "south"))
        door(t, cx, 2, zf, th["door"], "north")
        for x in (4, W - 5):
            t.set(x, 3, zf, th["window"]); t.set(x, 4, zf, th["window"])
        shrine_interior(t, th, 2, W - 3, zf, zb, 2, cushions=False)
        chandelier(t, th, cx, 6, zf + 2)
        for x in (2, W - 3):                     # stone lanterns next to the hall
            t.set(x, 1, zf - 2, stone_of(th)); t.set(x, 2, zf - 2, lantern(th, False))
        t.edge_jigsaw("east", 17, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"),
                      final_state=th["found"], sel=8, place=8)
        return t
    if v == 2:
        W, cx, zf, zb = 19, 9, 6, 18
        entrance(t, th, cx)
        t.fill(0, 0, 1, W - 1, 0, zb + 1, th["found"])
        for z in range(1, zf):
            t.set(cx, 0, z, th["path"])
        # open pavilion: four posts, a large hanging lantern and a curved roof
        bx = 2
        for (x, z) in ((bx - 1, 1), (bx + 1, 1), (bx - 1, 3), (bx + 1, 3)):
            for y in range(1, 5):
                t.set(x, y, z, log(th["log"], "y"))
        t.fill(bx - 1, 5, 1, bx + 1, 5, 3, th["planks"])
        chandelier(t, th, bx, 4, 2)
        t.set(bx, 1, 2, stone_of(th))
        hip_roof(t, th, bx - 1, 1, bx + 1, 3, 6, overhang=1, upturn=True)
        # low wings on the sides of the hall, open to it
        for (x0, x1) in ((0, 5), (W - 6, W - 1)):
            shell(t, th, x0, zf + 3, x1, zb - 2, 1, 4, roof="none")
            t.fill(x0 + 1, 6, zf + 4, x1 - 1, 6, zb - 3, th["planks"])
            hip_roof(t, th, x0, zf + 3, x1, zb - 2, 6, overhang=1, upturn=True, max_rings=2)
            t.fill(x0 + 1, 7, zf + 4, x1 - 1, 7, zb - 3, th["roof_full"])
            windows_on_wall(t, th, x0, zf + 3, x1, zb - 2, "north", 3, rng)
        pagoda_hall(t, th, 5, zf, W - 6, zb)
        for x in (5, W - 6):                     # steps from the hall to the wings
            for z in range(zf + 5, zb - 3):
                for y in (2, 3, 4):
                    t.set(x, y, z, "air")
        for x in range(cx - 1, cx + 2):
            t.set(x, 1, zf - 1, stairs(th["trim"], "south"))
        door(t, cx, 2, zf, th["door"], "north")
        shrine_interior(t, th, 5, W - 6, zf, zb, 2, cushions=False)
        for (x0, x1) in ((0, 5), (W - 6, W - 1)):
            for z in range(zf + 5, zb - 3, 2):
                t.set((x0 + x1) // 2, 2, z, f"{th['carpet'][0]}_carpet")
        chandelier(t, th, cx, 7, zf + 4)
        t.edge_jigsaw("east", zb - 4, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"),
                      final_state=th["found"], sel=8, place=8)
        return t
    W, D, zf = 13, 15, 3
    cx = W // 2
    zb = zf + D - 1
    entrance(t, th, cx)
    # plataforma de piedra
    t.fill(-1, 0, zf - 1, W, 0, zb + 1, th["found"])
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, th["found"])
    # torii over the entrance road
    torii(t, th, cx, 1, red)
    # sala principal
    pagoda_hall(t, th, 0, zf, W - 1, zb)
    for x in range(cx - 1, cx + 2):
        t.set(x, 1, zf - 1, stairs(th["trim"], "south"))
    door(t, cx, 2, zf, th["door"], "north")
    gl = f"{th['church_glass']}_stained_glass_pane"
    for z in range(zf + 3, zb - 1, 3):
        for x in (0, W - 1):
            t.set(x, 3, z, gl); t.set(x, 4, z, gl)
    for x in (cx - 3, cx + 3):
        t.set(x, 3, zf, gl); t.set(x, 4, zf, gl)
    # interior: altar at the back, aisle, cushions in rows
    shrine_interior(t, th, 0, W - 1, zf, zb, 2)
    for z in (zf + 4, zb - 5):
        chandelier(t, th, cx, 7, z)
    # four-tier pagoda, accessible from inside
    px0, pz0 = W + 2, zf + 4
    t.fill(W + 1, 0, pz0 - 1, px0 + 5, 0, pz0 + 5, th["found"])
    pagoda_tower(t, th, px0, pz0)
    t.fill(cx - 1, 0, zb + 2, cx + 1, 0, zb + 2, th["found"])
    t.edge_jigsaw("south", cx, 0, "heraldia:side", "heraldia:entrance", P(th, "cemetery"),
                  final_state=th["found"], sel=8, place=8)
    return t


# ======================================================================= CEMENTERIO
WALLS = {"cobblestone": "cobblestone_wall", "stone_bricks": "stone_brick_wall", "mossy_stone_bricks": "mossy_stone_brick_wall",
         "cobbled_deepslate": "cobbled_deepslate_wall", "sandstone": "sandstone_wall", "red_sandstone": "red_sandstone_wall",
         "mud_bricks": "mud_brick_wall", "tuff": "tuff_wall", "terracotta": "mud_brick_wall", "red_terracotta": "mud_brick_wall",
         "cut_sandstone": "sandstone_wall", "mossy_cobblestone": "mossy_cobblestone_wall"}


def cemetery(th, rng, name, v=0):
    """v: 0 graves on the sides of the path and mausoleum at the back (the original); 1 hedge, crossing paths with a stone cross
    in the middle, cypresses and a crypt in a corner; 2 rows of graves and a chapel of souls across the width of the back."""
    t = Template(name)
    N, z0 = 15, 1
    c = N // 2
    entrance(t, th, c)
    wallb = WALLS.get(th["found"], "cobblestone_wall")
    pillar_block = stone_of(th)
    hedge = v == 1 and th["family"] not in ("desierto", "badlands")     # seto (muro bajo en tierras secas)
    for x in range(N):
        for z in range(z0, z0 + N):
            edge = x in (0, N - 1) or z in (z0, z0 + N - 1)
            t.set(x, 0, z, "coarse_dirt" if rng.random() < 0.75 else "podzol")
            if edge:
                t.set(x, 0, z, pillar_block)
                t.set(x, 1, z, leaves(th) if hedge else wallb)
                if hedge:
                    t.set(x, 2, z, leaves(th))
            else:
                for y in (1, 2, 3):
                    t.set(x, y, z, "air")
    # gate with two pillars and lanterns
    t.set(c, 0, z0, th["path"])
    t.set(c, 1, z0, f"{th['gate']}[facing=north,open=false]")
    if hedge:
        t.set(c, 2, z0, "air")
    for x in (c - 1, c + 1):
        t.set(x, 1, z0, pillar_block); t.set(x, 2, z0, pillar_block); t.set(x, 3, z0, lantern(th, False))
    heads = ["stone_brick_wall", "cobblestone_wall", "mossy_stone_brick_wall", "mossy_cobblestone_wall"]
    flowers = ["poppy", "dandelion", "azure_bluet", "oxeye_daisy", "lily_of_the_valley"]

    def grave(x, z):
        """Grave two long towards +z with the headstone at the back."""
        t.set(x, 0, z, "podzol"); t.set(x, 0, z + 1, "podzol"); t.set(x, 0, z + 2, pillar_block)
        t.set(x, 1, z + 2, rng.choice(heads))
        if rng.random() < 0.4:
            t.set(x, 1, z + 1, rng.choice(flowers))

    if v == 0:
        mz0 = z0 + N - 6
        for z in range(z0 + 1, mz0):
            t.set(c, 0, z, th["path"])
        # graves in two symmetrical rows on each side of the path
        for x in (2, 4, N - 5, N - 3):
            for z in (z0 + 2, z0 + 5):
                grave(x, z)
        # mausoleum with the chest inside
        mx0 = c - 2
        t.fill(mx0, 0, mz0, mx0 + 4, 0, mz0 + 4, "stone_bricks")
        for y in range(1, 4):
            for x in range(mx0, mx0 + 5):
                for z in range(mz0, mz0 + 5):
                    edge = x in (mx0, mx0 + 4) or z in (mz0, mz0 + 4)
                    t.set(x, y, z, th["wall2"] if edge else "air")
        t.fill(mx0, 4, mz0, mx0 + 4, 4, mz0 + 4, th["wall2"])
        hip_roof(t, th, mx0, mz0, mx0 + 4, mz0 + 4, 5, overhang=0)
        t.set(c, 1, mz0, "air"); t.set(c, 2, mz0, "air")
        t.chest(c, 1, mz0 + 3, "north", L("cripta"))
        for x in (c - 1, c + 1):
            t.set(x, 1, mz0 + 3, "candle[candles=2,lit=true]")
        t.set(c, 3, mz0 + 2, lantern(th, True))
    elif v == 1:
        cz = z0 + c
        for z in range(z0 + 1, z0 + N - 1):
            t.set(c, 0, z, th["path"])
        for x in range(1, N - 1):
            t.set(x, 0, cz, th["path"])
        # stone cross at the crossing, on a platform
        t.set(c, 0, cz, pillar_block)
        for y in (1, 2, 3, 4):
            t.set(c, y, cz, wallb)
        t.set(c, 5, cz, pillar_block)
        for x, f in ((c - 1, "west"), (c + 1, "east")):
            t.set(x, 4, cz, stairs(th["trim"], f, half="top"))
        # one grave per quadrant on each side of the paths, with a cypress in the inner corner
        for (x, z) in ((2, z0 + 2), (4, z0 + 2), (N - 5, z0 + 2), (N - 3, z0 + 2),
                       (2, cz + 2), (N - 3, cz + 2)):
            grave(x, z)
        for (x, z) in ((c - 2, cz - 2), (c + 2, cz - 2), (c - 2, cz + 2), (c + 2, cz + 2)):
            t.set(x, 0, z, "podzol")
            t.set(x, 1, z, log(th["log"], "y"))
            for y in (2, 3, 4):
                t.set(x, y, z, leaves(th, "spruce_leaves"))
            t.set(x, 5, z, leaves(th, "spruce_leaves"))
        # crypt in the back corner, with steps and a door towards the path
        kx0, kz0 = N - 6, z0 + N - 6
        t.fill(kx0, 0, kz0, kx0 + 4, 0, kz0 + 4, "stone_bricks")
        for y in range(1, 4):
            for x in range(kx0, kx0 + 5):
                for z in range(kz0, kz0 + 5):
                    edge = x in (kx0, kx0 + 4) or z in (kz0, kz0 + 4)
                    t.set(x, y, z, th["wall2"] if edge else "air")
        gable_roof(t, th, kx0, kz0, kx0 + 4, kz0 + 4, 4, along="x", overhang=0, gable_fill=th["wall2"])
        t.set(kx0, 1, kz0 + 2, "air"); t.set(kx0, 2, kz0 + 2, "air")
        for x in range(c + 1, kx0):
            t.set(x, 0, kz0 + 2, th["path"])
        t.chest(kx0 + 3, 1, kz0 + 2, "west", L("cripta"))
        for z in (kz0 + 1, kz0 + 3):
            t.set(kx0 + 3, 1, z, "candle[candles=2,lit=true]")
        t.set(kx0 + 2, 3, kz0 + 2, lantern(th, True))
        # bench next to the crypt
        t.set(2, 1, z0 + N - 3, stairs(th["wstairs"], "west"))
        t.set(2, 1, z0 + N - 4, stairs(th["wstairs"], "west"))
    else:
        for z in range(z0 + 1, z0 + N - 5):
            t.set(c, 0, z, th["path"])
        # three rows of graves across the width
        for z in (z0 + 2, z0 + 5):
            for x in (1, 2, 3, 5, N - 6, N - 4, N - 3, N - 2):
                if x != c and (x, z) not in ((1, z0 + 5), (N - 2, z0 + 5)):
                    grave(x, z)
        # chapel of souls across the width of the back, with a gabled roof and the chest in the ossuary
        kx0, kx1, kz0, kz1 = 2, N - 3, z0 + N - 6, z0 + N - 2
        t.fill(kx0, 0, kz0, kx1, 0, kz1, "stone_bricks")
        for y in range(1, 4):
            for x in range(kx0, kx1 + 1):
                for z in range(kz0, kz1 + 1):
                    edge = x in (kx0, kx1) or z in (kz0, kz1)
                    t.set(x, y, z, th["wall2"] if edge else "air")
        t.fill(kx0 + 1, 4, kz0 + 1, kx1 - 1, 4, kz1 - 1, th["planks"])
        gable_roof(t, th, kx0, kz0, kx1, kz1, 4, along="x", overhang=1, gable_fill=th["wall2"])
        door(t, c, 1, kz0, th["door"], "north")
        for x in (c - 3, c + 3):
            t.set(x, 2, kz0, f"{th['church_glass']}_stained_glass_pane")
        t.chest(c, 1, kz1 - 1, "north", L("cripta"))
        for x in (c - 1, c + 1):
            t.set(x, 1, kz1 - 1, "candle[candles=3,lit=true]")
        for x in (kx0 + 1, kx1 - 1):
            t.set(x, 1, kz1 - 1, "skeleton_skull[rotation=8]")
        t.set(c, 3, kz0 + 2, lantern(th, True))
        # yew next to the door
        for x in (c - 2, c + 2):
            t.set(x, 0, kz0 - 1, th["path"])
    return t


# ======================================================================= AYUNTAMIENTO
def townhall(th, rng, name, v=0):
    """v: 0 porch with balcony and hipped roof (the original); 1 arcades under the upper floor and gabled
    roof; 2 lookout tower on the roof, with a ladder from the office."""
    t = Template(name)
    W, D, zf = 15, 11, 3
    cx = W // 2
    zb = zf + D - 1
    entrance(t, th, cx)
    t.fill(cx - 2, 0, 1, cx + 2, 0, zf - 1, stone_of(th))
    rk = th["roof_type"] if th["roof_type"] in ("flat", "pagoda") else "hip"
    if v == 1 and rk == "hip":
        rk = "steep" if th["roof_type"] == "steep" else "gable"
    shell(t, th, 0, zf, W - 1, zb, 0, 8, roof=rk, along="x")
    zi = zf if v != 1 else zf + 3            # ground floor facade (set back behind the arcades)
    door(t, cx, 1, zi, th["door"], "north")
    skip = [(cx, zf)]
    all_windows(t, th, 0, zf, W - 1, zb, 2, rng, skip=skip, tall=True, spacing=2)
    all_windows(t, th, 0, zf, W - 1, zb, 6, rng, skip=skip if v == 0 else (), spacing=2)
    if v == 1:
        # arcades: the upper floor overhangs on columns; ground-floor wall three blocks further back
        for x in range(0, W):
            for z in range(zf, zi):
                for y in range(1, 4):
                    t.set(x, y, z, "air")
                t.set(x, 0, z, stone_of(th))
            if x in (0, 3, 5, 9, 11, W - 1):
                for y in range(1, 4):
                    t.set(x, y, zf, log(th["log"], "y") if th["wall_style"] in ("frame", "logcabin") else stone_of(th))
            t.set(x, 4, zf, log(th["stripped"], "x"))
        for x in range(1, W - 1):
            for y in range(1, 4):
                t.set(x, y, zi, th["wall"] if not th["wall"].endswith("_log") else th["planks"])
        door(t, cx, 1, zi, th["door"], "north")
        for x in (3, 4, W - 5, W - 4):
            t.set(x, 2, zi, th["window"])
        for x in (cx - 2, cx + 2):
            t.set(x, 3, zi - 1, lantern(th, True))
        for x in (cx - 4, cx + 4):
            t.set(x, 7, zf - 1, f"{th['banner']}_wall_banner[facing=north]")
        golem_slot(t, cx - 3, 0, zf + 1, stone_of(th))
    if v == 0:
        # porch with a usable balcony on top
        for x in (cx - 2, cx + 2):
            for y in range(1, 4):
                t.set(x, y, 1, log(th["log"], "y"))
        t.fill(cx - 2, 4, 1, cx + 2, 4, zf - 1, f"{th['wslab']}[type=top]")
        for x in range(cx - 2, cx + 3):
            t.set(x, 5, 1, th["fence"])
        for x in (cx - 2, cx + 2):
            t.set(x, 5, 2, th["fence"])
        door(t, cx, 5, zf, th["door"], "north")
        for x in (cx - 4, cx + 4):
            t.set(x, 7, zf - 1, f"{th['banner']}_wall_banner[facing=north]")
    if v != 1:
        golem_slot(t, cx - 1, 0, 1, stone_of(th))
    if v == 2:
        for x in (cx - 2, cx + 2):
            t.set(x, 3, zf - 1, f"{th['banner']}_wall_banner[facing=north]")
    # floor slab and ladder in the back corner
    t.fill(1, 4, zi + 1, W - 2, 4, zb - 1, th["planks"])
    if v == 1:
        t.fill(1, 4, zf, W - 2, 4, zi, th["planks"])
    for y in range(1, 5):
        t.set(1, y, zb - 1, "ladder[facing=north]")
    # planta baja: sala de plenos
    tz = zf + 5 if v != 1 else zf + 7
    for x in range(4, W - 4):
        table(t, th, x, 1, tz)
        if x % 2 == 0:
            chair(t, th, x, 1, tz - 1, "north")
            chair(t, th, x, 1, tz + 1, "south")
    for x in range(3, W - 2):
        t.set(x, 1, zb - 1, "bookshelf"); t.set(x, 2, zb - 1, "bookshelf")
    t.set(W - 2, 1, zi + 1, "cartography_table")
    staff(t, th, W - 3, 0, zi + 2, "cartographer")
    for x in range(cx - 1, cx + 2):
        t.set(x, 1, zi + 1, f"{th['carpet'][0]}_carpet")
    t.set(cx, 3, tz, lantern(th, True))
    # planta alta: despacho
    table(t, th, cx, 5, zb - 3)
    chair(t, th, cx, 5, zb - 2, "south")
    t.chest(W - 2, 5, zb - 1, "north", L("ayuntamiento"))
    for x in (4, 5, W - 6, W - 5):
        t.set(x, 5, zb - 1, "bookshelf"); t.set(x, 6, zb - 1, "bookshelf")
    for x in range(cx - 1, cx + 2):
        for z in range(zf + 2, zf + 5):
            t.set(x, 5, z, f"{th['carpet'][0]}_carpet")
    for x in (cx - 1, cx + 1):
        t.set(x, 5, zf + 1, potted(rng.choice(th["plants"])))
    t.set(cx, 8, zf + 4, lantern(th, True))
    if v == 2:
        # lookout tower of 5 x 5 on the back wall: it rises from the roof, with oculi and finial
        tx0, tz0, ty0, ty1 = cx - 2, zb - 4, 9, 16
        for y in range(ty0, ty1 + 1):
            for x in range(tx0, tx0 + 5):
                for z in range(tz0, tz0 + 5):
                    edge = x in (tx0, tx0 + 4) or z in (tz0, tz0 + 4)
                    corner = x in (tx0, tx0 + 4) and z in (tz0, tz0 + 4)
                    if y == ty0 and not edge:
                        t.set(x, y, z, th["planks"])
                    elif edge:
                        t.set(x, y, z, (log(th["log"], "y") if th["wall_style"] in ("frame", "logcabin")
                                        else th["wall2"]) if corner else th["wall"])
                    else:
                        t.set(x, y, z, "air")
        for (x, z) in ((cx, tz0), (cx, tz0 + 4), (tx0, tz0 + 2), (tx0 + 4, tz0 + 2)):
            t.set(x, 12, z, th["window"]); t.set(x, 13, z, th["window"])
        for x in (cx - 1, cx + 1):           # framed oculus on the front face
            t.set(x, 15, tz0, stairs(th["trim"], "south", half="top"))
        t.set(cx, 15, tz0, th["window"])
        if rk == "flat":
            flat_roof(t, th, tx0, tz0, tx0 + 4, tz0 + 4, ty1 + 1)
        else:
            t.fill(tx0 + 1, ty1 + 1, tz0 + 1, tx0 + 3, ty1 + 1, tz0 + 3, th["planks"])
            hip_roof(t, th, tx0, tz0, tx0 + 4, tz0 + 4, ty1 + 1, overhang=1, upturn=(rk == "pagoda"))
        for y in range(5, ty0 + 1):
            t.set(cx, y, zb - 1, "ladder[facing=north]")
        t.set(cx, ty1, tz0 + 2, lantern(th, True))
        t.set(tx0 + 1, ty0 + 1, tz0 + 1, "barrel[facing=up]")
    return t


# ======================================================================= MERCADO
MARKET_WARES = [("fletching_table", None), ("stonecutter[facing=east]", "melon"), ("loom[facing=east]", "hay_block[axis=y]"),
                ("smoker[facing=west]", "barrel[facing=up]"), ("composter[level=5]", "pumpkin"),
                ("barrel[facing=up]", "dried_kelp_block")]


def stall(t, th, xb, xf, z0, i, awning=True, along="x"):
    """Stall 4 long: posts, striped wool awning, counter at the front (xf) and at the back (xb) its profession
    tool and its goods (or the barrel with the market loot). along="z": the same stall rotated (back at z=xb)."""
    wools = [th["carpet"][0], th["carpet"][1]]
    put = (lambda a, y, b, st: t.set(a, y, b, st)) if along == "x" else (lambda a, y, b, st: t.set(b, y, a, st))
    xa, xz = min(xb, xf), max(xb, xf)
    for (px, pz) in ((xa, z0), (xz, z0), (xa, z0 + 3), (xz, z0 + 3)):
        for y in (1, 2):
            put(px, y, pz, th["fence"])
    if awning:
        for x in range(xa, xz + 1):
            for z in range(z0, z0 + 4):
                put(x, 3, z, f"{wools[i % 2]}_wool" if (z - z0) % 2 == 0 else "white_wool")
    for z in (z0 + 1, z0 + 2):
        put(xf, 1, z, f"{th['wslab']}[type=top]")
    job, good = MARKET_WARES[i]
    if along == "z":
        job = job.replace("facing=east", "facing=south").replace("facing=west", "facing=north")
        good = good and good.replace("axis=y", "axis=y")
    put(xb, 1, z0 + 1, job)
    if good is None:
        if along == "x":
            t.barrel(xb, 1, z0 + 2, loot=L("mercado"))
        else:
            t.barrel(z0 + 2, 1, xb, loot=L("mercado"))
    else:
        put(xb, 1, z0 + 2, good)


def market(th, rng, name, v=0):
    """Market square. v: 0 stalls on both sides of a central aisle, with the well in the middle (the original);
    1 covered market hall: a large roof on pillars and the stalls underneath; 2 U-shaped arcaded square around a fountain."""
    t = Template(name)
    W, D = 17, 16
    cx = W // 2
    entrance(t, th, cx)
    for x in range(W):
        for z in range(1, D + 1):
            edge = x in (0, W - 1) or z in (1, D)
            t.set(x, 0, z, stone_of(th) if edge else (th["path"] if rng.random() < 0.8 else th["path2"]))
            for y in (1, 2, 3, 4):
                t.set(x, y, z, "air")
    if v == 1:
        return market_hall(t, th, rng, W, D)
    if v == 2:
        return market_square(t, th, rng, W, D)
    i = 0
    for side in ("west", "east"):
        for z0 in (2, 7, 12):
            xb, xf = (1, 4) if side == "west" else (W - 2, W - 5)      # back and counter
            stall(t, th, xb, xf, z0, i)
            i += 1
    # central well with curb and small roof on four posts
    wz = 8
    for x in range(cx - 1, cx + 2):
        for z in range(wz - 1, wz + 2):
            t.set(x, 0, z, stone_of(th))
            if (x, z) != (cx, wz):
                t.set(x, 1, z, stone_of(th))
    t.set(cx, 0, wz, "water"); t.set(cx, 1, wz, "water")
    for (x, z) in ((cx - 1, wz - 1), (cx + 1, wz - 1), (cx - 1, wz + 1), (cx + 1, wz + 1)):
        t.set(x, 2, z, th["fence"]); t.set(x, 3, z, th["fence"])
    t.fill(cx - 1, 4, wz - 1, cx + 1, 4, wz + 1, f"{th['roof_slab']}[type=bottom]")
    for (x, z) in ((0, 1), (W - 1, 1), (0, D), (W - 1, D)):
        t.set(x, 1, z, th["fence"]); t.set(x, 2, z, th["fence"]); t.set(x, 3, z, lantern(th, False))
    staff(t, th, 2, 0, 3, "fletcher", final=th["path"])
    golem_slot(t, cx, 0, 13, th["path"])
    t.min_size = (W, 6, D + 1)
    return t


def market_hall(t, th, rng, W, D):
    """Covered market hall: pillars on the perimeter, gabled roof lengthwise and stalls in two rows beneath it."""
    cx = W // 2
    post = log(th["log"], "y") if th["wall_style"] in ("frame", "logcabin") else stone_of(th)
    for x in range(W):
        for z in range(1, D + 1):
            if x in (0, W - 1) or z in (1, D):
                t.set(x, 0, z, stone_of(th))
            else:
                t.set(x, 0, z, th["path"] if abs(x - cx) <= 1 else stone_of(th))
    for x in (0, 4, cx, W - 5, W - 1):
        for z in (1, 5, 9, 12, D):
            if x in (0, W - 1) or z in (1, D):
                if x == cx and z == 1:
                    continue
                for y in range(1, 5):
                    t.set(x, y, z, post)
    for x in range(W):                       # beams on the pillars
        for z in (1, D):
            t.set(x, 5, z, log(th["log"], "x"))
    for z in range(1, D + 1):
        for x in (0, W - 1):
            t.set(x, 5, z, log(th["log"], "z"))
    rk = th["roof_type"]
    if rk in ("flat",):
        flat_roof(t, th, 0, 1, W - 1, D, 6, light=False)
    elif rk in ("hip", "pagoda", "cone"):
        hip_roof(t, th, 0, 1, W - 1, D, 6, overhang=1, upturn=(rk == "pagoda"))
    else:
        gable_roof(t, th, 0, 1, W - 1, D, 6, along="z", steep=(rk == "steep"), gable_fill=th["planks"])
    for x in range(1, W - 1):
        for z in range(2, D):
            for y in range(5, 7):
                if t.get(x, y, z) is None:
                    t.set(x, y, z, "air")
    i = 0
    for side in ("west", "east"):
        for z0 in (2, 7, 12):
            xb, xf = (1, 4) if side == "west" else (W - 2, W - 5)
            stall(t, th, xb, xf, z0 if z0 != 12 else 11, i, awning=False)
            i += 1
    for z in (4, 8, 12):
        t.set(cx, 5, z, lantern(th, True))
    t.set(cx - 2, 1, D - 1, "hay_block[axis=y]")
    t.set(cx + 2, 1, D - 1, "melon")
    staff(t, th, 2, 0, 6, "fletcher", final=stone_of(th))
    golem_slot(t, cx, 0, 13, th["path"])
    t.min_size = (W, 6, D + 1)
    return t


def market_square(t, th, rng, W, D):
    """Arcaded square: U-shaped arcades (west, back and east) with the stalls inside and a fountain in the middle."""
    cx = W // 2
    post = log(th["log"], "y") if th["wall_style"] in ("frame", "logcabin") else stone_of(th)
    back = th["wall"] if not th["wall"].endswith("_log") else th["planks"]
    for x in range(W):
        for z in range(1, D + 1):
            west, east, south = x <= 3, x >= W - 4, z >= D - 3
            if not (west or east or south):
                continue
            t.set(x, 0, z, stone_of(th))
            outer = x in (0, W - 1) or z == D
            for y in range(1, 4):
                t.set(x, y, z, back if outer else "air")
            # roof sloping towards the square
            depth = min([k for k, c in ((x, west), (W - 1 - x, east), (D - z, south)) if c])
            t.set(x, 4, z, th["roof_full"] if depth == 0 else
                  slab(th["roof_slab"], "top") if depth < 3 else slab(th["roof_slab"]))
    for (x, z) in ((3, 2), (3, 6), (3, 10), (W - 4, 2), (W - 4, 6), (W - 4, 10), (3, D - 3), (W - 4, D - 3),
                   (6, D - 3), (W - 7, D - 3)):
        for y in range(1, 4):
            t.set(x, y, z, post)
    for z in range(2, D - 3):                # windows in the back wall of the arcades
        if z % 4 == 0:
            t.set(0, 2, z, th["window"]); t.set(W - 1, 2, z, th["window"])
    i = 0
    for xb, xf in ((1, 3), (W - 2, W - 4)):
        for z0 in (2, 7):
            stall(t, th, xb, xf, z0, i, awning=False)
            i += 1
    for x0 in (1, W - 5):
        stall(t, th, D - 1, D - 3, x0, i, awning=False, along="z")
        i += 1
    # fountain: basin with water and central pillar with a lantern
    fz = 7
    for x in range(cx - 2, cx + 3):
        for z in range(fz - 2, fz + 3):
            rim = abs(x - cx) == 2 or abs(z - fz) == 2
            t.set(x, 0, z, stone_of(th) if rim or (x, z) == (cx, fz) else "water")
            if rim:
                t.set(x, 1, z, slab(th["roof_slab"]) if "slab" in th["roof_slab"] else stone_of(th))
    for y in (1, 2):
        t.set(cx, y, fz, stone_of(th))
    t.set(cx, 3, fz, lantern(th, False))
    for x in (cx - 4, cx + 4):               # trees in planters on the sides
        t.set(x, 0, fz + 4, "grass_block")
        t.set(x, 1, fz + 4, log(th["log"], "y"))
        for y in (2, 3):
            t.set(x, y, fz + 4, leaves(th))
    for (x, z) in ((4, 1), (W - 5, 1)):
        t.set(x, 1, z, th["fence"]); t.set(x, 2, z, th["fence"]); t.set(x, 3, z, lantern(th, False))
    staff(t, th, 2, 0, 11, "fletcher", final=stone_of(th))
    golem_slot(t, cx, 0, 12, th["path"])
    t.min_size = (W, 6, D + 1)
    return t


# ======================================================================= SMITHY
def blacksmith(th, rng, name, v=0):
    """v: 0 dwelling and open forge under one roof (the original); 1 forge courtyard in front and dwelling at the
    back; 2 stone workshop with the dwelling on the upper floor."""
    if v:
        return smithy_yard(th, rng, name) if v == 1 else smithy_tall(th, rng, name)
    t = Template(name)
    W, D, zf = 13, 11, 2
    zb = zf + D - 1
    cx = 3
    H = 4
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    # dwelling (left) and open forge (right) under one roof
    shell(t, th, 0, zf, 6, zb, 0, H, roof="none")
    t.fill(1, H + 1, zf + 1, 5, H + 1, zb - 1, th["planks"])
    t.fill(7, 0, zf, W - 1, 0, zb, "stone_bricks")
    for x in range(8, W - 1):
        t.set(x, 0, 1, "stone_brick_stairs[facing=south,half=bottom,shape=straight]")
    for (x, z) in ((W - 1, zf), (W - 1, zb)):
        for y in range(1, H + 1):
            t.set(x, y, z, log(th["log"], "y"))
    for x in range(7, W - 1):
        t.set(x, H, zf, log(th["stripped"], "x")); t.set(x, H, zb, log(th["stripped"], "x"))
    for z in range(zf + 1, zb):
        t.set(W - 1, H, z, log(th["stripped"], "z"))
    for x in range(7, W):
        for z in range(zf, zb + 1):
            for y in range(1, H + 1):
                if t.get(x, y, z) is None:
                    t.set(x, y, z, "air")
    rk = "hip" if th["roof_type"] == "cone" else th["roof_type"]
    if rk in ("gable", "steep"):
        top = gable_roof(t, th, 0, zf, W - 1, zb, H + 1, along="x", steep=(rk == "steep"))
    else:
        top = roof_for(t, th, 0, zf, W - 1, zb, H + 1, kind=rk)
    door(t, cx, 1, zf, th["door"], "north")
    for side in ("north", "south", "west"):
        windows_on_wall(t, th, 0, zf, 6, zb, side, 2, rng, skip=[(cx, zf)])
    # vivienda
    pallet(t, th, 1, 0, zb - 2)
    t.chest(5, 1, zb - 1, "north", L("herreria"))
    t.set(5, 1, zf + 1, "crafting_table")
    t.set(1, 1, zf + 1, f"{th['wslab']}[type=top]")
    t.set(1, 2, zf + 1, potted(rng.choice(th["plants"])))
    for x in range(2, 5):
        for z in range(zf + 4, zf + 7):
            t.set(x, 1, z, f"{th['carpet'][0]}_carpet")
    t.set(3, H, zf + 5, lantern(th, True))
    # forge: tools in a line against the dwelling wall, furnace at the back
    t.set(7, 1, zf + 2, "anvil[facing=north]")
    t.set(7, 1, zf + 3, "water_cauldron[level=3]")
    t.set(7, 1, zf + 5, "blast_furnace[facing=east]")
    t.set(7, 1, zf + 6, "smithing_table")
    t.set(W - 2, 1, zf + 2, "grindstone[face=floor,facing=west]")
    staff(t, th, 8, 0, zf + 5, "armorer", final="stone_bricks")
    for z in range(zf + 1, zb):
        t.set(W - 1, 1, z, "cobblestone_wall")
    for x in range(W - 4, W - 1):
        for z in range(zb - 2, zb + 1):
            for y in range(1, 4):
                t.set(x, y, z, "bricks")
    t.set(W - 3, 1, zb - 2, "lava_cauldron")
    t.set(W - 3, 2, zb - 2, "iron_bars")
    for y in range(4, top + 2):
        t.set(W - 3, y, zb - 1, "bricks")
    t.set(W - 3, top + 2, zb - 1, "campfire[lit=true,signal_fire=false]")
    for x in range(7, W - 4):
        t.set(x, 1, zb, "cobblestone_wall")
    t.set(9, H - 1, zf + 4, lantern(th, True))
    return t


def forge_hearth(t, th, x0, z0, y_top, mouth="north"):
    """3 x 3 brick hearth with a lava cauldron behind a grate on the `mouth` face and a chimney up to y_top."""
    for x in range(x0, x0 + 3):
        for z in range(z0, z0 + 3):
            for y in range(1, 4):
                t.set(x, y, z, "bricks")
    mx, mz = {"north": (x0 + 1, z0), "east": (x0 + 2, z0 + 1)}[mouth]
    t.set(mx, 1, mz, "lava_cauldron")
    t.set(mx, 2, mz, "iron_bars")
    for y in range(4, y_top + 2):
        t.set(x0 + 1, y, z0 + 1, "bricks")
    t.set(x0 + 1, y_top + 2, z0 + 1, "campfire[lit=true,signal_fire=false]")


def smith_house(t, th, rng, bx, by, bz, flip=False):
    """Furnishings of the smith's dwelling (pallet, chest, crafting table, carpet and flower pot) in an interior room of
    5 x 4 whose northwest corner is (bx, bz); the pallet goes against the west wall. The armourer stands at the blast
    furnace and sleeps in a house of the village (pallet): he walks the street to the smithy every morning."""
    pallet(t, th, bx, by, bz + 1)
    t.chest(bx + 4, by + 1, bz + 3, "north", L("herreria"))
    t.set(bx + 4, by + 1, bz, "crafting_table")
    t.set(bx + 2, by + 1, bz, f"{th['wslab']}[type=top]")
    t.set(bx + 2, by + 2, bz, potted(rng.choice(th["plants"])))
    for x in range(bx + 2, bx + 4):
        for z in range(bz + 2, bz + 4):
            t.set(x, by + 1, z, f"{th['carpet'][0]}_carpet")


def smithy_yard(th, rng, name):
    t = Template(name)
    W, cx = 13, 6
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    # forge courtyard (z 2..7): stone floor, low wall and small roof over the forge on the west side
    for x in range(W):
        for z in range(2, 8):
            t.set(x, 0, z, "stone_bricks")
            for y in range(1, 5):
                t.set(x, y, z, "air")
    for z in range(2, 8):
        t.set(W - 1, 1, z, "cobblestone_wall")
    for x in range(W):
        if abs(x - cx) > 1:
            t.set(x, 1, 2, "cobblestone_wall")
    for x in range(0, 5):
        for z in range(2, 8):
            t.set(x, 4, z, slab(th["roof_slab"], "top"))
    for (x, z) in ((4, 3), (4, 7)):
        for y in range(1, 4):
            t.set(x, y, z, log(th["log"], "y"))
    for z in range(3, 8):
        for y in (1, 2, 3):
            t.set(0, y, z, "cobblestone")
    forge_hearth(t, th, 0, 4, 5, mouth="east")
    t.set(3, 1, 3, "anvil[facing=north]")
    t.set(3, 1, 7, "water_cauldron[level=3]")
    t.set(W - 2, 1, 3, "blast_furnace[facing=west]")
    t.set(W - 2, 1, 5, "smithing_table")
    t.set(W - 2, 1, 7, "grindstone[face=floor,facing=west]")
    staff(t, th, W - 3, 0, 3, "armorer", final="stone_bricks")
    t.set(3, 3, 5, lantern(th, True))
    # dwelling at the back (z 8..12) with a gabled roof across the width
    H = 4
    rk = th["roof_type"] if th["roof_type"] not in ("cone", "pagoda") else "hip"
    shell(t, th, 0, 8, W - 1, 12, 0, H, roof=rk, along="x")
    door(t, cx, 1, 8, th["door"], "north")
    for side in ("south", "west", "east"):
        windows_on_wall(t, th, 0, 8, W - 1, 12, side, 2, rng)
    smith_house(t, th, rng, 1, 0, 9)
    for x in range(cx + 2, W - 1):
        t.set(x, 1, 11, "barrel[facing=up]" if x % 2 else th["planks"])
    t.set(cx, H, 10, lantern(th, True))
    return t


def smithy_tall(th, rng, name):
    t = Template(name)
    W, D, zf, cx = 11, 9, 2, 5
    zb = zf + D - 1
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    nth = dict(th)
    nth["wall"] = nth["wall2"] = stone_of(th)
    rk = th["roof_type"] if th["roof_type"] not in ("cone",) else "hip"
    top = shell(t, nth, 0, zf, W - 1, zb, 0, 4, roof="none", style="plain")
    for y in (5, 6, 7, 8):                   # upper floor with the walls of the style
        for x in range(W):
            for z in (zf, zb):
                t.set(x, y, z, th["wall"] if 0 < x < W - 1 else log(th["log"], "y") if th["wall_style"] in ("frame", "logcabin") else th["wall2"])
        for z in range(zf + 1, zb):
            for x in (0, W - 1):
                t.set(x, y, z, th["wall"])
    t.fill(1, 4, zf + 1, W - 2, 4, zb - 1, th["planks"])
    t.air(1, 5, zf + 1, W - 2, 8, zb - 1)
    t.fill(1, 9, zf + 1, W - 2, 9, zb - 1, th["planks"])
    top = roof_for(t, th, 0, zf, W - 1, zb, 9, kind=rk, along="x")
    # forge gate (3 wide) with lintel
    for x in range(cx - 1, cx + 2):
        for y in (1, 2, 3):
            t.set(x, y, zf, "air")
    for side in ("west", "east"):
        windows_on_wall(t, th, 0, zf, W - 1, zb, side, 2, rng)
    for side in ("north", "south", "west", "east"):
        windows_on_wall(t, th, 0, zf, W - 1, zb, side, 6, rng)
    # forge: hearth next to the back wall with the chimney passing through the dwelling, tools around
    forge_hearth(t, th, cx - 1, zb - 3, top)
    t.set(cx - 3, 1, zb - 1, "anvil[facing=north]")
    t.set(cx - 3, 1, zb - 3, "water_cauldron[level=3]")
    t.set(1, 1, zf + 2, "blast_furnace[facing=east]")
    t.set(1, 1, zf + 4, "smithing_table")
    t.set(W - 2, 1, zf + 2, "grindstone[face=floor,facing=west]")
    t.set(W - 2, 1, zf + 4, "barrel[facing=up]")
    staff(t, th, 2, 0, zf + 2, "armorer")
    t.set(cx, 3, zf + 2, lantern(th, True))
    # ladder to the upstairs dwelling
    for y in range(1, 5):
        t.set(W - 2, y, zb - 1, "ladder[facing=north]")
    smith_house(t, th, rng, 1, 4, zf + 1)
    t.set(cx, 8, zf + 4, lantern(th, True))
    return t


# ======================================================================= TAVERN / POSADA
def tavern(th, rng, name, inn=False, v=0):
    """Tavern (or inn with inn=True). v: 0 two-storey house with hearth and exterior chimney (the original);
    1 narrower house with a terrace under a pergola; 2 house with the upper floor jettied and gable facing the street."""
    if v:
        return tavern_variant(th, rng, name, inn, v)
    t = Template(name)
    W, D = (13, 13) if not inn else (15, 11)
    cx = W // 2
    zf = 2
    zb = zf + D - 1
    hz = zf + 4                                  # hearth on the east wall
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    top = shell(t, th, 0, zf, W - 1, zb, 0, 8)
    door(t, cx, 1, zf, th["door"], "north")
    for fl in (0, 1):
        for side in ("north", "south", "west", "east"):
            windows_on_wall(t, th, 0, zf, W - 1, zb, side, 2 + 4 * fl, rng,
                            skip=[(cx, zf), (W - 1, hz), (W - 1, hz - 1), (W - 1, hz + 1)])
    t.set(cx + 2, 4, zf - 1, f"{th['banner']}_wall_banner[facing=north]")
    t.set(cx - 2, 4, zf - 1, f"{th['banner']}_wall_banner[facing=north]")
    t.fill(1, 4, zf + 1, W - 2, 4, zb - 1, th["planks"])
    stair_flight(t, th, 2, zf + 1, "east")      # up to the rooms (a ladder would leave their beds out of reach)
    # hearth built into the wall with an exterior chimney
    for y in range(0, top + 2):
        t.set(W, y, hz, "bricks")
    for y in range(1, top + 1):
        if t.get(W - 1, y, hz) is not None:
            t.set(W - 1, y, hz, "bricks")
    t.set(W - 1, 1, hz, "campfire[lit=true,signal_fire=false]")
    t.set(W, top + 2, hz, "campfire[lit=true,signal_fire=false]")
    # bar at the back, barrels against the wall and the innkeeper behind
    bz = zb - 3
    for x in range(3, W - 3):
        t.set(x, 1, bz, stairs(th["wstairs"], "north", half="top"))
    for x in range(3, W - 3):
        t.set(x, 1, zb - 1, "smoker[facing=north]" if x == cx else "barrel[facing=north]")
    t.barrel(3, 2, zb - 1, "north", L("posada" if inn else "taberna"))
    t.barrel(W - 4, 2, zb - 1, "north")
    staff(t, th, cx, 0, zb - 2, "leatherworker" if inn else "butcher")
    if inn:
        t.set(W - 2, 1, zb - 1, "cauldron")
    # tables: two next to the walls and one central, chairs with their backs outwards
    for (x, z) in ((3, zf + 3), (W - 4, zf + 3), (cx, zf + (5 if inn else 6))):
        table(t, th, x, 1, z)
        chair(t, th, x - 1, 1, z, "west")
        chair(t, th, x + 1, 1, z, "east")
        if x != cx:
            t.set(x, 2, z, "candle[candles=2,lit=true]")
    t.set(cx, 3, zf + (5 if inn else 6), lantern(th, True))
    t.set(cx, 3, zb - 2, lantern(th, True))
    # upper floor: beds against the east wall, with bedside tables
    spots = [(W - 2, zf + 1, "farmer"), (W - 2, zf + 6, "librarian")]
    if inn:
        spots.append((1, zf + 5, "shepherd"))
    for (x, z, depth) in spots:
        bed_slot(t, th, x, 4, z, room_pool(th, depth))
        t.set(x, 5, z + 2, f"{th['wslab']}[type=top]")
        t.set(x, 6, z + 2, potted(rng.choice(th["plants"])))
    for x in range(cx - 1, cx + 2):
        for z in range(zf + 3, zf + 6):
            t.set(x, 5, z, f"{th['carpet'][1]}_carpet")
    t.set(cx, 8, zf + 4, lantern(th, True))
    return t


def tavern_variant(th, rng, name, inn, v):
    t = Template(name)
    W, D = (13, 13) if not inn else (15, 11)
    zf = 2
    zb = zf + D - 1
    if v == 1:                               # house from x 4..W-1 and terrace to the west
        x0, x1, yb = 4, W - 1, 0
        bx0, bx1 = x0, x1
    else:                                    # ground floor set in one block; the upper one overhangs it
        x0, x1, yb = 1, W - 2, 0
        bx0, bx1 = 0, W - 1
    cx = (x0 + x1) // 2
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    if v == 1:
        top = shell(t, th, x0, zf, x1, zb, 0, 8, along="z")
        t.fill(x0 + 1, 4, zf + 1, x1 - 1, 4, zb - 1, th["planks"])
        door(t, cx, 1, zf, th["door"], "north")
        door(t, x0, 1, zf + 4, th["door"], "west")
        for fl in (0, 1):
            for side in ("north", "south", "west", "east"):
                windows_on_wall(t, th, x0, zf, x1, zb, side, 2 + 4 * fl, rng, skip=[(cx, zf), (x0, zf + 4)])
        # terrace: decking, pergola with vine and two tables
        for x in range(0, x0):
            for z in range(zf, zb - 3):
                t.set(x, 0, z, th["planks"])
                for y in (1, 2, 3):
                    t.set(x, y, z, "air")
        for (x, z) in ((0, zf), (0, zb - 4), (2, zf), (2, zb - 4)):
            for y in (1, 2, 3):
                t.set(x, y, z, th["fence"])
        for x in range(0, x0):
            for z in range(zf, zb - 3):
                t.set(x, 4, z, leaves(th) if (x + z) % 3 else log(th["stripped"], "z"))
        for z in (zf + 2, zf + 6):
            if z < zb - 4:
                table(t, th, 1, 1, z)
                chair(t, th, 1, 1, z - 1, "north")
                chair(t, th, 1, 1, z + 1, "south")
        for z in range(zf, zb - 3):
            if t.get(3, 1, z) is None or t.get(3, 1, z) == "minecraft:air":
                t.set(3, 1, z, "air")
        t.set(x0 - 1, 3, zf + 4, lantern(th, True))
        flight_at = (x1 - 1, zf + 2, "south")
        hearth = (x1, zf + 7)
    else:
        nth = dict(th)
        nth["wall"] = nth["wall2"] = stone_of(th)
        t.fill(bx0, 0, zf, bx1, 0, zb, stone_of(th))
        shell(t, nth, x0, zf + 1, x1, zb - 1, 0, 3, roof="none", style="plain")
        # jettied upper floor: floor slab projecting one block on all sides, walls of the style
        t.fill(bx0, 4, zf, bx1, 4, zb, log(th["stripped"], "x"))
        t.fill(x0 + 1, 4, zf + 2, x1 - 1, 4, zb - 2, th["planks"])
        top = shell(t, th, bx0, zf, bx1, zb, 4, 4, along="z", roof="steep" if th["roof_type"] == "steep" else None)
        t.fill(x0 + 1, 4, zf + 2, x1 - 1, 4, zb - 2, th["planks"])
        for x in range(bx0, bx1 + 1):        # exposed beams under the jetty
            for z in (zf, zb):
                t.set(x, 4, z, log(th["stripped"], "x"))
        door(t, cx, 1, zf + 1, th["door"], "north")
        for side in ("north", "south", "west", "east"):
            windows_on_wall(t, th, x0, zf + 1, x1, zb - 1, side, 2, rng, skip=[(cx, zf + 1)])
            windows_on_wall(t, th, bx0, zf, bx1, zb, side, 6, rng)
        t.set(cx - 2, 3, zf, f"{th['banner']}_wall_banner[facing=north]")
        t.set(cx + 2, 3, zf, f"{th['banner']}_wall_banner[facing=north]")
        for x in (x0, x1):
            t.set(x, 3, zf, lantern(th, True))
        flight_at = (x1 - 1, zf + 3, "south")
        hearth = None
    # staircase up to the rooms (a ladder would leave their beds out of reach)
    stair_flight(t, th, *flight_at)
    if hearth:                               # hearth with chimney outside the east wall
        hx, hz = hearth
        for y in range(0, top + 2):
            t.set(hx + 1, y, hz, "bricks")
        for y in range(1, top + 1):
            if t.get(hx, y, hz) is not None:
                t.set(hx, y, hz, "bricks")
        t.set(hx, 1, hz, "campfire[lit=true,signal_fire=false]")
        t.set(hx + 1, top + 2, hz, "campfire[lit=true,signal_fire=false]")
    else:                                    # hearth in the corner with the chimney inside up to the roof
        hx, hz = x0 + 1, zb - 2
        t.set(hx, 1, hz, "campfire[lit=true,signal_fire=false]")
        for y in range(2, top + 2):
            t.set(hx, y, hz, "bricks")
        t.set(hx, top + 2, hz, "campfire[lit=true,signal_fire=false]")
    # bar at the back, barrels against the wall and the innkeeper behind
    zin1 = zb - 1 if v == 1 else zb - 2       # last interior z of the ground floor
    bz = zin1 - 2
    for x in range(x0 + 3, x1 - 2):
        t.set(x, 1, bz, stairs(th["wstairs"], "north", half="top"))
        t.set(x, 1, zin1, "smoker[facing=north]" if x == cx else "barrel[facing=north]")
    t.barrel(x0 + 3, 2, zin1, "north", L("posada" if inn else "taberna"))
    staff(t, th, cx, 0, zin1 - 1, "leatherworker" if inn else "butcher")
    if inn:
        t.set(x1 - 2, 1, zin1, "cauldron")
    zin0 = zf + 1 if v == 1 else zf + 2
    for (x, z) in ((cx, zin0 + 2),) + (((x0 + 2, zin0 + 4),) if v == 2 else ()):
        table(t, th, x, 1, z)
        chair(t, th, x - 1, 1, z, "west")
        chair(t, th, x + 1, 1, z, "east")
        t.set(x, 2, z, "candle[candles=2,lit=true]")
    t.set(cx, 3, zin0 + 4, lantern(th, True))
    # upper floor: beds against the walls, with bedside tables
    ux0, ux1 = (x0 + 1, x1 - 1) if v == 1 else (bx0 + 1, bx1 - 1)
    spots = [(ux0, zf + 1, "farmer"), (ux0, zf + 5, "librarian")]
    if inn:
        spots.append((ux1 - 1 if v == 1 else ux1, zf + 5, "shepherd"))
    for (x, z, depth) in spots:
        bed_slot(t, th, x, 4, z, room_pool(th, depth))
        t.set(x, 5, z + 2, f"{th['wslab']}[type=top]")
        t.set(x, 6, z + 2, potted(rng.choice(th["plants"])))
    for x in range(cx - 1, cx + 2):
        for z in range(zf + 3, zf + 6):
            if t.is_free(x, 5, z):
                t.set(x, 5, z, f"{th['carpet'][1]}_carpet")
    t.set(cx, 8, zf + 4, lantern(th, True))
    return t


# ======================================================================= BIBLIOTECA
def library(th, rng, name, v=0):
    """v: 0 elongated hall with a U-shaped mezzanine (the original); 1 square double-height hall with glazed lantern;
    2 cloister: two low wings in front and the hall at the back, with a garden in the middle."""
    if v:
        return library_variant(th, rng, name, v)
    t = Template(name)
    W, D, zf = 11, 15, 2
    cx = W // 2
    zb = zf + D - 1
    z0i, z1i = zf + 1, zb - 1                  # interior
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    shell(t, th, 0, zf, W - 1, zb, 0, 7, along="z")
    door(t, cx, 1, zf, th["door"], "north")
    wrows = list(range(zf + 3, zb - 1, 3))
    for z in wrows:
        for x in (0, W - 1):
            for y in range(2, 6):
                t.set(x, y, z, th["window"])
    # shelves from floor to mezzanine on the long walls, leaving the windows free
    for z in range(z0i, z1i + 1):
        if z in wrows:
            continue
        for x in (1, W - 2):
            for y in (1, 2, 3, 5, 6):
                t.set(x, y, z, "bookshelf")
    for x in range(2, W - 2):
        if x != cx:
            for y in (1, 2, 3):
                t.set(x, y, z1i, "bookshelf")
    # U-shaped mezzanine with railing
    for z in range(z0i, z1i + 1):
        for x in (1, 2, 3, W - 4, W - 3, W - 2):
            t.set(x, 4, z, f"{th['wslab']}[type=top]")
    for x in range(4, W - 4):
        for z in (z1i - 1, z1i):
            t.set(x, 4, z, f"{th['wslab']}[type=top]")
    for z in range(z0i, z1i - 1):
        t.set(3, 5, z, th["fence"]); t.set(W - 4, 5, z, th["fence"])
    for x in range(3, W - 3):
        t.set(x, 5, z1i - 1, th["fence"])
    # full staircase to the mezzanine (4 steps) on the west side
    sz0 = z0i + 1
    for k in range(4):
        z = sz0 + k
        t.set(3, 4, z, "air"); t.set(3, 5, z, "air")
        t.set(3, 1 + k, z, stairs(th["wstairs"], "south"))
        for y in range(1, 1 + k):
            t.set(3, y, z, th["planks"])
    t.set(3, 5, sz0 + 4, "air")                 # landing without railing
    # reading tables on the central axis
    for z in (zf + 7, zf + 10):
        table(t, th, cx, 1, z)
        t.set(cx, 2, z, "candle[candles=1,lit=true]")
        chair(t, th, cx - 1, 1, z, "west")
        chair(t, th, cx + 1, 1, z, "east")
    t.set(cx, 1, z1i, "lectern[facing=north]")
    t.set(W - 2, 2, z0i, "air"); t.set(W - 2, 3, z0i, "air")
    t.chest(W - 2, 1, z0i, "west", L("biblioteca"))
    staff(t, th, cx, 0, z1i - 2, "librarian")
    for z in (zf + 5, zf + 9):
        chandelier(t, th, cx, 7, z)
    t.set(cx, 1, z0i, f"{th['carpet'][0]}_carpet")
    return t


def shelves_on_walls(t, x0, z0, x1, z1, ys, skip_door=None, clear=()):
    """Bookshelves against the inside of the walls of [x0..x1]x[z0..z1] at heights ys, except in front of
    windows, doors, what is already placed and next to the `clear` cells (chests, lecterns), which stay accessible."""
    for x in range(x0 + 1, x1):
        for z in range(z0 + 1, z1):
            if not (x in (x0 + 1, x1 - 1) or z in (z0 + 1, z1 - 1)):
                continue
            wall = [(x0, z) if x == x0 + 1 else None, (x1, z) if x == x1 - 1 else None,
                    (x, z0) if z == z0 + 1 else None, (x, z1) if z == z1 - 1 else None]
            wall = [w for w in wall if w]
            for y in ys:
                if not t.is_free(x, y, z):
                    continue
                if any(t.get(wx, y, wz) and ("pane" in t.get(wx, y, wz) or "door" in t.get(wx, y, wz)
                                              or "glass" in t.get(wx, y, wz)) for wx, wz in wall):
                    continue
                if skip_door and abs(x - skip_door[0]) + abs(z - skip_door[1]) <= 1:
                    continue
                if any(abs(x - a) + abs(z - b) == 1 for a, b in clear):
                    continue
                t.set(x, y, z, "bookshelf")


def reading_table(t, th, x, z):
    table(t, th, x, 1, z)
    t.set(x, 2, z, "candle[candles=1,lit=true]")
    chair(t, th, x - 1, 1, z, "west")
    chair(t, th, x + 1, 1, z, "east")


def library_variant(th, rng, name, v):
    t = Template(name)
    if v == 1:
        W, zf = 13, 2
        D = 13
        zb, cx = zf + D - 1, W // 2
        entrance(t, th, cx)
        t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
        shell(t, th, 0, zf, W - 1, zb, 0, 7, roof="none")
        door(t, cx, 1, zf, th["door"], "north")
        for side in ("north", "south", "west", "east"):
            windows_on_wall(t, th, 0, zf, W - 1, zb, side, 5, rng, skip=[(cx, zf)])
        # roof with a central glazed lantern of 5 x 5
        lx0, lz0, lx1, lz1 = cx - 2, zf + 4, cx + 2, zb - 4
        if th["roof_type"] == "flat":
            flat_roof(t, th, 0, zf, W - 1, zb, 8, light=False)
            ly = 9
        else:
            hip_roof(t, th, 0, zf, W - 1, zb, 8, overhang=1, upturn=(th["roof_type"] == "pagoda"), max_rings=3)
            t.fill(1, 8, zf + 1, W - 2, 10, zb - 1, th["planks"], keep=True)
            ly = 11
        for x in range(lx0 - 1, lx1 + 2):
            for z in range(lz0 - 1, lz1 + 2):
                for y in range(8, ly + 3):
                    edge = x in (lx0 - 1, lx1 + 1) or z in (lz0 - 1, lz1 + 1)
                    corner = x in (lx0 - 1, lx1 + 1) and z in (lz0 - 1, lz1 + 1)
                    if y < ly:
                        t.set(x, y, z, th["wall"] if edge else "air")
                    elif edge:
                        t.set(x, y, z, log(th["log"], "y") if corner else th["window"])
                    else:
                        t.set(x, y, z, "air")
        if th["roof_type"] == "flat":
            flat_roof(t, th, lx0 - 1, lz0 - 1, lx1 + 1, lz1 + 1, ly + 3, light=False)
        else:
            t.fill(lx0, ly + 3, lz0, lx1, ly + 3, lz1, th["planks"])
            hip_roof(t, th, lx0 - 1, lz0 - 1, lx1 + 1, lz1 + 1, ly + 3, overhang=1, upturn=(th["roof_type"] == "pagoda"))
        # shelves three tall around the whole perimeter, tables under the lantern, lectern and chest
        t.set(W - 2, 1, zf + 1, "air")
        t.chest(W - 2, 1, zf + 1, "west", L("biblioteca"))
        t.set(cx, 1, zb - 1, "lectern[facing=north]")
        staff(t, th, cx, 0, zb - 3, "librarian")
        shelves_on_walls(t, 0, zf, W - 1, zb, (1, 2, 3, 4), skip_door=(cx, zf + 1), clear=[(W - 2, zf + 1)])
        for z in (zf + 4, zf + 8):
            reading_table(t, th, cx - 3, z)
            reading_table(t, th, cx + 3, z)
        t.set(cx, 1, zf + 1, f"{th['carpet'][0]}_carpet")
        chandelier(t, th, cx, ly + 2, zf + D // 2)
        for z in (zf + 3, zb - 3):
            t.set(cx, 7, z, lantern(th, True))
        return t
    # cloister: wings in front (z 2..8), hall at the back (z 9..16), garden in the middle
    W, cx = 13, 6
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, stone_of(th))
    zf, zm, zb = 2, 9, 16
    for (x0, x1) in ((0, 3), (W - 4, W - 1)):
        shell(t, th, x0, zf, x1, zm, 0, 4, along="z")
        windows_on_wall(t, th, x0, zf, x1, zm, "west" if x0 == 0 else "east", 2, rng)
        windows_on_wall(t, th, x0, zf, x1, zm, "north", 2, rng)
    shell(t, th, 0, zm, W - 1, zb, 0, 6, along="x")
    for x in (0, W - 1):                      # passage between the wings and the hall
        for y in (1, 2, 3):
            t.set(x + (1 if x == 0 else -1), y, zm, "air")
            t.set(x + (2 if x == 0 else -2), y, zm, "air")
    # garden with low wall and gate in front
    for x in range(4, W - 4):
        for z in range(zf, zm):
            t.set(x, 0, z, "grass_block")
            for y in (1, 2, 3):
                t.set(x, y, z, "air")
        t.set(x, 1, zf, th["fence"])
    t.set(cx, 0, zf, th["path"])
    # the gate stands open: the court is the library's only way in, the librarian is placed in the hall behind it, and
    # villagers never open a gate (shut, it kept the librarian inside for good: tools/gen/enclosures.py)
    t.set(cx, 1, zf, f"{th['gate']}[facing=north,open=true]")
    for z in range(zf + 1, zm):
        t.set(cx, 0, z, th["path"])
    for z in (zf + 2, zf + 5):
        for x in (cx - 2, cx + 2):
            t.set(x, 1, z, rng.choice(["poppy", "azure_bluet", "oxeye_daisy", "cornflower"]))
    door(t, cx, 1, zm, th["door"], "north")
    door(t, 3, 1, zf + 4, th["door"], "east")
    door(t, W - 4, 1, zf + 4, th["door"], "west")
    for side in ("south", "west", "east"):
        windows_on_wall(t, th, 0, zm, W - 1, zb, side, 3, rng)
    # back hall: shelves, lectern, chest and tables; wings with shelves and a reading table
    t.chest(W - 2, 1, zb - 1, "north", L("biblioteca"))
    t.set(cx, 1, zb - 1, "lectern[facing=north]")
    staff(t, th, cx, 0, zb - 3, "librarian")
    shelves_on_walls(t, 0, zm, W - 1, zb, (1, 2, 3), skip_door=(cx, zm + 1), clear=[(W - 2, zb - 1)])
    for (x0, x1) in ((0, 3), (W - 4, W - 1)):
        shelves_on_walls(t, x0, zf, x1, zm, (1, 2), skip_door=(3 if x0 == 0 else W - 4, zf + 4))
    reading_table(t, th, cx - 3, zm + 4)
    reading_table(t, th, cx + 3, zm + 4)
    for z in (zm + 3, zb - 2):
        t.set(cx, 6, z, lantern(th, True))
    for x in (1, W - 2):
        t.set(x, 4, zf + 4, lantern(th, True))
    return t


# ======================================================================= GRANJA
def farm(th, rng, name, v=0):
    """v: 0 two terraced plots in front, barn and pen at the back (the original); 1 pen and barn in front, terraced plots at the
    back with an irrigation ditch between them; 2 market garden in strips, fruit trees in the middle and a long barn and pen at the back."""
    if v:
        return farm_variant(th, rng, name, v)
    t = Template(name)
    W, D = 21, 19
    cx = W // 2
    dry = th["family"] in ("desierto", "badlands")
    soil = "coarse_dirt" if dry else "grass_block"
    entrance(t, th, cx)
    for x in range(W):
        for z in range(1, D + 1):
            t.set(x, 0, z, soil)
            for y in (1, 2, 3):
                t.set(x, y, z, "air")
    for x in range(W):
        for z in (1, D):
            t.set(x, 1, z, th["fence"])
    for z in range(1, D + 1):
        for x in (0, W - 1):
            t.set(x, 1, z, th["fence"])
    # central path from door to door (the back one leads to the mill)
    for z in range(1, D + 1):
        t.set(cx, 0, z, th["path"])
    # the two gates of the outer fence stand open: the farmer is placed in the barn inside it and sleeps in a house of
    # the village, and villagers never open a gate (shut, he never left the farm: tools/gen/enclosures.py). The pen
    # keeps its own gate shut, for the animals.
    t.set(cx, 1, 1, f"{th['gate']}[facing=north,open=true]")
    t.set(cx, 1, D, f"{th['gate']}[facing=north,open=true]")
    t.jigsaw(cx, 0, D, "south_up", "heraldia:side", "heraldia:entrance", P(th, "mill"),
             final_state=th["path"], sel=6, place=6)
    # two terraced plots with a central irrigation ditch
    crops = ["wheat", "carrots", "potatoes", "beetroots"]
    rng.shuffle(crops)
    for i, fx in enumerate((1, cx + 1)):
        crop = crops[i]
        for x in range(fx, fx + 9):
            for z in range(2, 9):
                if x == fx + 4:
                    t.set(x, 0, z, "water")
                else:
                    t.set(x, 0, z, "farmland[moisture=7]")
                    age = rng.randint(4, 7) if crop != "beetroots" else rng.randint(2, 3)
                    t.set(x, 1, z, f"{crop}[age={age}]")
    # barn with the farmer's bed in a corner
    bx0, bz0 = 1, 10
    rk = "flat" if th["roof_type"] == "flat" else "gable"
    shell(t, th, bx0, bz0, bx0 + 7, bz0 + 7, 0, 4, roof=rk, along="z")
    door(t, bx0 + 7, 1, bz0 + 3, th["door"], "east")
    windows_on_wall(t, th, bx0, bz0, bx0 + 7, bz0 + 7, "west", 2, rng)
    for (x, z) in ((bx0 + 1, bz0 + 5), (bx0 + 1, bz0 + 6), (bx0 + 2, bz0 + 6)):
        t.set(x, 1, z, "hay_block[axis=y]")
    t.set(bx0 + 1, 2, bz0 + 6, "hay_block[axis=y]")
    t.set(bx0 + 4, 1, bz0 + 6, "composter[level=0]")
    t.chest(bx0 + 6, 1, bz0 + 6, "north", L("granja"))
    staff(t, th, bx0 + 1, 0, bz0 + 1, "farmer")
    pallet(t, th, bx0 + 1, 0, bz0 + 2)
    t.set(bx0 + 4, 4, bz0 + 3, lantern(th, True))
    # pen against the outer fence
    px0, pz0 = cx + 1, 10
    for x in range(px0, W - 1):
        t.set(x, 1, pz0, th["fence"])
    for z in range(pz0, D):
        t.set(px0, 1, z, th["fence"])
    t.set(px0, 1, pz0 + 4, f"{th['gate']}[facing=west,open=false]")
    t.set(px0 + 1, 1, pz0 + 1, "water_cauldron[level=3]")
    t.set(W - 2, 1, pz0 + 1, "hay_block[axis=y]")
    beasts = rng.choice([("cow", "cow", "sheep", "sheep"), ("pig", "pig", "chicken", "chicken"),
                         ("sheep", "sheep", "goat"), ("cow", "pig", "chicken", "sheep")])
    for i, b in enumerate(beasts):
        t.entity(px0 + 2 + (i % 2) * 3, 1, pz0 + 3 + (i // 2) * 3, animal(b))
    t.min_size = (W, 6, D + 1)
    return t


def crop_plot(t, rng, x0, z0, x1, z1, crop, water_x=None, water_z=None):
    """Terraced plot of farmland with an irrigation ditch in column water_x or in row water_z."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if x == water_x or z == water_z:
                t.set(x, 0, z, "water")
            else:
                t.set(x, 0, z, "farmland[moisture=7]")
                age = rng.randint(4, 7) if crop != "beetroots" else rng.randint(2, 3)
                t.set(x, 1, z, f"{crop}[age={age}]")


def farm_barn(t, th, rng, bx0, bz0, bx1, bz1, door_x, door_z, door_f, rk=None, along="z"):
    """Barn with the farmer, a straw pallet, hay, composter (his profession), farm chest and lantern. The farmer sleeps in a
    house of the village and walks to the farm in the morning (vanilla AI claims the closest free bed)."""
    rk = rk or ("flat" if th["roof_type"] == "flat" else "gable")
    shell(t, th, bx0, bz0, bx1, bz1, 0, 4, roof=rk, along=along)
    door(t, door_x, 1, door_z, th["door"], door_f)
    for side in ("north", "south", "west", "east"):
        windows_on_wall(t, th, bx0, bz0, bx1, bz1, side, 2, rng, skip=[(door_x, door_z)])
    staff(t, th, bx0 + 1, 0, bz0 + 1, "farmer")
    pallet(t, th, bx0 + 1, 0, bz0 + 2)
    for (x, z) in ((bx1 - 1, bz1 - 1), (bx1 - 2, bz1 - 1), (bx1 - 1, bz1 - 2)):
        t.set(x, 1, z, "hay_block[axis=y]")
    t.set(bx1 - 1, 2, bz1 - 1, "hay_block[axis=y]")
    t.set(bx0 + 1, 1, bz1 - 1, "composter[level=0]")
    t.chest(bx0 + 3, 1, bz1 - 1, "north", L("granja"))
    t.set((bx0 + bx1) // 2, 4, (bz0 + bz1) // 2, lantern(th, True))


def farm_pen(t, th, rng, px0, pz0, px1, pz1, gate, gate_f):
    for x in range(px0, px1 + 1):
        for z in (pz0, pz1):
            t.set(x, 1, z, th["fence"])
    for z in range(pz0, pz1 + 1):
        for x in (px0, px1):
            t.set(x, 1, z, th["fence"])
    t.set(gate[0], 1, gate[1], f"{th['gate']}[facing={gate_f},open=false]")
    t.set(px0 + 1, 1, pz0 + 1, "water_cauldron[level=3]")
    t.set(px1 - 1, 1, pz0 + 1, "hay_block[axis=y]")
    beasts = rng.choice([("cow", "cow", "sheep", "sheep"), ("pig", "pig", "chicken", "chicken"),
                         ("sheep", "sheep", "goat"), ("cow", "pig", "chicken", "sheep")])
    for i, b in enumerate(beasts):
        t.entity(px0 + 2 + (i % 2) * 3, 1, pz0 + 3 + (i // 2) * 2, animal(b))


def farm_variant(th, rng, name, v):
    t = Template(name)
    W, D = 21, 19
    cx = W // 2
    dry = th["family"] in ("desierto", "badlands")
    soil = "coarse_dirt" if dry else "grass_block"
    entrance(t, th, cx)
    for x in range(W):
        for z in range(1, D + 1):
            t.set(x, 0, z, soil)
            for y in (1, 2, 3):
                t.set(x, y, z, "air")
    for x in range(W):
        for z in (1, D):
            t.set(x, 1, z, th["fence"])
    for z in range(1, D + 1):
        for x in (0, W - 1):
            t.set(x, 1, z, th["fence"])
    for z in range(1, D + 1):
        t.set(cx, 0, z, th["path"])
    # open, as in farm(): the farmer has to walk out (tools/gen/enclosures.py); the pen's gate stays shut
    t.set(cx, 1, 1, f"{th['gate']}[facing=north,open=true]")
    t.set(cx, 1, D, f"{th['gate']}[facing=north,open=true]")
    t.jigsaw(cx, 0, D, "south_up", "heraldia:side", "heraldia:entrance", P(th, "mill"),
             final_state=th["path"], sel=6, place=6)
    crops = ["wheat", "carrots", "potatoes", "beetroots"]
    rng.shuffle(crops)
    if v == 1:
        # in front: pen on the left and barn across the width on the right
        farm_pen(t, th, rng, 1, 2, cx - 2, 9, (cx - 2, 5), "west")
        for z in range(2, 10):
            t.set(cx + 1, 0, z, th["path"])
        farm_barn(t, th, rng, cx + 2, 2, W - 2, 9, cx + 2, 5, "west", along="x")
        # behind: four terraced plots in furrows across the width, with an irrigation ditch along each one
        for i, (x0, x1) in enumerate(((1, cx - 1), (cx + 1, W - 2))):
            crop_plot(t, rng, x0, 11, x1, 13, crops[2 * i])
            for x in range(x0, x1 + 1):
                t.set(x, 0, 14, "water")
            crop_plot(t, rng, x0, 15, x1, 17, crops[2 * i + 1])
        for x in range(1, W - 1):
            t.set(x, 0, 10, th["path"])
    else:
        # in front: market garden in strips of two furrows with irrigation ditches between them
        for i, (x0, x1) in enumerate(((1, cx - 1), (cx + 1, W - 2))):
            crop_plot(t, rng, x0, 2, x1, 3, crops[2 * i])
            for x in range(x0, x1 + 1):
                t.set(x, 0, 4, "water")
            crop_plot(t, rng, x0, 5, x1, 6, crops[2 * i + 1])
        # fruit trees on the sides of the path
        for x in (2, 6, W - 7, W - 3):
            z = 9
            t.set(x, 1, z, log(th["log"], "y"))
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    t.set(x + dx, 2, z + dz, leaves(th))
            t.set(x, 3, z, leaves(th))
        for x in range(1, W - 1):
            t.set(x, 0, 7, th["path"])
        # behind: pen on the left and long barn on the right, with the door to the path
        farm_pen(t, th, rng, 1, 11, cx - 2, D - 1, (cx - 2, 14), "west")
        farm_barn(t, th, rng, cx + 2, 11, W - 2, D - 1, cx + 2, 14, "west")
    t.min_size = (W, 6, D + 1)
    return t


# ======================================================================= MOLINO
def sails(t, th, c, hub_y, hz, plane="z", arm=5):
    """Sails: log axle projecting from the wall (hz is the outer face), four fence-post blades and a sail on one side of
    each. plane="z": in the plane z = hz - 1 (north wall); plane="x": in the plane x = hz + 1 (east wall)."""
    if plane == "z":
        put = lambda a, y: t.set(c + a, y, hz - 1, th["fence"])
        put_s = lambda a, y, st: t.set(c + a, y, hz - 1, st)
        t.set(c, hub_y, hz, log(th["log"], "z"))
        t.set(c, hub_y, hz - 1, log(th["log"], "z"))
    else:
        put = lambda a, y: t.set(hz + 1, y, c + a, th["fence"])
        put_s = lambda a, y, st: t.set(hz + 1, y, c + a, st)
        t.set(hz, hub_y, c, log(th["log"], "x"))
        t.set(hz + 1, hub_y, c, log(th["log"], "x"))
    sail = f"{th['wool']}_wool"
    for k in range(1, arm + 1):
        for (dx, dy) in ((k, 0), (-k, 0), (0, k), (0, -k)):
            put(dx, hub_y + dy)
    for k in range(2, arm + 1):
        put_s(k, hub_y + 1, sail)
        put_s(-k, hub_y - 1, sail)
        put_s(-1, hub_y + k, sail)
        put_s(1, hub_y - k, sail)


def mill(th, rng, name, v=0):
    """v: 0 almost square-plan tower with sails at the front (the original); 1 round whitewashed tower with a
    conical roof; 2 lower tower with the miller's house in front and the sails on the side."""
    if v:
        return mill_variant(th, rng, name, v)
    t = Template(name)
    N, c, zf = 7, 3, 3
    entrance(t, th, c)
    t.fill(c - 1, 0, 1, c + 1, 0, zf - 1, th["path"])
    Ht = 11
    stone = th["family"] not in ("bosque", "taiga", "jungla", "pantano")
    for y in range(0, Ht + 1):
        for x in range(N):
            for z in range(zf, zf + N):
                dx, dz = x - c, z - zf - c
                if abs(dx) == 3 and abs(dz) == 3:
                    continue
                if y == 0:
                    t.set(x, y, z, stone_of(th))
                elif max(abs(dx), abs(dz)) == 3:
                    t.set(x, y, z, (th["wall2"] if y < 4 else th["wall"]) if stone else (th["planks"] if y > 3 else th["wall2"]))
                else:
                    t.set(x, y, z, "air")
    door(t, c, 1, zf, th["door"], "north")
    for y in (3, 8):
        t.set(0, y, zf + 3, th["window"]); t.set(6, y, zf + 3, th["window"])
    # upper milling floor, reached by the ladder
    t.fill(1, 6, zf + 1, 5, 6, zf + 5, th["planks"])
    for y in range(1, 7):
        t.set(5, y, zf + 5, "ladder[facing=north]")
    t.fill(1, Ht, zf + 1, 5, Ht, zf + 5, th["planks"])
    for (x, z) in ((1, zf + 5), (1, zf + 4), (2, zf + 5)):
        t.set(x, 1, z, "hay_block[axis=y]")
    t.chest(1, 1, zf + 1, "east", L("molino"))
    t.set(3, 5, zf + 3, lantern(th, True))
    t.set(3, 7, zf + 3, "grindstone[face=floor,facing=north]")
    t.set(1, 7, zf + 1, "barrel[facing=up]"); t.set(1, 7, zf + 2, "hay_block[axis=y]")
    t.set(3, Ht - 1, zf + 3, lantern(th, True))
    if th["roof_type"] == "cone":
        cone_roof(t, th, c, zf + c, 3, Ht + 1)
    else:
        hip_roof(t, th, 0, zf, N - 1, zf + N - 1, Ht + 1, overhang=1)
    # sails: four fence posts from the axle and a sail on one side of each
    sails(t, th, c, Ht - 2, zf - 1)
    return t


def mill_variant(th, rng, name, v):
    t = Template(name)
    stone = th["family"] not in ("bosque", "taiga", "jungla", "pantano")
    if v == 1:
        r, c, zf, Ht = 3, 3, 3, 12
        cz = zf + r
        entrance(t, th, c)
        t.fill(c - 1, 0, 1, c + 1, 0, zf - 1, th["path"])
        body = "white_terracotta" if stone else th["wall"]
        for y in range(0, Ht + 1):
            for x in range(c - r, c + r + 1):
                for z in range(cz - r, cz + r + 1):
                    d = math.hypot(x - c, z - cz)
                    if d > r + 0.5:
                        continue
                    if y == 0:
                        t.set(x, y, z, stone_of(th))
                    elif d > r - 0.5:
                        t.set(x, y, z, stone_of(th) if y < 2 else body)
                    else:
                        t.set(x, y, z, "air")
        door(t, c, 1, zf, th["door"], "north")
        for y in (4, 9):
            t.set(c - r, y, cz, th["window"]); t.set(c + r, y, cz, th["window"])
        t.set(c, 9, cz + r, th["window"])
        t.fill(c - 2, 6, cz - 2, c + 2, 6, cz + 2, th["planks"])
        for x in range(c - r, c + r + 1):    # the floor slab only inside the circle
            for z in range(cz - r, cz + r + 1):
                if math.hypot(x - c, z - cz) > r - 0.5 and t.get(x, 6, z) == "minecraft:" + th["planks"]:
                    t.set(x, 6, z, body)
        for y in range(1, 7):
            t.set(c + 1, y, cz + 2, "ladder[facing=north]")
        t.fill(c - 2, Ht, cz - 2, c + 2, Ht, cz + 2, th["planks"])
        for (x, z) in ((c - 2, cz + 1), (c - 2, cz), (c - 1, cz + 2)):
            t.set(x, 1, z, "hay_block[axis=y]")
        t.chest(c - 2, 1, cz - 1, "east", L("molino"))
        t.set(c, 5, cz, lantern(th, True))
        t.set(c, 7, cz, "grindstone[face=floor,facing=north]")
        t.set(c - 2, 7, cz - 1, "barrel[facing=up]"); t.set(c - 2, 7, cz, "hay_block[axis=y]")
        t.set(c, Ht - 1, cz, lantern(th, True))
        cone_roof(t, th, c, cz, r, Ht + 1)
        sails(t, th, c, Ht - 2, zf - 1, arm=6)
        return t
    # miller's house in front (z 2..7) and 5 x 5 tower behind (z 8..12) with the sails to the east
    W, cx = 9, 4
    entrance(t, th, cx)
    t.fill(cx - 1, 0, 1, cx + 1, 0, 1, th["path"])
    rk = th["roof_type"] if th["roof_type"] not in ("cone", "pagoda") else "hip"
    shell(t, th, 0, 2, W - 1, 7, 0, 4, roof=rk, along="x")
    door(t, cx, 1, 2, th["door"], "north")
    for side in ("north", "west", "east"):
        windows_on_wall(t, th, 0, 2, W - 1, 7, side, 2, rng, skip=[(cx, 2)])
    t.chest(1, 1, 6, "north", L("molino"))
    for (x, z) in ((W - 2, 6), (W - 2, 5), (W - 3, 6)):
        t.set(x, 1, z, "hay_block[axis=y]")
    t.set(1, 1, 3, "crafting_table")
    t.set(cx, 4, 4, lantern(th, True))
    tx0, tz0, Ht = 2, 7, 13
    for y in range(0, Ht + 1):
        for x in range(tx0, tx0 + 5):
            for z in range(tz0, tz0 + 5):
                edge = x in (tx0, tx0 + 4) or z in (tz0, tz0 + 4)
                if y == 0:
                    t.set(x, y, z, stone_of(th))
                elif edge:
                    if z == tz0 and y <= 5:
                        continue                 # the house wall serves as the front of the tower
                    t.set(x, y, z, (th["wall2"] if y < 6 else th["wall"]) if stone else (th["planks"] if y > 5 else th["wall2"]))
                else:
                    t.set(x, y, z, "air")
    for y in (1, 2):
        t.set(cx, y, tz0, "air")
    for y in range(1, 8):
        t.set(tx0 + 1, y, tz0 + 3, "ladder[facing=north]")
    t.fill(tx0 + 1, 7, tz0 + 1, tx0 + 3, 7, tz0 + 3, th["planks"])
    t.set(tx0 + 1, 7, tz0 + 3, "ladder[facing=north]")
    t.set(cx, 8, tz0 + 2, "grindstone[face=floor,facing=north]")
    t.set(tx0 + 3, 8, tz0 + 3, "barrel[facing=up]")
    t.set(cx, 6, tz0 + 2, lantern(th, True))
    for (x, z) in ((tx0, tz0 + 2), (tx0 + 4, tz0 + 2)):
        t.set(x, 9, z, th["window"])
    t.fill(tx0 + 1, Ht, tz0 + 1, tx0 + 3, Ht, tz0 + 3, th["planks"])
    t.set(cx, Ht - 1, tz0 + 2, lantern(th, True))
    hip_roof(t, th, tx0, tz0, tx0 + 4, tz0 + 4, Ht + 1, overhang=1)
    sails(t, th, tz0 + 2, Ht - 3, tx0 + 4, plane="x")
    return t


# ======================================================================= HARBOR
# Two pieces: the hut with the pier (rigid, on land) and the quay (terrain_matching). The quay cannot be
# rigid: with beard_thin the game fills with earth up to 12 blocks below any rigid piece, and at sea it
# would raise a tongue of earth under the planks. terrain_matching rests each column on the surface (water counts):
# the plank (y=1) sits just above the water or the ground, and the piles (bottom row, y=0) go down to the bottom with the
# hasta_el_suelo processor. They do not hang from the village: AldeaStructure (Java) places them on the shore closest to the square,
# with the quay towards the sea, joining them by their heraldia:pier jigsaws (writer.village_with_port).
PIER_W, PIER_L = 9, 18


def port(th, rng, name, v=0):
    t = Template(name)
    W, D = PIER_W, 9
    pw = th["pier"]
    t.jigsaw(6, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty",
             final_state=stairs(pw["wstairs"], "south"))
    # port hut at the entrance, with the door to the pier
    shell(t, th, 0, 2, 4, 6, 0, 3)
    door(t, 4, 1, 4, th["door"], "east")
    t.chest(1, 1, 5, "north", L("puerto"))
    t.set(3, 1, 5, "barrel[facing=up]")
    t.set(1, 1, 3, "crafting_table")
    t.set(2, 3, 4, lantern(th, True))
    # pier: planks flush with the hut, railing to the east and cargo stacked in a corner
    for z in range(1, D):
        for x in range(5 if z < 7 else 0, W):
            t.set(x, 0, z, pw["planks"])
    for z in (1, 5):
        t.set(W - 1, 1, z, pw["fence"])
    t.set(W - 1, 2, 1, lantern(th, False))
    for (x, y, z) in ((0, 1, 8), (1, 1, 8), (0, 1, 7)):
        t.set(x, y, z, "barrel[facing=up]")
    t.jigsaw(4, 0, D - 1, "south_up", "heraldia:pier", "heraldia:pier", P(th, "port_pier"), final_state=pw["planks"])
    return t


def port_pier(th, rng, name, v=0):
    t = Template(name)
    W, Lp = PIER_W, PIER_L
    pw = th["pier"]
    for z in range(Lp):
        for x in range(W):
            t.set(x, 1, z, pw["planks"])
    # piles (bottom row: hasta_el_suelo extends them down to the bottom) with railing and lanterns
    for z in range(1, Lp, 4):
        for x in (0, W - 1):
            t.set(x, 0, z, log(pw["log"], "y"))
            t.set(x, 2, z, pw["fence"])
            if z % 8 == 5:
                t.set(x, 3, z, lantern(th, False))
    # crane with a barrel hanging at the tip
    gx, gz = W - 2, Lp - 3
    for y in range(2, 7):
        t.set(gx, y, gz, log(pw["log"], "y"))
    for x in range(gx - 3, gx + 1):
        t.set(x, 7, gz, log(pw["log"], "x"))
    for y in (6, 5):
        t.set(gx - 3, y, gz, "iron_chain[axis=y]")
    t.set(gx - 3, 4, gz, "barrel[facing=up]")
    t.set(1, 2, Lp - 1, "barrel[facing=up]")
    t.jigsaw(4, 1, 0, "north_up", "heraldia:pier", "heraldia:pier", "minecraft:empty", final_state=pw["planks"])
    wk = th["wood_kind"] if th["wood_kind"] not in ("bamboo", "pale_oak") else "oak"
    t.entity(-1, 1, Lp - 8, {"id": f"minecraft:{wk}_boat"})
    t.entity(W, 1, Lp - 4, {"id": "minecraft:oak_boat"})
    return t


SPECIALS = {
    "church": church, "cemetery": cemetery, "townhall": townhall, "market": market, "blacksmith": blacksmith,
    "tavern": tavern, "inn": lambda th, rng, n, v=0: tavern(th, rng, n, inn=True, v=v), "library": library,
    "farm": farm, "mill": mill, "port": port, "port_pier": port_pier,
}
# Variants of each special building (0 is the original); all with the same function and the same access
VARIANTS = {"church": 3, "cemetery": 3, "townhall": 3, "market": 3, "blacksmith": 3, "tavern": 3, "inn": 3,
            "library": 3, "farm": 3, "mill": 3}
