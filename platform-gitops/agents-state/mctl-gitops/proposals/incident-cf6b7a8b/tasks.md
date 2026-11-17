# Tasks: incident-cf6b7a8b

1. [ ] Find the ResourceQuota / tenant definition for the admins tenant in mctl-gitops and confirm the current `services` limit is 10.
2. [ ] Raise `services` to 15 (optionally pods to 24, limits.memory to 6Gi).
3. [ ] Verify the diff touches only the admins tenant quota and nothing else.
