"""Guard the control-plane failure-path inventory (mctlhq/mctl-gitops#2210).

Checks platform-gitops/governance/control-plane-failure-paths.yaml:
schema and closed sets, tracked_by on non-monitored rows, vm-rules alerts
exist, chart-default alerts are allowlisted and pinned to the chart version,
and an alert muted to receiver "null" cannot back a monitored row.

Run: python3 tests/test_control_plane_failure_paths.py
"""
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / "platform-gitops/governance/control-plane-failure-paths.yaml"
MONITORING = REPO / "platform-gitops/bootstrap/templates/observability/monitoring.yaml"
RULES = REPO / "platform-gitops/infra-components/observability/vm-rules"
CLASSES = {"etcd", "apiserver", "admission", "cp-node", "alerting-path"}
STATUSES = {"monitored", "partial", "unmonitored", "unverified"}
REQUIRED = ("id", "class", "failure", "blast_radius", "detection", "status", "evidence", "recovery")
# Pinned to this victoria-metrics-k8s-stack version; re-review on a bump.
CHART_VERSION = "0.72.5"
CHART_DEFAULT_ALERTS = {
    "KubeAPIDown", "KubeAPIErrorBudgetBurn", "KubeAPITerminatedRequests",
    "KubeClientCertificateExpiration", "KubeControllerManagerDown",
    "KubeSchedulerDown", "KubePodNotReady",
}


def rule_alerts(rules_dir):
    names = set()
    for f in pathlib.Path(rules_dir).glob("*.y*ml"):
        names.update(re.findall(r"^\s*-?\s*alert:\s*(\S+)", f.read_text(), re.M))
    return names


def null_routed(text):
    """Alert names matched by a null route whose only matcher is alertname."""
    names = set()
    pat = re.compile(r'receiver:\s*"null"\s*\n\s*matchers:\s*\n((?:[ \t]*-[ \t]+alertname[^\n]*\n|[ \t]*-[ \t]+(?!receiver)[^\n]*\n)+)')
    for m in pat.finditer(text):
        lines = [l.strip() for l in m.group(1).splitlines() if l.strip().startswith("-")]
        if len(lines) != 1:
            continue
        a = re.match(r'-\s*alertname\s*(=~|=)\s*"([^"]+)"', lines[0])
        if a:
            names.update(a.group(2).split("|"))
    return names


def chart_version(text):
    m = re.search(r'chart:\s*victoria-metrics-k8s-stack\s*\n\s*targetRevision:\s*"?([\w.]+)"?', text)
    return m.group(1) if m else None


def check(doc, alerts, nulls, live_chart_version):
    errs = []
    if doc.get("chart_version") != live_chart_version or CHART_VERSION != live_chart_version:
        errs.append(f"chart version {live_chart_version} differs from pinned allowlist {CHART_VERSION}")
    for p in doc.get("paths") or []:
        pid = p.get("id", "?")
        for k in REQUIRED:
            if k not in p:
                errs.append(f"{pid}: missing {k}")
        if p.get("class") not in CLASSES:
            errs.append(f"{pid}: bad class {p.get('class')}")
        if p.get("status") not in STATUSES:
            errs.append(f"{pid}: bad status {p.get('status')}")
        if p.get("status") != "monitored" and not p.get("tracked_by"):
            errs.append(f"{pid}: non-monitored without tracked_by")
        det = p.get("detection") or []
        if p.get("status") == "monitored" and not det:
            errs.append(f"{pid}: monitored without detection")
        live = [d for d in det if d.get("alert") not in nulls]
        if p.get("status") == "monitored" and not live:
            errs.append(f"{pid}: monitored but every alert is routed to null")
        for d in det:
            a, src = d.get("alert"), d.get("source")
            if src == "vm-rules" and a not in alerts:
                errs.append(f"{pid}: vm-rules alert {a} not found")
            elif src == "chart-default" and a not in CHART_DEFAULT_ALERTS:
                errs.append(f"{pid}: chart-default alert {a} not allowlisted")
            elif src not in ("vm-rules", "chart-default"):
                errs.append(f"{pid}: bad source {src}")
    return errs


def main():
    doc = yaml.safe_load(MANIFEST.read_text())
    text = MONITORING.read_text()
    args = (rule_alerts(RULES), null_routed(text), chart_version(text))
    errs = check(doc, *args)

    base = {"chart_version": CHART_VERSION, "paths": []}
    good = {"id": "x", "class": "etcd", "failure": "f", "blast_radius": "b", "evidence": [],
            "recovery": "r", "detection": [{"alert": "KubeAPIDown", "source": "chart-default"}],
            "status": "monitored"}
    def neg(**kw):
        return check({**base, "paths": [{**good, **kw}]}, *args)
    assert not neg(), "baseline row must pass"
    if not neg(status="bogus"):
        errs.append("negative T2 did not fail")
    if not neg(status="unmonitored"):
        errs.append("negative T3 did not fail")
    if not neg(detection=[{"alert": "EtcdSnapshotStale", "source": "vm-rules"}]):
        errs.append("negative T4 did not fail")
    if not neg(detection=[{"alert": "KubeSchedulerDown", "source": "chart-default"}]):
        errs.append("negative T5 did not fail")
    if not check({**base, "chart_version": "9.9.9"}, args[0], args[1], args[2]):
        errs.append("negative T6 did not fail")

    for e in errs:
        print("FAIL:", e)
    if errs:
        sys.exit(1)
    print(f"ok: {len(doc['paths'])} control-plane failure paths")


if __name__ == "__main__":
    main()
