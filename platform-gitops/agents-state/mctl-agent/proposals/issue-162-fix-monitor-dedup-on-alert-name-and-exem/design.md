# Design: issue-162-fix-monitor-dedup-on-alert-name-and-exem

## Current state
- `internal/ticket/store.go` `FindDuplicate(ctx, tenant, service, ticketType)` selects the newest ticket with `tenant=? AND service=? AND type=? AND status NOT IN (resolved, suppressed)`, going through `s.rebind` (`?` becomes `$n` for Postgres; `Store.dialect` is set in `NewStore`).
- `FindRecentlyResolved(ctx, tenant, service, ticketType, alertName, window)` already keys on `alert_name=?`. Its doc comment explains why: `classifyAlert` collapses alert names into shared types, and an empty name matches blank-name tickets.
- `internal/monitor/alerthandler.go`:
  - `alertStore` interface declares `FindDuplicate(ctx, tenant, service, ticketType string)`.
  - `processAlert` gets `tType, severity := classifyAlert(alertName)`. For firing alerts it calls `h.store.FindDuplicate(ctx, tenant, service, tType)`. On a hit it calls `TouchWithFingerprint(existing.ID, a.Fingerprint)` and returns. Otherwise, if `h.FlapCooldown > 0`, it calls `FindRecentlyResolved(..., alertName, h.FlapCooldown)` and suppresses on a hit. Last, it creates the ticket with `AlertName: alertName, Severity: severity`.
  - `classifyAlert` returns `ticket.SeverityCritical` (`internal/ticket/ticket.go`) for `PodCrashLooping`/`KubePodCrashLooping` and `VaultSealed`, and `SeverityWarning` for everything else.
- Other `FindDuplicate` callers use a concrete `*ticket.Store` and create tickets without `AlertName`, so the stored name is `''`. They are `internal/monitor/poller.go` (`TypeArgoCDDegraded`) and `internal/monitor/github_webhook.go` (`TypeGitHubActionsFailed`).
- `cmd/agent/main.go` sets `alertHandler.FlapCooldown = cfg.AlertFlapCooldown` (`internal/config/config.go`).
- Resolve path: `ResolveByTenantService` scopes by fingerprint set membership plus `EndsAt`. With several open tickets of one type, a resolve only closes the ticket that carries the alert's fingerprint. Fingerprintless legacy tickets are the exception (`alert_fingerprint = ''` arm).
- Tests: `internal/ticket/store_test.go` (`TestStoreFindDuplicate`) and `internal/monitor/alerthandler_test.go` (`TestAlertHandlerDedup`, `TestAlertHandlerFlapCooldown`, `TestAlertHandlerFlapCooldownKeyedByAlertName`, `blockingStore` wrapping `FindDuplicate`). Both use `NewStore(ctx, ":memory:")`, which is SQLite only.

## Proposed solution
1. **Store.** Change the signature to `FindDuplicate(ctx, tenant, service, ticketType, alertName string)` and add `AND alert_name=?` to the WHERE clause, with `alertName` bound between `ticketType` and the status args. Exact equality gives the empty-matches-empty rule for free, the same rule `FindRecentlyResolved` uses. Update the doc comment to explain why the key includes the name, and point to `FindRecentlyResolved`. The query still goes through `s.rebind`, and the SQL stays portable across SQLite and Postgres.
2. **Interface and callers.**
   - `alertStore.FindDuplicate` gets the new parameter.
   - `processAlert` passes `alertName`.
   - `poller.go` and `github_webhook.go` pass `""`. This keeps their behaviour exactly as it is, because their tickets store an empty `alert_name`.
   - The test wrapper `blockingStore.FindDuplicate` is updated to the new signature.
3. **Critical bypass.** Change the cooldown guard to `if h.FlapCooldown > 0 && severity != ticket.SeverityCritical { ... }`. A critical alert skips the `FindRecentlyResolved` lookup entirely; no extra query and no suppression. (Running the lookup only to log a "critical alert bypasses flap cooldown" line was considered and dropped, since it costs a query for log output only.) Update the `FlapCooldown` field comment to say critical alerts are exempt.
4. The dedup touch/fingerprint path for true duplicates is unchanged.

Why this way: the change is the smallest one that matches the existing `FindRecentlyResolved` convention. It needs no schema change, because `alert_name` already exists (added through `ensureColumn`). Severity comes from the value already computed in `processAlert` and stored on the ticket, so what gets suppressed stays consistent with what the operator sees in notifications (`internal/notify/telegram.go` branches on `SeverityCritical`).

## Alternatives
- **Add a separate `FindDuplicateByAlertName` and keep the old method.** This avoids touching the poller and webhook callers, but it leaves the name-blind method available and creates two near-identical queries. Dropped: one signature with an explicit `""` at the non-AlertManager call sites is clearer and harder to misuse.
- **Match `alert_name IN (?, '')` so legacy blank-name tickets still absorb named alerts.** Dropped: this reintroduces the folding bug for any blank-name ticket and breaks the empty-matches-empty rule the issue asks for.
- **Make the cooldown bypass depend on the Prometheus `severity` label or a configurable severity set.** Dropped for now: the issue says "classified as critical", and `classifyAlert` is the classification used everywhere else. A config knob adds surface area nobody has asked for. Recorded as an open question.

## Platform impact
- **Migrations:** none. `alert_name TEXT NOT NULL DEFAULT ''` already exists. An index is optional and not added; open-ticket counts are small.
- **Backward compatibility:** `FindDuplicate` is internal (no external importers; the MCP/REST APIs do not expose it). Poller and GitHub webhook behaviour is unchanged. For AlertManager tickets, `alert_name` has always been populated.
- **Behaviour change / risks:**
  - More tickets: alerts that share a type now each open a ticket, so the pipeline may run more diagnoses or open more PRs for the same tenant/service. Mitigation: the existing `CountPRsInWindow` rate limit and the per-alert fingerprint scoping on resolve, which keeps these tickets independent.
  - Critical re-fires now notify every time. Only three alert names are critical today, and they are exactly the ones operators want to see.
- **Resource impact:** negligible. One extra equality predicate. Critical alerts skip one query.
- **Rollback:** revert the PR. No data to clean up; the extra tickets created in the meantime resolve normally.
