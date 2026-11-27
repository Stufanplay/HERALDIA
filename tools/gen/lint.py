"""Design audit: intact jigsaws, supports, doors with an exit, complete stairs and accesses."""
from collections import deque, Counter
from core import parse_state

PASS_WORDS = ("_carpet", "torch", "_banner", "rail", "pressure_plate", "button", "tripwire",
              "ladder", "_door", "poppy", "dandelion", "allium", "azure_bluet", "tulip", "orchid", "cornflower",
              "oxeye", "lily_of_the_valley", "rose_bush", "fern", "dead_bush", "sweet_berry", "wheat", "carrots",
              "potatoes", "beetroots", "cobweb", "lily_pad", "vine", "_sign", "short_grass", "lever",
              "redstone_wire")


def bname(st):
    return st.split("[")[0].replace("minecraft:", "") if st else None


def passable(st):
    if st is None:
        return True
    b = bname(st)
    if b in ("air", "structure_void", "water", "jigsaw_pass"):
        return True
    if "trapdoor" in b:
        return "open=true" in st
    if "fence_gate" in b:
        return True
    if b.endswith("_leaves") or b.endswith("_wall") or b.endswith("_fence") or b.endswith("_pane") or b == "iron_bars":
        return False
    return any(w in b for w in PASS_WORDS)


def top_height(st):
    """Height of the walkable surface inside the block (None = not walkable)."""
    if st is None:
        return None
    b = bname(st)
    if passable(st) and "_carpet" not in b:
        return None
    if "_carpet" in b:
        return 0.0
    if b.endswith("_slab"):
        return 0.5 if "type=bottom" in st else 1.0
    if b.endswith("_stairs"):
        return 0.5 if "half=bottom" in st else 1.0
    if b.endswith("_fence") or b.endswith("_wall") or "fence_gate" in b:
        return 1.5
    if "trapdoor" in b:
        return 1.0 if "half=top" in st else 0.2
    if "_bed" in b:
        return 0.56
    if b in ("lantern", "soul_lantern", "candle", "flower_pot", "bell", "brewing_stand", "campfire", "iron_chain",
             "decorated_pot", "lightning_rod", "skeleton_skull", "grindstone", "lectern", "composter",
             "cauldron", "water_cauldron", "lava_cauldron", "anvil", "stonecutter") or b.startswith("potted_"):
        return 1.5      # obstacle: cannot be walked over
    return 1.0


def solid_full(st):
    if st is None:
        return False
    h = top_height(st)
    b = bname(st)
    return h == 1.0 and not b.endswith("_stairs") or b.endswith("_stairs") or (b.endswith("_slab") and "type=top" in st) \
        or (b.endswith("_slab") and "type=double" in st)


LADDER_BACK = {"north": (0, 1), "south": (0, -1), "east": (-1, 0), "west": (1, 0)}
NEEDS_FLOOR = ("_carpet", "candle", "flower_pot", "potted_", "_door", "rail", "pressure_plate", "wheat", "carrots",
               "potatoes", "beetroots", "poppy", "dandelion", "allium", "azure_bluet", "tulip", "orchid",
               "cornflower", "oxeye", "lily_of_the_valley", "fern", "dead_bush", "sweet_berry", "brewing_stand",
               "campfire", "cauldron", "lectern", "composter", "decorated_pot", "skeleton_skull",
               "grindstone", "anvil", "short_grass", "lily_pad")
PLANT_SOIL = {"grass_block", "dirt", "coarse_dirt", "podzol", "farmland", "moss_block", "rooted_dirt", "mud"}
FLOWERS = ("poppy", "dandelion", "allium", "azure_bluet", "tulip", "orchid", "cornflower", "oxeye",
           "lily_of_the_valley", "fern", "sweet_berry", "short_grass", "rose_bush")


def prop(st, k):
    return parse_state(st)[1].get(k)


def resolved(t):
    """View of the piece with each jigsaw replaced by its final state."""
    class V:
        pass
    v = V()
    blocks = dict(t.blocks)
    for pos, (st, nbt) in t.blocks.items():
        if nbt and nbt.get("id") == "minecraft:jigsaw":
            fs = nbt["final_state"]
            blocks[pos] = (None if "structure_void" in fs else fs, None)
    # "Resolved" state declared by the template (open puzzles): {pos: state or None}
    for pos, st in getattr(t, "lint_open", {}).items():
        blocks[pos] = (st, None)
    v.blocks = {p: b for p, b in blocks.items() if b[0] is not None}
    v.get = lambda x, y, z: (v.blocks.get((x, y, z)) or (None,))[0]
    v.jigsaws = t.jigsaws
    v.bounds = t.bounds
    v.orig = t
    return v


