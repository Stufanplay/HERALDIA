# Heraldia — rules every session must follow

Read this first. `docs/DEVELOPMENT.md` has the detail; where the two disagree, this file wins.

## Branches and deployment (the owner's decision, 28-Nov-2026)

Three branches, in this order, and nothing skips a step:

1. **`develop` — where all development happens.** Every session works here (its own branch off
   `develop`, merged back into `develop`). **Work stays in `develop` until the owner says to promote it.**
   **CI does not run on `develop`**: no pull_request and no push trigger (`.github/workflows/ci.yml`).
   Merging into `develop` therefore never waits for CI.
2. **`pre-production` — where CI has to pass.** Permanent branch, never deleted. CI runs on every push
   to `pre-production` and on every PR against it, and **the full battery has to be green here**. This is
   the only place the heavy tests run.
   **When to promote is the orchestrator's call to propose** (the owner's decision, 28-Nov-2026): it
   judges when `develop` is at a good point, says so with what is going in, and **the owner confirms or
   says to wait**. Nothing is promoted without that confirmation. Promote **often and in small batches**:
   with no CI on `develop`, a big promotion turns one red job into a hunt across many changes. Good
   moments to propose: a self-contained piece of work has landed and the tree is quiet; several small
   fixes have piled up; something touched shared code (`_common/`, the generator, `build.gradle`, CI,
   resources) and nothing has exercised it yet; or the last promotion is days behind.
3. **`main` — release.** Only `pre-production` goes into `main`, **only with the owner's explicit
   approval**, and only when `pre-production` is green. Never push to `main` on your own initiative.
   `.github/workflows/publish.yml` lives on `main` and is never modified.

## Tests each session runs

**Minutes, not hours.** A session runs only quick checks on its own work: the unit tests it touched or
added (`python3 -m pytest tools/gen/tests/...`), `python3 tools/changelog.py check`, and the static
guards of what it changed. A couple of minutes in total.

Do **not** run, per session: the full battery (`tools/test.py --all`), the server tests
(`tools/smoke/*.py` with a `.jar`), `./gradlew build` with the heavy JUnit (`testPesado`), the
generation cost (`generation_cost.py`) or the play cost (`runtime_cost.py`). Those belong to
`pre-production`, where CI runs them, or to a run the owner asks for by name.

Write a test for what you fix, and prefer a unit test over a server test whenever both can see the
defect: the unit test is what will still run per session.

When only a server test can see the defect — it needs a world, a seed or a running server — say so in
the PR. The per-session net for that defect is **partial by nature**: the unit test covers the decision,
and the regression itself would only appear in `pre-production`. First case recorded: the inhabitant
lost in the terrain (#91), where `InhabitantsTest` covers `Inhabitants.rescue` (the 16-block line and the
guards) but only `tools/smoke/inhabitant_lost.py` finds the trap the seed's terrain makes.

## Sessions

**One at a time** (the owner's decision, 28-Nov-2026): the orchestrator does not start a session until
the previous one has finished. No parallel fan-out, whatever the queue looks like.

## Standing constraints

- **Never to `main`** without the owner's approval. Never touch `.github/workflows/publish.yml`.
- **No version bump**: `mod_version` stays as it is unless the owner says otherwise.
- **Never change what the world or the server saves**: structure, advancement, loot and tag ids,
  translation keys, configuration keys, NBT / SavedData / attachment keys, and the names and aliases of
  existing commands. New keys and new commands are fine.
- The Java root package `io.github.albertosa23.heraldia` and `maven_group` stay as they are.
- **The owner's real name must not appear in any file of the repository.** Write "the owner".
- **Performance is the hard gate**: no threshold is raised, relaxed or removed to make something pass —
  not the 100 ms barrier, not any other. If a step genuinely does not fit, stop and report it with figures.
- Never skip, disable or quarantine a test to get green. A failed CI job gets one re-run at most, and
  "flake" is not a root cause.
- Code, comments, tests and `docs/` are in English. `CHANGELOG.md` too.
