"""The status of a cost job (tools/smoke/generation_cost.py, CI job "coste"; tools/smoke/runtime_cost.py, CI job "juego"),
written so that the three ways such a job can end read differently from outside, without downloading anything:

  MEASURED  it ran and measured: the comparison with the reference passed or was over the limit (with its figures).
  SKIPPED   it was skipped by path: no changed file is one the cost depends on (with the reason).
  DIED      it started and did not finish measuring (with the last phase it reached and how it ended: an exception, a
            signal, or no word at all, which is what a SIGKILL, the kernel's OOM killer or a lost runner leave).

Before, the three looked alike: a job skipped by path is a grey "skipped" with no text, and a job that died before
writing its summary left an artifact with only the last server log, or no artifact at all.

How it works. The measuring script calls start() as its first act, which writes <output>/estado.json ("started") and
the first line of <output>/progreso.log; every phase() rewrites the status and appends a line (flushed and fsynced, so
it is on disk whatever kills the process next); finish() writes the result. A SIGTERM, SIGINT or SIGHUP is written down
before the process exits. Then the CI step `verdict` (if: always()) reads the status and prints ONE line,
"COST-VERDICT <job> <MEASURED|SKIPPED|DIED>: ...", as a GitHub annotation on the job's check run, in the job summary and
in <output>/veredicto.txt. A job that has no such annotation once completed did not reach its verdict step: its runner
was lost (that is DIED too, and `ci` says so).

Usage:
  python3 tools/cost_status.py skip --job coste --output build/coste --reason "no changed file is in COST_PATHS"
  python3 tools/cost_status.py verdict --job coste --output build/coste --step-outcome failure
  python3 tools/cost_status.py ci --repo OWNER/REPO --sha SHA      # the verdict of each cost job of a commit's CI run (gh)

Only the standard library: the skip step runs it on a bare runner. The functions are tested in
tools/gen/tests/test_cost_status.py.
"""
import argparse, json, os, signal, subprocess, sys, time

STATUS_FILE, PROGRESS_FILE, VERDICT_FILE = "estado.json", "progreso.log", "veredicto.txt"
MARK = "COST-VERDICT"
# The cost jobs of .github/workflows/ci.yml: job id -> what it measures (and the start of its check run's name).
JOBS = {"coste": "Coste de generación", "juego": "Coste de jugar"}

