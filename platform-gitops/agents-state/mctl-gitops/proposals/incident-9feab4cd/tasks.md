# Tasks: incident-9feab4cd

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
   update the `expr:` of `mctl_telegram:oauth_5xx:ratio_rate1h` (group
   `mctl-telegram-slo-sli`) to wrap the numerator in
   `( <existing numerator> or 0 * <denominator-without-status-filter> )`,
   matching the zero-fill pattern already used by
   `mctl_telegram:oauth_availability:ratio_rate28d` in the same file.
2. [ ] Apply the identical zero-fill change to the `expr:` of
   `mctl_telegram:oauth_5xx:ratio_rate6h` in the same group, using `[6h]`
   ranges.
3. [ ] Verify the edited YAML is well-formed and the VMRule still lists all
   original rules/alerts (no unintended deletions); compare against
   `platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`
   if it covers these rules, and update/add a test case there for the
   zero-5xx case if the test file's format supports it.
4. [ ] No image tag or other service bump is needed — this is a VMRule
   config-only change and ArgoCD will reconcile it directly.
