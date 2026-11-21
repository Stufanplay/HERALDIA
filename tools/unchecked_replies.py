#!/usr/bin/env python3
"""How many of the server tests' command replies nobody ever looks at.

Counts, under `tools/`, every call whose attribute name is `run` (`ctx.run(...)`, `c.run(...)`, `s.run(...)`) that sits
directly inside an `ast.Expr` statement -- that is, a `.run(...)` whose parent node is an `Expr`, so its return value is
thrown away. That is the whole measurement: no type checking, no import following, so an unrelated `something.run(...)`
would be counted too.

Why it is worth knowing: `server_smoke.run` waits for `ok` **or** `ERROR_PATTERN` and **returns** whichever came first,
raising nothing. A caller that does not read what came back therefore accepts any failure of its command and carries on
as if it had worked. `server_smoke.must` is the same wait with the reply asserted.

The caveat, which matters as much as the number: a discarded reply is not a fault by itself. Most of these commands are
set-up (`forceload`, `fill`, `gamerule`, `tp`) and nothing later would be right if they had failed, so the test would
usually still go red -- just somewhere else, and for the wrong reason. This counts the size of the surface, not the
faults on it.

Deliberately not wired into CI: an instrument to look through, not a barrier to pass. Run it by hand.

Usage:
  python3 tools/unchecked_replies.py            # the total and the count per file
  python3 tools/unchecked_replies.py --lines     # also every file:line
"""
import argparse, ast, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def discarded(path):
    """The lines of `path` holding a `.run(...)` whose parent node is an `ast.Expr` (its reply is thrown away)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "run"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", action="store_true", help="print every file:line, not only the counts")
    a = ap.parse_args()
    total, files = 0, []
    for base, _, names in os.walk(os.path.join(ROOT, "tools")):
        if "__pycache__" in base:
            continue
        for n in sorted(names):
            if not n.endswith(".py"):
                continue
            path = os.path.join(base, n)
            lines = discarded(path)
            if lines:
                files.append((os.path.relpath(path, ROOT), lines))
                total += len(lines)
    for rel, lines in sorted(files, key=lambda f: -len(f[1])):
        print(f"{len(lines):5d}  {rel}")
        if a.lines:
            for ln in lines:
                print(f"         {rel}:{ln}")
    print(f"{total:5d}  TOTAL discarded .run(...) replies in {len(files)} files")


if __name__ == "__main__":
    main()
