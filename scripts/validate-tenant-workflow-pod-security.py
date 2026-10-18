#!/usr/bin/env python3
"""Fail when a workflow that runs in a tenant namespace is not Pod Security
"restricted"-compliant.

mctl-api's operations.WorkflowNamespace submits the ClusterWorkflowTemplates
in ENTRY_FILES into the tenant's own namespace. Those namespaces are moving
from enforce=baseline to enforce=restricted (handoff audit, block B step 3),
and once they are, a non-compliant pod is rejected at creation, which fails
every deploy, preview, rollback and retire of that tenant.

Checked for each entry workflow:
  * spec.securityContext: runAsNonRoot true, a numeric non-zero runAsUser,
    seccompProfile RuntimeDefault. Argo uses it as the pod securityContext
    of every step, including steps reached through templateRef.
  * spec.podSpecPatch: the init, wait and main containers set
    allowPrivilegeEscalation false and drop ALL capabilities (not inherited
    from the pod securityContext; Argo's own init/wait run as root by
    default).
  * no template-level securityContext or podSpecPatch that would replace or
    override the above.

Checked for every step in ENTRY_FILES and REFERENCED_FILES:
  * nothing installs packages or writes /usr/local/bin at runtime (needs
    root); bake it into mctl-workflow-tools instead.
  * a step that uses ssh runs mctl-workflow-tools: OpenSSH refuses to run
    for a uid with no passwd entry ("No user exists for uid 1000"), and the
    upstream alpine images have none.
  * no container securityContext re-grants root or privileges.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CWFT_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"

# Must match the workflows mctl-api runs in the tenant namespace (every
# template not listed in operations.WorkflowNamespace's platform cases).
ENTRY_FILES = (
    "wft-deploy-service.yaml",
    "wft-preview-deploy.yaml",
    "wft-preview-delete.yaml",
    "wft-provision-database.yaml",
    "wft-rollback-service.yaml",
    "wft-retire-service.yaml",
    "wft-smoke-test.yaml",
)
# Reached through templateRef (or the controller's exit hook) from the
# entry workflows; their pods run under the entry workflow's spec.
REFERENCED_FILES = (
    "tpl-git-commit.yaml",
    "tpl-validate-tenant.yaml",
    "tpl-vault-write.yaml",
    "cwft-global-workflow-completion-hook.yaml",
)

TOOLS_IMAGE = "ghcr.io/mctlhq/mctl-workflow-tools:"
ROOT_ONLY_RE = re.compile(r"\b(apk add|apt-get|apt install|yum install|dnf install)\b|/usr/local/bin/")
SSH_RE = re.compile(r"git@github\.com|~/\.ssh|\$HOME/\.ssh|\bssh\b")


def _drops_all(sc: dict) -> bool:
    return "ALL" in ((sc.get("capabilities") or {}).get("drop") or [])


def _check_pod_sc(where: str, sc: dict | None) -> list[str]:
    sc = sc or {}
    bad = []
    if sc.get("runAsNonRoot") is not True:
        bad.append(f"{where}: securityContext.runAsNonRoot must be true")
    uid = sc.get("runAsUser")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid == 0:
        bad.append(f"{where}: securityContext.runAsUser must be a numeric non-root uid")
    if (sc.get("seccompProfile") or {}).get("type") not in ("RuntimeDefault", "Localhost"):
        bad.append(f"{where}: securityContext.seccompProfile.type must be RuntimeDefault")
    return bad


def _check_container_sc(where: str, sc: dict | None, required: bool) -> list[str]:
    sc = sc or {}
    bad = []
    if required:
        if sc.get("allowPrivilegeEscalation") is not False:
            bad.append(f"{where}: allowPrivilegeEscalation must be false")
        if not _drops_all(sc):
            bad.append(f"{where}: capabilities.drop must contain ALL")
    if sc.get("privileged") is True:
        bad.append(f"{where}: privileged is not allowed")
    if sc.get("allowPrivilegeEscalation") is True:
        bad.append(f"{where}: allowPrivilegeEscalation true is not allowed")
    if sc.get("runAsNonRoot") is False or sc.get("runAsUser") == 0:
        bad.append(f"{where}: container must not run as root")
    if (sc.get("capabilities") or {}).get("add"):
        bad.append(f"{where}: capabilities.add is not allowed")
    return bad


def check_entry(name: str, doc: dict) -> list[str]:
    spec = doc.get("spec") or {}
    bad = _check_pod_sc(f"{name} spec", spec.get("securityContext"))
    raw = spec.get("podSpecPatch")
    if not raw:
        bad.append(f"{name} spec: podSpecPatch for init/wait/main is missing")
    else:
        try:
            patch = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            return bad + [f"{name} spec: podSpecPatch is not valid YAML: {exc}"]
        ctrs = {c.get("name"): c for c in (patch.get("containers") or [])}
        inits = {c.get("name"): c for c in (patch.get("initContainers") or [])}
        for label, table, cname in (("initContainer", inits, "init"),
                                    ("container", ctrs, "wait"),
                                    ("container", ctrs, "main")):
            if cname not in table:
                bad.append(f"{name} spec.podSpecPatch: {label} {cname} is missing")
                continue
            bad += _check_container_sc(f"{name} spec.podSpecPatch {cname}",
                                       table[cname].get("securityContext"), required=True)
    for tpl in spec.get("templates") or []:
        where = f"{name}:{tpl.get('name')}"
        if "securityContext" in tpl:
            bad.append(f"{where}: template-level securityContext replaces the workflow's; set it on spec")
        if "podSpecPatch" in tpl:
            bad.append(f"{where}: template-level podSpecPatch can override the workflow's; not allowed")
    return bad


def check_steps(name: str, doc: dict) -> list[str]:
    bad = []
    for tpl in (doc.get("spec") or {}).get("templates") or []:
        body = tpl.get("script") or tpl.get("container")
        if not body:
            continue
        where = f"{name}:{tpl.get('name')}"
        text = "\n".join(str(x) for x in [body.get("source") or ""]
                         + list(body.get("command") or []) + list(body.get("args") or []))
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(lines)
        m = ROOT_ONLY_RE.search(code)
        if m:
            bad.append(f"{where}: '{m.group(0)}' needs root at runtime; bake it into mctl-workflow-tools")
        image = str(body.get("image") or "")
        if SSH_RE.search(code) and not image.startswith(TOOLS_IMAGE):
            bad.append(f"{where}: uses ssh but runs {image!r}; ssh needs a passwd entry, use {TOOLS_IMAGE}<tag>")
        bad += _check_container_sc(where, body.get("securityContext"), required=False)
    return bad


def _load(directory: Path) -> dict[str, dict]:
    docs = {}
    for fname in ENTRY_FILES + REFERENCED_FILES:
        path = directory / fname
        if not path.is_file():
            raise FileNotFoundError(f"{path} is listed but missing; update the lists in this script")
        docs[fname] = yaml.safe_load(path.read_text())
    return docs


def violations(docs: dict[str, dict]) -> list[str]:
    found = []
    for fname, doc in docs.items():
        if fname in ENTRY_FILES:
            found += check_entry(fname, doc)
        found += check_steps(fname, doc)
    return found


def _step(docs: dict, fname: str, tname: str) -> dict:
    for tpl in docs[fname]["spec"]["templates"]:
        if tpl.get("name") == tname:
            return tpl.get("script") or tpl.get("container")
    raise KeyError(f"{fname}:{tname}")


def selftest() -> int:
    """Each mutation of the real templates must be caught; the unmodified set must pass."""
    base = _load(CWFT_DIR)

    def m_nonroot(d):
        del d["wft-deploy-service.yaml"]["spec"]["securityContext"]["runAsNonRoot"]

    def m_seccomp(d):
        del d["wft-rollback-service.yaml"]["spec"]["securityContext"]["seccompProfile"]

    def m_wait(d):
        p = yaml.safe_load(d["wft-preview-deploy.yaml"]["spec"]["podSpecPatch"])
        p["containers"] = [c for c in p["containers"] if c["name"] != "wait"]
        d["wft-preview-deploy.yaml"]["spec"]["podSpecPatch"] = yaml.safe_dump(p)

    def m_init_drop(d):
        p = yaml.safe_load(d["wft-smoke-test.yaml"]["spec"]["podSpecPatch"])
        p["initContainers"][0]["securityContext"]["capabilities"]["drop"] = []
        d["wft-smoke-test.yaml"]["spec"]["podSpecPatch"] = yaml.safe_dump(p)

    def m_apk(d):
        s = _step(d, "tpl-vault-write.yaml", "write-platform-secret")
        s["source"] = "apk add --no-cache curl\n" + s["source"]

    def m_usrlocal(d):
        s = _step(d, "tpl-git-commit.yaml", "commit-service")
        s["source"] += "\nmv /tmp/linux-amd64/helm /usr/local/bin/helm\n"

    def m_ssh_image(d):
        _step(d, "wft-rollback-service.yaml", "patch-values")["image"] = "alpine/git:2.45.2"

    def m_tpl_sc(d):
        d["wft-retire-service.yaml"]["spec"]["templates"][0]["securityContext"] = {"runAsUser": 0}

    def m_priv(d):
        _step(d, "cwft-global-workflow-completion-hook.yaml", "notify-completion")["securityContext"] = {
            "privileged": True}

    cases = [("real templates", None, False), ("no runAsNonRoot", m_nonroot, True),
             ("no seccomp", m_seccomp, True), ("no wait in patch", m_wait, True),
             ("init keeps caps", m_init_drop, True), ("apk add", m_apk, True),
             ("write /usr/local/bin", m_usrlocal, True), ("ssh on alpine/git", m_ssh_image, True),
             ("template securityContext", m_tpl_sc, True), ("privileged step", m_priv, True)]
    ok = True
    for label, mut, should_fail in cases:
        docs = copy.deepcopy(base)
        if mut:
            mut(docs)
        found = violations(docs)
        if bool(found) != should_fail:
            print(f"selftest FAIL: {label}: violations={found[:3]}, expected failure={should_fail}")
            ok = False
    if ok:
        print(f"selftest ok ({len(cases)} cases)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    found = violations(_load(CWFT_DIR))
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        return 1
    print(f"tenant workflow pod security ok ({len(ENTRY_FILES)} entry, {len(REFERENCED_FILES)} referenced)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
