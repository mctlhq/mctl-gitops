# Tasks: incident-58bb178b

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
   edit the `expr` of the `mctl_telegram:oauth_5xx:ratio_rate1h` record (in
   the `mctl-telegram-slo-sli` group) to wrap the numerator in an
   `or 0 * <denominator>` zero-fill, matching the pattern already used by
   `mctl_telegram:oauth_availability:ratio_rate28d` in the same file. Do not
   change `mctl_telegram:oauth_5xx:ratio_rate6h` or any other rule.
2. [ ] Verify the edited YAML still parses as a valid VMRule (indentation and
   the `|` block scalar for `expr` preserved) and that the rule name,
   labels and the `MctlTelegramOAuthAvailabilityFastBurn` alert expression
   that reads this series are unchanged.
3. [ ] No dependent changes (no image tag bump; this is a config-only VMRule
   edit reconciled by ArgoCD).
