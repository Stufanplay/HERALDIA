"""spawn_roads.py: the Herald's House roads (the owner's invariants as properties over many seeds and arena sites), the
roadside huts and the door rule over them, the blueprint, the options and the texts."""
import math
import random

import doors
import herald_house as h
import languages
import options
import spawn_roads as s

SPAWN_RADIUS = 48                       # herald/Siting.RADIUS: the town's centre is at most this far from spawn
ARENA_RINGS = range(200, 301, 25)       # arena/Site: RADIUS_MIN..RADIUS_MAX, every RADIUS_STEP
ARENA_HALF = 28                         # arena_waves.N // 2: the arena's box is 57 x 57


def _seeds(n, salt):
    r = random.Random(salt)
    return [r.getrandbits(64) - (1 << 63) for _ in range(n)]


def _world(r):
    """A town somewhere within SPAWN_RADIUS of spawn (0, 0) and an arena where arena/Site may put it."""
    ox, oz = r.randint(-SPAWN_RADIUS, SPAWN_RADIUS), r.randint(-SPAWN_RADIUS, SPAWN_RADIUS)
    ang = math.radians(15 * r.randrange(24))
    rad = r.choice(ARENA_RINGS)
    ax, az = round(rad * math.cos(ang)), round(rad * math.sin(ang))
    town = (ox - 64, oz - 64, ox + 63, oz + 63)
    gates = {k: (x + ox - 64, z + oz - 64) for k, (x, z) in h.GATES.items()}
    return town, gates, (ax - ARENA_HALF, az - ARENA_HALF, ax + ARENA_HALF, az + ARENA_HALF)


def _full(nr, start, from_head, res):
    return (s.head(nr) if from_head else nr) + res[0][1:]


# ------------------------------------------------------------------ the owner's invariants
def test_every_road_goes_away_from_spawn_for_at_least_45_blocks():
    for seed in _seeds(400, 1):
        for side in s.SIDES:
            gate = h.GATES[side]
            pts = s.normal_road(gate, side, seed)
            end = pts[-1]
            assert math.hypot(end[0] - gate[0] - 0.5, end[1] - gate[1] - 0.5) >= s.MIN_LENGTH >= 45
            # the distance to the town's centre (the spawn's plaza) grows along most of its segments: here, all but a tenth
            assert s.away_share(pts, (h.C + 0.5, h.PZ + 0.5)) >= 0.9, (seed, side)
            # and to a spawn anywhere the town may stand around it
            r = random.Random(seed)
            sx, sz = h.C + r.randint(-SPAWN_RADIUS, SPAWN_RADIUS), h.PZ + r.randint(-SPAWN_RADIUS, SPAWN_RADIUS)
            assert s.away_share(pts, (sx, sz)) > 0.5, (seed, side)


def test_the_straight_stretch_is_exact():
    for seed in _seeds(50, 2):
        for side in s.SIDES:
            gate = h.GATES[side]
            pts = s.normal_road(gate, side, seed)
            for p in s.head(pts):
                q = s.axis(gate, side, 0)
                dx, dz = s.outward(side)
                # on the gate's axis: its sideways coordinate is the gate's
                assert (p[0] - q[0]) * (-dz) + (p[1] - q[1]) * dx == 0
            assert s.head(pts)[-1] == s.axis(gate, side, s.STRAIGHT)


def test_the_arena_road_joins_the_town_and_the_arena_mostly_moving_away():
    r = random.Random(3)
    for seed in _seeds(1500, 3):
        town, gates, arena = _world(r)
        side, nr, start, from_head, res = s.arena_plan(gates, town, arena, seed)
        assert res is not None, (town, arena)
        pts, knots, clear = res
        entrance, approach = s.arena_points(arena)
        assert pts[-1] == entrance                     # it ends at the arena's entrance...
        boxes, _ = s.clear(pts, arena, town, lambda cx, cz: False)
        assert boxes                                   # ...without crossing its box or the town
        full = _full(nr, start, from_head, res)
        centre = ((town[0] + town[2]) / 2, (town[1] + town[3]) / 2)
        assert s.away_share(full, centre) > 0.5, (town, arena)
        assert s.polyline_length(full) <= s.LENGTH + s.MAX_ARENA_ROAD
        assert full[0] == s.axis(gates[side], side, 1)


