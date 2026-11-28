"""Wayfarers on the roads (the caravans' engine) on a real 26.3 dedicated server; complements WayfarersTest and WayfarerOptionsTest.

Usage: python3 tools/smoke/wayfarers.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke-viajeros"
In the battery it runs inside tools/smoke/caravans.py (`scenario`, in its first start: the same server and corridor, no group of its
own in CI); this file is in NOT_TESTS of tools/test.py and its main() is for running it alone.
Deterministic: the seed and the minimal grid of villages from roads.py (the same route on dry land as caravans.py), both rolls
turned off (caravanas.frecuencia = viajeros.frecuencia = 0: they only appear with the command) and a Carpet simulated player
next to the road, in the corridor of generated chunks. One start:
  1. /heraldia caravan wayfarer <kind> for each kind: it appears with its entities (the shepherd's sheep, the second guard,
     the hunter's tame wolf owned by the hunter), with its trades or none, it walks along the road, `list` shows it and a
     second one is refused (one at a time). The pilgrim only if a monastery or cathedral spawns within 3,000 blocks (it
     says so otherwise).
  2. Endings: the player moves away (dismissed, every entity removed); it is moved to the end of its stretch with the
     player beside it (it lingers in sight and is removed when the player leaves); the player hurts a guard (reputation
     with the village of origin drops once, the other guard turns on the player); the player kills the hunter (the
     encounter is lost, the dog is removed, nothing on the ground); `clear` removes the rest.
  3. A stray wayfarer entity (a sheep with the tags) is removed on load; a kind switched off and the general switch off
     with /heraldia reload: the command refuses, the one on the road leaves and /heraldia status says so.
"""
import argparse, json, math, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
import village_terrain as at
import importlib.util
from terralith_biomes import fetch
from trophies import CARPET

# the caravans' test by its path: plain "caravans" is the generator module (tools/gen, in sys.path)
_spec = importlib.util.spec_from_file_location("caravans_smoke", os.path.join(os.path.dirname(os.path.abspath(__file__)), "caravans.py"))
cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cv)

PLAYER = cv.PLAYER
TAG, LEADER, SHEEP, DOG, PARTNER = ("heraldia_caravana", "heraldia_caravana.viajero", "heraldia_caravana.oveja",
                                    "heraldia_caravana.perro", "heraldia_caravana.pareja")
KINDS = {"pilgrim": "peregrino", "shepherd": "pastor", "messenger": "mensajero", "patrol": "guardias", "hunter": "cazador"}
DEPARTS = re.compile(r"viajeros: sale (\w+) (\d+) de (.+?) hacia (.+?): (\d+) vértices \((\d+) bloques\) desde (-?\d+) (-?\d+) (-?\d+) "
                     r"hasta (-?\d+) (-?\d+), zona (\w+), (\d+) entidades(?:, camino de (\S+) en (-?\d+) (-?\d+))?")
NONE = r"There is no Heraldia road|No hay ningún camino|no monastery or cathedral|ningún monasterio ni catedral"


def configure(work, extra=None):
    cfg = {"aldeas": {"separacion_bloques": cv.cabin_adv.GRID, "maximo": 100}, "caravanas": {"frecuencia": 0}, "viajeros": {"frecuencia": 0}}
    for k, v in (extra or {}).items():
        cfg.setdefault(k, {}).update(v)
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def new_one(ctx, fails, route, kind, required=True):
    """The player next to the road and /heraldia caravan wayfarer <kind>: its log line and its vertices (None if it did not set off)."""
    a, b, _ = route
    for t in (0.5, 0.44, 0.56, 0.38, 0.62):
        x, z = cv.point(a, b, t)
        cv.on_floor(ctx, PLAYER, x, z)
        ctx.ticks(10)
        m = cv.as_player(ctx, f"heraldia caravan wayfarer {kind}", rf"{DEPARTS.pattern}|{NONE}|already \d+ wayfarers|Ya hay \d+ viajeros")
        if m.group(1):
            v = s.wait_for(ctx.lines, rf"viajeros: vértices de {m.group(2)}: (.*)", s.COMMAND_TIMEOUT_S, ctx.seen)
            w = {"kind": m.group(1), "id": m.group(2), "origen": m.group(3), "destino": m.group(4), "n": int(m.group(5)),
                 "zona": m.group(12), "entidades": int(m.group(13)), "santuario": m.group(14),
                 "vertices": [tuple(int(n) for n in p.split()) for p in v.group(1).strip().split("; ")]}
            print(f"{kind} {w['id']}: from {w['origen']} towards {w['destino']}, {w['n']} vertices, zone {w['zona']}, "
                  f"{w['entidades']} entities{', to ' + w['santuario'] if w['santuario'] else ''}")
            return w
        if re.search(r"monastery|monasterio", m.group(0)):
            print(f"{kind}: {m.group(0).strip()[-110:]}")
            if not required:
                return None
        print(f"no {kind} near {x} {z} (t = {t}): {m.group(0).strip()[-90:]}")
    if required:
        fails.append(f"/heraldia caravan wayfarer {kind}: nobody sets off next to the road")
    return None


