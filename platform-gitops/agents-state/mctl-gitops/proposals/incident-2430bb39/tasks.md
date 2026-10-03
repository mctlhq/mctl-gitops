# Tasks: incident-2430bb39

1. [ ] Add `docs/runbooks/mctl-telegram-session-borrow-slow-burn.md` (new
       file) containing: the alert name and links to
       `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
       and `mctl-telegram`'s `docs/slo.md`; the precise SLI definition
       (`mctl_sessions_borrow_total{result="error"}` vs. `result=~"ok|error"`
       over 6h, excluding `expired_idle`/`expired_absolute`); the triage path
       (query the metric by `result` in VictoriaMetrics/Grafana before
       reading logs, since base-service "mcp tool call" log lines do not
       reflect `Pool.Borrow()`'s result); the log-tooling limitation recorded
       in this proposal's design.md (a 6h `mctl_get_service_logs` pull
       exceeds the output-size limit around 90-100 lines, so pull in smaller
       `since` slices); and the out-of-scope follow-up correlating a
       confirmed error rate against `TelegramClientErrors` and Telegram
       flood-wait events before any pool/resource config change.
2. [ ] Verify the new file follows the existing style/structure of
       `docs/runbooks/otel-collector.md` (or another existing runbook in that
       directory) and that both linked paths
       (`mctl-telegram-slo.yaml` and `docs/slo.md`) resolve correctly.
3. [ ] No dependent changes (no image tag bump, no values.yaml edit, no
       alerting-rule edit) — this proposal is documentation-only.