def test_the_arena_road_takes_the_most_aligned_gate():
    gates = dict(h.GATES)
    for (ax, az), want in (((64, -250), "north"), ((64, 380), "south"), ((-240, 60), "west"), ((380, 60), "east")):
        assert s.arena_gate(gates, None, (ax, az)) == want


def test_a_structure_in_the_way_is_gone_round():
    arena = (36, -290, 92, -234)
    town = (0, 0, 127, 127)
    side, nr, start, from_head, straight = s.arena_plan(h.GATES, town, arena, 987654321)
    mx, mz = straight[0][len(straight[0]) // 2]
    bx, bz = math.floor(mx) >> 4, math.floor(mz) >> 4
    village = lambda cx, cz: abs(cx - bx) <= 1 and abs(cz - bz) <= 1
    side, nr, start, from_head, res = s.arena_plan(h.GATES, town, arena, 987654321, village)
    assert res[2] and len(res[1]) > 3
    assert s.clear(res[0], arena, town, village) == (True, True)
    # with structures everywhere it still joins them (their columns are left as they are) and says so
    side, nr, start, from_head, res = s.arena_plan(h.GATES, town, arena, 987654321, lambda cx, cz: True)
    assert res is not None and res[2] is False


def test_too_far_an_arena_is_not_joined():
    assert s.arena_road((64.5, -71.5), (36, -71 - s.MAX_ARENA_ROAD - 90, 92, -71 - s.MAX_ARENA_ROAD - 34), (0, 0, 127, 127), 1) is None


def test_no_dark_column_on_any_road():
    """Every road column is within LIGHT_REACH (Manhattan) of a lamp post: its block light at least 1 even with a few
    blocks of height between them (15 - 2, the lantern over the post's foot, - LIGHT_REACH - the terrain allowance)."""
    assert 15 - 2 - s.LIGHT_REACH >= 2
    r = random.Random(4)
    for seed in _seeds(150, 4):
        town, gates, arena = _world(r)
        side, nr, start, from_head, res = s.arena_plan(gates, town, arena, seed)
        roads = [s.normal_road(gates[k], k, seed) for k in s.SIDES if k != side]
        roads += [s.head(nr) if from_head else nr, res[0]]
        ls = [lamp for pts in roads[:-1] for lamp in s.lamps(pts)]  # every lamp lights every road
        ls += s.lamps(res[0], s.joined(nr, from_head))
        for pts in roads:
            for x, z in s.cells(pts):
                if town[0] <= x <= town[2] and town[1] <= z <= town[3]:
                    continue                           # the town's own columns: never paved (its wall, the gate)
                assert min(abs(x - lx) + abs(z - lz) for lx, lz in ls) <= s.LIGHT_REACH, (seed, x, z)


def test_lamps_never_fall_on_a_hut_or_on_the_road():
    for seed in _seeds(100, 5):
        for side in s.SIDES:
            gate = h.GATES[side]
            pts = s.normal_road(gate, side, seed)
            road = s.cells(pts)
            rects = []
            for _, sd, along in s.slots(True):
                _, _, world = s.hut_frame(gate, side, sd, along)
                cs = [world(x, z) for x in (0, s.HUT_SIZE[0] - 1) for z in (0, s.HUT_SIZE[2] - 1)]
                rects.append((min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs)))
            for lx, lz in s.lamps(pts):
                assert (lx, lz) not in road
                assert not any(r[0] <= lx <= r[2] and r[1] <= lz <= r[3] for r in rects), (side, lx, lz)