def ends(ctx, w, mark):
    return cv.wait(ctx, rf"viajeros: termina {w['kind']} {w['id']}: (\w+) \((\d+) entidades quitadas, \d+ s en camino(, \d+ s más a la vista)?\)", mark)


def check_party(ctx, fails, w, walk=300):
    kind = w["kind"]
    lead = f"@e[tag={LEADER}.{kind}]"
    if ctx.count(lead) != 1:
        fails.append(f"{kind}: {ctx.count(lead)} leaders (should be 1)")
    total = ctx.count(f"@e[tag={TAG}]")
    if total != w["entidades"]:
        fails.append(f"{kind}: {total} entities in the world, the log says {w['entidades']}")
    expected = {"peregrino": (1, 1), "mensajero": (1, 1), "guardias": (2, 2), "cazador": (2, 2), "pastor": (4, 6)}[kind]
    if not expected[0] <= total <= expected[1]:
        fails.append(f"{kind}: {total} entities (should be {expected[0]}-{expected[1]})")
    if kind == "pastor" and ctx.count(f"@e[tag={SHEEP},type=minecraft:sheep]") != total - 1:
        fails.append("the shepherd's sheep do not match")
    if kind == "guardias" and ctx.count(f"@e[tag={TAG},type=minecraft:iron_golem]") != 2:
        fails.append("the patrol is not two iron golems")
    if kind == "cazador":
        if ctx.count(f"@e[tag={DOG},type=minecraft:wolf]") != 1:
            fails.append("the hunter has no dog")
        owner = ctx.run(f"data get entity @e[tag={DOG},limit=1] Owner", r"has the following entity data: (.+)|Found no elements|No entity")
        uuid = ctx.run(f"data get entity {lead[:-1]},limit=1] UUID", r"has the following entity data: (.+)|No entity")
        print(f"the dog's owner: {owner.group(1)}; the hunter: {uuid.group(1)}")
        if not owner.group(1) or owner.group(1).strip() != (uuid.group(1) or "").strip():
            fails.append("the hunter's wolf is not tame with the hunter as its owner")
    if kind != "guardias":
        offers = ctx.run(f"data get entity {lead[:-1]},limit=1] Offers", r"has the following entity data: (.+)|Found no elements|No entity")
        text = offers.group(1) or ""
        sells = kind in ("pastor", "cazador")
        print(f"{kind} offers: {text[:160]}")
        if sells != ("emerald" in text):
            fails.append(f"{kind}: {'no' if sells else 'some'} trades ({text[:80]})")
        if kind == "pastor" and "wool" not in text:
            fails.append("the shepherd does not sell wool")
        if "netherite" in text or "elytra" in text or "enchant" in text:
            fails.append(f"{kind}: a trade breaks the progression")
    # it walks along the road towards the end
    finish = w["vertices"][-1]
    p0 = ctx.pos(lead)
    ctx.ticks(walk)
    p1 = ctx.pos(lead)
    if p0 and p1:
        d0, d1 = math.dist((p0[0], p0[2]), finish), math.dist((p1[0], p1[2]), finish)
        print(f"{kind} walks: from {d0:.0f} to {d1:.0f} blocks from the end in {walk / 20:.0f} s ({(d0 - d1) * 20 / walk:.1f} blocks/s)")
        if d1 > d0 - 4:
            fails.append(f"{kind} does not walk along the road: from {d0:.1f} to {d1:.1f} blocks from the end in {walk / 20:.0f} s")
    m = cv.as_player(ctx, "heraldia caravan list", r"Wayfarers on the road: (\d+)|Viajeros en camino: (\d+)")
    if (m.group(1) or m.group(2)) != "1":
        fails.append(f"/heraldia caravan list: {m.group(0)}")
    cv.as_player(ctx, f"heraldia caravan wayfarer {next(c for c, i in KINDS.items() if i == kind)}",
                 r"already 1 wayfarers|Ya hay 1 viajeros")


def far(ctx, fails, w):
    x, z = w["vertices"][0]
    mark = len(ctx.seen)
    cv.on_floor(ctx, PLAYER, x + 400, z)
    m = ends(ctx, w, mark)
    print(f"the player moves away: {m.group(0)}")
    if m.group(1) != "lejos" or int(m.group(2)) != w["entidades"] or ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"when the player moves away: {m.group(0)}; {ctx.count(f'@e[tag={TAG}]')} entities left")


