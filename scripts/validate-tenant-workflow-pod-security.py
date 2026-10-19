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
  * mctl-workflow-tools is referenced by digest, not by a tag alone.

Also: every wft-*.yaml is classified as tenant (ENTRY_FILES) or platform
(PLATFORM_FILES), so a new tenant workflow cannot slip past this gate
unlisted; the tools Dockerfile still installs what the steps call
(the steps no longer install anything, so a dropped package would only
surface as "not found" at runtime); and every mctl-workflow-tools pin under
platform-gitops/ is the Dockerfile's recorded `published:` build, whose
`built-from:` hash still matches the Dockerfile body, so the package check
describes the image that actually runs.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
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
    "wft-preview-reaper.yaml",
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

# The other wft-* templates: mctl-api submits these into argo-workflows
# (the platform cases of operations.WorkflowNamespace), or an operator / CI
# submits them there directly (bootstrap-platform, lifecycle-bootstrap,
# otel-trace-fixture); none is an mctl-api operation routed to a tenant.
PLATFORM_FILES = (
    "wft-add-custom-domain.yaml",
    "wft-bootstrap-platform.yaml",
    "wft-create-tenant.yaml",
    "wft-delete-tenant-safe.yaml",
    "wft-lifecycle-bootstrap.yaml",
    "wft-otel-trace-fixture.yaml",
    "wft-platform-skill-deprecate.yaml",
    "wft-platform-skill-disable.yaml",
    "wft-platform-skill-enable.yaml",
    "wft-platform-skill-publish.yaml",
    "wft-remove-custom-domain.yaml",
)

TOOLS_IMAGE = "ghcr.io/mctlhq/mctl-workflow-tools:"
# A digest pin is the whole sha256, not just the "@sha256:" marker: a typo'd
# digest would otherwise pass here and fail later with a confusing message.
DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
TOOLS_DOCKERFILE = ROOT / "platform-gitops/images/mctl-workflow-tools/Dockerfile"
PINS_DIR = ROOT / "platform-gitops"
PIN_RE = re.compile(r"ghcr\.io/mctlhq/mctl-workflow-tools:[^\s\"']+")
# Alpine packages the steps call now that they install nothing themselves:
# python3 + py3-yaml for rewrite_preview_values.py and tpl-vault-write's
# heredoc, openssh-client + git for the gitops pushes, curl/openssl/jq
# throughout, ca-certificates for every https call (its loss shows up as a
# TLS verification failure, not a missing binary). yq/helm/kubectl are
# downloaded and sha256-checked separately.
TOOLS_PACKAGES = ("bash", "ca-certificates", "curl", "git", "jq", "openssh-client", "openssl",
                  "python3", "py3-yaml")
TOOLS_BINARIES = ("YQ_VERSION", "HELM_VERSION", "KUBECTL_VERSION")
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
        if image.startswith(TOOLS_IMAGE) and not DIGEST_RE.search(image):
            bad.append(f"{where}: {image!r} must be pinned by digest (@sha256:<64 hex>), not by tag alone")
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


def check_classified(names: set[str]) -> list[str]:
    listed = set(ENTRY_FILES) | set(PLATFORM_FILES)
    bad = [f"{n}: not classified; add it to ENTRY_FILES (runs in the tenant namespace) "
           "or PLATFORM_FILES in this script" for n in sorted(names - listed)]
    bad += [f"{n}: listed in PLATFORM_FILES but missing" for n in sorted(set(PLATFORM_FILES) - names)]
    return bad


def check_dockerfile(text: str) -> list[str]:
    # The RUN line plus its backslash continuations.
    m = re.search(r"^RUN apk add(?:[^\n\\]|\\\n)*", text, re.M)
    pkgs = set(m.group(0).replace("\\", " ").split()) if m else set()
    bad = [f"mctl-workflow-tools Dockerfile: apk add no longer installs {p}"
           for p in TOOLS_PACKAGES if p not in pkgs]
    bad += [f"mctl-workflow-tools Dockerfile: {b} download is gone" for b in TOOLS_BINARIES
            if not re.search(rf"^ARG {b}=", text, re.M)]
    return bad


