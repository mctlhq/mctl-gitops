# Dedup on alert name and exempt critical alerts from flap cooldown

## Context
`AlertHandler.processAlert` (`internal/monitor/alerthandler.go`) has two gates that run before a ticket is created for a firing AlertManager alert. The dedup gate calls `Store.FindDuplicate(tenant, service, type)` (`internal/ticket/store.go`), which ignores `alert_name`. Because `classifyAlert` maps several distinct alert names onto one ticket type (`TenantCPUQuotaHigh`, `TenantMemoryQuotaHigh`, `CPUThrottlingHigh`, `ContainerOOMKilled`, `VaultSealed`, the `Node*` alerts all map to `TypeResourceLimit`; `PodCrashLooping` and `KubePodNotReady` both map to `TypePodCrashloop`), a new alert gets folded into any open ticket of the same type. That ticket is touched and no ticket is created, so a critical `VaultSealed` can disappear into an open warning-level `CPUThrottlingHigh` ticket. The flap-cooldown gate (`FindRecentlyResolved`, already keyed on `alert_name`) suppresses re-fires for every severity, which also hides critical alerts that re-fire shortly after resolving.

This proposal adds `alert_name` to the dedup key, using the same rule `FindRecentlyResolved` uses: an empty name matches only an empty name. It also makes alerts that `classifyAlert` labels `critical` bypass the flap cooldown. Source: audit finding OBS-008.

## User stories
- AS a platform operator I WANT every distinct alert to get its own ticket SO THAT a new, more serious alert is not hidden inside an unrelated open ticket of the same type.
- AS a platform operator I WANT critical alerts that re-fire after a short resolution to open a ticket SO THAT I see a recurring critical incident.
- AS a platform operator I WANT warning-level flapping alerts to stay suppressed SO THAT Telegram is not flooded by threshold toggling.

## Acceptance criteria (EARS)
- WHEN a firing alert arrives and an open ticket exists with the same tenant, service and type but a different `alert_name`, THE SYSTEM SHALL create a new ticket for the alert and SHALL NOT touch the existing ticket.
- WHEN a firing alert arrives and an open ticket exists with the same tenant, service, type and `alert_name`, THE SYSTEM SHALL treat it as a duplicate, call `TouchWithFingerprint` on that ticket and SHALL NOT create a ticket (same as today).
- WHEN `Store.FindDuplicate` is called with an empty alert name, THE SYSTEM SHALL match only open tickets whose `alert_name` is empty. Poller (`TypeArgoCDDegraded`) and GitHub webhook (`TypeGitHubActionsFailed`) dedup therefore keep working as they do today.
- IF a firing alert is classified with severity `critical` THEN THE SYSTEM SHALL skip the `FindRecentlyResolved` flap-cooldown check and create the ticket, even when the same alert resolved within `FlapCooldown`.
- IF a firing alert is classified with a severity other than `critical` and the same alert resolved within `FlapCooldown` THEN THE SYSTEM SHALL suppress ticket creation (same as today).
- WHILE `FlapCooldown` is zero THE SYSTEM SHALL create tickets as it does today, regardless of severity.
- THE SYSTEM SHALL keep using `s.rebind` for the updated `FindDuplicate` query, so it works on both the SQLite and the Postgres dialect.
- THE SYSTEM SHALL pass `go test ./...` and `go vet ./...`, and each new test SHALL fail when its production change is reverted.

## Out of scope
- Changing how `classifyAlert` maps alert names to types or severities, or reading the Prometheus `severity` label instead of `classifyAlert`'s severity.
- Changing how tickets are resolved (`ResolveByTenantService`, `reconcileWithAlertManager`, stale-ticket GC).
- Merging or migrating tickets already open with an empty `alert_name`.
- Adding a live Postgres test harness.
- Changing how the pipeline handles several open tickets for the same tenant/service/type, for example PR rate limiting.

## Open questions
- What counts as "critical": this proposal uses the severity returned by `classifyAlert`, which today means `PodCrashLooping`/`KubePodCrashLooping` and `VaultSealed`. This is also what is stored on the ticket. The Prometheus `severity` label is not consulted.
- The issue says both SQL dialects are "covered by the existing test setup", but `internal/ticket` tests run on SQLite (`:memory:`) only. This proposal does not build a Postgres harness. It covers the Postgres side with a dialect-level `rebind` assertion on the new query's placeholder count, and otherwise relies on the query using portable SQL only.
- Transition: tickets opened before this change always stored `alert_name` from AlertManager (column default `''` only applies to non-AlertManager sources). An open AlertManager ticket with an empty `alert_name` would no longer absorb named alerts. We expect this to be rare and accept it.
