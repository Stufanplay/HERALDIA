"""Traces of work in progress (traces.py, option aldeas.vida.rastros): what each style draws, that they are blocks only and
nothing functional, that they fit on their plot, pass the generic audit, are deterministic and do not move the style's
shared random source (the rest of the village's templates stay as they were)."""
import json
import pytest
import lint
import options
import pack
import traces
from pack import Registry, build_theme
from themes import THEMES

SEED = 1234
IDS = [th["id"] for th in THEMES]


@pytest.fixture(scope="module")
def reg():
    r = Registry()
    for th in THEMES:
        traces.build(r, th, SEED)
    return r


def test_every_style_has_traces_and_only_known_kinds():
    assert len(THEMES) == 36
    for th in THEMES:
        w = traces.weights(th)
        assert w, th["id"]
        assert set(w) <= set(traces.KINDS), th["id"]
        assert 2 <= len(w) <= len(traces.KINDS), th["id"]


def test_traces_that_would_look_wrong_are_not_drawn():
    by_id = {th["id"]: traces.weights(th) for th in THEMES}
    for th in THEMES:
        w = by_id[th["id"]]
        if th["family"] == "nieve":
            assert "laundry" not in w and "meal" not in w, th["id"]       # nobody hangs washing or picnics in the snow
        if th["family"] == "oscuro":
            assert "meal" not in w, th["id"]
        if "fish_rack" in w:
            assert th["family"] in ("costa", "pantano", "jungla") or th["id"] == "taiga_nordica", th["id"]
    assert "laundry" not in by_id["oscuro_gotica"]
    assert "meal" not in by_id["bosque_abadia"]
    assert "cart" not in by_id["cerezos_templo"]
    for th in THEMES:
        if th["family"] == "costa":
            assert "fish_rack" in by_id[th["id"]], th["id"]


def test_blocks_only_and_nothing_functional(reg):
    names = [n for n in reg.templates if "/traces/" in n or n.endswith("/fillers/plot")]
    assert len(names) == 36 + sum(len(traces.weights(th)) for th in THEMES)
    for n in names:
        t = reg.templates[n]
        assert t.entities == [], n
        for pos, (st, nbt) in t.blocks.items():
            b = lint.bname(st)
            if b == "jigsaw":
                continue
            assert nbt is None, (n, pos, st)                              # no chest, no loot, no block entity data
            assert not any(f in b for f in traces.FUNCTIONAL), (n, pos, st)


def test_each_trace_fits_on_its_plot_at_the_plot_s_level(reg):
    """Where the game puts it: a jigsaw facing up places its child's jigsaw in the cell ABOVE it. The trace's floor (its
    y = 0) must land on the plot's floor (the level of its entrance), not a block above it: from a trace standing a block
    up, a neighbour's 1.5-high wall was half a block up and villagers walked over it into a walled cemetery
    (docs/LESSONS.md). The first version of this test read the slot's own cell as the trace's, and passed."""
    for th in THEMES:
        plot = reg.templates[f"{th['id']}/fillers/plot"]
        px, py, pz = plot.size()
        slot = next(j for j in plot.jigsaws if j["name"] == "heraldia:slot")
        entrance = next(j for j in plot.jigsaws if j["name"] == "heraldia:entrance")
        sx, sy, sz = slot["pos"]
        floor = entrance["pos"][1]
        assert plot.get(0, floor, 1) is not None and sy == floor - 1, (th["id"], slot["pos"], entrance["pos"])
        for k in traces.weights(th):
            t = reg.templates[f"{th['id']}/traces/{k}"]
            j = t.jigsaws[0]
            assert tuple(j["pos"]) == (0, 0, 0)
            ty = sy + 1 - j["pos"][1]                     # the trace's y = 0 in the plot's coordinates
            assert ty == floor, (th["id"], k, ty, floor)
            w, h, d = t.size()
            assert (sx + w <= px, ty + h <= py, sz + d <= pz) == (True, True, True), (th["id"], k, t.size(), plot.size())


def test_generic_audit_passes(reg):
    bad = {n: iss for n, iss in lint.lint_registry(reg).items()}
    assert bad == {}


def test_pools(reg):
    for th in THEMES:
        p = reg.pools[f"heraldia:{th['id']}/traces"]
        assert p["fallback"] == f"heraldia:{th['id']}/traces"          # the plot may be at the maximum depth
        assert [e[1] for e in p["elements"]] == list(traces.weights(th).values())
        assert all(e[2] == "rigid" for e in p["elements"])


def _blocks(r):
    return {n: (sorted(t.blocks.items()), t.entities) for n, t in r.templates.items()}


def test_deterministic():
    a, b = Registry(), Registry()
    for r in (a, b):
        for th in THEMES[:6]:
            traces.build(r, th, SEED)
    assert _blocks(a) == _blocks(b)


def test_the_rest_of_the_style_does_not_change(monkeypatch):
    """With the traces, a style has the same templates as without them plus its plot and traces; only its houses pool changes."""
    th = THEMES[0]
    with_them = Registry()
    build_theme(with_them, th, SEED)
    monkeypatch.setattr(traces, "build", lambda reg, th, seed: None)
    without = Registry()
    build_theme(without, th, SEED)
    new = set(with_them.templates) - set(without.templates)
    assert new == {f"{th['id']}/fillers/plot"} | {f"{th['id']}/traces/{k}" for k in traces.weights(th)}
    a, b = _blocks(with_them), _blocks(without)
    assert {n: a[n] for n in b} == b
    changed = {p for p in without.pools if without.pools[p] != with_them.pools[p]}
    assert changed == {f"heraldia:{th['id']}/houses"}
    extra = [e for e in with_them.pools[f"heraldia:{th['id']}/houses"]["elements"]
             if e not in without.pools[f"heraldia:{th['id']}/houses"]["elements"]]
    assert [(e[0], e[1]) for e in extra] == [(f"{th['id']}/fillers/plot", traces.PLOT_WEIGHT)]


def test_option_and_texts():
    fixed = {k: (d, lo, hi) for k, d, lo, hi, _, _ in options._FIXED}
    assert fixed["aldeas.vida.rastros"] == (True, None, None)
    lang = options.lang()
    for code in ("es_es", "en_us"):
        assert lang[code]["heraldia.config.aldeas.vida.rastros"]
        assert lang[code]["heraldia.config.aldeas.vida.rastros.nombre"]
    for code in ("fr_fr", "de_de", "it_it", "pt_br", "ca_es", "gl_es"):
        with open(f"{pack.__file__.rsplit('/', 1)[0]}/languages/{code}.json", encoding="utf-8") as f:
            t = json.load(f)
        assert t["heraldia.config.aldeas.vida.rastros"] and t["heraldia.config.aldeas.vida.rastros.nombre"], code
