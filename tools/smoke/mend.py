"""/heraldia update mend on a world built by an EARLIER jar that has the faults (real 26.3 dedicated server).

Usage: python3 tools/smoke/mend.py --old-jar <jar with the faults> --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-mend"
The earlier jar is one built from a commit before the three fixes (the wharf guard's post, the inn's back door, the stream
from nowhere), e.g. develop at c8b9a66. Two starts of the same world:
1. With the earlier jar: the owner's steep spawn with a pond across the town's west wall (as tools/smoke/herald_steep.py),
   the Herald's House placed there and its grounds built (they leave running water with no source down the hillside);
   Roadside Inns and Fallen Shulker Wharfs of the End midlands generated naturally (found with /locate from points round
   the origin, their chunks loaded; medium structures four times as frequent). Somebody's changes, which the repair must never touch: one inn's window is glowstone; a player's
   fountain (a source with its water running off it) stands by the town; the first inn whose room chest stands in the
   way of the new door is filled to the brim (27 slots, full stacks, a 16-stack item and one with a component).
   The world is read back: the faults are there (or the test cannot say anything: it fails).
2. With the new jar: `heraldia update mend scan`, `heraldia update mend apply all` and its confirmation (from the
   console), then `apply all` again (it must find nothing to do), and the world read back:
   - no running water with no source in the town's area (herald_steep's own rule), the fountain still running;
   - every inn of an earlier version has its bedroom door, its room chest in the corner with what it held (every slot
     and every item of the full chest, its component kept, the old chest empty, none dropped); the inn with the
     glowstone is exactly as it was;
   - every midlands wharf's post is a purpur pillar and its guard, if alive, is on it, attached to its top;
   - no step over 100 ms on the server thread (the command's own log line).
Exit code 0 if everything passes.
"""
import argparse, json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s           # noqa: E402
import existing_world as ew        # noqa: E402
import herald_steep as hs          # noqa: E402
from guide import Server           # noqa: E402
from arena import Test             # noqa: E402
from trophies import CARPET        # noqa: E402
from modrinth import fetch         # noqa: E402

# Generated naturally (found with /locate and loaded): /place structure saves no structure start in the chunk, and the
# repair, as in a real world, finds what to repair by the starts the chunks keep.
INN_TARGET = "#heraldia:medianas/posada"
WHARF_TARGET = "heraldia:medianas/embarcadero_shulker/medias"
PROBES = [(1500 * i, 1500 * j) for r in range(1, 4) for i in range(-r, r + 1) for j in range(-r, r + 1) if max(abs(i), abs(j)) == r]
LOCATED = r"is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find"
FOUND = "mend-found.json"
STEP = 64
SLOW_MS = 100
# the inn's cells (tools/gen/mediums/inn.py: X1, Z0, Z1, PARTITION): the door, the old place of the room's chest, the new
INN_DOOR, INN_OLD_CHEST, INN_NEW_CHEST, INN_WINDOW = (16, 1, 8), (15, 1, 8), (12, 1, 5), (16, 2, 8)
# the wharf's guard post (tools/gen/mediums/shulker_dock.py: CX, 1, AZ - 3) and the guard's name
POST = (6, 1, 18)
GUARD = "heraldia.medianas.embarcadero_shulker.guardia"
# A chest filled to the brim, to catch a wrong slot or stack limit that 7 items in one slot cannot: the 27 slots of a
# chest, 25 of them a full stack of 64, one a full stack of an item whose stack is 16 (ender pearls), and one a single
# item carrying a component (a damaged sword). 25 * 64 + 16 + 1 = 1,617 items in 27 slots.
CHEST_FULL = ([(i, 64) for i in ("minecraft:diamond", "minecraft:gold_ingot", "minecraft:iron_ingot",
    "minecraft:emerald", "minecraft:redstone", "minecraft:lapis_lazuli", "minecraft:coal", "minecraft:copper_ingot",
    "minecraft:quartz", "minecraft:amethyst_shard", "minecraft:bone", "minecraft:string", "minecraft:leather",
    "minecraft:paper", "minecraft:book", "minecraft:stick", "minecraft:cobblestone", "minecraft:oak_log",
    "minecraft:dirt", "minecraft:sand", "minecraft:gravel", "minecraft:glass", "minecraft:brick",
    "minecraft:wheat", "minecraft:apple")]
    + [("minecraft:ender_pearl", 16), ("minecraft:diamond_sword[minecraft:damage=5]", 1)])
