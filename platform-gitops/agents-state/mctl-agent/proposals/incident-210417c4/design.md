# Design: incident-210417c4

## Confidence: LOW

## Diagnosis
MctlTelegramSessionBorrowFastBurn fires when
`mctl_telegram:session_borrow_errors:ratio_rate1h` (the 1h `Pool.Borrow()`
error ratio, excluding TTL expirations) exceeds 14.4% — see
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`.
mctl-agent escalated this ticket because it has no skill/diagnostic rule
registered for this alert name (`analysis` field: "no skill matched ...
Needs a human, or a new skill").

Independent evidence gathered here (labs/mctl-telegram logs, last ~15 minutes
around the incident) shows no session-pool, Telegram-client, or MCP tool
errors — every logged `mcp tool call` and canary `probe` entry reports
`status: "ok"`. That log window is INFO-level only and does not by itself
prove the metric is a false positive; it just shows nothing else was visibly
broken at the same time.

The SLO rule file itself documents this exact class of alert as prone to
false positives: "on a low-traffic service a 1h window holds few
invocations, so a couple of errors can cross a burn threshold" — and
explicitly declines to add a minimum-volume guard, deferring to
mctl-telegram's docs/slo.md. That means the rule should NOT be changed here;
the SLO owners made that call deliberately, and altering the threshold or
adding a volume guard would contradict a documented decision made outside
this proposal's scope.

What IS in scope and matches the escalation reason precisely ("needs ... a
new skill") is closing the Tier-1 diagnostic gap so this alert stops always
requiring a human. This is a code change in mctl-agent (Go), not a config
change, so it lands in the mctl-agent repo rather than mctl-gitops.

## Proposed Fix
Add a new mctl-agent Tier-1 diagnostic skill for alert
`MctlTelegramSessionBorrowFastBurn`, following the existing skill pattern in
`internal/monitor` (see `alerthandler.go::classifyAlert` and the other
registered skills for `MctlTelegramToolAvailabilityFastBurn`/
`MctlTelegramOAuthAvailabilityFastBurn` if present, for the shape to match).
The skill should, on receiving this alert:

1. Fetch recent logs for the affected tenant/service (labs/mctl-telegram) and
   check for corroborating error signals: Telegram MTProto client errors
   (`TelegramClientErrors`-style log lines), DB/session-store connectivity
   errors, or repeated non-"ok" `mcp tool call` entries.
2. If corroborating errors are found, treat as a real page-worthy incident
   and escalate as today (status=escalated) so a human/implementer proposal
   still gets written.
3. If no corroborating errors are found, note in the resolution that this
   matches the SLO rule's documented low-traffic-crossing caveat (cite
   `vm-rules/mctl-telegram-slo.yaml`) and auto-resolve with that explanation,
   rather than escalating every occurrence to a human by default.

This is an additive change (a new skill registration) and does not alter any
existing alerting or routing behavior.

## Scope
Minimal: add one new skill/diagnostic handler for
`MctlTelegramSessionBorrowFastBurn` in mctl-agent. Do not modify the VMRule
alert/recording-rule expressions in mctl-gitops — that would override an
already-documented, deliberate SLO design decision that is out of scope here.
