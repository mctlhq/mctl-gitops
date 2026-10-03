# Tasks: incident-b02e37d3

1. [ ] In platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml,
   add the two new recording rules (`mctl_telegram:session_borrow_errors:count_rate6h`
   and `mctl_telegram:session_borrow_attempts:count_rate6h`) to the
   `mctl-telegram-slo-sli` group, directly after the existing
   `mctl_telegram:session_borrow_errors:ratio_rate6h` rule.
2. [ ] In the same file, update `MctlTelegramSessionBorrowSlowBurn`'s
   `annotations.description` to include the sample-size `query` lookups,
   per design.md.
3. [ ] Confirm the deployed vmalert version supports the `query` template
   function in alert annotations. If it does not, replace step 2 with
   adding the two new recording rules as panels/queries on the existing
   mctl-telegram-overview Grafana dashboard ConfigMap instead, and drop the
   inline `query` calls from the description.
4. [ ] Validate the edited YAML against
   platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml
   (or add a minimal test case there) if that test file already exercises
   this VMRule, so the new recording rules and updated annotation don't
   silently break rule-file linting/CI.
5. [ ] No image tag or other service bump is needed — this is a
   monitoring-config-only change confined to one VMRule file.
