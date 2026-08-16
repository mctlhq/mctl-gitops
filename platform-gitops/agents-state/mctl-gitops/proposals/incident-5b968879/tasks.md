# Tasks: incident-5b968879

1. [ ] Locate the HPA configuration for labs-agent-worker-preview (likely in services/labs/agent-worker-preview/values.yaml)
2. [ ] Read the current maxReplicas value (expected: 5 or similar)
3. [ ] Change maxReplicas from current value to 10
4. [ ] Verify the change is syntactically correct (valid YAML)
5. [ ] Commit and push the change to the mctl-gitops repository
6. [ ] ArgoCD will automatically sync and apply the new HPA configuration
7. [ ] Verify that labs-agent-worker-preview scales up to accommodate pending load
8. [ ] Confirm ArgoCD health status returns to Healthy (green)
