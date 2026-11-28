"""A server test that throws away the reply of a Heraldia command must not have an `ok` that accepts the mod's own failure.

test_discarded_ok_patterns.py judges discarded replies against vanilla's failure replies (`server_smoke.FAILURE_REPLIES`,
what `ERROR_PATTERN` recognises). The mod's own refusals are a class that check cannot see: "Valor no válido para X",
"choice send: no recipe X", "Market stalls are not for rent on this server" match nothing in `ERROR_PATTERN`, so a
call whose `ok` accepts one carries on as if the command had worked, and nothing complains. A census of the tree when
this test landed found 35 such calls: 11 accepted a real failure of the command, 7 one that the next line happened to
check, 10 expected the refusal on purpose, 3 matched another command's text, and 4 were not Heraldia commands at all.

The failure texts are read from the source, not from a list kept by hand, so a new refusal is judged the day it is
added: every `sendFailure(...)` in src/main/java, its keys resolved through the `K`-style prefixes of its file and
looked up in the generator's own texts (`writer.texts`, the same dict the .jar's lang files are written from), plus its
string literals. Both languages are judged: the reply a test reads is in whatever language the source of the command
gets -- English for the console and for Carpet's players, as the server logs show ("Stall 1 is yours for 7 days",
"Repairing 8 places, a little at a time...") -- and the Spanish fallback where a client does not have the mod. Judging
both costs nothing and does not depend on knowing which one a given call gets.

The rule: a discarded `.run(cmd, ok)` whose command is a Heraldia command (`heraldia ` in its source) must not match
any of those texts, unless the line above says why: `# the refusal is the expected reply: ...`. The match is not
narrowed to the command's own refusals (the source does not say statically which handler a command reaches), so a
text from another command can match too; then the `ok` is narrowed anyway, which is cheap and keeps the check local.

What it cannot see is counted and pinned: `sendFailure` calls that build their text at run time (`UNRESOLVED`), and
the discarded calls whose `ok` is not a literal are already pinned by test_discarded_ok_patterns.NOT_LITERAL.

This test needs no server and no .jar.
"""
import ast
import pathlib
import re

import advancements
import uniques
import writer

ROOT = pathlib.Path(__file__).resolve().parents[3]
JAVA = ROOT / "src" / "main" / "java"
SKIPPED = ("tools/probes/",)          # probes, not tests (as in test_discarded_ok_patterns.py)
EXPECTED = "# the refusal is the expected reply:"
# sendFailure calls whose text is built at run time (a component made elsewhere, an exception's message): not judged.
UNRESOLVED = 5
_STR = r'"((?:[^"\\]|\\.)*)"'


class _Template:
    def __init__(self, sid):
        self.entities = [(0, 0, 0, {"id": "minecraft:zombie", "Tags": [f"{advancements.GUARDIAN_TAG}.{sid}"]})]


class _Registry:
    """Minimal registry, as in test_languages.py: one guardian per unique structure."""
    templates = {f"unicas/{sid}/x": _Template(sid) for sid, _ in uniques.modules()}


def _call(src, i):
    """The text of the call whose `(` is at src[i], up to its balanced `)`, string and char literals skipped."""
    depth, j = 0, i
    while j < len(src):
        c = src[j]
        if c == "'" and re.match(r"'(?:\\.|[^\\'])'", src[j:]):
            j += len(re.match(r"'(?:\\.|[^\\'])'", src[j:]).group(0))
            continue
        if c == '"':
            m = re.match(_STR, src[j:])
            j += len(m.group(0)) if m else 1
            continue
        depth += c == "("
        depth -= c == ")"
        if depth == 0:
            return src[i:j + 1]
        j += 1
    return src[i:]


def _constants():
    """(class, NAME) -> its initialiser, for every `static final String NAME = ...;` in the mod."""
    out = {}
    for f in JAVA.rglob("*.java"):
        for m in re.finditer(r"static final String (\w+)\s*=\s*([^;]+);", f.read_text(encoding="utf-8")):
            out.setdefault((f.stem, m.group(1)), m.group(2))
    return out


def _resolve(consts, cls, expr, depth=0):
    """A prefix expression such as `HeraldHouse.K + "caminos."` as the string it is, or None."""
    out = ""
    for part in (p.strip() for p in expr.split("+")):
        if part.startswith('"') and part.endswith('"'):
            out += part[1:-1]
            continue
        owner, _, name = part.rpartition(".")
        key = (owner or cls, name)
        if key not in consts or depth > 5:
            return None
        sub = _resolve(consts, owner or cls, consts[key], depth + 1)
        if sub is None:
            return None
        out += sub
    return out


