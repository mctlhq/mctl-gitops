# Tasks: incident-a2c2e080

1. [ ] Create `docs/runbooks/mctl-telegram-tool-availability-fast-burn.md`
       documenting the `MctlTelegramToolAvailabilityFastBurn` alert: what it
       measures (`mctl_telegram:tool_errors:ratio_rate1h` in
       `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`),
       the known low-traffic false-alarm shape (a couple of client-caused
       errors, e.g. `PEER_ID_INVALID`, crossing the 7.2% threshold in a quiet
       1h window), how to triage it (check `mctl-telegram` base-service logs
       for `"mcp tool call"` / `status=error` entries in the alert window and
       compare against canary health), and an explicit note that the
       threshold itself should not be changed without real traffic data.
2. [ ] Verify the new runbook renders correctly as markdown and follows the
       existing style/structure of `docs/runbooks/otel-collector.md` (title,
       short summary paragraph, source/links, troubleshooting section).
3. [ ] No dependent changes. No alert rules, SLO recording rules, image tags,
       or service code are touched by this proposal.
