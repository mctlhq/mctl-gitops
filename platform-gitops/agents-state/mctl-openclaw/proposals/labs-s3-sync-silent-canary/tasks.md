# Tasks: labs-s3-sync-silent-canary

- [ ] 1. Enumerate all containers in the `labs`/`openclaw` pod spec and re-run
  `mctl_get_service_logs` for each container name individually (not just the
  assumed `s3-sync` name) across a 1h and 6h window. — DoD: either fresh log
  output is found under a different container name, or naming is confirmed
  correct and the zero-line result stands.
- [ ] 2. Query Argo Workflows for the `labs` s3-sync CronWorkflow status directly
  (last scheduled run, last successful run, exit code/error, next scheduled run).
  (depends on 1, can run in parallel if tooling differs) — DoD: a timestamped
  status record for the `labs` CronWorkflow is captured and compared against the
  same query for `admins`/`ovk`.
- [ ] 3. If accessible read-only, list the `labs` S3 state bucket and record the
  most recent object write timestamp; compare against `admins`/`ovk` buckets
  sampled in the same window. — DoD: either a recent write is found (canary/log
  pipeline issue, sync itself is healthy) or no recent write is found (genuine
  gap, escalate).
- [ ] 4. Re-sample `labs` s3-sync logs over a longer window (e.g. 24h) and at a
  different time of day, to rule out a low-activity artifact of `labs` being the
  experimental/lower-traffic tenant. (depends on 1) — DoD: a 24h window sample is
  recorded with line count and timestamps (or confirmed still zero).
- [ ] 5. Write up a short root-cause determination (naming mismatch / tooling gap /
  genuine sync failure / low-activity artifact) with supporting evidence from
  tasks 1-4. (depends on 1, 2, 3, 4) — DoD: a one-page findings note exists,
  referencing the specific log/status/bucket evidence gathered.
- [ ] 6. IF task 5 confirms a genuine sync gap, open a tracked incident/action item
  with the findings attached; IF it confirms a tooling/logging gap, document the
  correct query/container name for future metrics passes. (depends on 5) —
  DoD: either an incident is opened and linked here, or a documented correction is
  recorded for the next researcher pass; this proposal does not close silently on
  an unexplained zero-line result.

## Tests
- [ ] T1. Confirm the corrected log query (per task 1/6) reliably returns non-zero
  output for `labs`/`openclaw` s3-sync when sync is known to be healthy (sanity
  check against the same query pattern that already works for `admins`/`ovk`).
- [ ] T2. Confirm the Argo Workflows status check (task 2) can be repeated
  on-demand and produces consistent last-run timestamps across two separate query
  runs a few minutes apart.
- [ ] T3. If an incident is opened (task 6), confirm it is visible via
  `mctl_list_incidents` for team `labs` on the next check.

## Rollback
This proposal makes no configuration, code, or infrastructure changes — it is a
read-only diagnostic pass, so there is nothing to roll back. If task 6 results in an
incident being opened in error (e.g. later shown to be a false positive from a
tooling gap), the rollback is simply to close/annotate that incident with the
corrected finding; no system state needs to be reverted.
