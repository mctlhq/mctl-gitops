# Tasks: incident-d58db8bb

1. [ ] Confirm the exact label key(s) the default `RecordingRulesNoData`
       alert carries for the affected recording rule (e.g. `recording`,
       `rule_group`/`group`) by inspecting a firing/recent instance via the
       Alertmanager API or vmalert `/api/v1/alerts` — do not assume the
       `recording`/`rule_group` names guessed in design.md without checking.
2. [ ] Add a new route in
       `platform-gitops/bootstrap/templates/observability/monitoring.yaml`,
       above the existing catch-all `RecordingRulesNoData|...` /
       `namespace = "monitoring"` route, sending
       `alertname = "RecordingRulesNoData"` scoped to only
       `mctl_telegram:oauth_5xx:ratio_rate1h` to the `"null"` receiver, using
       the label(s) confirmed in task 1.
3. [ ] Verify the existing catch-all `RecordingRulesNoData|ScrapePoolHasNoTargets|TooManyScrapeErrors|TooManyLogs`
       route is unchanged and still catches RecordingRulesNoData for every
       other recording rule.
4. [ ] If `amtool` or an equivalent config-check tool is available in CI,
       run `amtool config routes test` (or the repo's existing equivalent)
       against the new route to confirm it matches only the intended alert.
