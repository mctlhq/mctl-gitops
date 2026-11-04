"""release-gate (mctlhq/mctl-agents#1007): green on a converged tree, red on
mutations, and actually wired into both bump workflows.

Plain script like the other release-deploy tests: `python3 tests/test_release_gate.py`.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/release-gate.py"
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(f"{name}: {detail}")


def selftest(script):
    return subprocess.run([sys.executable, str(script), "--selftest"], capture_output=True, text=True)


# 1. The real repo tree passes its own gate, and the selftest is green.
r = subprocess.run([sys.executable, str(GATE), "verify"], cwd=ROOT, capture_output=True, text=True)
check("the repo tree passes the gate", r.returncode == 0, r.stderr)
check("selftest is green", selftest(GATE).returncode == 0)

# 2. Each mutation of the gate itself must turn the selftest red.
MUTANTS = {
    "unreadable gate is a pass": ('return [f"UNKNOWN: gate {GATE} unreadable', 'return []; _ = [f"UNKNOWN: gate {GATE} unreadable'),
    "partial bump allowed": ("if sorted(touched) != sorted(paths):", "if False:"),
    "floor ignored on bump": ("elif nt < floor:", "elif False:"),
    "non-semver new tag allowed": ("if nt is None:", "if False:"),
    "requires ignored": ('if got != r["equals"]:', "if False:"),
    "verify ignores current floor": ("elif files is None and cur < _semver", "elif False and cur < _semver"),
    "unreadable file is skipped": ('out.append(f"UNKNOWN: {p} image.tag unreadable: {type(exc).__name__}")\n                continue', "continue"),
    "unreadable required key is skipped": ('out.append(f"UNKNOWN: {r[\'path\']} {r[\'key\']} unreadable: {type(exc).__name__}")\n                continue', "continue"),
}
src = GATE.read_text()
for name, (old, new) in MUTANTS.items():
    check(f"mutant anchor exists: {name}", src.count(old) == 1, f"count={src.count(old)}")
    with tempfile.TemporaryDirectory() as d:
        m = pathlib.Path(d) / "release-gate.py"
        m.write_text(src.replace(old, new))
        check(f"mutant killed: {name}", selftest(m).returncode != 0)

# 3. Both bump workflows call the gate before writing and before pushing.
rd = (ROOT / ".github/workflows/release-deploy.yaml").read_text()
gb = (ROOT / ".github/workflows/gitops-bump.yaml").read_text()
for label, wf in (("release-deploy", rd), ("gitops-bump", gb)):
    check(f"{label}: gate check runs before the bump writes", wf.count('"scripts/release-gate.py", "check"') == 1)
    check(f"{label}: a refusal stops the bump", "release gate refused this bump" in wf)
check("release-deploy: gate re-runs on every push attempt, after the rebase",
      re.search(r"for attempt in 1 2 3 4 5; do\n\s+release_gate\n", rd) is not None)
check("gitops-bump: gate verifies the tree right before git push",
      re.search(r"release-gate\.py verify\n\s+git push", gb) is not None)

# 4. A bump script that cannot reach the gate must not succeed (fail closed).
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    (tmp / "scripts").mkdir()  # no release-gate.py inside
    p = subprocess.run(
        [sys.executable, str(GATE), "--root", str(tmp), "check", "--files", "x", "--new-tag", "1.0.0"],
        capture_output=True, text=True)
    check("a missing gate file refuses", p.returncode == 6, p.stderr)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
