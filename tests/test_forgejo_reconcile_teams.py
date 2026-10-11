"""The Forgejo reconciler's scoped-team repository rule, proven both ways.

platform-gitops/infra-components/data/forgejo/reconcile.yaml carries main.tf
in a ConfigMap. A scoped team (orgs[].teams[]) must name the repositories it
reaches, with one exception: a team whose units are exactly
["repo.packages"] may name none. That is the org-registry-only account
(Forgejo grants org packages by team permission, whatever the repositories).
Every other team without repositories must still fail the plan, and a
repository outside the org must fail whatever the units.

The test does not re-implement the rule. It copies the `repos` and
`scoped_teams` locals and the precondition's condition out of main.tf
verbatim, evaluates them with OpenTofu against small manifests decoded by
jsondecode() as the reconciler does, and checks each team's verdict.

T1. The precondition, `repos` and `scoped_teams` are found in main.tf.
T2. Accepted: a packages-only team with no repositories; teams whose
    repositories all belong to the org, with default or explicit units.
T3. Refused: no repositories with default units, with ["repo.code"], or with
    repo.packages next to another unit; a repository outside the org, also
    for a packages-only team.

Needs `tofu` on PATH (no providers, no network). No pytest, matching the
plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_forgejo_reconcile_teams.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECONCILE = ROOT / "platform-gitops" / "infra-components" / "data" / "forgejo" / "reconcile.yaml"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


docs = [d for d in yaml.safe_load_all(RECONCILE.read_text()) if d]
main_tf = next((d["data"]["main.tf"] for d in docs
                if d.get("kind") == "ConfigMap" and "main.tf" in d.get("data", {})), None)
if main_tf is None:
    fail(f"no ConfigMap with main.tf in {RECONCILE}")


def local_expr(name: str) -> str:
    # A local of the form `name = merge(...[ ... ]...)`, ending at the first
    # line that closes it with `]...)`.
    m = re.search(rf"^  {name}\s*= (merge\(.*?^  \]\.\.\.\))$", main_tf, re.S | re.M)
    if not m:
        fail(f"local {name} not found in main.tf")
    return m.group(1)


# T1
team = re.search(r'^resource "forgejo_team" "scoped" \{\n(.*?)^\}', main_tf, re.S | re.M)
if not team:
    fail('resource "forgejo_team" "scoped" not found in main.tf')
cond = None
for m in re.finditer(r"precondition \{\n\s*condition\s*=\s*(.+)\n\s*error_message\s*=\s*(.+)\n", team.group(1)):
    if "every repo" in m.group(2):
        cond = m.group(1).strip()
if cond is None:
    fail("the scoped team's repository precondition was not found")
if "each.value" not in cond:
    fail(f"the precondition does not read each.value: {cond}")

module = f"""
variable "manifest" {{
  type = string
}}

locals {{
  m            = jsondecode(var.manifest)
  repos        = {local_expr("repos")}
  scoped_teams = {local_expr("scoped_teams")}
  verdict      = {{ for k, team in local.scoped_teams : k => ({cond.replace("each.value", "team")}) }}
}}
"""

MANIFEST = """
orgs:
  - name: acme
    repos: [{name: app}, {name: lib}]
    teams:
%s
  - name: other
    repos: [{name: elsewhere}]
"""

CASES = {
    # T2
    "packages-only, no repos": ("{name: Pkg, permission: write, units: [repo.packages]}", True),
    "packages-only, repos absent": ("{name: Pkg, permission: read, units: [repo.packages], members: []}", True),
    "default units, own repos": ("{name: Dep, permission: write, repos: [app, lib]}", True),
    "code unit, own repo": ("{name: Src, permission: read, units: [repo.code], repos: [app]}", True),
    # T3
    "default units, no repos": ("{name: Dep, permission: write}", False),
    "default units, empty repos": ("{name: Dep, permission: write, repos: []}", False),
    "code unit, no repos": ("{name: Src, permission: read, units: [repo.code], repos: []}", False),
    "packages plus code, no repos": ("{name: Mix, permission: write, units: [repo.packages, repo.code]}", False),
    "code plus packages, no repos": ("{name: Mix, permission: write, units: [repo.code, repo.packages]}", False),
    "repo of another org": ("{name: Dep, permission: write, repos: [elsewhere]}", False),
    "packages-only, foreign repo": ("{name: Pkg, permission: write, units: [repo.packages], repos: [elsewhere]}", False),
    "packages-only, unknown repo": ("{name: Pkg, permission: write, units: [repo.packages], repos: [nope]}", False),
}

tofu = shutil.which("tofu")
if tofu is None:
    fail("tofu is not on PATH")

failures: list[str] = []
with tempfile.TemporaryDirectory() as tmp:
    Path(tmp, "main.tf").write_text(module)
    init = subprocess.run([tofu, "init", "-backend=false", "-input=false", "-no-color"],
                          cwd=tmp, capture_output=True, text=True)
    if init.returncode != 0:
        fail(f"tofu init: {init.stderr or init.stdout}")
    for name, (team_yaml, want) in CASES.items():
        manifest = MANIFEST % f"      - {team_yaml}"
        Path(tmp, "case.tfvars.json").write_text(json.dumps({"manifest": json.dumps(yaml.safe_load(manifest))}))
        out = subprocess.run([tofu, "console", "-var-file=case.tfvars.json", "-no-color"],
                             cwd=tmp, input="jsonencode(local.verdict)\n",
                             capture_output=True, text=True)
        if out.returncode != 0:
            failures.append(f"{name}: tofu console failed: {out.stderr.strip()}")
            continue
        # console prints the JSON as an HCL string literal.
        verdict = json.loads(json.loads(out.stdout.strip()))
        if len(verdict) != 1:
            failures.append(f"{name}: expected one team, got {verdict}")
            continue
        got = next(iter(verdict.values()))
        if got is not want:
            failures.append(f"{name}: precondition gave {got}, want {want}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"forgejo reconcile: scoped-team repository rule holds in {len(CASES)} cases")
