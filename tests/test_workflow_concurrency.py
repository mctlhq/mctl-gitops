"""Workflow-level concurrency that relieves hosted-runner saturation (mctlhq/mctl-gitops#2993).

Pins: PR runs are superseded per PR number; merge_group and release builds
resolve to run-scoped, never-cancelled groups; the push group from #2935 stays;
the review workflows carry no workflow-level group; and the preview build_id
prefix matches what wft-preview-deploy.yaml actually sends.
"""
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"


def load(name):
    return yaml.safe_load((WF / name).read_text())


def conc(name):
    c = load(name).get("concurrency")
    assert c, f"{name} has no workflow-level concurrency"
    return " ".join(str(c["group"]).split()), str(c["cancel-in-progress"])


def test_validate_manifests():
    group, cancel = conc("validate-manifests.yml")
    assert "github.event_name == 'push' && format('validate-manifests-push-{0}', github.ref)" in group
    assert "github.event_name == 'pull_request' && format('validate-manifests-pr-{0}', github.event.pull_request.number)" in group
    # merge_group falls through to the per-run group
    assert group.endswith("|| format('validate-manifests-{0}', github.run_id) }}")
    assert cancel == "${{ github.event_name == 'push' || github.event_name == 'pull_request' }}"
    assert "merge_group" not in group and "merge_group" not in cancel


def test_pr_superseding_workflows():
    for name, prefix in [
        ("cloudflare-plan.yml", "cloudflare-plan"),
        ("yamllint.yml", "yamllint"),
        ("security.yml", "security"),
    ]:
        group, cancel = conc(name)
        assert f"format('{prefix}-pr-{{0}}', github.event.pull_request.number)" in group, name
        assert "merge_group" not in group and "merge_group" not in cancel, name
    assert conc("cloudflare-plan.yml")[0].endswith("|| format('cloudflare-plan-{0}', github.run_id) }}")
    assert conc("cloudflare-plan.yml")[1] == "${{ github.event_name == 'pull_request' }}"
    assert conc("security.yml")[1] == "${{ github.event_name == 'pull_request' }}"


def test_build_image_cancels_only_preview():
    group, cancel = conc("build-image.yaml")
    assert group.startswith("${{ startsWith(inputs.build_id, 'preview-deploy')")
    assert "format('build-image-preview-{0}-{1}-{2}', inputs.team_name, inputs.component_name, inputs.git_ref)" in group
    assert group.endswith("|| format('build-image-{0}', github.run_id) }}")
    assert cancel == "${{ startsWith(inputs.build_id, 'preview-deploy') }}"
    # release-deploy builds use rd-<run_id>, which must not match the preview prefix
    rd = (WF / "release-deploy.yaml").read_text()
    assert "rd-" in rd
    assert not "rd-".startswith("preview-deploy")


def test_review_workflows_have_no_group():
    for name in ("agy-review.yml", "claude-review.yml"):
        assert "concurrency" not in load(name), name


def test_preview_prefix_matches_argo_template():
    t = yaml.safe_load(
        (ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml").read_text()
    )
    assert t["metadata"]["name"] == "preview-deploy"
    assert 'build_id        = "{{workflow.name}}"' in (
        ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml"
    ).read_text()
