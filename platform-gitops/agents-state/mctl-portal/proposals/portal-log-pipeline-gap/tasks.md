# Tasks: portal-log-pipeline-gap

- [ ] 1. Generate controlled traffic against mctl-portal (manual login or scaffolder
      action) and immediately query `mctl_get_service_logs` for that exact window —
      DoD: result is either non-zero lines (query-window issue confirmed) or
      confirmed still zero (rules out query-window as sole cause).
- [ ] 2. Inspect the running mctl-portal backend pod's configured log level and
      output stream (depends on 1) — DoD: documented finding of whether the app is
      emitting logs to stdout/stderr at an expected level.
- [ ] 3. Verify the log-shipping agent status on the node(s)/namespace hosting
      mctl-portal (depends on 2) — DoD: documented finding of whether the shipper is
      running and scraping this workload.
- [ ] 4. Verify Loki-side label matching (namespace/tenant/service labels) used by
      `mctl_get_service_logs`, cross-checking against the `argocd-service-field-gap`
      investigation (depends on 3) — DoD: documented finding of whether label
      mismatch explains the gap, and whether it is the same root cause as the ArgoCD
      `service` field being null.
- [ ] 5. Apply the fix at the identified layer (app config, shipper config, or Loki
      label/query fix) (depends on 4) — DoD: change reviewed and deployed to a lower
      environment first.
- [ ] 6. Re-run task 1's reproduction against the fixed pipeline (depends on 5) —
      DoD: `mctl_get_service_logs` returns non-zero, correctly-scoped log lines for
      the test traffic window.
- [ ] 7. Deploy the validated fix to `admins` production (depends on 6) — DoD:
      `mctl_get_service_logs` returns non-zero lines for mctl-portal on the next
      daily research cycle.

## Tests
- [ ] T1. Manual reproduction test: generate known traffic, confirm corresponding
      log lines appear via `mctl_get_service_logs` within a defined time window.
- [ ] T2. Regression check: confirm no other `admins`-tenant service's logging is
      degraded by any shipper/agent configuration change made during the fix.
- [ ] T3. Follow-up check on the next scheduled daily cycle to confirm the gap does
      not reappear.

## Rollback
If a shipper or Loki-label configuration change causes unexpected side effects
(e.g., log volume spike, other services' logs disrupted), revert the specific
configuration change via the same deployment path it was applied through (gitops
commit revert), restoring the prior (non-functional but non-disruptive) log-shipping
state while the investigation continues offline.