def test_the_same_numbers_as_the_java():
    """roads/SpawnRoadLayoutTest checks the Java against these same numbers: the two layouts cannot drift apart."""
    nr = s.normal_road((64, 0), "north", 12345)
    assert len(nr) == 6 and nr[0] == (64.5, -0.5) and nr[3] == (64.5, -43.5) and nr[5] == (62.5, -71.5)
    assert abs(nr[4][0] - 63.623404223) < 1e-6 and abs(nr[4][1] + 57.508814587) < 1e-6
    assert s.lateral(-7046029254386353131, (1000, -37)) == -7
    gates = {"north": (64, 0), "south": (64, 127), "west": (0, 60), "east": (127, 60)}
    side, nr, start, from_head, res = s.arena_plan(gates, (0, 0, 127, 127), (36, -290, 92, -234), 987654321)
    assert (side, from_head, start, len(res[0]), len(res[1])) == ("north", False, (69.5, -71.5), 11, 3)
    assert abs(res[0][8][0] - 65.467164748) < 1e-6 and abs(res[0][8][1] + 205.735851666) < 1e-6
    assert abs(s.polyline_length(res[0]) - 167.23663) < 1e-5
    assert s.lamps(nr)[:4] == [(68, -5), (61, -12), (68, -19), (61, -26)] and len(s.lamps(nr)) == 11
    al = s.lamps(res[0], s.joined(nr, from_head))
    assert len(al) == 25 and al[22:] == [(68, -224), (61, -231), (77, -157)]
    assert s.hut_frame((64, 0), "north", 1, 8)[:2] == ("counterclockwise_90", (67, -8))
    assert s.hut_frame((64, 127), "south", 1, 26)[:2] == ("clockwise_90", (61, 153))


# ------------------------------------------------------------------ the huts and the door rule
def test_the_door_rule_holds_for_every_hut():
    assert s.layout_errors() == []
    assert s.template_errors() == []
    for t in s.templates().values():
        assert doors.template_report(t) == []
    assert s.errors() == []


def test_the_door_rule_catches_a_hut_facing_a_wall():
    """Something built across the road, five blocks in front of a hut's door: the rule (doors.footprint_errors) refuses it."""
    gate = h.GATES["north"]
    rect, (facing, x, z) = s.hut_rect(gate, "north", *s.GUIDE_SLOT[1:])
    dx, dz = doors.OPEN_DIR[facing]
    wall = (min(x + 5 * dx, x + 6 * dx) - 1 * (dx == 0), min(z + 5 * dz, z + 6 * dz) - 1 * (dz == 0),
            max(x + 5 * dx, x + 6 * dx) + 1 * (dx == 0), max(z + 5 * dz, z + 6 * dz) + 1 * (dz == 0))
    e = doors.footprint_errors([("guide", rect, [(facing, x, z)]), ("stall", wall, [])])
    assert any("faces the wall of stall 5 blocks away" in m for m in e), e


def test_the_door_rule_catches_a_blocked_door():
    t = s.hut("farmer")
    x, y, z = s.DOOR
    t.set(x, y, z - 2, "cobblestone")
    t.set(x, y + 1, z - 2, "cobblestone")
    assert doors.template_report(t) != []
    assert any("door" in m for m in s.template_errors({"broken": t}))


def test_every_hut_has_what_a_villager_needs():
    for name, t in s.templates().items():
        names = [st for st, _ in t.blocks.values()]
        assert sum("_bed" in st for st in names) == 2
        assert sum(st.startswith("minecraft:bell") for st in names) == 1
        assert not any("torch" in st for st in names)
        (v,) = t.entities
        nbt = v[3]
        assert nbt["VillagerData"]["profession"] == "minecraft:" + (s.GUIDE_PROFESSION if name == "guia" else name)
        assert nbt["Xp"] == 1                    # the profession stays (vanilla trades)
        assert s.HUT_TAG in nbt["Tags"] and (s.GUIDE_TAG in nbt["Tags"]) == (name == "guia")
        assert t.get(*s.BELL).startswith("minecraft:bell[attachment=floor")
        assert s.STATIONS[s.GUIDE_PROFESSION if name == "guia" else name].split("[")[0] in t.get(*s.STATION)


