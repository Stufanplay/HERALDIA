"""Builds all the pieces, pools and JSON of the datapack."""
import json, os, random, shutil
import uniques
import mediums
import mines
import houses
import shore as coast
from uniques._common import chest_loot
from core import Template, nsid, NS
from lint import passable
from themes import THEMES, FAMILIES
from houses import make_house, PROFS_HOUSE
import streets
from streets import (straight, crossroad, terminator_end, watchtower, gate, plaza, avenue, decor_piece, P)
from specials import SPECIALS, VARIANTS
from fillers import filler, villager_piece, golem_piece, rug_piece
import board
import traces
import trades
import parallel

SPARE = 22        # weight of "free bed" in the houses

ALL_PROFS = ["armorer", "butcher", "cartographer", "cleric", "farmer", "fisherman", "fletcher", "leatherworker",
             "librarian", "mason", "shepherd", "toolsmith", "weaponsmith"]

# the special buildings whose stone walls show lived-in wear (houses.weather_outside); the farm, the port and the graveyard
# are fences and low walls, not buildings
WEATHERED = ("church", "townhall", "market", "tavern", "blacksmith", "library", "inn", "mill")
AVENUES = {"a": ("church", "townhall"), "b": ("market", "tavern"), "c": ("blacksmith", "library"),
           "d": ("farm", None)}  # right of D: inn (the coast port is separate, on the shore)


def fix_supports(t):
    """Hanging lanterns: if there is no ceiling right above, they hang by a chain from the ceiling;
    if there is no ceiling nearby, they are propped up or removed."""
    for (x, y, z), (st, nbt) in list(t.blocks.items()):
        if "lantern[" in st and "hanging=true" in st:
            above = t.get(x, y + 1, z)
            if above and not passable(above):
                continue
            for k in range(1, 9):
                b = t.get(x, y + k, z)
                if b and not passable(b):
                    for kk in range(1, k):
                        t.set(x, y + kk, z, "iron_chain[axis=y]")
                    break
            else:
                below = t.get(x, y - 1, z)
                if below and not passable(below):
                    t.set(x, y, z, st.replace("hanging=true", "hanging=false"))
                else:
                    t.clear(x, y, z)


class Registry:
    def __init__(self):
        self.templates = {}       # nombre -> Template
        self.pools = {}           # id -> dict(elements=[(loc|None, weight, projection, processors)], fallback)
        self.kinds = {}           # template name -> type (house, special:x, filler, street...)
        self.warnings = []
        self.story = {}        # unique structure id -> chests with the table of its sheet (STORY["cofre"])
        self.guardians = {}      # unique structure id -> {mob type: original death table} (tag_guardians, trophies)

    def add(self, t, kind):
        fix_supports(t)
        t.normalize()
        x0, y0, z0, x1, y1, z1 = t.bounds()
        sx, sy, sz = t.size()
        for j in t.jigsaws:
            f = j["orientation"].split("_")[0]
            x, y, z = j["pos"]
            if j["name"] in ("heraldia:entrance", "heraldia:avenue") and z != 0:
                self.warnings.append(f"{t.name}: entrance is not on the edge (z={z})")
            if j["name"] in ("heraldia:side", "heraldia:street", "heraldia:avenue", "heraldia:entrance"):
                ok = {"north": z == 0, "south": z == sz - 1, "west": x == 0, "east": x == sx - 1}[f]
                if not ok:
                    self.warnings.append(f"{t.name}: connector {j['name']} {f} at {j['pos']} is not on the face of the box {sx, sy, sz}")
            st = t.get(x, y, z)
            if st is None or "jigsaw" not in st:
                self.warnings.append(f"{t.name}: jigsaw sobrescrito en {j['pos']}")
        self.templates[t.name] = t
        self.kinds[t.name] = kind
        return t.name

    def pool(self, pid, elements, fallback="minecraft:empty"):
        self.pools[nsid(pid)] = dict(elements=elements, fallback=nsid(fallback) if fallback != "minecraft:empty" else fallback)


VARIANT_WEIGHTS = (2, 1, 1, 1, 1, 1, 1, 1)
# Each house holds the workstation of the house HOUSE_JOB_SHIFT places further on in the style's list (a fixed
# permutation of the same professions, so the village offers the same workstations): its resident works elsewhere and
# walks there every morning. 5 of 12 pairs a small house with a medium or large one, which stand on other streets more often.
HOUSE_JOB_SHIFT = 5   # the original slightly more frequent than each new variant


