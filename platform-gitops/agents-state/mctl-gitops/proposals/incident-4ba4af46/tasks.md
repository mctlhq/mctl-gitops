# Tasks: incident-4ba4af46

1. [ ] Edit `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
       group `mctl-telegram-slo-sli`: wrap the numerator of the
       `mctl_telegram:oauth_5xx:ratio_rate1h` recording rule's `expr` in a
       `(... or 0 * sum by (job, namespace) (rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h])))`
       zero-fill guard, matching the pattern already used in the
       `mctl-telegram-slo-compliance` group's 28d rules in the same file.
2. [ ] Apply the identical zero-fill transform to the
       `mctl_telegram:oauth_5xx:ratio_rate6h` recording rule immediately
       below it (same pattern, `[6h]` windows).
3. [ ] Verify the edited YAML is valid (VMRule spec parses, `expr` block
       scalars are well-formed) and that no other field (record name,
       interval, the alert rules below in `mctl-telegram-slo-burn`) was
       touched.
4. [ ] Add or extend a case in
       `platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`
       mirroring the existing 28d "records 1 when there is no 5xx series at
       all" test, but for `mctl_telegram:oauth_5xx:ratio_rate1h`, to pin the
       fix and prevent regression.
5. [ ] No image tag or dependent service change needed — this is a
       rules-only GitOps change; ArgoCD sync of the VMRule is sufficient.
