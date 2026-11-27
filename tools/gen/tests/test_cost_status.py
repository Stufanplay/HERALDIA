"""tools/cost_status.py: the three ends of a cost job (measured, skipped by path, died) read differently, from disk and
from GitHub's check runs, and a process killed by a signal leaves its phase written down."""
import json, os, signal, subprocess, sys, textwrap, time

TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(TOOLS)
import cost_status as cs   # noqa: E402


def outcome(tmp_path, step=None):
    return cs.verdict(cs.read_status(str(tmp_path)), "coste", step)


def test_measured_pass_and_over_the_limit(tmp_path):
    p = cs.Progress(str(tmp_path), "coste")
    p.phase("pass 1 (sin Heraldia)")
    p.finish(True, "overcost +2.5% (limit +19.7%)")
    assert outcome(tmp_path, "success")[:2] == ("MEASURED", "notice")
    p = cs.Progress(str(tmp_path), "coste")
    p.finish(False, "overcost +30% (limit +19.7%)")
    o, level, text = outcome(tmp_path, "failure")
    assert (o, level) == ("MEASURED", "error") and "over the limit" in text and "+30%" in text


def test_skipped_says_why(tmp_path):
    cs.skip(str(tmp_path), "coste", "none of the 3 changed file(s) is in COST_PATHS")
    o, level, text = outcome(tmp_path, "skipped")
    assert (o, level) == ("SKIPPED", "notice") and "none of the 3" in text


def test_started_and_never_finished_is_died_with_its_phase(tmp_path):
    p = cs.Progress(str(tmp_path), "coste")
    p.phase("pass 2 (con Heraldia)")
    p.phase("pass with Heraldia: zone aldea")
    p.note("stopping the server")             # cleanup does not move the phase
    o, level, text = outcome(tmp_path, "failure")
    assert (o, level) == ("DIED", "error") and "'pass with Heraldia: zone aldea'" in text and "without a word" in text


def test_no_status_file_is_died(tmp_path):
    assert outcome(tmp_path)[0] == "DIED"


def test_a_pass_that_then_fails_its_step_is_not_a_pass(tmp_path):
    p = cs.Progress(str(tmp_path), "juego")
    p.finish(True, "ok")
    assert outcome(tmp_path, "failure")[0] == "DIED"
    assert outcome(tmp_path, "cancelled")[0] == "DIED"
    assert outcome(tmp_path, "success")[0] == "MEASURED"


CHILD = textwrap.dedent("""
    import sys, time
    sys.path.append(sys.argv[1])
    import cost_status
    def main(argv=None):
        cost_status.start(sys.argv[2], "coste")
        cost_status.phase("pass 1 (sin Heraldia)")
        if sys.argv[3] == "raise":
            raise SystemExit("the server shut down early")
        print("READY", flush=True)
        try:
            time.sleep(60)
        finally:
            cost_status.note("stopping the server")
    sys.exit(cost_status.guard(main))
""")


def run_child(tmp_path, mode):
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    out = tmp_path / "out"
    p = subprocess.Popen([sys.executable, str(script), TOOLS, str(out), mode], stdout=subprocess.PIPE, text=True)
    return p, out


def test_a_signal_is_written_down_with_the_phase(tmp_path):
    for sig in (signal.SIGTERM, signal.SIGINT):
        p, out = run_child(tmp_path, "wait")
        assert p.stdout.readline().startswith("PROGRESS")
        while not p.stdout.readline().startswith("READY"):
            pass
        p.send_signal(sig)
        assert p.wait(timeout=20) == 128 + sig
        o, _, text = cs.verdict(cs.read_status(str(out)), "coste", "failure")
        assert o == "DIED" and sig.name in text and "'pass 1 (sin Heraldia)'" in text, text


def test_sigkill_leaves_the_last_phase_on_disk(tmp_path):
    p, out = run_child(tmp_path, "wait")
    while not p.stdout.readline().startswith("READY"):
        pass
    p.kill()
    p.wait(timeout=20)
    o, _, text = cs.verdict(cs.read_status(str(out)), "coste", "failure")
    assert o == "DIED" and "without a word" in text and "'pass 1 (sin Heraldia)'" in text
    assert "pass 1 (sin Heraldia)" in (out / cs.PROGRESS_FILE).read_text()


