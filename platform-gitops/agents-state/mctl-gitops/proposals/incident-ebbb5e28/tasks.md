# Tasks: incident-ebbb5e28

1. [ ] Search platform-gitops for Job/CronJob templates and values belonging to tenant erpact; identify the one matching KubeJobFailed.
2. [ ] If found, add ttlSecondsAfterFinished / adjust backoffLimit, or fix the single misconfigured field causing the failure.
3. [ ] Verify the change is limited to that one field and renders correctly; if no failing Job is identifiable in the repo, make no change and report needs-triage.
