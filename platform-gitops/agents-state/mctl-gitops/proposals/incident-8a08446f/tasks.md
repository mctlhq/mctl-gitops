# Tasks: incident-8a08446f

1. [ ] Edit `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`:
   change the `expr` of the `mctl_telegram:oauth_5xx:ratio_rate1h` recording
   rule (in the `mctl-telegram-slo-sli` group) to zero-fill the numerator with
   `or 0 * sum by (job, namespace) (...)`, matching the pattern already used
   by `mctl_telegram:oauth_availability:ratio_rate28d` in the same file. See
   design.md for the exact before/after expr.
2. [ ] Verify the YAML still parses as a valid VMRule (indentation of the
   parenthesized `expr` block, `|` block scalar preserved) and that only the
   `ratio_rate1h` rule changed — `ratio_rate6h` and all other rules in the
   file must be byte-for-byte unchanged.
3. [ ] Add a unit test case to
   `platform-gitops/infra-components/observability/vm-rules/tests/mctl-telegram-slo_test.yaml`
   under a new "OAuth 5xx SLI" section: assert
   `mctl_telegram:oauth_5xx:ratio_rate1h` records `0` (not no series) when
   `mctl_http_requests_total` has only `status_code="200"` samples on
   `/oauth/token`, mirroring the existing "oauth availability compliance
   records 1 when there is no 5xx series at all" test for the 28d rule.
4. [ ] Run the repo's VM rules check (`scripts/check-vm-rules.sh` /
   promtool test, as used by the existing test suite) to confirm the new and
   existing tests pass.
5. [ ] No image tag bump or other dependent changes needed — this is a rules
   config-only change.
