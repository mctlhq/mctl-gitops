"""Every Job and CronJob a service renders must pass restricted PodSecurity.

Tenant namespaces enforce `pod-security.kubernetes.io/enforce: restricted`,
so a non-compliant pod is not degraded, it is never created: the CronJob
keeps firing and every Job fails admission. labs-mctl-telegram's
demo-reviewer-watch was such a CronJob (postgres:17-alpine as root, with a
runtime `apk add curl`), and nothing noticed because it is renderIf-gated on
DEMO_REVIEWER_ENABLED and the flag was off.

So for every services/<team>/<service>/values.yaml this renders base-service
twice: as committed, and with every `.Values.env.<FLAG>` that an extraObjects
renderIf reads forced to "true", so a gated object is checked before anyone
flips its flag. In each render, every container and initContainer of a Job,
CronJob or Pod must:

- run as non-root (runAsNonRoot, and no runAsUser 0),
- set allowPrivilegeEscalation: false and drop ALL capabilities,
- have a RuntimeDefault or Localhost seccomp profile (pod or container),
- not be privileged,

a pod that pulls a ghcr.io/mctlhq/ image must set imagePullSecrets (those
packages are private, so without it every run sits in ImagePullBackOff),
and no script may install packages at runtime (that needs root and an
unpinned network fetch).

Run: python3 tests/test_service_extra_jobs_restricted.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
SERVICES = pathlib.Path("platform-gitops/services")
GATE_FLAG = re.compile(r"\.Values\.env\.([A-Za-z0-9_]+)")
PRIVATE_REGISTRY = "ghcr.io/mctlhq/"
PACKAGE_INSTALL = re.compile(r"\b(apk\s+add|apt-get\s+install|apt\s+install|yum\s+install|dnf\s+install|pip3?\s+install)\b")

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values_file, sets):
    cmd = ["helm", "template", "t", str(CHART), "-f", str(values_file)]
    for flag in sets:
        cmd += ["--set-string", f"env.{flag}=true"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"helm template failed for {values_file} {sets}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def pod_spec(doc):
    kind = doc.get("kind")
    if kind == "CronJob":
        return doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    if kind == "Job":
        return doc["spec"]["template"]["spec"]
    if kind == "Pod":
        return doc["spec"]
    return None


def check_pod(where, spec):
    pod_sc = spec.get("securityContext") or {}
    containers = (spec.get("initContainers") or []) + (spec.get("containers") or [])
    check(containers, f"{where}: no containers")
    for c in containers:
        name = f"{where} container {c.get('name')}"
        sc = c.get("securityContext") or {}
        non_root = sc.get("runAsNonRoot", pod_sc.get("runAsNonRoot"))
        check(non_root is True, f"{name}: runAsNonRoot is not true")
        check(sc.get("runAsUser", pod_sc.get("runAsUser")) != 0, f"{name}: runAsUser 0")
        check(sc.get("allowPrivilegeEscalation") is False,
              f"{name}: allowPrivilegeEscalation is not false")
        drop = (sc.get("capabilities") or {}).get("drop") or []
        check("ALL" in drop, f"{name}: capabilities.drop lacks ALL")
        seccomp = (sc.get("seccompProfile") or pod_sc.get("seccompProfile") or {}).get("type")
        check(seccomp in ("RuntimeDefault", "Localhost"), f"{name}: seccompProfile is {seccomp!r}")
        check(not sc.get("privileged"), f"{name}: privileged")
        script = "\n".join(str(x) for x in (c.get("command") or []) + (c.get("args") or []))
        hit = PACKAGE_INSTALL.search(script)
        check(not hit, f"{name}: installs packages at runtime ({hit.group(0) if hit else ''})")
        if str(c.get("image", "")).startswith(PRIVATE_REGISTRY):
            check(spec.get("imagePullSecrets"),
                  f"{name}: pulls {c['image']} without imagePullSecrets")


def gate_flags(values_file):
    values = yaml.safe_load(values_file.read_text()) or {}
    flags = set()
    for obj in values.get("extraObjects") or []:
        flags |= set(GATE_FLAG.findall(str(obj.get("renderIf", ""))))
    return sorted(flags)


def main():
    files = sorted(SERVICES.glob("*/*/values.yaml"))
    if not files:
        raise SystemExit(f"no service values under {SERVICES}")
    pods = 0
    for values_file in files:
        flags = gate_flags(values_file)
        variants = [[]] + ([flags] if flags else [])
        for sets in variants:
            for doc in render(values_file, sets):
                spec = pod_spec(doc)
                if spec is None:
                    continue
                pods += 1
                label = "+".join(sets) or "as committed"
                check_pod(f"{values_file} [{label}] {doc['kind']}/{doc['metadata']['name']}", spec)
    # The gated reviewer CronJobs are what this test exists for; if the gate
    # flip silently stopped rendering them, the test would pass vacuously.
    check(pods >= 3, f"only {pods} Job/CronJob/Pod specs rendered; gate flipping is broken")
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS: {pods} Job/CronJob/Pod specs across {len(files)} services are restricted-compliant")


if __name__ == "__main__":
    main()