def test_the_cap_and_the_professions():
    assert s.MAX_VILLAGERS == 8
    assert len(s.SIDES) * len(s.SLOTS) + 1 >= s.MAX_VILLAGERS
    assert 1 <= s.DEFAULT_VILLAGERS <= s.MAX_VILLAGERS
    assert len(set(s.PROFESSIONS)) == len(s.PROFESSIONS) and s.GUIDE_PROFESSION not in s.PROFESSIONS


# ------------------------------------------------------------------ what the Java side reads, options and texts
def test_the_blueprint(tmp_path):
    written = {}
    lang = s.write(str(tmp_path), lambda out, rel, obj: written.__setitem__(rel, obj))
    d = written["heraldia/caminos_casa.json"]
    assert d == s.dataset()
    assert (d["recto"], d["largo"], d["minimo"], d["ancho"]) == (s.STRAIGHT, s.LENGTH, s.MIN_LENGTH, s.WIDTH)
    assert d["chozas"]["maximo"] == 8 and d["lados"] == list(s.SIDES)
    assert {o["oficio"] for o in d["chozas"]["oficios"]} == set(s.PROFESSIONS)
    for name in list(s.PROFESSIONS) + ["guia"]:
        assert (tmp_path / "data" / "heraldia" / "structure" / (s.TEMPLATE_PREFIX + name + ".nbt")).is_file()
    assert lang == s.lang()


def test_the_options():
    ops = {o["clave"]: o for o in options.schema()["opciones"]}
    a, v = ops["casa_heraldo.caminos.activado"], ops["casa_heraldo.caminos.aldeanos"]
    assert a["defecto"] is True
    assert (v["defecto"], v["min"], v["max"]) == (s.DEFAULT_VILLAGERS, 0, s.MAX_VILLAGERS)
    assert a["seccion"] == v["seccion"] == "casa_heraldo"
    assert not options.is_generation("casa_heraldo.caminos.activado")


def test_the_texts_in_every_language():
    base = s.lang()
    assert base["es_es"].keys() == base["en_us"].keys()
    for code in languages.TRANSLATIONS:
        t = languages.load_data(code)
        for k in base["es_es"]:
            assert k in t, (code, k)
    assert s.text_errors({c: languages.load_data(c) for c in languages.TRANSLATIONS}) == []


def test_the_door_rule_is_really_checked_on_each_hut():
    """A block in front of a hut's door breaks the rule: no porch cover hides the door from the check (a door under a
    cover on its way out is skipped by doors.template_report, so a hut's porch stays open over its door)."""
    for name, t in s.templates().items():
        x, y, z = s.DOOR
        assert doors.template_report(t) == [], name
        t.set(x, 1, z - 2, "cobblestone")
        t.set(x, 2, z - 2, "cobblestone")
        assert doors.template_report(t), name


def test_no_two_huts_are_the_same_building():
    """Each hut has its own silhouette (the height of every column) and its own walls: eight buildings, not one cube
    with eight awnings. What the Java side places by position (door, bed, workstation, bell) is the same in all."""
    ts = s.templates()
    def skyline(t):
        top = {}
        for (x, y, z), (st, _) in t.blocks.items():
            if st != "minecraft:air" and "wool" not in st and "lantern" not in st:
                top[(x, z)] = max(top.get((x, z), 0), y)
        return tuple(sorted(top.items()))
    walls = {n: t.get(2, 3, s.HUT_SIZE[2] - 1) for n, t in ts.items()}
    assert len(set(walls.values())) == len(ts), walls
    assert len({skyline(t) for t in ts.values()}) >= 6
    for n, t in ts.items():
        assert "_door" in t.get(*s.DOOR) and "bell" in t.get(*s.BELL) and "_bed" in t.get(*s.BED[0]), n
