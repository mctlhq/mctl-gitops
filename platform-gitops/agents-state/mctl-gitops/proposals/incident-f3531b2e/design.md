# Design: incident-f3531b2e

## Confidence: LOW

## Diagnosis
MctlTelegramSessionBorrowSlowBurn fires when
`mctl_telegram:session_borrow_errors:ratio_rate6h` (the share of `Pool.Borrow()`
calls returning `result="error"`, excluding TTL expirations) exceeds 6% over a
6-hour window (infra-components/observability/vm-rules/mctl-telegram-slo.yaml).
No skill matched this ticket, and the ~13 minutes of logs available to this
responder (last 50 lines, tenant=labs/service=mctl-telegram) show zero errors of
any kind: every OAuth client_registration, MCP tool call, and 10-minute canary
probe in that window completed successfully. The window this responder can see
is far shorter than the alert's 6h lookback, so it cannot confirm or rule out
where in that window the error volume actually accumulated — the condition may
already have self-resolved, or the failures may be sparse enough not to appear
in a 13-minute tail.

The strongest lead is not in the logs but in this repo's own history: the
canary CronJob comment in services/labs/mctl-telegram/values.yaml documents that
sharing one MTProto identity across the stable and preview deployments causes
`AUTH_KEY_DUPLICATED` session-borrow failures, and records an unresolved,
acknowledged discrepancy — the canary is *intended* to run as Telegram user
924671154, but "the secret was never reminted after the note below was
written," and "both databases confirm 210408407 is active on stable and preview
simultaneously." Separately, services/labs/mctl-telegram-preview/values.yaml
confirms 210408407 is deliberately kept logged in on preview with
`AGENT_ENABLED: "true"` and `listener_enabled` on that account's own MTProto
session, for the continuous communication-agent soak. If 210408407's stable-side
session is still in play anywhere in the pool (directly, or via secret drift),
that overlap is a plausible, previously-flagged source of intermittent
session-borrow errors on the stable pool — but this responder has no metrics
access (logs only) and cannot confirm the error series actually correlates with
this identity, so this remains a lead, not a confirmed root cause.

## Proposed Fix
No git-manageable root-cause fix is available: the canary's identity lives in an
out-of-band Kubernetes Secret (`mctl-telegram-canary`, holding `tg_user_id` +
`bearer_token`), explicitly documented as "not in git," so no gitops PR can
rotate it. The only safe, minimal, git-manageable action is to convert the
already-known-but-easy-to-miss risk into an explicit, actionable operator
checklist at the point future readers are most likely to be editing this file.

File: services/labs/mctl-telegram/values.yaml
Add a short comment block immediately above the existing canary CronJob comment
(the block starting "# Synthetic end-to-end canary...", around line 437), noting:
- Incident 5a1534d8-b8e8-4985-885d-a969f3531b2e (MctlTelegramSessionBorrowSlowBurn)
  observed on 2026-09-24 flagged this drift as a live suspect.
- Verify the live secret's identity:
  `kubectl -n labs get secret mctl-telegram-canary -o jsonpath='{.data.tg_user_id}' | base64 -d`
- Expected value: 924671154. If it reads 210408407, remint it via the canary's
  self-renewal path (see mctl-telegram#421) or an operator login, since
  210408407 is concurrently held open on preview
  (services/labs/mctl-telegram-preview/values.yaml, AGENT_ENABLED soak).

This does not resolve the alert by itself — it turns a documented-but-buried
risk into a checked, datestamped operator action. A human should verify the
live secret value directly; this responder has no shell/kubectl access to do so.

## Scope
Minimal: one comment addition to one file. No env vars, resource limits, or
alert thresholds are changed. No code change is proposed given LOW confidence
in the root cause.
