"""Run wft-create-tenant's existence checks against a fixture checkout.

create-tenant creates a tenant. Its commit step used to find an existing
tenant directory, skip writing the tenant and carry on provisioning, so a
request for a taken name "succeeded" without creating anything. An existing
tenant is now refused in validate unless reprovision=true asks for a re-run,
and the commit step refuses one that appeared after validate.

Both blocks are extracted from the template rather than restated here, because
a restated copy would keep passing after the template changed. `git clone` is
replaced by a stub on PATH that copies a fixture checkout, or fails.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml")
doc = yaml.safe_load(TPL.read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
VALIDATE = TEMPLATES["validate-tenant-name"]["script"]["source"]
COMMIT = TEMPLATES["commit-tenant-to-git"]["script"]["source"]

m = re.search(r'^(TENANT_DIR="platform-gitops/tenants/\$\{TENANT\}"\n.*?\nfi)$',
              COMMIT, re.S | re.M)
assert m, "could not extract the commit step's existence check"
COMMIT_CHECK = m.group(1) + '\necho "SKIP_GIT=$SKIP_GIT"\n'

# The workflow must hand reprovision to both steps, or the default applies.
pipeline = [t for t in TEMPLATES["create-tenant-pipeline"]["dag"]["tasks"]]
for task in ("validate", "commit-to-git"):
    params = {p["name"]: p["value"] for t in pipeline if t["name"] == task
              for p in t["arguments"]["parameters"]}
    assert params.get("reprovision") == "{{workflow.parameters.reprovision}}", \
        f"{task} does not receive reprovision"
defaults = {p["name"]: p.get("value") for p in doc["spec"]["arguments"]["parameters"]}
assert defaults.get("reprovision") == "false", "reprovision must default to false"

GIT_STUB = """#!/bin/sh
# git clone <url> <dest>: copy the fixture, or fail like an unreachable remote.
[ "$1" = clone ] || exit 0
for dest; do :; done
[ -n "$FIXTURE" ] || { echo "fatal: unable to access" >&2; exit 128; }
cp -R "$FIXTURE" "$dest"
"""

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def run_validate(tenant, reprovision, fixture):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "bin").mkdir()
        stub = tmp / "bin" / "git"
        stub.write_text(GIT_STUB)
        stub.chmod(0o755)
        # The step clones to a fixed /tmp path; point it into this temp dir.
        source = VALIDATE.replace("/tmp/mctl-gitops", str(tmp / "clone"))
        env = {
            "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}",
            "PARAM_TENANT_NAME": tenant,
            "PARAM_REPROVISION": reprovision,
            "GITOPS_ORG": "example",
            "GITOPS_REPO": "gitops",
            "FIXTURE": str(fixture) if fixture else "",
        }
        return subprocess.run(["sh", "-c", source], env=env,
                              capture_output=True, text=True)


def run_commit_check(tenant, reprovision, checkout):
    script = f'set -e\nTENANT="$PARAM_TENANT_NAME"\n{COMMIT_CHECK}'
    env = {"PATH": os.environ["PATH"], "PARAM_TENANT_NAME": tenant,
           "PARAM_REPROVISION": reprovision}
    return subprocess.run(["sh", "-c", script], cwd=checkout, env=env,
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as d:
    fixture = pathlib.Path(d) / "checkout"
    (fixture / "platform-gitops" / "tenants" / "taken").mkdir(parents=True)
    (fixture / "platform-gitops" / "tenants" / "taken" / "values.yaml").write_text(
        "tenant:\n  name: taken\n")

    r = run_validate("fresh", "false", fixture)
    check("a new tenant passes validate", r.returncode == 0, r.stdout + r.stderr)

    r = run_validate("taken", "false", fixture)
    check("an existing tenant fails validate", r.returncode != 0, r.stdout)
    check("the failure names the tenant and the way to re-run",
          "already exists" in r.stdout and "reprovision=true" in r.stdout, r.stdout)

    r = run_validate("taken", "true", fixture)
    check("reprovision=true lets an existing tenant through",
          r.returncode == 0, r.stdout + r.stderr)

    r = run_validate("fresh", "true", fixture)
    check("reprovision=true refuses a tenant that does not exist",
          r.returncode != 0, r.stdout)

    r = run_validate("fresh", "yes", fixture)
    check("reprovision other than true/false is refused", r.returncode != 0, r.stdout)

    r = run_validate("fresh", "false", None)
    check("a failed clone fails validate (could not check is not absent)",
          r.returncode != 0, r.stdout)

    r = run_validate("fresh\nkube-system", "false", fixture)
    check("a multi-line name is refused", r.returncode != 0, r.stdout)

    r = run_validate("kube-system", "false", fixture)
    check("a reserved name is still refused", r.returncode != 0, r.stdout)

    r = run_commit_check("fresh", "false", fixture)
    check("commit: a new tenant writes its files",
          r.returncode == 0 and "SKIP_GIT=false" in r.stdout, r.stdout + r.stderr)

    r = run_commit_check("taken", "false", fixture)
    check("commit: a tenant created after validate fails the step",
          r.returncode != 0, r.stdout)

    r = run_commit_check("taken", "true", fixture)
    check("commit: reprovision=true skips the files and carries on",
          r.returncode == 0 and "SKIP_GIT=true" in r.stdout, r.stdout + r.stderr)

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
