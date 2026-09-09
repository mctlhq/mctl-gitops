# Design: incident-9dafe20c

## Diagnosis
The MctlTelegramToolAvailabilitySlowBurn alert fires on
`mctl_telegram:tool_errors:ratio_rate6h` (defined in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`),
which is `sum(rate(mctl_tool_invocations_total{status="error"}[6h])) /
sum(rate(mctl_tool_invocations_total[6h]))`. This metric has only two status
values, "ok" and "error" (per the metrics.go provenance comment in that file),
with no further classification of the error. Logs for tenant labs / service
mctl-telegram over the alert window show the synthetic canary succeeding on
every run (`"msg":"canary run complete","ok":true` every ~10 minutes,
`probe ok` for every step), but repeated WARN-level `"mcp tool call"` entries
with `status":"error"` for the `get_messages` tool, all with
`CHANNEL_INVALID` / `PEER_ID_INVALID` errors whose message is literally
"it is not in your dialog list; call list_dialogs and use an id exactly as
returned there". That is a caller passing a stale or wrong peer/channel
reference — a client usage error, not a service-side failure — yet it
increments the same `status="error"` counter that feeds the SLO. On a
tool with modest volume, a short burst of these client errors is enough to
push the 6h ratio over the 3.0% slow-burn threshold while the service itself,
per the canary, was never down.

This is a mctl-telegram code issue, not a mctl-gitops rule issue: the
`mctl_tool_invocations_total{status}` label only carries "ok"/"error" today,
so there is no way to exclude client-input errors from the SLO at the PromQL
layer (unlike `mctl_sessions_borrow_total{result}`, which already
distinguishes `expired_idle`/`expired_absolute` from real errors and is
excluded from that SLI for the same reason — see the session-borrow SLI
comment in mctl-telegram-slo.yaml). The precise call site that classifies
`CHANNEL_INVALID`/`PEER_ID_INVALID` and increments the invocation counter is
in the mctl-telegram source repo (internal/metrics + wherever MCP tool
handlers map Telegram API errors to the "ok"/"error" status label); this
responder does not have access to that repo to name the exact file/line.

## Proposed Fix
In mctl-telegram, stop counting known client-input errors as SLO-relevant
failures:
1. Locate where `mctl_tool_invocations_total{status=...}` is incremented
   (near the MCP tool call handlers / wherever Telegram API errors such as
   CHANNEL_INVALID and PEER_ID_INVALID are already being detected to produce
   the log lines above).
2. Add a third status value, e.g. `status="client_error"`, for errors that
   are caused by invalid caller-supplied input the service correctly
   rejected (starting with CHANNEL_INVALID and PEER_ID_INVALID — "not in
   your dialog list" is a caller mistake, not a reliability problem).
3. `mctl_tool_invocations_total` keeps recording all three values so total
   call-volume dashboards are unaffected.
4. `mctl_telegram:tool_errors:ratio_rate1h` / `...ratio_rate6h` and
   `mctl_telegram:tool_availability:ratio_rate28d` in
   platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml
   keep their current `status="error"` / `status="ok"` selectors unchanged —
   they will automatically stop counting the reclassified calls once the
   client only emits `status="client_error"` for these cases, no VMRule edit
   needed.
5. If reaching into mctl-telegram code is out of scope for this proposal,
   the minimal gitops-only fallback is to raise the slow-burn threshold or
   add a `for:` stabilization window on MctlTelegramToolAvailabilitySlowBurn
   in mctl-telegram-slo.yaml — but this is explicitly against the file's own
   documented policy ("for: 0m throughout, per docs/slo.md ... adding a for:
   on top would delay every page") and papers over the metric rather than
   fixing the misclassification, so it is not the preferred option.

## Scope
Minimal: add one new status classification for CHANNEL_INVALID/PEER_ID_INVALID
at the existing error-mapping site in mctl-telegram; no change to the SLO
recording rules or alert thresholds in mctl-gitops is required.

## Confidence: LOW
The root-cause mechanism (client-input errors inflating the SLO error
counter) is well evidenced by the logs and the VMRule's own metric
definition. The exact file/line in the mctl-telegram source repo is not,
since this responder has no access to that repo — only to mctl-gitops. The
implementer should locate the actual call site before making the change.
