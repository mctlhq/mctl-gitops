"""Protected-path list of .github/workflows/auto-merge.yml (mctlhq/mctl-gitops#1033).

The pattern is read out of the workflow, not restated, so the test follows the
real list. MUTANTS at the end drop the release-gate entries and require the
matching rows to stop holding.
"""
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

import yaml

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
    "tests/test_release_deploy_bump.py",
    "tests/test_gitops_bump_inputs.py",
    "tests/test_wft_deploy_service_autoscaling_values.py",
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
    "tests/test_release_deploy_validate_inputs.py",
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


def gate_templates():
    """Every cluster template that mentions the release gate must be protected."""
    out = []
    for f in sorted((ROOT / CT).glob("*.yaml")):
        if "release-gate" in f.read_text():
            out.append(CT + f.name)
    return out


def guard_script():
    doc = yaml.safe_load(WF.read_text())
    for step in doc["jobs"]["auto-merge"]["steps"]:
        if step.get("id") == "guard":
            return step["run"]
    raise AssertionError("guard step not found")


def run_guard(files, regex=None):
    """Run the real guard step with a fake gh. Returns (exit code, outputs)."""
    script = guard_script()
    if regex is not None:
        script, n = re.subn(r"^(\s*)protected_re='[^']*'", lambda m: f"{m.group(1)}protected_re='{regex}'", script, flags=re.M)
        assert n == 1
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        listing = "".join(f"{f}\t\n" for f in files)
        (d / "listing").write_text(listing)
        gh = d / "bin" / "gh"
        gh.parent.mkdir()
        gh.write_text(
            "#!/bin/sh\n"
            'case "$*" in\n'
            f'  *--paginate*) cat "{d}/listing" ;;\n'
            f'  *) echo "deadbeef {len(files)}" ;;\n'
            "esac\n")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        out = d / "out"
        out.write_text("")
        env = {"PATH": f"{gh.parent}:{os.environ['PATH']}", "GITHUB_OUTPUT": str(out),
               "REPO": "o/r", "PR": "1", "HEAD_REF": "claude/x", "GH_TOKEN": "x"}
        r = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        return r.returncode, out.read_text()


def main():
    pat = pattern()
    bad = failures(pat)
    assert not bad, f"wrong classification: {bad}"
    # Any template that mentions the release gate is on the list.
    gt = gate_templates()
    assert gt, "no gate templates found"
    assert not [p for p in gt if not grep(pat, p)], f"unprotected gate templates: {gt}"
    # Runtime: no match is empty (merge), a match holds, a broken pattern fails hard.
    rc, out = run_guard(["README.md"])
    assert rc == 0 and "merge=true" in out, (rc, out)
    rc, out = run_guard(["scripts/release-gate.py"])
    assert rc == 0 and "merge=false" in out, (rc, out)
    rc, out = run_guard(["README.md"], regex="(")
    assert rc != 0 and "merge=true" not in out, f"invalid pattern read as clean: {rc} {out}"
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