def check_pins(text: str, pins: list[tuple[str, str]]) -> list[str]:
    """Every pin is the recorded published build, and that build's recorded
    source is still the Dockerfile body (FROM to the end)."""
    published = re.search(r"^#\s+published:\s+(\S+)\s*$", text, re.M)
    built_from = re.search(r"^#\s+built-from:\s+sha256:([0-9a-f]{64})\s*$", text, re.M)
    if not published or not built_from:
        return ["mctl-workflow-tools Dockerfile: header lacks a 'published:' or 'built-from: sha256:' line"]
    ref = published.group(1)
    bad = []
    if not ref.startswith(TOOLS_IMAGE) or not DIGEST_RE.search(ref):
        bad.append(f"mctl-workflow-tools Dockerfile: published {ref!r} must be {TOOLS_IMAGE}<tag>@sha256:<digest>")
    start = text.find("\nFROM ")
    body = text[start + 1:] if start >= 0 else ""
    if hashlib.sha256(body.encode()).hexdigest() != built_from.group(1):
        bad.append("mctl-workflow-tools Dockerfile: body changed since the published build (built-from "
                   "hash mismatch); rebuild, then update published, built-from and every pin")
    if not pins:
        bad.append(f"no {TOOLS_IMAGE} pins found under {PINS_DIR}; the scan is broken")
    bad += [f"{where}: pins {pin!r}, but the Dockerfile's published build is {ref!r}"
            for where, pin in pins if pin != ref]
    return bad


