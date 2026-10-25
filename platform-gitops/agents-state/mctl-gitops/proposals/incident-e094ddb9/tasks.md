# Tasks: incident-e094ddb9

1. [ ] Verify whether the vault StatefulSet is still unready; if the alert has cleared, make no change.
2. [ ] Review recent changes to the vault service values in mctl-gitops and identify any field (image tag, resources, probes, storage) that plausibly blocks rollout.
3. [ ] If a faulty field is found, correct that single field; otherwise leave files unchanged and note the finding.