def support_issues(t):
    out = []
    for j in t.jigsaws:
        st = t.get(*j["pos"])
        if st is None or bname(st) != "jigsaw":
            out.append(("jigsaw sobrescrito", j["pos"]))
    terrain = any(k in t.name for k in ("/streets/", "/avenues/", "/terminators/end", "/decor/"))
    t = resolved(t)
    g = t.get
    for (x, y, z), (st, nbt) in t.blocks.items():
        b = bname(st)
        below, above = g(x, y - 1, z), g(x, y + 1, z)
        if "lantern" in b and b != "sea_lantern":
            if prop(st, "hanging") == "true":
                if above is None or passable(above) and "iron_chain" not in above:
                    out.append(("farol colgante sin techo", (x, y, z)))
            elif (below is None and y > 0) or bname(below) == "air":
                out.append(("farol de pie sin apoyo", (x, y, z)))
        elif b == "iron_chain":
            if above is None or bname(above) == "air":
                out.append(("cadena sin enganche", (x, y, z)))
            if below is None or bname(below) == "air":
                out.append(("cadena sin nada colgado", (x, y, z)))
        elif b == "ladder":
            dx, dz = LADDER_BACK[prop(st, "facing")]
            back = g(x + dx, y, z + dz)
            if back is None or passable(back):
                out.append(("escalera de mano sin pared detrás", (x, y, z)))
        elif "wall_banner" in b or b == "wall_torch":
            dx, dz = LADDER_BACK[prop(st, "facing")]
            back = g(x + dx, y, z + dz)
            if back is None or passable(back):
                out.append((b + " sin pared", (x, y, z)))
        elif b.endswith("_door") and prop(st, "half") == "upper":
            continue
        elif b == "bell":
            if prop(st, "attachment") == "ceiling" and (above is None or passable(above)):
                out.append(("campana sin viga", (x, y, z)))
            if prop(st, "attachment") == "floor" and (below is None or passable(below)):
                out.append(("campana sin apoyo", (x, y, z)))
        elif b.endswith("_leaves"):
            continue
        elif any(w in b for w in NEEDS_FLOOR) or b.endswith("_fence") or b.endswith("_banner"):
            ground_ok = below is None and (y == 0 or (y == 1 and terrain))
            if b.endswith("_fence") and above is not None and bname(above).endswith("_fence"):
                ground_ok = True
            if not ground_ok and (below is None or bname(below) in ("air", "structure_void") or (
                    passable(below) and "_fence" not in below and bname(below) not in ("water",))):
                if not (b.endswith("_fence") and any(g(x + a, y, z + c) and bname(g(x + a, y, z + c)).endswith("_fence")
                                                     for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1)))):
                    if y > 0 or b not in ("rail",):
                        out.append((b + " sin apoyo", (x, y, z)))
        if b in ("wheat", "carrots", "potatoes", "beetroots") and bname(below) != "farmland":
            out.append(("cultivo fuera de tierra labrada", (x, y, z)))
        if not b.startswith("potted_") and any(w in b for w in FLOWERS) and "half=upper" not in st \
                and bname(below) not in PLANT_SOIL:
            out.append((b + " sobre suelo donde no vive", (x, y, z)))
        if b == "dead_bush" and bname(below) not in PLANT_SOIL | {"sand", "red_sand", "terracotta"}:
            out.append(("dead_bush sobre suelo donde no vive", (x, y, z)))
        if b == "lily_pad" and bname(below) != "water":
            out.append(("nenúfar fuera del agua", (x, y, z)))
        if b.endswith("_stairs") and y > 0 and "half=bottom" in st and (below is None or bname(below) == "air") \
                and (above is None or passable(above)) and "roof" not in b:
            sides = sum(1 for a, c2 in ((1, 0), (-1, 0), (0, 1), (0, -1))
                        if g(x + a, y, z + c2) is not None and not passable(g(x + a, y, z + c2)))
            if sides == 0:
                out.append(("peldaño suelto en el aire", (x, y, z)))
    return out


