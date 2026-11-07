"""Run patch-autoscaling-values' update logic against fixtures, with real yq.

The step used to rewrite values.yaml with four `sed -i` substitutions anchored
only on the key name, so they hit EVERY `enabled`, `minReplicas`, `maxReplicas`
and `targetCPUUtilizationPercentage` in the file, not just the ones under
`autoscaling:` (gitops#2413): an unrelated `enabled: false` was switched on and
another block's replica bounds were overwritten.

The script is taken from the template, not restated here, and only the part
that validates the parameters and edits values.yaml is run. Everything with a
side effect is left out or stubbed:

  * the SSH key and known_hosts setup, `git clone`, and everything after the
    values.yaml edit (git commit, release-gate-guard `outgoing`, `git push`)
    are not part of the extracted text and never run;
  * the `git clone` / `cd` pair is replaced by a `cd` into a temp directory;
  * release-gate-guard.sh `target` is a recording stub inside that directory;
  * git, ssh, kubectl and argo are shims first on PATH that record the call
    and fail, so a regression that reaches one of them is visible and harmless.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/wft-deploy-service.yaml")
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "patch-autoscaling-values"][0]["script"]["source"]

start = SOURCE.index('TEAM="$PARAM_TEAM_NAME"')
end = SOURCE.index('git config user.email "ci@mctl.ai"')
LOGIC = SOURCE[start:end]

CLONE = 'git clone --depth=1 "${REPO}" /tmp/mctl-gitops\ncd /tmp/mctl-gitops\n'
assert CLONE in LOGIC, "the clone/cd lines moved: update this test's extraction"
LOGIC = LOGIC.replace(CLONE, 'cd "$WORKDIR"\n')
assert "git clone" not in LOGIC and "git push" not in LOGIC and "ssh" not in LOGIC

SCRIPT = "set -euo pipefail\n" + LOGIC

BLOCKS = """\
image:
  repository: example/app
  tag: "1.0.0"
replicaCount: 2
ingress:
  enabled: false
serviceMonitor:
  enabled: false
  minReplicas: 7
  maxReplicas: 9
pdb:
  enabled: false
  minReplicas: 3
  targetCPUUtilizationPercentage: 55
"""
EXISTING = BLOCKS + """\
autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 5
  targetCPUUtilizationPercentage: 80
"""
# An autoscaling block that is not last, with something after it.
EXISTING_MIDDLE = BLOCKS + """\
autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 5
  targetCPUUtilizationPercentage: 80
env:
  enabled: "keep"
