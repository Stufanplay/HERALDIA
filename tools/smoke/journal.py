"""Each player's journal (/heraldia journal) on a real 26.3 dedicated server, with a simulated player (Carpet, like guide.py).

Usage: python3 tools/smoke/journal.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
Reads from the .jar (and the disabled families from the configuration) the advancements that make the catalog (aldeas/todas, unicas/todas, medianas/todas|nether|end, minas/*,
costa/*), the unique structures' dimension and the en_us texts, and checks that:
  - a new player sees every kind at 0 out of the total that the advancements give (the Nether and End ones apart), and the
    overall total;
  - after granting one advancement (or criterion) of each kind, each kind counts 1 and the total goes up by as many;
  - /heraldia journal uniques gives the discovered one by name and the rest as missing; mines keep their size order;
  - nothing in the replies is a coordinate;
  - /heraldia status, asked by the player, counts the Nether medium structure as discovered and points to the journal.
The end of the Chronicle (chronicle/ChronicleEnding) runs here too, because the CI server groups are full:
  - /heraldia journal chronicle starts at 0 of the main world's guardians;
  - guardian advancements granted by command (what a kill before this version left) count, but do not close it alone;
  - the last guardian, killed by the player (/damage ... by), closes it: the advancement cronica/final, the last leaf (with
    the "still keeping watch" beyond page) and the Standard of the Heralds, once; a second player nearby is credited with
    that guardian; a second kill gives nothing again;
  - the Nether guardian (advancement) and the End one (killed) give cronica/mas_alla and swap the leaf for one with the
    "beyond" page done, still a single copy; /heraldia journal chronicle book gives a copy only to a Herald;
  - a player who had every guardian advancement before joining gets the end when they join (the old-world path).
"""
import argparse, json, os, re, shutil, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from terralith_biomes import fetch
from trophies import CARPET
from guide import Server

PLAYER = "cronista"   # lowercase: this Carpet build logs the fake player in as "cronista" for "Cronista"
X, Y, Z = 0, 101, 0
OVERVIEW_END = r"are in the Herald's Guide: |You have found everything"   # the last line while unique structures are missing
DETAIL_END = r"\[« Journal\]"
SECTIONS = {"villages": "Village families", "uniques": "Unique structures", "mediums": r"Medium structures \(by type\)",
            "mines": r"Mine entrances \(by size\)", "coast": "Coast: lighthouse and shipwreck", "nether": "The Nether",
            "end": "The End"}


def jar_data(jar):
    """(expected totals per section, the first id of each kind, en_us texts) from the .jar's advancements and structures."""
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        adv = lambda p: json.loads(z.read(f"data/heraldia/advancement/{p}.json"))
        lang = json.loads(z.read("assets/heraldia/lang/en_us.json"))
        families = sorted(adv("aldeas/todas")["criteria"])
        uniques = {"uniques": [], "nether": [], "end": []}
        for sid in sorted(adv("unicas/todas")["criteria"]):
            st = json.loads(z.read(f"data/heraldia/worldgen/structure/unicas/{sid}.json"))
            uniques[st.get("modo", "uniques") if st["type"] == "heraldia:dimension" else "uniques"].append(sid)
        mediums = {d: sorted(adv(f"medianas/{p}")["criteria"]) if f"data/heraldia/advancement/medianas/{p}.json" in names else []
                   for d, p in (("mediums", "todas"), ("nether", "nether"), ("end", "end"))}
        mines = [m for m in ("pequena", "mediana", "grande") if f"data/heraldia/advancement/minas/{m}.json" in names]
        coast = [c for c in ("faro", "naufragio") if f"data/heraldia/advancement/costa/{c}.json" in names]
    totals = {"villages": len(families), "uniques": len(uniques["uniques"]), "mediums": len(mediums["mediums"]),
              "mines": len(mines), "coast": len(coast), "nether": len(uniques["nether"]) + len(mediums["nether"]),
              "end": len(uniques["end"]) + len(mediums["end"])}
    first = {"family": families[0], "unique": uniques["uniques"][0], "medium": mediums["mediums"][0], "by_dimension": uniques,
             "nether_medium": mediums["nether"][0] if mediums["nether"] else None, "mines": mines, "coast": coast[0]}
    return totals, first, lang


REPLIES = []


