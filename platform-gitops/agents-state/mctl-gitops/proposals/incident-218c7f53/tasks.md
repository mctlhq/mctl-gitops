# Tasks: incident-218c7f53

1. [ ] Locate the ArgoCD application / service definition for admins-mctl-api in mctl-gitops; confirm whether it exists.
2. [ ] If it exists, inspect values.yaml and manifests for the Degraded cause and fix the single faulty field.
3. [ ] If it does not exist, check the ArgoCDApplicationDegraded rule label mapping; change nothing if the alert is stale.
4. [ ] Verify the change looks correct and is minimal.
