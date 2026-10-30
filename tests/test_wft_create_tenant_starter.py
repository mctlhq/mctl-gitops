"""Execute the workflow's profile generator and render its actual quotas."""
import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = yaml.safe_load((ROOT / 'platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml').read_text())
COMMIT = next(t for t in DOC['spec']['templates'] if t['name'] == 'commit-tenant-to-git')
SOURCE = COMMIT['script']['source']


class StarterProfile(unittest.TestCase):
    def generate(self, profile):
        start = SOURCE.index('# The starter envelope')
        end = SOURCE.index('# Write catalog-info.yaml')
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, WORKSPACE_PROFILE=profile, TENANT_DIR=tmp,
                       TENANT='profile-test', DISPLAY_NAME='Profile test', DESCRIPTION='Test',
                       MEMBERS_BLOCK='', CPU_REQ='8', CPU_LIM='16', MEM_REQ='8Gi',
                       MEM_LIM='16Gi', PODS='99', INTERNET_EGRESS='false')
            subprocess.run(['sh', '-ec', SOURCE[start:end]], env=env, check=True)
            values = pathlib.Path(tmp) / 'values.yaml'
            parsed = yaml.safe_load(values.read_text())
            rendered = subprocess.check_output(['helm', 'template', 'profile-test',
                str(ROOT / 'platform-gitops/helm-charts/tenant'), '-f', str(values)], text=True)
            quotas = {d['metadata']['namespace']: d['spec']['hard']
                      for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'ResourceQuota'}
            return parsed['tenant'], quotas

    def test_starter_overrides_oversized_input_and_caps_both_namespaces(self):
        tenant, quotas = self.generate('starter')
        prod, preview = quotas['profile-test'], quotas['profile-test-preview']
        self.assertEqual(prod['requests.memory'], '512Mi')
        self.assertEqual(prod['requests.cpu'], '500m')
        self.assertEqual(prod['limits.memory'], '1Gi')
        self.assertEqual(prod['limits.cpu'], '2')
        self.assertEqual(prod['requests.storage'], '10Gi')
        self.assertEqual(prod['persistentvolumeclaims'], '1')
        self.assertEqual(preview['requests.memory'], '256Mi')
        self.assertEqual(preview['requests.cpu'], '100m')
        self.assertEqual(preview['limits.memory'], '512Mi')
        self.assertEqual(preview['requests.storage'], '0')
        self.assertEqual(preview['persistentvolumeclaims'], '0')
        self.assertEqual(tenant['limitRange']['max']['memory'], '1Gi')

    def test_default_app_rollout_and_workflow_containers_fit(self):
        # Old + new app, workflow main + executor wait all receive defaults.
        # Read those defaults from generated values, not a second profile copy.
        tenant, quotas = self.generate('starter')
        count = 4
        lr = tenant['limitRange']
        self.assertLessEqual(count * int(lr['defaultRequest']['cpu'].removesuffix('m')),
                             int(quotas['profile-test']['requests.cpu'].removesuffix('m')))
        self.assertLessEqual(count * int(lr['default']['cpu'].removesuffix('m')),
                             1000 * int(quotas['profile-test']['limits.cpu']))
        self.assertLessEqual(count * int(lr['defaultRequest']['memory'].removesuffix('Mi')), 512)
        self.assertLessEqual(count * int(lr['default']['memory'].removesuffix('Mi')), 1024)

    def test_standard_preserves_existing_defaults_and_supplied_quotas(self):
        _, quotas = self.generate('standard')
        self.assertEqual(quotas['profile-test']['requests.memory'], '8Gi')
        self.assertNotIn('requests.storage', quotas['profile-test'])
        self.assertEqual(quotas['profile-test-preview']['requests.memory'], '256Mi')
        self.assertEqual(quotas['profile-test-preview']['limits.memory'], '1Gi')

    def test_profile_is_bound_through_workflow_input_and_env(self):
        self.assertIn({'name': 'PARAM_WORKSPACE_PROFILE', 'value': '{{inputs.parameters.workspace_profile}}'}, COMMIT['script']['env'])
        pipeline = next(t for t in DOC['spec']['templates'] if t['name'] == 'create-tenant-pipeline')
        task = next(t for t in pipeline['dag']['tasks'] if t.get('template') == 'commit-tenant-to-git')
        self.assertIn({'name': 'workspace_profile', 'value': '{{workflow.parameters.workspace_profile}}'}, task['arguments']['parameters'])
        start = SOURCE.index('WORKSPACE_PROFILE=')
        end = SOURCE.index('TENANT=', start)
        result = subprocess.run(['sh', '-ec', SOURCE[start:end]], env=dict(os.environ, PARAM_WORKSPACE_PROFILE='unknown'), capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
