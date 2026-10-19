"""Render the tenant chart and pin down what the central workflow SA holds.

argo-workflows/argo-workflow-sa runs the platform workflows (create/delete
tenant, smoke-test, rotate-github-token, the labs restart CronWorkflow). The
tenant chart used to bind it, in every tenant namespace, to
argo-workflow-helm-deploy (write on Deployments, Secrets, Services, Pods) and
argo-workflow-smoke-verify (Secret reads, pods/exec), although tenant
workflows run as the tenant-local SA and only labs and admins are ever
targeted from argo-workflows. Both are opt-in now (tenant.centralWorkflowSA).

For every tenant values file:

- no RoleBinding gives the central SA argo-workflow-helm-deploy;
- the central SA is bound to smoke-verify exactly where smokeVerify is set,
  and its restart Role patches only the listed Deployments;
- a tenant with externalSecretPatchTargets has smokeVerify, because
  cwft-rotate-github-token patches them as the central SA;
- every `kubectl -n <tenant> rollout restart deployment/<name>` in a
  template that runs in argo-workflows is covered by that tenant's
  restartDeployments, so dropping a grant fails here, not on a Sunday.

Run: python3 tests/test_tenant_central_sa_bindings.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
CWFT = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
CENTRAL = ("ServiceAccount", "argo-workflows", "argo-workflow-sa")
RESTART = re.compile(r"kubectl -n ([a-z0-9-]+) rollout restart deployment/([a-z0-9-]+)")

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


# Restarts the platform workflows perform, by tenant namespace.
wanted_restarts = {}
for path in sorted(CWFT.glob("*.yaml")):
    for ns, deploy in RESTART.findall(path.read_text()):
        wanted_restarts.setdefault(ns, set()).add(deploy)
check(wanted_restarts, "found no `rollout restart` in the cluster templates; "
      "the RESTART pattern no longer matches what they run")

checked = 0
for values_file in sorted(TENANTS.glob("*/values.yaml")):
    tenant = values_file.parent.name
    values = (yaml.safe_load(values_file.read_text()) or {}).get("tenant") or {}
    central = values.get("centralWorkflowSA") or {}
    smoke = bool(central.get("smokeVerify"))
    restarts = set(central.get("restartDeployments") or [])
    docs = render(values_file, tenant)
    checked += 1
    roles = {(d["metadata"]["namespace"], d["metadata"]["name"]): d.get("rules") or []
             for d in docs if d["kind"] == "Role"}

    smoke_bound, restart_patch = False, set()
    for b in docs:
        if b["kind"] != "RoleBinding":
            continue
        if CENTRAL not in {(s["kind"], s.get("namespace"), s["name"])
                           for s in b.get("subjects") or []}:
            continue
        ns, ref = b["metadata"]["namespace"], b["roleRef"]["name"]
        check(ref != "argo-workflow-helm-deploy",
              f"{tenant}: {b['metadata']['name']} in {ns} gives the central SA "
              "argo-workflow-helm-deploy (write on Secrets, Deployments, Pods)")
        if ref == "argo-workflow-helm-deploy":
            continue
        if ref == "argo-workflow-smoke-verify":
            smoke_bound = True
            continue
        if ref == "argo-workflow-central-restart":
            for r in roles.get((ns, ref), []):
                if "patch" in r.get("verbs", []):
                    check(r.get("resourceNames"),
                          f"{tenant}: {ref} in {ns} patches Deployments without resourceNames")
                    restart_patch |= set(r.get("resourceNames") or [])
                check(set(r.get("resources", [])) == {"deployments"}
                      and set(r.get("verbs", [])) <= {"get", "list", "watch", "patch"},
                      f"{tenant}: {ref} in {ns} grants more than Deployment reads and patch: {r}")
            continue
        check(False, f"{tenant}: {b['metadata']['name']} in {ns} binds the central SA to "
              f"{ref}; add it to tenant.centralWorkflowSA and to this test")

    check(smoke_bound == smoke,
          f"{tenant}: central SA bound to smoke-verify = {smoke_bound}, "
          f"tenant.centralWorkflowSA.smokeVerify = {smoke}")
    if values.get("externalSecretPatchTargets"):
        check(smoke, f"{tenant}: externalSecretPatchTargets are patched by "
              "cwft-rotate-github-token as the central SA; set centralWorkflowSA.smokeVerify")
    check(restart_patch == restarts,
          f"{tenant}: restart Role patches {sorted(restart_patch)}, values list {sorted(restarts)}")
    missing = wanted_restarts.get(tenant, set()) - restart_patch
    check(not missing, f"{tenant}: a template in argo-workflows restarts {sorted(missing)} "
          "here but the central SA has no patch grant for it")

for ns in set(wanted_restarts) - {p.parent.name for p in TENANTS.glob("*/values.yaml")}:
    check(False, f"a template restarts Deployments in {ns}, which is no tenant")
check(checked > 0, "no tenant rendered; the test checked nothing")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"tenant central SA bindings: {checked} tenants, no helm-deploy, opt-ins match values")
