"""scripts/ci-queue-latency.py against a recorded window (mctlhq/mctl-gitops#2993).

Checks the numbers on tests/fixtures/ci_queue_latency/window.json, that a failed
read is an error (exit 2) and never an empty report, and that each named mutation
of the script turns at least one case red. Plain script:
`python3 tests/test_ci_queue_latency.py`.
"""
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci-queue-latency.py"
FIXTURE = ROOT / "tests/fixtures/ci_queue_latency/window.json"


def load(source):
    mod = types.ModuleType("ci_queue_latency")
    mod.__file__ = str(SCRIPT)
    exec(compile(source, str(SCRIPT), "exec"), mod.__dict__)
    return mod


def run_cases(source):
    """Returns the list of failed case names for the given script source."""
    bad = []

    def check(name, cond):
        if not cond:
            bad.append(name)

    try:
        mod = load(source)
        import json
        m = mod.report(json.loads(FIXTURE.read_text()))
        mg = m["merge_group_start"]
        check("merge-group n", mg["n"] == 2)
        check("merge-group p50 is 330s (60s and 600s)", mg.get("p50") == 330)
        check("merge-group max is 600s", mg.get("max") == 600)
        q = m["queue_enqueue_to_merge"]
        check("queue latency is 1800s from the EARLIEST enqueue", q["n"] == 1 and q["max"] == 1800)
        r = m["release_dispatch_to_bump_merge"]
        check("release latency is 2400s", r["n"] == 1 and r["max"] == 2400)
        check("cancelled before start is 1", m["cancelled_before_start"] == 1)
        check("run with unreadable jobs is unknown, not zero", m["unknown_runs"] == 1)
        check("merge-group excludes the unreadable run", mg["n"] == 2)
        check("empty metric renders as not measured",
              "not measured" in mod.render(mod.report({"runs": [], "jobs": {}, "prs": [], "timelines": {}}), "w"))

        # A failed gh read must surface as ReadError / exit 2, not an empty window.
        with tempfile.TemporaryDirectory() as d:
            gh = pathlib.Path(d) / "gh"
            gh.write_text("#!/bin/sh\necho '[]'\necho boom >&2\nexit 1\n")
            gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{d}:{old}"
            try:
                try:
                    mod.gh_json("repos/x/y/actions/runs")
                    check("failed gh read raises ReadError", False)
                except mod.ReadError:
                    pass
            finally:
                os.environ["PATH"] = old
        check("unreadable fixture exits 2", mod.main(["--fixture", "/nonexistent.json"]) == 2)
    except Exception as e:  # a mutation may break the script outright; that is red too
        bad.append(f"exception: {type(e).__name__}: {e}")
    return bad


MUTATIONS = {
    "unknown run counted as zero": ('if rid not in jobs:', 'if False:'),
    "merge-group filter drops the event check": ('run["event"] == "merge_group" and start', 'start'),
    "queue uses latest enqueue event": ('seconds(min(events)', 'seconds(max(events)'),
    "failed gh read treated as success": ('if r.returncode != 0:', 'if False:'),
    "failed read exits 0": ('return 2', 'return 0'),
    "cancelled-before-start ignores start": ('and start is None', ''),
}

source = SCRIPT.read_text()
failures = []
base = run_cases(source)
if base:
    failures.append(f"baseline red: {base}")
for name, (old, new) in MUTATIONS.items():
    if source.count(old) < 1:
        failures.append(f"mutation '{name}': anchor not found in script")
        continue
    if not run_cases(source.replace(old, new, 1)):
        failures.append(f"mutation '{name}' stayed green")

if failures:
    print("FAIL")
    print("\n".join(failures))
    sys.exit(1)
print(f"ok: baseline green, {len(MUTATIONS)} mutations red")
