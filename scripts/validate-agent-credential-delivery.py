#!/usr/bin/env python3
"""Fail when an agent credential regains an env seed or a loose file mount.

mctl-gitops#2288: credentials in the mctl-agents ClusterWorkflowTemplates are
classified in platform-gitops/governance/agent-credential-delivery.yaml.

1. Every env[].valueFrom.secretKeyRef in an agent_image step must be listed.
2. A secretKeyRef for a `delivery: file` row fails (the env seed is back).
3. A `delivery: file` row needs a Secret volume item for its key, mounted
   readOnly at mount_path in that container, mode <= 0440, and the file_env
   variable pointing under the mount.
4. A credential volume must not be mounted in an initContainer.

A file mount is NOT model-shell isolation (mctlhq/mctl-agents#869).
Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import argparse
import copy
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CWFT_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"
INVENTORY = ROOT / "platform-gitops/governance/agent-credential-delivery.yaml"
MARKER = "workflow.parameters.agent_image"
MAX_MODE = 0o440


def _body(tpl: dict) -> dict:
    return tpl.get("container") or tpl.get("script") or {}


def _is_agent(tpl: dict) -> bool:
    return MARKER in str(_body(tpl).get("image", ""))


def _secret_refs(containers) -> list[tuple[str, str, str]]:
    out = []
    for c in containers:
        for e in c.get("env") or []:
            ref = (e.get("valueFrom") or {}).get("secretKeyRef")
            if ref:
                out.append((e["name"], ref.get("name", ""), str(ref.get("key", ""))))
    return out


def _volumes(spec: dict, tpl: dict) -> dict:
    return {v["name"]: v for v in (spec.get("volumes") or []) + (tpl.get("volumes") or [])}


def _mode_ok(vol_mode, item_mode) -> bool:
    mode = item_mode if item_mode is not None else vol_mode
    # YAML 1.1 reads 0440 as octal int 288; absent means the k8s default 0644.
    return isinstance(mode, int) and mode <= MAX_MODE


def check_template(where: str, tpl: dict, spec: dict, rows: list[dict]) -> list[str]:
    bad: list[str] = []
    body = _body(tpl)
    mine = rows
    listed = {(r["env"], r["secret"], r["key"]) for r in mine}
    file_rows = [r for r in mine if r["delivery"] == "file"]
    file_envs = {r["env"] for r in file_rows}

    for env, secret, key in _secret_refs([body]):
        if env in file_envs:
            bad.append(f"{where}: {env} regained a secretKeyRef env seed but is delivery: file")
        elif (env, secret, key) not in listed:
            bad.append(f"{where}: {env} secretKeyRef {secret}/{key} is not in the credential inventory")
    for r in mine:
        if r["delivery"] == "env-seed" and not any(
            (e, s, k) == (r["env"], r["secret"], r["key"]) for e, s, k in _secret_refs([body])
        ):
            bad.append(f"{where}: inventory says env-seed for {r['env']} but no secretKeyRef is set")

    vols = _volumes(spec, tpl)
    file_vols = set()
    for r in file_rows:
        found = None
        for m in body.get("volumeMounts") or []:
            v = vols.get(m["name"])
            for item in ((v or {}).get("secret") or {}).get("items") or []:
                if item.get("key") == r["key"] and v["secret"].get("secretName") == r["secret"]:
                    found = (m, v, item)
        if not found:
            bad.append(f"{where}: {r['env']} is delivery: file but no Secret volume item for {r['secret']}/{r['key']} is mounted")
            continue
        m, v, item = found
        file_vols.add(m["name"])
        if m.get("readOnly") is not True:
            bad.append(f"{where}: {r['env']} file mount {m['name']} must be readOnly: true")
        if m.get("mountPath") != r["mount_path"]:
            bad.append(f"{where}: {r['env']} file mount {m['name']} must be at {r['mount_path']}")
        if not _mode_ok(v["secret"].get("defaultMode"), item.get("mode")):
            bad.append(f"{where}: {r['env']} file volume {v['name']} mode must be <= 0440 (set defaultMode: 0440)")
        envs = {e["name"]: e.get("value", "") for e in body.get("env") or []}
        if not str(envs.get(r["file_env"], "")).startswith(r["mount_path"] + "/"):
            bad.append(f"{where}: {r['file_env']} must be set to a path under {r['mount_path']}")

    for init in tpl.get("initContainers") or []:
        for m in init.get("volumeMounts") or []:
            if m["name"] in file_vols:
                bad.append(f"{where}: credential volume {m['name']} must not be mounted in initContainer {init.get('name')}")
    return bad


def violations(directory: Path, inventory: dict) -> list[str]:
    found: list[str] = []
    seen = set()
    matched = 0
    rows = inventory.get("credentials") or []
    for path in sorted(directory.glob("cwft-mctl-agents-*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not isinstance(doc, dict):
                continue
            spec = doc.get("spec") or {}
            for tpl in spec.get("templates") or []:
                if not _is_agent(tpl):
                    continue
                matched += 1
                mine = [r for r in rows if r["cwft"] == path.name and r["template"] == tpl.get("name")]
                seen.update((r["cwft"], r["template"]) for r in mine)
                found += check_template(f"{path.name}:{tpl.get('name')}", tpl, spec, mine)
    if matched == 0:
        found.append(f"no agent_image templates found under {directory}; glob or image expression changed")
    for r in rows:
        if r.get("agent_image") and (r["cwft"], r["template"]) not in seen:
            found.append(f"inventory lists {r['cwft']}:{r['template']} but no such agent_image template exists")
    return found


def _fixture() -> tuple[dict, dict]:
    doc = {"apiVersion": "argoproj.io/v1alpha1", "kind": "ClusterWorkflowTemplate",
           "metadata": {"name": "x"},
           "spec": {"volumes": [{"name": "cred", "secret": {"secretName": "s", "defaultMode": 0o440,
                                                           "items": [{"key": "k", "path": "k"}]}}],
                    "templates": [{"name": "agent",
                                   "container": {"image": "{{workflow.parameters.agent_image}}",
                                                 "env": [{"name": "TOK_FILE", "value": "/var/run/c/k"}],
                                                 "volumeMounts": [{"name": "cred", "mountPath": "/var/run/c",
                                                                   "readOnly": True}]}}]}}
    inv = {"credentials": [{"cwft": "cwft-mctl-agents-x.yaml", "template": "agent", "env": "TOK",
                            "secret": "s", "key": "k", "delivery": "file", "file_env": "TOK_FILE",
                            "mount_path": "/var/run/c", "agent_image": True}]}
    return doc, inv


def selftest() -> int:
    def seed(d):
        d["spec"]["templates"][0]["container"]["env"].append(
            {"name": "TOK", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}})
    def unknown(d):
        d["spec"]["templates"][0]["container"]["env"].append(
            {"name": "OTHER", "valueFrom": {"secretKeyRef": {"name": "s", "key": "o"}}})
    def mode(d): d["spec"]["volumes"][0]["secret"]["defaultMode"] = 0o644
    def rw(d): del d["spec"]["templates"][0]["container"]["volumeMounts"][0]["readOnly"]
    def init(d):
        d["spec"]["templates"][0]["initContainers"] = [
            {"name": "i", "volumeMounts": [{"name": "cred", "mountPath": "/x"}]}]
    cases = [("migrated", None, False), ("env seed restored", seed, True),
             ("unlisted secretKeyRef", unknown, True), ("mode 0644", mode, True),
             ("not readOnly", rw, True), ("init mount", init, True)]
    ok = True
    for label, mut, should_fail in cases:
        doc, inv = _fixture()
        if mut:
            mut(doc)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cwft-mctl-agents-x.yaml").write_text(yaml.safe_dump(copy.deepcopy(doc)))
            res = violations(Path(d), inv)
        failed = bool(res)
        print(f"selftest {'ok' if failed == should_fail else 'FAIL'}: {label}: "
              f"{'rejected' if failed else 'passed'}")
        ok &= failed == should_fail
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", type=Path, default=CWFT_DIR)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    found = violations(args.dir, yaml.safe_load(args.inventory.read_text()))
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        print("(mctl-gitops#2288)", file=sys.stderr)
        return 1
    print("agent credential delivery ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
