"""village_terrain.py's terrain fit over several world seeds, in its measure mode (prints, compares nothing): the forest
or taiga village nearest the origin of each seed, its doors within a step of their street, and each door that is not,
by name. To tell whether a change moves the fit of villages in general or only that of the test's own village
(FIT_SEED = "heraldia"), run it with the same seeds on both .jars.

Usage: wfit.py <work> <jar> <seed> [<seed> ...]   (HERALDIA pointing at the repository; Java 25 on the PATH)
Not a test, not run by CI (tools/probes/README.md). ~1.5 min a seed.
"""
import os, sys
ROOT = os.environ.get("HERALDIA", "/home/user/heraldia")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
import village_terrain as vt


def main():
    work, jar, seeds = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3:]
    for seed in seeds:
        vt.FIT_SEED = seed
        fails = []
        print(f"SEED {seed}", flush=True)
        vt.terrain_fit(jar, os.path.join(work, seed), fails, True)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
