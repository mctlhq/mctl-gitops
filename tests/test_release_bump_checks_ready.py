"""release-bump readiness excludes the named own check run and nothing else.

Plain script: `python3 tests/test_release_bump_checks_ready.py`.

When auto-merge.yml enqueued release-bump PRs, its step was itself a pending
check run on the PR it waited for (mctl-gitops#2739, #2748), hence --own-check.
The enqueue now runs in the release workflows, whose wait script passes an
empty --own-check; that wiring, and the step that calls this script, are tested
in tests/test_release_bump_enqueue.py. Here: the script on check-run lists, with
mutants that must turn a case red.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-bump-checks-ready.py"
REQ = "cloudflare-plan,reserved-hosts,validate"
OWN = "auto-merge"
HEAD = "a" * 40


def run_for(name, status="completed", conclusion="success", i=[0]):
    i[0] += 1
    return {"id": i[0], "name": name, "status": status, "conclusion": conclusion}


def green():
    return [run_for(n) for n in REQ.split(",")] + [run_for("claude-review / review"), run_for("trivy")]


def own(status="in_progress", conclusion=None):
    return run_for(OWN, status, conclusion)


def verdict(runs, script=SCRIPT, expect="auto", raw=None, own_name=OWN):
    text = raw if raw is not None else "\n".join(json.dumps(r) for r in runs)
    args = [sys.executable, str(script), "--own-check", own_name, "--required", REQ]
    if expect == "auto":
        expect = len(runs) if raw is None else None
    if expect is not None:
        args += ["--expect", str(expect)]
    return subprocess.run(args, input=text, capture_output=True, text=True).returncode


def script_cases(script=SCRIPT):
    """(name, got exit code, want exit code)."""
    v = lambda *a, **k: verdict(*a, script=script, **k)
    c = []
    # (a) only the own check is pending
    c.append(("a: only own check pending -> ready", v(green() + [own()]), 0))
    c.append(("a: own check queued -> ready", v(green() + [own("queued")]), 0))
    c.append(("a: no own check at all -> ready", v(green()), 0))
    # An empty own name (release-bump-enqueue-wait.sh) excludes nothing.
    c.append(("a: empty own name, all green -> ready", v(green(), own_name=""), 0))
    c.append(("b: empty own name keeps a pending auto-merge run", v(green() + [own()], own_name=""), 10))
    c.append(("a: skipped and neutral are green", v(green() + [run_for("x", conclusion="skipped"), run_for("y", conclusion="neutral")]), 0))
    c.append(("a: a re-run supersedes an old failure", v(green() + [run_for("t", conclusion="failure"), run_for("t")]), 0))
    # (b) fail closed
    for st in ("queued", "in_progress", "waiting", "pending"):
        c.append((f"b: another check {st} -> wait", v(green() + [run_for("trivy2", st, None)]), 10))
    for concl in ("failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"):
        c.append((f"b: another check {concl} -> fail", v(green() + [run_for("trivy2", conclusion=concl)]), 11))
    c.append(("b: a re-run that is now failing wins over the older pass", v(green() + [run_for("t"), run_for("t", conclusion="failure")]), 11))
    for n in REQ.split(","):
        c.append((f"b: required {n} missing -> wait", v([r for r in green() if r["name"] != n] + [own()]), 10))
    c.append(("b: no check runs at all -> wait", v([]), 10))
    c.append(("b: completed without conclusion -> unknown", v(green() + [run_for("z", conclusion=None)]), 12))
    c.append(("b: unknown status -> unknown", v(green() + [run_for("z", "mystery", None)]), 12))
    c.append(("b: truncated list (expect > read) -> unknown", v(green(), expect=len(green()) + 1), 12))
    c.append(("b: not JSON -> unknown", v(None, raw="<html>502</html>"), 12))
    c.append(("b: truncated JSON -> unknown", v(None, raw='{"id": 1, "name": "validate", "sta'), 12))
    c.append(("b: entry without a name -> unknown", v(None, raw=json.dumps({"id": 1, "status": "completed", "conclusion": "success"})), 12))
    c.append(("b: unknown outranks a failure", v(green() + [run_for("z", conclusion=None), run_for("f", conclusion="failure")]), 12))
    # (c) exact own name only
    for other in ("auto-merge-lint", "auto-merge2", "Auto-Merge", "auto-merge ", "my-auto-merge", "auto-merg"):
        c.append((f"c: {other!r} pending is NOT excluded", v(green() + [run_for(other, "in_progress", None)]), 10))
        c.append((f"c: {other!r} failed is NOT excluded", v(green() + [run_for(other, conclusion="failure")]), 11))
    return c


def main():
    bad = [(n, g, w) for n, g, w in script_cases() if g != w]
    assert not bad, f"wrong verdicts: {bad}"
    # MUTANTS of the script: each must turn at least one case red.
    src = SCRIPT.read_text()
    mutants = {
        "own exclusion reverted": ('if r["name"] == own:\n            continue', 'if False:\n            continue'),
        "own exclusion widened to a prefix": ('if r["name"] == own:', 'if r["name"].startswith(own):'),
        "own exclusion widened to case-insensitive": ('if r["name"] == own:', 'if r["name"].lower() == own.lower():'),
        "failure ignored": ("elif isinstance(concl, str) and concl:\n            failed.append", "elif isinstance(concl, str) and concl:\n            pass; (lambda *_: 0)"),
        "unreadable treated as ok": ("return UNKNOWN, [f\"unreadable check run: {r!r}\"]", "continue"),
        "truncation ignored": ("if expect is not None and len(runs) != expect:", "if False:"),
        "non-JSON treated as ok": ('print(f"unknown: check runs are not JSON ({e})")\n        return UNKNOWN', 'return READY'),
        "missing required ignored": ("        if name not in latest:", "        if False:"),
        "pending ignored": ("        if st in PENDING:", "        if False:"),
    }
    with tempfile.TemporaryDirectory() as d:
        for name, (old, new) in mutants.items():
            assert src.count(old) == 1, f"mutant anchor {name}: {src.count(old)}"
            m = pathlib.Path(d) / "m.py"
            m.write_text(src.replace(old, new))
            red = [n for n, g, w in script_cases(script=m) if g != w]
            assert red, f"script mutant survives: {name}"
            print(f"mutant killed: {name} ({len(red)} red)")
    # Drift guard: the names are the job ids that tests/test_required_check_job_ids.py
    # pins as the required checks of ruleset main-protection (check name == job id,
    # no `name:`), so a renamed or dropped job fails here as well as there.
    for wf, jobs in ((".github/workflows/validate-manifests.yml", ["validate", "reserved-hosts"]),
                     (".github/workflows/cloudflare-plan.yml", ["cloudflare-plan"])):
        have = yaml.safe_load((ROOT / wf).read_text())["jobs"]
        for j in jobs:
            assert j in have, f"required check {j} has no job in {wf}"
            assert have[j].get("name", j) == j, f"job {j} in {wf} is named differently from its id"
    assert sorted(REQ.split(",")) == sorted(["validate", "reserved-hosts", "cloudflare-plan"])
    print("ok")


if __name__ == "__main__":
    sys.exit(main())
