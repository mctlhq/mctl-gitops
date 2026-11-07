#!/usr/bin/env python3
"""Fail when the agent-pod label contract is broken (mctl-gitops#2289).

The canonical agent-pod label is `app.kubernetes.io/name: mctl-agents` in
`spec.podMetadata.labels` of an agent (Cluster)WorkflowTemplate. NetworkPolicies
select agent pods by it (allow-agent-ingress of the egress proxy today, the
argo-workflows ingress narrowing in mctl-gitops#2301 next), so it is a security
selector. See docs/runbooks/agent-pod-isolation.md.

Fails when:
  - an agent template lacks the label;
  - a CronWorkflow/Workflow that references an agent template sets
    podMetadata.labels["app.kubernetes.io/name"] to another value;
  - a CronWorkflow/Workflow that runs the agents inline (no agent template
    reference) lacks the label;
  - a non-agent template or run carries the label (it would lose platform paths).

Scans every *.yaml under platform-gitops/argo-workflows/ recursively, so a run
placed outside cluster-templates/ is not silently skipped.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from agent_templates import AGENT_LABEL_KEY, AGENT_LABEL_VALUE, is_agent_cwft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIR = ROOT / "platform-gitops/argo-workflows"
TEMPLATE_KINDS = ("ClusterWorkflowTemplate", "WorkflowTemplate")
RUN_KINDS = ("CronWorkflow", "Workflow")


def _label(spec: dict):
    return ((spec.get("podMetadata") or {}).get("labels") or {}).get(AGENT_LABEL_KEY)


def _template_labels(spec: dict):
    """Yield (template name, label value) for per-template metadata that sets the key.

    Argo applies templates[].metadata.labels to the step pod over podMetadata.
    """
    for t in spec.get("templates") or []:
        labels = ((t or {}).get("metadata") or {}).get("labels") or {}
        if AGENT_LABEL_KEY in labels:
            yield (t or {}).get("name", "?"), labels[AGENT_LABEL_KEY]


def violations(docs: list[tuple[str, dict]]) -> list[str]:
    found: list[str] = []
    agents: set[str] = set()
    templates = [(w, d) for w, d in docs if d.get("kind") in TEMPLATE_KINDS]
    for where, doc in templates:
        name = (doc.get("metadata") or {}).get("name", "")
        spec = doc.get("spec") or {}
        label = _label(spec)
        if is_agent_cwft(name, spec):
            agents.add(name)
            if label != AGENT_LABEL_VALUE:
                found.append(f"{where}: agent template {name} must set spec.podMetadata.labels"
                             f"[{AGENT_LABEL_KEY}] to {AGENT_LABEL_VALUE} (got {label!r})")
            for tname, val in _template_labels(spec):
                if val != AGENT_LABEL_VALUE:
                    found.append(f"{where}: agent template {name} step {tname} overrides "
                                 f"{AGENT_LABEL_KEY} to {val!r} in templates[].metadata.labels")
        elif label == AGENT_LABEL_VALUE:
            found.append(f"{where}: non-agent template {name} carries {AGENT_LABEL_KEY}: "
                         f"{AGENT_LABEL_VALUE}; it would lose platform paths")
        if not is_agent_cwft(name, spec):
            for tname, val in _template_labels(spec):
                if val == AGENT_LABEL_VALUE:
                    found.append(f"{where}: non-agent template {name} step {tname} carries "
                                 f"{AGENT_LABEL_KEY}: {AGENT_LABEL_VALUE}; it would lose platform paths")
    if not agents:
        found.append("no agent templates found; glob or detection changed")

    for where, doc in docs:
        if doc.get("kind") not in RUN_KINDS:
            continue
        spec = doc.get("spec") or {}
        wspec = spec.get("workflowSpec") if doc["kind"] == "CronWorkflow" else spec
        wspec = wspec or {}
        ref = (wspec.get("workflowTemplateRef") or {}).get("name")
        label = _label(wspec)
        name = (doc.get("metadata") or {}).get("name", "")
        inline_agent = is_agent_cwft(name, wspec)
        if ref in agents or inline_agent:
            for tname, val in _template_labels(wspec):
                if val != AGENT_LABEL_VALUE:
                    found.append(f"{where}: agent run overrides {AGENT_LABEL_KEY} to {val!r} "
                                 f"in inline template {tname}")
        else:
            if label == AGENT_LABEL_VALUE:
                found.append(f"{where}: non-agent run {name} carries {AGENT_LABEL_KEY}: "
                             f"{AGENT_LABEL_VALUE}; it would lose platform paths")
            for tname, val in _template_labels(wspec):
                if val == AGENT_LABEL_VALUE:
                    found.append(f"{where}: non-agent run {name} step {tname} carries "
                                 f"{AGENT_LABEL_KEY}: {AGENT_LABEL_VALUE}; it would lose platform paths")
        if ref in agents and label is not None and label != AGENT_LABEL_VALUE:
            found.append(f"{where}: references agent template {ref} but sets podMetadata "
                         f"{AGENT_LABEL_KEY}: {label}")
        elif inline_agent and ref not in agents and label != AGENT_LABEL_VALUE:
            found.append(f"{where}: inline agent run {name} must set podMetadata.labels"
                         f"[{AGENT_LABEL_KEY}] to {AGENT_LABEL_VALUE} (got {label!r})")
    return found


def load(directory: Path) -> list[tuple[str, dict]]:
    docs: list[tuple[str, dict]] = []
    for path in sorted(directory.rglob("*.yaml")):
        where = str(path.relative_to(directory))
        try:
            parsed = list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError as e:
            # An unreadable file is not an empty one: its runs would go unchecked.
            raise SystemExit(f"ERROR: {where}: cannot parse YAML: {e}")
        for doc in parsed:
            if isinstance(doc, dict):
                docs.append((where, doc))
    return docs


def _fixture() -> list[tuple[str, dict]]:
    agent = {"kind": "ClusterWorkflowTemplate", "metadata": {"name": "mctl-agents-x"},
             "spec": {"podMetadata": {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}},
                      "templates": [{"name": "a", "container": {"image": "{{workflow.parameters.agent_image}}"}}]}}
    platform = {"kind": "ClusterWorkflowTemplate", "metadata": {"name": "deploy"},
                "spec": {"templates": [{"name": "a", "container": {"image": "alpine"}}]}}
    cron = {"kind": "CronWorkflow", "metadata": {"name": "c"},
            "spec": {"workflowSpec": {"workflowTemplateRef": {"name": "mctl-agents-x", "clusterScope": True}}}}
    return [("agent.yaml", agent), ("platform.yaml", platform), ("cron.yaml", cron)]


def selftest() -> int:
    def no_label(d): del d[0][1]["spec"]["podMetadata"]
    def wrong_label(d): d[0][1]["spec"]["podMetadata"]["labels"][AGENT_LABEL_KEY] = "other"
    def cron_override(d): d[2][1]["spec"]["workflowSpec"]["podMetadata"] = {"labels": {AGENT_LABEL_KEY: "x"}}
    def platform_labelled(d): d[1][1]["spec"]["podMetadata"] = {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}}
    def image_only(d):
        d[0][1]["metadata"]["name"] = "renamed"
        d[0][1]["spec"]["templates"][0]["container"]["image"] = "ghcr.io/mctlhq/mctl-agents:1"
        del d[0][1]["spec"]["podMetadata"]

    def tmpl_override(d): d[0][1]["spec"]["templates"][0]["metadata"] = {"labels": {AGENT_LABEL_KEY: "other"}}
    def platform_tmpl_labelled(d):
        d[1][1]["spec"]["templates"][0]["metadata"] = {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}}
    def cron_inline_override(d):
        d[2][1]["spec"]["workflowSpec"]["templates"] = [
            {"name": "i", "metadata": {"labels": {AGENT_LABEL_KEY: "x"}}}]

    def inline_agent_run(labelled):
        def mut(d):
            wspec = {"templates": [{"name": "a", "container": {"image": "ghcr.io/mctlhq/mctl-agents:1"}}]}
            if labelled:
                wspec["podMetadata"] = {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}}
            d.append(("run.yaml", {"kind": "Workflow", "metadata": {"name": "w"}, "spec": wspec}))
        return mut

    def platform_run(where):
        def mut(d):
            wspec = {"workflowTemplateRef": {"name": "deploy", "clusterScope": True}}
            if where == "pod":
                wspec["podMetadata"] = {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}}
            else:
                wspec["templates"] = [{"name": "i", "metadata": {"labels": {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}}}]
            d.append(("run.yaml", {"kind": "Workflow", "metadata": {"name": "p"}, "spec": wspec}))
        return mut

    cases = [("clean", None, False), ("missing label", no_label, True),
             ("wrong label", wrong_label, True), ("cron override", cron_override, True),
             ("platform carries label", platform_labelled, True),
             ("image-detected agent without label", image_only, True),
             ("template-level override", tmpl_override, True),
             ("platform template-level agent label", platform_tmpl_labelled, True),
             ("cron inline template override", cron_inline_override, True),
             ("inline agent run without label", inline_agent_run(False), True),
             ("inline agent run with label", inline_agent_run(True), False),
             ("platform run carries label", platform_run("pod"), True),
             ("platform run template-level agent label", platform_run("step"), True)]
    ok = True
    for label, mut, should_fail in cases:
        docs = copy.deepcopy(_fixture())
        if mut:
            mut(docs)
        failed = bool(violations(docs))
        if failed != should_fail:
            print(f"selftest FAIL: {label}: failed={failed}, expected {should_fail}")
            ok = False
    ok = _selftest_load() and ok
    if ok:
        print("selftest ok")
    return 0 if ok else 1


def _selftest_load() -> bool:
    """The scan must reach nested directories and refuse unparseable YAML."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        nested = Path(tmp) / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "run.yaml").write_text("kind: Workflow\nmetadata: {name: w}\n")
        if [w for w, _ in load(Path(tmp))] != ["a/b/run.yaml"]:
            print("selftest FAIL: nested directory not scanned")
            return False
        (nested / "bad.yaml").write_text("kind: [unclosed\n")
        try:
            load(Path(tmp))
        except SystemExit:
            return True
        print("selftest FAIL: unparseable YAML accepted")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", type=Path, default=SCAN_DIR)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    found = violations(load(args.dir))
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        print("(mctl-gitops#2289, docs/runbooks/agent-pod-isolation.md)", file=sys.stderr)
        return 1
    print("agent pod labels ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
