# Auto-resolve stale `analyzing` and `fix_proposed` incidents

## Context

`mctl-agent` runs an in-process stale-ticket garbage collector in
`internal/monitor/poller.go:224-274` (`resolveStale()`). Today it only resolves
tickets in `StatusOpen` after `AUTO_RESOLVE_STALE_AFTER` (default 24h). Tickets
that progress to `StatusAnalyzing` (skill-pipeline picked them up) or
`StatusFixProposed` (agent opened a PR) are never TTL'd by this GC.

In production this gap causes incidents to pile up indefinitely. Concrete
examples observed on 2026-05-06 (six open incidents in the daily Telegram
digest):

- Four ovk/smoke* incidents in `analyzing` since 2026-05-04 — synthetic
  Telegram-routing test alerts; the underlying services never existed, so
  AlertManager never sent a `resolved` webhook.
- One ovk/ovk-openclaw-base-service in `analyzing` since 2026-05-03 — the
  pod was healthy again within minutes after a rollback, but no
  `resolved` webhook arrived.
- One admins/admins-openclaw-base-service `resource_limit` from 2026-05-05
  — transient throttling, service healthy now.

All six had to be closed by hand via `mctl_resolve_incident`. The
`StatusOpen`-only TTL did not catch any of them because every one had
already been picked up by a skill and moved to `analyzing`.

This proposal — Phase 1 of a three-phase incident auto-cleanup track —
extends the existing `resolveStale()` GC to cover `StatusAnalyzing` and
`StatusFixProposed`, with separate (longer) thresholds appropriate to each
state. Phase 2 (active AlertManager reconciliation) and Phase 3 (orphan
service pruning) are tracked as separate proposals.

## User stories

- AS an on-call SRE I WANT incidents stuck in `analyzing` for >48 hours to
  auto-resolve SO THAT the daily digest reflects current platform health
  instead of historical noise.
- AS a platform engineer I WANT incidents whose proposed fix PR was never
  merged within 7 days to auto-resolve SO THAT abandoned remediation
  attempts do not pollute the open-incident list forever.
- AS an operator I WANT each auto-resolution to record the GC reason in
  the ticket's analysis field SO THAT I can distinguish operator-driven
  resolutions from automatic cleanup when auditing.

## Acceptance criteria (EARS)

- WHEN a ticket has `status = analyzing` and `updated_at` is older than
  `AUTO_RESOLVE_ANALYZING_AFTER`, THE SYSTEM SHALL transition it to
  `resolved` and append `Auto-resolved by stale TTL GC (status=analyzing,
  age=<X>h, threshold=<Y>h)` to its analysis field.
- WHEN a ticket has `status = fix_proposed` and `updated_at` is older than
  `AUTO_RESOLVE_FIX_PROPOSED_AFTER`, THE SYSTEM SHALL transition it to
  `resolved` with the analogous reason string.
- WHEN a ticket has `status = open` and is older than
  `AUTO_RESOLVE_STALE_AFTER`, THE SYSTEM SHALL continue to behave exactly
  as before this change (no regression in existing eligibility filters
  for type and source).
- WHEN `AUTO_RESOLVE_ANALYZING_AFTER` is unset, THE SYSTEM SHALL default
  to 48h. WHEN `AUTO_RESOLVE_FIX_PROPOSED_AFTER` is unset, THE SYSTEM
  SHALL default to 168h (7d).
- WHILE the poller is running, THE SYSTEM SHALL run the new
  status-specific TTL passes on every poll cycle, gated by the same
  ticket-type and source allow-lists used by the existing `StatusOpen`
  pass.
- IF an environment value is malformed (e.g. `12hours`), THE SYSTEM SHALL
  fail the process at startup with a clear error, matching the existing
  `AUTO_RESOLVE_STALE_AFTER` parsing behaviour.

## Out of scope

- Active reconciliation against the AlertManager API (Phase 2 — separate
  proposal).
- Pruning of incidents whose underlying service no longer exists (Phase 3
  — separate proposal).
- Adding Prometheus metrics for cleanup counts (mctl-agent does not yet
  wire `prometheus/client_golang`; this is tracked separately).
- Backfilling old `analyzing` / `fix_proposed` tickets — the new GC will
  pick them up on its first cycle after deploy.
- Changing the existing `AUTO_RESOLVE_STALE_AFTER` semantics or default.
- Telegram or UI notifications about auto-resolutions — log line is
  sufficient for now.