def ask(srv, cmd, end, who=PLAYER):
    """Everything the server writes in reply to `cmd` (as the player) up to the line matching `end`."""
    mark = len(srv.seen)
    srv.ctx.run(f"execute as {who} run {cmd}", end + r"|Unknown|Incorrect")
    text = "".join(srv.seen[mark:])
    if "journal" in cmd:
        REPLIES.append(text)
    return text


def counts(text):
    out = {}
    for sec, name in SECTIONS.items():
        m = re.search(rf"(\d+)/(\d+) {name}", text)
        if m:
            out[sec] = (int(m.group(1)), int(m.group(2)))
    return out


CHRONICLE_END = r"\[« Journal\]"
# odd names: Carpet takes a real account's capitalisation ("Testigo") when the name exists, and the selectors would miss it
WITNESS, VETERAN = "hrd_testigo", "hrd_veterano"
LEAF = "minecraft:written_book[minecraft:custom_data={heraldia_ultimo_pliego:1}]"


def chronicle(srv, by_dimension, lang):
    """The end of the Chronicle with the player of the journal checks (see the docstring); returns the failures."""
    ctx, fails = srv.ctx, []
    main_ids = [sid for sid in by_dimension["uniques"]]
    beyond = by_dimension["nether"] + by_dimension["end"]
    last = "castillo" if "castillo" in main_ids else main_ids[-1]          # killed by the player; the rest, by advancement
    n = len(main_ids)

    def advancement(who, path):
        return ctx.test(f"execute if entity @a[name={who},advancements={{heraldia:{path}=true}}]")

    def items(who, pred):
        m = ctx.run(f"execute if items entity {who} container.* {pred}", r"Test passed\. Count: (\d+)|Test failed")
        return int(m.group(1) or 0)

    def kill(sid, who):
        """A guardian of `sid` (a zombie with its tags) next to the players, killed by `who` (credited like a real kill)."""
        before = len(re.findall(rf"Heraldia: chronicle: {sid} fell", ctx.log()))
        ctx.run(f'summon minecraft:zombie {X} {Y} {Z + 2} {{NoAI:1b,Tags:["heraldia_guardian","heraldia_guardian.{sid}"]}}',
                r"Summoned new|Unable")
        ctx.run(f"damage @e[tag=heraldia_guardian.{sid},limit=1] 1000 minecraft:player_attack by {who}", r"Applied|No entity|Unable")
        end = time.monotonic() + 30
        while len(re.findall(rf"Heraldia: chronicle: {sid} fell", ctx.log())) <= before and time.monotonic() < end:
            ctx.ticks(10)
        return len(re.findall(rf"Heraldia: chronicle: {sid} fell", ctx.log())) > before

    banner = lambda who: f'minecraft:blue_banner[minecraft:custom_data={{heraldia_estandarte:"{who}"}}]'
    text = ask(srv, "heraldia journal chronicle", CHRONICLE_END)
    if f"0/{n}" not in text or "Chronicle: guardians defeated" not in text:
        fails.append(f"chronicle: a new player should be at 0/{n}: {text[-800:]}")
    # every guardian but the last one, by advancement (what a kill before this version left)
    for sid in main_ids:
        if sid != last:
            ctx.run(f"advancement grant {PLAYER} only heraldia:unicas/{sid}/guardian", r"Granted|granted|Couldn't|No ")
    text = ask(srv, "heraldia journal chronicle", CHRONICLE_END)
    if f"Defeated ({n - 1}):" not in text or f"Still keeping watch (1): {lang[f'heraldia.unicas.{last}.nombre']}" not in text:
        fails.append(f"chronicle: after {n - 1} guardian advancements: {text[-1200:]}")
    if advancement(PLAYER, "cronica/final"):
        fails.append("chronicle: closed before the last guardian fell")
    # the last one, killed by the player, with a second player nearby
    srv.spawn(WITNESS)
    if not kill(last, PLAYER):
        fails.append(f"chronicle: the death of the {last} guardian is not logged")
    ctx.ticks(10)
    if not advancement(PLAYER, "cronica/final"):
        fails.append("chronicle: the last guardian killed by the player does not close it (no cronica/final)")
    if items(PLAYER, LEAF) != 1 or items(PLAYER, banner(PLAYER)) != 1:
        fails.append(f"chronicle: last leaf {items(PLAYER, LEAF)}, standard {items(PLAYER, banner(PLAYER))}; one of each expected")
    inv = srv.inventory(PLAYER)
    if beyond and "heraldia.cronica.pagina.coda.pendiente" not in inv:
        fails.append("chronicle: the last leaf lacks the 'still keeping watch' beyond page")
    if not re.search(rf"Heraldia: chronicle: {PLAYER} closed the Chronicle", ctx.log()):
        fails.append("chronicle: no 'closed the Chronicle' line in the log")
    text = ask(srv, "heraldia journal chronicle", CHRONICLE_END, who=WITNESS)
    if "Defeated (1):" not in text:
        fails.append(f"chronicle: the player nearby is not credited with the {last} guardian: {text[-800:]}")
    text = ask(srv, "heraldia journal", OVERVIEW_END)
    if f"{PLAYER}, Herald of Atlantis" not in text or f"{n}/{n} Chronicle: guardians defeated" not in text:
        fails.append(f"chronicle: the journal does not show the title and the full line: {text[-1500:]}")
    # once: another kill gives nothing again
    kill(last, PLAYER)
    ctx.ticks(10)
    if items(PLAYER, banner(PLAYER)) != 1 or items(PLAYER, LEAF) != 1:
        fails.append("chronicle: a second kill gives the leaf or the standard again")
    # beyond the map: the Nether by advancement, the End by a kill
    if beyond:
        for sid in by_dimension["nether"]:
            ctx.run(f"advancement grant {PLAYER} only heraldia:unicas/{sid}/guardian", r"Granted|granted|Couldn't|No ")
        for sid in by_dimension["end"]:
            kill(sid, PLAYER)
        ctx.ticks(10)
        if not advancement(PLAYER, "cronica/mas_alla"):
            fails.append("chronicle: the Nether and End guardians do not give cronica/mas_alla")
        if items(PLAYER, LEAF) != 1 or "heraldia.cronica.pagina.coda.hecho" not in srv.inventory(PLAYER):
            fails.append("chronicle: beyond the map does not swap the leaf for one with its page done (a single copy)")
        if items(PLAYER, banner(PLAYER)) != 1:
            fails.append("chronicle: beyond the map gives the standard again")
    # a copy only for a Herald
    text = ask(srv, "heraldia journal chronicle book", r"copy of the last leaf|not closed yet|turned off")
    if "Here is a copy of the last leaf" not in text or items(PLAYER, LEAF) != 1:
        fails.append(f"chronicle: the copy is not given in place of the one carried: {text[-400:]}")
    text = ask(srv, "heraldia journal chronicle book", r"copy of the last leaf|not closed yet|turned off", who=WITNESS)
    if "not closed yet" not in text:
        fails.append(f"chronicle: a player who is not a Herald gets a copy: {text[-400:]}")
    # the old-world path: every guardian advancement held before joining, the end on joining
    srv.spawn(VETERAN)
    for sid in main_ids:
        ctx.run(f"advancement grant {VETERAN} only heraldia:unicas/{sid}/guardian", r"Granted|granted|Couldn't|No ")
    if advancement(VETERAN, "cronica/final"):
        fails.append("chronicle: granting advancements by command closed it without a death or a join (it should wait)")
    srv.leave(VETERAN)
    srv.spawn(VETERAN)
    ctx.ticks(20)
    if not advancement(VETERAN, "cronica/final") or items(VETERAN, banner(VETERAN)) != 1:
        fails.append("chronicle: a player with every guardian defeated before joining does not get the end on joining")
    bad = [l.strip() for l in ctx.log().splitlines() if "Exception" in l and ("chronicle" in l.lower() or "cronica" in l.lower())]
    if bad:
        fails.append(f"chronicle: errors in the log: {bad[:3]}")
    print(f"chronicle: {n} main-world guardians, {len(beyond)} beyond, {len(fails)} failures")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-diario"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    totals, first, lang = jar_data(a.jar)
    fails = []
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    srv = Server(a.work, launcher)
    try:
        ctx = srv.ctx
        # a family disabled in the configuration (pantano, by default) is not missing: it cannot appear
        with open(os.path.join(a.work, "config", "heraldia.json"), encoding="utf-8") as f:
            off = [k for k, v in json.load(f).get("aldeas", {}).get("familias", {}).items() if v is False]
        totals["villages"] -= len(off)
        if first["family"] in off:
            raise SystemExit(f"the first family ({first['family']}) is disabled in this configuration")
        ctx.run(f"forceload add {X} {Z}", r"Marked|force|already")
        for rule in ("spawn_mobs", "advance_time"):
            ctx.run(f"gamerule {rule} false", rf"[Gg]ame ?rule .*{rule}")
        srv.spawn(PLAYER)
        ctx.run(f"advancement revoke {PLAYER} everything", r"Revoked|revoked|Couldn't")
        # 1) nothing found yet: every kind at 0 of its total
        text = ask(srv, "heraldia journal", OVERVIEW_END)
        total = sum(totals.values())
        print(f"expected totals (families disabled: {off}): {totals}")
        if f"{PLAYER}'s journal" not in text or f"0 of {total} discoveries in total" not in text:
            fails.append(f"new player: no title or total 0 of {total}: {text[-1500:]}")
        got = counts(text)
        for sec, n in totals.items():
            want = (0, n) if n else None
            if got.get(sec) != want:
                fails.append(f"new player, {sec}: {got.get(sec)}, should be {want}")
        print(f"journal of a new player: {got}")
        # 2) one of each kind
        grants = [f"only heraldia:aldeas/{first['family']}", f"only heraldia:unicas/{first['unique']}/descubrir",
                  f"only heraldia:medianas/todas {first['medium']}", f"only heraldia:minas/{first['mines'][0]}",
                  f"only heraldia:costa/{first['coast']}"]
        if first["nether_medium"]:
            grants.append(f"only heraldia:medianas/nether {first['nether_medium']}")
        for g in grants:
            ctx.run(f"advancement grant {PLAYER} {g}", r"Granted|granted|Couldn't|No ")
        text = ask(srv, "heraldia journal", OVERVIEW_END)
        got = counts(text)
        for sec in ("villages", "uniques", "mediums", "mines", "coast") + (("nether",) if first["nether_medium"] else ()):
            if got.get(sec) != (1, totals[sec]):
                fails.append(f"after one of each kind, {sec}: {got.get(sec)}, should be (1, {totals[sec]})")
        if f"{len(grants)} of {total} discoveries in total" not in text:
            fails.append(f"after {len(grants)} discoveries the total does not say so: {text[-1500:]}")
        if "/heraldia guide" not in text:
            fails.append("with unique structures missing it does not point to the Herald's Guide")
        print(f"after one of each kind: {got}")
        # 3) a kind's detail: names found and missing
        text = ask(srv, "heraldia journal uniques", DETAIL_END)
        name = lang[f"heraldia.unicas.{first['unique']}.nombre"]
        if f"Found (1): {name}" not in text or f"Still to find ({totals['uniques'] - 1}):" not in text:
            fails.append(f"journal uniques: {text[-1200:]}")
        text = ask(srv, "heraldia journal mines", DETAIL_END)
        names = [lang[f"heraldia.minas.{m}.nombre"] for m in first["mines"]]
        if f"Found (1): {names[0]}" not in text or ("Still to find" in text and ", ".join(names[1:]) not in text):
            fails.append(f"journal mines (size order): {text[-800:]}")
        # no coordinates in any journal reply (three numbers in a row, or a "[x, y, z]")
        for t in REPLIES:
            for line in t.splitlines():
                body = line.split("]: ", 1)[-1]
                if re.search(r"-?\d+,? -?~?\d+,? -?\d+|\[-?\d+, ", body):
                    fails.append(f"a journal reply looks like coordinates: {body}")
        # 4) /heraldia status: the Nether medium counts and the player is pointed to the journal
        text = ""
        for page in range(1, 6):   # paged: 8 lines a page, the last one has only the previous-page button
            text += ask(srv, f"heraldia status {page}", r"\[« Previous page\]|\[Next page »\]")
            if re.search(r"page (\d+) of \1\)", text):
                break
        if "/heraldia journal" not in text:
            fails.append(f"/heraldia status does not point to the journal: {text[-1200:]}")
        m = re.search(r"Medium structures \(by type\): (\d+) of (\d+)", text)
        want = 2 if first["nether_medium"] else 1
        if not m or int(m.group(1)) != want:
            fails.append(f"/heraldia status medium structures: {m and m.group(0)}, should count {want} (the Nether one too)")
        # 5) the end of the Chronicle
        fails += chronicle(srv, first["by_dimension"], lang)
    finally:
        srv.stop()
    if fails:
        print("JOURNAL FAILED:\n - " + "\n - ".join(fails))
        return 1
    print("JOURNAL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