def failures():
    """(keys, literals, unresolved): what the mod sends with sendFailure, read from its source."""
    consts, keys, literals, unresolved = _constants(), {}, {}, []
    for f in sorted(JAVA.rglob("*.java")):
        src, rel = f.read_text(encoding="utf-8"), f.relative_to(ROOT).as_posix()
        for m in re.finditer(r"sendFailure\(", src):
            call, where = _call(src, m.end() - 1), f"{rel}:{src.count(chr(10), 0, m.start()) + 1}"
            for km in re.finditer(r"((?:\w+\.)?[A-Z_]+)\s*\+\s*" + _STR, call):
                prefix = _resolve(consts, f.stem, km.group(1))
                if prefix is not None:
                    keys.setdefault(prefix + km.group(2), where)
            for lm in re.finditer(_STR, call):
                s_ = lm.group(1)
                if re.fullmatch(r"heraldia\.[\w.]+", s_):
                    keys.setdefault(s_, where)
                elif " " in s_:
                    literals.setdefault(s_, where)
            if "Texts.t" not in call and "translatable" not in call and not re.search(_STR, call):
                unresolved.append(where)
    return keys, literals, unresolved


def _reply(text):
    """A format text as the server prints it: each argument as a placeholder that matches no pattern word."""
    return re.sub(r"%(\d+\$)?[sd]", "X", text).replace("%%", "%")


def failure_texts():
    keys, literals, _ = failures()
    lang = writer.texts(_Registry)
    out = {}
    for k, where in keys.items():
        for code in ("en_us", "es_es"):
            if k in lang[code]:
                out.setdefault(_reply(lang[code][k]), (k, code, where))
    for text, where in literals.items():
        out.setdefault(text, (None, "literal", where))
    return out


def _discarded_heraldia(source):
    """(lineno, ok, the line above) of every discarded `.run(cmd, ok)` on a Heraldia command with a literal `ok`."""
    lines, out = source.split("\n"), []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "run" and len(node.value.args) > 1):
            cmd, ok = ast.get_source_segment(source, node.value.args[0]) or "", node.value.args[-1]
            if "heraldia " in cmd and isinstance(ok, ast.Constant) and isinstance(ok.value, str):
                out.append((node.lineno, ok.value, lines[node.lineno - 2].strip() if node.lineno > 1 else ""))
    return out


def _scan(texts):
    bad, expected, total = [], 0, 0
    for path in sorted(ROOT.glob("tools/**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIPPED):
            continue
        try:
            calls = _discarded_heraldia(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno, ok, above in calls:
            total += 1
            hit = next(((t, o) for t, o in texts.items() if re.search(ok, t)), None)
            if hit and above.startswith(EXPECTED):
                expected += 1
            elif hit:
                bad.append(f"{rel}:{lineno} ok={ok!r} accepts {hit[0][:90]!r} ({hit[1][0] or hit[1][1]}, {hit[1][2]})")
    return bad, expected, total


def test_no_discarded_heraldia_reply_accepts_a_mod_failure_unless_it_says_why():
    bad, _, _ = _scan(failure_texts())
    assert not bad, ("discarded replies of Heraldia commands whose ok accepts one of the mod's own failures; narrow the ok "
                     f"to the success, or if the refusal is what the test wants, say so on the line above ({EXPECTED} ...):\n  "
                     + "\n  ".join(bad))


def test_the_failures_it_cannot_read_have_a_number():
    _, _, unresolved = failures()
    assert len(unresolved) == UNRESOLVED, (
        f"{len(unresolved)} sendFailure calls build their text at run time (pinned: {UNRESOLVED}); this check cannot judge "
        "them, so a change in that number is worth a look before updating it:\n  " + "\n  ".join(unresolved))


def test_the_check_sees_what_it_is_meant_to_see():
    """Guards the checker itself: blind, it would pass by finding nothing."""
    keys, literals, _ = failures()
    texts = failure_texts()
    assert len(keys) >= 60 and len(literals) >= 5, (len(keys), len(literals))
    assert len(texts) >= 2 * len(keys) - 10, "most failure keys should have both an English and a Spanish text"
    _, expected, total = _scan(texts)
    assert total >= 100, f"only {total} discarded replies of Heraldia commands seen; the walk has stopped seeing them"
    assert expected >= 9, "the refusals the tests expect on purpose are no longer seen as such"


def test_the_holes_it_was_written_for_are_seen():
    """The shapes found by the census, each against the failure it swallowed."""
    texts = failure_texts()
    for ok, failure in [
        (r"guardadas por|Valor no válido", "Valor no válido para X: X"),
        (r"choice send: [^\n]*", "choice send: no recipe "),
        (r"Market stalls|Puestos del mercado", "Market stalls are not for rent on this server"),
        (r"heraldia|Herald|Heraldo|confirm", "This world already has its Herald's House, at X X X"),
    ]:
        assert failure in texts, failure
        assert re.search(ok, failure)
