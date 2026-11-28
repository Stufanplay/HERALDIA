"""Safe updates (T46), path B and undo, on a real dedicated 26.3 server: /heraldia update apply places NEW Heraldia
structures in already generated chunks and /heraldia update undo takes them away again.

Usage: python3 tools/smoke/update_path_b.py --jar build/libs/heraldia-X.jar [--work build/smoke-actualizar-b]
update.py only exercises path A (regenerating pristine chunks): its zone has no path-B candidates. Here, five starts of the
same world (smoke-test seed, no new mobs or random ticks, nobody nearby: InhabitedTime 0):
0. With the default content, /locate finds the medium structure (#heraldia:medianas) closest to each of ORIGINS and its start chunk
   is generated: its box (the pieces saved in the start) aims the zone. The world is then deleted.
1. Medium structures turned off (medianas.activadas false, as in a world made before they existed): the zone around the box
   is generated and a small "house" (bed and crafting table, in the air) is put east of the box, HOUSE_GAP blocks past its
   chunks: its 50-block margin protects the column of chunks next to the box, but no chunk of the box. The box chunks
   next to that column are then not pristine ("beside" a protected chunk, Detector), so the start is not regenerated
   (path A would leave the structure cut) but placed by path B.
2. Medium structures back on. analyze reports >= 1 new structure to place (path B), the located one among them, and
   changes nothing; apply (console), confirm with backup: the server stops by itself. The test copies the zone's region,
   entity and POI files.
3. On starting: "apply terminado" with every placement placed and none skipped. For each placement of the plan: its start
   is saved in the start chunk (structures.starts, with the plan's box), the saved chunks of its box reference it, blocks
   changed in its box and the game sees it (location_check predicate at the start piece). No chunk within the 50-block
   margin of the house changed and nothing outside the plan (boxes, regenerated chunks and their neighbours) changed. Then
   undo (console) + confirm: the server stops by itself.
4. On starting: "undo: restaurados"; the zone's region, entity and POI files are byte-equal to the copy made before apply
   (and the chunks NBT-equal), the starts and references of the placed structures are gone and the predicate fails.
Exit code 0 if everything passes.
"""
import argparse, glob, json, math, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s                       # noqa: E402
import existing_world as me                   # noqa: E402
import update as up                           # noqa: E402

# /locate from these points (far from spawn and from the 12 village cells, within ~3,000 blocks of 0,0) until a medium
# structure has no other structure in the chunks of its box: path B does not place where the box overlaps, in plan view,
# the pieces of a saved structure (Detector.placeable), and vanilla mineshafts and trial chambers are underground almost everywhere.
ORIGINS = [(4000, 4000), (4000, -4000), (-4000, 4000), (-4000, -4000), (5000, 0), (0, 5000), (-5000, 0), (0, -5000),
           (6000, 6000), (6000, -6000), (-6000, 6000), (-6000, -6000)]
HOUSE_GAP = 57               # blocks from the box's last chunk to the house: <= 50 to the next column, > 50 to the box
HOUSE_Y = 150                # the house, in the air
MARGIN = 50
RING = 3                     # chunks generated around the box (and around the house's protected chunks)
CONFIG_ON = json.loads(json.dumps(s.TEST_CONFIG))
CONFIG_OFF = json.loads(json.dumps(s.TEST_CONFIG)) | {"medianas": {"activadas": False}}
FOLDERS = ("region", "entities", "poi")


def overworld(world):
    for base in (os.path.join(world, "dimensions", "minecraft", "overworld"), world):
        if os.path.isdir(os.path.join(base, "region")):
            return base
    raise SystemExit(f"no overworld region folder in {world}")


def regions_of(chunks):
    return sorted({f"r.{cx >> 5}.{cz >> 5}.mca" for cx, cz in chunks})


def copy_regions(world, names, dest):
    shutil.rmtree(dest, ignore_errors=True)
    ow = overworld(world)
    for folder in FOLDERS:
        os.makedirs(os.path.join(dest, folder), exist_ok=True)
        for n in names:
            p = os.path.join(ow, folder, n)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(dest, folder, n))


