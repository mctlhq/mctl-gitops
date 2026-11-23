# Tasks: incident-d7b7eb91

1. [ ] Read platform-gitops/services/admins/mctl-agents-worker/values.yaml and compare image tag and replica/autoscaling settings with live state (imageTag 1.117.0, Healthy).
2. [ ] Identify the field causing the persistent OutOfSync diff; apply the minimal fix (align value or add a narrow ignoreDifferences entry).
3. [ ] Verify the change touches only this service; if no cause is found in the repo, make no change and note it in the PR or report.