_current = None


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path, data):
    """Write `data` as JSON to `path` atomically (a reader sees the old file or the new one, never half of one)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_status(output):
    path = os.path.join(output, STATUS_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        return {"state": "unreadable", "error": f"{type(e).__name__}: {e}"}


class Progress:
    """The status of one measuring run in `output`. Use the module functions (start, phase, finish), not this directly."""

    def __init__(self, output, job):
        self.output, self.job = output, job
        os.makedirs(output, exist_ok=True)
        self.status = {"job": job, "state": "started", "phase": "start", "started": _now(), "updated": _now(),
                       "pid": os.getpid(), "phases": 0}
        open(os.path.join(output, PROGRESS_FILE), "w", encoding="utf-8").close()
        self._save("start")

    def _save(self, line):
        self.status["updated"] = _now()
        _write_json(os.path.join(self.output, STATUS_FILE), self.status)
        with open(os.path.join(self.output, PROGRESS_FILE), "a", encoding="utf-8") as f:
            f.write(f"{self.status['updated']} {line}\n")
            f.flush()
            os.fsync(f.fileno())
        print(f"PROGRESS {self.job}: {line}", flush=True)

    def phase(self, name, detail=None):
        self.status.update(phase=name, phases=self.status["phases"] + 1)
        self._save(name + (f": {detail}" if detail else ""))

    def note(self, text):
        """A line in the progress log that does not change the phase: cleanup (stopping a server) after a failure must
        not hide the phase the failure happened in."""
        self._save(f"({self.status['phase']}) {text}")

    def finish(self, ok, text):
        self.status.update(state="measured", ok=bool(ok), text=text)
        self._save(f"measured, {'pass' if ok else 'over the limit'}: {text}")

    def died(self, how, error=None):
        if self.status["state"] != "started":
            return                          # already finished (or already recorded how it died)
        self.status.update(state="died", how=how, **({"error": error} if error else {}))
        self._save(f"died in phase {self.status['phase']!r} ({how})" + (f": {error}" if error else ""))


def start(output, job, signals=True):
    """Starts the status of a measuring run (the first thing the script does, before preparing the server). With
    `signals`, a SIGTERM/SIGINT/SIGHUP is written down and then ends the process as SystemExit (so the script's
    `finally` blocks still stop its server)."""
    global _current
    _current = Progress(output, job)
    if signals:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, _on_signal)
    return _current


def _on_signal(signum, frame):
    name = signal.Signals(signum).name
    if _current:
        _current.died(f"signal {name}")
    signal.signal(signum, signal.SIG_DFL)   # a second one ends it at once
    raise SystemExit(128 + signum)


def phase(name, detail=None):
    """Records that the run has reached `name` (no-op if start() was not called: local runs without --output)."""
    if _current:
        _current.phase(name, detail)


def note(text):
    """A progress line that keeps the current phase (no-op without start())."""
    if _current:
        _current.note(text)


def finish(ok, text):
    if _current:
        _current.finish(ok, text)


def died(how, error=None):
    if _current:
        _current.died(how, error)


def guard(main, argv=None):
    """Runs main(argv) and, if it raises, writes down how it died before letting the exception go on."""
    try:
        return main(argv)
    except SystemExit as e:
        if e.code not in (0, None):
            died("exit", str(e.code))
        raise
    except BaseException as e:
        died("exception", f"{type(e).__name__}: {e}")
        raise


def verdict(status, job, step_outcome=None):
    """(outcome, level, text) for a status read from disk: outcome MEASURED/SKIPPED/DIED, level notice/warning/error."""
    if status is None:
        return "DIED", "error", (f"{job} left no {STATUS_FILE}: it died before starting to measure (or its measuring "
                                 f"step never ran; step outcome {step_outcome or 'unknown'})")
    state = status.get("state")
    where = f"in phase {status.get('phase')!r} after {status.get('phases', 0)} phases (last progress {status.get('updated')})"
    if state == "skipped":
        return "SKIPPED", "notice", f"{job} skipped by path: {status.get('reason')}"
    if state == "measured":
        if step_outcome not in (None, "", "success", "failure"):
            return "DIED", "error", f"{job} measured but its step ended {step_outcome}: {status.get('text')}"
        if status.get("ok") and step_outcome == "failure":
            return "DIED", "error", f"{job} measured and passed, then its step failed: {status.get('text')}"
        if status.get("ok"):
            return "MEASURED", "notice", f"{job} measured, pass: {status.get('text')}"
        return "MEASURED", "error", f"{job} measured, over the limit: {status.get('text')}"
    if state == "died":
        return "DIED", "error", f"{job} died {where}: {status.get('how')}" + (
            f": {status['error']}" if status.get("error") else "")
    if state == "started":
        return "DIED", "error", (f"{job} died {where} without a word (killed with no chance to write: SIGKILL, the OOM "
                                 f"killer or the job's time limit; step outcome {step_outcome or 'unknown'})")
    return "DIED", "error", f"{job}: status {state!r} in {STATUS_FILE} ({status.get('error', '')})"


def _escape(text):
    """A GitHub workflow command's message: %, CR and LF are escaped."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(output, job, step_outcome=None):
    """Prints the verdict line (and its annotation), appends it to the job summary and writes veredicto.txt. Exit code:
    0 for MEASURED (the measuring step already carries pass or fail) and SKIPPED, 1 for DIED."""
    outcome, level, text = verdict(read_status(output), job, step_outcome)
    line = f"{MARK} {job} {outcome}: {text}"
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title={MARK} {job} {outcome}::{_escape(line)}", flush=True)
    print(line, flush=True)
    os.makedirs(output, exist_ok=True)
    with open(os.path.join(output, VERDICT_FILE), "w", encoding="utf-8") as f:
        f.write(line + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"\n**{MARK} {job} {outcome}**: {text}\n")
    return 1 if outcome == "DIED" else 0


