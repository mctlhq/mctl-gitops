"""Render base-service and assert the main container pauses before SIGTERM.

Deleting a pod and removing it from the Service's endpoints happen in
parallel. Without a pause the main process can exit while Traefik still
routes to the pod: gitops#1946 replaced admins/mctl-web's only pod one second
after its successor was Ready and still served one 502. `preStopSleepSeconds`
renders the kubelet's native preStop sleep on the main container.

This pins down, for both workload kinds (the chart renders a Deployment *or*
a Rollout, and the two templates are maintained by hand):

- the default is a 5s sleep;
- a custom value is rendered, and 0 renders no lifecycle at all;
- a sleep that reaches terminationGracePeriodSeconds (default 30, and an
  explicit 0 counts) fails the render instead of being cut short by SIGKILL;
- the grace period the guard checks is the one rendered on the pod;
- every real service renders the sleep on its main container.

Run: python3 tests/test_base_service_prestop_sleep.py
"""
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
SERVICES = pathlib.Path("platform-gitops/services")
KINDS = ("Deployment", "Rollout")

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def helm(values_file):
    return subprocess.run(
        ["helm", "template", "test", str(CHART), "-f", str(values_file),
         "--namespace", "labs"],
        capture_output=True, text=True)


def render(values):
    """Return (docs, stderr); docs is None when the render failed."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as fh:
        yaml.safe_dump(values, fh)
        fh.flush()
        proc = helm(fh.name)
    if proc.returncode != 0:
        return None, proc.stderr
    return [d for d in yaml.safe_load_all(proc.stdout) if d], ""


def main_container(docs):
    workloads = [d for d in docs if d.get("kind") in KINDS]
    if len(workloads) != 1:
        raise AssertionError(f"want one Deployment or Rollout, got {len(workloads)}")
    return workloads[0]["kind"], workloads[0]["spec"]["template"]["spec"]["containers"][0]


def base(kind, **extra):
    values = {"image": {"tag": "1.0.0"},
              "blueGreen": {"enabled": kind == "Rollout"}}
    values.update(extra)
    return values


for kind in KINDS:
    # 1. Default: a native 5s sleep on the main container.
    docs, err = render(base(kind))
    check(docs is not None, f"{kind}: default render failed: {err}")
    if docs:
        got_kind, c = main_container(docs)
        check(got_kind == kind, f"rendered {got_kind}, want {kind}")
        check(c.get("lifecycle") == {"preStop": {"sleep": {"seconds": 5}}},
              f"{kind} default: lifecycle {c.get('lifecycle')}")

    # 2. A custom value is rendered as given.
    docs, err = render(base(kind, preStopSleepSeconds=10))
    check(docs is not None, f"{kind}: preStopSleepSeconds=10 failed: {err}")
    if docs:
        _, c = main_container(docs)
        check(c.get("lifecycle", {}).get("preStop", {}).get("sleep") == {"seconds": 10},
              f"{kind} 10s: lifecycle {c.get('lifecycle')}")

    # 3. 0 turns it off entirely.
    docs, err = render(base(kind, preStopSleepSeconds=0))
    check(docs is not None, f"{kind}: preStopSleepSeconds=0 failed: {err}")
    if docs:
        _, c = main_container(docs)
        check("lifecycle" not in c, f"{kind} 0: still renders {c.get('lifecycle')}")

    # 4. The sleep must stay below the grace period, default or explicit.
    for extra, label in (({"preStopSleepSeconds": 30}, "30 vs default 30"),
                         ({"preStopSleepSeconds": 20,
                           "terminationGracePeriodSeconds": 20}, "20 vs 20")):
        docs, err = render(base(kind, **extra))
        check(docs is None and "must be below terminationGracePeriodSeconds" in err,
              f"{kind} {label}: render should fail, got {'ok' if docs else err}")
    docs, err = render(base(kind, preStopSleepSeconds=30,
                            terminationGracePeriodSeconds=60))
    check(docs is not None, f"{kind} 30 vs 60: render failed: {err}")

    # 5. An explicit grace of 0 is a real value, not "unset": the default
    #    sleep must fail against it, and turning the sleep off must pass.
    docs, err = render(base(kind, terminationGracePeriodSeconds=0))
    check(docs is None and "must be below terminationGracePeriodSeconds" in err,
          f"{kind} 5 vs grace 0: render should fail, got {'ok' if docs else err}")
    docs, err = render(base(kind, preStopSleepSeconds=0,
                            terminationGracePeriodSeconds=0))
    check(docs is not None, f"{kind} 0 vs grace 0: render failed: {err}")

    # 6. The grace period the guard checks against is the one the pod gets.
    docs, err = render(base(kind, terminationGracePeriodSeconds=60))
    if docs:
        workload = next(d for d in docs if d.get("kind") in KINDS)
        got = workload["spec"]["template"]["spec"].get("terminationGracePeriodSeconds")
        check(got == 60, f"{kind}: terminationGracePeriodSeconds {got} rendered, want 60")

# 7. Every real service gets the default sleep on its main container.
count = 0
for values_file in sorted(SERVICES.glob("*/*/values.yaml")):
    data = yaml.safe_load(values_file.read_text()) or {}
    if data.get("chart", "base-service") != "base-service":
        continue
    proc = helm(values_file)
    if proc.returncode != 0:
        failures.append(f"{values_file}: render failed: {proc.stderr.strip()}")
        continue
    try:
        _, c = main_container([d for d in yaml.safe_load_all(proc.stdout) if d])
    except AssertionError as exc:
        print(f"skip {values_file}: {exc}", file=sys.stderr)
        continue
    count += 1
    want = data.get("preStopSleepSeconds", 5)
    got = (c.get("lifecycle") or {}).get("preStop", {}).get("sleep", {}).get("seconds", 0)
    check(got == want, f"{values_file}: preStop sleep {got}, want {want}")
check(count > 10, f"only {count} service values rendered; the glob is wrong")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"base-service preStop sleep: 5s default, custom and 0 honoured, capped below the grace period, Deployment and Rollout agree; {count} services covered")
