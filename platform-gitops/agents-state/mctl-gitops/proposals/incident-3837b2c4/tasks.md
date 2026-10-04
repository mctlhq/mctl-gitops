# Tasks: incident-3837b2c4

1. [ ] Locate the erpact-backup definition under platform-gitops/services/erpact/ and determine the container waiting reason (image, missing secret/configmap, scheduling).
2. [ ] Correct the offending value (image tag, secret reference, resource request) in that definition; if no definition exists, make no change and record that the pod is orphaned.
3. [ ] Verify the change is limited to the single faulty field and that the ArgoCD app name matches the service naming convention.
