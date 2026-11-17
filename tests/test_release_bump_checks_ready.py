"""release-bump readiness excludes auto-merge's own check run and nothing else.

Plain script: `python3 tests/test_release_bump_checks_ready.py`.

auto-merge.yml's release-bump step is itself a pending check run on the PR it
waits for (mctl-gitops#2739, #2748). Two layers are tested, each with mutants
that must turn a case red:
  * scripts/release-bump-checks-ready.py on check-run lists;
  * the real workflow step, run with a fake gh, so the wiring (own name,
    unreadable reads, enqueue with expectedHeadOid) is covered too.
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-bump-checks-ready.py"
WF = ROOT / ".github/workflows/auto-merge.yml"
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


def step_script():
    doc = yaml.safe_load(WF.read_text())
    for step in doc["jobs"]["auto-merge"]["steps"]:
        if step.get("name", "").startswith("Enqueue release-bump PR"):
            return step["run"], step["env"]
    raise AssertionError("enqueue step not found")


def run_step(runs, *, total=None, runs_ok=True, head=HEAD, review_commit=None, script=None, enqueue_ok=True):
    """Run the real step with a fake gh. Returns (rc, enqueue calls, output)."""
    body, env_decl = step_script()
    body = script or body
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "runs").write_text("\n".join(json.dumps(r) for r in runs))
        (d / "total").write_text(str(len(runs) if total is None else total))
        gh = d / "bin" / "gh"
        gh.parent.mkdir()
        gh.write_text(
            "#!/bin/sh\n"
            'case "$*" in\n'
            f'  *"pr view"*) if [ -f "{d}/enqueue" ]; then echo "{head} MERGED PRID"; else echo "{head} OPEN PRID"; fi ;;\n'
            f'  *enqueuePullRequest*) echo "$*" >> "{d}/enqueue"; {"echo ok" if enqueue_ok else "echo refused; exit 1"} ;;\n'
            f'  *isInMergeQueue*) echo false ;;\n'
            f'  *"per_page=1 "*) cat "{d}/total" ;;\n'
            f'  *check-runs*) {"cat " + str(d / "runs") if runs_ok else "exit 1"} ;;\n'
            '  *) exit 1 ;;\n'
            "esac\n")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        sleep = d / "bin" / "sleep"  # a wait verdict must not stall the test: loop exits via deadline
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(sleep.stat().st_mode | stat.S_IEXEC)
        # SECONDS cannot be faked, so shrink the deadline and let `wait` loops expire.
        body = body.replace("SECONDS + 2700", "SECONDS + 1")
        body = body.replace("sleep 30", "sleep 1")
        env = {"PATH": f"{gh.parent}:{os.environ['PATH']}", "GH_TOKEN": "x", "REPO": "o/r", "PR": "7",
               "HEAD_SHA": HEAD, "REVIEW_COMMIT": review_commit or HEAD,
               "OWN_CHECK": env_decl["OWN_CHECK"], "REQUIRED_CHECKS": env_decl["REQUIRED_CHECKS"]}
        r = subprocess.run(["bash", "-c", body], env=env, capture_output=True, text=True, cwd=ROOT, timeout=60)
        calls = (d / "enqueue").read_text() if (d / "enqueue").exists() else ""
        return r.returncode, calls, r.stdout + r.stderr


def step_cases(script=None):
    def enq(rc_calls_out):
        rc, calls, _ = rc_calls_out
        return rc == 0 and "expectedHeadOid" in calls and f"h={HEAD}" in calls
    def noenq(rc_calls_out):
        rc, calls, _ = rc_calls_out
        return rc != 0 and calls == ""
    s = lambda *a, **k: run_step(*a, script=script, **k)
    c = []
    c.append(("step a: only own check pending enqueues the exact head", enq(s(green() + [own()])), True))
    c.append(("step b: another pending check does not enqueue", noenq(s(green() + [run_for("trivy2", "in_progress", None)])), True))
    c.append(("step b: another cancelled check does not enqueue", noenq(s(green() + [run_for("trivy2", conclusion="cancelled")])), True))
    c.append(("step b: missing required check does not enqueue", noenq(s([r for r in green() if r["name"] != "validate"] + [own()])), True))
    c.append(("step b: unreadable check list does not enqueue", noenq(s(green(), runs_ok=False)), True))
    c.append(("step b: truncated check list does not enqueue", noenq(s(green(), total=len(green()) + 5)), True))
    c.append(("step c: a similarly named pending check does not enqueue", noenq(s(green() + [run_for("auto-merge-lint", "in_progress", None)])), True))
    c.append(("step: refused enqueue fails the job", s(green() + [own()], enqueue_ok=False)[0] != 0, True))
    rc, calls, _ = s(green() + [own()], review_commit="b" * 40)
    c.append(("step: approval on another head does not enqueue", rc == 0 and calls == "", True))
    return c


def main():
    bad = [(n, g, w) for n, g, w in script_cases() + step_cases() if g != w]
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
    # MUTANTS of the workflow step.
    base, _ = step_script()
    wmut = {
        "own check name not passed": ('--own-check "$OWN_CHECK"', '--own-check "nothing"'),
        "unreadable check list ignored": ('echo "::error::could not read the check runs of ${HEAD_SHA}; not merging."\n      exit 1', "exit 0"),
        "not-ready verdict enqueues": ('*) echo "::error::#${PR} is not mergeable: ${verdict}"; exit 1 ;;', '*) rc=0 ;;'),
        "enqueue without head pin": ('-f h="$HEAD_SHA"', '-f h=""'),
        "review on another head accepted": ('if [ "$REVIEW_COMMIT" != "$HEAD_SHA" ]; then', 'if false; then'),
    }
    for name, (old, new) in wmut.items():
        assert base.count(old) == 1, f"mutant anchor {name}: {base.count(old)}"
        red = [n for n, g, w in step_cases(script=base.replace(old, new)) if g != w]
        assert red, f"step mutant survives: {name}"
        print(f"mutant killed: {name} ({len(red)} red)")
    # The step's own-check name is the job's real check name (name, else id).
    job = yaml.safe_load(WF.read_text())["jobs"]["auto-merge"]
    assert step_script()[1]["OWN_CHECK"] == job.get("name", "auto-merge"), "OWN_CHECK != the job's check name"
    # Required checks match the ruleset's documented list.
    assert step_script()[1]["REQUIRED_CHECKS"] == REQ
    print("ok")


if __name__ == "__main__":
    sys.exit(main())
