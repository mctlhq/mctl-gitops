"""preview-deploy renders the preview id and gitops commit an approved plan binds.

mctl-api's deploy_plan digest (.github#254, mctl-api#1026) binds a preview id,
the host built from it and the service values at the gitops commit the plan
was computed against. The workflow used to derive its id from its own name and
read the default branch, so an approved apply could not land on what was
approved. These tests run the deploy template's own script with stub tools on
PATH, stopping at the first tool after the checkout (python3):

- a valid preview_id is used verbatim for /tmp/preview_id and the URL;
- an invalid preview_id or gitops_ref fails before anything is cloned;
- an empty preview_id keeps the old name-derived id;
- a gitops_ref is fetched and checked out, and a checkout that does not land
  on it fails the step instead of deploying the default branch.

PREVIEW_TEST_SHELL picks the shell the script runs under (default bash; CI
repeats the run under busybox sh, the shell of the tools image).

Run: python3 tests/test_preview_deploy_server_set_id.py
"""
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

import yaml

DEPLOY = pathlib.Path("platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml")
SHELL = os.environ.get("PREVIEW_TEST_SHELL", "bash")
REF = "0123456789abcdef0123456789abcdef01234567"

GIT_STUB = """#!/bin/sh
echo "git $*" >> "$CALLS"
case "$*" in
  clone*) mkdir -p "$TMPROOT/mctl-gitops" ;;
  *"rev-parse HEAD") echo "${STUB_HEAD:-}" ;;
esac
exit 0
"""

# python3 is the first tool after the checkout: reaching it means every check
# before it passed. It exits with a marker code so the test can tell.
PY_STUB = """#!/bin/sh
echo "python3 $*" >> "$CALLS"
exit 42
"""


def template_script(path, name):
    doc = yaml.safe_load(path.read_text())
    for t in doc["spec"]["templates"]:
        if t["name"] == name:
            return t["script"]
    raise AssertionError(f"{path}: no template {name}")


class PreviewDeployServerSetID(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        # The script writes absolute /tmp paths; point them at the sandbox.
        self.source = template_script(DEPLOY, "deploy")["source"].replace("/tmp/", f"{root}/")
        bindir = root / "bin"
        bindir.mkdir()
        for name, body in (("git", GIT_STUB), ("python3", PY_STUB)):
            f = bindir / name
            f.write_text(body)
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.root = root
        self.calls = root / "calls"
        self.calls.touch()
        self.env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "CALLS": str(self.calls),
            "TMPROOT": str(root),
            "PARAM_TEAM_NAME": "labs",
            "PARAM_COMPONENT_NAME": "probe",
            "PARAM_IMAGE_TAG": "1.0.0",
            "PARAM_TTL_HOURS": "24",
            "PARAM_PORT": "",
            "PARAM_PREVIEW_ID": "",
            "PARAM_GITOPS_REF": "",
            "ARGO_WORKFLOW_NAME": "preview-deploy-x7k2q",
            "PLATFORM_DOMAIN": "mctl.ai",
            "GITOPS_ORG": "mctlhq",
            "GITOPS_REPO": "mctl-gitops",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, **extra):
        proc = subprocess.run([SHELL, "-c", self.source], env={**self.env, **extra},
                              capture_output=True, text=True)
        return proc, self.calls.read_text().splitlines()

    def outputs(self):
        return ((self.root / "preview_id").read_text().strip(),
                (self.root / "preview_url").read_text().strip())

    def test_server_set_id_is_used(self):
        proc, _ = self.run_script(PARAM_PREVIEW_ID="ab12cd")
        self.assertEqual(proc.returncode, 42, proc.stderr)
        self.assertEqual(self.outputs(), ("ab12cd", "https://probe-ab12cd.mctl.ai"))

    def test_empty_id_keeps_name_derived_id(self):
        proc, _ = self.run_script()
        self.assertEqual(proc.returncode, 42, proc.stderr)
        self.assertEqual(self.outputs(), ("ployx7k2q"[-6:], "https://probe-yx7k2q.mctl.ai"))

    def test_invalid_id_fails_before_clone(self):
        for bad in ("AB12CD", "ab12c", "ab12cde", "ab-2cd", "ab12c;", "ab12c\n"):
            with self.subTest(bad=bad):
                self.calls.write_text("")
                proc, calls = self.run_script(PARAM_PREVIEW_ID=bad)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn("preview_id must be", proc.stderr)
                self.assertEqual(calls, [])

    def test_invalid_ref_fails_before_clone(self):
        for bad in (REF[:-1], REF + "0", REF.upper(), "main", REF[:-1] + "g"):
            with self.subTest(bad=bad):
                self.calls.write_text("")
                proc, calls = self.run_script(PARAM_GITOPS_REF=bad)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn("gitops_ref must be", proc.stderr)
                self.assertEqual(calls, [])

    def test_ref_is_fetched_and_checked_out(self):
        proc, calls = self.run_script(PARAM_GITOPS_REF=REF, STUB_HEAD=REF)
        self.assertEqual(proc.returncode, 42, proc.stderr)
        repo = f"{self.root}/mctl-gitops"
        self.assertIn(f"git -C {repo} fetch --depth=1 origin {REF}", calls)
        self.assertIn(f"git -C {repo} checkout --quiet --detach FETCH_HEAD", calls)
        self.assertLess(calls.index(f"git -C {repo} checkout --quiet --detach FETCH_HEAD"),
                        next(i for i, c in enumerate(calls) if c.startswith("python3")))

    def test_checkout_on_other_commit_fails(self):
        proc, calls = self.run_script(PARAM_GITOPS_REF=REF, STUB_HEAD="f" * 40)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn(f"expected {REF}", proc.stderr)
        self.assertFalse([c for c in calls if c.startswith("python3")])

    def test_no_ref_reads_default_branch(self):
        proc, calls = self.run_script()
        self.assertEqual(proc.returncode, 42, proc.stderr)
        self.assertFalse([c for c in calls if " fetch " in c or " checkout " in c])

    def test_parameters_reach_the_script(self):
        doc = yaml.safe_load(DEPLOY.read_text())
        args = {p["name"]: p for p in doc["spec"]["arguments"]["parameters"]}
        for name in ("preview_id", "gitops_ref"):
            self.assertEqual(args[name].get("value"), "", name)
        tmpl = template_script(DEPLOY, "deploy")
        env = {e["name"]: e["value"] for e in tmpl["env"]}
        self.assertEqual(env["PARAM_PREVIEW_ID"], "{{inputs.parameters.preview_id}}")
        self.assertEqual(env["PARAM_GITOPS_REF"], "{{inputs.parameters.gitops_ref}}")
        task = next(t for t in next(t for t in doc["spec"]["templates"] if t["name"] == "preview-pipeline")["dag"]["tasks"]
                    if t["name"] == "deploy-preview")
        passed = {p["name"]: p["value"] for p in task["arguments"]["parameters"]}
        self.assertEqual(passed["preview_id"], "{{workflow.parameters.preview_id}}")
        self.assertEqual(passed["gitops_ref"], "{{workflow.parameters.gitops_ref}}")
        # No placeholder may be interpolated into the script text (gitops#992).
        self.assertNotIn("{{", tmpl["source"])


if __name__ == "__main__":
    unittest.main()
