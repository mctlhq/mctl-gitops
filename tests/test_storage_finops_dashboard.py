"""Validate declarative storage & finops dashboard ConfigMaps.

Checks:
- mctl-finops-storage-dashboard ConfigMap metadata and labels.
- Embedded Grafana JSON schema, panel ID uniqueness, and PromQL query semantics.
- Verification that LocalDir quota queries scope to argo-workflows and argo-workdir-local.
- Verification that PV capacity breakdown joins on persistentvolume to propagate storageclass.
- Verification that mctl-platform-dashboard includes Node Disk % panel with link to /d/mctl-finops-storage.
- Full YAML and inner JSON validity of all dashboards in infra-components/observability/grafana-dashboards/.

Run: python3 tests/test_storage_finops_dashboard.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS_DIR = (
    ROOT
    / "platform-gitops"
    / "infra-components"
    / "observability"
    / "grafana-dashboards"
)
FINOPS_DASHBOARD = (
    DASHBOARDS_DIR / "mctl-finops-storage-dashboard-configmap.yaml"
)
PLATFORM_DASHBOARD = (
    DASHBOARDS_DIR / "mctl-platform-dashboard-configmap.yaml"
)

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def test_finops_storage_dashboard_structure() -> None:
    check(FINOPS_DASHBOARD.exists(), f"{FINOPS_DASHBOARD} does not exist")
    doc = yaml.safe_load(FINOPS_DASHBOARD.read_text())

    check(doc.get("apiVersion") == "v1", f"unexpected apiVersion: {doc.get('apiVersion')}")
    check(doc.get("kind") == "ConfigMap", f"unexpected kind: {doc.get('kind')}")
    metadata = doc.get("metadata", {})
    check(
        metadata.get("name") == "mctl-finops-storage-dashboard",
        f"unexpected metadata.name: {metadata.get('name')}",
    )
    check(
        metadata.get("namespace") == "monitoring",
        f"unexpected metadata.namespace: {metadata.get('namespace')}",
    )
    check(
        metadata.get("labels", {}).get("grafana_dashboard") == "1",
        f"missing grafana_dashboard: '1' label: {metadata.get('labels')}",
    )

    data = doc.get("data", {})
    check(
        "mctl-finops-storage.json" in data,
        f"mctl-finops-storage.json key missing from data: {list(data.keys())}",
    )

    dashboard = json.loads(data["mctl-finops-storage.json"])
    check(dashboard.get("uid") == "mctl-finops-storage", f"unexpected uid: {dashboard.get('uid')}")
    check(dashboard.get("title") == "mctl — Storage & FinOps", f"unexpected title: {dashboard.get('title')}")

    panels = dashboard.get("panels", [])
    check(len(panels) > 0, "dashboard has no panels")

    panel_ids = [p["id"] for p in panels if "id" in p]
    check(len(panel_ids) == len(set(panel_ids)), f"duplicate panel IDs found: {panel_ids}")

    # Check panel 1: LocalDir Quota Saturation
    p1 = next((p for p in panels if p.get("id") == 1), None)
    check(p1 is not None, "panel 1 (LocalDir Quota Saturation) missing")
    if p1:
        expr = p1["targets"][0]["expr"]
        check(
            'namespace="argo-workflows"' in expr and 'argo-workdir-local.storageclass.storage.k8s.io/requests.storage' in expr,
            f"panel 1 missing namespace or resource quota scoping: {expr}",
        )

    # Check panel 5: LocalDir Quota Usage vs Limit
    p5 = next((p for p in panels if p.get("id") == 5), None)
    check(p5 is not None, "panel 5 (LocalDir Quota Usage vs Limit) missing")
    if p5:
        expr = p5["targets"][0]["expr"]
        check(
            'namespace="argo-workflows"' in expr and 'argo-workdir-local.storageclass.storage.k8s.io/requests.storage' in expr,
            f"panel 5 missing namespace or resource scoping: {expr}",
        )

    # Check panel 12: Persistent Volumes Total Capacity join
    p12 = next((p for p in panels if p.get("id") == 12), None)
    check(p12 is not None, "panel 12 (PV Capacity by StorageClass) missing")
    if p12:
        expr = p12["targets"][0]["expr"]
        check(
            "group_left(storageclass)" in expr and "on (persistentvolume)" in expr,
            f"panel 12 does not join with kube_persistentvolume_info on persistentvolume: {expr}",
        )


def test_platform_dashboard_node_disk() -> None:
    check(PLATFORM_DASHBOARD.exists(), f"{PLATFORM_DASHBOARD} does not exist")
    doc = yaml.safe_load(PLATFORM_DASHBOARD.read_text())
    dashboard = json.loads(doc["data"]["mctl-platform.json"])
    panels = dashboard.get("panels", [])

    disk_panel = next((p for p in panels if p.get("title") == "Node Disk %"), None)
    check(disk_panel is not None, "Node Disk % panel not found in mctl-platform dashboard")
    if disk_panel:
        check(
            "node_filesystem_avail_bytes" in disk_panel["targets"][0]["expr"],
            f"unexpected expr in Node Disk % panel: {disk_panel['targets'][0]['expr']}",
        )
        links = disk_panel.get("fieldConfig", {}).get("defaults", {}).get("links", [])
        check(
            any(l.get("url") == "/d/mctl-finops-storage" for l in links),
            f"Node Disk % panel missing link to /d/mctl-finops-storage: {links}",
        )


def test_all_dashboards_valid() -> None:
    for path_str in glob.glob(str(DASHBOARDS_DIR / "*.yaml")):
        p = Path(path_str)
        try:
            docs = list(yaml.safe_load_all(p.read_text()))
            for doc in docs:
                if not doc:
                    continue
                check(doc.get("kind") == "ConfigMap", f"{p.name}: not a ConfigMap")
                check(
                    doc.get("metadata", {}).get("labels", {}).get("grafana_dashboard") == "1",
                    f"{p.name}: missing grafana_dashboard: '1' label",
                )
                for k, v in doc.get("data", {}).items():
                    if k.endswith(".json"):
                        json.loads(v)
        except Exception as exc:
            failures.append(f"{p.name} failed validation: {exc}")


def main() -> int:
    test_finops_storage_dashboard_structure()
    test_platform_dashboard_node_disk()
    test_all_dashboards_valid()

    if failures:
        print(f"FAILED ({len(failures)} failures):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("PASS: all dashboard tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