# ---------------------------------------------------------------- recorrido a pie
def climbable(g, x, y, z):
    """Ladder, or open trapdoor right above one (in the game you can also climb it)."""
    st = g(x, y, z)
    if bname(st) == "ladder":
        return True
    return bool(st) and "trapdoor" in bname(st) and "open=true" in st and bname(g(x, y - 1, z)) == "ladder"


FACE = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}


def walk(t, extra_ground=True):
    """Cells (x, y, z) where a player entering through the piece's access can stand,
    without jumping or breaking blocks. Returns {cell: feet height}."""
    t = resolved(t)
    g = t.get
    x0, y0, z0, x1, y1, z1 = t.bounds()

    def surf(x, y, z, mdx=0, mdz=0):
        """(height on entering, support height) with the feet in cell y, or None."""
        st = g(x, y, z)
        h = top_height(st)
        b = bname(st) if st else None
        if st is not None and b.endswith("_stairs") and "half=bottom" in st:
            fx, fz = FACE[prop(st, "facing")]
            low = (mdx, mdz) == (fx, fz)            # you enter from the low side going up
            return (y + 0.5 if low else y + 1.0, y + 1.0)
        if h is not None and h <= 0.6:
            return (y + h, y + h)
        if h is not None:
            return None
        below = g(x, y - 1, z)
        if below is None:
            return (float(y), float(y)) if (extra_ground and y - 1 < 0) else None
        hb = top_height(below)
        if hb is None:
            return (float(y), float(y)) if bname(below) == "water" or climbable(g, x, y - 1, z) else None
        if hb != 1.0 or (bname(below).endswith("_stairs") and "half=bottom" in below):
            return None
        return (float(y), float(y))

    def headroom(x, y, z, s):
        top = s + 1.8
        cy = y if s < y + 1 else y + 1
        while cy < top:
            st = g(x, cy, z)
            if cy == y:
                cy += 1
                continue
            if not passable(st):
                lowpart = cy + (0.5 if ("half=top" in st or "type=top" in st) else 0.0)
                if lowpart < top:
                    return False
            cy += 1
        return True

    seen = {}
    q = deque()
    for j in t.jigsaws:
        if j["name"] in ("heraldia:entrance", "heraldia:street", "heraldia:avenue"):
            x, y, z = j["pos"]
            st = g(x, y, z)
            if st is None or passable(st):
                seen[(x, y, z)] = float(y)
            else:
                seen[(x, y + 1, z)] = float(y + 1)
            q.append(next(iter([k for k in seen if k[0] == x and k[2] == z])))
    while q:
        x, y, z = q.popleft()
        s = seen[(x, y, z)]
        cand = []
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if not (x0 - 1 <= nx <= x1 + 1 and z0 - 1 <= nz <= z1 + 1):
                continue
            for ny in range(y + 1, y - 5, -1):
                r = surf(nx, ny, nz, dx, dz)
                if r is None:
                    if ny < y and not passable(g(nx, ny, nz)):
                        break           # going down you do not pass through a solid block (roof of the room below)
                    continue
                enter, stand = r
                if enter - s > 0.6 or stand > s + 1.01 or not headroom(nx, ny, nz, stand):
                    if passable(g(nx, ny, nz)):
                        continue        # air or ladder: keep going down the same column
                    break
                # the passage must be clear at body height
                cand.append((nx, ny if stand < ny + 1 else ny + 1, nz, stand))
                break
        here = g(x, y, z)
        if climbable(g, x, y, z) or climbable(g, x, y + 1, z) or climbable(g, x, y - 1, z):
            for ny in (y + 1, y - 1):
                st = g(x, ny, z)
                if climbable(g, x, ny, z) or (climbable(g, x, y, z) and passable(st)):
                    cand.append((x, ny, z, float(ny)))
        for (nx, ny, nz, ns) in cand:
            if (nx, ny, nz) not in seen:
                seen[(nx, ny, nz)] = ns
                q.append((nx, ny, nz))
    return seen


INTEREST = ("chest", "barrel", "crafting_table", "furnace", "blast_furnace", "smoker", "cartography_table",
            "brewing_stand", "composter", "fletching_table", "cauldron", "lectern", "stonecutter", "loom",
            "smithing_table", "grindstone", "anvil", "bell")


