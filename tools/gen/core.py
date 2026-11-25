"""Core: structure templates (NBT 26.3), jigsaws and entities."""
import gzip, io, json, os, re, struct
import nbtlib
from nbtlib import Compound, List, Int, String, Double, Byte, Float, File

DATA_VERSION = 5023          # Minecraft 26.3
NS = "heraldia"
EMPTY_MARK = "heraldia_empty_on_purpose"   # a container left empty on purpose (filler_loot.leave_empty); never written

_STATE_RE = re.compile(r"^([a-z0-9_:./]+)(?:\[(.*)\])?$")


def norm_id(i):
    return i if ":" in i else "minecraft:" + i


def parse_state(s):
    m = _STATE_RE.match(s.strip())
    if not m:
        raise ValueError("invalid state: " + s)
    bid = norm_id(m.group(1))
    props = {}
    if m.group(2):
        for kv in m.group(2).split(","):
            k, v = kv.split("=")
            props[k.strip()] = v.strip()
    return bid, props


def state_str(bid, props):
    if not props:
        return bid
    return bid + "[" + ",".join(f"{k}={v}" for k, v in sorted(props.items())) + "]"


def with_props(s, **kw):
    bid, p = parse_state(s)
    p.update({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in kw.items()})
    return state_str(bid, p)


# Direcciones
DIRS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
OPP = {"north": "south", "south": "north", "west": "east", "east": "west", "up": "down", "down": "up"}
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}


