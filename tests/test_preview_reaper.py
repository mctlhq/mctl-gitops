"""Preview ttl_hours is enforced: preview-deploy stamps, preview-reaper reaps.

Until this test existed nothing deleted a preview when its ttl_hours ran out
(a preview-mctl-web release from 2026-05-10 was still on record in October),
although the docs and the mctl_create_preview description promise it.

- preview-deploy checks ttl_hours and stamps the release with
  --labels mctl.ai/expires-at=<now + ttl_hours * 3600>;
- preview-reaper (run with stub kubectl/helm/date on PATH):
  - reaps an expired release (helm uninstall, then its ${RELEASE}-tls),
    keeps an unexpired one, and reads the newest revision of each release;
  - leaves a release with no, a malformed or an over-long label alone and
    fails the run (unknown lifetime is not "expired");
  - fails without deleting anything when the Secret listing fails;
  - keeps going after one failed uninstall, then fails the run;
  - takes its namespace from the workflow, not from a parameter;
- the tenant chart renders the CronWorkflow into every tenant namespace with
  preview enabled, and AppProject platform admits CronWorkflow.

Run: python3 tests/test_preview_reaper.py
PREVIEW_TEST_SHELL picks the shell the scripts run under (default bash);
CI also runs the Reaper and Deploy cases under busybox sh in an alpine
container, the shell the tools image actually uses.
"""
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

import yaml

TEMPLATES = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
REAPER = TEMPLATES / "wft-preview-reaper.yaml"
DEPLOY = TEMPLATES / "wft-preview-deploy.yaml"
CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
PROJECT = pathlib.Path("platform-gitops/bootstrap/templates/projects/project-platform.yaml")
NOW = 1_800_000_000
# The scripts run under the tools image's sh (busybox ash, which takes
# `set -o pipefail`); /bin/sh on the CI runner is dash, which does not, so
# bash stands in for it unless PREVIEW_TEST_SHELL says otherwise.
SHELL = os.environ.get("PREVIEW_TEST_SHELL", "bash")

KUBECTL_STUB = """#!/bin/sh
echo "kubectl $*" >> "$CALLS"
if [ "$1" = get ]; then
  [ -n "$LIST_RC" ] && exit "$LIST_RC"
  cat "$LISTING"
fi
exit 0
"""

HELM_STUB = """#!/bin/sh
echo "helm $*" >> "$CALLS"
[ "$1" = uninstall ] && [ "$2" = "$FAIL_RELEASE" ] && exit 1
exit 0
"""

DATE_STUB = f"""#!/bin/sh
echo {NOW}
"""


def helm_release_record(name, version, expires=None):
    labels = {"name": name, "owner": "helm", "status": "deployed",
              "version": str(version)}
    if expires is not None:
        labels["mctl.ai/expires-at"] = str(expires)
    return {"metadata": {"name": f"sh.helm.release.v1.{name}.v{version}",
                         "labels": labels}}


class Reaper(unittest.TestCase):
    def setUp(self):
        doc = yaml.safe_load(REAPER.read_text())
        self.doc = doc
        self.script = doc["spec"]["templates"][0]["script"]
        self.tmp = tempfile.TemporaryDirectory()
        bindir = pathlib.Path(self.tmp.name, "bin")
        bindir.mkdir()
        for name, body in (("kubectl", KUBECTL_STUB), ("helm", HELM_STUB),
                           ("date", DATE_STUB)):
            f = bindir / name
            f.write_text(body)
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.calls = pathlib.Path(self.tmp.name, "calls")
        self.listing = pathlib.Path(self.tmp.name, "listing.json")
        self.env = {"PATH": f"{bindir}:{os.environ['PATH']}",
                    "CALLS": str(self.calls), "LISTING": str(self.listing),
                    "WORKFLOW_NAMESPACE": "labs"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_reaper(self, items, **extra):
        self.listing.write_text(json.dumps({"items": items}))
        self.calls.write_text("")
        proc = subprocess.run([SHELL, "-c", self.script["source"]],
                              env={**self.env, **extra},
                              capture_output=True, text=True)
        return proc, self.calls.read_text().splitlines()

    @staticmethod
    def uninstalled(calls):
        return [c.split()[2] for c in calls if c.startswith("helm uninstall")]

    def test_reaps_expired_keeps_unexpired(self):
        proc, calls = self.run_reaper([
            helm_release_record("preview-a-111111", 1, NOW - 60),
            helm_release_record("preview-b-222222", 1, NOW + 3600),
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.uninstalled(calls), ["preview-a-111111"])
        self.assertIn("helm uninstall preview-a-111111 -n labs-preview --wait --timeout 2m", calls)
        self.assertIn("kubectl delete secret preview-a-111111-tls -n labs-preview"
                      " --ignore-not-found", calls)
        self.assertNotIn("kubectl delete secret preview-b-222222-tls -n labs-preview"
                         " --ignore-not-found", calls)

    def test_newest_revision_decides(self):
        proc, calls = self.run_reaper([
            helm_release_record("preview-a-111111", 1, NOW - 60),
            helm_release_record("preview-a-111111", 10, NOW + 3600),
            helm_release_record("preview-a-111111", 2, NOW - 60),
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.uninstalled(calls), [])

    def test_unlabeled_or_malformed_is_left_and_fails(self):
        # 12 digits is past any real expiry; 20 is past the shell's integer
        # range, where `[ -gt ]` errors out and must not read as "expired".
        for expires in (None, "soon", "1" * 12, "9" * 20):
            proc, calls = self.run_reaper([
                helm_release_record("preview-a-111111", 1, expires),
                helm_release_record("preview-b-222222", 1, NOW - 60),
            ])
            self.assertNotEqual(proc.returncode, 0, expires)
            self.assertEqual(self.uninstalled(calls), ["preview-b-222222"], expires)

    def test_listing_failure_deletes_nothing(self):
        proc, calls = self.run_reaper([helm_release_record("preview-a-111111", 1, NOW - 60)],
                                      LIST_RC="1")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.uninstalled(calls), [])

    def test_one_failure_does_not_stop_the_rest(self):
        proc, calls = self.run_reaper([
            helm_release_record("preview-a-111111", 1, NOW - 60),
            helm_release_record("preview-b-222222", 1, NOW - 60),
        ], FAIL_RELEASE="preview-a-111111")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.uninstalled(calls), ["preview-a-111111", "preview-b-222222"])
        self.assertNotIn("kubectl delete secret preview-a-111111-tls -n labs-preview"
                         " --ignore-not-found", calls)

    def test_empty_namespace_is_clean(self):
        proc, calls = self.run_reaper([])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.uninstalled(calls), [])

    def test_namespace_comes_from_the_workflow(self):
        env = {e["name"]: e["value"] for e in self.script["env"]}
        self.assertEqual(env, {"WORKFLOW_NAMESPACE": "{{workflow.namespace}}"})
        self.assertNotIn("arguments", self.doc["spec"])


