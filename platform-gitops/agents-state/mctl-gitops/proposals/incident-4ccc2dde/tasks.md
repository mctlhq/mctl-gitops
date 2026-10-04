# Tasks: incident-4ccc2dde

1. [ ] Review platform-gitops/services/ovk/openclaw/values.yaml and the Application definition for ovk-openclaw (targetRevision, path) to identify the OutOfSync diff
2. [ ] Apply the minimal fix (correct the value, or add a scoped ignoreDifferences for the single drifting field)
3. [ ] Verify the change renders cleanly and matches the fix applied for admins-openclaw