def arrives(ctx, fails, w):
    lead = f"@e[tag={LEADER}.{w['kind']}]"
    mark = len(ctx.seen)
    for k in range(1, len(w["vertices"])):
        x, z = w["vertices"][k]
        cv.on_floor(ctx, lead, x, z)
        cv.on_floor(ctx, PLAYER, x + 4, z)
        ctx.ticks(30)
        if re.search(rf"termina {w['kind']} {w['id']}", "".join(ctx.seen[mark:])):
            break
    ctx.ticks(60)
    alive = ctx.count(lead)
    print(f"at the end of its stretch with the player beside it: {alive} leader still walking")
    if alive != 1:
        fails.append("at the end of its stretch, with the player in sight, the wayfarer vanishes instead of walking on")
    x, z = w["vertices"][-1]
    cv.on_floor(ctx, PLAYER, x + 200, z)
    m = ends(ctx, w, mark)
    print(f"the player leaves: {m.group(0)}")
    if m.group(1) not in ("llegada", "atascada") or not m.group(3) or ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"arrival in sight: {m.group(0)}")


def hurt_guard(ctx, fails, w):
    mark = len(ctx.seen)
    # the reputation logged is the village's new total, not the change: an escorted caravan earlier in the same start
    # leaves +15 with its destination, and when the guards come from that village 15 -> 12 is right (CI, Nov 2026)
    before = re.findall(rf"de {re.escape(w['origen'])}: reputación (-?\d+)", "".join(ctx.seen[:mark]))
    expected = str((int(before[-1]) if before else 0) - 3)
    lead = f"@e[tag={LEADER}.{w['kind']},limit=1]"
    ctx.run(f"damage {lead} 1 minecraft:player_attack by {PLAYER}", r"Applied|damage")
    ctx.run(f"damage {lead} 1 minecraft:player_attack by {PLAYER}", r"Applied|damage")
    ctx.ticks(10)
    log = "".join(ctx.seen[mark:]) + "".join(s.drain(ctx))
    hits = re.findall(rf"encargos: {PLAYER} golpea a un viajero \(guardias\) de (.+?): reputación (-?\d+)", log)
    print(f"hurting a guard twice: {hits}")
    if len(hits) != 1 or hits[0][0] != w["origen"] or hits[0][1] != expected:
        fails.append(f"hurting a guard: the reputation with {w['origen']} should drop once by 3, to {expected} ({hits})")
    target = ctx.run(f"data get entity @e[tag={PARTNER},limit=1] AngryAt", r"has the following entity data: (.+)|Found no elements|No entity")
    print(f"the other guard: {target.group(0).strip()[-80:]}")


def kill_hunter(ctx, fails, w):
    lead = f"@e[tag={LEADER}.{w['kind']},limit=1]"
    p = ctx.pos(lead)
    mark = len(ctx.seen)
    ctx.run(f"damage {lead} 1000 minecraft:player_attack by {PLAYER}", r"Applied|damage")
    m = ends(ctx, w, mark)
    ctx.ticks(40)
    floor = ctx.count(f"@e[type=minecraft:item,x={p[0]:.0f},y={p[1]:.0f},z={p[2]:.0f},distance=..24]")
    rep = re.search(rf"encargos: {PLAYER} mata a un viajero \(cazador\) de (.+?): reputación (-?\d+)", ctx.log())
    print(f"the hunter killed: {m.group(0)}; {floor} items on the ground; {rep and rep.group(0)}")
    if m.group(1) != "perdida" or floor or ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"killing the hunter: {m.group(0)}, {floor} items on the ground, {ctx.count(f'@e[tag={TAG}]')} entities left"
                     + (": " + "; ".join(cv.ground_items(ctx, p, floor)) if floor else ""))
    if not rep or rep.group(1) != w["origen"]:
        fails.append("killing the hunter costs no reputation with its village")


