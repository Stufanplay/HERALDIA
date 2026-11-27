"""The walled cemetery and the trace beside it, built on purpose: does a villager get in over the wall, and how often?

On a flat world, SITES copies of one composition: the style's cemetery (`specials/cemetery`) and, against its east wall,
the style's plot (`fillers/plot`) with a trace (`traces/<kind>`) on its slot, in one of three ways:
  raised  the trace where the game puts it: a jigsaw facing up places its child's jigsaw in the cell ABOVE it, so the
          trace's own floor (its y = 0) lands on the plot's y = 1, a block above the plot's ground (seen in a placed
          village: llanuras_castellana, the plot south of the cemetery). The wall's top is then half a block above it;
  flush   the trace with its floor on the plot's y = 0, as `traces.trace` meant it (the fix);
  none    the plot alone (control: no trace at all).
Or, with `--neighbour`, any template of the style in place of the plot (`--at`, `--rotation`), in variants `with` and
`none`; with `--ring`, the cemetery of a .jar that has its ring of ground (17 x 17). Each site gets `--villagers`
villagers on the plot, two cells from the wall (or at `--spawn`), and the server runs `--ticks` ticks at noon with the
clock stopped. A tick function tags every villager whose feet stand exactly on a wall's top (`walltop`) and every
villager inside a cemetery (`inside`), and leaves a marker where each first happened. At the end it prints, per
variant and counted BY PLACE (at that variant's sites, whoever's villagers they are): how many villagers are inside,
how many got in, how many stood on a wall top, and from which variant's row those inside came.

Two modes:
  wander  nitwits (no job, no POI to look for): only their idle strolls move them. Frequency of the trap.
  poi     unemployed villagers and a lectern INSIDE each cemetery, its only door a closed gate. A villager claims a
          job site only if its path search finds a way to it, so one that walks in shows the SEARCH planning a path
          over the wall, not a push. One villager per site, so no other villager can push it.

  python3 tools/probes/wcemetery.py <work> <jar> [--mode wander|poi] [--sites 8] [--villagers 3] [--ticks 12000]
                                                 [--style llanuras_castellana] [--kind cart] [--variants raised,flush,none]
                                                 [--neighbour fillers/haystack --at 13,0,21 --rotation 180 --spawn 11,1,19]
                                                 [--ring] [--high H] [--setblock 'dx,dy,dz,block;...']
Not a test, not run by CI (tools/probes/README.md).
"""
import argparse, json, os, queue, subprocess, sys, threading, time

REPO = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(REPO, "tools", "smoke"))
import server_smoke as s

Y = -60                  # the templates' y = 0, one above the flat world's grass, as in a placed village
SPACING = 48             # between sites: a villager strolls within 10 blocks, so no two sites share one
POI_SPACING = 112        # in poi mode: a villager looks for a job site within 48 blocks
TICK_RATE = 400
PLOT_AT = (15, 4)        # the plot's origin from the cemetery's: its x = 0 column against the east wall (x = 14;
                         # the cemetery's walls at x = 0, 14 and z = 1, 15, its gate at (7, 1, 1))
SHIFT = 0                # --ring: the cemetery with its ring of ground (17 x 17), everything a block further east


def sites(variants, n, spacing):
    out = []
    for i, v in enumerate(variants):
        for k in range(n):
            out.append((v, k * spacing, i * spacing))
    return out


