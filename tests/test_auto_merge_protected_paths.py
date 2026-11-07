"""Protected-path list of .github/workflows/auto-merge.yml (mctlhq/mctl-gitops#1033).

The pattern is read out of the workflow, not restated, so the test follows the
real list. MUTANTS at the end drop the release-gate entries and require the
matching rows to stop holding.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows/auto-merge.yml"
CT = "platform-gitops/argo-workflows/cluster-templates/"

PROTECTED = [
    "platform-gitops/agent-platform/x.yaml",
    "platform-gitops/agents-state/mctl-agents/proposals/issue-1/.status.yaml",
    "scripts/release-gate.py",
    "platform-gitops/release-gates.yaml",
    "platform-gitops/argo-workflows/scripts/release-gate-guard.sh",
    CT + "tpl-git-commit.yaml",
    CT + "tpl-validate-tenant.yaml",
    CT + "wft-add-custom-domain.yaml",
    CT + "wft-deploy-service.yaml",
    CT + "wft-provision-database.yaml",
    CT + "wft-remove-custom-domain.yaml",
    CT + "wft-rollback-service.yaml",
    ".github/workflows/auto-merge.yml",
    ".github/workflows/gitops-bump.yaml",
    ".github/workflows/release-deploy.yaml",
    ".github/workflows/release-gate-watch.yml",
    ".github/workflows/validate-manifests.yml",
    "tests/test_release_gate.py",
    "tests/test_release_gate_guard.py",
    "tests/test_release_gate_watch.py",
    "tests/test_auto_merge_protected_paths.py",
]
NOT_PROTECTED = [
    "README.md",
    "platform-gitops/services/foo/values.yaml",
    "platform-gitops/agents-state/mctl-agents/proposals/issue-1/proposal.md",
    "scripts/release-gate.py.bak",
    "scripts/other.py",
    "platform-gitops/release-gates.yaml.orig",
    CT + "wft-scale-service.yaml",
    ".github/workflows/ci.yml",
    "tests/test_other.py",
]


def pattern():
    m = re.search(r"^\s*protected_re='([^']*)'\s*$", WF.read_text(), re.M)
    assert m, "protected_re assignment not found in auto-merge.yml"
    return m.group(1)


def grep(pat, path):
    r = subprocess.run(["grep", "-E", pat], input=path + "\n", text=True, capture_output=True)
    assert r.returncode in (0, 1), f"grep failed: {r.stderr}"
    return r.returncode == 0


def failures(pat):
    bad = [p for p in PROTECTED if not grep(pat, p)]
    bad += [p for p in NOT_PROTECTED if grep(pat, p)]
    return bad


def main():
    pat = pattern()
    bad = failures(pat)
    assert not bad, f"wrong classification: {bad}"
    # The workflow must actually use the variable.
    assert 'grep -E "$protected_re"' in WF.read_text()
    # MUTANTS: removing the release-gate entries must turn rows red.
    gate_alts = ["release-gate", "release-gates", "cluster-templates", "workflows", "tests/test_"]
    for needle in gate_alts:
        parts = pat.split("|")
        kept = [a for a in parts if needle not in a]
        assert len(kept) < len(parts), f"mutant {needle} removed nothing"
        assert failures("|".join(kept)), f"mutant dropping {needle} still passes"
    # Original (pre-change) list must fail the new rows.
    old = "|".join(pat.split("|")[:2])
    assert failures(old), "old list unexpectedly passes"
    print("ok")


if __name__ == "__main__":
    sys.exit(main())
