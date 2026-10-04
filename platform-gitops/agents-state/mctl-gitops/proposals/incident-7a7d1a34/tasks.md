# Tasks: incident-7a7d1a34

1. [ ] Review platform-gitops/services/admins/openclaw/values.yaml and the Application definition for admins-openclaw (targetRevision, path) to identify the OutOfSync diff
2. [ ] Apply the minimal fix (correct the value, or add a scoped ignoreDifferences for the single drifting field)
3. [ ] Verify the change renders cleanly and matches the fix applied for ovk-openclaw
