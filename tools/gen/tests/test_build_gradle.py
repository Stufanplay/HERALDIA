"""What `build.gradle` has to say for the checks to be the checks they claim to be.

Two defects of `./gradlew clean build` that these guard against, both found by reading the build and both of the same
shape -- a task that passes green without having done its work:

* `testPesado` ran the mines tests against the real 26.3 terrain without the `heraldia.mcmeta` system property that
  tells them where the registry summary is, so they could not find it;
* `testGen` runs pytest, and several of those tests skip themselves when the registry summary is missing. Nothing gave
  it the summary and nothing ordered it against `clean`, which deletes `build/` (the summary and this task's own
  marker). With `parallel=true` the order was not defined.

A task whose tests skip is not a task that passed. These read the file as text on purpose: they must fail when someone
removes a line, with no Gradle and no daemon, in the seconds the per-session checks are allowed.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def build_gradle():
    with open(os.path.join(ROOT, "build.gradle"), encoding="utf-8") as f:
        return f.read()


def block(name):
    """The body of a task registration or configuration block, by brace depth."""
    text = build_gradle()
    m = re.search(r"(?:tasks\.register\('%s'|^%s)\s*[^\n{]*\{" % (name, name), text, re.M)
    assert m, f"no block for {name} in build.gradle"
    i, depth = m.end() - 1, 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    raise AssertionError(f"unbalanced braces in {name}")


def test_test_pesado_is_told_where_the_registry_summary_is():
    """Without it the mines tests on the real 26.3 terrain cannot find the summary (the second clean-build defect)."""
    body = block("testPesado")
    assert "systemProperty 'heraldia.mcmeta', mcmetaDir.get().absolutePath" in body, body
    assert "dependsOn fetchRegistries" in body, body


def test_test_pesado_asks_for_what_test_asks_for():
    """The two JUnit tasks run the same classes: whatever `test` needs to find, `testPesado` needs too."""
    for prop in re.findall(r"systemProperty '([^']+)'", block("test")):
        assert prop in block("testPesado"), prop


def test_test_gen_gets_the_summary_its_tests_need():
    """Several tests under tools/gen/tests skip themselves without it, and a skipped test guards nothing."""
    body = block("testGen")
    assert "environment 'MCMETA_SUMMARY', mcmetaDir.get().absolutePath" in body, body
    assert "dependsOn fetchRegistries" in body, body


def test_test_gen_runs_after_clean():
    """clean deletes build/, which holds this task's marker and the summary; with parallel=true nothing ordered them."""
    assert "mustRunAfter tasks.named('clean')" in block("testGen"), block("testGen")


def test_every_task_that_reads_the_summary_also_fetches_it():
    """A task that reads mcmetaDir without depending on fetchRegistries works only by luck of ordering."""
    text = build_gradle()
    for name in ("test", "testPesado", "testGen", "generateStructures"):
        body = block(name)
        if "mcmetaDir" in body or "MCMETA_SUMMARY" in body:
            assert "dependsOn fetchRegistries" in body, f"{name} reads the summary without fetching it"
    assert "mcmetaDir" in text