CHEST_ITEMS = sum(n for _, n in CHEST_FULL)
MEND_DONE = r"Heraldia: update mend (scan|apply) (\S+): (\d+) steps, (\d+) ms on the server thread, the slowest (\S+ -?\d+ -?\d+(?: \(part\))?) (\d+) ms[^;]*; (.*)"
CONFIRM = r"heraldia update mend apply all confirm (\S+)"


def rotate(rot, x, z):
    """StructureTemplate.calculateRelativePosition with no mirror or pivot."""
    return {"NONE": (x, z), "CLOCKWISE_90": (-z, x), "CLOCKWISE_180": (-x, -z), "COUNTERCLOCKWISE_90": (z, -x)}[rot]


def chunks(areas):
    """The chunks under a list of boxes (x0, z0, x1, z1 in blocks), each once."""
    seen = []
    for area in areas:
        for cx in range(area[0] >> 4, (area[2] >> 4) + 1):
            for cz in range(area[1] >> 4, (area[3] >> 4) + 1):
                if (cx, cz) not in seen:
                    seen.append((cx, cz))
    return seen


def starts(root, prefix, areas):
    """The structure starts saved in a dimension's regions under `areas` whose id starts with `prefix`:
    [(template, rotation, (x, y, z) of its origin)] of their single pieces."""
    out = []
    for cx, cz in chunks(areas):
        if True:
            n = ew.read_chunk(root, cx, cz)
            if n is None:
                continue
            for sid, st in n.get("structures", {}).get("starts", {}).items():
                if not str(sid).startswith(prefix) or str(st.get("id", "INVALID")) == "INVALID":
                    continue
                for ch in st.get("Children", []):
                    loc = str(ch.get("pool_element", {}).get("location", ""))
                    out.append((loc, str(ch.get("rotation", "NONE")), (int(ch["PosX"]), int(ch["PosY"]), int(ch["PosZ"]))))
    return out


def cell(piece, local):
    _, rot, (ox, oy, oz) = piece
    dx, dz = rotate(rot, local[0], local[2])
    return ox + dx, oy + local[1], oz + dz


def block_entity(root, x, y, z):
    n = ew.read_chunk(root, x >> 4, z >> 4)
    for be in (n or {}).get("block_entities", []):
        if int(be["x"]) == x and int(be["y"]) == y and int(be["z"]) == z:
            return be
    return None


def entities(root, areas):
    out = []
    for cx, cz in chunks(areas):
        if True:
            n = ew.read_chunk(root, cx, cz, "entities")
            out.extend((n or {}).get("Entities", []))
    return out


def guard_name(e):
    cn = e.get("CustomName")
    return isinstance(cn, dict) and str(cn.get("translate", "")) == GUARD or GUARD in str(cn)


def town_world(work):
    return hs.World(os.path.join(work, "world"))


class GameWorld(hs.World):
    """The saved world as the game sees water: a waterlogged block (a wall, a lantern, a slab with water in it) is a
    source, as it is in the game (it pours water and keeps what runs from it). herald_steep's rule counts only water
    blocks: in a town whose template was placed into a pond (a world from f865237) the walls came out waterlogged and
    feed a stream of 735 blocks that no tick would ever dry; that is not a stream from nowhere."""

    def block(self, x, y, z):
        cx, cz, sy = x >> 4, z >> 4, y >> 4
        if (cx, cz) not in self.chunks:
            n = ew.read_chunk(self.path, cx, cz)
            self.chunks[(cx, cz)] = n if n is not None and str(n.get("Status", "")).endswith("full") else None
        n = self.chunks[(cx, cz)]
        if n is None:
            return None
        key = (cx, cz, sy)
        if key not in self.sections:
            st = None
            for sec in n.get("sections", []):
                if int(sec["Y"]) == sy and sec.get("block_states") is not None:
                    st = ["water" if dict(q[1]).get("waterlogged") == "true" else hs.name(q)
                          for q in ew.states(ew._blueprint(sec["block_states"]))]
            self.sections[key] = st
        st = self.sections[key]
        return "air" if st is None else st[((y & 15) << 8) | ((z & 15) << 4) | (x & 15)]


