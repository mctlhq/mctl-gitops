"""preview-delete removes the TLS Secret cert-manager leaves behind.

preview-deploy points the Ingress at ingress.tls[0].secretName=${RELEASE}-tls.
cert-manager creates that Secret for the Ingress's Certificate and keeps it
when the Certificate goes, so `helm uninstall` alone left one orphan per
preview in {team}-preview (two found in labs-preview on 2026-10-19).

Runs the template's own script with stub helm/kubectl on PATH:

- release present: uninstall, then delete ${RELEASE}-tls in {team}-preview;
- release already gone: the Secret is still deleted (cleans earlier orphans);
- a kubectl error fails the step instead of being swallowed;
- the name it deletes is the name preview-deploy configures.

Run: python3 tests/test_preview_delete_tls_secret.py
"""
import os
import pathlib
import re
import stat
import subprocess
import tempfile
import unittest

import yaml

TEMPLATES = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
DELETE = TEMPLATES / "wft-preview-delete.yaml"
DEPLOY = TEMPLATES / "wft-preview-deploy.yaml"
RELEASE_RE = re.compile(r'^\s*RELEASE="([^"]+)"\s*$', re.M)

HELM_STUB = """#!/bin/sh
echo "helm $*" >> "$CALLS"
if [ "$1" = status ]; then
  [ "$4" = "$HELM_PRESENT_NS" ] && exit 0
  exit 1
fi
exit 0
"""

KUBECTL_STUB = """#!/bin/sh
echo "kubectl $*" >> "$CALLS"
exit "${KUBECTL_RC:-0}"
"""


def template_script(path, name):
    doc = yaml.safe_load(path.read_text())
    for t in doc["spec"]["templates"]:
        if t["name"] == name:
            return t["script"]
    raise AssertionError(f"{path}: no template {name}")


class PreviewDeleteTLSSecret(unittest.TestCase):
    def setUp(self):
        self.script = template_script(DELETE, "delete")
        self.tmp = tempfile.TemporaryDirectory()
        bindir = pathlib.Path(self.tmp.name, "bin")
        bindir.mkdir()
        for name, body in (("helm", HELM_STUB), ("kubectl", KUBECTL_STUB)):
            f = bindir / name
            f.write_text(body)
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.calls = pathlib.Path(self.tmp.name, "calls")
        self.calls.touch()
        self.env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "CALLS": str(self.calls),
            "PARAM_TEAM_NAME": "labs",
            "PARAM_COMPONENT_NAME": "probe",
            "PARAM_PREVIEW_ID": "abc123",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, **extra):
        proc = subprocess.run(["sh", "-c", self.script["source"]],
                              env={**self.env, **extra},
                              capture_output=True, text=True)
        return proc, self.calls.read_text().splitlines()

    WANT = "kubectl delete secret preview-probe-abc123-tls -n labs-preview --ignore-not-found"

    def test_release_present(self):
        proc, calls = self.run_script(HELM_PRESENT_NS="labs-preview")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("helm uninstall preview-probe-abc123 -n labs-preview --wait", calls)
        self.assertIn(self.WANT, calls)
        self.assertLess(calls.index("helm uninstall preview-probe-abc123 -n labs-preview --wait"),
                        calls.index(self.WANT))

    def test_release_already_gone(self):
        proc, calls = self.run_script(HELM_PRESENT_NS="none")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse([c for c in calls if c.startswith("helm uninstall")])
        self.assertIn(self.WANT, calls)

    def test_kubectl_error_fails_the_step(self):
        proc, _ = self.run_script(HELM_PRESENT_NS="none", KUBECTL_RC="1")
        self.assertNotEqual(proc.returncode, 0)

    def test_image_has_kubectl(self):
        self.assertTrue(self.script["image"].startswith("ghcr.io/mctlhq/mctl-workflow-tools:"),
                        self.script["image"])

    def test_name_matches_preview_deploy(self):
        deploy = DEPLOY.read_text()
        self.assertIn('ingress.tls[0].secretName=${RELEASE}-tls', deploy)
        self.assertEqual(RELEASE_RE.findall(deploy), RELEASE_RE.findall(self.script["source"]))
        self.assertTrue(RELEASE_RE.findall(deploy))


if __name__ == "__main__":
    unittest.main()
