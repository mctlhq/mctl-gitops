# Design: incident-2430bb39

## Confidence: LOW

## Diagnosis
`MctlTelegramSessionBorrowSlowBurn` is a multi-window burn-rate SLO alert
(docs/slo.md in mctlhq/mctl-telegram), not a rule keyed to a specific log
signature, and no skill in mctl-agent has a diagnostic for it yet — hence the
escalation. Reading the deployed VMRule
(platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml),
it fires on `mctl_telegram:session_borrow_errors:ratio_rate6h > 0.060`: the
Pool.Borrow() error rate (excluding expected idle/absolute TTL expirations)
exceeded 6% over the trailing 6h. This tool has no VictoriaMetrics query
access and no direct access to the `mctl_sessions_borrow_total{result}`
series, so the specific borrows that failed cannot be enumerated from here.
mctl_get_service_logs over the full 6h window (776 lines, LOG_LEVEL=info) shows
no `status="error"` or borrow-failure log line at all — every sampled
`mcp tool call` and canary `probe` entry is `ok`. That does not clear the
alert: an `info`-level service may simply not log borrow failures at that
level, or the failures fall outside the sampled lines.

The one concrete, documented lead in this service's own config is the canary
CronJob comment in
platform-gitops/services/labs/mctl-telegram/values.yaml (lines ~437-451):
the canary's Telegram identity is meant to be 924671154, moved off 210408407
specifically because 210408407 is also logged into preview MCP and "sharing
one MTProto user across prod+preview causes AUTH_KEY_DUPLICATED" — and the
same comment states the out-of-band `mctl-telegram-canary` Secret "was never
reminted after the note below was written" and both databases still show
210408407 active on stable and preview simultaneously. AUTH_KEY_DUPLICATED is
exactly the class of MTProto failure that would surface as a Pool.Borrow()
error on every subsequent call for that identity — a small, low but sustained
error contribution consistent with a *slow* burn (6x/6h) rather than a fast
one (14.4x/1h). This is a plausible contributing cause already flagged by a
prior engineer, not a fresh guess, but it is unverified against the actual
metric breakdown, hence LOW confidence.

## Proposed Fix
This tool cannot rotate the out-of-band Vault-backed `mctl-telegram-canary`
Secret itself — by design (see the values.yaml comment) that identity lives
outside git and outside this pipeline's write scope
(`$INCIDENT_STATE_DIR/` only). The gitops-safe, minimal action available here
is to put the lead where the human who files/reads the reliability ticket
will see it, directly on the alert:

File: `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
Field: `spec.groups[name=mctl-telegram-slo-burn].rules[alert=MctlTelegramSessionBorrowSlowBurn].annotations.description`

Current value (lines 300-307):
```
description: >-
  The Pool.Borrow() error rate over the last 6h, excluding expected
  TTL expirations, is {{ $value | humanizePercentage }} — above the
  6.0% slow-burn threshold (6x the 99% objective's budget). File a
  reliability ticket; no page.
  SLO and error-budget policy:
  https://github.com/mctlhq/mctl-telegram/blob/main/docs/slo.md
```

New value: append one sentence pointing at the documented AUTH_KEY_DUPLICATED
risk so the next occurrence does not need to be re-derived from scratch:
```
description: >-
  The Pool.Borrow() error rate over the last 6h, excluding expected
  TTL expirations, is {{ $value | humanizePercentage }} — above the
  6.0% slow-burn threshold (6x the 99% objective's budget). File a
  reliability ticket; no page.
  Known contributing risk (unverified, check first): the canary's
  out-of-band mctl-telegram-canary Secret may still carry tg_user_id
  210408407 instead of the intended 924671154, which is also logged into
  preview MCP — a shared MTProto identity across prod+preview causes
  AUTH_KEY_DUPLICATED, which surfaces as Pool.Borrow() errors. See the
  canary CronJob comment in
  platform-gitops/services/labs/mctl-telegram/values.yaml.
  SLO and error-budget policy:
  https://github.com/mctlhq/mctl-telegram/blob/main/docs/slo.md
```

This is documentation-only: it changes no alerting threshold, no routing, and
no application behavior, so it carries no risk of masking or suppressing a
real page.

## Scope
Minimal. Only the `description` annotation string on the single
`MctlTelegramSessionBorrowSlowBurn` alert rule is touched. No other alert, no
threshold, no application code, and no Secret is touched by this proposal.