def access_issues(t):
    out = []
    if not any(j["name"] in ("heraldia:entrance", "heraldia:street", "heraldia:avenue") for j in t.jigsaws):
        return out
    seen = walk(t)
    cells = set(seen)
    t = resolved(t)

    def near(x, y, z, r=1):
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                for dy in (-1, 0, 1):
                    if abs(dx) + abs(dz) <= r and (x + dx, y + dy, z + dz) in cells:
                        return True
        return False

    g = t.get
    for (x, y, z), (st, nbt) in t.blocks.items():
        b = bname(st)
        if b.endswith("_door") and prop(st, "half") == "lower":
            f = prop(st, "facing")
            dx, dz = (0, 1) if f in ("north", "south") else (1, 0)
            a = (x + dx, y, z + dz) in cells or (x + dx, y - 1, z + dz) in cells
            c = (x - dx, y, z - dz) in cells or (x - dx, y - 1, z - dz) in cells
            if not (a and c):
                out.append(("puerta sin salida o sin acceso", (x, y, z)))
        elif b == "ladder":
            if not climbable(g, x, y + 1, z):
                # end of the stairs: must lead to a floor
                if not any((x + dx, y + 1, z + dz) in cells or (x + dx, y, z + dz) in cells
                           for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0))) or \
                        not any((x + dx, yy, z + dz) in cells for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                                for yy in (y, y + 1)):
                    out.append(("escalera de mano que no lleva a ningún sitio", (x, y, z)))
            if (x, y, z) not in cells:
                out.append(("escalera de mano inaccesible", (x, y, z)))
        elif b in INTEREST:
            hanging = bname(g(x, y + 1, z)) == "iron_chain" or prop(st, "attachment") == "ceiling"
            if not hanging and not near(x, y, z):
                out.append((b + " inaccesible", (x, y, z)))
    for j in t.jigsaws:
        if j["name"] == "heraldia:slot" and "villagers" in j["pool"]:
            x, y, z = j["pos"]
            if not near(x, y + 1, z, 1) and (x, y + 1, z) not in cells:
                out.append(("cama/aldeano inaccesible", (x, y, z)))
    return out


def template_issues(t, kind=None):
    # double doors and stair headroom: in all templates, including those audited separately
    iss = door_pair_issues(t) + stair_headroom_issues(t)
    if not getattr(t, "no_generic_audit", False):   # structures audited as a whole in their module
        # lint_view: the same piece with its mechanisms activated (e.g. secret doors open)
        iss += support_issues(t) + access_issues(getattr(t, "lint_view", None) or t)
    if kind is not None:
        import ladders
        if ladders.is_village(kind):
            # a village ladder a villager can climb from the ground, and the closet that shuts its foot
            iss += ladders.issues(t)
            # a villager placed behind a shut fence gate, which it never opens (the farms, the cloister library)
            import enclosures
            iss += enclosures.issues(t)
    return iss


def lint_registry(reg, only=None):
    """{template: warnings} of the generic audit, in registry order (split across processes)."""
    import parallel
    names = [n for n in reg.templates if not only or only(n)]
    kinds = getattr(reg, "kinds", {})        # the kind picks the audits of a village piece (ladders.issues)
    found = parallel.map_obj(lambda n: template_issues(reg.templates[n], kinds.get(n)), names, chunksize=8)
    return {n: iss for n, iss in zip(names, found) if iss}


def summarize(res):
    c = Counter()
    ex = {}
    for name, iss in res.items():
        kind = "/".join(name.split("/")[1:])
        for msg, pos in iss:
            c[(kind, msg)] += 1
            ex.setdefault((kind, msg), (name, pos))
    return c, ex


# ---------------------------------------------------------------- double doors and stairs with a ceiling
LEFT_OF = {"north": "west", "west": "south", "south": "east", "east": "north"}   # izquierda de quien mira hacia `facing`
RIGHT_OF = {v: k for k, v in LEFT_OF.items()}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def door_hinge(facing, side):
    """Hinge of the leaf of a double door facing `facing`; `side` is the direction in which the other leaf lies.
    Each leaf has its hinge on its outer side (as when placing them by hand in the game): so they open as mirror images."""
    if side == LEFT_OF[facing]:
        return "right"
    if side == RIGHT_OF[facing]:
        return "left"
    raise ValueError(f"the other leaf ({side}) is not next to a door facing {facing}")