def byte_differences(world, names, dest):
    """Files (folder/name) that differ between the world and the copy (missing on one side included)."""
    ow, out = overworld(world), []
    for folder in FOLDERS:
        for n in names:
            a, b = os.path.join(ow, folder, n), os.path.join(dest, folder, n)
            if os.path.isfile(a) != os.path.isfile(b):
                out.append(f"{folder}/{n} {'falta' if os.path.isfile(b) else 'sobra'}")
            elif os.path.isfile(a):
                with open(a, "rb") as fa, open(b, "rb") as fb:
                    if fa.read() != fb.read():
                        out.append(f"{folder}/{n} distinto")
    return out


def box_chunks(box):
    return {(cx, cz) for cx in range(box[0] >> 4, (box[3] >> 4) + 1) for cz in range(box[2] >> 4, (box[5] >> 4) + 1)}


def near_house(house, cx, cz):
    dx = max(0, house[0] - (cx * 16 + 15), cx * 16 - house[3])
    dz = max(0, house[2] - (cz * 16 + 15), cz * 16 - house[5])
    return math.hypot(dx, dz) <= MARGIN


def structures(world, cx, cz):
    """(starts {id: nbt}, references {id: [packed longs]}) saved in the chunk, or (None, None) if it is not saved."""
    n = me.read_chunk(world, cx, cz)
    if n is None:
        return None, None
    st = n.get("structures") or {}
    starts = {str(k): v for k, v in (st.get("starts") or {}).items() if str(v.get("id", "INVALID")) != "INVALID"}
    refs = {str(k): [int(x) for x in v] for k, v in (st.get("References") or {}).items()}
    return starts, refs


def packed(cx, cz):
    """ChunkPos.pack (the long of a structure reference), signed as NBT stores it."""
    v = (cx & 0xFFFFFFFF) | ((cz & 0xFFFFFFFF) << 32)
    return v - (1 << 64) if v >= 1 << 63 else v


def start_piece_center(start):
    ch = start.get("Children") or []
    if not ch:
        return None
    bb = [int(x) for x in ch[0]["BB"]]
    return (bb[0] + bb[3]) // 2, (bb[1] + bb[4]) // 2, (bb[2] + bb[5]) // 2


