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


def test_a_retry_round_keeps_the_first_rounds_passes_in_the_partial(tmp_path, monkeypatch):
    """The retry (a second call to measure()) must not overwrite *.parcial.json with its own passes only: a job killed
    in the retry round keeps the first round. For juego that round does not fit its time limit, by arithmetic (46-47 min
    measured in CI for one round, ~85 with the retry, against 60); not observed in CI, where no run has retried yet."""
    _path = list(sys.path)      # tools/smoke only while importing (see test_compat_mods.py)
    sys.path.insert(0, os.path.join(TOOLS, "smoke"))
    import generation_cost as g, runtime_cost as rc
    sys.path[:] = _path
    (tmp_path / "server.properties").write_text("level-seed=x\n")
    (tmp_path / "config").mkdir()
    for m in (g, rc):
        monkeypatch.setattr(m.s, "prepare", lambda *a: "launcher")
        monkeypatch.setattr(m.modrinth, "install", lambda *a: None)
        monkeypatch.setattr(m, "OUTPUT", str(tmp_path))
    monkeypatch.setattr(g, "_measured", {"sin": [], "con": []})
    monkeypatch.setattr(g, "sweep", lambda work, jar, with_it, launcher: {"con": with_it, "chunks": 1, "segundos": 1.0})
    g.measure("jar", str(tmp_path), 3)
    g.measure("jar", str(tmp_path), 3)
    p = json.loads((tmp_path / "coste_generacion.parcial.json").read_text())
    assert (len(p["sin"]), len(p["con"])) == (6, 6)
    monkeypatch.setattr(rc, "_measured", [])
    monkeypatch.setattr(rc, "sweep", lambda work, jar, with_it, launcher, pos, s_, w_, e_: ({"escenarios": {}}, pos or {}))
    rc.measure("jar", str(tmp_path), 1, 60, 30, True)
    rc.measure("jar", str(tmp_path), 1, 60, 30, False, {})
    p = json.loads((tmp_path / "coste_juego.parcial.json").read_text())
    assert [x["con"] for x in p["pasadas"]] == [True, False, True, False]


def test_a_died_verdict_names_the_servers_own_reason(tmp_path, capsys):
    """CI 44965032309: juego died in 18 s on "FAILED TO BIND TO PORT"; the verdict now carries that line (or the first
    ERROR line) of the newest server log in --output, so the annotation says why without opening anything."""
    p = cs.Progress(str(tmp_path), "juego")
    p.phase("pass with Heraldia: starting the server")
    p.died("exit", "the server shut down early")
    (tmp_path / "latest.log").write_text("[00:12:05] [Server thread/INFO]: Starting Minecraft server on *:57181\n"
                                         "[00:12:05] [Server thread/WARN]: **** FAILED TO BIND TO PORT!\n"
                                         "[00:12:05] [Server thread/ERROR]: Encountered an unexpected exception\n")
    assert cs.report(str(tmp_path), "juego", "failure") == 1
    out = capsys.readouterr().out
    assert "starting the server" in out and "server log, latest.log: [00:12:05] [Server thread/WARN]: **** FAILED TO BIND" in out
    (tmp_path / "latest.log").unlink()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "01-with.log").write_text("x\n[Server thread/ERROR]: boom\n")
    cs.report(str(tmp_path), "juego", "failure")
    assert "server log, logs/01-with.log: [Server thread/ERROR]: boom" in capsys.readouterr().out
    cs.Progress(str(tmp_path), "juego").finish(True, "ok")                  # a measurement carries no hint
    cs.report(str(tmp_path), "juego", "success")
    assert "server log" not in capsys.readouterr().out
