# Tasks: incident-fd4ba576

1. [ ] Identify the failed Job in the erpact namespace and its owning CronJob/service in platform-gitops/services/erpact/
2. [ ] Determine the failure cause from pod logs/events; edit the single offending value (or add job history/TTL limits for stale failed Jobs)
3. [ ] Verify the change is minimal and that no change touches monitoring-kube-state-metrics itself