def door_pair_issues(t):
    """Pairs of adjacent doors (side by side) that do not form a correct double door:
    same `facing` and opposite hinges with the hinge on the outer side of each leaf."""
    out = []
    for (x, y, z), (st, _) in t.blocks.items():
        if not st or not bname(st).endswith("_door") or prop(st, "half") != "lower":
            continue
        f = prop(st, "facing")
        for side in (LEFT_OF[f], RIGHT_OF[f]):
            dx, dz = FACE[side]
            o = t.get(x + dx, y, z + dz)
            if not o or not bname(o).endswith("_door") or prop(o, "half") != "lower":
                continue
            if prop(o, "facing") not in (f, OPPOSITE[f]):
                continue
            if prop(o, "facing") != f or prop(st, "hinge") != door_hinge(f, side):
                out.append(("puerta doble con la bisagra mal emparejada", (x, y, z)))
    return out


def _bottom_stair(st, facing=None):
    return bool(st) and bname(st).endswith("_stairs") and "half=bottom" in st and (
        facing is None or prop(st, "facing") == facing)


def _blocks_body(st):
    return not passable(st)


def stair_headroom_issues(t):
    """Stairs of steps that cannot be passed without breaking anything. A flight is a row of two or more steps
    (step down, same `facing`) that rise one at a time and start from a walkable floor (this rules out roofs).
    Above each step two passable blocks are needed and, if another step follows, a third: when going up, the player
    (1.8 tall and 0.6 wide) puts their feet on the next step (at +1.5 and +2) with the body still over this one.
    On the landing at the top, two passable blocks above the floor."""
    v = resolved(t)
    g = v.get
    out = []
    for (x, y, z), (st, _) in v.blocks.items():
        if not _bottom_stair(st):
            continue
        f = prop(st, "facing")
        fx, fz = FACE[f]
        if _bottom_stair(g(x - fx, y - 1, z - fz), f) or not _bottom_stair(g(x + fx, y + 1, z + fz), f):
            continue        # only from the first step of each flight
        bx, by, bz = x - fx, y, z - fz      # cell from which the first step is stepped on
        base, under = g(bx, by, bz), g(bx, by - 1, bz)
        if not (passable(base) and (under is None and by <= 0 or under and top_height(under) == 1.0
                                     or bname(under) == "water" or _bottom_stair(under))
                or base and bname(base).endswith("_slab") and "type=bottom" in base
                or base and "_carpet" in bname(base)):
            continue        # no arranca de un suelo: tejado o adorno
        steps, cx, cy, cz = [], x, y, z
        while _bottom_stair(g(cx, cy, cz), f):
            steps.append((cx, cy, cz))
            cx, cy, cz = cx + fx, cy + 1, cz + fz
        if any(_bottom_stair(g(a, b + 1, c), f) for a, b, c in steps):
            continue        # stacked steps: the mass of a roof, not a staircase
        for cx, cy, cz in steps:
            nxt = _bottom_stair(g(cx + fx, cy + 1, cz + fz), f)
            if any(_blocks_body(g(cx, cy + k, cz)) for k in (1, 2)):
                out.append(("escalera con techo bajo", (cx, cy, cz)))
            elif nxt and _blocks_body(g(cx, cy + 3, cz)):
                out.append(("escalera con techo bajo en la subida", (cx, cy, cz)))
            if not nxt:
                ax, az = cx + fx, cz + fz
                land, up = g(ax, cy, az), g(ax, cy + 1, az)
                if up and (_bottom_stair(up) or bname(up).endswith("_slab") and "type=bottom" in up):
                    # half a step more: feet at +1.5 with the body still over the last step
                    if any(_blocks_body(g(q, cy + k, r)) for k in (2, 3) for q, r in ((ax, az), (cx, cz))):
                        out.append(("escalera con techo bajo al llegar arriba", (cx, cy, cz)))
                elif land and top_height(land) == 1.0 and not passable(land) and passable(up) \
                        and _blocks_body(g(ax, cy + 2, az)):
                    out.append(("escalera con techo bajo al llegar arriba", (cx, cy, cz)))
    return out