def in_structure(ctx, sid, x, y, z):
    """Does the game see block x y z inside a piece of structure sid? (location_check, which uses the chunk's references)"""
    pred = f'{{type:"minecraft:location_check",predicate:{{structures:"{sid}"}}}}'
    m = up.with_chunk(ctx, x, z, lambda: ctx.run(f"execute positioned {x} {y} {z} if predicate {pred}", r"Test passed|Test failed"))
    if not m.group(0).startswith("Test "):           # a parse error must not pass for "not there" after undo
        raise SystemExit(f"the location_check predicate does not run: {m.string.strip()}")
    return m.group(0) == "Test passed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-actualizar-b"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    world = os.path.join(a.work, "world")
    folder = os.path.join(world, "heraldia", "actualizar")
    copy_dir = os.path.join(a.work, "antes-de-apply")
    fails, t_all = [], time.time()

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print("FAIL:", msg)
        return cond

    # ------------------------------------------------------------------ start 0: aim the zone
    t0 = time.time()
    proc, ctx = me.start_up(a.work, launcher, CONFIG_ON)
    try:
        found = None
        for ox, oz in ORIGINS:
            m = ctx.run(f"execute positioned {ox} 64 {oz} run locate structure #heraldia:medianas",
                        r"\((heraldia:[^)]+)\) is at \[(-?\d+), [^,]+, (-?\d+)\]|Could not find")
            if not m.lastindex:
                continue
            sid, sx, sz = m.group(1), int(m.group(2)), int(m.group(3))
            scx, scz = sx >> 4, sz >> 4
            up.with_chunk(ctx, sx, sz, lambda: ctx.run("save-all flush", r"Saved the game|saved"))
            st = (structures(world, scx, scz)[0] or {}).get(sid)
            if st is None:
                print(f"{sid} located at {sx}, {sz} but not saved in chunk {scx}, {scz}")
                continue
            bbs = [[int(x) for x in ch["BB"]] for ch in st["Children"]]
            box = [min(b[i] for b in bbs) for i in range(3)] + [max(b[i] for b in bbs) for i in range(3, 6)]
            for x0, z0, x1, z1 in me.fragments(box_chunks(box)):
                ctx.run(f"forceload add {x0} {z0} {x1} {z1}", r"Marked|[Aa]dded|force|already")
            for cx, cz in sorted(box_chunks(box)):
                ctx.until(f"execute if loaded {cx * 16} 64 {cz * 16}", timeout=300)
            ctx.run("save-all flush", r"Saved the game|saved")
            ctx.run("forceload remove all", r"[Rr]emoved|[Uu]nmarked|force")
            others = set()
            for c in box_chunks(box):
                starts, refs = structures(world, *c)
                others |= (set(starts or {}) | set(refs or {})) - {sid}
            print(f"candidate {sid} at {sx}, {sz}, box {box}: other structures in its chunks: {sorted(others)}")
            if not others:
                found = sid, sx, sz, box
                break
        if not found:
            raise SystemExit(f"no medium structure near {ORIGINS} without other structures in the chunks of its box")
        sid, sx, sz, box = found
    finally:
        me.halt(proc, ctx)
    scx, scz = sx >> 4, sz >> 4
    B = box_chunks(box)
    east = ((box[3] >> 4) + 1) * 16                       # first block east of the box's chunks
    hz = scz * 16 + 8
    house = (east + HOUSE_GAP, HOUSE_Y, hz, east + HOUSE_GAP + 1, HOUSE_Y, hz + 1)
    bx0, bz0, bx1, bz1 = min(c[0] for c in B), min(c[1] for c in B), max(c[0] for c in B), max(c[1] for c in B)
    zone = {(x, z) for x in range(bx0 - RING, (house[3] + MARGIN >> 4) + RING + 1) for z in range(bz0 - RING, bz1 + RING + 1)}
    zone |= {(x, z) for x in range(bx0 - RING, (house[3] + MARGIN >> 4) + RING + 1)
             for z in range((hz - MARGIN >> 4) - RING, (hz + MARGIN >> 4) + RING + 1)}
    protected = {c for c in zone if near_house(house, *c)}
    beside = {c for c in B if any((c[0] + dx, c[1] + dz) in protected for dx in (-1, 0, 1) for dz in (-1, 0, 1))}
    print(f"start 0 ({time.time() - t0:.0f} s): {sid} at {sx}, {sz} (chunk {scx}, {scz}), box {box} ({len(B)} chunks); "
          f"zone of {len(zone)} chunks, {len(protected)} within {MARGIN} blocks of the house at {house[0]}, {house[2]}; "
          f"box chunks beside them: {sorted(beside)}")
    if B & protected or not beside:
        raise SystemExit(f"the house does not protect a chunk next to the box without protecting the box: {sorted(B & protected)}")
    shutil.rmtree(world)

    # ------------------------------------------------------------------ start 1: generated without medium structures
    t0 = time.time()
    proc, ctx = me.start_up(a.work, launcher, CONFIG_OFF)
    try:
        ctx.run("gamerule advance_time false", r"Gamerule|set to")
        me.load_data(ctx, zone)
        x0, y, z0, x1, _, z1 = house
        up.with_chunk(ctx, x0, z0, lambda: [
            ctx.run(f"setblock {x0} {y} {z0} minecraft:red_bed[facing=south,part=foot]", r"Changed the block|Could not"),
            ctx.run(f"setblock {x0} {y} {z0 + 1} minecraft:red_bed[facing=south,part=head]", r"Changed the block|Could not"),
            ctx.run(f"setblock {x1} {y} {z0} minecraft:crafting_table", r"Changed the block|Could not")])
    finally:
        me.halt(proc, ctx)
    before = up.snapshot(world, zone)
    print(f"start 1 ({time.time() - t0:.0f} s): {len(before)} of {len(zone)} chunks fully saved")
    check(len(before) == len(zone), f"only {len(before)} of {len(zone)} chunks of the zone fully saved")
    s_before, _ = structures(world, scx, scz)
    check(s_before is not None and sid not in s_before, f"{sid} already in chunk {scx}, {scz} with medium structures off")

    # ------------------------------------------------------------------ start 2: analyze and apply
    t0 = time.time()
    proc, ctx = me.start_up(a.work, launcher, CONFIG_ON)
    try:
        me.freeze(ctx)
        n0 = len(ctx.seen)
        ctx.run("heraldia update analyze", r"Analizando|Analysing")
        m = up.wait_since(ctx, n0, r"update analyze: (\d+) chunks, (\d+) construcciones, (\d+) protegidos, (\d+) vírgenes \((\d+) se "
                          r"regenerarían\), (\d+) estructuras nuevas que colocar \((\d+) sin sitio seguro\)", 600)
        total, built, prot, virg, regen, new, unsafe = (int(m.group(i)) for i in range(1, 8))
        print(f"analyze: {total} chunks, {built} builds, {prot} protected, {virg} pristine ({regen} to regenerate), "
              f"{new} new structures to place ({unsafe} without a safe spot)")
        check(new >= 1, "analyze proposes no new structure to place (path B)")
        reports = sorted(glob.glob(os.path.join(folder, "analisis-*.txt")))
        listed = re.findall(r"^  (heraldia:\S+) @ chunk (-?\d+),(-?\d+)", open(reports[-1], encoding="utf-8").read(), re.M) if reports else []
        print("placements in the report:", listed)
        check((sid, str(scx), str(scz)) in listed, f"the located {sid} at chunk {scx}, {scz} is not among the placements")
        check(len(listed) == new, f"the report lists {len(listed)} placements, the log says {new}")
        ctx.run("save-all flush", r"Saved the game|saved")
        diff = me.compare("analyze", before, up.snapshot(world, zone))
        check(not diff, "analyze changed chunks: " + "; ".join(diff[:3]))
        n0 = len(ctx.seen)
        ctx.run("heraldia update apply", r"Analizando|Analysing")
        ident = up.wait_since(ctx, n0, r"update apply confirm (\w+) backup", 600).group(1)
        s.send(proc, f"heraldia update apply confirm {ident} backup")
        up.wait_since(ctx, n0, r"update apply confirmado .*el servidor se para", 60)
        proc.wait(timeout=180)
        print("the server stopped by itself after confirming apply")
    finally:
        if proc.poll() is None:
            proc.kill()
    with open(os.path.join(folder, "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    placements = [(p["estructura"], p["cx"], p["cz"], p["caja"]) for p in plan["colocar"]]
    regenerate = {(c["cx"], c["cz"]) for c in plan["regenerar"]}
    check(placements, "the confirmed plan has no structure to place")
    pre = up.snapshot(world, zone)
    names = regions_of(zone | {c for p in placements for c in box_chunks(p[3])})
    copy_regions(world, names, copy_dir)
    print(f"start 2 ({time.time() - t0:.0f} s): plan {ident} with {len(placements)} placements, {len(regenerate)} chunks "
          f"to regenerate; copied {names}")
    in_boxes = {c for p in placements for c in box_chunks(p[3])}
    check(not in_boxes & protected, f"a placement box touches the house's protected chunks: {sorted(in_boxes & protected)}")

    # ------------------------------------------------------------------ start 3: apply done; undo
    t0 = time.time()
    proc, ctx = me.start_up(a.work, launcher, CONFIG_ON)
    try:
        m = up.wait(ctx, r"update apply terminado: (\d+) chunks regenerables, (\d+) dejados, (\d+) estructuras colocadas, "
                         r"(\d+) omitidas", 300)
        placed, skipped = int(m.group(3)), int(m.group(4))
        print(f"apply: {placed} structures placed, {skipped} skipped, {m.group(1)} chunks deleted to regenerate")
        check(placed == len(placements) and skipped == 0, f"apply placed {placed} and skipped {skipped} of {len(placements)}")
        log3 = ctx.log()
        for sid_, cx, cz, _ in placements:
            check(f"colocada {sid_} en el chunk {cx}, {cz}" in log3, f"the log does not say {sid_} was placed at {cx}, {cz}")
        me.freeze(ctx)
        ctx.run("save-all flush", r"Saved the game|saved")
        after = up.snapshot(world, zone)
        centres = {}
        changed = {c for c in zone if c in pre and c in after and me.differences(pre[c], after[c])}
        for sid_, cx, cz, box in placements:
            starts, _ = structures(world, cx, cz)
            st = (starts or {}).get(sid_)
            if not check(st is not None, f"{sid_}: no start saved in chunk {cx}, {cz}"):
                continue
            bbs = [[int(x) for x in ch["BB"]] for ch in st.get("Children", [])]
            u = [min(b[i] for b in bbs) for i in range(3)] + [max(b[i] for b in bbs) for i in range(3, 6)] if bbs else None
            check(u is not None and (u[0], u[2], u[3], u[5]) == (box[0], box[2], box[3], box[5]),
                  f"{sid_}: saved pieces {u} do not match the plan's box {box}")
            missing = []
            for c in sorted(box_chunks(box)):
                _, refs = structures(world, *c)
                if refs is not None and packed(cx, cz) not in refs.get(sid_, []):
                    missing.append(c)
            check(not missing, f"{sid_}: generated chunks of its box without a reference to it: {missing}")
            check(changed & box_chunks(box), f"{sid_}: no block changed in the chunks of its box {sorted(box_chunks(box))}")
            centre = centres[sid_, cx, cz] = start_piece_center(st)
            check(centre and in_structure(ctx, sid_, *centre), f"{sid_}: location_check does not see it at {centre}")
            print(f"{sid_} at chunk {cx}, {cz}: box {box}, {len(changed & box_chunks(box))} chunks changed, start piece at {centre}")
        allowed = in_boxes | regenerate | {(x + dx, z + dz) for x, z in regenerate for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
        diff = me.compare("apply (protected)", {c: pre[c] for c in protected if c in pre}, after)
        check(not diff, f"apply changed chunks within {MARGIN} blocks of the house: " + "; ".join(diff[:3]))
        diff = me.compare("apply (outside the plan)", {c: pre[c] for c in zone - allowed if c in pre}, after)
        check(not diff, "apply changed chunks outside the plan: " + "; ".join(diff[:3]))
        print(f"apply: {len(changed)} chunks of the zone changed, {len(changed - allowed)} outside the plan")
        n0 = len(ctx.seen)
        ctx.run("heraldia update undo", r"update undo confirm|No hay")
        m = re.search(r"update undo confirm (\w+)", "".join(ctx.seen[n0:]))
        check(m and m.group(1) == ident, f"undo does not offer the plan {ident}: {m and m.group(0)}")
        s.send(proc, f"heraldia update undo confirm {ident}")
        up.wait_since(ctx, n0, rf"update undo {ident} confirmado .*el servidor se para", 60)
        proc.wait(timeout=180)
        print("the server stopped by itself after confirming undo")
    finally:
        if proc.poll() is None:
            proc.kill()
    print(f"start 3: {time.time() - t0:.0f} s")

    # ------------------------------------------------------------------ start 4: undone
    t0 = time.time()
    proc, ctx = me.start_up(a.work, launcher, CONFIG_ON)
    try:
        m = up.wait(ctx, r"update undo: restaurados (\d+) ficheros", 120)
        print(f"undo: {m.group(1)} files restored")
        # the zone is far from the spawn: nothing has loaded it yet
        diff = byte_differences(world, names, copy_dir)
        check(not diff, "after undo the files differ from before apply: " + ", ".join(diff[:6]))
        diff = me.compare("undo", pre, up.snapshot(world, zone))
        check(not diff, "after undo chunks differ from before apply: " + "; ".join(diff[:3]))
        check(os.path.exists(os.path.join(folder, f"deshecho-{ident}.json")) and not os.path.exists(os.path.join(folder, "deshacer.json")),
              "the undo plan was not left as done (deshecho-<id>.json)")
        for sid_, cx, cz, box in placements:
            starts, _ = structures(world, cx, cz)
            check(starts is not None and sid_ not in starts, f"{sid_}: its start is still in chunk {cx}, {cz} after undo")
            left = [c for c in sorted(box_chunks(box)) if packed(cx, cz) in (structures(world, *c)[1] or {}).get(sid_, [])]
            check(not left, f"{sid_}: references to it remain after undo in {left}")
        me.freeze(ctx)
        for (sid_, cx, cz), centre in centres.items():
            check(not (centre and in_structure(ctx, sid_, *centre)), f"{sid_}: location_check still sees it at {centre} after undo")
        me.halt(proc, ctx)
    finally:
        if proc.poll() is None:
            proc.kill()
    print(f"start 4: {time.time() - t0:.0f} s; total {time.time() - t_all:.0f} s")
    if fails:
        print(f"{len(fails)} fallos")
        return 1
    print("update path B: all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
