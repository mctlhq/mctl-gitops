# Design: incident-0f966f1f

## Confidence: LOW

## Diagnosis
This is at least the fifth escalation of `MctlTelegramSessionBorrowSlowBurn`
(plus one related `MctlTelegramSessionBorrowFastBurn` escalation) for tenant
`labs` in the last three weeks: incidents
08255c19-3574-4ce8-95ff-31d6776dd0cd (2026-09-07),
a0693eab-1a7f-4fdd-a900-7578b5d6684e (2026-09-08),
a93817fc-3623-41fa-94cb-eff7a6a813e1 (2026-09-09),
b87ca113-2bf5-4793-8b44-d343e22f370d (2026-09-14), and the fast-burn variant
277ec562-431c-4f02-b75a-5cba6670553a (2026-09-22). No skill exists for this
alert, so mctl-agent escalates it every time with the same `analysis`: "no
skill matched ... the agent has no diagnostic rule for this signal."

The evidence available to this responder (a short tail of
`mctl_get_service_logs`, since the log tool has no pagination and this
service is high-volume) again shows nothing at WARN/ERROR level and no
mention of "session", "borrow", or "error" — identical to the pattern
recorded in incidents 776dd0cd and 6670553a. Those two prior proposals already
diagnosed the actual gap: mctl-telegram increments
`mctl_sessions_borrow_total{result="error"}` (registered in
`internal/metrics/metrics.go`, per the VMRule provenance comment in
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`)
without logging anything at the failure site, so the metric that trips this
alert cannot be correlated to a log line — not by mctl-agent, not by a future
skill, and not by this responder, again, today.

This responder has no source checkout and no PR/build-history access, so it
cannot confirm whether the logging fix proposed in 776dd0cd/6670553a has
already shipped. The service's image tag has advanced from 0.62.0 (first
occurrence) to 0.68.0 (this occurrence), so at least some releases have gone
out since the first proposal, but that does not by itself confirm this
specific change landed. Two possibilities follow from today's evidence:
- If the fix has not shipped, this incident is simply further confirmation
  that it is needed — the same silent-metric gap recurring for the fourth
  time.
- If the fix has shipped and this incident still produced no error-level log
  line, then either no `Pool.Borrow()` errors actually occurred in the ~21
  minutes of log tail retrievable here (the alert's 6h window can easily
  contain a burst outside that slice), or the fix does not cover every error
  path in `Pool.Borrow()`.

One log line of interest, consistent with the alternate mechanism raised in
incident e22f370d: `"idle telegram client, closing","user_id":1,"idle":658038463385}`
(idle ~658s, ~11 minutes). If MTProto client idle-eviction is aggressive
relative to real request spacing for this tenant, a borrow landing right
after eviction pays full reconnect cost — a plausible, still-unconfirmed
contributor to a moderate, sustained 6x-over-6h burn rather than a hard
outage.

## Proposed Fix
1. In the `mctlhq/mctl-telegram` repo, confirm whether a WARN/ERROR log line
   already exists at the `Pool.Borrow()` `result="error"` branch (search for
   the `mctl_sessions_borrow_total` metric name or a `Borrow(` method,
   expected in the session pool package, e.g. `internal/session/pool.go`).
2. If it does not exist, add one now carrying the underlying error, the
   tenant/user identifier (e.g. `tg_user_id`, matching existing field naming),
   and the session identifier if available — no secrets or tokens. This is
   the single highest-leverage change available: it turns every future
   occurrence of this alert from undiagnosable into diagnosable from logs.
3. If the log line already exists and this incident still produced none, note
   that explicitly in the PR description as evidence for a follow-up: whether
   MTProto idle-client eviction (`"idle telegram client, closing"`) is
   aggressive enough relative to this tenant's traffic pattern to be a
   contributing cause, independent of logging (see incident
   b87ca113-2bf5-4793-8b44-d343e22f370d).
4. Do not change `Pool.Borrow()` retry behavior, pool sizing, idle-eviction
   timeouts, or the alert's SLO thresholds in this change — those remain out
   of scope until the logging fix (step 2) produces enough data to justify
   them.

## Scope
Minimal: the `Pool.Borrow()` error-branch log call (if not already present),
and a PR-description note if it is already present. No pool sizing,
retry-logic, idle-timeout, or alert-threshold changes.
