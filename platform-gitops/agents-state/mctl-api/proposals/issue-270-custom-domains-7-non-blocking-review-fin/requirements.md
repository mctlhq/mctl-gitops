# Custom domains: close the 7 non-blocking review findings from #269

## Context

`mctl-api#269` made mctl-api the system of record for custom domains
(`internal/domains`, `internal/api/handlers_domains.go`,
`toolRemoveCustomDomain` in `internal/mcp/server.go`). It went through six
rounds of review; every P1/P2 was fixed inline, but seven P3s were
deliberately deferred. Issue #270 collects them so they are not lost.

The seven items fall into four groups: (a) two remaining case-folding gaps
where the mixed-case normalization pass of #269 stopped short — the `team`
argument passed to `Executor.Submit` in `triggerRemoveCustomDomain`, and the
no-`?team=` fall-through in `resolveDomainForMutation`; (b) a missing
functional index, because `ListByTeam`'s `lower(team)=lower($1)` made the
existing `custom_domains_team (team, service)` index unusable and nothing
replaced it; (c) an ambiguous `ingress_cleanup: "skipped"` response value
that conflates a genuine no-op with two very different "cleanup did not
run" conditions, one of which is a production misconfiguration that
silently orphans real ingress; and (d) three test-quality gaps (untested
`listErr != nil` branch in the MCP tool's fallback note, a sibling test that
asserts only a submission count, and a stale doc comment). None of these is
a live outage; together they are the difference between "the case-folding
pass is complete and observable" and "it is complete in four of six places
and an operator cannot tell a no-op from a failure."

## User stories

- AS a tenant owner with a legacy mixed-case `custom_domains` row I WANT
  every read and mutation path to resolve my row the same way SO THAT
  `DELETE /api/v1/domains/{id}` without `?team=` behaves identically to the
  same call with `?team=`.
- AS a platform operator I WANT `ingress_cleanup` in the delete response to
  distinguish "nothing needed cleaning" from "cleanup could not run" SO THAT
  I can page on the second without alerting on the first.
- AS a platform operator I WANT `GET /api/v1/domains?team=X` to use an index
  SO THAT the list endpoint does not degrade into a sequential scan as the
  registry grows.
- AS an mctl-api maintainer I WANT the workflow label on a
  `remove-custom-domain` submission to carry the same normalized team as the
  workflow parameters SO THAT label-based workflow queries are not split
  across casings.
- AS an mctl-api maintainer I WANT the untested branches and the stale test
  doc comment fixed SO THAT the next change to this code is protected by
  tests that actually cover the production failure mode.

## Acceptance criteria (EARS)

Case folding

- WHEN `triggerRemoveCustomDomain` calls `h.opts.Executor.Submit` THE SYSTEM
  SHALL pass the normalized team (`normalizeIdentifier(d.Team)`, the same
  value already used for `params["team_name"]`) as the `team` argument.
- WHEN `resolveDomainForMutation` reaches the no-`?team=` fall-through for a
  non-admin caller THE SYSTEM SHALL evaluate
  `user.HasTenantAccess(normalizeIdentifier(d.Team))`.
- WHILE a legacy row is stored with `team = "Labs"` THE SYSTEM SHALL resolve
  it identically for a caller in group `labs` whether or not `?team=` is
  supplied.
- IF a stored team value is not a valid identifier after normalization THEN
  THE SYSTEM SHALL still reject it at `Registry.ValidateInput` before
  `Submit`, exactly as today (normalization must not weaken that gate).

Index

- WHEN the domains store initializes THE SYSTEM SHALL ensure a functional
  index `custom_domains_team_lower ON custom_domains (lower(team),
  lower(service))` exists.
- IF creating that index fails THEN THE SYSTEM SHALL log a warning and
  continue serving (index absence is a performance regression, not a
  startup failure), mirroring `internal/audit/postgres.go`.
- WHEN `ListByTeam` runs against a Postgres instance with the index present
  THE SYSTEM SHALL return the same rows as before the index existed
  (behaviour-neutral change).

