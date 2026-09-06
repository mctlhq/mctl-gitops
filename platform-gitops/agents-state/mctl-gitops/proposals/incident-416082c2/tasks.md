# Tasks: incident-416082c2

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
   update the `expr` of the `mctl_telegram:oauth_5xx:ratio_rate1h` record
   (group `mctl-telegram-slo-sli`) to add the `or (0 * sum by (job, namespace)
   (rate(mctl_http_requests_total[1h])))` fallback shown in design.md.
2. [ ] Run `scripts/check-vm-rules.sh` (or the repo's equivalent promtool test
   entrypoint) to regenerate `tests/generated/mctl-telegram-slo.yaml` and
   confirm the existing OAuth burn-rate tests in
   `platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`
   still pass unchanged.
3. [ ] Add a new `promql_expr_test` case to that test file, mirroring the
   existing 28d-compliance "records 0/1 at the extremes" tests, that feeds
   only unrelated-route traffic (no `/oauth/token` or
   `/oauth/telegram/callback` series at all) and asserts
   `mctl_telegram:oauth_5xx:ratio_rate1h` records `0` for that (job,
   namespace) instead of no series.
4. [ ] Verify the change does not alter recorded values for any window that
   already has OAuth-route traffic (division result identical; the `or`
   branch only activates when the primary expression is empty).
5. [ ] File a follow-up note (or a separate proposal) for applying the same
   zero-fill fallback to `mctl_telegram:oauth_5xx:ratio_rate6h`,
   `mctl_telegram:tool_errors:ratio_rate1h/6h`, and
   `mctl_telegram:session_borrow_errors:ratio_rate1h/6h`, which share the same
   latent gap but are out of scope for this specific alert.