class Deploy(unittest.TestCase):
    def setUp(self):
        doc = yaml.safe_load(DEPLOY.read_text())
        self.source = next(t["script"]["source"] for t in doc["spec"]["templates"]
                           if "helm upgrade --install" in t.get("script", {}).get("source", ""))

    def test_stamps_expiry(self):
        self.assertIn('--labels "mctl.ai/expires-at=${EXPIRES_AT}"', self.source)

    def ttl_block(self):
        # The stretch from the ttl_hours check to EXPIRES_AT, run on its own.
        start = self.source.index('case "$TTL_HOURS" in')
        end = self.source.index("\n", self.source.index("EXPIRES_AT=$(("))
        return self.source[start:end]

    def expires_for(self, ttl):
        with tempfile.TemporaryDirectory() as d:
            date = pathlib.Path(d, "date")
            date.write_text(DATE_STUB)
            date.chmod(0o755)
            proc = subprocess.run(
                [SHELL, "-c", "set -eu\n" + self.ttl_block() + '\necho "$EXPIRES_AT"'],
                env={"PATH": f"{d}:{os.environ['PATH']}", "TTL_HOURS": ttl},
                capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip()

    def test_expiry_arithmetic(self):
        self.assertEqual(self.expires_for("24"), (0, str(NOW + 24 * 3600)))
        self.assertEqual(self.expires_for("08"), (0, str(NOW + 8 * 3600)))
        self.assertEqual(self.expires_for("0"), (0, str(NOW)))
        self.assertEqual(self.expires_for("9999"), (0, str(NOW + 9999 * 3600)))

    def test_rejects_non_numeric_ttl(self):
        for ttl in ("", "1h", "1;id", "-1", "99999"):
            rc, _ = self.expires_for(ttl)
            self.assertNotEqual(rc, 0, ttl)


class Wiring(unittest.TestCase):
    def test_every_preview_tenant_gets_the_cronworkflow(self):
        checked = 0
        for values in sorted(TENANTS.glob("*/values.yaml")):
            tenant = values.parent.name
            out = subprocess.run(
                ["helm", "template", f"tenant-{tenant}", str(CHART), "-f", str(values),
                 "--namespace", tenant], capture_output=True, text=True, check=True).stdout
            docs = [d for d in yaml.safe_load_all(out) if d]
            preview = [d for d in docs if d["kind"] == "Namespace"
                       and d["metadata"].get("labels", {}).get("mctl.me/preview") == "true"]
            crons = [d for d in docs if d["kind"] == "CronWorkflow"]
            if not preview:
                self.assertEqual(crons, [], tenant)
                continue
            checked += 1
            self.assertEqual(len(crons), 1, tenant)
            cron = crons[0]
            self.assertEqual(cron["metadata"]["namespace"], tenant)
            self.assertEqual(preview[0]["metadata"]["name"], f"{tenant}-preview")
            self.assertEqual(cron["spec"]["workflowSpec"]["workflowTemplateRef"],
                             {"name": "preview-reaper", "clusterScope": True})
            self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")
            # The singular `schedule` is removed in Argo 4.0.
            self.assertNotIn("schedule", cron["spec"])
            self.assertEqual(cron["spec"]["schedules"], ["17 * * * *"])
        self.assertGreater(checked, 0)

    def test_project_admits_cronworkflow(self):
        text = PROJECT.read_text()
        start = text.index("namespaceResourceWhitelist:")
        block = text[start:]
        self.assertIn("- group: argoproj.io\n      kind: CronWorkflow", block)


if __name__ == "__main__":
    unittest.main()