def scenario(ctx, fails, route, work):
    """Every check above, on a server already started with the corridor generated and the player next to the road (the
    caravans' test runs it in its first start, so that it costs no server start of its own). It leaves the player in
    creative and the wayfarers switched off, as the caravans' test expects."""
    s.send(ctx.proc, f"gamemode survival {PLAYER}")     # (survival: the guards may turn on it; resistance keeps it alive)
    ctx.run(f"effect give {PLAYER} minecraft:resistance infinite 4 true", r"Applied effect|Gave")
    ctx.run(f"effect give {PLAYER} minecraft:saturation infinite 4 true", r"Applied effect|Gave")
    ctx.run("gamerule advance_time false", r"[Gg]ame ?rule .*advance_time")
    ctx.run("time set noon", r"Set .*(time|noon)")
    # each kind: what it brings, that it walks, one at a time; then its ending
    # (the messenger, fast, only walks 5 s: it would reach the end of its stretch before the others' endings)
    for kind, ending, walk in (("shepherd", far, 200), ("messenger", None, 100), ("patrol", hurt_guard, 100),
                               ("hunter", arrives, 100), ("hunter", kill_hunter, 60)):
        w = new_one(ctx, fails, route, kind)
        if w is None:
            continue
        check_party(ctx, fails, w, walk)
        if ending:
            ending(ctx, fails, w)
        cv.as_player(ctx, "heraldia caravan clear", r"Caravans removed: (\d+)|Caravanas quitadas: (\d+)")
        ctx.ticks(10)
        if ctx.count(f"@e[tag={TAG}]"):
            fails.append(f"after {kind} and clear, {ctx.count(f'@e[tag={TAG}]')} entities remain")
    w = new_one(ctx, fails, route, "pilgrim", required=False)
    if w is not None:
        check_party(ctx, fails, w)
        if not w["santuario"] or not re.match(r"heraldia:unicas/(monasterio|catedral)", w["santuario"]):
            fails.append(f"the pilgrim walks towards no shrine: {w['santuario']}")
        cv.as_player(ctx, "heraldia caravan clear", r"Caravans removed|Caravanas quitadas")
    # a stray one is removed on load
    va, vb, _ = route
    x, z = cv.point(va, vb, 0.5)
    cv.on_floor(ctx, PLAYER, x, z)
    ctx.ticks(10)
    mark = len(ctx.seen)
    ctx.run(f'execute at {PLAYER} run summon minecraft:sheep ~2 ~ ~ {{Tags:["{TAG}","{SHEEP}"]}}', r"Summoned|Unable")
    m = cv.wait(ctx, r"quitada una entidad de una caravana que ya no está en camino \((\w+)", mark)
    ctx.ticks(5)
    if m.group(1) != "sheep" or ctx.count(f"@e[tag={TAG}]"):
        fails.append(f"a stray wayfarer sheep is not removed on load: {m.group(0)}")
    # a kind switched off, then all of them, with /heraldia reload
    configure(work, {"viajeros": {"pastor": {"activado": False}}})
    ctx.run("heraldia reload", r"Heraldia: configuración recargada")
    cv.as_player(ctx, "heraldia caravan wayfarer shepherd", r"That kind of wayfarer \(shepherd\) is disabled|Ese tipo de viajero \(pastor\)")
    w = new_one(ctx, fails, route, "messenger")
    configure(work, {"viajeros": {"activado": False}})
    mark = len(ctx.seen)
    ctx.run("heraldia reload", r"Heraldia: configuración recargada")
    if w is not None:
        m = ends(ctx, w, mark)
        if m.group(1) != "limpieza":
            fails.append(f"when disabled, the wayfarer on the road ends as '{m.group(1)}'")
    ctx.ticks(10)
    if ctx.count(f"@e[tag={TAG}]"):
        fails.append("disabled, wayfarer entities remain")
    cv.as_player(ctx, "heraldia caravan wayfarer", r"Wayfarers are disabled|gente de paso está desactivada")
    if cv.state(ctx, r"Wayfarers: disabled|Gente de paso: desactivada") is None:
        fails.append("/heraldia status does not say the wayfarers are disabled")
    s.send(ctx.proc, f"gamemode creative {PLAYER}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-viajeros"))
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    os.makedirs(a.work, exist_ok=True)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    configure(a.work)
    proc, ctx = at.start_server(a.work, launcher)
    try:
        route = cv.cabin_adv.find_path(ctx)
        if route is None:
            raise SystemExit("no overland route from the located villages")
        va, vb, L = route
        print(f"route from {va} to {vb}: {L} blocks")
        corridor = [c for c in cv.cabin_adv.chunks_of(va, vb) if cv.SEGMENT[0] <= c[0] <= cv.SEGMENT[1]]
        cv.cabin_adv.generate(ctx, corridor)
        x, z = cv.point(va, vb, 0.5)
        ctx.run(f"player {PLAYER} spawn at {x} 200 {z}", r"joined the game")
        if not ctx.until(f"execute if entity @a[name={PLAYER}]"):
            raise SystemExit(f"simulated player {PLAYER} does not appear (Carpet)")
        scenario(ctx, fails, route, a.work)
        ctx.run(f"player {PLAYER} kill", r"left the game")
    finally:
        cv.cabin_adv.halt(proc, ctx)
    if fails:
        print("FALLOS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: every wayfarer with its entities and trades, walking the road, one at a time, dismissed when the player leaves, "
          "lingering in sight at the end, reputation for hurting and killing them, stray entities removed and switched off live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
