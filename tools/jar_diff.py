#!/usr/bin/env python3
"""What a change really changes in the built mod: the data pack of two jars compared file by file.

    python3 tools/jar_diff.py BEFORE.jar AFTER.jar [--list KIND]

A design change says "only the streets" or "the houses are what they were". This says whether that is true: how many
data files are new, removed and changed, grouped by kind (the folder that names what a template is: houses, specials,
streets, plaza, decor, a unique's name...), and that everything else is identical byte for byte. The generator shares
one random source per village style, so a single new draw anywhere changes every piece built after it: run this before
handing a design change in, and put its output in the pull request. `--list KIND` prints the files of one kind.

Not a test and not run by CI: a jar of `develop` has to be built to compare with (`./gradlew build -x test` in a
checkout of it)."""
import argparse, collections, sys, zipfile

ROOT = "data/heraldia/"


def kind(name):
    """The kind of a data file: for a structure template, its family folder (`<style>/houses/small_0.nbt` → houses,
    `unicas/castillo/...` → unicas/castillo); for anything else, its registry folder (loot_table, worldgen/template_pool...)."""
    p = name[len(ROOT):].split("/")
    if p[0] != "structure":
        return "/".join(p[:2]) if p[0] == "worldgen" and len(p) > 2 else p[0]
    p = p[1:]
    if p[0] in ("unicas", "medianas", "minas", "costa", "casa_heraldo"):
        return "/".join(p[:2]) if len(p) > 2 else p[0]
    return p[1] if len(p) > 2 else p[0]


def compare(before, after):
    a, b = zipfile.ZipFile(before), zipfile.ZipFile(after)
    na = {n for n in a.namelist() if n.startswith(ROOT) and not n.endswith("/")}
    nb = {n for n in b.namelist() if n.startswith(ROOT) and not n.endswith("/")}
    changed = sorted(n for n in na & nb if a.read(n) != b.read(n))
    return na, nb, sorted(nb - na), sorted(na - nb), changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--list", metavar="KIND", help="print the new, removed and changed files of this kind")
    a = ap.parse_args()
    na, nb, new, gone, changed = compare(a.before, a.after)
    total = collections.Counter(kind(n) for n in na | nb)
    print(f"data files: {len(na)} -> {len(nb)}; {len(new)} new, {len(gone)} removed, {len(changed)} changed, "
          f"{len(na & nb) - len(changed)} identical")
    for label, names in (("new", new), ("removed", gone), ("changed", changed)):
        by = collections.Counter(kind(n) for n in names)
        if by:
            print(f"{label}: " + ", ".join(f"{k} {v} of {total[k]}" for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))))
    touched = {kind(n) for n in new + gone + changed}
    same = sorted(k for k in total if k not in touched)
    print(f"untouched kinds ({len(same)}): " + ", ".join(same))
    if a.list:
        for label, names in (("new", new), ("removed", gone), ("changed", changed)):
            for n in names:
                if kind(n) == a.list:
                    print(f"  {label}: {n[len(ROOT):]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
