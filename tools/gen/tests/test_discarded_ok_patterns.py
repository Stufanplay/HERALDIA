"""A server test that throws a command's reply away must not have an `ok` that accepts a failure.

`server_smoke.run` fails by default: a reply that matches `ERROR_PATTERN` and not the call's `ok` raises. So a call
whose reply nobody reads is protected -- unless its own `ok` matches the failure reply, and then the failure is the
accepted reply and the test carries on as if the command had worked. Some do it on purpose (`...|Unknown|Incorrect`),
some by accident of substring: `now` is inside `Unknown`, `not` matches `not loaded`, `sitio` is inside `position`, and
a pattern ending in `|.` accepts any line at all. When the switch landed there were 97 such calls in `tools/` (91 in
the server tests, 6 in `tools/probes/`, which are probes and not tests and are left out here).

The rule: for every discarded `.run(cmd, ok)` (the same calls `tools/unchecked_replies.py` counts), `ok` must not match
any of the real failure replies in `server_smoke.FAILURE_REPLIES` that `ERROR_PATTERN` recognises. The calls that still
break it are listed in `STILL_SWALLOW`, keyed by (file, the literal `ok`) with the exact number of such calls -- not
by line, which moves with every edit, and compared for **equality**, not "at most": a new site fails the test, and so
does a site that was fixed without taking it off the list, so the list cannot go stale and keep claiming exceptions
that no longer exist. Each lot that narrows patterns proves itself by shrinking this list.

What it cannot see: an `ok` built at run time (an f-string or a variable). Those are counted, not judged, and the
count is pinned too (`NOT_LITERAL`), so the hole has a number.

This test needs no server and no .jar.
"""
import ast
import collections
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_path = list(sys.path)      # tools/smoke only while importing (see test_compat_mods.py)
sys.path.insert(0, str(ROOT / "tools" / "smoke"))
import server_smoke as s  # noqa: E402
sys.path[:] = _path

# The failure replies a discarded call is judged against: the real ones the switch raises on.
FAILURES = [r for r in s.FAILURE_REPLIES.values() if re.search(s.ERROR_PATTERN, r)]
SKIPPED = ("tools/probes/",)          # probes, not tests: nobody decides a green with them

# (file, ok) -> how many discarded calls in that file still have that `ok`. Shrinks as each lot lands.
STILL_SWALLOW = {
    ('tools/smoke/journal.py', 'Applied|No entity|Unable|Unknown|Incorrect'): 1,
    ('tools/smoke/journal.py', "Granted|granted|Couldn't|Unknown|Incorrect|No "): 1,
    ('tools/smoke/journal.py', "Granted|granted|Couldn't|Unknown|No "): 3,
    ('tools/smoke/light_profile.py', '[Ss]print|ticks|Unknown'): 1,
    ('tools/smoke/mend.py', 'Teleported|Unknown'): 1,
    ('tools/smoke/runtime_cost.py', 'Events stopped|Eventos parados|Unknown|Incorrect'): 1,
    ('tools/smoke/runtime_cost.py', 'Prepárate|Get ready|Unknown|Incorrect|already|ya hay'): 1,
    ('tools/smoke/runtime_cost.py', 'joined the game|Unknown|Incorrect'): 1,
    ('tools/smoke/runtime_cost.py', 'left the game|Unknown|Incorrect'): 1,
    ('tools/smoke/treasure.py', 'Dropped|Gave|No items|Unknown'): 1,
    ('tools/smoke/treasure.py', 'Successfully filled|No blocks|Unknown|Incorrect'): 1,
    ('tools/smoke/update.py', 'Summoned|Unable|Invalid'): 1,
    ('tools/smoke/update_check.py', 'Made .* a server operator|Nothing changed|Unknown|Incorrect'): 1,
    ('tools/smoke/wizard_huts.py', 'Loaded template|Failed'): 1,
}
NOT_LITERAL = 24          # discarded calls whose `ok` is built at run time: not judged, only counted


