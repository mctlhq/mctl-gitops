#!/usr/bin/env python3
"""Fail when a workflow parameter is interpolated into a shell or Python block.

Argo substitutes `{{inputs.parameters.X}}` into the *text* of a script before
any interpreter parses it. A value carrying a quote and a semicolon therefore
runs as a command, in pods that are root and hold the gitops deploy key, a
Vault token, or GITHUB_PAT. Binding the value through `env:` and reading it as
`"$PARAM_X"` removes the exposure regardless of what the API accepts.

This check is a ratchet, not a clean bill of health. BASELINE below records the
sites that still interpolate, each one tracked in gitops#992; the check fails
on anything NOT in that list, so the count can go down and never up.

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

# (file, template, parameter) still interpolated. Every entry is a known
# injection site tracked in gitops#992 — shrink this list, never grow it.
# The `tpl-*` entries are the harder half: `env_vars` / `secret_env_vars` are
# free-form multi-line user input by design, and one site feeds a quoted
# heredoc whose terminator a crafted value can reproduce, so converting them
# changes the surrounding shell rather than one assignment.
BASELINE: set[tuple[str, str, str]] = {
    ("tpl-git-commit.yaml", "commit-service", p)
    for p in ("image_tag", "port", "host", "env_vars", "secret_env_vars",
              "dockerfile_repo", "service_template")
} | {
    ("tpl-validate-tenant.yaml", "validate", p)
    for p in ("host", "dockerfile_repo", "image_tag", "git_tag", "service_template")
} | {
    ("tpl-vault-write.yaml", "write-service-secrets", "secret_env_vars"),
    ("tpl-vault-write.yaml", "write-service-secrets", "telegram_bot_token"),
    ("tpl-vault-write.yaml", "write-platform-secret", "json_data"),
    ("tpl-vault-write.yaml", "write-platform-secret", "vault_path"),
    ("tpl-git-commit.yaml", "commit-service", "config_patch"),
    ("tpl-git-commit.yaml", "commit-service", "default_model"),
    ("wft-smoke-test.yaml", "run-onboard", "dockerfile_repo"),
    ("wft-smoke-test.yaml", "run-onboard", "git_tag"),
    ("wft-smoke-test.yaml", "run-onboard", "provision_database_on_onboard"),
    ("wft-smoke-test.yaml", "run-deploy", "dockerfile_repo"),
    ("wft-smoke-test.yaml", "run-deploy", "git_tag"),
    ("wft-smoke-test.yaml", "check-pod-running", "previous_generation"),
} | {
    # Internal template parameters whose origin has NOT been traced to a
    # caller-supplied value. They are listed rather than excluded because
    # "looks internal" is the assumption that lets one of these turn out to
    # be user input; each still needs its origin confirmed under gitops#992.
    (f, "assert-attempt", p)
    for f in ("cwft-mctl-agents-implement.yaml", "cwft-mctl-agents-investigate.yaml",
              "cwft-mctl-agents-run.yaml", "cwft-mctl-agents-shepherd.yaml")
    for p in ("primary", "fallback")
}

# Parameters the operations registry constrains with an anchored Pattern or an
# Enum, mirrored here because mctl-api is a different repository and a check
# that silently skips when the other repo is absent is not a check at all.
# Keep in sync with internal/operations/registry.go; an entry here is a claim
# that the API rejects a value the shell would otherwise execute.
CONSTRAINED = {
    "team_name", "tenant_name", "component_name", "service_name", "app_name",
    "component_type", "action", "slug", "service", "skill_name", "file_name",
    "clear_env", "clear_secrets", "provision_database", "skip_health_check",
    "autoscaling_enabled", "allow_internet_egress", "delete_vault_secrets",
    "mode", "dry_run", "issue_url", "max_proposals", "target_tag_pattern",
}


def shell_blocks(tmpl: dict):
    """Every place this template hands text to an interpreter."""
    out = []
    source = (tmpl.get("script") or {}).get("source")
    if source:
        out.append(("script.source", source))
    for key in ("container", "script"):
        for i, arg in enumerate((tmpl.get(key) or {}).get("args") or []):
            if isinstance(arg, str) and "\n" in arg:
                out.append((f"{key}.args[{i}]", arg))
    for c in tmpl.get("initContainers") or []:
        for i, arg in enumerate(c.get("args") or []):
            if isinstance(arg, str) and "\n" in arg:
                out.append((f"initContainers[{c.get('name')}].args[{i}]", arg))
    return out


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
    print("✅ selftest: detector fires on an interpolated parameter")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if not TEMPLATES.is_dir():
        print(f"❌ {TEMPLATES} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    new, stale = [], set(BASELINE)
    for fname, tname, where, param in scan(TEMPLATES):
        key = (fname, tname, param)
        stale.discard(key)
        if key in BASELINE or param in CONSTRAINED:
            continue
        new.append((fname, tname, where, param))

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

    if stale:
        print("❌ BASELINE lists sites that no longer exist — remove them:\n", file=sys.stderr)
        for entry in sorted(stale):
            print(f"   {entry}", file=sys.stderr)
        print("\n   A baseline that outlives its sites stops being a ratchet.\n", file=sys.stderr)
        return 1

    print(f"✅ No new shell interpolation ({len(BASELINE)} known sites remain, gitops#992)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
