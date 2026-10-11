#!/usr/bin/env python3
"""Fail when a workflow parameter is interpolated into a shell or Python block.

Argo substitutes `{{inputs.parameters.X}}` into the *text* of a script before
any interpreter parses it. A value carrying a quote and a semicolon therefore
runs as a command, in pods that are root and hold the gitops deploy key, a
Vault token, or GITHUB_PAT. Binding the value through `env:` and reading it as
`"$PARAM_X"` removes the exposure regardless of what the API accepts.

This check is a ban, not a ratchet: any `inputs.parameters` or
`workflow.parameters` placeholder (or `{{= ... }}` expression mentioning them)
in a shell block fails, with no allow-list. Which parameters the API happens to
constrain is a claim about another repository; this check does not rely on it.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "platform-gitops/argo-workflows/cluster-templates"

PLACEHOLDER = re.compile(r"\{\{\s*(?:inputs|workflow)\.parameters\.([A-Za-z0-9_.-]+)\s*\}\}")

# `{{= ... }}` expression tags are evaluated by Argo before the shell runs, so
# one that reads a parameter is the same exposure as a plain placeholder.
EXPRESSION = re.compile(r"\{\{=(.*?)\}\}", re.S)
EXPR_PARAM = re.compile(r"parameters\.(\w+)|parameters\[['\"](\w+)")


def shell_blocks(tmpl: dict):
    """Every place this template hands text to an interpreter.

    Every string in `command` and `args` is inspected, not only the
    multi-line ones: an inline `sh -c '... {{inputs.parameters.x}} ...'`
    is a single-line arg and carries exactly the same exposure. Scanning
    short strings costs nothing — they contain no placeholders — while the
    length filter this replaces would have let that shape through
    unnoticed (claude P3 on gitops#993).
    """
    out = []
    source = (tmpl.get("script") or {}).get("source")
    if source:
        out.append(("script.source", source))
    for key in ("container", "script"):
        spec = tmpl.get(key) or {}
        for field in ("command", "args"):
            for i, arg in enumerate(spec.get(field) or []):
                if isinstance(arg, str):
                    out.append((f"{key}.{field}[{i}]", arg))
    for c in tmpl.get("initContainers") or []:
        for field in ("command", "args"):
            for i, arg in enumerate(c.get(field) or []):
                if isinstance(arg, str):
                    out.append((f"initContainers[{c.get('name')}].{field}[{i}]", arg))
    for s in tmpl.get("sidecars") or []:
        for field in ("command", "args"):
            for i, arg in enumerate(s.get(field) or []):
                if isinstance(arg, str):
                    out.append((f"sidecars[{s.get('name')}].{field}[{i}]", arg))
    for c in (tmpl.get("containerSet") or {}).get("containers") or []:
        for field in ("command", "args"):
            for i, arg in enumerate(c.get(field) or []):
                if isinstance(arg, str):
                    out.append((f"containerSet[{c.get('name')}].{field}[{i}]", arg))
    return out


def specs(tmpl: dict):
    """Every container-like spec of a template, as (label, spec, text)."""
    out = []
    for key in ("script", "container"):
        spec = tmpl.get(key)
        if spec:
            parts = [spec.get("source") or ""]
            for field in ("command", "args"):
                parts += [a for a in spec.get(field) or [] if isinstance(a, str)]
            out.append((key, spec, "\n".join(parts)))
    groups = [("initContainers", tmpl.get("initContainers") or []),
              ("sidecars", tmpl.get("sidecars") or []),
              ("containerSet", (tmpl.get("containerSet") or {}).get("containers") or [])]
    for label, items in groups:
        for c in items:
            parts = [a for f in ("command", "args") for a in c.get(f) or []
                     if isinstance(a, str)]
            out.append((f"{label}[{c.get('name')}]", c, "\n".join(parts)))
    return out


PARAM_REF = re.compile(r"\$\{?(PARAM_[A-Z0-9_]+)")
PARAM_PY_REF = re.compile(r"os\.environ\[\"(PARAM_[A-Z0-9_]+)\"\]")


def check_env_bindings(directory: Path):
    """Every PARAM_* a script reads must be defined in that template's own env.

    The conversion this check accompanies is mechanical, and a mechanical
    edit can put the `env:` entries on the neighbouring template — which is
    exactly what happened on gitops#993 and would have broken every preview
    deploy at the first assignment under `set -u`. A missing binding is
    silent in YAML and only fails at run time, so it is checked here.
    """
    problems = []
    for path in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc:
                continue
            for tmpl in (doc.get("spec") or {}).get("templates") or []:
                for label, spec, text in specs(tmpl):
                    if not text.strip():
                        continue
                    defined = [e["name"] for e in spec.get("env") or []]
                    used = set(PARAM_REF.findall(text)) | set(PARAM_PY_REF.findall(text))
                    for name in sorted(used - set(defined)):
                        problems.append(
                            f"{path.name} / {tmpl.get('name')} / {label}: reads ${name}, "
                            f"but this spec's env does not define it")
                    for name in sorted({e for e in defined if defined.count(e) > 1}):
                        problems.append(
                            f"{path.name} / {tmpl.get('name')} / {label}: "
                            f"env defines {name} twice")
    return problems


def scan(directory: Path):
    """Yield (file, template, where, parameter) for every interpolation."""
    for path in sorted(directory.glob("*.yaml")):
        try:
            docs = list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError as exc:
            print(f"❌ {path.name}: not parseable as YAML: {exc}", file=sys.stderr)
            sys.exit(2)
        for doc in docs:
            if not doc:
                continue
            for tmpl in (doc.get("spec") or {}).get("templates") or []:
                for where, text in shell_blocks(tmpl):
                    for m in PLACEHOLDER.finditer(text):
                        yield path.name, tmpl.get("name", "?"), where, m.group(1)
                    for m in EXPRESSION.finditer(text):
                        if not re.search(r"(?:inputs|workflow)\.parameters", m.group(1)):
                            continue
                        p = EXPR_PARAM.search(m.group(1))
                        name = (p.group(1) or p.group(2)) if p else "<expression>"
                        yield path.name, tmpl.get("name", "?"), where, name


def selftest() -> int:
    """Prove the detector fires. A checker nobody has seen fail is not a checker."""
    import tempfile

    doc = {
        "spec": {
            "templates": [{
                "name": "t",
                "script": {"source": 'X="{{inputs.parameters.display_name}}"\n'},
            }]
        }
    }
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        p.write_text(yaml.dump(doc))
        found = list(scan(Path(d)))
    if found != [("bad.yaml", "t", "script.source", "display_name")]:
        print(f"❌ selftest: detector did not fire; got {found}", file=sys.stderr)
        return 1

    def fires(tmpl, want):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.yaml").write_text(
                yaml.dump({"spec": {"templates": [dict(tmpl, name="t")]}}))
            return any(p == want for _, _, _, p in scan(Path(d)))

    cases = {
        "an inline command": ({"container": {
            "command": ["sh", "-c", "echo {{inputs.parameters.host}}"]}}, "host"),
        "a here-document body": ({"script": {
            "source": "cat <<'EOF'\n{{inputs.parameters.x}}\nEOF\n"}}, "x"),
        "a {{= }} expression": ({"script": {
            "source": "echo {{=sprig.trim(inputs.parameters.x)}}\n"}}, "x"),
        "a sidecar arg": ({"sidecars": [{
            "name": "s", "args": ["{{workflow.parameters.x}}"]}]}, "x"),
        "a containerSet arg": ({"containerSet": {"containers": [{
            "name": "c", "args": ["{{workflow.parameters.x}}"]}]}}, "x"),
    }
    for what, (tmpl, want) in cases.items():
        if not fires(tmpl, want):
            print(f"❌ selftest: detector missed {what}", file=sys.stderr)
            return 1

    # A script reading a PARAM_* its own env does not define.
    doc_env = {"spec": {"templates": [{
        "name": "t",
        "script": {"source": 'X="$PARAM_MISSING"\n', "env": [{"name": "PARAM_OTHER"}]},
    }]}}
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "env.yaml").write_text(yaml.dump(doc_env))
        if not check_env_bindings(Path(d)):
            print("❌ selftest: unbound PARAM_* not reported", file=sys.stderr)
            return 1

    print("✅ selftest: detector fires on script.source, an inline command, "
          "a here-document, a {{= }} expression, a sidecar arg, a containerSet arg "
          "and an unbound PARAM_*")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if not TEMPLATES.is_dir():
        print(f"❌ {TEMPLATES} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    new = list(scan(TEMPLATES))

    if new:
        print("❌ Workflow parameters interpolated into a script's text:\n", file=sys.stderr)
        for fname, tname, where, param in new:
            print(f"   {fname} / {tname} / {where}: {param}", file=sys.stderr)
        print(
            "\n   Argo substitutes these BEFORE the interpreter parses the line, so a\n"
            "   value containing a quote and a semicolon executes as a command.\n"
            "   Bind it through env: instead —\n\n"
            "       env:\n"
            "         - name: PARAM_EXAMPLE\n"
            "           value: \"{{inputs.parameters.example}}\"\n\n"
            "   and read it as \"$PARAM_EXAMPLE\". See gitops#992.\n",
            file=sys.stderr,
        )
        return 1

    unbound = check_env_bindings(TEMPLATES)
    if unbound:
        print("❌ PARAM_* read without an env binding in the same template:\n", file=sys.stderr)
        for line in unbound:
            print(f"   {line}", file=sys.stderr)
        print("\n   Under `set -u` this fails at the first assignment, at run time.\n",
              file=sys.stderr)
        return 1

    print("✅ No workflow parameter is interpolated into any shell block")
    return 0


if __name__ == "__main__":
    sys.exit(main())
