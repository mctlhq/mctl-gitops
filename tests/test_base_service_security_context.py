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
# What a service sets to opt in to step 2.
STRICT = {"containerSecurityContext": {"runAsNonRoot": True,
                                       "readOnlyRootFilesystem": True}}
STRICT_SC = {**DEFAULT_SC, "runAsNonRoot": True, "readOnlyRootFilesystem": True}

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


def writable(spec):
    """(mountPath -> volume name) for the main container's emptyDir mounts."""
    empty = {v["name"] for v in spec.get("volumes") or [] if "emptyDir" in v}
    return {m["mountPath"]: m["name"]
            for m in spec["containers"][0].get("volumeMounts") or []
            if m["name"] in empty}


for extra, label in (({}, "Deployment"), ({"blueGreen": {"enabled": True}}, "Rollout")):
    # 6. Without an opt-in nothing changes: no step-2 keys, no emptyDirs.
    _, spec = pod_spec(render({**BASE, **extra}))
    check(writable(spec) == {} and "volumes" not in spec,
          f"{label}: default renders writable mounts {writable(spec)!r}")

    # 7. Opting in merges over the defaults and brings a writable /tmp.
    _, spec = pod_spec(render({**BASE, **extra, **STRICT}))
    check(spec["containers"][0].get("securityContext") == STRICT_SC,
          f"{label}: opted-in securityContext = "
          f"{spec['containers'][0].get('securityContext')!r}")
    check(writable(spec) == {"/tmp": "writable-tmp"},
          f"{label}: opted-in writable mounts = {writable(spec)!r}")

    # 8. A service lists the full set; each path gets its own emptyDir.
    _, spec = pod_spec(render({**BASE, **extra, **STRICT,
                               "writablePaths": ["/tmp", "/var/cache/nginx"]}))
    check(writable(spec) == {"/tmp": "writable-tmp",
                             "/var/cache/nginx": "writable-var-cache-nginx"},
          f"{label}: listed writable mounts = {writable(spec)!r}")

    # 9. A path the service already mounts itself is not mounted twice
    #    (the API rejects duplicate mountPaths).
    _, spec = pod_spec(render({
        **BASE, **extra, **STRICT,
        "extraVolumes": [{"name": "scratch", "emptyDir": {}}],
        "extraVolumeMounts": [{"name": "scratch", "mountPath": "/tmp"}]}))
    paths = [m["mountPath"] for m in spec["containers"][0]["volumeMounts"]]
    check(paths == ["/tmp"],
          f"{label}: /tmp already in extraVolumeMounts, got mounts {paths!r}")

    # 10. A path listed twice is mounted once.
    _, spec = pod_spec(render({**BASE, **extra, **STRICT,
                               "writablePaths": ["/tmp", "/tmp"]}))
    check(writable(spec) == {"/tmp": "writable-tmp"}
          and len(spec.get("volumes") or []) == 1,
          f"{label}: repeated path renders volumes {spec.get('volumes')!r}")

    # 11. Two paths whose volume names collide fail the render with a
    #    readable message, instead of a duplicate-name error at apply time.
    try:
        render({**BASE, **extra, **STRICT,
                "writablePaths": ["/var/cache/nginx", "/var/cache-nginx"]})
        check(False, f"{label}: colliding writablePaths rendered without error")
    except AssertionError as err:
        check("both map to volume" in str(err),
              f"{label}: colliding writablePaths failed without the message: {err}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("base-service securityContext: container keys win, defaults fill gaps, "
      "step 2 is opt-in, writablePaths mount once, Deployment and Rollout agree")
