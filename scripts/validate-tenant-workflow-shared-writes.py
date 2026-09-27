#!/usr/bin/env python3
"""Fail when a tenant workflow template writes a path not scoped to one tenant.

`wft-create-tenant.yaml`, `wft-delete-tenant.yaml` and
`wft-delete-tenant-safe.yaml` all run concurrently for different tenants.
Two concurrent runs are only safe from a git-merge-conflict-then-`set -e`-abort
if every write they make lands on a path that differs between tenants. That
was violated once already: both `create-tenant` runs used to `awk`-insert a
6-line RBAC block into the single shared
`platform-gitops/argocd/values.yaml` at the same anchor point, so the second
run's `git rebase origin/main` hit a real content conflict and the workflow
step died under `set -e`, leaving an orphaned Vault policy behind
(mctlhq/mctl-gitops#1431). The fix moved that write to a
per-tenant file; this script is the regression test that the pattern does
not come back, here or anywhere else in these three templates.

It parses each template's `script.source` block(s), finds every path written
via `cat > ... <<HEREDOC`, `sed -i ... FILE`, `git add`, `git rm` / `git rm
-rf`, or `mv SRC DEST` (the classic "build a new file, then rename it into
place" pattern the old `awk` block used), resolves simple one-level shell
variable references back to their literal form, and fails on any resolved
path that both sits under `platform-gitops/` and does not carry the tenant
name.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"
TEMPLATE_FILES = (
    "wft-create-tenant.yaml",
    "wft-delete-tenant.yaml",
    "wft-delete-tenant-safe.yaml",
)

# Real instances of the same "shared file, not parameterized by tenant name"
# shape — but delete-only, part of the CNPG shared-cluster lifecycle, and
# explicitly out of scope for issue 1431 per the proposal's requirements.md.
# Tracked separately; do not add to this list to work around a new finding.
WAIVED_PATHS = {
    "platform-gitops/infra-components/data/cnpg/shared/databases.yaml",
    "platform-gitops/infra-components/data/cnpg/shared/secrets.yaml",
    "platform-gitops/infra-components/data/cnpg/shared/cluster.yaml",
}

TENANT_MARKERS = ("${TENANT}", "$TENANT", "${PARAM_TENANT_NAME}", "$PARAM_TENANT_NAME")

ASSIGNMENT_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)="([^"\n]*)"\s*$', re.MULTILINE)
VARREF_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)')
CONTINUATION_RE = re.compile(r'\\\r?\n[ \t]*')

CAT_HEREDOC_RE = re.compile(r'cat\s*>\s*(~?[^\s<]+|"[^"]*")\s*<<')
SED_LINE_RE = re.compile(r'^.*\bsed\s+-i\b.*$', re.MULTILINE)
GIT_ADD_RE = re.compile(r'\bgit add\s+((?:"[^"]*"\s*)+)')
GIT_RM_RE = re.compile(r'\bgit rm\s+(?:-[a-zA-Z]+\s+)*("[^"]*")')
MV_RE = re.compile(r'\bmv\s+\S+\s+("[^"]*"|\S+)')
QUOTED_RE = re.compile(r'"([^"]*)"')


def walk_script_sources(doc):
    """Yield every `script.source` string found anywhere under this YAML doc."""
    if isinstance(doc, dict):
        script = doc.get("script")
        if isinstance(script, dict) and isinstance(script.get("source"), str):
            yield script["source"]
        for v in doc.values():
            yield from walk_script_sources(v)
    elif isinstance(doc, list):
        for item in doc:
            yield from walk_script_sources(item)


def extract_var_map(source: str) -> dict[str, str]:
    """Simple `VAR="literal"` assignments, last assignment per name wins."""
    var_map: dict[str, str] = {}
    for name, value in ASSIGNMENT_RE.findall(source):
        var_map[name] = value
    return var_map


def resolve_literal(text: str, var_map: dict[str, str], depth: int = 3) -> str:
    """Substitute known ${VAR}/$VAR references, leaving tenant markers alone.

    Bounded recursion (default enough for one level of nesting, e.g.
    DB_FILE="${CNPG_DIR}/databases.yaml" where CNPG_DIR was itself a literal
    assignment) — never used to expand the tenant markers themselves, which
    are excluded by name so they remain visible to the marker check below.
    """
    if depth <= 0:
        return text

    def repl(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name in ("TENANT", "PARAM_TENANT_NAME"):
            return m.group(0)
        if name in var_map:
            return resolve_literal(var_map[name], var_map, depth - 1)
        return m.group(0)

    return VARREF_RE.sub(repl, text)


def resolve_token(token: str, var_map: dict[str, str]) -> str:
    """Strip surrounding quotes from an extracted path token, then resolve it."""
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    return resolve_literal(token, var_map)


def find_write_paths(source: str, var_map: dict[str, str]) -> list[str]:
    """Every resolved path this script writes, removes, or renames into place."""
    resolved: list[str] = []

    for m in CAT_HEREDOC_RE.finditer(source):
        resolved.append(resolve_token(m.group(1), var_map))

    for line in SED_LINE_RE.findall(source):
        quoted = QUOTED_RE.findall(line)
        if quoted:
            resolved.append(resolve_literal(quoted[-1], var_map))

    for m in GIT_ADD_RE.finditer(source):
        for path in QUOTED_RE.findall(m.group(1)):
            resolved.append(resolve_literal(path, var_map))

    for m in GIT_RM_RE.finditer(source):
        resolved.append(resolve_token(m.group(1), var_map))

    for m in MV_RE.finditer(source):
        resolved.append(resolve_token(m.group(1), var_map))

    return resolved


def is_pass(path: str) -> bool:
    if "platform-gitops/" not in path:
        return True
    if path.endswith(".tmp"):
        return True
    if any(marker in path for marker in TENANT_MARKERS):
        return True
    if path in WAIVED_PATHS:
        return True
    return False


def check_source(source: str) -> list[str]:
    """Return every FAILing resolved path found in one script.source block."""
    var_map = extract_var_map(source)
    normalized = CONTINUATION_RE.sub(" ", source)
    paths = find_write_paths(normalized, var_map)
    return [p for p in paths if not is_pass(p)]


def check_file(path: Path) -> list[str]:
    """Return (path-string) failures found across every doc/template in a file."""
    failures = []
    for doc in yaml.safe_load_all(path.read_text()):
        if not doc:
            continue
        for source in walk_script_sources(doc):
            failures.extend(check_source(source))
    return failures


def selftest() -> int:
    """Prove the detector fires on the old pattern and is silent on the new one."""
    old_awk_source = '''
          # ── Append ArgoCD RBAC entries ──────────────────────────────────────
          ARGOCD_VALUES="platform-gitops/argocd/values.yaml"

          RBAC_BLOCK="
                  # Tenant: ${TENANT}
                  p, role:team-${TENANT}, applications, get, apps/${TENANT}-*, allow
                  g, ${TENANT}, role:team-${TENANT}"

          if grep -q "role:team-${TENANT}," "$ARGOCD_VALUES"; then
            echo "WARNING: already exists, skipping."
          else
            awk -v rbac="$RBAC_BLOCK" '
              /^    secret:/ { print rbac }
              { print }
            ' "$ARGOCD_VALUES" > /tmp/argocd_values_new.yaml
            mv /tmp/argocd_values_new.yaml "$ARGOCD_VALUES"
          fi

          git add \\
            "platform-gitops/tenants/${TENANT}/values.yaml" \\
            "platform-gitops/argocd/values.yaml"
'''
    old_failures = check_source(old_awk_source)
    if "platform-gitops/argocd/values.yaml" not in old_failures:
        print(
            f"FAIL selftest: detector did not fire on the old awk-into-values.yaml "
            f"pattern; got failures={old_failures}",
            file=sys.stderr,
        )
        return 1

    new_source = '''
          RBAC_FILE="platform-gitops/argocd/rbac/tenants/${TENANT}.csv"

          if [ -f "$RBAC_FILE" ]; then
            echo "WARNING: already exists, skipping."
          else
            cat > "$RBAC_FILE" <<EOF
          # Tenant: ${TENANT} — generated by wft-create-tenant. No exec (SOC F4).
          p, role:team-${TENANT}, applications, get, apps/${TENANT}-*, allow
          g, ${TENANT}, role:team-${TENANT}
          EOF
          fi

          git add \\
            "platform-gitops/tenants/${TENANT}/values.yaml" \\
            "platform-gitops/tenants/${TENANT}/catalog-info.yaml" \\
            "$RBAC_FILE" \\
            "platform-gitops/argo-workflows/sso-team-${TENANT}.yaml"
'''
    new_failures = check_source(new_source)
    if new_failures:
        print(
            f"FAIL selftest: detector raised a false positive on the new "
            f"per-tenant style: {new_failures}",
            file=sys.stderr,
        )
        return 1

    # One-level variable nesting, e.g. DB_FILE="${CNPG_DIR}/databases.yaml"
    # where CNPG_DIR was itself a literal assignment, resolves and is waived.
    cnpg_source = '''
          CNPG_DIR="platform-gitops/infra-components/data/cnpg/shared"
          DB_FILE="${CNPG_DIR}/databases.yaml"
          sed -i "/name: ${TENANT}-/,+8d" "$DB_FILE"
          git add "$DB_FILE"
'''
    cnpg_failures = check_source(cnpg_source)
    if cnpg_failures:
        print(
            f"FAIL selftest: waived CNPG path via one-level nesting incorrectly "
            f"flagged: {cnpg_failures}",
            file=sys.stderr,
        )
        return 1

    # A genuinely new, non-tenant, non-waived shared path must still fire.
    other_shared_source = '''
          SHARED="platform-gitops/some/other/shared.yaml"
          git add "$SHARED"
'''
    other_failures = check_source(other_shared_source)
    if "platform-gitops/some/other/shared.yaml" not in other_failures:
        print(
            f"FAIL selftest: detector did not fire on an unwaived shared path; "
            f"got failures={other_failures}",
            file=sys.stderr,
        )
        return 1

    print(
        "OK selftest: detector fires on the old awk-into-values.yaml pattern and "
        "on a fresh unwaived shared path, and stays silent on the new per-tenant "
        "style and on the waived CNPG paths"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not TEMPLATES_DIR.is_dir():
        print(f"::error::{TEMPLATES_DIR} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    any_failure = False
    for fname in TEMPLATE_FILES:
        path = TEMPLATES_DIR / fname
        if not path.is_file():
            print(f"::error::{path} not found", file=sys.stderr)
            any_failure = True
            continue
        for bad_path in check_file(path):
            print(
                f"::error file={fname}::writes to shared path not parameterized "
                f"by tenant name and not waived: {bad_path}",
                file=sys.stderr,
            )
            any_failure = True

    if any_failure:
        return 1

    print(
        f"OK: every write in {', '.join(TEMPLATE_FILES)} is tenant-scoped or waived"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