Cleanup status disambiguation

- WHEN `DeleteDomain` skips teardown because the row's status is neither
  `active`, `verified` nor `failed` THE SYSTEM SHALL respond with
  `"ingress_cleanup": "not-required"`.
- WHEN `DeleteDomain` cannot run teardown because `Executor` or `Registry`
  is nil THE SYSTEM SHALL respond with `"ingress_cleanup": "unavailable"`.
- WHEN `DeleteDomain` cannot run teardown because `remove-custom-domain` is
  absent from the operations registry THE SYSTEM SHALL respond with
  `"ingress_cleanup": "misconfigured"` and SHALL log at error level (not
  warn), because real ingress may be left behind.
- WHEN teardown is submitted THE SYSTEM SHALL keep responding
  `"ingress_cleanup": "workflow-submitted"` together with `workflow_name`,
  unchanged.
- WHILE any of these outcomes is returned THE SYSTEM SHALL still return HTTP
  200 with `"status": "deleted"` and SHALL still delete the row, preserving
  #269's contract that only a submission *error* keeps the row.

Tests and comments

- WHEN the MCP `mctl_remove_custom_domain` tool's list call fails outright
  (transport error or >=400 response, both surfaced as a non-nil error by
  `doRequest`) THE SYSTEM SHALL fall back to the operations execute path and
  SHALL include the "could not consult the domains registry" note in the
  result text; this branch SHALL be covered by a test.
- WHEN `TestDeleteDomain_FailedRowStillSubmitsTeardown` runs THE SYSTEM
  SHALL assert the submitted params (`team_name`, `service_name`, `domain`)
  and `ingress_cleanup == "workflow-submitted"`, matching its three sibling
  tests.
- WHEN a reviewer reads `TestDeleteDomain_SkipsTeardownForPendingRow`'s doc
  comment THE SYSTEM SHALL describe the actual gate (pending-only skip;
  `failed` is deliberately NOT skipped) rather than the stale
  "never reached StatusVerified/StatusActive" wording.
- WHEN `ListByTeam` is exercised against a genuinely mixed-case stored row
  (inserted via `Store.Create` directly, bypassing `AddDomain`'s
  normalization) THE SYSTEM SHALL return that row for a lowercase `team`
  query.

## Out of scope

- Any data migration that rewrites existing mixed-case `team`/`service`
  values to lowercase. #269 chose case-insensitive comparison over a
  migration; this proposal keeps that decision.
- Adding a `CHECK` constraint or `CITEXT` column type to `custom_domains`.
- Changing the delete ordering contract (submit-then-delete) or the
  inverse-failure window documented on `DeleteDomain`.
- Changing which statuses are eligible for teardown.
- Adding domains paths to `internal/openapi/openapi.yaml` (the domains
  routes are not described there today; documenting the whole surface is a
  separate piece of work).
- Any change to the `add-custom-domain` workflow or the Argo workflow
  templates in mctl-gitops.

## Open questions

- Should the now-unused `custom_domains_team (team, service)` index be
  dropped once `custom_domains_team_lower` exists? Proceeding with: keep
  it. The table is tiny, `DROP INDEX` from application startup code is
  riskier than a redundant index, and a future exact-match query would still
  use it. Recorded for a later cleanup.
- Exact vocabulary for the disambiguated `ingress_cleanup` values. The issue
  suggests `not-required` vs `unavailable`; proceeding with three values —
  `not-required`, `unavailable`, `misconfigured` — because item 4 explicitly
  names three distinct outcomes and the third is the one worth paging on.
- Whether any consumer outside this repo parses `ingress_cleanup:
  "skipped"`. A repo-wide grep finds it only in
  `internal/api/handlers_domains.go` and its tests; the MCP tool relays the
  delete response body verbatim without parsing it. Proceeding on the
  assumption that no machine consumer depends on the literal `"skipped"`,
  and calling it out in the PR body.
