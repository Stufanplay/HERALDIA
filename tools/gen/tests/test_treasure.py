"""tesoro.py (T40, chained treasure hunt): the first hint in the loot and its probability, the final chest, the
texts in the 8 languages, the Guide page, the advancements, the options and that what the Java reads matches."""
import json
import os
import re
import types

import pytest

import guide
import languages
import mediums
import mines
import options
import board
import treasure
import uniques
from uniques._common import chest_loot

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
JAVA = os.path.join(ROOT, "src/main/java/io/github/albertosa23/heraldia")


def _java(rel):
    with open(os.path.join(JAVA, rel), encoding="utf-8") as f:
        return f.read()


def _trans():
    return {c: languages.read(c) if hasattr(languages, "read") else json.load(open(languages.route(c), encoding="utf-8"))
            for c in languages.TRANSLATIONS}


# ------------------------------------------------------------------ the first hint in the loot
def test_with_hint_adds_a_group_with_the_condition_and_the_factor():
    tbl = {"type": "minecraft:chest", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": "minecraft:bread"}]}]}
    for family, factor in treasure.FACTOR.items():
        t = treasure.with_hint(tbl, family)
        assert t["pools"][:-1] == tbl["pools"], "does not touch what was there"
        p = t["pools"][-1]
        assert p["rolls"] == 1 and p["entries"] == [{"type": "minecraft:loot_table", "value": treasure.FRAGMENT}]
        assert p["condition"] == {"type": treasure.CONDITION, "factor": factor}
        assert "solo_sin_lootr" not in p, "with Lootr too: each player gets their own"
    assert len(tbl["pools"]) == 1, "does not change the original table"


def test_probability_of_the_first_hint():
    assert treasure.probability(3.0, treasure.FACTOR["medianas"]) == pytest.approx(0.03)
    assert treasure.probability(3.0, treasure.FACTOR["minas"]) == pytest.approx(0.03)
    assert treasure.probability(3.0, treasure.FACTOR["unicas"]) == pytest.approx(0.015)
    assert treasure.probability(3.0, treasure.FACTOR["hazanas"]) == pytest.approx(0.15)
    assert treasure.probability(3.0, treasure.FACTOR["encargos"]) == pytest.approx(0.03)
    assert treasure.probability(0, 5) == 0 and treasure.probability(100, 5) == 1 and treasure.probability(50, 0.5) == 0.25


def test_probability_simulation():
    """With the same computation as PistaCondition (chance < probability), the observed frequency approaches the expected one."""
    import random
    rnd = random.Random(40)
    for pct, factor in ((3.0, 1.0), (3.0, 0.5), (10.0, 5.0)):
        p = treasure.probability(pct, factor)
        n = 200_000
        hits = sum(rnd.random() < p for _ in range(n))
        assert abs(hits / n - p) < 4 * (p * (1 - p) / n) ** 0.5 + 1e-9


def test_same_count_as_java():
    java = _java("treasure/ClueCondition.java")
    assert "Math.max(0, Math.min(1, percent / 100.0 * factor))" in java
    assert 'optionalFieldOf("factor", 1.0)' in java
    assert f'"{treasure.CONDITION.split(":")[1]}"' in _java("treasure/Treasure.java")


def test_mediums_and_mines_carry_the_hint_in_all_their_tables(tmp_path):
    written_list = {}

    def jdump(out, rel, obj):
        written_list[rel] = obj
    mediums.write(str(tmp_path), jdump)
    mines.write(str(tmp_path), jdump)
    tables = {k: v for k, v in written_list.items() if "/loot_table/" in k}
    assert len(tables) == len(mediums.tables()) + len(mines.tables())
    for rel, t in tables.items():
        family = "minas" if "/loot_table/minas/" in rel else "medianas"
        assert t["pools"][-1] == treasure.clue_pool(family), rel


def test_only_in_chests_barrels_and_jars():
    """The tables of the unique structures that carry the hint: those of some container (never that of a trap dispenser)."""
    def t(*blocks):
        return types.SimpleNamespace(blocks={i: b for i, b in enumerate(blocks)})
    reg = types.SimpleNamespace(templates={
        "a": t(("minecraft:chest[facing=north]", {"LootTable": "heraldia:unicas/x/premium"}),
               ("minecraft:trapped_chest", {"LootTable": "heraldia:unicas/x/trampa"}),
               ("minecraft:barrel[facing=up]", {"LootTable": "heraldia:unicas/x/barril"}),
               ("minecraft:decorated_pot[facing=north]", {"LootTable": "heraldia:unicas/x/vasija"}),
               ("minecraft:dispenser[facing=up]", {"LootTable": "heraldia:unicas/x/flechas"}),
               ("minecraft:dropper", {"LootTable": "heraldia:unicas/x/soltador"}),
               ("minecraft:stone", None), ("minecraft:chest", {"Items": []}))})
    assert treasure.tables_in_containers(reg) == {"heraldia:unicas/x/premium", "heraldia:unicas/x/trampa",
                                                  "heraldia:unicas/x/barril", "heraldia:unicas/x/vasija"}


def test_reward_of_the_board_feats():
    for name, t in board.tables().items():
        assert t["type"] == "minecraft:advancement_reward"
        assert t["pools"][-1] == treasure.clue_pool("hazanas"), name


def test_pay_of_the_board_quests():
    """T38: each delivered quest rolls heraldia:tesoro/encargo (only the fragment, with the quest factor)."""
    t = treasure.quest()
    assert t["pools"] == [treasure.clue_pool("encargos")]
    assert treasure.QUEST == "heraldia:tesoro/encargo"
    assert 'Heraldia.id("tesoro/encargo")' in _java("treasure/Treasure.java")
    assert "Treasure.reward(p)" in _java("quests/Quests.java")


def test_the_writer_applies_the_hint_to_the_uniques():
    with open(os.path.join(os.path.dirname(treasure.__file__), "writer.py"), encoding="utf-8") as f:
        w = f.read()
    assert 'treasure.with_hint(table, "unicas")' in w and "treasure.tables_in_containers(reg)" in w
    assert "treasure.write(out, jdump)" in w and "treasure.lang()" in w and "treasure.errors(" in w


# ------------------------------------------------------------------ the fragment and the final chest
def _components(entrance):
    return next(m["components"] for m in entrance["modifier"] if m["type"] == "minecraft:set_components")


def test_fragment():
    t = treasure.fragment()
    (e,) = t["pools"][0]["entries"]
    assert e["name"] == "minecraft:paper"
    c = _components(e)
    assert c["minecraft:custom_data"] == "{heraldia_busqueda: {v: 1}}"
    assert c["minecraft:max_stack_size"] == 1, "each fragment, its own chain"
    assert c["minecraft:item_name"]["translate"] == treasure.key("fragmento.nombre")
    assert [l["translate"] for l in c["minecraft:lore"]] == [treasure.key("fragmento.lore"), treasure.key("fragmento.uso")]
    assert all(l["italic"] is False for l in c["minecraft:lore"])


def test_mark_is_the_java_one_and_distinct_from_others():
    assert f'MARK = "{treasure.MARK}"' in _java("treasure/Chain.java")
    import advancements
    assert treasure.MARK not in (advancements.TREASURE_MARK, chest_loot.STORY_MARK, guide.MARK)


def test_chest_final_good_without_break_the_progression():
    t = treasure.place_chest()
    assert t["pools"][0]["rolls"] == 1 and t["pools"][0]["entries"] == [treasure.memento()]
    text = json.dumps(t)
    for p in treasure.FORBIDDEN:
        assert p not in text
    valuables = {e["name"].split(":")[1] for e in treasure.VALUABLE}
    assert {"diamond", "emerald", "gold_ingot"} <= valuables
    assert treasure.errors() == []


def test_keepsake_with_name():
    c = _components(treasure.memento())
    assert treasure.memento()["name"] == "minecraft:compass"
    assert c["minecraft:item_name"]["translate"] == treasure.key("recuerdo.nombre")
    assert c["minecraft:custom_data"] == "{heraldia_recuerdo_tesoro: 1b}"
    assert c["minecraft:rarity"] == "rare"


def test_items_exist():
    """Against the real 26.3 registry (mcmeta summary left by the build); without it, it is skipped."""
    summary = os.environ.get("MCMETA_SUMMARY") or os.path.join(ROOT, "build", "mcmeta-summary")
    f = os.path.join(summary, "registries", "data.json")
    if not os.path.isfile(f):
        pytest.skip(f"without the 26.3 registry summary ({summary}): run ./gradlew fetchRegistries or set MCMETA_SUMMARY")
    with open(f, encoding="utf-8") as fh:
        items = set(json.load(fh)["item"])
    names = re.findall(r'"name": "minecraft:([a-z0-9_]+)"', json.dumps([treasure.fragment(), treasure.place_chest()]))
    assert names and set(names) <= items, set(names) - items
    emblems = [a["display"]["icon"]["id"].split(":")[1] for a in treasure.advancements().values()]
    assert set(emblems) <= items


def test_errors_detects_lore_long(monkeypatch):
    monkeypatch.setitem(treasure.TEXTS, "mapa.uso", ("x" * 80, "ok"))
    assert any("mapa.uso" in e for e in treasure.errors())


# ------------------------------------------------------------------ texts in the 8 languages
def test_texts_in_the_two_base_languages():
    l = treasure.lang()
    assert l["es_es"].keys() == l["en_us"].keys()
    assert all(v.strip() for d in l.values() for v in d.values())
    mark = re.compile(r"%(?:\d+\$)?s")
    for k in l["es_es"]:
        assert len(mark.findall(l["es_es"][k])) == len(mark.findall(l["en_us"][k])), k


def test_texts_in_the_translations():
    base = dict(treasure.lang()["en_us"], **treasure.lang_advancements()["en_us"])
    mark = re.compile(r"%(?:\d+\$)?s")
    for lang_code, t in _trans().items():
        for k, en in base.items():
            assert t.get(k, "").strip(), f"{lang_code}: missing {k}"
            assert len(mark.findall(t[k])) == len(mark.findall(en)), f"{lang_code}: huecos de {k}"
        for k in ("heraldia.guia.pagina.tesoro", "heraldia.guia.pagina.tesoro.titulo", "heraldia.config.tesoro.activado",
                  "heraldia.config.tesoro.probabilidad", "heraldia.config.tesoro.radio_max", "heraldia.config.seccion.tesoro"):
            assert t.get(k, "").strip(), f"{lang_code}: missing {k}"
    assert treasure.errors(_trans()) == [], "the lore fits in all languages"


def test_map_lore_fits_with_a_long_biome():
    for lang_code, t in [("en", treasure.lang()["en_us"]), ("es", treasure.lang()["es_es"])] + list(_trans().items()):
        line = languages.format_text(t[treasure.key("pista.donde")], ["Old Growth Spruce Taiga", t.get("heraldia.info.dir.ne", "northeast")])
        assert chest_loot.width(line) <= treasure.LORE_MAX_PX + 60, f"{lang_code}: {line}"


# ------------------------------------------------------------------ the Guide
def test_guide_page():
    ids = [pid for pid, _, _ in guide.PAGES]
    assert "tesoro" in ids and ids.index("tesoro") == ids.index("mapas") + 1, "next to the treasure maps"
    assert "tesoro" in guide.dataset(uniques.modules())["paginas"]
    es = guide.lang()["es_es"]
    assert "Ysolda" in es["heraldia.guia.pagina.tesoro"]
    assert guide.errors(uniques.modules(), _trans()) == []


def test_guide_page_fits_in_each_language():
    for lang_code, t in list(_trans().items()) + [("es", guide.lang()["es_es"]), ("en", guide.lang()["en_us"])]:
        title, text = t["heraldia.guia.pagina.tesoro.titulo"], t["heraldia.guia.pagina.tesoro"]
        assert guide.page_lines(title, text) <= chest_loot.BOOK_LINES, lang_code
        assert guide.title_lines(title) == 1, lang_code


# ------------------------------------------------------------------ logros
def test_advancements():
    a = treasure.advancements()
    assert set(a) == {"tesoro/fragmento", "tesoro/cofre"}
    assert a["tesoro/fragmento"]["parent"] == "heraldia:raiz" and a["tesoro/cofre"]["parent"] == "heraldia:tesoro/fragmento"
    pred = a["tesoro/fragmento"]["criteria"]["fragmento"]["conditions"]["items"][0]
    assert pred["items"] == "minecraft:paper" and pred["predicates"]["minecraft:custom_data"] == {treasure.MARK: {}}
    assert a["tesoro/cofre"]["criteria"]["cofre"] == {"trigger": "minecraft:player_generates_container_loot",
                                                      "conditions": {"loot_tables": treasure.CHEST_TABLE}}
    assert a["tesoro/cofre"]["display"]["frame"] == "goal"
    assert all(set(x.get("rewards", {})) <= {"experience"} for x in a.values()), "experience only"
    l = treasure.lang_advancements()["es_es"]
    for x in a.values():
        assert x["display"]["title"]["translate"] in l and x["display"]["description"]["translate"] in l


def test_advancements_go_with_the_others():
    import advancements
    import inspect
    assert "advs.update(treasure.advancements())" in inspect.getsource(advancements.build)


def test_the_java_uses_the_tables():
    t = _java("treasure/Treasure.java")
    assert 'Heraldia.id("tesoro/fragmento")' in t and 'Heraldia.id("tesoro/cofre")' in t
    assert treasure.FRAGMENT == "heraldia:tesoro/fragmento" and treasure.CHEST_TABLE == "heraldia:tesoro/cofre"


# ------------------------------------------------------------------ opciones
def test_options():
    o = {x["clave"]: x for x in options.schema()["opciones"]}
    assert o["tesoro.activado"]["defecto"] is True
    assert o["tesoro.probabilidad"]["defecto"] == treasure.DEFAULT_PROBABILITY
    assert (o["tesoro.probabilidad"]["min"], o["tesoro.probabilidad"]["max"]) == (0, 100)
    assert o["tesoro.radio_max"]["defecto"] == treasure.DEFAULT_RADIUS
    assert o["tesoro.radio_max"]["min"] >= 300
    for k in ("tesoro.activado", "tesoro.probabilidad", "tesoro.radio_max"):
        assert not o[k].get("generacion"), f"{k} is not a generation option"
        assert o[k]["seccion"] == "tesoro"
        assert not o[k].get("perfil"), "profiles do not touch it"
    j = _java("treasure/ClueCondition.java")
    assert all(f'"{k}"' in j for k in ("tesoro.activado", "tesoro.probabilidad", "tesoro.radio_max"))


def test_reloadable_options_in_java():
    assert re.search(r'RELOADABLE = List\.of\([^;]*"tesoro\."', _java("config/Reload.java"), re.S)
