# Design: incident-a2c2e080

## Diagnosis
MctlTelegramToolAvailabilityFastBurn fires when
`mctl_telegram:tool_errors:ratio_rate1h` (the 1h error ratio over
`mctl_tool_invocations_total`) exceeds 7.2%. In the window around this
incident, two portal-routed tool calls from the same user (user_id=1) —
`search_messages` and `get_messages` — failed within the same second
(2026-09-19T20:33:01Z) with `PEER_ID_INVALID`: the caller supplied a peer id
that was not (or was no longer) in that user's Telegram dialog list. The
service logged both failures clearly, including a caller-actionable message
("call list_dialogs and use an id exactly as returned there"). Nine seconds
later the same user called `list_dialogs`, then successfully retried
`search_messages` and `get_messages` against a valid peer id. Every canary
probe cycle and every other tool call in the surrounding hour (20:30-21:10)
returned `status=ok` — mctl-telegram itself was healthy throughout; there is
no evidence of an outage, regression, or infrastructure problem.

Two real errors are enough to cross the 7.2% fast-burn threshold only because
this is a low-traffic service/window — exactly the situation
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
already documents in its header comment:

> Known property, not a bug: on a low-traffic service a 1h window holds few
> invocations, so a couple of errors can cross a burn threshold. docs/slo.md
> prescribes no minimum-volume guard and none is invented here; the
> thresholds are exactly the ones the SLO doc decided. Tune with observed
> traffic rather than by guessing...

Because that file explicitly warns against changing the threshold or adding a
minimum-volume guard without real traffic-pattern data (which this responder
does not have — it only has this one incident's ~40-minute log window), this
proposal does NOT touch the alert expression, the SLI recording rules, or
`mctl-telegram`'s SLO objective. Doing so would contradict the repo's own
documented policy and would be exactly the kind of untuned guess that comment
warns against.

## Proposed Fix
Add a short runbook entry so the next time this alert fires with the same
signature (a handful of `PEER_ID_INVALID` tool-call errors driving the 1h
ratio over 7.2%, canary and all other tool calls healthy), whoever triages it
— human or agent — can recognize the pattern quickly instead of re-deriving
this investigation.

New file: `docs/runbooks/mctl-telegram-tool-availability-fast-burn.md`

Contents: a short runbook (modeled on the existing
`docs/runbooks/otel-collector.md` style) that:
- Names the alert (`MctlTelegramToolAvailabilityFastBurn`) and links to
  `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
  and `mctl-telegram`'s `docs/slo.md`.
- Documents the known low-traffic-false-alarm shape: check whether the errors
  behind `mctl_telegram:tool_errors:ratio_rate1h` are `PEER_ID_INVALID` (or
  other 4xx-shaped MTProto errors) rather than a service-side failure, by
  reading `mctl-telegram` base-service logs for `"mcp tool call"` entries with
  `status=error` in the alert window.
- States plainly that the burn-rate threshold is intentional and should not be
  changed without real traffic data (quoting the existing warning), so no
  agent or on-call engineer re-proposes the same threshold tweak each time
  this fires on a quiet window.
- Notes as a separate, explicitly out-of-scope follow-up: if `PEER_ID_INVALID`
  turns out to be a recurring pattern from the portal client specifically, the
  portal's dialog/peer cache freshness may be worth investigating in
  `mctlhq/mctl-telegram` — that is source-code work outside what this
  responder can verify without access to that repo, and is left for a human
  or a future `mctl-telegram` proposal.

## Scope
Minimal. Adds one new documentation file. No alerting rule, SLO objective, or
service code is modified.