def _discarded(source):
    """(lineno, ok or None) of every `.run(...)` whose parent is an `ast.Expr` (its reply is thrown away)."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "run" and node.value.args):
            ok = node.value.args[-1]
            out.append((node.lineno, ok.value if isinstance(ok, ast.Constant) and isinstance(ok.value, str) else None))
    return out


def swallows(ok):
    """Does this `ok` accept a real failure reply the switch would otherwise raise on?"""
    return any(re.search(ok, reply) for reply in FAILURES)


def _scan():
    found, lines, not_literal, total = collections.Counter(), collections.defaultdict(list), 0, 0
    for path in sorted(ROOT.glob("tools/**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIPPED):
            continue
        try:
            calls = _discarded(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno, ok in calls:
            total += 1
            if ok is None:
                not_literal += 1
            elif swallows(ok):
                found[(rel, ok)] += 1
                lines[(rel, ok)].append(lineno)
    return found, lines, not_literal, total


def test_no_discarded_reply_accepts_a_failure_beyond_the_list():
    found, lines, _, _ = _scan()
    new = {k: found[k] - STILL_SWALLOW.get(k, 0) for k in found if found[k] > STILL_SWALLOW.get(k, 0)}
    gone = {k: STILL_SWALLOW[k] - found.get(k, 0) for k in STILL_SWALLOW if found.get(k, 0) < STILL_SWALLOW[k]}
    remaining = sum(found.values())
    files = sorted({f for f, _ in found})
    msg = []
    if new:
        msg.append("discarded replies whose ok accepts a failure, not on the list (narrow the ok, do not list it):\n  "
                   + "\n  ".join(f"{f}:{lines[(f, ok)]} ok={ok!r} (+{n})" for (f, ok), n in sorted(new.items())))
    if gone:
        msg.append("fixed but still listed -- take them off STILL_SWALLOW:\n  "
                   + "\n  ".join(f"{f} ok={ok!r} (-{n})" for (f, ok), n in sorted(gone.items())))
    assert not msg, "\n".join(msg) + f"\n{remaining} still swallow a failure, in {len(files)} files: {', '.join(files)}"


def test_the_hole_it_cannot_see_has_a_number():
    _, _, not_literal, _ = _scan()
    assert not_literal == NOT_LITERAL, (
        f"{not_literal} discarded calls build their ok at run time (pinned: {NOT_LITERAL}); this check cannot judge "
        "them, so a change in that number is worth a look before updating it")


def test_the_check_sees_the_calls_it_is_meant_to_see():
    """Guards the checker itself: blind, it would pass by finding nothing, the way a deleted assertion passes."""
    found, _, _, total = _scan()
    assert total >= 600, f"only {total} discarded .run(...) calls seen; the walk has stopped seeing them"
    assert sum(found.values()) == sum(STILL_SWALLOW.values()), "the list and the code disagree (see the first test)"


@pytest.mark.parametrize("ok, reply", [
    (r"Gamerule|set to|now", s.FAILURE_REPLIES["Unknown"]),                    # `now` inside "Unknown"
    (r"[Rr]emoved|[Uu]nmarked|force|not", s.FAILURE_REPLIES["not loaded"]),    # `not` in "not loaded"
    (r"heraldia|Herald|Heraldo|place|confirm", s.FAILURE_REPLIES["Failed"]),  # `place` in "Failed to place"
    (r"no cabe|No hay|room|sitio", s.FAILURE_REPLIES["not loaded"]),          # `sitio` inside "position"
    (r"left the game|Unknown|Incorrect|.", "anything at all"),                # `.` accepts any line
])
def test_the_accidents_were_real(ok, reply):
    """The five shapes found when the switch landed, each against the reply it swallowed."""
    assert re.search(ok, reply)


# Lot 1 and 2: each narrowed pattern against the success replies read on a 26.3 server, and against every failure.
NARROWED = [
    (r"Gamerule|set to", ["Game rule spawn_mobs is now set to false", "Game rule spawn_mobs is already set to false"]),
    (r"Gamerule|set", ["Game rule max_block_modifications is now set to 4000000"]),
    (r"Unmarked|force", ["Unmarked chunk [0, 0] in minecraft:overworld for force loading",
                         "No chunks were removed from force loading",
                         "Unmarked all force loaded chunks in minecraft:overworld"]),
    (r"[Rr]emoved|[Uu]nmarked|force", ["Unmarked 9 chunks in minecraft:overworld from [0, 0] to [2, 2] for force loading",
                                       "No chunks were removed from force loading"]),
    (r"heraldia|Herald|Heraldo|confirm", ["To build it: /heraldia herald place confirm"]),
    (r"starts in|Empieza el evento|not started|no cabe|No hay|There is no|room|no hay sitio",
     ["Esta aldea no tiene plaza (se quedó sin ella al generarse): no hay sitio para un evento (mercado).",
      "No hay sitio libre en la plaza para el evento «mercado»: algo lo ocupa (una construcción, el tablón, una pieza que falta)."]),
    (r"left the game|Can only manipulate existing players", ["Testigo left the game", "Can only manipulate existing players"]),
]


@pytest.mark.parametrize("ok, successes", NARROWED)
def test_a_narrowed_pattern_still_takes_its_success_and_no_failure(ok, successes):
    for reply in successes:
        assert re.search(ok, reply), reply
    assert not swallows(ok)