def function_signature(t):
    """What a special building does: villager and golem slots (with their pool), connectors to other pieces,
    loot tables, bells and workstations (each gives a profession to a villager; except barrels, which everywhere
    are also storage and decoration). All the variants of a special building must have the same."""
    from collections import Counter
    from build import WORKSTATION
    jobs = {b: p for p, b in WORKSTATION.items()}
    next_unique = Counter()
    for j in t.jigsaws:
        if j["name"] != "heraldia:entrance":
            next_unique[("jigsaw", j["name"], j["pool"])] += 1
    for st, nbt in t.blocks.values():
        if nbt and nbt.get("LootTable"):
            next_unique[("botín", str(nbt["LootTable"]))] += 1
        b = st.split("[")[0].replace("minecraft:", "")
        if b == "bell":
            next_unique[("campana",)] += 1
        b = "cauldron" if b.endswith("_cauldron") else b
        if b in jobs and b != "barrel":
            next_unique[("oficio", jobs[b])] += 1
    return next_unique


def variant_errors(reg, names):
    base = function_signature(reg.templates[names[0]])
    return [f"{n}: no hace lo mismo que {names[0]} ({function_signature(reg.templates[n]) - base} de más, "
            f"{base - function_signature(reg.templates[n])} de menos)"
            for n in names[1:] if function_signature(reg.templates[n]) != base]


def build_theme(reg, th, seed):
    rng = random.Random(seed)
    tid = th["id"]
    street_proc = nsid(f"{tid}/street")
    bld_proc = nsid(f"{tid}/building")
    # ---- calles
    els = []
    for i, (fn, w) in enumerate([(lambda n: straight(th, rng, n, 16), 4), (lambda n: straight(th, rng, n, 16), 2),
                                 (lambda n: straight(th, rng, n, 10), 3), (lambda n: crossroad(th, rng, n, "x"), 4),
                                 (lambda n: crossroad(th, rng, n, "t"), 5), (lambda n: crossroad(th, rng, n, "l"), 2)]):
        name = reg.add(fn(f"{tid}/streets/s{i}"), "street")
        els.append((name, w, "terrain_matching", street_proc))
    reg.pool(f"{tid}/streets", els, fallback=f"{tid}/terminators")
    els = [(reg.add(terminator_end(th, rng, f"{tid}/terminators/end"), "street"), 10, "terrain_matching", street_proc),
           (reg.add(watchtower(th, rng, f"{tid}/terminators/tower", stone=th["wall_style"] != "logcabin"), "tower"), 1, "rigid", bld_proc),
           (reg.add(watchtower(th, rng, f"{tid}/terminators/tower_b", stone=th["wall_style"] != "logcabin", with_golem=False), "tower"), 1, "rigid", bld_proc),
           (reg.add(gate(th, rng, f"{tid}/terminators/gate"), "gate"), 1, "rigid", bld_proc)]
    reg.pool(f"{tid}/terminators", els)
    # ---- small decoration
    els = []
    for k, w in streets.DECOR_WEIGHTS:
        els.append((reg.add(decor_piece(th, rng, f"{tid}/decor/{k}", k), "decor"), w, "rigid", None))
    els.append((None, streets.DECOR_EMPTY, "rigid", None))
    reg.pool(f"{tid}/decor", els, fallback=f"{tid}/decor")
    # ---- casas
    els = []
    profs = PROFS_HOUSE[:]
    rng.shuffle(profs)
    n = 0
    sizes = (("small", 4, 3), ("medium", 5, 3), ("large", 3, 2))
    depths = [profs[k % len(profs)] for k in range(sum(c for _, c, _ in sizes))]
    for size, count, w in sizes:
        for i in range(count):
            depth, job = depths[n], depths[(n + HOUSE_JOB_SHIFT) % len(depths)]
            n += 1
            t = make_house(th, rng, f"{tid}/houses/{size}_{i}", size, depth, job)
            els.append((reg.add(t, "house"), w, "rigid", bld_proc))
    fills = list(dict.fromkeys(list(th["decor"]) + ["well", "garden"]))
    for k in fills:
        t = filler(th, rng, f"{tid}/fillers/{k}", k)
        els.append((reg.add(t, "filler"), 1, "rigid", bld_proc))
    # traces of work in progress (aldeas.vida.rastros): a plot with its trace, on its own random source (tools/gen/traces.py)
    plot = traces.build(reg, th, seed)
    if plot:
        els.append((plot, traces.PLOT_WEIGHT, "rigid", bld_proc))
    reg.pool(f"{tid}/houses", els)
    # ---- especiales
    # the coast has an inn on the avenue like the rest; its port (hut + pier) is placed separately, on the shore, by
    # AldeaStructure (Java), which uses the pools special/port and port_pier
    # each special building has VARIANTS[kind] variants (0 is the original, with the style's shared rng so that it does not
    # change; the others with their own deterministic rng) and the pool draws them with VARIANT_WEIGHTS
    for kind in ("church", "townhall", "market", "tavern", "blacksmith", "library", "farm", "inn", "port", "cemetery", "mill"):
        if kind == "port" and th["family"] != "costa":
            continue
        els = []
        for v in range(VARIANTS.get(kind, 1)):
            vrng = rng if v == 0 else random.Random(f"{seed}/{tid}/{kind}/{v}")
            t = SPECIALS[kind](th, vrng, f"{tid}/specials/{kind}" + ("" if v == 0 else f"_{'abcdefgh'[v]}"), v=v)
            if kind in WEATHERED:
                houses.weather_outside(t)
            els.append((reg.add(t, "special:" + kind), VARIANT_WEIGHTS[v] if VARIANTS.get(kind, 1) > 1 else 1,
                        "rigid", bld_proc))
        reg.warnings += variant_errors(reg, [e[0] for e in els])
        pid = f"{tid}/{kind}" if kind in ("cemetery", "mill") else f"{tid}/special/{kind}"
        reg.pool(pid, els)
    if th["family"] == "costa":
        t = SPECIALS["port_pier"](th, rng, f"{tid}/specials/port_pier")
        reg.pool(f"{tid}/port_pier", [(reg.add(t, "special:port_pier"), 1, "terrain_matching", nsid(f"{tid}/pier"))])
    # ---- avenidas
    for a, (lft, rgt) in AVENUES.items():
        if a == "d":
            rgt = "inn"
        t = avenue(th, rng, f"{tid}/avenues/{a}", P(th, f"special/{lft}"), P(th, f"special/{rgt}"))
        reg.pool(f"{tid}/avenue_{a}", [(reg.add(t, "avenue"), 1, "terrain_matching", street_proc)])
    # ---- quest board (hung in the square)
    board.build(reg, th)
    # ---- plaza
    reg.pool(f"{tid}/plaza", [(reg.add(plaza(th, rng, f"{tid}/plaza/std"), "plaza"), 1, "rigid", bld_proc)])
    reg.pool(f"{tid}/plaza_grande", [(reg.add(plaza(th, rng, f"{tid}/plaza/grande", large=True), "plaza"), 1, "rigid", bld_proc)])