def datapack(work, boxes, high=None):
    """A tick function that tags villagers on a wall top and inside a cemetery's walls."""
    root = os.path.join(work, "world", "datapacks", "probe")
    os.makedirs(os.path.join(root, "data", "probe", "function"), exist_ok=True)
    os.makedirs(os.path.join(root, "data", "minecraft", "tags", "function"), exist_ok=True)
    with open(os.path.join(root, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "wcemetery probe", "min_format": 121, "max_format": 121}}, f)
    # a marker where each first tag happened (tags mk_walltop, mk_inside): at the end their positions go to the server
    # log, so that what a count cannot say -- on which wall it stood, where it got in -- can be read
    # on a wall top: the feet exactly at the top of a wall (Y + 2.5, read as Pos[1] x 100) with a wall under them. Not
    # "the centre above a wall block": a wall is narrow, and a villager jumping beside one has its centre over the
    # wall's column with its feet at Y + 1.75 (seen: a first probe counted those)
    top = int(round((Y + 2.5) * 100))
    lines = ["execute as @e[type=minecraft:villager,tag=!walltop] store result score @s probe_y run data get entity @s Pos[1] 100",
             f"execute as @e[type=minecraft:villager,tag=!walltop,scores={{probe_y={top - 1}..{top + 1}}}] at @s "
             "if block ~ ~-0.6 ~ #minecraft:walls run function probe:walltop"]
    for x0, y0, z0, dx, dy, dz in boxes:
        lines.append(f"execute as @e[type=minecraft:villager,x={x0},y={y0},z={z0},dx={dx},dy={dy},dz={dz},tag=!inside] "
                     "run function probe:inside")
    if high is not None:
        # up high: the feet at Y + `high` or more (on top of what a trace or a neighbour piles up), once per villager
        lines.insert(0, "execute as @e[type=minecraft:villager] store result score @s probe_h run data get entity @s Pos[1] 100")
        lines.append(f"execute as @e[type=minecraft:villager,tag=!high,scores={{probe_h={int(round((Y + high) * 100))}..}}] "
                     "run function probe:high")
    for tag in ("walltop", "inside", "high"):
        with open(os.path.join(root, "data", "probe", "function", f"{tag}.mcfunction"), "w") as f:
            f.write(f"tag @s add {tag}\nexecute at @s run summon minecraft:marker ~ ~ ~ {{Tags:[\"mk_{tag}\"]}}\n")
    with open(os.path.join(root, "data", "probe", "function", "tick.mcfunction"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(root, "data", "minecraft", "tags", "function", "tick.json"), "w") as f:
        json.dump({"values": ["probe:tick"]}, f)


def interior(x, z):
    """The selector box (x, y, z, dx, dy, dz) of a cemetery's inside, cells x 1..13 and z 2..14. A selector's box runs
    from x to x + dx + 1 (the + 1 is the game's: a first probe missed it and counted villagers on the plot beside the
    wall) and is tested against the hitbox, so it stops 0.2 below the wall's top and 0.2 short of the wall's middle: a
    villager inside (feet at Y + 1) touches it, one standing on the wall (feet at Y + 2.5) or on the plot does not."""
    return (x + 1 + SHIFT, Y + 1, z + 2, 12, 0.3, 12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work"); ap.add_argument("jar")
    ap.add_argument("--mode", choices=("wander", "poi"), default="wander")
    ap.add_argument("--sites", type=int, default=8)
    ap.add_argument("--villagers", type=int, default=3)
    ap.add_argument("--ticks", type=int, default=12000)
    ap.add_argument("--style", default="llanuras_castellana")
    ap.add_argument("--kind", default="cart")
    ap.add_argument("--variants", default="raised,flush,none")
    ap.add_argument("--setblock", help="'dx,dy,dz,block;...' from the cemetery's origin, set after placing; in poi mode "
                                       "it replaces the lectern inside the cemetery (put the job site where you want it)")
    ap.add_argument("--ring", action="store_true", help="the .jar's cemetery has its ring of ground (17 x 17): the "
                    "wall, the gate and the plot a block further east; --at and --spawn are given as they are")
    ap.add_argument("--high", type=float, help="also count villagers whose feet get to Y + HIGH or more (tag high)")
    ap.add_argument("--neighbour", help="instead of the plot: this template of the style (e.g. fillers/well), in variants "
                                        "'with' (placed) and 'none' (left out)")
    ap.add_argument("--at", default="10,0,22", help="the neighbour's placing position from the cemetery's origin")
    ap.add_argument("--rotation", default="180", help="its rotation (/place template: none, clockwise_90, 180, ...)")
    ap.add_argument("--spawn", default="7,1,19", help="where the villagers stand, from the cemetery's origin (feet)")
    a = ap.parse_args()
    global SHIFT
    SHIFT = 1 if a.ring else 0
    work, jar = os.path.abspath(a.work), os.path.abspath(a.jar)
    variants = a.variants.split(",")
    per = 1 if a.mode == "poi" else a.villagers
    layout = sites(variants, a.sites, POI_SPACING if a.mode == "poi" else SPACING)
    launcher = s.prepare(work, jar, s.gradle_properties())
    with open(os.path.join(work, "server.properties"), "a") as f:
        # no vanilla village: a flat world has them, and a villager that strolls 150 blocks off takes a job there
        f.write("level-type=minecraft:flat\ngenerate-structures=false\n")
    datapack(work, [interior(x, z) for _, x, z in layout], a.high)
    proc = subprocess.Popen(["java", "-Xmx3G", "-jar", launcher, "nogui"], cwd=work, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, seen = queue.Queue(), []
    threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout] and lines.put(None), daemon=True).start()
    ctx = s.Context(proc, lines, seen)
    try:
        s.wait_for(lines, r"Heraldia: (\d+) estructuras registradas", s.START_TIMEOUT_S, seen)
        for cmd in ("scoreboard objectives add probe_y dummy", "scoreboard objectives add probe_h dummy", "gamerule advance_time false", "gamerule advance_weather false", "gamerule spawn_mobs false",
                    "time set noon"):
            ctx.run(cmd, r"Game rule|to time|Set the time|Created new objective")
        for _, x, z in layout:          # one box per site: a single box over all of them passes forceload's 256 chunks
            ctx.must(f"forceload add {x - 16} {z - 16} {x + 40} {z + 32}", r"Marked|Added|already")
        ctx.run("datapack list", r"available|enabled")
        st = a.style
        for v, x, z in layout:
            ctx.must(f"place template heraldia:{st}/specials/cemetery {x} {Y} {z}", r"Loaded template|placed")
            px, pz = x + PLOT_AT[0] + 2 * SHIFT, z + PLOT_AT[1]
            if a.neighbour:
                if v != "none":
                    nx, ny, nz = (int(c) for c in a.at.split(","))
                    ctx.must(f"place template heraldia:{st}/{a.neighbour} {x + nx} {Y + ny} {z + nz} {a.rotation}",
                             r"Loaded template|placed")
            else:
                ctx.must(f"place template heraldia:{st}/fillers/plot {px} {Y} {pz}", r"Loaded template|placed")
            if not a.neighbour and v != "none":
                ty = Y + 1 if v == "raised" else Y
                ctx.must(f"place template heraldia:{st}/traces/{a.kind} {px} {ty} {pz + 1}", r"Loaded template|placed")
            # the cemetery's wall is still there, and so is its shut gate (the probe measures the composition, not a hole)
            for c in ((x + 14 + SHIFT, Y + 1, z + 8), (x + 7 + SHIFT, Y + 1, z + 15)):
                if not ctx.block(c, "#minecraft:walls"):
                    raise SystemExit(f"no wall at {c}: the composition is not the one meant")
            if not ctx.block((x + 7 + SHIFT, Y + 1, z + 1), "#minecraft:fence_gates[open=false]"):
                raise SystemExit(f"the gate at {(x + 7 + SHIFT, Y + 1, z + 1)} is not a shut gate")
            for item in (a.setblock.split(";") if a.setblock else ()):
                dx, dy, dz, blk = item.split(",", 3)
                ctx.must(f"setblock {x + int(dx)} {Y + int(dy)} {z + int(dz)} minecraft:{blk}", r"Changed|changed")
            if a.mode == "poi" and not a.setblock:
                ctx.must(f"setblock {x + 7 + SHIFT} {Y + 1} {z + 8} minecraft:lectern[facing=north]", r"Changed|changed")
            fy = Y + (2 if v == "raised" else 1)        # the feet on the plot (on the trace's floor when raised)
            prof = "minecraft:none" if a.mode == "poi" else "minecraft:nitwit"
            if a.neighbour:
                sx_, sy_, sz_ = (float(c) for c in a.spawn.split(","))
                fy = Y + sy_ if v != "none" else Y
            for k in range(per):
                vx, vz = px + 2 + (k % 3), pz + 3 + (k // 3) * 2
                if a.neighbour:
                    vx, vz = int(x + sx_) + (k % 3) - 1, int(z + sz_)
                ctx.must(f"summon minecraft:villager {vx + 0.5} {fy} {vz + 0.5} {{VillagerData:{{profession:\"{prof}\","
                         f"level:1,type:\"minecraft:plains\"}},PersistenceRequired:1b,Tags:[\"probe\",\"v_{v}\"]}}",
                         r"Summoned")
        total = ctx.count("@e[type=minecraft:villager,tag=probe]")
        if total != per * len(layout):
            raise SystemExit(f"{total} villagers summoned, {per * len(layout)} meant")
        ctx.run(f"tick rate {TICK_RATE}", r"rate|Set|set")
        t0, end = time.monotonic(), ctx.gametime() + a.ticks
        while ctx.gametime() < end:             # not ctx.ticks: it sleeps n / 20 s whatever the tick rate
            if time.monotonic() - t0 > 7200:
                raise SystemExit(f"the server did not run {a.ticks} ticks in 2 h")
            time.sleep(2)
        ctx.run("tick rate 20", r"rate|Set|set")
        print(f"ran {a.ticks} ticks in {time.monotonic() - t0:.0f} s", flush=True)
        res = {}

        def at_sites(v, sel, box):
            return sum(ctx.count(f"@e[{sel},x={b[0]},y={b[1]},z={b[2]},dx={b[3]},dy={b[4]},dz={b[5]}]")
                       for (vv, x, z) in layout if vv == v for b in [box(x, z)])
        # Counted BY PLACE, at the sites of each variant: a villager strolls 48 blocks and more (seen: villagers of the
        # flush and none rows walked to a raised site and got in there), so a count by the villager's own tag mixes the
        # variants. `from_*` says whose villagers are inside each variant's cemeteries at the end.
        site_box = lambda x, z: (x - 1, Y - 1, z, 23, 6, 16)
        for v in variants:
            res[v] = dict(inside_now=at_sites(v, "type=minecraft:villager", interior),
                          got_in=at_sites(v, "type=minecraft:marker,tag=mk_inside", site_box),
                          on_wall_top=at_sites(v, "type=minecraft:marker,tag=mk_walltop", site_box))
            if a.high is not None:
                res[v]["up_high"] = at_sites(v, "type=minecraft:marker,tag=mk_high", site_box)
            for w in variants:
                res[v][f"from_{w}"] = at_sites(v, f"type=minecraft:villager,tag=v_{w}", interior)
            sel = f"type=minecraft:villager,tag=v_{v}"
            if a.mode == "poi":
                res[v]["job_site_set"] = ctx.count(f"@e[{sel},nbt={{Brain:{{memories:{{\"minecraft:job_site\":{{}}}}}}}}]")
                res[v]["librarian"] = ctx.count(f"@e[{sel},nbt={{VillagerData:{{profession:\"minecraft:librarian\"}}}}]")
            print(v, json.dumps(res[v]), flush=True)
        for tag in ("walltop", "inside", "high"):
            s.send(proc, f"execute as @e[type=minecraft:marker,tag=mk_{tag}] run data get entity @s Pos")
        time.sleep(3)
        if a.mode == "poi":
            # each villager's position and memories, for the server log (logs/latest.log): what a count cannot say
            for v in variants:
                s.send(proc, f"execute as @e[type=minecraft:villager,tag=v_{v}] run data get entity @s Pos")
                s.send(proc, f"execute as @e[type=minecraft:villager,tag=v_{v}] run data get entity @s Brain.memories")
            time.sleep(3)
        print("RESULT " + json.dumps(dict(mode=a.mode, style=a.style, kind=a.kind, sites=a.sites, per_site=per,
                                          ticks=a.ticks, variants=res)), flush=True)
    finally:
        s.send(proc, "stop")
        proc.wait(timeout=120)


if __name__ == "__main__":
    main()
