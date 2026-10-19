"""Render the tenant chart and pin down who may read Secrets in a tenant namespace.

A tenant namespace holds the gitops deploy key (mctl-gitops-deploy-key) and
github-actions-pat, because mctl-api submits deploy-service, preview-deploy,
provision-database and retire-service there and those mount both. Until this
test, two subjects that never need them could read them anyway:

- the team's Argo UI SSO account (argo-workflows/sso-team-<tenant>, i.e. every
  tenant member) through the cluster-wide argo-workflows-admin-extra
  ClusterRole, which grants get on every Secret;
- mctl-api, whose submit binding reused the workflow pods' own
  argo-workflow-runner Role (get secrets), although mctl-api only creates the
  handoff Secret and never reads one.

For every tenant values file, in every non-preview namespace the chart
renders:

- every RoleBinding's role is known (a Role rendered here, or a ClusterRole
  classified below), so a new binding cannot escape the check;
- only the workflow ServiceAccounts read Secrets without resourceNames;
- the SSO account reads exactly the artifact-repository credentials Secret
  that the controller config names, and nothing else;
- mctl-api cannot get, list or watch any Secret.

Run: python3 tests/test_tenant_secret_readers.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
CONTROLLER = pathlib.Path("platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml")
READ = {"get", "list", "watch", "*"}
# ClusterRoles a tenant RoleBinding may reference, with the Secret rules they
# carry. argo-workflows-view comes from the upstream argo-workflows chart and
# only covers argoproj.io resources.
CLUSTER_ROLES = {"argo-workflows-view": []}
# Subjects that run workflow pods here and mount the Secrets themselves.
WORKFLOW_SAS = {"argo-workflow-sa"}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values_file, tenant):
    proc = subprocess.run(
        ["helm", "template", f"tenant-{tenant}", str(CHART), "-f", str(values_file),
         "--namespace", tenant],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"helm template failed for {tenant}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def secret_reads(rules):
    """(unrestricted, names): whether any rule reads all Secrets, and which
    Secrets are readable by name."""
    unrestricted, names = False, set()
    for r in rules or []:
        if not ({"", "*"} & set(r.get("apiGroups", []))):
            continue
        if not ({"secrets", "*"} & set(r.get("resources", []))):
            continue
        if not (READ & set(r.get("verbs", []))):
            continue
        if r.get("resourceNames"):
            names |= set(r["resourceNames"])
        else:
            unrestricted = True
    return unrestricted, names


m = re.search(r"artifactRepository:.*?accessKeySecret:\s*\n\s*name:\s*(\S+)",
              CONTROLLER.read_text(), re.S)
check(m is not None, f"could not find artifactRepository.s3.accessKeySecret.name in {CONTROLLER}")
ARTIFACT_SECRET = m.group(1) if m else None

checked = 0
for values_file in sorted(TENANTS.glob("*/values.yaml")):
    tenant = values_file.parent.name
    docs = render(values_file, tenant)
    namespaces = [d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"
                  and d["metadata"].get("labels", {}).get("mctl.me/preview") != "true"]
    check(namespaces, f"{tenant}: the chart rendered no tenant namespace")
    for ns in namespaces:
        checked += 1
        roles = {d["metadata"]["name"]: d.get("rules") for d in docs
                 if d["kind"] == "Role" and d["metadata"].get("namespace") == ns}
        sso = ("ServiceAccount", "argo-workflows", f"sso-team-{tenant}")
        sso_names = set()
        for b in docs:
            if b["kind"] != "RoleBinding" or b["metadata"].get("namespace") != ns:
                continue
            name, ref = b["metadata"]["name"], b["roleRef"]
            if ref["kind"] == "Role":
                check(ref["name"] in roles,
                      f"{tenant}: RoleBinding {name} in {ns} references Role {ref['name']}, "
                      "which the chart does not render")
                rules = roles.get(ref["name"])
            else:
                check(ref["name"] in CLUSTER_ROLES,
                      f"{tenant}: RoleBinding {name} in {ns} references ClusterRole "
                      f"{ref['name']}; classify its Secret access in CLUSTER_ROLES")
                rules = CLUSTER_ROLES.get(ref["name"])
            unrestricted, names = secret_reads(rules)
            for s in b.get("subjects") or []:
                who = (s["kind"], s.get("namespace"), s["name"])
                if who == sso:
                    check(not unrestricted,
                          f"{tenant}: {name} in {ns} lets the SSO account {s['name']} read every "
                          "Secret, including the gitops deploy key")
                    sso_names |= names
                    continue
                if s["kind"] == "ServiceAccount" and s["name"] == "mctl-api":
                    check(not unrestricted and not names,
                          f"{tenant}: {name} in {ns} lets mctl-api read Secrets "
                          f"({'all' if unrestricted else sorted(names)}); it only creates them")
                    continue
                if unrestricted:
                    check(s["kind"] == "ServiceAccount" and s["name"] in WORKFLOW_SAS,
                          f"{tenant}: {name} in {ns} grants get/list on every Secret to "
                          f"{s.get('namespace')}/{s['name']}")
        check(sso_names == {ARTIFACT_SECRET},
              f"{tenant}: the SSO account must read exactly {ARTIFACT_SECRET} in {ns} "
              f"(archived logs in the Argo UI), got {sorted(sso_names)}")

check(checked > 0, "no tenant namespace rendered; the test checked nothing")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"tenant Secret readers: {checked} namespaces, only workflow SAs read all Secrets")
