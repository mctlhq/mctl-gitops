#!/usr/bin/env python3
"""Fail when an agent-image step lacks the restricted pod posture.

mctl-gitops#1717: every ClusterWorkflowTemplate step that runs the
`agent_image` (model-driven shell) must set a template-level pod
securityContext and a hardened agent container. initContainers on those
templates may be root, but only explicitly, with escalation off and
`capabilities.drop: [ALL]`.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CWFT_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"
MARKER = "workflow.parameters.agent_image"


def _image(tpl: dict) -> str:
    for key in ("container", "script"):
        body = tpl.get(key)
        if isinstance(body, dict):
            return str(body.get("image", ""))
    return ""


def _drops_all(sc: dict) -> bool:
    caps = sc.get("capabilities") or {}
    return "ALL" in (caps.get("drop") or [])


def check_template(where: str, tpl: dict, spec: dict) -> list[str]:
    bad: list[str] = []
    pod = tpl.get("securityContext") or spec.get("securityContext") or {}
    if pod.get("runAsNonRoot") is not True:
        bad.append(f"{where}: pod securityContext.runAsNonRoot must be true")
    if pod.get("runAsUser") != 1000:
        bad.append(f"{where}: pod securityContext.runAsUser must be 1000")
    if pod.get("fsGroup") != 1000:
        bad.append(f"{where}: pod securityContext.fsGroup must be 1000")
    if (pod.get("seccompProfile") or {}).get("type") != "RuntimeDefault":
        bad.append(f"{where}: pod seccompProfile.type must be RuntimeDefault")

    body = tpl.get("container") or tpl.get("script") or {}
    sc = body.get("securityContext") or {}
    if sc.get("allowPrivilegeEscalation") is not False:
        bad.append(f"{where}: container allowPrivilegeEscalation must be false")
    if not _drops_all(sc):
        bad.append(f"{where}: container capabilities.drop must contain ALL")
    if sc.get("runAsNonRoot") is False:
        bad.append(f"{where}: container runAsNonRoot must not be false")

    for init in tpl.get("initContainers") or []:
        isc = init.get("securityContext") or {}
        name = init.get("name", "?")
        if isc.get("allowPrivilegeEscalation") is not False:
            bad.append(f"{where}: initContainer {name} allowPrivilegeEscalation must be false")
        if not _drops_all(isc):
            bad.append(f"{where}: initContainer {name} capabilities.drop must contain ALL")
    return bad


def violations(directory: Path) -> list[str]:
    found: list[str] = []
    matched = 0
    for path in sorted(directory.glob("cwft-mctl-agents-*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not isinstance(doc, dict):
                continue
            spec = doc.get("spec") or {}
            for tpl in spec.get("templates") or []:
                if MARKER in _image(tpl):
                    matched += 1
                    found += check_template(f"{path.name}:{tpl.get('name')}", tpl, spec)
    if matched == 0:
        found.append(f"no agent_image templates found under {directory}; glob or image expression changed")
    return found


def _fixture() -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ClusterWorkflowTemplate",
        "metadata": {"name": "x"},
        "spec": {"templates": [{
            "name": "agent",
            "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000,
                                "fsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
            "initContainers": [{"name": "clone-gitops", "image": "alpine/git",
                                "securityContext": {"runAsUser": 0, "runAsNonRoot": False,
                                                    "allowPrivilegeEscalation": False,
                                                    "capabilities": {"drop": ["ALL"], "add": ["CHOWN"]}}}],
            "container": {"image": "{{workflow.parameters.agent_image}}",
                          "securityContext": {"runAsNonRoot": True, "allowPrivilegeEscalation": False,
                                              "capabilities": {"drop": ["ALL"]}}},
        }]},
    }


def selftest() -> int:
    def mutate_pod(t): del t["securityContext"]
    def mutate_ape(t): del t["container"]["securityContext"]["allowPrivilegeEscalation"]
    def mutate_drop(t): del t["container"]["securityContext"]["capabilities"]
    def mutate_init(t): del t["initContainers"][0]["securityContext"]["capabilities"]["drop"]

    cases = [("hardened", None, False), ("no pod block", mutate_pod, True),
             ("no allowPrivilegeEscalation", mutate_ape, True),
             ("no capabilities.drop", mutate_drop, True),
             ("init without drop ALL", mutate_init, True)]
    ok = True
    for label, mut, should_fail in cases:
        doc = _fixture()
        if mut:
            mut(doc["spec"]["templates"][0])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cwft-mctl-agents-x.yaml").write_text(yaml.safe_dump(doc))
            failed = bool(violations(Path(d)))
        if failed != should_fail:
            print(f"selftest FAIL: {label}: failed={failed}, expected {should_fail}")
            ok = False
    if ok:
        print("selftest ok")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", type=Path, default=CWFT_DIR)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    found = violations(args.dir)
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        print("(mctl-gitops#1717)", file=sys.stderr)
        return 1
    print("agent pod security ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
