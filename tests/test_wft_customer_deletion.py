"""Exercise deletion callbacks from the actual workflow with isolated tools."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

WORKFLOW = Path('platform-gitops/argo-workflows/cluster-templates/wft-delete-tenant-safe.yaml')

class CustomerDeletionWorkflow(unittest.TestCase):
    def setUp(self):
        self.doc = yaml.safe_load(WORKFLOW.read_text())
        self.templates = {t['name']: t for t in self.doc['spec']['templates']}

    def test_order_and_opt_in(self):
        args = {p['name']: p.get('value') for p in self.doc['spec']['arguments']['parameters']}
        self.assertEqual(args['delete_customer_account'], 'false')
        tasks = {t['name']: t for t in self.templates['delete-tenant-safe-pipeline']['dag']['tasks']}
        self.assertEqual(tasks['retire-services']['dependencies'], ['begin-customer-account'])
        self.assertEqual(set(tasks['cleanup-portal']['dependencies']), {'delete-k8s', 'delete-vault'})
        self.assertEqual(tasks['complete-customer-account']['dependencies'], ['cleanup-portal'])
        for step in ['begin-customer-account', 'complete-customer-account']:
            self.assertIn('delete_customer_account', tasks[step]['when'])

    def test_callback_observation(self):
        for template, bodies in {
            'customer-account-step': [('200', '{"status":"succeeded","stage":"complete"}', True), ('503', '{"details":{"stage":"site-sessions"}}', False), ('200', '{}', False), ('200', '{"status":"succeeded","stage":"begin"}', False)],
            'cleanup-portal': [('200', '{"tenant":"test-customer","cleaned":true}', True), ('200', '{}', False), ('200', '{"tenant":"other","cleaned":true}', False)],
        }.items():
            for status, body, success in bodies:
                with self.subTest(template=template,status=status,body=body), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for name, script in {
                        'apk': '#!/bin/sh\nexit 0\n',
                        'curl': '#!/bin/sh\nif [ "$1" = "--output" ]; then printf "%s" "$BODY" > "$2"; printf "%s" "$STATUS"; else printf "%s" "$BODY"; fi\n',
                    }.items():
                        p = root/name; p.write_text(script); p.chmod(0o755)
                    source = self.templates[template]['script']['source'].replace('/tmp/result.json',str(root/'result.json'))
                    env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}', TENANT='test-customer', PRINCIPAL='prn_01M45DR1GWC87109EH88VBJX25', STAGE='complete', MCTL_API_TOKEN='test', BACKSTAGE_TOKEN='test', BODY=body, STATUS=status)
                    result = subprocess.run(['sh','-c',source],env=env,capture_output=True,text=True)
                    self.assertEqual(result.returncode == 0,success,result.stderr+result.stdout)

if __name__ == '__main__':
    unittest.main()
