# Tasks: incident-d35920f1

1. [ ] Edit `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`:
       add an `or 0 * sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h]))`
       zero-fill to the numerator of the `mctl_telegram:oauth_5xx:ratio_rate1h`
       recording rule (currently at line 86), matching the pattern used by
       `mctl_telegram:oauth_availability:ratio_rate28d` further down the file.
2. [ ] Apply the same zero-fill (with `[6h]` in place of `[1h]`) to the
       numerator of `mctl_telegram:oauth_5xx:ratio_rate6h` (currently at
       line 95).
3. [ ] Verify the edited YAML is still valid (indentation, `expr: |` block
       scalars) and that `mctl_telegram-slo_test.yaml` under
       `platform-gitops/infra-components/observability/vm-rules/tests/` still
       parses against the new expressions — update its expected fixtures if it
       asserts on the exact `expr` text.
4. [ ] No image tag or other service bump is needed; this is a VMRule-only
       change reconciled by ArgoCD.