def orphans_in(work, box, ground_y):
    """On the saved world: (running water with no source by the game's rule, still water standing in the air, the
    running water that only herald_steep's rule calls sourceless (fed by waterlogged blocks), world)."""
    world = town_world(work)
    ox, oz, mx, mz = box
    area = (ox - hs.RING, oz - hs.RING, mx + hs.RING, mz + hs.RING)
    cols = hs.survey(world, area, ground_y - 70, ground_y + 60)
    plain = hs.orphans(world, cols)
    game = hs.orphans(GameWorld(os.path.join(work, "world")), cols)
    return game, hs.standing(world, cols), sorted(set(plain) - set(game)), world


def read_state(work, inn_areas, wharf_areas):
    """What the test looks at: each inn's door, chests and window; each midlands wharf's post and guard."""
    ow, end = os.path.join(work, "world"), os.path.join(work, "world", "dimensions", "minecraft", "the_end")
    W, E = hs.World(ow), hs.World(end)
    inns = []
    for piece in starts(ow, "heraldia:medianas/posada/", inn_areas):
        b = lambda c: W.block(*cell(piece, c))
        old_be = block_entity(ow, *cell(piece, INN_OLD_CHEST))
        new_be = block_entity(ow, *cell(piece, INN_NEW_CHEST))
        inns.append({"piece": piece, "door": b(INN_DOOR), "upper": b(INN_WINDOW), "old_chest": b(INN_OLD_CHEST),
                     "new_chest": b(INN_NEW_CHEST), "old_items": (old_be or {}).get("Items", []), "new_items": (new_be or {}).get("Items", [])})
    wharfs = []
    ents = entities(end, [(b[0] - 32, b[1] - 32, b[2] + 32, b[3] + 32) for b in wharf_areas])
    for piece in starts(end, "heraldia:medianas/embarcadero_shulker/medias", wharf_areas):
        if not piece[0].endswith("/a"):
            continue                              # the b variant has no guard
        post = cell(piece, POST)
        guards = [e for e in ents if guard_name(e)]
        near = [e for e in guards if abs(float(e["Pos"][0]) - post[0]) <= 12 and abs(float(e["Pos"][2]) - post[2]) <= 12]
        on = [e for e in near if (int(float(e["Pos"][0]) // 1), int(round(float(e["Pos"][1]))), int(float(e["Pos"][2]) // 1))
              == (post[0], post[1] + 1, post[2])]
        wharfs.append({"piece": piece, "post": E.block(*post), "guards": len(near), "on_post": len(on),
                       "face": [int(e.get("AttachFace", -1)) for e in on]})
    return inns, wharfs


def find_natural(ctx, p, dim, target, n):
    """Up to `n` structures of `target` found with /locate from points round the origin and generated whole (their chunks
    loaded): their boxes, to read back."""
    found = []
    for px, pz in PROBES:
        if len(found) >= n:
            break
        m = ctx.run(f"execute in {dim} positioned {px} 64 {pz} run locate structure {target}", LOCATED)
        if not m.lastindex:
            continue
        x, z = int(m.group(1)), int(m.group(2))
        if any(abs(x - f[0]) < 64 and abs(z - f[1]) < 64 for f in found):
            continue
        ctx.run(f"execute in {dim} run forceload add {x - 48} {z - 48} {x + 64} {z + 64}", r"[Cc]hunk|marked|already")
        ctx.until(f"execute in {dim} if loaded {x + 63} 64 {z + 63}")
        ctx.until(f"execute in {dim} if loaded {x - 47} 64 {z - 47}")
        ctx.ticks(20)
        ctx.run(f"execute in {dim} run forceload remove {x - 48} {z - 48} {x + 64} {z + 64}", r"[Cc]hunk|unmarked|No")
        found.append((x, z))
    p.check(len(found) >= 2, f"{target}: only {len(found)} found")
    return [(x - 48, z - 48, x + 64, z + 64) for x, z in found]


def structures(ctx, p, work):
    """The inns and the wharfs, generated naturally; their boxes saved for the next starts."""
    inns = find_natural(ctx, p, "minecraft:overworld", INN_TARGET, 6)
    wharfs = find_natural(ctx, p, "minecraft:the_end", WHARF_TARGET, 8)
    ctx.ticks(100)                         # the wharf guards load, let go of their wall and teleport
    with open(os.path.join(work, FOUND), "w") as f:
        json.dump({"inns": inns, "wharfs": wharfs}, f)


def phase_old(a, p):
    """Start 1 (the earlier jar): the town on steep land, the inns, the wharfs and somebody's changes."""
    srv = Server(a.work, a.launcher)
    p.ctx = srv.ctx
    ctx, box, ground_y = srv.ctx, None, hs.SPAWN[1] - 1
    try:
        x, y, z = hs.SPAWN
        wx = x - 64
        ctx.run(f"forceload add {wx - 24} {z + 2} {wx + 24} {z + 30}", r"[Cc]hunk|marked|already")
        if not p.check(ctx.until(f"execute if loaded {wx - 12} {y} {z + 18}"), "the pond's chunks do not load"):
            return None
        top = ground_y + hs.POND_OVER
        ctx.run(f"fill {wx - 10} {ground_y - 30} {z + 8} {wx + 10} {top} {z + 28} minecraft:dirt", r"filled|Successfully|No blocks")
        ctx.run(f"fill {wx - 6} {top - hs.POND_DEPTH + 1} {z + 12} {wx + 6} {top} {z + 24} minecraft:water", r"filled|Successfully|No blocks")
        ctx.ticks(10)
        ctx.run(f"forceload remove {wx - 24} {z + 2} {wx + 24} {z + 30}", r"[Cc]hunk|unmarked|No")
        ctx.run(f"player {hs.P} spawn at {x} {y} {z}", r"joined the game|Unknown|Incorrect")
        if not p.check(ctx.until(f"execute if entity @a[name={hs.P}]"), "Carpet's player does not appear"):
            return None
        ctx.run(f"tp {hs.P} {x} {y} {z}", r"Teleported|Unknown")
        ctx.run(f"execute as {hs.P} run heraldia herald place here", r"heraldia|Herald|Heraldo|place|confirm")
        ctx.run(f"execute as {hs.P} run heraldia herald place confirm", r"Building the Herald's House|Construyendo la Casa del Heraldo")
        m = p.wait_log(hs.PLACED, 900)
        if not p.check(m, "the town is not placed"):
            return None
        box = [int(v) for v in m.groups()[3:]]
        ground_y = int(m.group(2))
        if not p.check(p.wait_log(hs.BUILT, 900), "the grounds' build does not finish"):
            return None
        ctx.run(f"player {hs.P} kill", r"left the game|Unknown|Incorrect")
        # a player's fountain by the town: a source on a pillar, its water running off it (fed: never to be touched)
        fx, fz = box[0] - 20, box[2] + 10
        ctx.run(f"forceload add {fx - 8} {fz - 8} {fx + 8} {fz + 8}", r"[Cc]hunk|marked|already")
        ctx.until(f"execute if loaded {fx} 64 {fz}")
        fy = 200                               # high in the air: its water falls to the ring, fed all the way
        ctx.run(f"setblock {fx} {fy - 1} {fz} minecraft:stone_bricks", r"Changed|Could not")
        ctx.run(f"setblock {fx} {fy} {fz} minecraft:water", r"Changed|Could not")
        ctx.ticks(200)
        fountain = (fx, fy, fz)
        ctx.run(f"forceload remove {fx - 8} {fz - 8} {fx + 8} {fz + 8}", r"[Cc]hunk|unmarked|No")
        structures(ctx, p, a.work)
        ctx.run("save-all flush", r"Saved the game|saved")
    finally:
        srv.stop()
    return box, ground_y, fountain


def phase_structures(a, p):
    """Start 1 without an earlier jar: the inns and the wharfs, placed by this jar (they come out right)."""
    srv = Server(a.work, a.launcher)
    p.ctx = srv.ctx
    try:
        structures(srv.ctx, p, a.work)
        srv.ctx.run("save-all flush", r"Saved the game|saved")
    finally:
        srv.stop()
    return True


FACING = {"NONE": {}, "CLOCKWISE_90": {"north": "east", "east": "south", "south": "west", "west": "north"},
          "CLOCKWISE_180": {"north": "south", "east": "west", "south": "north", "west": "east"},
          "COUNTERCLOCKWISE_90": {"north": "west", "east": "north", "south": "east", "west": "south"}}


def rotated(state, rot):
    return re.sub(r"facing=(\w+)", lambda m: "facing=" + FACING[rot].get(m.group(1), m.group(1)), state)


def age(a, p, inn_area, wharf_area):
    """Without an earlier jar: each structure is put back, block by block, as the version before the fix placed it
    (the patches' first `before`, rotated as the piece): the inn's wall and window where the door is, its room chest back
    in the door's way (empty: the generator's loot is not the point), the wharf's wall under its guard (who lets go of it
    and teleports, as he did)."""
    patches = {}
    for kind in ("inn", "wharf"):
        with open(os.path.join(s.ROOT, "src", "main", "resources", "heraldia", "mend", f"{kind}.json")) as f:
            for piece in json.load(f)["pieces"]:
                patches[piece["template"]] = piece
    ow, end = os.path.join(a.work, "world"), os.path.join(a.work, "world", "dimensions", "minecraft", "the_end")
    todo = [("minecraft:overworld", q) for q in starts(ow, "heraldia:medianas/posada/", inn_area)]
    todo += [("minecraft:the_end", q) for q in starts(end, "heraldia:medianas/embarcadero_shulker/", wharf_area)]
    srv = Server(a.work, a.launcher)
    ctx = p.ctx = srv.ctx
    aged = 0
    try:
        for dim, piece in todo:
            patch = patches.get(piece[0])
            if not patch:
                continue
            x, _, z = cell(piece, patch["cells"][0]["pos"])
            ctx.run(f"execute in {dim} run forceload add {x - 16} {z - 16} {x + 16} {z + 16}", r"[Cc]hunk|marked|already")
            ctx.until(f"execute in {dim} if loaded {x} 64 {z}")
            # the cells that take a container first (back to air), then the old blocks
            for c in sorted(patch["cells"], key=lambda c: "chest" not in c["after"]):
                w = cell(piece, c["pos"])
                ctx.run(f"execute in {dim} run setblock {w[0]} {w[1]} {w[2]} {rotated(c['before'][0], piece[1])}", r"Changed|Could not")
            aged += 1
        for dim in ("minecraft:overworld", "minecraft:the_end"):
            # the door's halves dropped as items when the other half went: not the repair's doing, so not left to count
            ctx.run(f"execute in {dim} run kill @e[type=minecraft:item]", r"Killed|No entity")
        ctx.ticks(100)                         # the guards let go of the wall and teleport
        ctx.run("save-all flush", r"Saved the game|saved")
    finally:
        srv.stop()
    return p.check(aged > 0, "nothing to age")


def tamper(a, p, inn_area):
    """Somebody's changes, made through the game (start 1b, earlier jar): glowstone in one inn's window, diamonds in
    another inn's room chest."""
    ow = os.path.join(a.work, "world")
    pieces = starts(ow, "heraldia:medianas/posada/", inn_area)
    if not p.check(len(pieces) >= 2, f"only {len(pieces)} inns saved"):
        return None, None
    srv = Server(a.work, a.launcher)
    ctx = p.ctx = srv.ctx
    try:
        mine, rich = pieces[0], pieces[1]
        for piece in (mine, rich):
            x, _, z = cell(piece, INN_DOOR)
            ctx.run(f"forceload add {x} {z}", r"[Cc]hunk|marked|already")
            ctx.until(f"execute if loaded {x} 64 {z}")
        ctx.run("setblock {} {} {} minecraft:glowstone".format(*cell(mine, INN_WINDOW)), r"Changed|Could not")
        x, y, z = cell(rich, INN_OLD_CHEST)
        for slot, (item, n) in enumerate(CHEST_FULL):
            ctx.run(f"item replace block {x} {y} {z} container.{slot} with {item} {n}", r"Replaced")
        ctx.run("save-all flush", r"Saved the game|saved")
    finally:
        srv.stop()
    return mine, rich


def mend(a, p):
    """Start 2 (the new jar): scan, apply all, confirm, apply all again."""
    srv = Server(a.work, a.launcher)
    p.ctx = srv.ctx
    ctx, out = srv.ctx, {}
    try:
        ctx.run("heraldia update mend scan", r"Looking for|Buscando|Unknown|Incorrect")
        m = p.wait_log(MEND_DONE, 900)
        if not p.check(m and m.group(1) == "scan", "the scan does not finish"):
            return out
        out["scan"] = m.group(0)
        print(f"MEND {m.group(0)}", flush=True)
        # declined: the operator is offered the repair and does not confirm it (the dialog's Cancel only closes it): a
        # scan afterwards finds exactly what the first one found, and the offer's id no longer confirms anything
        k = len(re.findall(MEND_DONE, ctx.log()))
        ctx.run("heraldia update mend apply all", r"Looking for|Buscando|Unknown|Incorrect")
        declined = p.wait_log(CONFIRM, 900)
        ctx.ticks(100)
        ctx.run("heraldia update mend scan", r"Looking for|Buscando|Unknown|Incorrect")
        end = time.monotonic() + 900
        while time.monotonic() < end and len(re.findall(MEND_DONE, ctx.log())) < k + 2:
            ctx.ticks(20)
        later = list(re.finditer(MEND_DONE, ctx.log()))[k:]
        if p.check(declined and len(later) >= 2, "the declined offer or the scan after it does not finish"):
            p.check(later[-1].group(7) == m.group(7), f"not confirming changed something: {m.group(7)} -> {later[-1].group(7)}")
            # a stale id (a later scan replaced that offer): refused, nothing runs
            r = ctx.run(f"heraldia update mend apply all confirm {declined.group(1)}",
                        r"Repairing|Reparando|no longer valid|ya no vale")
            p.check("no longer valid" in r.group(0) or "ya no vale" in r.group(0), f"a stale confirmation was not refused: {r.group(0)}")
            ctx.ticks(40)
            p.check(not any(x.group(1) == "apply" for x in re.finditer(MEND_DONE, ctx.log())), "a stale confirmation repaired")
            print("MEND declined and stale confirmations: nothing changed, nothing ran", flush=True)
        n_before = len(re.findall(MEND_DONE, ctx.log()))
        ctx.run("heraldia update mend apply all", r"Looking for|Buscando|Unknown|Incorrect")
        c = None
        end = time.monotonic() + 900
        while time.monotonic() < end and c is None:
            found = list(re.finditer(CONFIRM, ctx.log()))
            c = found[-1] if declined and found and found[-1].group(1) != declined.group(1) else (found[-1] if found and not declined else None)
            if c is None:
                ctx.ticks(20)
        if not p.check(c, "apply all does not offer its confirmation"):
            return out
        ctx.run(f"heraldia update mend apply all confirm {c.group(1)}", r"Repairing|Reparando|no longer|ya no")
        end = time.monotonic() + 900
        while time.monotonic() < end and not any(x.group(1) == "apply" for x in re.finditer(MEND_DONE, ctx.log())):
            ctx.ticks(20)
        ap = [x for x in re.finditer(MEND_DONE, ctx.log()) if x.group(1) == "apply"]
        if not p.check(ap, "the apply does not finish"):
            return out
        out["apply"] = ap[0].group(0)
        print(f"MEND {ap[0].group(0)}", flush=True)
        # again: nothing left to do
        k = len(re.findall(MEND_DONE, ctx.log()))
        ctx.run("heraldia update mend apply all", r"Looking for|Buscando|Unknown|Incorrect")
        end = time.monotonic() + 900
        while time.monotonic() < end and len(re.findall(MEND_DONE, ctx.log())) <= k:
            ctx.ticks(20)
        again = list(re.finditer(MEND_DONE, ctx.log()))[k:]
        if p.check(again, "the second apply's scan does not finish"):
            out["again"] = again[0].group(0)
            print(f"MEND again: {again[0].group(0)}", flush=True)
        ctx.ticks(200)                         # the streams' ticks run; the guards settle
        ctx.run("save-all flush", r"Saved the game|saved")
        for line in re.findall(r"Heraldia: update mend (?:scan|apply) \S+: \S+ (?:repair|left|notice) at .*", ctx.log()):
            print("MEND " + line, flush=True)
        out["slow"] = re.findall(r"update mend: a slow step: .*", ctx.log())
        out["n_before"] = n_before
    finally:
        srv.stop()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-jar", help="a jar from before the fixes; without it, the faults are made by hand (no town: streams untested)")
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-mend"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    a.launcher = s.prepare(a.work, os.path.abspath(a.old_jar or a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg["arena"] = {"generar_en_mundos_nuevos": False}
    cfg["casa_heraldo"] = {"generar_en_mundos_nuevos": False}
    cfg["medianas"] = {"frecuencia_porcentaje": 400}
    with open(os.path.join(a.work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)
    props = os.path.join(a.work, "server.properties")
    with open(props) as f:
        text = f.read().replace("level-seed=heraldia", f"level-seed={hs.SEED}\nlevel-type={hs.LEVEL_TYPE}\ndifficulty=hard")
    with open(props, "w") as f:
        f.write(text)
    fails, t0 = [], time.monotonic()
    p = Test(None, fails)
    town = None
    if a.old_jar:
        built = phase_old(a, p)
        if not built:
            print("MEND:", fails)
            return 1
        box, ground_y, fountain = built
        town = (box[0], box[2], box[3], box[5])
    elif not phase_structures(a, p):
        print("MEND:", fails)
        return 1
    with open(os.path.join(a.work, FOUND)) as f:
        found = json.load(f)
    inn_area, wharf_area = found["inns"], found["wharfs"]
    if not a.old_jar and not age(a, p, inn_area, wharf_area):
        print("MEND:", fails)
        return 1
    mine, rich = tamper(a, p, inn_area)
    # ---- the earlier world: the faults are there
    inns, wharfs = read_state(a.work, inn_area, wharf_area)
    if town:
        lost, wet, logged, world = orphans_in(a.work, town, ground_y)
        print(f"BEFORE: {len(lost)} blocks of running water with no source, {len(wet)} of still water standing in the air, "
              f"{len(logged)} running from waterlogged blocks; fountain {world.block(*fountain)}", flush=True)
        # which of the two an earlier jar leaves depends on the jar (the shores fix came first, the running-water one after)
        p.check(lost or wet, "before: neither a stream from nowhere nor water standing in the air by the town")
        p.check(world.block(*fountain) == "water", f"before: the fountain is {world.block(*fountain)}")
    for i in inns:
        print(f"BEFORE inn {i['piece']}: door {i['door']}/{i['upper']}, chest {i['old_chest']} -> {i['new_chest']}", flush=True)
    for w in wharfs:
        print(f"BEFORE wharf {w['piece']}: post {w['post']}, {w['guards']} guards near, {w['on_post']} on the post", flush=True)
    p.check(any(i["door"] != "air" and not i["door"].endswith("_door") for i in inns), "before: no inn without its back door")
    p.check(any(w["post"] == "end_stone_brick_wall" for w in wharfs), f"before: no wharf with a wall under its guard ({len(wharfs)} sentries)")
    before = {i["piece"]: i for i in inns}
    # the fill has to be in the world BEFORE the repair, or "nothing was lost" would mean nothing
    held = before.get(rich, {}).get("old_items", [])
    print(f"BEFORE inn {rich}: the chest holds {len(held)} slots, "
          f"{sum(int(it.get('count', 1)) for it in held)} items", flush=True)
    p.check(len(held) == len(CHEST_FULL) and sum(int(it.get("count", 1)) for it in held) == CHEST_ITEMS,
            f"the full chest was not filled, so the carry cannot be measured: {len(held)} slots")
    # ---- the new jar
    if a.old_jar and os.path.basename(a.old_jar) != os.path.basename(a.jar):
        shutil.copy(os.path.abspath(a.jar), os.path.join(a.work, "mods"))
        os.remove(os.path.join(a.work, "mods", os.path.basename(a.old_jar)))
    out = mend(a, p)
    for k in ("scan", "apply"):
        m = re.search(MEND_DONE, out.get(k, ""))
        if m:
            p.check(int(m.group(6)) <= SLOW_MS, f"{k}: a step of {m.group(6)} ms on the server thread (at most {SLOW_MS})")
            print(f"COST mend {k}: {m.group(3)} steps, {m.group(4)} ms on the server thread, the slowest {m.group(6)} ms", flush=True)
    m = re.search(MEND_DONE, out.get("again", ""))
    if p.check(m, "no second run"):
        p.check(" 0 to repair" in m.group(7) and not re.search(r"[1-9]\d* to repair", m.group(7)),
                f"the second run still finds something to repair: {m.group(7)}")
    # ---- read back
    if town:
        lost, wet, logged, world = orphans_in(a.work, town, ground_y)
        print(f"AFTER: {len(lost)} blocks of running water with no source, {len(wet)} of still water standing in the air, "
              f"{len(logged)} running from waterlogged blocks (not repaired: fed, by the game's rule); "
              f"fountain {world.block(*fountain)}", flush=True)
        p.check(not lost, f"after: {len(lost)} blocks of running water with no source by the town: {lost[:5]}")
        p.check(not wet, f"after: {len(wet)} blocks of still water standing in the air by the town: {wet[:5]}")
        p.check(world.block(*fountain) == "water", f"after: the player's fountain is {world.block(*fountain)}")
    else:
        print("streams: not exercised (no --old-jar: there is no town built by an earlier version)", flush=True)
    inns, wharfs = read_state(a.work, inn_area, wharf_area)
    fixed = left = 0
    for i in inns:
        b = before.get(i["piece"])
        print(f"AFTER inn {i['piece']}: door {i['door']}/{i['upper']}, chest {i['old_chest']} -> {i['new_chest']}", flush=True)
        if i["piece"] == mine:
            p.check(i["upper"] == "glowstone" and i["door"] == b["door"] and i["old_chest"] == b["old_chest"],
                    f"the inn with somebody's glowstone was touched: {i}")
            continue
        ok = i["door"].endswith("_door") and i["upper"].endswith("_door") and i["new_chest"] == "chest" and i["old_chest"] == "air"
        same = all(i[k] == b[k] for k in ("door", "upper", "old_chest", "new_chest"))
        fixed += ok
        left += same and not ok
        # either repaired whole, or left exactly as it was (the command found somebody's block there): nothing in between
        p.check(ok or same, f"an inn half repaired: {b} -> {i}")
        if i["piece"] == rich:
            got = sum(int(it.get("count", 1)) for it in i["new_items"])
            print(f"AFTER inn {i['piece']}: the full chest carried {len(i['new_items'])}/{len(CHEST_FULL)} slots, "
                  f"{got}/{CHEST_ITEMS} items; {len(i['old_items'])} slots left behind", flush=True)
            p.check(len(i["new_items"]) == len(CHEST_FULL),
                    f"the full chest lost slots: {len(i['new_items'])} of {len(CHEST_FULL)}")
            p.check(got == CHEST_ITEMS, f"the full chest lost items: {got} of {CHEST_ITEMS}")
            p.check(not i["old_items"], f"items stayed in the old chest: {i['old_items']}")
            p.check(any("damage" in str(it.get("components", "")) for it in i["new_items"]),
                    f"the item's component did not survive the carry: {i['new_items']}")
    p.check(fixed >= 1, "no inn repaired")
    print(f"AFTER: {fixed} inns repaired, {left} left exactly as they were", flush=True)
    # nothing dropped where the repair worked (the inns' crops drop their own seeds now and then: not counted)
    spots = [cell(i["piece"], c) for i in inns for c in (INN_DOOR, INN_OLD_CHEST, INN_NEW_CHEST, INN_WINDOW)]
    near = lambda e: any(abs(float(e["Pos"][0]) - x) <= 3 and abs(float(e["Pos"][1]) - y) <= 3 and abs(float(e["Pos"][2]) - z) <= 3
                         for x, y, z in spots)
    drops = [e for e in entities(os.path.join(a.work, "world"), inn_area) if str(e.get("id")) == "minecraft:item" and near(e)]
    p.check(not drops, f"items dropped where the inns were repaired: {[str(e.get('Item')) for e in drops][:3]}")
    for w in wharfs:
        print(f"AFTER wharf {w['piece']}: post {w['post']}, {w['guards']} guards near, {w['on_post']} on the post, faces {w['face']}", flush=True)
        p.check(w["post"] == "purpur_pillar", f"a wharf post is still {w['post']}")
        if w["guards"]:
            p.check(w["on_post"] == 1 and w["face"] == [0], f"the guard is not on its post: {w}")
    p.check(not out.get("slow"), f"slow steps: {out.get('slow')}")
    print(f"MEND: {time.monotonic() - t0:.0f} s;", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
