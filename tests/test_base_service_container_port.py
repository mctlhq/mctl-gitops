"""Render base-service and assert the container port can move without the Service.

`service.port` used to drive the containerPort, the Service port and the
Ingress backend number all at once. gitops#1933 changed it from 80 to 8080 on
the live admins/mctl-docs. ArgoCD applied the Deployment and the Ingress, but
the Service apply failed: Service ports merge by port number, so the 8080
entry landed next to the old 80 one, both named `http`
(`spec.ports[1].name: Duplicate value: "http"`). The Ingress then pointed at a
port the Service did not have, and docs.mctl.ai returned 404 until the revert
(gitops#1934).

`service.containerPort` moves only the container. The Service and Ingress stay
on `service.port` and reach the pod through the named targetPort `http`, which
follows the containerPort. This test pins down both directions:

- unset, every rendering is what it was before the value existed;
- set, only the container port changes.

It covers both workload kinds, because the chart renders a Deployment *or* a
Rollout and the two templates are maintained by hand.

Run: python3 tests/test_base_service_container_port.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
SERVICES = pathlib.Path("platform-gitops/services")

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values=None, values_file=None, name="test", namespace="labs"):
    """helm template the chart with `values` (or a values file) over the defaults."""
    if values_file is None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            yaml.safe_dump(values, fh)
            values_file = fh.name
    proc = subprocess.run(
        ["helm", "template", name, str(CHART), "-f", str(values_file),
         "--namespace", namespace],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"helm template failed for {values_file}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def ports(docs):
    """(kind, containerPort, {service name: (port, targetPort)}, [ingress numbers])."""
    work = [d for d in docs if d.get("kind") in ("Deployment", "Rollout")
            and d["metadata"]["name"].startswith("test-")]
    assert len(work) == 1, f"expected one workload, got {[d['kind'] for d in work]}"
    container = work[0]["spec"]["template"]["spec"]["containers"][0]
    http = [p for p in container.get("ports", []) if p.get("name") == "http"]
    assert len(http) == 1, f"expected one http port, got {container.get('ports')}"
    services = {}
    for d in docs:
        if d.get("kind") == "Service":
            for p in d["spec"]["ports"]:
                if p["name"] == "http":
                    services[d["metadata"]["name"]] = (p["port"], p["targetPort"])
    ingress = []
    for d in docs:
        if d.get("kind") == "Ingress":
            for rule in d["spec"].get("rules", []):
                for path in rule["http"]["paths"]:
                    ingress.append(path["backend"]["service"]["port"]["number"])
    return work[0]["kind"], http[0]["containerPort"], services, ingress


BASE = {
    "image": {"repository": "ghcr.io/mctlhq/example", "tag": "1.0.0"},
    "ingress": {"enabled": True, "hosts": ["example.mctl.ai"]},
}
KINDS = {
    "Deployment": {},
    "Rollout": {"blueGreen": {"enabled": True}},
}


for kind_name, extra in KINDS.items():
    # 1. Unset: the container listens on service.port, as before the value
    #    existed, and the Service and Ingress agree with it.
    kind, cport, services, ingress = ports(render({
        **BASE, **extra, "service": {"port": 80}}))
    check(kind == kind_name, f"{kind_name}: rendered {kind}")
    check(cport == 80, f"{kind_name}, unset: containerPort {cport}, want 80")
    check(services and all(v == (80, "http") for v in services.values()),
          f"{kind_name}, unset: Service ports {services}, want (80, 'http')")
    check(ingress and all(n == 80 for n in ingress),
          f"{kind_name}, unset: Ingress backends {ingress}, want 80")

    # 2. Set: only the container moves. The Service (and the blueGreen
    #    preview Service) keeps port 80 with the named targetPort, and the
    #    Ingress keeps 80, so a live service needs no Service port change.
    kind, cport, services, ingress = ports(render({
        **BASE, **extra, "service": {"port": 80, "containerPort": 8080}}))
    check(cport == 8080, f"{kind_name}, set: containerPort {cport}, want 8080")
    check(services and all(v == (80, "http") for v in services.values()),
          f"{kind_name}, set: Service ports {services}, want (80, 'http')")
    check(ingress and all(n == 80 for n in ingress),
          f"{kind_name}, set: Ingress backends {ingress}, want 80")

    # 3. The probes name the port rather than number it, so they follow the
    #    container wherever it listens.
    docs = render({**BASE, **extra, "service": {"port": 80, "containerPort": 8080}})
    work = [d for d in docs if d.get("kind") == kind_name][0]
    container = work["spec"]["template"]["spec"]["containers"][0]
    for probe in ("livenessProbe", "readinessProbe", "startupProbe"):
        if probe in container:
            port = container[probe]["httpGet"]["port"]
            check(port == "http",
                  f"{kind_name}: {probe} uses port {port!r}, want the name 'http'")

# 4. Every real service: unless it sets containerPort, the container still
#    listens on service.port. The chart change alone moves nothing.
count = 0
for values_file in sorted(SERVICES.glob("*/*/values.yaml")):
    data = yaml.safe_load(values_file.read_text()) or {}
    if data.get("chart", "base-service") != "base-service":
        continue
    try:
        kind, cport, services, ingress = ports(render(values_file=values_file))
    except AssertionError as exc:
        # Not a single main workload (not a base-service app); other tests own it.
        print(f"skip {values_file}: {str(exc).splitlines()[0]}", file=sys.stderr)
        continue
    count += 1
    svc = data.get("service") or {}
    want = svc.get("containerPort", svc.get("port", 8080))
    check(cport == want,
          f"{values_file}: containerPort {cport}, want {want}")
check(count > 10, f"only {count} service values rendered; the glob is wrong")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"base-service containerPort: unset keeps service.port, set moves only the container; Deployment and Rollout agree; {count} services unchanged")
