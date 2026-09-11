"""Render base-service both ways and assert the container env agrees.

gitops#1189 shipped the OTEL opt-in into `templates/deployment.yaml` only. The
chart renders a Deployment *or* a Rollout -- `rollout.yaml` opens with
`{{- if .Values.blueGreen.enabled }}` and `deployment.yaml` with the negation --
so a blueGreen service setting `otel.enabled: true` got a Rollout with no OTEL
variables at all: no traces, no error, nothing in a diff to look at. One service
(`admins/mctl-web`) is on that path today.

A copy-paste into the second template would have fixed the symptom and left the
cause: two hand-maintained env blocks that drift again the next time one of them
is edited. Both now include `base-service.env`, and this test renders the two
kinds from the same values and compares them, so the next divergence fails here
instead of in production.

It also covers the case with no `env:` key at all, because that is what most
services look like and `hasKey` against a nil map is a template error rather
than a false.

Run: python3 tests/test_base_service_otel_env.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
OTEL_KEYS = {
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values, name="test", namespace="labs"):
    """helm template the chart with `values` merged over the chart defaults."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(values, fh)
        path = fh.name
    proc = subprocess.run(
        ["helm", "template", name, str(CHART), "-f", path,
         "--namespace", namespace],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"helm template failed for {json.dumps(values)}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def workload(docs):
    """The single Deployment or Rollout in a rendering, and its env list."""
    found = [d for d in docs if d.get("kind") in ("Deployment", "Rollout")]
    assert len(found) == 1, f"expected one workload, got {[d['kind'] for d in found]}"
    doc = found[0]
    container = doc["spec"]["template"]["spec"]["containers"][0]
    return doc["kind"], {e["name"]: e.get("value") for e in container.get("env", [])}


BASE = {
    "image": {"repository": "ghcr.io/mctlhq/example", "tag": "1.0.0"},
}


# 1. The defect itself: blueGreen + otel must produce a Rollout that carries
#    the variables, not a Rollout that silently carries none.
kind, env = workload(render({
    **BASE,
    "blueGreen": {"enabled": True},
    "otel": {"enabled": True},
}))
check(kind == "Rollout", f"blueGreen.enabled should render a Rollout, got {kind}")
check(OTEL_KEYS <= set(env),
      f"Rollout is missing {sorted(OTEL_KEYS - set(env))} -- this is gitops#1189")

# 2. Both kinds, same values, same env. This is the guarantee the shared
#    partial exists to give; comparing the two is what keeps them together.
_, dep_env = workload(render({**BASE, "otel": {"enabled": True}}))
_, rol_env = workload(render({
    **BASE, "blueGreen": {"enabled": True}, "otel": {"enabled": True}}))
check(dep_env == rol_env,
      f"Deployment and Rollout env differ:\n  only in Deployment: "
      f"{sorted(set(dep_env) - set(rol_env))}\n  only in Rollout: "
      f"{sorted(set(rol_env) - set(dep_env))}")

# 3. A service with no `env:` key at all -- the shape of most values.yaml
#    files. Must render, and must still get the OTEL variables.
for extra, label in (({}, "no env key"),
                     ({"env": None}, "bare `env:` with nothing under it")):
    _, env = workload(render({**BASE, "otel": {"enabled": True}, **extra}))
    check(OTEL_KEYS <= set(env),
          f"{label}: missing {sorted(OTEL_KEYS - set(env))}")

# 4. Default-off: nothing appears unless a service opts in.
for values, label in (({**BASE}, "Deployment"),
                      ({**BASE, "blueGreen": {"enabled": True}}, "Rollout")):
    _, env = workload(render(values))
    check(not (OTEL_KEYS & set(env)),
          f"{label} carries OTEL vars without otel.enabled: "
          f"{sorted(OTEL_KEYS & set(env))}")

# 5. A service's own `env` wins, and wins by not rendering the default at all:
#    a duplicate name would be resolved by Kubernetes rather than by us.
docs = render({
    **BASE,
    "otel": {"enabled": True},
    "env": {"OTEL_SERVICE_NAME": "chosen-by-the-service"},
})
kind, env = workload(docs)
check(env.get("OTEL_SERVICE_NAME") == "chosen-by-the-service",
      f"service env did not win: OTEL_SERVICE_NAME={env.get('OTEL_SERVICE_NAME')!r}")
names = [e["name"] for e in
         [d for d in docs if d["kind"] == kind][0]
         ["spec"]["template"]["spec"]["containers"][0]["env"]]
check(len(names) == len(set(names)),
      f"duplicate env names rendered: "
      f"{sorted(n for n in set(names) if names.count(n) > 1)}")

# 6. The endpoint is the in-cluster collector, not a guess.
_, env = workload(render({**BASE, "otel": {"enabled": True}}))
# Compared whole rather than by prefix: a prefix test on a URL is the shape
# CodeQL flags as incomplete-URL-substring-sanitization, and the value here is
# a fixed in-cluster address, so there is nothing to match loosely.
check(env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
      == "http://otel-collector.monitoring.svc.cluster.local:4318",
      f"unexpected endpoint {env.get('OTEL_EXPORTER_OTLP_ENDPOINT')!r}")
check(env.get("OTEL_RESOURCE_ATTRIBUTES") == "service.namespace=labs",
      f"namespace not carried: {env.get('OTEL_RESOURCE_ATTRIBUTES')!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("base-service otel env: Deployment and Rollout agree, default-off holds")
