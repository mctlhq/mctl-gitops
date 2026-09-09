"""Run wft-provision-database's values.yaml patch against fixtures, with real yq.

gitops#1102: the block this covers used to be a single `printf ... >> values.yaml`
guarded only on `dbSecret:` being absent. A service that already declared
`envFrom:` — 17 of them do — got a *second* top-level `envFrom:`, and Helm's
loader keeps the last duplicate, so the pod started with the database
credentials and nothing else. seerrsense crashlooped on 2026-09-09 while the
previous pod kept serving, which is why it read as a stuck rollout.

Nothing would have caught it: the workflow's bot pushes straight to `main`, so
yamllint (whose `relaxed` profile does keep key-duplicates at error) never ran,
and validate-manifests, which does run on that push, uses `helm template` —
which accepts duplicate keys silently.

So the guarantee has to come from the generator itself. The block is extracted
from the template rather than restated here, because a restated copy would keep
passing after the template changed.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/wft-provision-database.yaml")
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "do-provision"][0]["script"]["source"]


def dedent(block, width):
    return "\n".join(ln[width:] if ln.startswith(" " * width) else ln
                     for ln in block.split("\n"))


# YAML strips the block scalar's indentation, so `source` is already at
# column 0 and the nested guard sits two spaces in.
m = re.search(
    r'^(SVC_VALUES="platform-gitops/services/.*?\nfi)$', SOURCE, re.S | re.M)
assert m, "could not extract the values.yaml patch block from the template"
BLOCK = m.group(1)

SCRIPT = "set -e\nTEAM=labs\nAPP=demo\nVAULT_PATH=teams/labs/demo/database\n" + BLOCK

WITH_ENVFROM = """image:
  repository: ghcr.io/mctlhq/demo
  tag: "1.0.0"
envFrom:
  - secretRef:
      name: demo-secrets
  - secretRef:
      name: demo-extra
"""

WITHOUT_ENVFROM = """image:
  repository: ghcr.io/mctlhq/demo
  tag: "1.0.0"
"""

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


if not shutil.which("yq"):
    print("yq not on PATH — this test needs the real binary", file=sys.stderr)
    sys.exit(2)


def run(values, runs=1):
    """Apply the extracted block `runs` times; return (proc, text, first_text)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        svc = tmp / "platform-gitops" / "services" / "labs" / "demo"
        svc.mkdir(parents=True)
        (svc / "values.yaml").write_text(values)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        first = None
        for i in range(runs):
            proc = subprocess.run(["sh", "-c", SCRIPT], cwd=tmp,
                                  capture_output=True, text=True)
            if i == 0:
                first = (svc / "values.yaml").read_text()
            if proc.returncode != 0:
                break
        return proc, (svc / "values.yaml").read_text(), first


def top_level_keys(text):
    return [ln.split(":")[0] for ln in text.splitlines()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", ln)]


# 1. The case that broke production: a file that already declares envFrom.
proc, text, _ = run(WITH_ENVFROM)
check("patching a file that already has envFrom succeeds",
      proc.returncode == 0, f"rc={proc.returncode} err={proc.stderr}")
check("exactly one top-level envFrom survives",
      top_level_keys(text).count("envFrom") == 1, top_level_keys(text))
names = yaml.safe_load(text)["envFrom"]
check("the pre-existing secretRefs are kept",
      [e["secretRef"]["name"] for e in names[:2]] == ["demo-secrets", "demo-extra"],
      names)
check("the db secretRef is appended last, so app secrets keep winning",
      names[-1]["secretRef"]["name"] == "labs-demo-db-creds", names)
check("dbSecret is written",
      yaml.safe_load(text)["dbSecret"] == {
          "vaultPath": "teams/labs/demo/database",
          "secretName": "labs-demo-db-creds"},
      yaml.safe_load(text).get("dbSecret"))
check("no dbInitJob is emitted — the chart defaults it, and the SQL that used "
      "to be hardcoded here is mctl-telegram's",
      "dbInitJob" not in yaml.safe_load(text), top_level_keys(text))

# 2. A file with no envFrom at all still gets the key.
proc, text, _ = run(WITHOUT_ENVFROM)
check("a file without envFrom gets the key created",
      proc.returncode == 0
      and [e["secretRef"]["name"] for e in yaml.safe_load(text)["envFrom"]]
      == ["labs-demo-db-creds"],
      f"rc={proc.returncode} err={proc.stderr} text={text}")

# 3. Re-provisioning must not accumulate. The old block was guarded by
#    `grep -q dbSecret:`; this one has no guard, so idempotency has to come
#    from the merge itself.
proc, text, first = run(WITH_ENVFROM, runs=3)
check("re-running is a no-op", text == first, f"first={first!r} then={text!r}")
check("re-running does not duplicate the db secretRef",
      [e["secretRef"]["name"] for e in yaml.safe_load(text)["envFrom"]]
      == ["demo-secrets", "demo-extra", "labs-demo-db-creds"],
      yaml.safe_load(text)["envFrom"])

# 4. The incident's own file, fed through the whole block rather than the guard
#    alone. yq could plausibly collapse a duplicate key on its read/write round
#    trip, which would leave the guard with nothing to find and quietly repair a
#    file that ArgoCD is already serving from. It does not: yq preserves both
#    occurrences and appends to the last, so the file stays duplicated and the
#    guard stops the commit. Asserting on that is the only way the guard is
#    known to cover the shape it exists for.
DUPLICATED = WITH_ENVFROM + """envFrom:
  - secretRef:
      name: labs-demo-db-creds
"""
proc, text, _ = run(DUPLICATED)
check("an already-duplicated values.yaml fails the run rather than being "
      "silently rewritten",
      proc.returncode != 0 and "duplicate top-level keys" in proc.stderr,
      f"rc={proc.returncode} err={proc.stderr}")
check("the duplicate is still visible to the guard after yq has run",
      top_level_keys(text).count("envFrom") == 2, top_level_keys(text))

# 5. The guard is what stops a future regression from reaching main at all,
#    so exercise it on a file it must reject rather than trusting it by reading.
GUARD = re.search(r"^(  DUPES=.*?\n  fi)$", SOURCE, re.S | re.M)
assert GUARD, "could not extract the duplicate-key guard from the template"
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    (tmp / "values.yaml").write_text(WITH_ENVFROM + 'envFrom:\n  - secretRef:\n      name: labs-demo-db-creds\n')
    guard = subprocess.run(
        ["sh", "-c", 'set -e\nSVC_VALUES=values.yaml\n' + dedent(GUARD.group(1), 2)],
        cwd=tmp, capture_output=True, text=True)
check("the guard rejects a file with a duplicate top-level key",
      guard.returncode != 0 and "envFrom" in guard.stderr,
      f"rc={guard.returncode} err={guard.stderr}")
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    (tmp / "values.yaml").write_text(WITH_ENVFROM)
    guard = subprocess.run(
        ["sh", "-c", 'set -e\nSVC_VALUES=values.yaml\n' + dedent(GUARD.group(1), 2)],
        cwd=tmp, capture_output=True, text=True)
check("the guard accepts a clean file", guard.returncode == 0,
      f"rc={guard.returncode} err={guard.stderr}")

# 6. The shape that caused the incident must not come back by another route.
check("the template no longer appends to values.yaml",
      '>> "$SVC_VALUES"' not in SOURCE,
      "something still text-appends to the service values file")

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("\nall checks passed")
