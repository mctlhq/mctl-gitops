# Auto-resolve incidents whose underlying service no longer exists

## Context

Phase 1 of the incident auto-cleanup track (mctl-agent#11, shipped in
1.8.0) extended the stale-ticket TTL GC to cover `StatusAnalyzing` and
`StatusFixProposed` in addition to `StatusOpen`. That closes the
"AlertManager never sent a `resolved` webhook" gap on a 24h–7d horizon.

It does not close the **synthetic / orphaned alert** gap: alerts whose
underlying `(tenant, service)` does not (and may never have) existed
from the platform's perspective. The 2026-05-06 triage uncovered four
such incidents in a single batch — `ovk/smoke`, `ovk/smoke-after`,
`ovk/smoke-bot`, `ovk/verify-routing-1777932562` — synthetic Telegram
routing tests that fired alerts into AlertManager and stayed in the
incident list for 48+ hours because the source pods never existed and
AlertManager never sent a `resolved` webhook.

The Phase 1 TTL would have eventually swept those at 48h, but the
fingerprint of the noise — `(tenant, service)` does not exist — is
strong enough to act on much earlier. mctl-agent already enumerates all
deployed services on every poll cycle via `mctlclient.ListServices()`
(`internal/monitor/poller.go:101`); we can reuse that list and resolve
any open ticket whose `(tenant, service)` is not in it after a short
grace window.

This is Phase 3 of the three-phase track. Phase 2 (active AlertManager
reconciliation by fingerprint) remains a separate proposal.

## User stories

- AS an on-call SRE I WANT incidents created from synthetic / smoke
  alerts to auto-resolve within an hour SO THAT they do not accumulate
  in the daily Telegram digest while I deal with real incidents.
- AS a platform engineer I WANT incidents whose `(tenant, service)` was
  retired or never deployed to auto-resolve SO THAT the open-incident
  list reflects the current shape of the platform.
- AS an operator I WANT each orphan-pruning resolution to clearly state
  that the underlying service does not exist SO THAT I can distinguish
  this case from a genuinely transient resolution.

## Acceptance criteria (EARS)

- WHEN the poller's most recent `ListServices()` call **succeeded** (i.e.
  the service inventory is fresh), AND a ticket has `(tenant, service)`
  that is not present in that inventory, AND `updated_at` is older than
  `AUTO_RESOLVE_ORPHAN_AFTER`, THE SYSTEM SHALL transition the ticket to
  `resolved` and append `Auto-resolved: service does not exist (likely
  synthetic / orphaned alert)` to its analysis field.
- WHEN the most recent `ListServices()` call **failed** (i.e. the
  inventory is stale), THE SYSTEM SHALL skip the orphan-pruning pass for
  that cycle and SHALL NOT resolve any tickets on the basis of presumed
  absence.
- WHILE a ticket is in `StatusFixApplied`, `StatusResolved`, or
  `StatusSuppressed`, THE SYSTEM SHALL NOT consider it for orphan
  pruning.
- WHEN `AUTO_RESOLVE_ORPHAN_AFTER` is unset, THE SYSTEM SHALL default to
  1 hour. WHEN it is set to a value `<= 0`, THE SYSTEM SHALL skip the
  orphan-pruning pass entirely (operator opt-out).
- WHEN a ticket has source `SourceManual` (operator-initiated, no
  recurring signal), THE SYSTEM SHALL NOT orphan-prune it — manual
  tickets are kept until explicitly resolved.
- WHEN the orphan-pruning pass is enabled, THE SYSTEM SHALL run it on
  every poll cycle, after the existing stale-TTL pass.
- WHEN the implementation reuses `mctlclient.ListServices()` results
  already fetched by `pollDegraded()`, THE SYSTEM SHALL NOT issue a
  second HTTP call for orphan pruning.

## Out of scope

- Active reconciliation against the AlertManager API by fingerprint
  (Phase 2 — separate proposal).
- Pruning by k8s namespace/pod existence directly (mctl-api delegation
  is sufficient and avoids adding `k8s.io/client-go` to mctl-agent).
- Notifying Telegram about each orphan resolution — log line is enough.
- Caching `ListServices()` between cycles. The data is already fetched
  every cycle by `pollDegraded()`; reuse that, do not introduce a
  separate cache.
- Backfilling currently-stuck synthetic tickets — the new pass will pick
  them up on its first cycle after deploy.
