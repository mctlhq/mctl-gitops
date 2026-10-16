"""Render base-service both ways and assert the container hardening holds.

The chart merges `extraContainerSecurityContext` under every initContainer's
and extraContainer's own `securityContext` through one helper,
`base-service.hardenedContainers`, called from both `deployment.yaml` and
`rollout.yaml`. Two things can go wrong silently:

- the argument order of `merge` decides who wins on a collision. Swapped, the
  chart default would overwrite a container's explicit setting, and an
  explicit `allowPrivilegeEscalation: true` or `capabilities.add` would vanish
  without an error -- or, the other way round, a default could stop applying;
- the chart renders a Deployment OR a Rollout, never both, so an edit to one
  template is invisible in the other's output (the gitops#1189 shape).

This renders both kinds from the same values and checks the merged result, so
either mistake fails here instead of in a tenant namespace.

Run: python3 tests/test_base_service_security_context.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
DEFAULT_SC = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}

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


def pod_spec(docs):
    found = [d for d in docs if d.get("kind") in ("Deployment", "Rollout")]
    assert len(found) == 1, f"expected one workload, got {[d['kind'] for d in found]}"
    return found[0]["kind"], found[0]["spec"]["template"]["spec"]


def by_name(containers):
    return {c["name"]: c.get("securityContext") for c in containers or []}


BASE = {"image": {"repository": "ghcr.io/mctlhq/example", "tag": "1.0.0"}}
CONTAINERS = {
    "initContainers": [
        # Partial securityContext of its own: every key here must survive,
        # and only the missing `capabilities.drop` comes from the default.
        {"name": "own", "image": "busybox",
         "securityContext": {"allowPrivilegeEscalation": True,
                             "runAsUser": 0,
                             "capabilities": {"add": ["NET_ADMIN"]}}},
        # No securityContext at all: gets the default as is. Placed after
        # `own` so a default mutated by the previous iteration shows up here.
        {"name": "bare", "image": "busybox"},
    ],
    "extraContainers": [
        {"name": "sidecar", "image": "busybox",
         "securityContext": {"capabilities": {"drop": ["NET_RAW"]}}},
        {"name": "sidecar-bare", "image": "busybox"},
    ],
}
EXPECTED = {
    "own": {"allowPrivilegeEscalation": True, "runAsUser": 0,
            "capabilities": {"add": ["NET_ADMIN"], "drop": ["ALL"]}},
    "bare": DEFAULT_SC,
    # The container's own `drop` list wins whole; lists are not unioned.
    # This is the case that catches a swapped `merge`: mergo treats `false`
    # as unset, so `own`'s `allowPrivilegeEscalation: true` survives either
    # argument order, but a non-empty list is only kept when the container
    # is the destination.
    "sidecar": {"allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["NET_RAW"]}},
    "sidecar-bare": DEFAULT_SC,
}

rendered = {}
for extra, label in (({}, "Deployment"), ({"blueGreen": {"enabled": True}}, "Rollout")):
    kind, spec = pod_spec(render({**BASE, **CONTAINERS, **extra}))
    check(kind == label, f"expected {label}, got {kind}")
    got = {**by_name(spec.get("initContainers")),
           **by_name(c for c in spec["containers"][1:])}
    rendered[label] = (spec, got)

    # 1. Precedence: the container's keys win, defaults fill only the gaps.
    for name, want in EXPECTED.items():
        check(got.get(name) == want,
              f"{label}: {name} securityContext = {got.get(name)!r}, want {want!r}")

    # 2. The main container and the pod get the chart-level defaults.
    check(spec["containers"][0].get("securityContext") == DEFAULT_SC,
          f"{label}: main container securityContext = "
          f"{spec['containers'][0].get('securityContext')!r}")
    check(spec.get("securityContext") == {"seccompProfile": {"type": "RuntimeDefault"}},
          f"{label}: pod securityContext = {spec.get('securityContext')!r}")

# 3. Both kinds, same values, same pod spec for everything this PR touches.
dep_spec, dep_got = rendered["Deployment"]
rol_spec, rol_got = rendered["Rollout"]
check(dep_got == rol_got,
      f"Deployment and Rollout container securityContexts differ:\n"
      f"  Deployment: {dep_got}\n  Rollout: {rol_got}")
check(dep_spec.get("securityContext") == rol_spec.get("securityContext"),
      "Deployment and Rollout pod securityContexts differ")

# 4. A service can switch the extra-container default off entirely: with it
#    null, containers render exactly as written (no securityContext key added).
for extra, label in (({}, "Deployment"), ({"blueGreen": {"enabled": True}}, "Rollout")):
    _, spec = pod_spec(render({
        **BASE, **extra, "extraContainerSecurityContext": None,
        "initContainers": [{"name": "bare", "image": "busybox"}]}))
    check("securityContext" not in spec["initContainers"][0],
          f"{label}: extraContainerSecurityContext=null still rendered "
          f"{spec['initContainers'][0].get('securityContext')!r}")

# 5. The db-init Job gets the same defaults (it has no per-container override).
# dbSecret is required alongside dbInitJob: the Job reads dbSecret.secretName.
docs = render({**BASE, "dbInitJob": {"enabled": True, "database": "example"},
               "dbSecret": {"vaultPath": "teams/labs/example/database"}})
jobs = [d for d in docs if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-db-init")]
check(len(jobs) == 1, f"expected one db-init Job, got {len(jobs)}")
if jobs:
    jspec = jobs[0]["spec"]["template"]["spec"]
    check(jspec["containers"][0].get("securityContext") == DEFAULT_SC,
          f"db-init container securityContext = {jspec['containers'][0].get('securityContext')!r}")
    check(jspec.get("securityContext") == {"seccompProfile": {"type": "RuntimeDefault"}},
          f"db-init pod securityContext = {jspec.get('securityContext')!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("base-service securityContext: container keys win, defaults fill gaps, "
      "Deployment and Rollout agree")
