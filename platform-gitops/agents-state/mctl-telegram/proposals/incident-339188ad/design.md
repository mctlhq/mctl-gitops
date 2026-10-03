# Design: incident-339188ad

## Diagnosis
`MctlTelegramSessionBorrowSlowBurn` is a burn-rate alert on the latency of
borrowing (acquiring) a Telegram client session from mctl-telegram's session
pool, tripped at 6x its threshold sustained over a 6-hour window — a slow,
low-grade degradation rather than a hard failure spike, which is why mctl-agent
had no matching skill and escalated it as `type=generic`. Service logs for the
`labs` mctl-telegram base-service show a recurring `"idle telegram client,
closing"` event with `idle` consistently around 600045245290ns (~600s / 10
minutes) — the service evicts a user's Telegram client session after roughly
10 minutes of inactivity. Any subsequent MCP tool call or canary probe that
arrives after an eviction has to pay the cost of establishing a fresh Telegram
client session before it can serve the request, instead of reusing an
already-authenticated warm session. Given the observed traffic (canary probes
roughly every 5-10 minutes, interactive tool calls in bursts with gaps between
them), sessions are plausibly being evicted between usage bursts often enough
that a meaningful fraction of borrows pay the cold-start cost, which would
gradually push the borrow-latency burn rate up over a 6-hour window without
ever producing a single hard error — consistent with the alert firing as a
slow burn.

## Confidence: LOW
The container stdout logs available to this responder show the idle-eviction
event and its ~600s interval, but not the underlying session-borrow-duration
metric/histogram that actually drives the alert, so the causal link between
the eviction interval and the burn-rate alert is inferred, not directly
observed. It is also not confirmed from gitops alone whether the idle timeout
is an env-configurable value or a constant in the mctl-telegram Go source —
the implementer should verify before applying.

## Proposed Fix
Increase the Telegram client idle-eviction timeout used by mctl-telegram's
session pool (currently ~600s / 10 minutes, per the `"idle telegram client,
closing"` log line) to a larger value, e.g. 1800s (30 minutes), so that
sessions used at the observed polling/canary cadence stay warm and avoid
repeated cold-start borrow costs.
- If the timeout is exposed as an environment variable in the mctl-telegram
  Helm values (e.g. something like `TELEGRAM_CLIENT_IDLE_TIMEOUT_SECONDS`),
  raise it there in `platform-gitops/services/labs/mctl-telegram/values.yaml`
  (or the equivalent env block) and let ArgoCD roll it out.
- If it is a hardcoded constant in the Go client-pool logic instead, this
  proposal is filed against `mctl-telegram` rather than `mctl-gitops` so the
  implementer can bump the constant in source and cut a release.

## Scope
Minimal. Only touch the idle-eviction timeout for the Telegram client session
pool. Do not change unrelated pool sizing, auth flow, or retry logic.
