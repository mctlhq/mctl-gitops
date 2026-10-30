"""Render the tenant chart and pin down who may run Helm in {tenant}-preview.

mctl-api submits preview-deploy and preview-delete in the tenant namespace
(operations.WorkflowNamespace), so they run as {tenant}/argo-workflow-sa.
Until gitops#1969 the helm-deploy Role in {tenant}-preview was bound only to
the central argo-workflows/argo-workflow-sa, so every preview failed on a
forbidden `helm list`, while the central SA, which nothing runs as there,
held write access to every tenant's preview secrets.

For every tenant values file in platform-gitops/tenants/ with preview on:

- the tenant-local argo-workflow-sa is bound to argo-workflow-helm-deploy in
  {tenant}-preview;
- no RoleBinding in {tenant}-preview has a subject outside the tenant's own
  namespaces, except mctl-api's two readers: resourcequotas (readiness) and
  apps/deployments (mctl_list_previews, mctl-api#698). Both are asserted
  read-only on exactly those resources, so neither can widen to secrets.

Run: python3 tests/test_tenant_preview_rbac.py
"""
import pathlib
import subprocess
import sys

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
QUOTA_READER = "mctl-api-preview-quota-reader"
PREVIEW_READER = "mctl-api-preview-reader"
# Role -> the only (apiGroup, resource) pairs mctl-api may read through it.
MCTL_API_READERS = {
    QUOTA_READER: {("", "resourcequotas")},
    PREVIEW_READER: {("apps", "deployments")},
}

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


checked = 0
for values_file in sorted(TENANTS.glob("*/values.yaml")):
    tenant = values_file.parent.name
    docs = render(values_file, tenant)
    preview_ns = [d["metadata"]["name"] for d in docs
                  if d["kind"] == "Namespace"
                  and d["metadata"].get("labels", {}).get("mctl.me/preview") == "true"]
    if not preview_ns:
        continue
    check(len(preview_ns) == 1, f"{tenant}: want one preview namespace, got {preview_ns}")
    ns = preview_ns[0]
    checked += 1
    roles = {d["metadata"]["name"]: d for d in docs
             if d["kind"] == "Role" and d["metadata"].get("namespace") == ns}
    bindings = [d for d in docs
                if d["kind"] == "RoleBinding" and d["metadata"].get("namespace") == ns]

    helm_subjects = {(s["kind"], s.get("namespace"), s["name"])
                     for b in bindings if b["roleRef"]["name"] == "argo-workflow-helm-deploy"
                     for s in b["subjects"]}
    check(("ServiceAccount", tenant, "argo-workflow-sa") in helm_subjects,
          f"{tenant}: {tenant}/argo-workflow-sa is not bound to argo-workflow-helm-deploy "
          f"in {ns}; preview-deploy/delete run as it (got {sorted(helm_subjects)})")

    for b in bindings:
        name = b["metadata"]["name"]
        for s in b["subjects"]:
            if name in MCTL_API_READERS:
                check(s == {"kind": "ServiceAccount", "name": "mctl-api", "namespace": "mctl-api"},
                      f"{tenant}: unexpected subject {s} on {name} in {ns}")
                continue
            check(s["kind"] == "ServiceAccount" and s.get("namespace") in (tenant, ns),
                  f"{tenant}: RoleBinding {name} in {ns} grants {b['roleRef']['name']} to "
                  f"{s.get('namespace')}/{s['name']}, outside the tenant. Preview "
                  "workflows run as the tenant-local argo-workflow-sa")

    for reader, allowed in MCTL_API_READERS.items():
        role = roles.get(reader)
        check(role is not None, f"{tenant}: {reader} Role missing in {ns}")
        if not role:
            continue
        verbs = {v for r in role["rules"] for v in r["verbs"]}
        pairs = {(g, x) for r in role["rules"]
                 for g in r.get("apiGroups", []) for x in r["resources"]}
        check(verbs <= {"get", "list", "watch"} and pairs == allowed,
              f"{tenant}: {reader} must stay read-only on {sorted(allowed)} "
              f"(verbs {sorted(verbs)}, resources {sorted(pairs)})")
        check(any(b["roleRef"]["name"] == reader for b in bindings),
              f"{tenant}: {reader} Role in {ns} is not bound to mctl-api")

check(checked > 0, "no tenant renders a preview namespace; the test checked nothing")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"tenant preview RBAC: {checked} tenants, tenant SA bound, no out-of-tenant subjects")
