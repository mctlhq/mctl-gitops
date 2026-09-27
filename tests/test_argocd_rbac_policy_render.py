"""issue-1431: per-tenant ArgoCD RBAC fragments render the same effective
policy as the pre-migration single-file `policy.csv`, minus the intentionally
dropped orphan tenants.

`helm` is not assumed to be on PATH in CI or in this run's sandbox, and
`platform-gitops/argocd/values.yaml`'s `policy.csv` is literal, untemplated
YAML -- no Helm functions run inside that string -- so parsing it directly
with pyyaml and concatenating it with the per-tenant fragments exactly the
way `platform-gitops/argocd/templates/argocd-rbac-cm.yaml` does (base,
trimmed, then each `rbac/tenants/*.csv` fragment, sorted by filename,
trimmed) is an accurate simulation of the real Helm render for this one key.
No pytest, matching the plain `python3 tests/<file>.py` convention of
`tests/test_otel_collector_backends_render.py`.

T1. The normalized (comments and blank lines stripped, sorted) union of the
    base `policy.csv` and every `rbac/tenants/*.csv` fragment equals
    `tests/fixtures/argocd-rbac-policy.baseline.csv`'s content minus exactly
    the 6 `yyy` and 6 `xxxx` lines -- the only intentional difference, since
    the migration dropped those two orphan tenants (no matching
    `platform-gitops/tenants/{yyy,xxxx}/` directory exists for either).
T2. `argo-cd.configs.rbac.create` is `false` -- the argo-cd subchart must not
    also try to own `argocd-rbac-cm`.
T3. `policy.default` is `""` and `scopes` is `"[groups]"`, unchanged by the
    migration.

If `helm` happens to be on PATH, an additional belt-and-suspenders render is
attempted and cross-checked against the same normalized fixture; its absence
is not a failure.

Run: python3 tests/test_argocd_rbac_policy_render.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "argocd"
VALUES_FILE = CHART / "values.yaml"
FRAGMENTS_DIR = CHART / "rbac" / "tenants"
BASELINE_FILE = ROOT / "tests" / "fixtures" / "argocd-rbac-policy.baseline.csv"

DROPPED_ORPHAN_TENANTS = ("yyy", "xxxx")

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


values = yaml.safe_load(VALUES_FILE.read_text())
rbac = values["argo-cd"]["configs"]["rbac"]

base_policy = rbac["policy.csv"]

# Simulate templates/argocd-rbac-cm.yaml: base policy trimmed, then every
# rbac/tenants/*.csv fragment (sorted by filename) trimmed, concatenated.
rendered_parts = [base_policy.strip()]
fragment_paths = sorted(FRAGMENTS_DIR.glob("*.csv"))
check(len(fragment_paths) > 0, f"no fragments found under {FRAGMENTS_DIR}")
for p in fragment_paths:
    rendered_parts.append(p.read_text().strip())
rendered_policy = "\n".join(rendered_parts)

rendered_lines = normalize(rendered_policy)

baseline_lines = normalize(BASELINE_FILE.read_text())
expected_lines = sorted(
    line
    for line in baseline_lines
    if not any(f"team-{t}" in line or f", {t}," in line or f" {t}," in line for t in DROPPED_ORPHAN_TENANTS)
)
# The filter above is deliberately loose (substring match on the tenant
# name); assert it removed exactly the 12 expected lines, not more or fewer,
# so a coincidental substring match elsewhere would be caught here.
check(
    len(baseline_lines) - len(expected_lines) == 12,
    f"expected filtering yyy/xxxx to drop exactly 12 lines from the baseline, "
    f"dropped {len(baseline_lines) - len(expected_lines)}",
)

check(
    rendered_lines == expected_lines,
    "rendered policy.csv (base + fragments) does not equal the baseline minus "
    f"the yyy/xxxx lines.\nOnly in rendered: {sorted(set(rendered_lines) - set(expected_lines))}\n"
    f"Only in expected: {sorted(set(expected_lines) - set(rendered_lines))}",
)

check(
    rbac.get("create") is False,
    f"argo-cd.configs.rbac.create must be false so the subchart does not also "
    f"try to own argocd-rbac-cm, got {rbac.get('create')!r}",
)
check(
    rbac.get("policy.default") == "",
    f"argo-cd.configs.rbac['policy.default'] must survive the move unchanged, "
    f"got {rbac.get('policy.default')!r}",
)
check(
    rbac.get("scopes") == "[groups]",
    f"argo-cd.configs.rbac.scopes must survive the move unchanged, "
    f"got {rbac.get('scopes')!r}",
)

# Belt-and-suspenders: if helm is actually available, cross-check with a real
# render. Its absence is not a failure -- the pure-Python check above is the
# one that must exist and pass regardless.
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
                    "does not match the pure-Python simulation",
                )
    except subprocess.CalledProcessError as exc:
        failures.append(f"helm template failed unexpectedly: {exc.stderr}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(
    "argocd tenant rbac render: fragments + base policy equal the baseline "
    "minus yyy/xxxx, create=false, policy.default/scopes unchanged"
)