def build_common(reg):
    for vtype in ("plains", "taiga", "snow", "desert", "savanna", "jungle", "swamp"):
        un = reg.add(villager_piece(vtype, f"villagers/{vtype}/unemployed", depth="none", employed=False), "villager")
        spare = reg.add(villager_piece(vtype, f"villagers/{vtype}/spare_bed"), "bed")
        rug = reg.add(rug_piece(vtype, f"villagers/{vtype}/rug"), "rug")
        for depth in ALL_PROFS:
            e = reg.add(villager_piece(vtype, f"villagers/{vtype}/e_{depth}", depth=depth), "villager")
            nb = reg.add(villager_piece(vtype, f"villagers/{vtype}/nb_{depth}", depth=depth, bed=False), "villager_nobed")
            # house bed slots: 12 % with a villager (2/3 with a profession), 37 % a free bed and the rest a rug (beds
            # ~1.1x villagers). The smith and the farmer sleep in houses (specials.pallet): the free beds went up from
            # 30 to 37 (27 to 34 in large villages) to keep that ratio.
            # the fallback points to the pool itself so that maximum-depth pieces are populated too
            p = f"villagers/{vtype}/{depth}"
            reg.pool(p, [(e, 8, "rigid", None), (un, 4, "rigid", None),
                         (spare, 37, "rigid", None), (rug, 51, "rigid", None)], fallback=p)
            # large villages (aliases in the structure): somewhat more population
            pg = f"villagers/{vtype}/{depth}_grande"
            reg.pool(pg, [(e, 16, "rigid", None), (un, 6, "rigid", None),
                          (spare, 34, "rigid", None), (rug, 44, "rigid", None)], fallback=pg)
            # inn and tavern rooms (on the avenues, next to the special buildings whose staff sleep elsewhere): always
            # a bed, sometimes with its guest; the same in both sizes
            pr = f"villagers/{vtype}/room_{depth}"
            reg.pool(pr, [(e, 12, "rigid", None), (un, 6, "rigid", None), (spare, 82, "rigid", None)], fallback=pr)
            reg.pool(f"villagers/{vtype}/fixed_{depth}", [(e, 1, "rigid", None)], fallback=f"villagers/{vtype}/fixed_{depth}")
            reg.pool(f"villagers/{vtype}/nobed_{depth}", [(nb, 1, "rigid", None)], fallback=f"villagers/{vtype}/nobed_{depth}")
    g = reg.add(golem_piece("golem"), "golem")
    reg.pool("golem", [(g, 1, "rigid", None)], fallback="golem")


# Relative cost of building each unique structure (measured): the longest ones are distributed among the processes first.
COST = {"isla_corsario": 9, "atlantida": 8, "acueducto": 6, "piramide": 6, "mina_perdida": 5, "ciudadela": 4}


