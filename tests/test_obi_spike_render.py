#!/usr/bin/env python3
"""issue-2286 T1: the OBI spike render, flag off and flag on.

Flag off (the committed default): no object of the spike renders, and the
bootstrap output is byte-identical to the same chart with obi-spike.yaml
removed.

Flag on (tests/fixtures/obi-spike.example-values.yaml): the render pins
  - the exact capabilities.add list, drop [ALL], privileged false, hostPID
    true, hostNetwork false and the hostPath list;
  - no tolerations, and the control-plane DoesNotExist node affinity;
  - discovery.instrument equal to obiSpike.targets, with no glob characters;
  - ClusterRole verbs of get/list/watch only;
  - no mctl.me/tenant label on the spike namespace.

Run: python3 tests/test_obi_spike_render.py   (needs helm)
"""
import datetime
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
VALUES = CHART / "values.yaml"
OVERLAY = ROOT / "tests" / "fixtures" / "obi-spike.example-values.yaml"
TEMPLATE = "templates/observability/obi-spike.yaml"
SPIKE_NS = "observability-obi-spike"

CAPS = ["BPF", "PERFMON", "SYS_PTRACE", "DAC_READ_SEARCH", "CHECKPOINT_RESTORE"]
HOST_PATHS = ["/sys/fs/cgroup"]
GLOBS = set("*?[]{}")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def helm(chart, *extra):
    return subprocess.run(["helm", "template", "t", str(chart), "-f", str(VALUES), *extra],
                          capture_output=True, text=True, check=True).stdout


def docs(rendered):
    return [d for d in yaml.safe_load_all(rendered) if d]


def is_spike(d):
    meta = d["metadata"]
    return (meta.get("name") == SPIKE_NS or meta.get("namespace") == SPIKE_NS
            or str(meta.get("name", "")).startswith(("obi-", "obi"))
            or meta.get("name") == "allow-otel-collector-ingress-obi-spike")


def main():
    # Flag off.
    off = helm(CHART)
    check(not any(is_spike(d) for d in docs(off)), "flag off: spike objects rendered")
    with tempfile.TemporaryDirectory() as tmp:
        stripped = pathlib.Path(tmp) / "bootstrap"
        shutil.copytree(CHART, stripped)
        (stripped / TEMPLATE).unlink()
        check(off == helm(stripped), "flag off: render differs from the chart without obi-spike.yaml")

    # Flag on.
    teardown = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    on = docs(helm(CHART, "-f", str(OVERLAY), "--set", f"obiSpike.teardownAfter={teardown}"))
    by = {(d["kind"], d["metadata"].get("namespace"), d["metadata"]["name"]): d for d in on}

    ns = by[("Namespace", None, SPIKE_NS)]
    check("mctl.me/tenant" not in ns["metadata"]["labels"], "spike namespace carries mctl.me/tenant")
    check(ns["metadata"]["labels"].get("pod-security.kubernetes.io/enforce") == "privileged", "PSA label")
    check(ns["metadata"]["annotations"].get("mctl.ai/teardown-after") == teardown, "teardown annotation")

    ds = by[("DaemonSet", SPIKE_NS, "obi")]
    pod = ds["spec"]["template"]["spec"]
    c = pod["containers"][0]
    sc = c["securityContext"]
    check(sc["capabilities"]["add"] == CAPS, f"capabilities.add: {sc['capabilities']['add']}")
    check(sc["capabilities"]["drop"] == ["ALL"], "capabilities.drop")
    check(sc["privileged"] is False, "privileged")
    check(pod["hostPID"] is True, "hostPID")
    check(pod["hostNetwork"] is False, "hostNetwork")
    paths = [v["hostPath"]["path"] for v in pod["volumes"] if "hostPath" in v]
    check(paths == HOST_PATHS, f"hostPath list: {paths}")
    check("tolerations" not in pod, "DaemonSet has tolerations")
    terms = pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    check(terms == [{"matchExpressions": [{"key": "node-role.kubernetes.io/control-plane", "operator": "DoesNotExist"}]}],
          "control-plane anti-affinity")
    check("@sha256:" in c["image"], "image is not pinned by digest")

    values = yaml.safe_load(VALUES.read_text())["obiSpike"]
    cfg = yaml.safe_load(by[("ConfigMap", SPIKE_NS, "obi-config")]["data"]["config.yaml"])
    inst = [{"namespace": i["k8s_namespace"], "deployment": i["k8s_deployment_name"]}
            for i in cfg["discovery"]["instrument"]]
    check(inst == values["targets"], f"discovery.instrument != obiSpike.targets: {inst}")
    check(not any(GLOBS.intersection(v) for t in inst for v in t.values()), "glob in discovery.instrument")

    for kind in ("ClusterRole",):
        for (k, _, name), d in by.items():
            if k == kind and name in ("obi-spike", "obi-spike-collector"):
                for rule in d["rules"]:
                    check(sorted(rule["verbs"]) == ["get", "list", "watch"], f"{name} verbs: {rule['verbs']}")

    ctx_dep = by[("Deployment", SPIKE_NS, "obi-spike-collector")]
    check("tolerations" not in ctx_dep["spec"]["template"]["spec"], "collector has tolerations")

    # No customer namespace beyond the two fixture tenants.
    allowed = {None, SPIKE_NS, "monitoring", values["fixtures"]["tenantA"], values["fixtures"]["tenantB"]}
    new_objs = [d for d in on if d["kind"] != "Application" and is_spike(d) or
                d["metadata"].get("namespace") in {values["fixtures"]["tenantA"], values["fixtures"]["tenantB"]}]
    for d in new_objs:
        check(d["metadata"].get("namespace") in allowed, f"unexpected namespace on {d['kind']}/{d['metadata']['name']}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print("obi spike render: flag off is empty and byte-identical; flag on pins the privilege set")


if __name__ == "__main__":
    main()
