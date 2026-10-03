# Tasks: mctl-self-observability-gap

- [ ] 1. Check whether the broken lookup path is shared with any authorization decision code
      (per architecture.md's cross-tenant-leak known limitation) — DoD: written confirmation
      (PR/issue comment) that the config/status/log lookup path is either (a) fully separate from
      tenant-scope authorization logic, or (b) shared, in which case this task's finding is
      escalated to a security-priority fix before continuing.
- [ ] 2. Reproduce the three failures (`get_service_config`, null `service` field in
      `get_service_status`, empty `get_service_logs`) against `team=admins, service=mctl-api` in a
      controlled/staging environment, and run the same three calls against at least one other
      known-good `admins`-tenant service — DoD: documented comparison showing mctl-api-specific
      failure vs. the other service's success (or documented finding that the bug is broader,
      per requirements' follow-up clause).
- [ ] 3. Inspect mctl-api's own Backstage catalog entry (`catalog-info.yaml` or scaffolder-
      generated equivalent) and compare its `metadata.name`/`metadata.namespace` (or equivalent
      identifying fields) against the exact key string `admins/mctl-api` used internally by
      `get_service_config` and `get_service_logs` (depends on 2) — DoD: documented root-cause
      finding: either a confirmed key mismatch (with the exact mismatched strings), or confirmation
      the catalog entry is correctly keyed and the bug is elsewhere.
- [ ] 4. Inspect the Kubernetes label selector `get_service_status`'s pod-metrics path and
      `get_service_logs`'s Loki (or equivalent) query use, and compare against mctl-api's actual
      deployed pod labels (depends on 2) — DoD: documented root-cause finding: either a confirmed
      label/selector mismatch (with exact expected vs. actual labels), or confirmation labels are
      correct and the bug is elsewhere.
- [ ] 5. Implement the fix at the resolution/query layer (not a special-case alias) based on the
      root cause(s) found in tasks 3 and 4 (depends on 3, 4) — DoD: code change reviewed and
      merged; `go build ./...` and `go test ./...` pass.
- [ ] 6. Regression-test all four tools (`get_service_status`, `get_service_config`,
      `get_service_logs`, `get_tenant_metrics`) against `team=admins, service=mctl-api` in staging
      (depends on 5) — DoD: `get_service_config` returns a valid config object with a deployed
      image tag; `get_service_status`'s `service` field is non-null with CPU/memory/replica data;
      `get_service_logs` returns `count > 0` and non-null `lines` for a window with known traffic.
- [ ] 7. Cross-check the fix does not regress the other known-good service used in task 2 (depends
      on 6) — DoD: the comparison service's tool responses are unchanged (still correct) after the
      fix.
- [ ] 8. Update `context/current-version.md`'s "Last update of this file" date and confirm its
      stated version (4.14.0) against the now-working `get_service_config` output (depends on 6) —
      DoD: `current-version.md` reflects a verified, current image tag and date.
- [ ] 9. Deploy via mctl-gitops → ArgoCD to `admins` tenant (depends on 5, 6, 7) — DoD: ArgoCD
      reports `Healthy`/`Synced` for `admins-mctl-api`; the three previously-broken tool calls
      succeed against production.

## Tests
- [ ] T1. `mctl_get_service_config(team=admins, service=mctl-api)` returns a valid config object
      (no "service not found" error).
- [ ] T2. `mctl_get_service_status(team=admins, service=mctl-api)` returns a non-null `service`
      field with plausible CPU/memory/replica values.
- [ ] T3. `mctl_get_service_logs(team=admins, service=mctl-api, since=24h)` returns `count > 0`
      and non-null `lines` during a window with known request traffic (e.g. immediately after a
      manual smoke-test call to the service).
- [ ] T4. The comparison service from task 2/7 still returns correct data for all three tools
      after the fix (no regression).
- [ ] T5. If task 1 found any shared authorization-path risk, a dedicated security regression test
      confirms tenant-scope authorization is unaffected by the fix.

## Rollback
1. Revert the resolution/query-layer code change: `git revert <commit-sha>`.
2. Revert any Backstage catalog-info or Kubernetes label manifest change via mctl-gitops.
3. Redeploy via ArgoCD; confirm `admins-mctl-api` returns to `Healthy`/`Synced`.
4. Since this fix only touches lookup/query logic (no data migration, no schema change), rollback
   restores the prior (broken-but-known) observability state with no data-loss risk — the only
   regression is losing self-introspection again, not a functional outage of mctl-api itself.