class Template:
    def __init__(self, name):
        self.name = name          # ruta relativa: <tema>/houses/h1
        self.blocks = {}          # (x,y,z) -> (state, nbt|None)
        self.entities = []        # (x,y,z, nbt dict)
        self.jigsaws = []         # info for the simulator
        self.closets = []         # ladders.shut: [{"ladder": (x, z, y0, y1), "cells": {(x,y,z): previous state}}]
        self.min_size = (1, 1, 1)

    # --- blocks ---
    def set(self, x, y, z, state, nbt=None, keep=False):
        if state is None:
            return
        if keep and (x, y, z) in self.blocks and not self.blocks[(x, y, z)][0].startswith("minecraft:air"):
            return
        bid, props = parse_state(state)
        self.blocks[(x, y, z)] = (state_str(bid, props), nbt)

    def get(self, x, y, z):
        b = self.blocks.get((x, y, z))
        return b[0] if b else None

    def is_free(self, x, y, z):
        b = self.get(x, y, z)
        return b is None or b == "minecraft:air"

    def clear(self, x, y, z):
        self.blocks.pop((x, y, z), None)

    def fill(self, x1, y1, z1, x2, y2, z2, state, keep=False):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    self.set(x, y, z, state, keep=keep)

    def air(self, x1, y1, z1, x2, y2, z2):
        self.fill(x1, y1, z1, x2, y2, z2, "air")

    # --- blocks with an entity ---
    def chest(self, x, y, z, facing, loot, kind="chest"):
        st = f"{kind}[facing={facing}]"
        nbt = {"id": norm_id(kind), "LootTable": loot}
        self.set(x, y, z, st, nbt)

    def barrel(self, x, y, z, facing="up", loot=None):
        nbt = {"id": "minecraft:barrel"}
        if loot:
            nbt["LootTable"] = loot
        self.set(x, y, z, f"barrel[facing={facing}]", nbt)

    def jigsaw(self, x, y, z, orientation, name, target, pool, final_state="minecraft:air",
               joint="aligned", sel=0, place=0):
        fb, fp = parse_state(final_state)
        final_state = state_str(fb, fp)
        nbt = {"id": "minecraft:jigsaw", "name": nsid(name), "target": nsid(target),
               "pool": nsid(pool), "final_state": final_state, "joint": joint,
               "selection_priority": sel, "placement_priority": place}
        self.set(x, y, z, f"jigsaw[orientation={orientation}]", nbt)
        self.jigsaws.append(dict(pos=(x, y, z), orientation=orientation, name=nsid(name),
                                 target=nsid(target), pool=nsid(pool), joint=joint,
                                 sel=sel, place=place))

    def edge_jigsaw(self, side, along, y, name, target, pool, final_state="minecraft:structure_void", **kw):
        """Horizontal jigsaw on the outer face of the current bounding box."""
        x0, y0, z0, x1, y1, z1 = self.bounds()
        pos = {"east": (x1, y, along), "west": (x0, y, along), "south": (along, y, z1), "north": (along, y, z0)}[side]
        self.jigsaw(*pos, f"{side}_up", name, target, pool, final_state=final_state, **kw)

    # --- entidades ---
    def entity(self, x, y, z, nbt):
        self.entities.append((x, y, z, nbt))

    # --- utilidades ---
    def bounds(self):
        xs = [p[0] for p in self.blocks] + [e[0] for e in self.entities]
        ys = [p[1] for p in self.blocks] + [e[1] for e in self.entities]
        zs = [p[2] for p in self.blocks] + [e[2] for e in self.entities]
        return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)

    def normalize(self):
        """Shifts everything to coordinates >= 0."""
        x0, y0, z0, *_ = self.bounds()
        if (x0, y0, z0) == (0, 0, 0):
            return
        self.blocks = {(x - x0, y - y0, z - z0): v for (x, y, z), v in self.blocks.items()}
        self.entities = [(x - x0, y - y0, z - z0, n) for x, y, z, n in self.entities]
        for j in self.jigsaws:
            x, y, z = j["pos"]
            j["pos"] = (x - x0, y - y0, z - z0)
        for c in self.closets:
            lx, lz, ly0, ly1 = c["ladder"]
            c["ladder"] = (lx - x0, lz - z0, ly0 - y0, ly1 - y0)
            c["cells"] = {(x - x0, y - y0, z - z0): st for (x, y, z), st in c["cells"].items()}

    def size(self):
        x0, y0, z0, x1, y1, z1 = self.bounds()
        return (max(x1 + 1, self.min_size[0]), max(y1 + 1, self.min_size[1]), max(z1 + 1, self.min_size[2]))

    def to_nbt(self):
        x0, y0, z0, *_ = self.bounds()
        assert (x0, y0, z0) >= (0, 0, 0) and min(x0, y0, z0) >= 0, (self.name, x0, y0, z0)
        palette, index = [], {}
        blocks = []
        for pos in sorted(self.blocks, key=lambda p: (p[1], p[2], p[0])):
            st, nbt = self.blocks[pos]
            if st not in index:
                index[st] = len(palette)
                bid, props = parse_state(st)
                e = {"id": String(bid)}
                if props:
                    e["properties"] = Compound({k: String(v) for k, v in props.items()})
                palette.append(Compound(e))
            b = {"pos": List[Int]([Int(c) for c in pos]), "state": Int(index[st])}
            nbt = _written(nbt)
            if nbt:
                b["nbt"] = to_tag(nbt)
            blocks.append(Compound(b))
        ents = []
        for x, y, z, n in self.entities:
            fx, fz = x + 0.5, z + 0.5
            n = dict(n)
            n.setdefault("Pos", [float(fx), float(y), float(fz)])
            ents.append(Compound({
                "pos": List[Double]([Double(fx), Double(y), Double(fz)]),
                "blockPos": List[Int]([Int(x), Int(y), Int(z)]),
                "nbt": to_tag(n)}))
        sx, sy, sz = self.size()
        root = Compound({
            "DataVersion": Int(DATA_VERSION),
            "size": List[Int]([Int(sx), Int(sy), Int(sz)]),
            "palette": List[Compound](palette),
            "blocks": List[Compound](blocks),
            "entities": List[Compound](ents),
        })
        return root

    def nbt_raw(self):
        """The (uncompressed) NBT bytes of to_nbt(), written directly: the same bytes as File(self.to_nbt()).write,
        but without building an nbtlib Compound per block (that was almost all of the generator's time). What goes inside
        each block or entity (its nbt) still goes through to_tag and nbtlib, as before. tests/test_core.py compares it."""
        x0, y0, z0, *_ = self.bounds()
        assert (x0, y0, z0) >= (0, 0, 0) and min(x0, y0, z0) >= 0, (self.name, x0, y0, z0)
        out = io.BytesIO()
        w = out.write
        _tag(w, 10, "")                                               # File: unnamed root compound
        _tag(w, 3, "DataVersion")
        w(_I.pack(DATA_VERSION))
        _tag(w, 9, "size")
        _ints(w, self.size())
        palette, index, blocks = [], {}, []
        for pos in sorted(self.blocks, key=lambda p: (p[1], p[2], p[0])):
            st, nbt = self.blocks[pos]
            if st not in index:
                index[st] = len(palette)
                palette.append(st)
            blocks.append((pos, index[st], _written(nbt)))
        _tag(w, 9, "palette")
        w(b"\x0a" + _I.pack(len(palette)))
        for st in palette:
            bid, props = parse_state(st)
            _tag(w, 8, "id")
            _str(w, bid)
            if props:
                _tag(w, 10, "properties")
                for k, v in props.items():
                    _tag(w, 8, k)
                    _str(w, v)
                w(b"\x00")
            w(b"\x00")
        _tag(w, 9, "blocks")
        w(b"\x0a" + _I.pack(len(blocks)))
        for pos, i, nbt in blocks:
            _tag(w, 9, "pos")
            _ints(w, pos)
            _tag(w, 3, "state")
            w(_I.pack(i))
            if nbt:
                t = to_tag(nbt)
                _tag(w, t.tag_id, "nbt")
                t.write(out, "big")
            w(b"\x00")
        _tag(w, 9, "entities")
        w(b"\x0a" + _I.pack(len(self.entities)))
        for x, y, z, n in self.entities:
            fx, fz = x + 0.5, z + 0.5
            n = dict(n)
            n.setdefault("Pos", [float(fx), float(y), float(fz)])
            _tag(w, 9, "pos")
            w(b"\x06" + _I.pack(3) + _D.pack(float(fx)) + _D.pack(float(y)) + _D.pack(float(fz)))
            _tag(w, 9, "blockPos")
            _ints(w, (x, y, z))
            t = to_tag(n)
            _tag(w, t.tag_id, "nbt")
            t.write(out, "big")
            w(b"\x00")
        w(b"\x00")                                                    # end of the root compound
        return out.getvalue()

    def nbt_bytes(self):
        """The template's .nbt (gzip), compressed in one go and without a timestamp in the header (mtime 0): two generations of the
        same code give the same bytes (the header used to change on every build)."""
        return gzip.compress(self.nbt_raw(), compresslevel=9, mtime=0)

    def save(self, root_dir):
        """Writes the template; first every container without a table gets its filler table (filler_loot.fill, which
        fails if one has neither a table, nor a rule, nor the empty-on-purpose mark)."""
        import filler_loot
        filler_loot.fill(self)
        path = os.path.join(root_dir, "data", NS, "structure", self.name + ".nbt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.nbt_bytes())
        return path


def _written(nbt):
    """A block's nbt as it goes into the .nbt: without the generator's own mark EMPTY_MARK."""
    if nbt and EMPTY_MARK in nbt:
        return {k: v for k, v in nbt.items() if k != EMPTY_MARK}
    return nbt


_I, _D, _H = struct.Struct(">i"), struct.Struct(">d"), struct.Struct(">H")


def _str(w, s):
    b = s.encode("utf-8")
    w(_H.pack(len(b)) + b)


def _tag(w, tid, name):
    """Header of a named tag inside a compound: type and name."""
    w(bytes((tid,)))
    _str(w, name)


def _ints(w, vals):
    """Lista de enteros (List[Int])."""
    w(b"\x03" + _I.pack(len(vals)) + b"".join(_I.pack(int(v)) for v in vals))


def nsid(s):
    if s.startswith("minecraft:") or ":" in s:
        return s
    return f"{NS}:{s}"


class B(int):
    """Marca un byte NBT."""


class F(float):
    """Marca un float NBT."""


def to_tag(v):
    if isinstance(v, nbtlib.tag.Base):      # cualquier etiqueta NBT ya construida (p. ej. IntArray)
        return v
    if isinstance(v, B):
        return Byte(int(v))
    if isinstance(v, bool):
        return Byte(1 if v else 0)
    if isinstance(v, F):
        return Float(float(v))
    if isinstance(v, int):
        return Int(v)
    if isinstance(v, float):
        return Double(v)
    if isinstance(v, str):
        return String(v)
    if isinstance(v, dict):
        return Compound({k: to_tag(x) for k, x in v.items()})
    if isinstance(v, list):
        if not v:
            return List([])
        tags = [to_tag(x) for x in v]
        return List[type(tags[0])](tags)
    raise TypeError(type(v))


# --- entidades comunes ---
# The mobs of a template go through finalizeSpawn when placed. The zombies' one rolls a baby (5 %, with a chicken
# jockey) without looking at the NBT's IsBaby: the mod (ZombieMixin) prevents it for those carrying ADULT_TAG, and validate.py requires
# the tag on every BABY_ZOMBIE mob in the templates. Hoglin and zoglin come out as babies 20 % of the time with no fix in the mod: they
# cannot be put in templates. Animals and villagers (AgeableMob) are not affected: with a new group the first one is never a baby.
ADULT_TAG = "heraldia_adulto"
BABY_ZOMBIE = {"minecraft:" + m for m in ("zombie", "husk", "drowned", "zombie_villager", "zombified_piglin")}
BABY_NO_PROTECTION = {"minecraft:hoglin", "minecraft:zoglin"}


def adult(n):
    """Puts ADULT_TAG on the NBT of a mob that could spawn as a baby (BABY_ZOMBIE); returns the same NBT."""
    if n["id"] in BABY_ZOMBIE and ADULT_TAG not in n.get("Tags", []):
        n["Tags"] = list(n.get("Tags", [])) + [ADULT_TAG]
    return n


# Anchored mobs (the mod, comun/Anclaje.java, on loading them): they do not pick up items and do not wander until attacked. The
# finalizeSpawn of zombies and skeletons rolls CanPickUpLoot without looking at the NBT (piglins always have it), and a
# persistent mob wanders up to 10 blocks in the first 100 ticks of each load (sometimes outside its room). validate.py
# requires ANCHORED_TAG on every final guardian (pieces.GUARDIAN_TAG) and on every PICKS_UP_LOOT mob in the templates.
ANCHORED_TAG = "heraldia_anclado"
PICKS_UP_LOOT = BABY_ZOMBIE | {"minecraft:" + m for m in ("skeleton", "stray", "bogged", "wither_skeleton", "parched",
                                                         "piglin", "piglin_brute")}


def anchored(n, always=False):
    """Puts ANCHORED_TAG on the NBT of a mob that would pick up items (PICKS_UP_LOOT) or, with `always`, of any type (the
    final guardians); returns the same NBT."""
    if (always or n["id"] in PICKS_UP_LOOT) and ANCHORED_TAG not in n.get("Tags", []):
        n["Tags"] = list(n.get("Tags", [])) + [ANCHORED_TAG]
    return n


def villager(depth, vtype, employed=True):
    n = {"id": "minecraft:villager", "PersistenceRequired": B(1), "Tags": ["heraldia"],   # the map trades (maps.py) ask for it
         "VillagerData": {"profession": "minecraft:" + (depth if employed else "none"),
                          "level": 1, "type": "minecraft:" + vtype}}
    if employed:
        n["Xp"] = 1           # locks the profession
    return n


def golem():
    return {"id": "minecraft:iron_golem", "PlayerCreated": B(0), "PersistenceRequired": B(1)}


def animal(kind, **extra):
    n = {"id": "minecraft:" + kind, "PersistenceRequired": B(1)}
    n.update(extra)
    return n


def center_marker(tags):
    return {"id": "minecraft:armor_stand", "Invisible": B(1), "Marker": B(1), "NoGravity": B(1),
            "Invulnerable": B(1), "Silent": B(1), "Tags": list(tags)}
