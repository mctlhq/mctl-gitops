"""release-gate-watch.yml: a violation alerts, and only a violation says so.

The Verify step is extracted from the workflow and run the way GitHub runs it,
under bash -e, against a converged tree and against deliberate mutations of it.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows/release-gate-watch.yml"
doc = yaml.safe_load(WF.read_text())
STEPS = doc["jobs"]["verify"]["steps"]
VERIFY = [s for s in STEPS if s.get("id") == "verify"][0]["run"]
GATE = "platform-gitops/release-gates.yaml"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def tree(tmp):
    gate = yaml.safe_load((ROOT / GATE).read_text())
    (tmp / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/release-gate.py", tmp / "scripts/release-gate.py")
    (tmp / GATE).parent.mkdir(parents=True)
    shutil.copy(ROOT / GATE, tmp / GATE)
    for g in gate["gates"]:
        for p in g["paths"]:
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / p, tmp / p)
    return gate["gates"][0]["paths"]


def run(mutate=None, script=VERIFY):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        paths = tree(tmp)
        if mutate:
            mutate(tmp, paths)
        out = tmp / "gh_output"
        out.touch()
        s = tmp / "step.sh"
        s.write_text(script)
        r = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", str(s)], cwd=tmp,
                           capture_output=True, text=True, env={**os.environ, "GITHUB_OUTPUT": str(out)})
        return r.returncode, out.read_text()


def lower_one(tmp, paths):
    v = tmp / paths[0]
    data = yaml.safe_load(v.read_text())
    v.write_text(v.read_text().replace(f'tag: "{data["image"]["tag"]}"', 'tag: "0.0.1"'))


def no_script(tmp, paths):
    (tmp / "scripts/release-gate.py").unlink()


def no_gate(tmp, paths):
    (tmp / GATE).unlink()


rc, out = run()
check("a converged tree passes with no state", rc == 0 and "state=" not in out, f"{rc} {out}")
rc, out = run(lower_one)
check("a drifted group is a violation and goes red", rc == 6 and "state=violated" in out, f"{rc} {out}")
rc, out = run(no_gate)
check("an unreadable gate is a violation and goes red", rc == 6 and "state=violated" in out, f"{rc} {out}")
rc, out = run(no_script)
check("a check that did not run goes red but is no violation",
      rc != 0 and "state=violated" not in out, f"{rc} {out}")

# Remove each part in turn: the alert keys on the state, and bash -e must not
# end the step before it is written.
FORM = "python3 scripts/release-gate.py verify || rc=$?"
assert FORM in VERIFY
rc, out = run(lower_one, script=VERIFY.replace(FORM, "python3 scripts/release-gate.py verify\nrc=$?"))
check("mutant caught: a bare call loses the state under bash -e", "state=violated" not in out, out)
rc, out = run(lower_one, script=VERIFY.replace("state=violated", "state=clean"))
check("mutant caught: the violation state is what the alert keys on", "state=violated" not in out, out)

on = doc.get(True) or doc.get("on")
check("runs on every push to main", on["push"]["branches"] == ["main"])
check("runs daily, independent of pushes", bool(on["schedule"]))
by_name = {s.get("name", ""): s for s in STEPS}
viol = by_name["Notify Telegram - gate violated"]["if"]
other = by_name["Notify Telegram - the check itself failed"]["if"]
check("the violation alert needs the violated state", "== 'violated'" in viol and "failure()" in viol)
check("the other alert excludes it", "!= 'violated'" in other and "failure()" in other)
check("a pull request never alerts", "!= 'pull_request'" in viol and "!= 'pull_request'" in other)

conc = doc["concurrency"]["group"]
check("a push gets its own concurrency group per commit",
      "github.sha" in conc and "github.event_name == 'push'" in conc, conc)
check("other triggers share one group per ref", "github.ref" in conc, conc)
check("no run is cancelled mid-flight", doc["concurrency"]["cancel-in-progress"] is False)
vif = by_name["Verify"].get("if", "")
check("Verify runs after a failed comparison and not when cancelled",
      "success()" in vif and "failure()" in vif and "always()" not in vif, vif)
dif = by_name["Compare content with the parent"].get("if", "")
check("the comparison runs only on a push", "github.event_name == 'push'" in dif, dif)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f[:300])
    sys.exit(1)
print("all checks passed")
