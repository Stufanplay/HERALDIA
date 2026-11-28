"""A server test that inspects a command's failure reply must accept that reply in its own `ok`.

`server_smoke.run` waits on `f"{ok}|{ERROR_PATTERN}"` and **returns** the match, so a caller can
read a failure out of it today without having put that failure in `ok`. Half the battery relies on
exactly that:

    for _ in range(s.PLACE_ATTEMPTS):
        m = ctx.run(f"fill ... minecraft:stone", r"Successfully filled|No blocks")
        if "not loaded" not in m.string:        # <- read out of ERROR_PATTERN, not out of `ok`
            break

That retry works only while `run` is lenient. Once `run` fails by default -- which is where
this harness is now -- such a branch becomes dead code and the test dies on a slow chunk instead
of retrying. It would not die in the pass that turned the switch on: the branch is only taken when a
column happens not to be loaded, which a measured full pass hit in 2 of 17 sites. That is the worst
shape a change can have, so the invariant is checked statically instead of being left to a battery
run that is green for the wrong reason.

The rule: if a call's reply is inspected for one of the failure texts below, that call's own `ok`
must match it. 18 sites in the battery already did this before the rule existed; the other 17 were
brought in line with it.

This test needs no server and no .jar.
"""
import ast
import pathlib
import re

import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_path = list(sys.path)      # tools/smoke only while importing (see test_compat_mods.py)
sys.path.insert(0, str(ROOT / "tools" / "smoke"))
import server_smoke as s  # noqa: E402
sys.path[:] = _path

# The fragment a caller greps for -> a real reply of the dedicated server that carries it. The reply
# is what `ok` is tested against: a caller asking `"failed" in ...` of a "Test failed" reply whose
# `ok` holds "Test failed" is right, and testing `ok` against the bare fragment would call it wrong.
# The list lives in `server_smoke.FAILURE_REPLIES`, shared with test_discarded_ok_patterns.py.
FAILURE_REPLIES = s.FAILURE_REPLIES
QUOTED = re.compile('"([^"]*)"')
LOOKAHEAD = 8


def _is_run_call(node):
    """`run(...)`, `s.run(...)`, `ctx.run(...)`, `srv.run(...)` -- both spellings are in use."""
    if not isinstance(node, ast.Call):
        return False
    return ((isinstance(node.func, ast.Attribute) and node.func.attr == "run")
            or (isinstance(node.func, ast.Name) and node.func.id == "run"))


def _ok_pattern(node):
    """The `ok` argument: the last plain-string positional. Skips calls whose pattern is built at
    run time (an f-string or a variable), which this check cannot read and does not judge."""
    literals = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return literals[-1] if literals else None


