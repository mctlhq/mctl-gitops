# Tasks: incident-50557b9f

1. [ ] Locate the forgejo Job/CronJob definition in mctl-gitops that could produce KubeJobFailed.
2. [ ] If found, apply the minimal fix (history limit / ttlSecondsAfterFinished, or the cause of the failure) in its values.yaml.
3. [ ] Verify the change is limited to that one field; if no Job is found, make no change and say so.
