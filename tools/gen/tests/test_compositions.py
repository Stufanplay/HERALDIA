"""Two village pieces side by side (compositions.py): the audit finds a way into a pen that is in neither piece, as the
game's search and a villager's body take it, and stays quiet where one of them does not (measured on a server with
tools/probes/wcemetery.py: the raised trace and the haystack got villagers into the cemetery, the well's rim under its
roof did not)."""
import compositions as C
import ladders
from core import Template
from mediums import _paths as P


def pen(name="t/specials/pen"):
    """A walled 7 x 7 pen with nothing inside, its entrance on the north edge, no gate: the cemetery's shape."""
    t = Template(name)
    t.jigsaw(3, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty", final_state="stone")
    for x in range(7):
        for z in range(1, 8):
            t.set(x, 0, z, "stone")
            t.set(x, 1, z, "cobblestone_wall" if x in (0, 6) or z in (1, 7) else "air")
    return t


def yard(name="t/fillers/yard", block=None, roof=False):
    """A 7 x 7 yard of flat ground; with `block`, a one-high block on its east edge (a hay bale, a barrel...), and with
    `roof` a roof over it as the well's is over its rim: a villager stands on the block, its head under the roof."""
    t = Template(name)
    t.jigsaw(3, 0, 0, "north_up", "heraldia:entrance", "heraldia:side", "minecraft:empty", final_state="stone")
    for x in range(7):
        for z in range(1, 8):
            t.set(x, 0, z, "grass_block")
    if block:
        for z in (3, 4, 5):
            t.set(6, 1, z, block)
            if roof:
                t.set(6, 4, z, "spruce_planks")      # room to stand on the block (feet 2 + 1.95 < 4), not to
                t.set(5, 4, z, "spruce_planks")      # rise half a block more onto the wall's top
    return t


def test_the_pen_is_a_trap_behind_its_wall():
    floors, traps = C.profile(pen())
    assert 2.5 in traps                          # the top of its 1.5-high wall, at the entrance's level + 1
    assert all(f <= 1.0 for f in floors)         # nothing to step from on its own edge


def test_a_one_high_block_on_the_edge_is_a_way_in():
    profs = {lab: ("t", lab, *C.profile(t)) for lab, t in (("t/specials/pen", pen()),
                                                           ("t/fillers/yard", yard(block="hay_block[axis=y]")))}
    found = C.pairs(profs)
    assert [(a, f, b, top) for a, f, _, b, top, _ in found] == [("t/fillers/yard", 2.0, "t/specials/pen", 2.5)]


def test_flat_ground_or_a_roof_over_the_block_is_not():
    for t in (yard(), yard(block="hay_block[axis=y]", roof=True)):
        profs = {"t/specials/pen": ("t", "p", *C.profile(pen())), "t/fillers/yard": ("t", "y", *C.profile(t))}
        assert C.pairs(profs) == []


def test_a_slot_child_is_placed_a_cell_above_its_slot():
    """The plot and its trace, as `traces.plot` had them: the slot at the floor, so the trace's floor a block up."""
    host = yard("t/fillers/plot")
    host.jigsaw(0, 0, 1, "up_south", "heraldia:slot", "heraldia:bottom", "heraldia:t/traces", final_state="grass_block")
    child = Template("t/traces/x")
    for x in range(7):
        for z in range(7):
            child.set(x, 0, z, "coarse_dirt")
    child.jigsaw(0, 0, 0, "down_south", "heraldia:bottom", "heraldia:slot", "minecraft:empty", final_state="coarse_dirt")
    u = C.compose(host, host.jigsaws[1], child)
    assert u.get(3, 1, 4) == "minecraft:coarse_dirt" and u.get(3, 0, 4) == "minecraft:grass_block"
    profs = {"t/specials/pen": ("t", "p", *C.profile(pen())), "t/fillers/plot": ("t", "q", *C.profile(u))}
    assert [(f, top) for _, f, _, _, top, _ in C.pairs(profs)] == [(2.0, 2.5)]
    # the slot under the floor, as `traces.plot` has it now: the trace's floor takes the plot's
    host.jigsaws[1]["pos"] = (0, -1, 1)
    host.set(0, -1, 1, "jigsaw[orientation=up_south]", {"id": "minecraft:jigsaw", "final_state": "minecraft:dirt"})
    u = C.compose(host, host.jigsaws[1], child)
    profs["t/fillers/plot"] = ("t", "q", *C.profile(u))
    assert C.pairs(profs) == []


def test_the_build_audit_names_both_pieces_of_a_pair():
    """`issues` over a registry, as main.py runs it: one finding on each piece, none for pieces of another style."""
    from pack import Registry
    reg = Registry()
    reg.add(pen("t/specials/pen"), "special:cemetery")
    reg.add(yard("t/fillers/yard", block="barrel[facing=up]"), "filler")
    reg.add(yard("u/fillers/yard", block="barrel[facing=up]"), "filler")      # another style: never its neighbour
    reg.add(yard("t/fillers/flat"), "filler")
    found = C.issues(reg)
    assert sorted(found) == ["t/fillers/yard", "t/specials/pen"]
    assert all(m == C.MSG for iss in found.values() for m, _ in iss)
