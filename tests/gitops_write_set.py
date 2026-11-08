"""Shared helpers for the tests that track who holds the gitops write credentials
(tracker: mctlhq/mctl-gitops#1033).

Not a test: imported by test_gitops_write_credential_holders.py,
test_gitops_tenant_template_write_set.py and test_read_steps_no_credential.py,
which are run as `python3 tests/<file>.py` (the script directory is on sys.path).

"Could not observe" is never "observed absent": every unreadable or unparsable
input raises ReadError, and the callers let it fail the test.
"""
import pathlib
import re
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Kubernetes Secret names that carry write access to this repository or the
# token that dispatches its image builds, and the Vault paths they come from.
SECRET_NAMES = ("mctl-gitops-deploy-key", "github-actions-pat")
VAULT_PATHS = ("platform/argo-workflows/gitops-deploy-key",
               "platform/argo-workflows/github-actions-pat")
# The same deploy key as an Actions environment secret (CI bump jobs).
CI_SECRET_NAMES = ("GITOPS_BUMP_DEPLOY_KEY",)
ALL_NAMES = SECRET_NAMES + VAULT_PATHS + CI_SECRET_NAMES


class ReadError(Exception):
    """An input could not be read or parsed. Never means 'nothing found'."""


def strip_comment_lines(text):
    return "\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("#"))


def mentions(text, names=ALL_NAMES):
    """Names that appear on a non-comment line of `text`."""
    code = strip_comment_lines(text)
    return {n for n in names if n in code}


def _keys(path):
    return [p for p in path if isinstance(p, str)]


def sites_in_doc(doc, names=ALL_NAMES):
    """Every place a parsed document refers to one of `names`.

    Returns a sorted list of (document, template, mechanism, name). `mechanism`
    is the last two mapping keys leading to the reference (for example
    `secret.secretName` for a volume, `secretKeyRef.name` for an env var,
    `secretRef.name` for envFrom, `secret.name` for a projected source,
    `metadata.name` for an ExternalSecret), or `text:<key>` when the name occurs
    inside a longer string such as a script body (comment lines ignored).
    Nothing is selected by mechanism: any occurrence counts, so a mechanism this
    function has never seen is still reported.
    """
    if not isinstance(doc, dict):
        return []
    meta = doc.get("metadata") or {}
    if doc.get("kind"):
        label = f"{doc['kind']}/{meta.get('name', '?') if isinstance(meta, dict) else '?'}"
    else:
        label = f"document/{doc.get('name', '?')}"  # for example a GitHub Actions workflow
    out = []

    def walk(node, path, template):
        if isinstance(node, dict):
            for k, v in node.items():
                t = template
                if path and path[-1] == "jobs":  # GitHub Actions: the job id is the locator
                    t = str(k)
                walk(v, path + [k], t)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                t = template
                if path and path[-1] == "templates" and isinstance(v, dict) and "name" in v:
                    t = str(v["name"])
                walk(v, path + [i], t)
        elif isinstance(node, str):
            ks = _keys(path)
            if node in names:
                out.append((label, template, ".".join(ks[-2:]), node))
            else:
                for n in sorted(mentions(node, names)):
                    out.append((label, template, f"text:{ks[-1] if ks else '-'}", n))

    walk(doc, [], "-")
    return sorted(out)


def load_docs(path):
    try:
        return [d for d in yaml.safe_load_all(pathlib.Path(path).read_text()) if d]
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise ReadError(f"{path}: {e}") from e


def helm_render(chart, values_file, release, namespace):
    try:
        proc = subprocess.run(
            ["helm", "template", release, str(chart), "-f", str(values_file),
             "--namespace", namespace],
            capture_output=True, text=True, cwd=ROOT)
    except OSError as e:
        raise ReadError(f"helm not runnable: {e}") from e
    if proc.returncode != 0:
        raise ReadError(f"helm template failed for {release}: {proc.stderr[:300]}")
    try:
        return [d for d in yaml.safe_load_all(proc.stdout) if d]
    except yaml.YAMLError as e:
        raise ReadError(f"helm output for {release} is not YAML: {e}") from e


def tenant_values():
    files = sorted((ROOT / "platform-gitops/tenants").glob("*/values.yaml"))
    if not files:
        raise ReadError("no tenant values files found")
    return files


def container_secret_refs(cont, volumes, names=SECRET_NAMES):
    """Names from `names` a container (or init container, sidecar) can read:
    through a mounted Secret volume (plain or projected), an env secretKeyRef,
    or envFrom. `volumes` is the pod-level plus template-level volume list."""
    refs = set()
    held = {}
    for v in volumes or []:
        if not isinstance(v, dict):
            continue
        sec = v.get("secret") or {}
        if sec.get("secretName") in names:
            held.setdefault(v.get("name"), set()).add(sec["secretName"])
        for src in (v.get("projected") or {}).get("sources") or []:
            s = (src or {}).get("secret") or {}
            if s.get("name") in names:
                held.setdefault(v.get("name"), set()).add(s["name"])
    for m in cont.get("volumeMounts") or []:
        refs |= held.get(m.get("name"), set())
    for e in cont.get("env") or []:
        ref = ((e or {}).get("valueFrom") or {}).get("secretKeyRef") or {}
        if ref.get("name") in names:
            refs.add(ref["name"])
    for e in cont.get("envFrom") or []:
        ref = (e or {}).get("secretRef") or {}
        if ref.get("name") in names:
            refs.add(ref["name"])
    return refs


def workflow_templates(doc):
    """(templates, volumes) of a Workflow-family document: spec.templates for
    templates and workflows, spec.workflowSpec.templates for CronWorkflows."""
    spec = doc.get("spec") or {}
    out = []
    for s in (spec, spec.get("workflowSpec") or {}):
        out.append((s.get("templates") or [], s.get("volumes") or []))
    return out