def _part(task, seed):
    """Builds one part of the registry (the common part, a style or a unique structure) in its own registry."""
    reg = Registry()
    kind, x = task
    if kind == "comun":
        build_common(reg)
    elif kind == "estilo":
        build_theme(reg, THEMES[x], seed * 100 + x)
    elif kind == "mediana":
        mediums.build(reg, x)
    elif kind == "mina":
        mines.build(reg, x)
    elif kind == "costa":
        coast.build(reg, x)
    else:
        mod = dict(uniques.modules())[x]
        mod.build(reg)
        tag_guardians(reg, x)
        reg.warnings += chest_loot.trophy_errors(x, getattr(mod, "TROPHY", None))
        reg.warnings += story_chest(reg, x, mod)
    return reg


def build_all(seed=2026):
    """Full registry: the common part, each style, each unique structure, each medium structure and each mine size (in this order, as in serial), built in parallel
    (parallel.map_with_state: the data that a build leaves in its module returns to the parent). Same result in serial
    (HERALDIA_PROCESOS=1)."""
    tasks = [("comun", None)] + [("estilo", i) for i in range(len(THEMES))] + [("unica", sid) for sid, _ in uniques.modules()] \
        + [("mediana", mid) for mid, _ in mediums.modules()] + [("mina", size) for size in mines.SIZES] \
        + [("costa", kind) for kind in coast.KINDS]
    parts = parallel.map_with_state(lambda t: _part(t, seed), tasks,
                                      priority=lambda t: COST.get(t[1], 1) if t[0] == "unica" else 0)
    reg = Registry()
    for p in parts:
        for k, v in p.templates.items():
            if k in reg.templates:
                reg.warnings.append(f"duplicate template: {k}")
        reg.templates.update(p.templates)
        reg.pools.update(p.pools)
        reg.kinds.update(p.kinds)
        reg.warnings += p.warnings
        reg.story.update(p.story)
        reg.guardians.update(p.guardians)
    reg.warnings += chest_loot.story_chain_errors(uniques.modules())
    reg.warnings += trades.errors(uniques.modules()) + board.errors(THEMES)
    return reg


def story_chest(reg, sid, mod):
    """STORY contract (chest_loot.story_errors) and that its chest exists: some container of the unique structure's templates
    uses the table STORY["cofre"] (the sheet does not change the geometry: it goes in a chest that was already there)."""
    d = getattr(mod, "STORY", None)
    e = chest_loot.story_errors(sid, d, getattr(mod, "LOOT", {}))
    if e:
        return e
    tbl = f"{NS}:unicas/{sid}/{d['cofre']}"
    n = sum(1 for name, t in reg.templates.items() if name.startswith(f"unicas/{sid}/")
            for _, nbt in t.blocks.values() if nbt and str(nbt.get("LootTable", "")) == tbl)
    reg.story[sid] = n
    return [] if n else [f"unicas/{sid}: ningún cofre de sus plantillas usa {tbl} (HISTORIA.cofre)"]


def tag_guardians(reg, sid):
    """Adds to the guardians of a unique structure (Tags with pieces.GUARDIAN_TAG) the tag heraldia_guardian.<id>, with which
    its advancement recognises them on death (advancements.py), and sets as their DeathLootTable the table of its trophy
    (chest_loot.guardian_table: their usual loot + the trophy if a player kills them). Every unique structure must have at least one."""
    from uniques._common.pieces import GUARDIAN_TAG
    found, orig = 0, reg.guardians.setdefault(sid, {})
    for name, t in reg.templates.items():
        if not name.startswith(f"unicas/{sid}/"):
            continue
        for *_, n in t.entities:
            tags = n.get("Tags") or []
            if GUARDIAN_TAG in tags:
                if f"{GUARDIAN_TAG}.{sid}" not in tags:
                    n["Tags"] = list(tags) + [f"{GUARDIAN_TAG}.{sid}"]
                mob = str(n["id"])
                prev = str(n.get("DeathLootTable") or f"minecraft:entities/{mob.split(':')[-1]}")
                if prev != chest_loot.guardian_table_id(sid, mob):
                    if orig.setdefault(mob, prev) != prev:
                        reg.warnings.append(f"unicas/{sid}: guardians {mob} with different death tables")
                    n["DeathLootTable"] = chest_loot.guardian_table_id(sid, mob)
                found += 1
    if not found:
        reg.warnings.append(f"unicas/{sid}: no guardian with the tag {GUARDIAN_TAG} (use _comun/piezas.guardian)")
    elif found > 1:   # each guardian drops a trophy: one per structure
        reg.warnings.append(f"unicas/{sid}: {found} guardians with the tag {GUARDIAN_TAG}; there must be one (its trophy)")
