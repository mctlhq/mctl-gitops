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
    "semver fullmatch weakened to match": ("SEMVER.fullmatch(str(tag))", "SEMVER.match(str(tag))"),
    "floor compared as strings": ("elif nt < floor:", 'elif str(new_tag) < str(g["min_tag"]):'),
    "requires outside the group accepted": (' and r["path"] in g["paths"]', ""),
    "tag differences ignored": ("if len({str(t) for t in tags.values()}) > 1:", "if False:"),
    "repository ignored": ('if g.get("repository") and', "if False and"),
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

# 3. Both bump workflows call the gate before writing and before pushing, and
#    a refusal (or a crash) stops them. Structure, not just presence.
rd = (ROOT / ".github/workflows/release-deploy.yaml").read_text()
gb = (ROOT / ".github/workflows/gitops-bump.yaml").read_text()
for label, wf, first_write in (("release-deploy", rd, "with open(path, 'w')"), ("gitops-bump", gb, "with open(path, 'w')")):
    call = wf.find('"scripts/release-gate.py", "check"')
    check(f"{label}: exactly one check call", wf.count('"scripts/release-gate.py", "check"') == 1)
    check(f"{label}: check runs before the first write", 0 < call < wf.find(first_write), f"{call} {wf.find(first_write)}")
    check(f"{label}: check sees normalised paths", "*[os.path.normpath(f) for f in files]" in wf)
    check(f"{label}: any nonzero exit refuses",
          re.search(r"if _gate\.returncode != 0:\n\s+print\([^\n]*\n\s+sys\.exit\(6\)", wf) is not None)
    inst = wf.find("pip install --quiet pyyaml==6.0.2")
    bump = wf.find("- name: Bump image tag")
    check(f"{label}: PyYAML is installed before the bump", 0 < inst < bump)
check("release-deploy: verify runs every push attempt, after the rebase, and is fatal",
      re.search(r"release_gate\(\) \{\n\s+python3 scripts/release-gate\.py verify \|\| \{\n\s+echo[^\n]*\n\s+exit 1\n", rd)
      is not None and re.search(r"for attempt in 1 2 3 4 5; do\n\s+release_gate\n", rd) is not None
      and "verify || true" not in rd)
check("gitops-bump: verify is the line right before git push",
      re.search(r"release-gate\.py verify\n\s+git push", gb) is not None)

# 3b. The rollback workflow pushes one values file with the bypass key: it must
#     refuse gated files, and a missing gate file, without needing an interpreter.
rb = (ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-rollback-service.yaml").read_text()
m = re.search(r"# release-gate guard begin.*?\n(.*?)\n\s*# release-gate guard end", rb, re.S)
check("rollback: guard present", m is not None)
if m:
    guard = "\n".join(ln[10:] if ln.startswith(" " * 10) else ln for ln in m.group(1).split("\n"))
    gated = "platform-gitops/services/admins/mctl-agents-worker-exec/values.yaml"
    other = "platform-gitops/services/admins/mctl-docs/values.yaml"
    for name, values, with_gate, want in (("gated file refused", gated, True, 1), ("other file allowed", other, True, 0),
                                         ("missing gate refused", other, False, 1)):
        with tempfile.TemporaryDirectory() as d:
            if with_gate:
                (pathlib.Path(d) / "platform-gitops").mkdir()
                shutil.copy(ROOT / "platform-gitops/release-gates.yaml", pathlib.Path(d) / "platform-gitops/release-gates.yaml")
            rr = subprocess.run(["bash", "-c", f'VALUES="{values}"\n{guard}'], cwd=d, capture_output=True, text=True)
            check(f"rollback: {name}", rr.returncode == want, f"rc={rr.returncode} {rr.stderr}")

# 3c. The real gate config still says what the design says; a PR that deletes
#     the group or empties `requires` must fail here, not pass silently.
import yaml  # noqa: E402

cfg = yaml.safe_load((ROOT / "platform-gitops/release-gates.yaml").read_text())
grp = next((g for g in cfg["gates"] if g["name"] == "mctl-agents-workers"), None)
check("gate config: the worker group exists", grp is not None)
if grp:
    check("gate config: all three worker files", len(grp["paths"]) == 3 and all("mctl-agents-worker" in p for p in grp["paths"]))
    check("gate config: Recreate on the control worker",
          {"path": "platform-gitops/services/admins/mctl-agents-worker/values.yaml", "key": "strategy.type", "equals": "Recreate"}
          in grp["requires"])
    check("gate config: floor is at least 1.117.0", tuple(map(int, grp["min_tag"].split("."))) >= (1, 117, 0))
    check("gate config: image repository pinned", grp.get("repository") == "ghcr.io/mctlhq/mctl-agents")

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