"""
GUARD_STUB = '#!/bin/sh\necho "$@" >> "$WORKDIR/guard.log"\n'
SHIM = '#!/bin/sh\necho "$0 $*" >> "$SHIM_LOG"\nexit 99\n'

# The workflow image has GNU sed; BSD sed (macOS) rejects `sed -i EXPR FILE`. When the
# host sed is not GNU, a shim maps GNU's `-i` onto BSD's `-i ''` so the ORIGINAL
# substitutions can run here, which is what makes the regression visible on a laptop.
GNU_SED = subprocess.run(["sed", "--version"], capture_output=True).returncode == 0
REAL_SED = shutil.which("sed")
SED_SHIM = ('#!/bin/sh\nif [ "$1" = "-i" ]; then shift; exec %s -i "" "$@"; fi\nexec %s "$@"\n'
            % (REAL_SED, REAL_SED))

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def run(values, mn="2", mx="6", cpu="65", runs=1):
    """Returns (last proc, values.yaml text after each run, guard log, shim log)."""
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        work = root / "work"
        shims = root / "shims"
        shims.mkdir()
        for tool in ("git", "ssh", "kubectl", "argo", "scp"):
            (shims / tool).write_text(SHIM)
            (shims / tool).chmod(0o755)
        if not GNU_SED:
            (shims / "sed").write_text(SED_SHIM)
            (shims / "sed").chmod(0o755)
        guard = work / "platform-gitops/argo-workflows/scripts/release-gate-guard.sh"
        guard.parent.mkdir(parents=True)
        guard.write_text(GUARD_STUB)
        target = work / "platform-gitops/services/team1/svc1/values.yaml"
        target.parent.mkdir(parents=True)
        if values is not None:
            target.write_text(values)
        env = {
            "PATH": f"{shims}:{os.environ['PATH']}",
            "HOME": str(root),
            "WORKDIR": str(work),
            "SHIM_LOG": str(root / "shim.log"),
            "GITOPS_ORG": "example-org",
            "GITOPS_REPO": "example-repo",
            "PARAM_TEAM_NAME": "team1",
            "PARAM_COMPONENT_NAME": "svc1",
            "PARAM_MIN_REPLICAS": mn,
            "PARAM_MAX_REPLICAS": mx,
            "PARAM_CPU_THRESHOLD": cpu,
        }
        texts, proc = [], None
        for _ in range(runs):
            proc = subprocess.run(["sh", "-c", SCRIPT], env=env, cwd=root,
                                  capture_output=True, text=True)
            texts.append(target.read_text() if target.exists() else None)
        log = lambda p: p.read_text() if p.exists() else ""
        return proc, texts, log(work / "guard.log"), log(root / "shim.log")


if not shutil.which("yq"):
    print("yq not on PATH — this test needs the real binary", file=sys.stderr)
    sys.exit(2)

# 1. An existing block is updated, and nothing outside it moves.
proc, (text,), guard, shim = run(EXISTING)
got = yaml.safe_load(text)
want = yaml.safe_load(EXISTING)
check("existing block: the step succeeds", proc.returncode == 0, proc.stderr)
check("existing block: autoscaling is enabled with the requested bounds",
      got["autoscaling"] == {"enabled": True, "minReplicas": 2, "maxReplicas": 6,
                             "targetCPUUtilizationPercentage": 65}, got.get("autoscaling"))
others = {k: v for k, v in got.items() if k != "autoscaling"}
check("existing block: every other block is untouched",
      others == {k: v for k, v in want.items() if k != "autoscaling"}, others)
check("existing block: an unrelated enabled: false stays false",
      got["ingress"]["enabled"] is False and got["serviceMonitor"]["enabled"] is False
      and got["pdb"]["enabled"] is False, got)
check("existing block: same-named numeric keys in other blocks keep their values",
      got["serviceMonitor"]["minReplicas"] == 7 and got["serviceMonitor"]["maxReplicas"] == 9
      and got["pdb"]["minReplicas"] == 3 and got["pdb"]["targetCPUUtilizationPercentage"] == 55, got)

# 2. A block that is not the last one in the file, followed by another `enabled`.
proc, (text,), _, _ = run(EXISTING_MIDDLE)
got = yaml.safe_load(text)
check("block in the middle: the block after it is untouched",
      proc.returncode == 0 and got["env"] == {"enabled": "keep"}, f"{got.get('env')} {proc.stderr}")
check("block in the middle: the block itself is updated",
      got["autoscaling"]["enabled"] is True and got["autoscaling"]["maxReplicas"] == 6,
      got.get("autoscaling"))

# 3. A missing block is created, with the unrelated keys untouched.
proc, (text,), _, _ = run(BLOCKS)
got = yaml.safe_load(text)
check("missing block: the step succeeds", proc.returncode == 0, proc.stderr)
check("missing block: the block is created",
      got.get("autoscaling") == {"enabled": True, "minReplicas": 2, "maxReplicas": 6,
                                 "targetCPUUtilizationPercentage": 65}, got.get("autoscaling"))
check("missing block: unrelated blocks keep their values",
      {k: v for k, v in got.items() if k != "autoscaling"}
      == yaml.safe_load(BLOCKS), got)

# 4. Numbers stay numbers (an !!int node), also with leading zeros.
for mn, mx, cpu in (("2", "6", "65"), ("02", "010", "0070"), ("0", "0", "0")):
    proc, (text,), _, _ = run(EXISTING, mn, mx, cpu)
    a = yaml.safe_load(text)["autoscaling"]
    check(f"types: ints stay ints for {mn}/{mx}/{cpu}",
          proc.returncode == 0 and all(type(a[k]) is int for k in
                                       ("minReplicas", "maxReplicas", "targetCPUUtilizationPercentage"))
          and (a["minReplicas"], a["maxReplicas"], a["targetCPUUtilizationPercentage"])
          == (int(mn), int(mx), int(cpu)) and a["enabled"] is True,
          f"{a} {proc.stderr}")
    check(f"types: no quoted number is written for {mn}/{mx}/{cpu}",
          not re.search(r"^\s*(min|max)Replicas: ['\"]", text, re.M)
          and not re.search(r"^\s*targetCPUUtilizationPercentage: ['\"]", text, re.M), text)

# 5. Idempotent: a second run changes nothing, for both starting shapes.
for name, values in (("existing", EXISTING), ("missing", BLOCKS)):
    proc, (first, second), _, _ = run(values, runs=2)
    check(f"idempotent ({name}): the second run is byte-identical",
          proc.returncode == 0 and first == second, f"{first!r} != {second!r}")

# 6. The guard still runs, against the right service, before the edit.
proc, _, guard, _ = run(EXISTING)
check("release-gate-guard target is called with team and component",
      guard.split() == ["target", "team1", "svc1"], repr(guard))

# 7. The offline run never reached git, ssh, kubectl or argo.
proc, _, _, shim = run(EXISTING)
check("no git/ssh/kubectl/argo call is made by the extracted logic", shim == "", shim)

# 8. Integer validation is preserved: a bad value fails before anything is written.
for bad in ("", "abc", "1.5", "-1", "5 ", "1\nimage:\n  repository: pwned", "1|2", "$(id)"):
    for field in ("mn", "mx", "cpu"):
        kw = {"mn": "2", "mx": "6", "cpu": "65"}
        kw[field] = bad
        proc, (text,), guard, shim = run(EXISTING, **kw)
        check(f"validation: {field}={bad!r} is rejected and nothing is written",
              proc.returncode != 0 and text == EXISTING and guard == "" and shim == "",
              f"rc={proc.returncode} guard={guard!r}")

# 9. The sed substitutions are gone from this step. The first checks above are the
#    behavioural proof; this one pins the shape the fix chose.
CODE = "\n".join(ln for ln in SOURCE.splitlines() if not ln.lstrip().startswith("#"))
check("the step no longer rewrites values.yaml with sed", "sed -i" not in CODE, CODE)
check("the update is written with yq", "yq eval -i" in CODE)

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
