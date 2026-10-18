"""Render the tenant chart and pin down where its Pod Security labels come from.

The chart documents podSecurityLevel and podSecurityObserveLevel under
tenant:, like every other value, but until this test the templates read them
from the top level. A tenant that set tenant.podSecurityLevel: restricted
therefore still rendered enforce=baseline, with nothing to say so.

For every tenant values file in platform-gitops/tenants/, and for each
namespace the chart renders (the tenant's own, per-team ones and the preview
one):

- enforce follows tenant.podSecurityLevel (default baseline), and audit/warn
  follow tenant.podSecurityObserveLevel (default restricted);
- overriding tenant.podSecurityLevel / tenant.podSecurityObserveLevel changes
  every one of them, while the same keys at the top level change nothing;
- no tenant values file sets either key at the top level.

Run: python3 tests/test_tenant_pod_security_level.py
"""
import pathlib
import subprocess
import sys

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
ENFORCE = "pod-security.kubernetes.io/enforce"
AUDIT = "pod-security.kubernetes.io/audit"
WARN = "pod-security.kubernetes.io/warn"
KEYS = ("podSecurityLevel", "podSecurityObserveLevel")

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def namespaces(values_file, tenant, *sets):
    args = ["helm", "template", f"tenant-{tenant}", str(CHART), "-f", str(values_file),
            "--namespace", tenant]
    for s in sets:
        args += ["--set", s]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"helm template failed for {tenant} {sets}:\n{proc.stderr}")
    docs = [d for d in yaml.safe_load_all(proc.stdout) if d]
    return {d["metadata"]["name"]: d["metadata"].get("labels", {})
            for d in docs if d["kind"] == "Namespace"}


def labels_are(rendered, tenant, case, enforce, observe):
    check(rendered, f"{tenant} [{case}]: the chart rendered no Namespace")
    for ns, labels in rendered.items():
        got = (labels.get(ENFORCE), labels.get(AUDIT), labels.get(WARN))
        check(got == (enforce, observe, observe),
              f"{tenant} [{case}]: {ns} has enforce/audit/warn {got}, "
              f"want ({enforce}, {observe}, {observe})")


checked = 0
for values_file in sorted(TENANTS.glob("*/values.yaml")):
    tenant = values_file.parent.name
    values = yaml.safe_load(values_file.read_text()) or {}
    for key in KEYS:
        check(key not in values,
              f"{tenant}: {key} is set at the top level of {values_file}, where the "
              f"chart ignores it; set tenant.{key}")
    t = values.get("tenant") or {}
    enforce = t.get("podSecurityLevel") or "baseline"
    observe = t.get("podSecurityObserveLevel") or "restricted"

    labels_are(namespaces(values_file, tenant), tenant, "as committed", enforce, observe)
    labels_are(namespaces(values_file, tenant,
                          "tenant.podSecurityLevel=privileged",
                          "tenant.podSecurityObserveLevel=baseline"),
               tenant, "tenant.* overridden", "privileged", "baseline")
    labels_are(namespaces(values_file, tenant,
                          "podSecurityLevel=privileged",
                          "podSecurityObserveLevel=baseline"),
               tenant, "top-level keys set", enforce, observe)
    checked += 1

# No tenant uses the multi-team branch of namespace.yaml today; render it
# through the first tenant so its labels are held to the same rule.
first = sorted(TENANTS.glob("*/values.yaml"))[0]
team = "psa-team"
multi = namespaces(first, first.parent.name, f"tenant.teams[0].name={team}",
                   "tenant.podSecurityLevel=privileged",
                   "tenant.podSecurityObserveLevel=baseline")
check(any(ns.endswith(f"-{team}") for ns in multi),
      f"multi-team render produced no -{team} namespace: {sorted(multi)}")
labels_are(multi, first.parent.name, "multi-team, tenant.* overridden", "privileged", "baseline")

check(checked > 0, f"no tenant values files found under {TENANTS}")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"PASS: Pod Security labels follow tenant.podSecurityLevel for {checked} tenants")
