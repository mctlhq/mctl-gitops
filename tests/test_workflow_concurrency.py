"""Workflow-level concurrency that relieves hosted-runner saturation (mctlhq/mctl-gitops#2993).

Pins: PR runs are superseded per PR number; merge_group and release builds
resolve to run-scoped, never-cancelled groups; the push group from #2935 stays;
the review workflows carry no workflow-level group; the preview build_id
prefix matches what wft-preview-deploy.yaml actually sends; and release-deploy
supersedes only `-preview` components built from a `main-<sha>` tag.

Plain script, run by validate-manifests.yml:
`python3 tests/test_workflow_concurrency.py`.
"""
import pathlib
import subprocess
import sys

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
    assert conc("security.yml")[0].endswith("|| format('security-{0}', github.run_id) }}")
    # yamllint also supersedes per pushed ref; anything else is per-run
    group, cancel = conc("yamllint.yml")
    assert "github.event_name == 'push' && format('yamllint-push-{0}', github.ref)" in group
    assert group.endswith("|| format('yamllint-{0}', github.run_id) }}")
    assert cancel == "${{ github.event_name == 'pull_request' || github.event_name == 'push' }}"


def test_build_image_cancels_only_preview():
    group, cancel = conc("build-image.yaml")
    assert group.startswith("${{ startsWith(inputs.build_id, 'preview-deploy')")
    assert "format('build-image-preview-{0}-{1}-{2}', inputs.team_name, inputs.component_name, inputs.git_ref)" in group
    assert group.endswith("|| format('build-image-{0}', github.run_id) }}")
    assert cancel == "${{ startsWith(inputs.build_id, 'preview-deploy') }}"
    # release-deploy builds pass rd-<run_id>, which the preview prefix cannot match
    rd = load("release-deploy.yaml")["jobs"]["build"]["with"]["build_id"]
    assert rd == "rd-${{ github.run_id }}", rd


PREVIEW = "endsWith(inputs.component_name, '-preview') && startsWith(inputs.image_tag, 'main-')"


def test_release_deploy_cancels_only_main_sha_previews():
    group, cancel = conc("release-deploy.yaml")
    # both conditions, in the group and in the cancel flag: a semver tag never
    # starts with `main-`, so a release always falls through to the per-run group
    assert group == (
        "${{ " + PREVIEW
        + " && format('release-deploy-preview-{0}-{1}', inputs.team_name, inputs.component_name)"
        + " || format('release-deploy-{0}', github.run_id) }}"
    ), group
    assert cancel == "${{ " + PREVIEW + " }}", cancel


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


def test_preview_images_take_the_direct_route():
    """release-deploy may cancel a preview run mid-flight only because its bump
    is one direct push. On the PR route a cancelled run would leave an open
    release-bump pull request that nothing supersedes (a `main-<sha>` suffix is
    not a semver tag). Every `-preview` service must therefore resolve to
    `direct` through the real route script. If this fails, take the image off
    the PR route or make the preview group in release-deploy.yaml non-cancelling.
    """
    dirs = sorted(d for d in (ROOT / "platform-gitops/services").glob("*/*-preview") if d.is_dir())
    assert dirs, "no -preview service found: the check would pass on nothing"
    for d in dirs:
        image = (yaml.safe_load((d / "values.yaml").read_text()).get("image") or {}).get("repository")
        assert isinstance(image, str) and image, f"{d.name}: image.repository could not be read"
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts/release-bump-route.py"), "--image", image, "--root", str(ROOT)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"{d.name}: route for {image} could not be decided: {r.stderr.strip()}"
        assert r.stdout.strip() == "direct", f"{d.name}: {image} is on the {r.stdout.strip()!r} route"


def test_ci_runs_this_test():
    assert "python3 tests/test_workflow_concurrency.py" in (WF / "validate-manifests.yml").read_text()


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
