# Tasks: incident-5b1eed1e

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`,
       edit the `mctl_telegram:oauth_5xx:ratio_rate1h` recording rule (group
       `mctl-telegram-slo-sli`) to wrap its numerator in the same
       `(<expr> or 0 * <denominator-shape>)` zero-fill pattern already used by
       `mctl_telegram:oauth_availability:ratio_rate28d` in the same file.
2. [ ] Apply the identical zero-fill edit to the `mctl_telegram:oauth_5xx:ratio_rate6h`
       recording rule immediately below it, using `[6h]` range vectors to match
       the existing rate1h/rate6h pairing.
3. [ ] Verify the edited YAML is still valid (VMRule `spec.groups[].rules[].expr`
       parses as PromQL) and that no other rule, alert threshold, or label in the
       file was changed — this should be a two-expression diff only.
4. [ ] No image tag or other service bump is needed; this is a VMRule
       config-only change reconciled by ArgoCD.
