# Tasks: incident-39b614f8

1. [ ] Find the labs tenant ResourceQuota definition in mctl-gitops and confirm which resource the KubeQuotaAlmostFull alert evaluates (services at 23/25 is the suspected one).
2. [ ] Raise the `services` quota for labs from 25 to 40 (or the resource actually identified in step 1), changing only that field.
3. [ ] Verify the diff touches only the labs quota and that the new value does not exceed platform capacity.