def _pins() -> list[tuple[str, str]]:
    found = []
    for path in sorted(PINS_DIR.rglob("*.y*ml")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            found += [(f"{path.relative_to(ROOT)}:{n}", m.group(0)) for m in PIN_RE.finditer(line)]
    return found


def violations(docs: dict[str, dict], wft_names: set[str] | None = None,
               dockerfile: str | None = None,
               pins: list[tuple[str, str]] | None = None) -> list[str]:
    found = []
    if wft_names is not None:
        found += check_classified(wft_names)
    if dockerfile is not None:
        found += check_dockerfile(dockerfile)
        if pins is not None:
            found += check_pins(dockerfile, pins)
    for fname, doc in docs.items():
        if fname in ENTRY_FILES:
            found += check_entry(fname, doc)
        found += check_steps(fname, doc)
    return found


def _wft_names() -> set[str]:
    return {p.name for p in CWFT_DIR.glob("wft-*.yaml")}


def _step(docs: dict, fname: str, tname: str) -> dict:
    for tpl in docs[fname]["spec"]["templates"]:
        if tpl.get("name") == tname:
            return tpl.get("script") or tpl.get("container")
    raise KeyError(f"{fname}:{tname}")


def selftest() -> int:
    """Each mutation of the real templates must be caught; the unmodified set must pass."""
    base = _load(CWFT_DIR)
    names = _wft_names()
    dockerfile = TOOLS_DOCKERFILE.read_text()
    pins = _pins()

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
        s = _step(d, "tpl-vault-write.yaml", "write-service-secrets")
        s["source"] = "apk add --no-cache curl\n" + s["source"]

    def m_usrlocal(d):
        s = _step(d, "tpl-git-commit.yaml", "commit-service")
        s["source"] += "\nmv /tmp/linux-amd64/helm /usr/local/bin/helm\n"

    def m_ssh_image(d):
        _step(d, "wft-rollback-service.yaml", "patch-values")["image"] = "alpine/git:2.45.2"

    def m_tpl_sc(d):
        d["wft-retire-service.yaml"]["spec"]["templates"][0]["securityContext"] = {"runAsUser": 0}

    def m_tag_only(d):
        s = _step(d, "tpl-git-commit.yaml", "commit-service")
        s["image"] = s["image"].split("@")[0]

    def m_bad_digest(d):
        s = _step(d, "tpl-git-commit.yaml", "commit-service")
        s["image"] = s["image"].split("@")[0] + "@sha256:zz"

    def m_priv(d):
        _step(d, "cwft-global-workflow-completion-hook.yaml", "notify-completion")["securityContext"] = {
            "privileged": True}

    cases = [("real templates", None, False), ("no runAsNonRoot", m_nonroot, True),
             ("no seccomp", m_seccomp, True), ("no wait in patch", m_wait, True),
             ("init keeps caps", m_init_drop, True), ("apk add", m_apk, True),
             ("write /usr/local/bin", m_usrlocal, True), ("ssh on alpine/git", m_ssh_image, True),
             ("template securityContext", m_tpl_sc, True), ("privileged step", m_priv, True),
             ("tools image by tag only", m_tag_only, True),
             ("tools image with a malformed digest", m_bad_digest, True)]
    # Mutations of the inputs outside the templates: (label, wft names, Dockerfile, pins).
    # The package cases pass pins=None: any body edit also breaks the
    # built-from hash, which would mask a package check that stopped working.
    # A header-only edit must stay green: the hash covers FROM onwards.
    # Published line and every pin moved to the same malformed digest, so only
    # the format check can catch it (the pin-equality check stays satisfied).
    bad_ref = re.sub(r"@sha256:[0-9a-f]{64}", "@sha256:zz", pins[0][1]) if pins else ""
    bad_digest = (re.sub(r"(^#\s+published:\s+)\S+", lambda m: m.group(1) + bad_ref, dockerfile, flags=re.M),
                  [(w, bad_ref) for w, _ in pins])
    other_tag = [(w, p.replace(":1.0.0@", ":1.0.1@") if ":1.0.0@" in p else p + "x") for w, p in pins]
    extra = [("unclassified wft", names | {"wft-new-tenant-op.yaml"}, dockerfile, pins, True),
             ("Dockerfile drops py3-yaml", names, dockerfile.replace(" py3-yaml", ""), None, True),
             ("Dockerfile drops ca-certificates", names, dockerfile.replace(" ca-certificates", ""),
              None, True),
             ("Dockerfile drops yq", names, re.sub(r"^ARG YQ_VERSION=.*$", "", dockerfile, flags=re.M),
              None, True),
             ("Dockerfile body edited, hash kept", names,
              dockerfile.replace("USER 1000:1000", "USER 1000:1000\nRUN true"), pins, True),
             ("Dockerfile header comment edited", names,
              dockerfile.replace("# syntax=docker/dockerfile:1\n", "# syntax=docker/dockerfile:1\n# note\n"),
              pins, False),
             ("published line missing", names, re.sub(r"^#\s+published:.*$", "", dockerfile, flags=re.M),
              pins, True),
             ("one pin on another build", names, dockerfile, pins[:1] and [other_tag[0]] + pins[1:], True),
             ("no pins found", names, dockerfile, [], True),
             ("published digest malformed", names, bad_digest[0], bad_digest[1], True)]
    ok = True
    for label, mut, should_fail in cases + [(lbl, None, sf) for lbl, _, _, _, sf in extra]:
        docs = copy.deepcopy(base)
        if mut:
            mut(docs)
        n, df, pn = next(((n, df, pn) for lbl, n, df, pn, _ in extra if lbl == label),
                         (names, dockerfile, pins))
        found = violations(docs, n, df, pn)
        if bool(found) != should_fail:
            print(f"selftest FAIL: {label}: violations={found[:3]}, expected failure={should_fail}")
            ok = False
    if ok:
        print(f"selftest ok ({len(cases) + len(extra)} cases)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    found = violations(_load(CWFT_DIR), _wft_names(), TOOLS_DOCKERFILE.read_text(), _pins())
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        return 1
    print(f"tenant workflow pod security ok ({len(ENTRY_FILES)} entry, {len(REFERENCED_FILES)} referenced, "
          f"{len(_pins())} tools pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