def _sites():
    """Every `run()` call whose reply is inspected for a failure text, with the verdict for each."""
    for path in sorted(ROOT.glob("tools/**/*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:                     # not ours to police
            continue
        lines = source.split("\n")
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                assigned[id(node.value)] = node.targets[0].id
        for node in ast.walk(tree):
            if not _is_run_call(node):
                continue
            target = assigned.get(id(node))
            ok = _ok_pattern(node)
            if target is None or ok is None:     # a reply nobody keeps cannot be inspected
                continue
            # Stop at the next assignment to the same name: beyond it the checks belong to that call,
            # and attributing them here reports a site that is perfectly correct.
            reassigned = re.compile(rf"^\s*{re.escape(target)}\s*=[^=]")
            for line in lines[node.lineno:node.lineno + LOOKAHEAD]:
                if reassigned.match(line):
                    break
                if not re.search(rf"\b{target}\b\s*\.\s*(string|group)", line):
                    continue
                fragments = [f for f in QUOTED.findall(line) if f in FAILURE_REPLIES]
                if not fragments:
                    continue
                bare = isinstance(node.func, ast.Name)
                for fragment in fragments:
                    reply = FAILURE_REPLIES[fragment]
                    try:
                        covered = bool(re.search(ok, reply))
                    except re.error:
                        covered = False
                    yield path.relative_to(ROOT), node.lineno, fragment, ok, covered, bare
                break


def test_a_failure_that_is_read_is_a_failure_that_is_accepted():
    offenders = [f"{p}:{ln} reads {frag!r} (reply {FAILURE_REPLIES[frag]!r}) out of a wait whose ok is {ok!r}"
                 for p, ln, frag, ok, covered, _ in _sites() if not covered]
    assert not offenders, (
        "these waits read a failure reply they do not accept, so they depend on run() being lenient "
        "and break the moment it fails by default:\n  " + "\n  ".join(offenders))


def test_the_check_sees_the_sites_it_is_meant_to_see():
    """Guards the checker itself: were the AST walk or the window to stop matching, the test above
    would pass by finding nothing at all -- the way a deleted assertion passes."""
    sites = list(_sites())
    assert len(sites) >= 30, f"the checker found only {len(sites)} inspected replies; it has stopped seeing them"
    # Both spellings must still be reached. Naming the FORM and not the file is the point: every file
    # that holds a bare `run(...)` also holds `ctx.run(...)` ones, so asserting a file is in the list
    # passes just as well with bare calls no longer matched -- an assertion that guards nothing.
    assert any(bare for *_, bare in sites), "bare run(...) calls are no longer being scanned"
    assert any(not bare for *_, bare in sites), "attribute .run(...) calls are no longer being scanned"
    files = {str(p) for p, *_ in sites}
    assert any("village" in f for f in files), "the village tests are no longer being scanned"


MOD_LOG_LINE = ("[00:00:00] [Server thread/INFO]: Heraldia: village look: k id: placed 1, removed 0, "
                "left alone 2 (3 spots, 9 µs) (some chunks not loaded yet)")
UNLOADED_REPLY = "[00:00:00] [Server thread/INFO]: System chat: That position is not loaded"


@pytest.mark.parametrize("ok, reply, expected", [
    (r"Successfully filled|No blocks", "That position is not loaded", False),
    (r"Successfully filled|No blocks|not loaded(?! yet)", "That position is not loaded", True),
    (r"Generated structure", "That position is not loaded", False),
    (r"Test passed|Test failed", "Test failed", True),          # the fragment is "failed"; the reply matches
    (r"Test passed|Test failed", "That position is not loaded", False),
])
def test_coverage_is_judged_on_the_reply(ok, reply, expected):
    assert bool(re.search(ok, reply)) is expected


@pytest.mark.parametrize("ok", [
    r"Successfully filled|No blocks|not loaded(?! yet)",
    r"Generated structure|not loaded(?! yet)",
    r"Test passed|Test failed|not loaded(?! yet)",
])
def test_the_accepted_failure_does_not_swallow_the_mods_own_log_line(ok):
    """Why the patterns say `not loaded(?! yet)` and not a bare `not loaded`.

    `run` skips a line of the mod's own log ("[...]: Heraldia: ...") **unless `ok` matches it**, because
    such a line is no command's reply -- that is on record: one was taken as the reply to `/time query
    gametime` and killed caravans.py with a TypeError (CI, Nov 2026). The only string in the mod that
    carries "not loaded" is `Welcome.java`'s " (some chunks not loaded yet)", so a bare `not loaded` in
    `ok` would have made that line match, stopped the guard skipping it, and handed it back as the reply
    -- on `place structure` that means a retry of a command that had in fact worked, i.e. placing the
    structure twice. The negative lookahead keeps the vanilla reply and leaves the mod's line to the
    guard, which is what makes these edits neutral today rather than merely small."""
    assert re.search(ok, UNLOADED_REPLY), "the vanilla reply must still be accepted"
    assert not re.search(ok, MOD_LOG_LINE), "the mod's own log line must stay invisible to this wait"