def skip(output, job, reason):
    os.makedirs(output, exist_ok=True)
    _write_json(os.path.join(output, STATUS_FILE),
                {"job": job, "state": "skipped", "reason": reason, "started": _now(), "updated": _now()})


# ---------------------------------------------------------------- from outside (the CI run of a commit)

def classify_check_run(run, annotations):
    """(outcome, text) of one cost job's check run from GitHub: its verdict annotation if it has one; otherwise what its
    conclusion allows to say (a completed run with no verdict annotation did not reach its verdict step: DIED)."""
    marks = [a for a in annotations if (a.get("title") or "").startswith(MARK)]
    if run.get("status") != "completed":
        return "RUNNING", f"{run.get('status')}"
    if len(marks) == 1:
        title = marks[0]["title"].split()
        return (title[2] if len(title) > 2 else "?"), marks[0].get("message", "")
    if len(marks) > 1:
        return "DIED", f"{len(marks)} verdict annotations (expected one): " + " | ".join(m.get("message", "") for m in marks)
    if run.get("conclusion") == "skipped":
        return "NOT-RUN", "the job itself was skipped (a job it needs failed or was cancelled): it neither measured nor said why"
    return "DIED", (f"conclusion {run.get('conclusion')} and no {MARK} annotation: the job never reached its verdict "
                    f"step (runner lost, cancelled before it, or a step before the measurement failed)")


def _gh(path):
    """The pages of a GitHub API listing, one JSON document each (gh api --paginate --slurp, gh 2.48 or later)."""
    out = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"gh api {path}: {out.stderr.strip()}")
    return json.loads(out.stdout) if out.stdout.strip() else []


def ci(repo, sha):
    """Prints, for each cost job of the CI run of `sha`, its check run's conclusion and its verdict. Exit code 0 only if
    every cost job is MEASURED or SKIPPED (a measurement over the limit is MEASURED: it ran)."""
    runs = []
    for d in _gh(f"repos/{repo}/commits/{sha}/check-runs?per_page=100"):
        runs += d.get("check_runs", []) if isinstance(d, dict) else []
    bad, found = 0, 0
    for job, title in JOBS.items():
        mine = [r for r in runs if (r.get("name") or "").startswith(title)]
        if not mine:
            print(f"{job}: no check run named '{title}...' for {sha}")
            bad += 1
            continue
        r = max(mine, key=lambda r: r.get("started_at") or "")
        found += 1
        ann = []
        for d in _gh(f"repos/{repo}/check-runs/{r['id']}/annotations?per_page=100"):
            ann += d if isinstance(d, list) else []
        outcome, text = classify_check_run(r, ann)
        print(f"{job}: {outcome} (check run {r['id']} '{r.get('name')}', {r.get('conclusion') or r.get('status')}): {text}")
        bad += outcome not in ("MEASURED", "SKIPPED")
    return 1 if bad or not found else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("skip", help="writes the status of a job skipped by path")
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--reason", required=True)
    p = sub.add_parser("verdict", help="reads the status and prints the one verdict line")
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--step-outcome", default=None, help="steps.<measuring step>.outcome (success, failure, cancelled, skipped)")
    p = sub.add_parser("ci", help="the verdict of each cost job of a commit's CI run, from GitHub (needs gh)")
    p.add_argument("--repo", required=True)
    p.add_argument("--sha", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "skip":
        skip(a.output, a.job, a.reason)       # the verdict (the one annotation) is the job's last step, not this
        print(f"{a.job}: skipped by path, written to {os.path.join(a.output, STATUS_FILE)}: {a.reason}", flush=True)
        return 0
    if a.cmd == "verdict":
        return report(a.output, a.job, a.step_outcome or None)
    return ci(a.repo, a.sha)


if __name__ == "__main__":
    sys.exit(main())