def test_an_exception_is_written_down(tmp_path):
    p, out = run_child(tmp_path, "raise")
    p.communicate(timeout=20)
    assert p.returncode == 1
    o, _, text = cs.verdict(cs.read_status(str(out)), "coste", "failure")
    assert o == "DIED" and "the server shut down early" in text


def test_report_writes_one_line_and_its_exit_code(tmp_path, capsys, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    cs.skip(str(tmp_path), "juego", "100% sure\nsecond line")
    assert cs.report(str(tmp_path), "juego", "skipped") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("::notice title=COST-VERDICT juego SKIPPED::") and "%25" in out[0] and "%0A" in out[0]
    assert out[1].startswith("COST-VERDICT juego SKIPPED: ")
    assert (tmp_path / cs.VERDICT_FILE).read_text().startswith("COST-VERDICT juego SKIPPED")
    assert "COST-VERDICT juego SKIPPED" in summary.read_text()
    (tmp_path / cs.STATUS_FILE).unlink()
    assert cs.report(str(tmp_path), "juego", "failure") == 1


def ann(outcome_word, msg="m"):
    return {"title": f"COST-VERDICT coste {outcome_word}", "message": msg}


def test_check_runs_from_outside():
    done = {"status": "completed", "conclusion": "success"}
    assert cs.classify_check_run(done, [ann("MEASURED")])[0] == "MEASURED"
    assert cs.classify_check_run(done, [ann("SKIPPED"), {"title": "other", "message": "x"}])[0] == "SKIPPED"
    assert cs.classify_check_run(dict(done, conclusion="failure"), [ann("DIED")])[0] == "DIED"
    # the runner was lost: no verdict annotation at all
    assert cs.classify_check_run(dict(done, conclusion="failure"), [])[0] == "DIED"
    assert cs.classify_check_run(dict(done, conclusion="cancelled"), [])[0] == "DIED"
    # a native skip (a needed job failed) neither measured nor said why
    assert cs.classify_check_run(dict(done, conclusion="skipped"), [])[0] == "NOT-RUN"
    assert cs.classify_check_run({"status": "in_progress"}, [])[0] == "RUNNING"
    assert cs.classify_check_run(done, [ann("MEASURED"), ann("MEASURED")])[0] == "DIED"


def test_ci_reads_gh(tmp_path, monkeypatch, capsys):
    """`ci` against a fake gh: one job measured, one skipped -> 0; one completed without its annotation -> 1."""
    runs = {"check_runs": [
        {"id": 1, "name": "Coste de generación (con y sin Heraldia)", "status": "completed", "conclusion": "success",
         "started_at": "2026-11-27T10:00:00Z"},
        {"id": 2, "name": "Coste de jugar (tiempo por tick con y sin Heraldia) · saltado por ruta", "status": "completed",
         "conclusion": "success", "started_at": "2026-11-27T10:00:00Z"}]}
    answers = {"repos/o/r/commits/abc/check-runs?per_page=100": [runs],
               "repos/o/r/check-runs/1/annotations?per_page=100": [[ann("MEASURED")]],
               "repos/o/r/check-runs/2/annotations?per_page=100": [[{"title": "COST-VERDICT juego SKIPPED", "message": "s"}]]}
    monkeypatch.setattr(cs, "_gh", lambda path: answers[path])
    assert cs.ci("o/r", "abc") == 0
    answers["repos/o/r/check-runs/1/annotations?per_page=100"] = [[]]
    runs["check_runs"][0]["conclusion"] = "failure"
    assert cs.ci("o/r", "abc") == 1
    out = capsys.readouterr().out
    assert "coste: DIED" in out and "juego: SKIPPED" in out


def test_the_skip_step_and_the_verdict_step_make_one_annotation(tmp_path, capsys, monkeypatch):
    """CI runs `skip` and then `verdict` (if: always()): together they must leave exactly one COST-VERDICT annotation,
    or `ci` reads the job as DIED."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cs.main(["skip", "--job", "coste", "--output", str(tmp_path), "--reason", "r"]) == 0
    assert cs.main(["verdict", "--job", "coste", "--output", str(tmp_path), "--step-outcome", "skipped"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert sum(l.startswith("::notice title=COST-VERDICT") or l.startswith("::error title=COST-VERDICT") for l in lines) == 1
