#!/usr/bin/env python3
"""Validate invariants for the node-local Argo workdir rollout."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVISIONER = (
    ROOT
    / "platform-gitops/bootstrap/templates/core-infra/local-path-provisioner.yaml"
)
QUOTA = ROOT / "platform-gitops/argo-workflows/config/local-workdir-quota.yaml"
CANARY = (
    ROOT
    / "platform-gitops/argo-workflows/cluster-templates/"
    "cwft-argo-local-workdir-canary.yaml"
)
ALERTS = (
    ROOT
    / "platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml"
)
SMOKE = (
    ROOT
    / "platform-gitops/argo-workflows/cluster-templates/wft-smoke-test.yaml"
)
AGENT_TEMPLATE_DIR = (
    ROOT / "platform-gitops/argo-workflows/cluster-templates"
)
AGENT_TEMPLATES = (
    "cwft-mctl-agents-reconcile.yaml",
    "cwft-mctl-agents-implement.yaml",
    "cwft-mctl-agents-investigate.yaml",
    "cwft-mctl-agents-issue-poll.yaml",
    "cwft-mctl-agents-run.yaml",
    "cwft-mctl-agents-shepherd.yaml",
)
WORKERS = {
    "mctl-preprod-worker-cx43-fsn1-ftx",
    "mctl-preprod-worker-cx43-fsn1-hnn",
    "mctl-preprod-worker-cx43-fsn1-xgf",
}
LOCAL_PATH = "/var/lib/mctl/argo-workdir"
LOCAL_CLASS = "argo-workdir-local"
LOCAL_QUOTA_RESOURCE = (
    "argo-workdir-local.storageclass.storage.k8s.io/requests.storage"
)


def documents(path: Path) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(path.read_text()) if doc]


def only(docs: list[dict], kind: str, name: str) -> dict:
    matches = [
        doc
        for doc in docs
        if doc.get("kind") == kind
        and doc.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{kind}/{name}: expected one document, found {len(matches)}"
        )
    return matches[0]


def validate_provisioner() -> None:
    docs = documents(PROVISIONER)
    storage_class = only(docs, "StorageClass", LOCAL_CLASS)
    assert storage_class["provisioner"] == "rancher.io/local-path"
    assert storage_class["volumeBindingMode"] == "WaitForFirstConsumer"
    assert storage_class["reclaimPolicy"] == "Delete"
    assert storage_class["allowVolumeExpansion"] is False

    config_map = only(docs, "ConfigMap", "local-path-config")
    config = json.loads(config_map["data"]["config.json"])
    mapping = {
        item["node"]: item["paths"] for item in config["nodePathMap"]
    }
    assert set(mapping) == WORKERS
    assert all(paths == [LOCAL_PATH] for paths in mapping.values())
    assert "DEFAULT_PATH_FOR_NON_LISTED_NODES" not in mapping
    assert 'mkdir -m 0777 -p "$VOL_DIR"' in config_map["data"]["setup"]

    deployment = only(docs, "Deployment", "local-path-provisioner")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].endswith("local-path-provisioner:v0.0.36")


def validate_quota() -> None:
    quota = only(documents(QUOTA), "ResourceQuota", "argo-workdir-local")
    hard = quota["spec"]["hard"]
    assert hard == {LOCAL_QUOTA_RESOURCE: "48Gi"}


def validate_canary() -> None:
    canary = only(
        documents(CANARY), "ClusterWorkflowTemplate", "argo-local-workdir-canary"
    )
    spec = canary["spec"]
    assert spec["volumeClaimGC"]["strategy"] == "OnWorkflowCompletion"
    claim = spec["volumeClaimTemplates"][0]
    assert claim["spec"]["storageClassName"] == LOCAL_CLASS
    assert claim["spec"]["resources"]["requests"]["storage"] == "1Gi"

    templates = {template["name"]: template for template in spec["templates"]}
    assert {"verify-local-workdir", "write-marker", "pause", "read-marker"} <= set(
        templates
    )
    assert templates["pause"]["suspend"] == {}
    for name in ("write-marker", "read-marker"):
        mounts = templates[name]["container"]["volumeMounts"]
        assert {"name": "workdir", "mountPath": "/workdir"} in mounts
        security = templates[name]["container"]["securityContext"]
        assert security["runAsNonRoot"] is True
        assert security["runAsUser"] == 65534


def validate_alerts() -> None:
    rules = only(documents(ALERTS), "VMRule", "mctl-custom-alerts")
    by_name = {
        rule["alert"]: rule
        for group in rules["spec"]["groups"]
        for rule in group.get("rules", [])
        if "alert" in rule
    }
    expected = {
        "ArgoLocalWorkdirPodPending",
        "ArgoLocalWorkdirQuotaHigh",
        "ArgoLocalWorkdirQuotaCritical",
        "NodeDiskSpaceHigh",
        "NodeDiskSpaceCritical",
    }
    assert expected <= set(by_name)

    pending = by_name["ArgoLocalWorkdirPodPending"]["expr"]
    assert "kube_pod_spec_volumes_persistentvolumeclaims_info" in pending
    assert "kube_persistentvolumeclaim_info" in pending
    assert 'storageclass="argo-workdir-local"' in pending
    assert by_name["ArgoLocalWorkdirPodPending"]["for"] == "10m"

    high = by_name["ArgoLocalWorkdirQuotaHigh"]["expr"]
    critical = by_name["ArgoLocalWorkdirQuotaCritical"]["expr"]
    assert LOCAL_QUOTA_RESOURCE in high
    assert LOCAL_QUOTA_RESOURCE in critical
    assert "> 0.80" in high
    assert "> 0.95" in critical


def validate_smoke_flow() -> None:
    smoke = only(documents(SMOKE), "ClusterWorkflowTemplate", "smoke-test")
    spec = smoke["spec"]
    parameters = {
        parameter["name"]: parameter.get("value")
        for parameter in spec["arguments"]["parameters"]
    }
    assert parameters["component_type"] == "worker-service"
    assert parameters["git_tag"] == "main"
    assert parameters["provision_database_on_onboard"] == "false"

    templates = {template["name"]: template for template in spec["templates"]}
    pipeline = [
        step[0]["name"] for step in templates["smoke-pipeline"]["steps"]
    ]
    assert pipeline.index("onboard") < pipeline.index("verify-pod")
    assert pipeline.index("verify-k8s-secret") < pipeline.index(
        "verify-db-wiring"
    )
    assert pipeline[-2:] == ["retire", "verify-retired"]

    onboard = templates["run-onboard"]["script"]["source"]
    assert 'value: "${PROVISION_DB}"' in onboard
    assert 'eq \\$node.displayName \\"provision-database\\"' in onboard
    assert 'eq \\$node.displayName \\"commit\\"' in onboard
    assert all(
        expression.startswith("workflow.parameters.")
        for expression in re.findall(r"\{\{([^}]+)\}\}", onboard)
    )
    assert "DB_FINISHED" in onboard and "COMMIT_STARTED" in onboard

    pod_check = templates["check-pod-running"]["script"]["source"]
    assert "CreateContainerConfigError" in pod_check
    assert "secret .* not found" in pod_check

    assert "check-db-secret-wiring" in templates
    assert "check-retired" in templates


def validate_opted_in_agent_templates() -> None:
    for filename in AGENT_TEMPLATES:
        template = documents(AGENT_TEMPLATE_DIR / filename)[0]
        spec = template["spec"]
        claims = spec.get("volumeClaimTemplates", [])
        local_claims = [
            claim
            for claim in claims
            if claim.get("spec", {}).get("storageClassName") == LOCAL_CLASS
        ]
        if not local_claims:
            continue
        assert spec["volumeClaimGC"]["strategy"] == "OnWorkflowCompletion"
        assert len(local_claims) == len(claims)


def main() -> int:
    checks = (
        validate_provisioner,
        validate_quota,
        validate_canary,
        validate_alerts,
        validate_smoke_flow,
        validate_opted_in_agent_templates,
    )
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        sys.exit(1)
