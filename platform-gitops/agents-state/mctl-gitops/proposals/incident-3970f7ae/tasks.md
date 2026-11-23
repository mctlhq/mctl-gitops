# Tasks: incident-3970f7ae

1. [ ] Find the ResourceQuota for namespace labs-preview in mctl-gitops and identify which dimension is at its hard limit.
2. [ ] If a legitimate workload needs more, raise only that field modestly; otherwise leave quota unchanged and adjust the KubeQuotaFullyUsed rule for preview namespaces.
3. [ ] Verify the diff touches only that one field or rule.
