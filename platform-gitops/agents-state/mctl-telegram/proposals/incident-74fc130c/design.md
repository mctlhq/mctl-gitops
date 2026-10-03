# Design: incident-74fc130c

## Confidence: LOW

## Diagnosis
`MctlTelegramSessionBorrowFastBurn` fires on
`mctl_telegram:session_borrow_errors:ratio_rate1h` exceeding 14.4%
(mctl-telegram-slo.yaml) — a real `mctl_sessions_borrow_total{result="error"}`
signal, excluding expected TTL expirations. No skill matches this alert
because it is a generic SLO burn-rate rule with no dedicated diagnostic rule.

Application logs for labs/mctl-telegram over the full 6h window (which fully
covers the 1h burn window this alert evaluates) contain no line mentioning
"borrow" or "pool", and no ERROR-level line at all; the two WARN-level lines
present are an unrelated OAuth bearer-token expiry on the MCP HTTP layer
(route /mcp, provider local-jwt), not the Telegram MTProto session pool this
alert measures, and neither by itself explains a 14.4x/1h burn. The service
is otherwise healthy: ArgoCD reports Healthy/Synced, and the synthetic
canary succeeds on every run in the window. This is not a diagnosis gap
unique to this run — it is the identical evidence pattern recorded on prior
escalations of this same alert pair going back to 2026-09-07 (most recently
the fast-burn variant on 2026-09-22), two of which already proposed adding a
log line at the `Pool.Borrow()` error path. The alert has continued to recur
through image versions 0.62.x, 0.67.0, 0.68.0 and now 0.69.0, which means
either that fix was never merged, or the observability gap it targeted is
still open.

This incident's slow-burn sibling (9204d14c-ac54-48e9-b0f6-e29e4331f490)
fired in the same minute — the first time in this alert's history that both
windows crossed together — which may indicate a real, larger burst of borrow
failures rather than the low-traffic trickle seen in earlier occurrences.
The root cause of the underlying `Pool.Borrow()` errors themselves remains
unconfirmed — this responder has no source access to mctl-telegram (no
shell, no metrics-query tool) and cannot inspect the pool implementation or
query `mctl_sessions_borrow_total` directly.

## Proposed Fix
In the mctl-telegram repository, add a structured log line (WARN or ERROR
level, so it survives the deployed `LOG_LEVEL: info`) at the `Pool.Borrow()`
error-return path — wherever `mctl_sessions_borrow_total{result="error"}` is
incremented in the session pool package — recording at minimum the
user/session identifier and the underlying error. This does not change
`Pool.Borrow()` control flow, retries, or pool sizing; it only makes the
next occurrence of this alert diagnosable from Loki logs instead of requiring
direct Prometheus/VictoriaMetrics access this responder does not have.

This is the same fix as its slow-burn sibling proposal
(mctl-telegram/proposals/incident-4331f490) — one code change should satisfy
both; the implementer should treat these as duplicates of the same
underlying gap rather than two separate changes.

## Scope
Minimal. Logging only, at the `Pool.Borrow()` error path. Do not change
`Pool.Borrow()` retry logic, session pool sizing, or the SLO alert
expressions/thresholds in mctl-telegram-slo.yaml — that file's own comments
state the SLO doc deliberately omits a minimum-volume guard, and nothing
else observed in this window (canary, MCP tool calls, ArgoCD health)
indicates an unrelated regression.
