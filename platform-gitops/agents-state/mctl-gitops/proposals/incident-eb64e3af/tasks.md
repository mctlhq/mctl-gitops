# Tasks: incident-eb64e3af

1. [ ] Identify the failed Job in the forgejo namespace (kube_job_failed labels) and its failure reason.
2. [ ] If it is a stale or one-off failure, set ttlSecondsAfterFinished / failedJobsHistoryLimit in platform-gitops/services/forgejo values; otherwise fix the real cause.
3. [ ] Verify the change looks correct; if nothing actionable is found, make no change and report no-op.
