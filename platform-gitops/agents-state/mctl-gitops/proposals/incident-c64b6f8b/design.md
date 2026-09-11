# Design: incident-c64b6f8b

## Diagnosis
`MctlTelegramSessionBorrowSlowBurn` is a multi-window burn-rate alert on
session-borrow latency/errors for the `mctl-telegram` service in tenant
`labs`. It escalated to this responder because no diagnostic skill exists yet
for this alert type (type=generic, analysis noted "no skill matched").

The service logs sampled at diagnosis time (canary probe runs and
base-service MCP tool calls, covering the most recent activity inside the
alert's 6h window) show only healthy ("ok") results, with canary end-to-end
duration consistently in the 1.4-1.6s range. No explicit session-pool errors,
timeouts, or borrow failures appear in this sample. This is consistent with
either:
(a) a genuine but low-rate/intermittent session-pool contention issue that
    only shows up in the underlying burn-rate metric and not in the small
    INFO-level log sample retrieved, or
(b) an alert threshold that is too sensitive relative to otherwise-healthy
    service behavior.

This responder has no access to a metrics/Prometheus query tool, so it
cannot directly inspect the `session_borrow` histogram/counter that backs
this alert. The diagnosis is therefore low confidence and the implementer
should confirm the branch above before editing any configuration.

## Confidence: LOW

## Proposed Fix
Two candidate remediations, gated on the implementer first checking the
actual `session_borrow` metric for tenant labs / service mctl-telegram over
the alert's 6h window:

1. If contention is confirmed (borrow latency/errors genuinely elevated):
   increase the Telegram client session-pool size and/or borrow timeout for
   the labs `mctl-telegram` deployment in
   `platform-gitops/services/labs/mctl-telegram/values.yaml` (pool-related
   env vars, or replica count if the pool is per-pod).
2. If the metric looks normal and the alert is oversensitive: relax the
   `MctlTelegramSessionBorrowSlowBurn` burn-rate thresholds in the
   AlertManager/PrometheusRule definition for mctl-telegram under
   `platform-gitops/` (rule file covering mctl-telegram alerts).

Do not guess which branch applies without checking the metric first — the
log evidence alone does not distinguish them.

## Scope
Minimal. Only touch the session-pool sizing/timeout fields (branch 1) or the
specific alert rule thresholds (branch 2) for this alert. Do not change
unrelated mctl-telegram configuration.
