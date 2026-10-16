"""Run wft-create-tenant's creator_catalog_key handling against stubs.

create-tenant writes the creator's owner entry. With creator_catalog_key=principal
(a self-service customer, mctl-web docs/plans/site-onboarding-review.md stage C2)
the entry carries `catalogKey: principal`, so the portal names the catalog User
by principalId: the GitHub login is display only and may later belong to
someone else. Any value other than login/principal, and principal without a
principal id, must fail the step rather than fall back to a login-keyed owner.

The validation case block and the members block are extracted from the
template rather than restated here, because a restated copy would keep passing
after the template changed.
"""
import pathlib
import re
import subprocess
import sys

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml")
doc = yaml.safe_load(TPL.read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
COMMIT_T = TEMPLATES["commit-tenant-to-git"]
COMMIT = COMMIT_T["script"]["source"]


def block(start, end):
    m = re.search(rf"^({re.escape(start)}.*?)^{re.escape(end)}", COMMIT, re.S | re.M)
    assert m, f"could not extract the block starting {start!r}"
    return m.group(1)


CASE = block("# creator_catalog_key is one of two words", "# The five quota values")
MEMBERS = block("# Build members section if creator is specified", "# Write values.yaml")
SCRIPT = ("set -e\nCREATOR_CATALOG_KEY=\"$PARAM_CREATOR_CATALOG_KEY\"\n"
          + CASE + MEMBERS + 'printf "%s\\n" "$MEMBERS_BLOCK"\n')

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


# The parameter must default to login and reach the commit step's env.
defaults = {p["name"]: p.get("value") for p in doc["spec"]["arguments"]["parameters"]}
check("creator_catalog_key defaults to login",
      defaults.get("creator_catalog_key") == "login", str(defaults.get("creator_catalog_key")))
dag = TEMPLATES["create-tenant-pipeline"]["dag"]["tasks"]
args = {p["name"]: p["value"] for t in dag if t["name"] == "commit-to-git"
        for p in t["arguments"]["parameters"]}
check("commit-to-git receives creator_catalog_key",
      args.get("creator_catalog_key") == "{{workflow.parameters.creator_catalog_key}}", str(args))
inputs = {p["name"] for p in COMMIT_T["inputs"]["parameters"]}
env = {e["name"]: e.get("value") for e in COMMIT_T["script"].get("env", [])}
check("the commit step declares the input and exports it",
      "creator_catalog_key" in inputs
      and env.get("PARAM_CREATOR_CATALOG_KEY") == "{{inputs.parameters.creator_catalog_key}}",
      str(env.get("PARAM_CREATOR_CATALOG_KEY")))
check("the commit step reads the env var it is given",
      'CREATOR_CATALOG_KEY="$PARAM_CREATOR_CATALOG_KEY"' in COMMIT)

PID = "prn_01M39HRB7JRXZ2PHW5VVB695YZ"


def run(key, pid, user="alice"):
    r = subprocess.run(["sh", "-c", SCRIPT], capture_output=True, text=True, env={
        "PATH": "/usr/bin:/bin", "PARAM_CREATOR_CATALOG_KEY": key,
        "CREATOR_USER_ID": user, "CREATOR_PRINCIPAL_ID": pid})
    members = None
    if r.returncode == 0 and r.stdout.strip():
        members = yaml.safe_load("tenant:\n" + r.stdout)["tenant"]["members"]
    return r, members


LOGIN_ENTRY = [{"userId": "alice", "principalId": PID, "role": "owner"}]
for key in ("", "login"):
    r, m = run(key, PID)
    check(f"creator_catalog_key={key!r} writes a login-keyed owner (no catalogKey)",
          r.returncode == 0 and m == LOGIN_ENTRY, r.stdout + r.stderr)

r, m = run("principal", PID)
check("creator_catalog_key=principal writes catalogKey: principal",
      r.returncode == 0 and m == [dict(LOGIN_ENTRY[0], catalogKey="principal")],
      r.stdout + r.stderr)

r, m = run("principal", "")
check("principal without creator_principal_id fails the step",
      r.returncode != 0 and "without creator_principal_id" in r.stderr, r.stdout + r.stderr)

for key in ("Principal", "bogus", "principal "):
    r, m = run(key, PID)
    check(f"unknown creator_catalog_key {key!r} fails the step (no login fallback)",
          r.returncode != 0 and "must be login or principal" in r.stderr, r.stdout + r.stderr)

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
