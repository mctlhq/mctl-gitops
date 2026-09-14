# Tasks: incident-79d4bcb1

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
   edit the `expr` of the `mctl_telegram:oauth_5xx:ratio_rate1h` recording
   rule (in the `mctl-telegram-slo-sli` group) to zero-fill both the
   numerator and the denominator against the route-unfiltered
   `mctl_http_requests_total` rate for the same `(job, namespace)`, per
   design.md's "New" block.
2. [ ] In the same file, apply the identical zero-fill pattern to the
   `mctl_telegram:oauth_5xx:ratio_rate6h` recording rule, using `[6h]`
   windows throughout (do not mix `[1h]` and `[6h]` ranges within one rule).
3. [ ] Verify the edited YAML still parses as a valid VMRule (same
   structure/indentation as the surrounding rules) and that the two
   `MctlTelegramOAuthAvailability{Fast,Slow}Burn` alerts still reference
   `mctl_telegram:oauth_5xx:ratio_rate1h` / `ratio_rate6h` unchanged — only
   the recording rules' `expr` changes, not the alerts.
4. [ ] Update `platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`
   with a `promql_expr_test` case asserting that
   `mctl_telegram:oauth_5xx:ratio_rate1h` records `0` (not no series) when
   `mctl_http_requests_total` has samples on an unrelated route but none on
   `/oauth/token` or `/oauth/telegram/callback` in the window — mirroring
   the existing "compliance records 0/1, not nothing" tests already in that
   file for the 28d rules.
5. [ ] No image tag bump or other service change is needed — this is a
   VMRule-only GitOps change picked up by ArgoCD on merge.
