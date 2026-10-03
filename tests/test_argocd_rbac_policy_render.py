"""ArgoCD RBAC render: base policy plus per-tenant fragments (issue-1431).

`platform-gitops/argocd/templates/argocd-rbac-cm.yaml` renders policy.csv as
the base `policy.csv` from `platform-gitops/argocd/values.yaml` (trimmed)
followed by every `rbac/tenants/*.csv` fragment (sorted by filename, trimmed).
`wft-create-tenant` writes one fragment per tenant straight to main and
`wft-delete-tenant` removes it, so the tenant set changes without a PR.

The first version of this test compared the render with the frozen
pre-migration snapshot `tests/fixtures/argocd-rbac-policy.baseline.csv`. That
proved the migration once, then failed validate on every open PR the moment a
tenant was created (2b557d10, fixed by hand in #1512). The checks below hold
for any tenant set instead:

T1. The base policy (every line that is not a `role:team-*` line) equals the
    snapshot's non-tenant lines: platform roles do not drift silently.
T2. Every tenant directory under `platform-gitops/tenants/` has exactly one
    fragment and every fragment has a tenant directory, except tenants bound
    to `role:admin` in the base policy, which have none. An orphan fragment
    (the old yyy/xxxx case) grants a role nobody provisioned.
T3. Every fragment equals what `wft-create-tenant` writes for that tenant:
    the heredoc is read from the workflow itself, so a hand-edited fragment
    (an extra `exec` line, another tenant's apps) or a changed template
    without regenerated fragments fails here.
T4. If `helm` is on PATH (it is in the validate job), a real render of
    argocd-rbac-cm must equal the base policy plus the fragments.
T5. `argo-cd.configs.rbac.create` is false, `policy.default` is "" and
    `scopes` is "[groups]".

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_argocd_rbac_policy_render.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "argocd"
VALUES_FILE = CHART / "values.yaml"
FRAGMENTS_DIR = CHART / "rbac" / "tenants"
TENANTS_DIR = ROOT / "platform-gitops" / "tenants"
CREATE_TENANT = ROOT / "platform-gitops" / "argo-workflows" / "cluster-templates" / "wft-create-tenant.yaml"
BASELINE_FILE = ROOT / "tests" / "fixtures" / "argocd-rbac-policy.baseline.csv"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def normalize(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return sorted(out)


def is_tenant_line(line: str) -> bool:
    return "role:team-" in line


values = yaml.safe_load(VALUES_FILE.read_text())
rbac = values["argo-cd"]["configs"]["rbac"]
base_policy = rbac["policy.csv"]
base_lines = normalize(base_policy)

# T1: the base policy is the snapshot's platform part.
check(not any(is_tenant_line(l) for l in base_lines),
      "base policy.csv must not carry tenant (role:team-*) lines; they belong in rbac/tenants/<tenant>.csv")
snapshot_base = [l for l in normalize(BASELINE_FILE.read_text()) if not is_tenant_line(l)]
check(len(snapshot_base) > 0, f"no non-tenant lines in {BASELINE_FILE}: the read is broken, not the policy")
check(
    base_lines == snapshot_base,
    "base policy.csv differs from the platform lines of the snapshot.\n"
    f"Only in values.yaml: {sorted(set(base_lines) - set(snapshot_base))}\n"
    f"Only in snapshot: {sorted(set(snapshot_base) - set(base_lines))}\n"
    "If the change is intended, update the non-tenant lines of the snapshot in the same PR.",
)

# T2: tenants and fragments correspond one to one.
fragment_paths = sorted(FRAGMENTS_DIR.glob("*.csv"))
check(len(fragment_paths) > 0, f"no fragments found under {FRAGMENTS_DIR}")
tenant_dirs = sorted(p.name for p in TENANTS_DIR.iterdir() if p.is_dir())
check(len(tenant_dirs) > 0, f"no tenant directories under {TENANTS_DIR}")
admin_tenants = {m.group(1) for l in base_lines for m in [re.fullmatch(r"g,\s*([^,\s]+),\s*role:admin", l)] if m}
expected_fragments = set(tenant_dirs) - admin_tenants
actual_fragments = {p.stem for p in fragment_paths}
check(
    actual_fragments == expected_fragments,
    "rbac/tenants fragments do not match platform-gitops/tenants/.\n"
    f"Tenant without fragment: {sorted(expected_fragments - actual_fragments)}\n"
    f"Fragment without tenant (orphan role): {sorted(actual_fragments - expected_fragments)}",
)

# T3: each fragment is exactly the wft-create-tenant template for its tenant.
m = re.search(r'cat > "\$RBAC_FILE" <<EOF\n(.*?)\n[ \t]*EOF\n', CREATE_TENANT.read_text(), re.S)
check(m is not None, f"could not find the RBAC fragment heredoc in {CREATE_TENANT}")
if m:
    template = textwrap.dedent(m.group(1))
    check("${TENANT}" in template, "the RBAC heredoc in wft-create-tenant no longer uses ${TENANT}")
    for p in fragment_paths:
        want = normalize(template.replace("${TENANT}", p.stem))
        got = normalize(p.read_text())
        check(
            got == want,
            f"{p.relative_to(ROOT)} is not what wft-create-tenant writes for tenant {p.stem!r}.\n"
            f"Extra: {sorted(set(got) - set(want))}\nMissing: {sorted(set(want) - set(got))}",
        )

# T4: the render is base + fragments, in the template's order.
rendered_parts = [base_policy.strip()] + [p.read_text().strip() for p in fragment_paths]
expected_lines = normalize("\n".join(rendered_parts))

# T5: settings unchanged by the migration.
check(
    rbac.get("create") is False,
    f"argo-cd.configs.rbac.create must be false so the subchart does not also "
    f"try to own argocd-rbac-cm, got {rbac.get('create')!r}",
)
check(
    rbac.get("policy.default") == "",
    f"argo-cd.configs.rbac['policy.default'] must be unchanged, got {rbac.get('policy.default')!r}",
)
check(
    rbac.get("scopes") == "[groups]",
    f"argo-cd.configs.rbac.scopes must be unchanged, got {rbac.get('scopes')!r}",
)

# If helm is available, the real render must match the simulation. Its
# absence is not a failure; the checks above do not depend on it.
if shutil.which("helm"):
    try:
        with tempfile.TemporaryDirectory() as d:
            out = subprocess.run(
                ["helm", "template", "test", str(CHART), "-f", str(VALUES_FILE)],
                capture_output=True, text=True, check=True, cwd=d,
            )
            docs = list(yaml.safe_load_all(out.stdout))
            cm_docs = [doc for doc in docs if doc and doc.get("kind") == "ConfigMap"
                       and doc.get("metadata", {}).get("name") == "argocd-rbac-cm"]
            check(len(cm_docs) == 1, f"expected exactly one argocd-rbac-cm ConfigMap, got {len(cm_docs)}")
            if cm_docs:
                helm_lines = normalize(cm_docs[0]["data"]["policy.csv"])
                check(
                    helm_lines == expected_lines,
                    "real helm template render of argocd-rbac-cm's policy.csv "
                    "does not match the base + fragments simulation",
                )
    except subprocess.CalledProcessError as exc:
        failures.append(f"helm template failed unexpectedly: {exc.stderr}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(
    f"argocd tenant rbac render: base policy unchanged, {len(fragment_paths)} fragments match "
    f"{len(expected_fragments)} tenants and the wft-create-tenant template, render = base + fragments"
)
