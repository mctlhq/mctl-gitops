# Tasks: incident-1f50946c

1. [ ] Locate the Job behind the KubeJobFailed alert in the forgejo namespace and its owning values file in mctl-gitops
2. [ ] Verify the cause; if it is a stale failed Job, set ttlSecondsAfterFinished or failedJobsHistoryLimit; if there is a config error, fix that single value
3. [ ] If no failing Job or recurrence is found, make no change and say so in the PR description
