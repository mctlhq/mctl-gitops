# Tasks: incident-c64b6f8b

1. [ ] Query the session-borrow metric/histogram backing `MctlTelegramSessionBorrowSlowBurn` for tenant labs / service mctl-telegram over the alert's 6h window to confirm whether borrow latency/errors are genuinely elevated.
2. [ ] If contention is confirmed: locate and increase the session-pool size / borrow timeout setting for labs mctl-telegram in `platform-gitops/services/labs/mctl-telegram/values.yaml`.
3. [ ] If the metric looks normal and the alert is oversensitive: locate and relax the `MctlTelegramSessionBorrowSlowBurn` rule thresholds in the relevant PrometheusRule/AlertManager file under platform-gitops.
4. [ ] Verify the edited YAML is valid and consistent with neighboring rules/values (indentation, keys, no unrelated fields touched).
5. [ ] Bump any dependent chart/values version if the gitops convention requires it for the change to sync via ArgoCD.
