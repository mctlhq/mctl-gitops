"""build-image.yaml "Validate inputs": control-character and shape guard for
git_ref / image_name / image_tag, and the pull-request-ref classification that
withholds the GH_PACKAGES_TOKEN BuildKit secret and the App token
(mctlhq/mctl-gitops#1029 items 1 and 3, #764).

Runs the step's own script, extracted from the workflow, under bash.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
WF = REPO / ".github/workflows/build-image.yaml"
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


wf = yaml.safe_load(WF.read_text())
steps = next(iter(wf["jobs"].values()))["steps"]
by_id = {s.get("id"): s for s in steps if s.get("id")}
step = by_id["validate"]
check(steps[0] is step, "Validate inputs must be the first step")
SCRIPT = step["run"]
for key in ("INPUT_GIT_REF", "INPUT_IMAGE_NAME", "INPUT_IMAGE_TAG"):
    check(key in step["env"], f"{key} must be bound through env, not interpolated")

OK = dict(
    INPUT_REPO="mctlhq/mctl-web", INPUT_GIT_REF="main",
    INPUT_IMAGE_NAME="ghcr.io/mctlhq/mctl-web", INPUT_IMAGE_TAG="main-abc1234",
    INPUT_DOCKERFILE_PATH="Dockerfile", INPUT_TEAM_NAME="platform",
    INPUT_COMPONENT_NAME="mctl-web", INPUT_BUILD_ID="123",
)


def run(**over):
    env = {**OK, **over}
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "out"
        out.touch()
        p = subprocess.run(["bash", "-c", SCRIPT], env={**os.environ, **env, "GITHUB_OUTPUT": str(out)},
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr, out.read_text()


rc, log, out = run()
check(rc == 0 and "untrusted_ref=false" in out, f"plain branch: rc={rc} {log} {out}")

# Newline / control characters in the three inputs (and the rest) refuse.
for name in ("INPUT_GIT_REF", "INPUT_IMAGE_NAME", "INPUT_IMAGE_TAG", "INPUT_REPO", "INPUT_DOCKERFILE_PATH"):
    for bad in ("a\nb=c", "a\rb", "a\tb", "a\x7fb"):
        rc, log, out = run(**{name: bad})
        check(rc != 0 and "control character" in log and not out,
              f"{name}={bad!r} must be refused as a control character: rc={rc} {log}")

# Shape.
for name, bad in [("INPUT_IMAGE_TAG", "bad tag"), ("INPUT_IMAGE_TAG", "-x"), ("INPUT_IMAGE_NAME", "GHCR.io/Up"),
                  ("INPUT_IMAGE_NAME", "ghcr.io/a b"), ("INPUT_GIT_REF", "--upload-pack=x"),
                  ("INPUT_GIT_REF", "a b"), ("INPUT_GIT_REF", ""), ("INPUT_GIT_REF", "a" * 256)]:
    rc, log, out = run(**{name: bad})
    check(rc != 0 and not out, f"{name}={bad!r} must be refused: rc={rc} {log}")

# Legitimate refs still pass, untrusted only for PR refs.
for ref, want in [("feature/x-1", "false"), ("1.2.3", "false"), ("0123456789abcdef0123456789abcdef01234567", "false"),
                  ("refs/heads/main", "false"), ("pulls-fix", "false"), ("fix/pull-up", "false"),
                  ("refs/pull/12/head", "true"), ("refs/pull/12/merge", "true"), ("pull/12/head", "true"),
                  ("PULL/12/head", "true"), ("origin/pull/3/head", "true"), ("refs/remotes/origin/pull/3/head", "true"),
                  ("refs/pull-requests/3/from", "true"), ("x/pull/5/merge", "true")]:
    rc, log, out = run(INPUT_GIT_REF=ref)
    check(rc == 0 and f"untrusted_ref={want}" in out, f"git_ref {ref!r}: want {want}: rc={rc} {log} {out}")

# The credentials are gated on that output.
app = by_id["app_token"]
check("steps.validate.outputs.untrusted_ref != 'true'" in app["if"], f"app_token if: {app['if']}")
push = by_id["push"]
check("steps.validate.outputs.untrusted_ref != 'true'" in push["with"]["secrets"]
      and "GH_PACKAGES_TOKEN" in push["with"]["secrets"], f"github_token secret: {push['with']['secrets']}")
check("inputs.repo" in push["with"]["secrets"], "github_token must stay gated on the repo allow-list")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("build-image validate inputs: control chars, shapes, PR-ref classification, credential gates")
