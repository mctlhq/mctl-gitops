# Design: incident-c571cbd8

## Diagnosis
`MctlTelegramSessionBorrowSlowBurn` is a multi-window SLO burn-rate alert
(platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml)
that fires when `mctl_telegram:session_borrow_errors:ratio_rate6h` — the ratio
of `Pool.Borrow()` calls with `result="error"` over `result=~"ok|error"`,
deliberately excluding `expired_idle`/`expired_absolute` TTL expirations —
exceeds 6% over a rolling 6h window (6x the 99% session-borrow-success
objective's error budget). It escalated with "no skill matched" because these
three SLO burn-rate rules were only recently ported into this cluster
(mctlhq/mctl-telegram#546/#555) and have no corresponding automated diagnostic
rule yet, unlike the operational alerts in mctl-telegram-ops.yaml, which all
carry a `runbook_url` anchor into mctl-telegram's docs/runbook.md.

This responder cannot query the underlying VictoriaMetrics series directly
(no metrics tool is available, only Loki logs and the mctl-gitops repo), and
the only log window it could read within the tool's output-size limit was the
trailing ~10 minutes of the 6h alerting window, all of which shows healthy,
successful MCP tool calls and canary probes — consistent with either a
resolved transient condition earlier in the window, or a burst under
concurrent load. The log excerpt in requirements.md shows one user (9980)
issuing a rapid sequence of MCP tool calls (get_messages/get_unread_messages
across multiple peer types) within about 90 seconds, i.e. concurrent session
activity of the kind that stresses a session/client pool.

mctl-telegram's own `mctl_telegram_pool_capacity` gauge is documented (in
mctl-telegram-ops.yaml) as reading -1 (uncapped) because `TELEGRAM_MAX_SESSIONS`
is unset, and the pool-capacity alerts are explicitly noted as inert while
this is the case — so pool saturation is presently unmonitored and cannot be
correlated against the historical error burst that tripped this SLO alert.
Separately, the pod's memory limit (256Mi, values.yaml) was right-sized on
2026-08-03 against a steady-state p95 of 42MB/24h; that sizing pass did not
account for burst concurrent session-borrow contention of the kind visible in
the log excerpt, and the MTProto handshake path is independently documented in
the same file as CPU/latency sensitive.

## Confidence: LOW
No direct evidence (metrics query, OOM/restart event, or a borrow-error log
line) confirms the root cause. The proposed fix below is a conservative,
low-risk headroom increase consistent with the one concrete gap this
responder could verify (memory sizing not accounting for burst concurrency),
not a confirmed fix for the specific error burst that tripped the alert. The
implementer should verify against current VictoriaMetrics data
(`mctl_sessions_borrow_total{result="error"}`, container memory/OOM history)
before or after applying, and treat this as a mitigation attempt rather than a
guaranteed resolution.

## Proposed Fix
File: `platform-gitops/services/labs/mctl-telegram/values.yaml`
Field: `resources.limits.memory`
Current value: `256Mi`
New value: `512Mi`

Leave `resources.requests.memory` (128Mi) and all CPU values unchanged — this
only raises the ceiling available during bursty concurrent session-borrow
activity, it does not change steady-state scheduling.

## Scope
Minimal. Only the single `resources.limits.memory` field in
`platform-gitops/services/labs/mctl-telegram/values.yaml` changes. No alert
rule, image tag, or other config is touched.
