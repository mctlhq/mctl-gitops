# Tasks: incident-6804a10f

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
       edit the `expr` of the `mctl_telegram:oauth_5xx:ratio_rate1h` recording rule (group
       `mctl-telegram-slo-sli`) to wrap the numerator in an `or 0 * <denominator>` zero-fill,
       exactly matching the pattern already used for `mctl_telegram:oauth_availability:ratio_rate28d`
       in the same file. Do not change the `ratio_rate6h` rule or any other rule in this
       change — out of scope per design.md.
2. [ ] Verify the edited YAML is well-formed (valid VMRule `expr` block scalar, same
       `sum by (job, namespace) (...) / sum by (job, namespace) (...)` shape as the other
       rules in this file) and that only this one rule's `expr` differs from before.
3. [ ] No image tag bump or other dependent change is needed — this is a VMRule
       config-only change reconciled by ArgoCD.
