# Reconcile automation/v1 contract with the owner-reviewed AMEND gates before automation-api-store

## Context

mctl-api#948 defined the `automation/v1` contract. Its original, unamended proposal was approved
and implemented in merged PR #950 (`docs/automation-contract.md` and `internal/automation/contract/**`).
The owner later had three proposal amendments reviewed in mctl-gitops#2452, but that PR was never
merged before the #948 approval, so the merged code does not include them. This issue (a re-file
of #955, whose DevLoop completed with no live grant) asks for a corrective, contract-only change
that makes the merged contract and its deterministic tests satisfy those amendments. It does not
edit the #948 `.status.yaml`, reopen DevLoop `dev-loop-mctlhq-mctl-api-948`, or treat #2452 as
consumed by the #948 approval.

The gaps on `main` today:
- `OccurrenceKey` in `internal/automation/contract/occurrence.go` hashes `definition_version`, so a
  replay across an update yields a new occurrence. The pipe-joined input is not length-prefixed.
- `OccurrenceSet.Claim` returns `automation_occurrence_duplicate` (409) for a normal retry.
- `work_items_tenant_external_key_open` (`internal/workitems/store.go`) only covers open items, and
  child rows are `ON DELETE CASCADE`, so there is no durable dedupe after closure or cleanup.
- Section 7 of the doc treats Commerce (`internal/commerce/budget.go`: payer account,
  `monthly_limit_minor`, `per_request_max_minor`) as the per-run/day/tenant usage authority.
- `support.diagnostic-followup.v1` allows a 24h TTL while `AgentScopeSupport` tokens are
  `DefaultTTL: 10m, MaxTTL: 1h` (`internal/auth/agent_scope.go`).
- `run` has no request schema. 403/404 precedence and producer event identity have no negative
  tests. `Etc/GMT+N` zones pass the offset-only check in `trigger.go`.

All new behaviour is contract-only: `isolated-model` or `unknown`. None of it is live enforcement.

## User stories

- AS the platform owner I WANT the merged contract to match the amendments I reviewed SO THAT
  `automation-api-store` is built against the correct target.
- AS the future `automation-api-store` implementer I WANT a normative, tested occurrence-claim
  model SO THAT I can't ship dedupe that breaks on retention or crash.
- AS a tenant owner I WANT Support follow-ups to need my live consent and a fresh token each time
  SO THAT a 24h definition never becomes a 24h credential.
- AS a reviewer I WANT each statement tagged with a claim class SO THAT I can tell modelled rules
  from enforced ones.

## Acceptance criteria (EARS)

### Occurrence identity
- WHEN an occurrence key is derived THE SYSTEM SHALL hash a domain-separated
  (`mctl.automation.occurrence.v1`), length-prefixed encoding of `(au_id, trigger_kind,
  occurrence_source_id)`, and SHALL NOT include the definition version.
- WHEN the trigger is `at` or `schedule` THE SYSTEM SHALL use the scheduled instant, normalised to
  UTC RFC 3339 with nanosecond precision, as the source ID.
- WHEN the trigger is `event` or `dependency` THE SYSTEM SHALL use the authenticated `(producer,
  event_type, stable_producer_event_id)` and SHALL NOT use any per-delivery or transport ID.
- WHEN the trigger is manual THE SYSTEM SHALL use the server-bound `(principal, tenant,
  caller_idempotency_key)` and SHALL NOT accept a client-supplied occurrence ID.
- IF any source component is empty THEN THE SYSTEM SHALL refuse with `automation_invalid`.
- WHEN the same occurrence is claimed again with an identical binding THE SYSTEM SHALL return the
  original `wi_` and admitted version with `replayed: true`. It SHALL NOT mint a second `wi_`,
  reserve budget again, or cause another side effect.
- IF an occurrence key is reused with a different binding (tenant, `au_`, or request hash) THEN THE
  SYSTEM SHALL refuse with the new typed code `automation_occurrence_conflict` (409).
- THE SYSTEM SHALL keep `automation_occurrence_duplicate` in the vocabulary, with its meaning
  unchanged (codes are only ever added), and SHALL stop emitting it for an identical replay.
- WHEN an occurrence is admitted THE SYSTEM SHALL record the admitted definition version on the
  claim, separately from the key. The `automation-run` view keeps `definition_version` as that
  admitted version.

### Durable claim (isolated model, gate for automation-api-store)
- THE SYSTEM SHALL specify an occurrence claim that is unique on `(tenant, au_id, occurrence_key)`
  and maps to `wi_id`, `admitted_version`, `status` (`claimed|bound|closed|tombstoned|failed`) and a
  request hash.
- WHEN two claims race for one key THE SYSTEM SHALL mint at most one `wi_`. The model is a single
  critical section and is tested under `-race`.
- IF the claim source is unavailable THEN THE SYSTEM SHALL fail closed with
  `automation_authority_unavailable` and mint nothing.
- WHEN the WorkItem closes or its history is cleaned up THE SYSTEM SHALL keep a tombstone for at
  least the source replay horizon, and a replay inside the horizon SHALL return `replayed: true`
  without minting.
- WHEN reconciliation finds a `claimed` row with no `wi_` (a crash between claim and mint) THE
  SYSTEM SHALL bind it to an existing WorkItem found by `external_key`, or mark it `failed`. It
  SHALL never mint during reconciliation.
- THE SYSTEM SHALL state in `docs/automation-contract.md` section 12 that `automation-api-store`
  is hard-gated on implementing this claim durably, and that this issue does not approve that
  slice.

### Usage authority
- THE SYSTEM SHALL document Commerce payer/payment limits (monthly, per-request) as distinct from
  inference/FinOps usage metering with per-run, per-day and per-tenant ceilings, and SHALL mark the
  usage authority `unknown`.
- IF the usage authority is unknown, or is only Commerce payment, THEN `Decide` SHALL deny with
  `automation_authority_unavailable`, whatever the headroom values.
- THE SYSTEM SHALL specify reservation, settlement and release as idempotent per occurrence key,
  in the contract text only.

### Support consent and token
- WHILE `support.diagnostic-followup.v1` is not separately authorized THE SYSTEM SHALL keep it
  registered and schema-valid, absent from the enabled allowlist, and refused with
  `automation_trigger_unsupported`.
- THE SYSTEM SHALL state that a definition TTL of up to 24h never extends a support run token past
  `AgentScopeSupport.MaxTTL` (1h).
- WHEN a Support fire is evaluated THE SYSTEM SHALL require all of: live tenant-owner consent that
  was independently verified, and a token freshly minted for this fire through a separately
  approved path, unexpired, with TTL at most 1h, not self-minted by an agent or service, and not
  authorized by `auth_ref` presence alone. Otherwise it SHALL refuse with
  `automation_support_constraint`.
- THE SYSTEM SHALL NOT assume mctl-api#901 is approved.

### Manual run
- THE SYSTEM SHALL add `automation-manual-run-request.v1` (JSON Schema) with an opaque caller
  `idempotency_key` and `additionalProperties: false`. A client-supplied `occurrence_key`,
  `principal`, `tenant` or `au_id` SHALL be refused with `automation_server_owned_field`.
- WHEN a manual request is replayed with the same `(principal, tenant, au_id, idempotency_key)` and
  the same body THE SYSTEM SHALL return the same occurrence with `replayed: true`. With a different
  body it SHALL refuse with `automation_idempotency_key_reused` (409).
- WHEN the same caller key is used by a different principal, tenant or `au_` THE SYSTEM SHALL
  derive a different occurrence, so there is no cross-principal collision.
- WHILE manual execution is not gated on THE SYSTEM SHALL refuse execution with
  `automation_trigger_unsupported`.

### Authorization and templates
- IF the caller is unlinked THEN THE SYSTEM SHALL return 403 `automation_identity_unlinked` before
  any resource lookup, for every existence, owner and tenant combination.
- WHEN an authenticated caller targets an absent, foreign-owner or foreign-tenant resource THE
  SYSTEM SHALL return a byte-identical 404 body.
- THE SYSTEM SHALL scope create idempotency by `(authenticated principal, tenant,
  idempotency_key)`.
- THE SYSTEM SHALL separate the template registry (`LookupTemplate`) from the enabled-template
  allowlist (`TemplateEnabled`).

### Toolchain finding and P3
- WHEN the tests run on the repo toolchain (`go.mod` `go 1.26.11`) THE SYSTEM SHALL test that
  `time.Parse(time.RFC3339, ...)` accepts fractional-second instants and that loop variables are
  per iteration. The Agy `FAIL:P2` is recorded as not reproduced, based on that evidence.
- IF a zone is a GMT-family zone with a numeric suffix (`Etc/GMT+2`, `Etc/GMT-14`, `Etc/GMT0`,
  `GMT0`, `GMT+0`) THEN THE SYSTEM SHALL refuse it with `automation_invalid`. `UTC`, `Etc/UTC`,
  `GMT`, `Etc/GMT` and named IANA zones stay accepted.

### Scope guard
- THE SYSTEM SHALL change only `docs/automation-contract.md` and `internal/automation/contract/**`,
  including its schemas, fixtures and tests.
- THE SYSTEM SHALL add no production importer of `internal/automation/contract`.

## Out of scope

- Any REST route, MCP tool, OpenAPI entry, DB table or migration, Temporal Schedule, worker,
  feature flag, Helm or GitOps change, or release activation.
- Enabling `support.diagnostic-followup.v1`, minting support tokens, or approving mctl-api#901.
- Implementing `automation-api-store` or any later slice. This issue does not approve them.
- Editing the #948 `.status.yaml`, reopening its DevLoop, or merging mctl-gitops#2452.
- Choosing the real usage-metering authority.

## Open questions

- mctl-gitops#2452's diff was not readable from this run. The implementer must do the
  section-by-section comparison against #2452 and #950 in the PR description, and must adjust if
  #2452 words a rule differently from this proposal.
- Tombstone horizon value: proposed default is the maximum of 30 days and the source replay
  horizon (the GitHub webhook redelivery window is `unknown`). The owner should confirm.
- New code `automation_occurrence_conflict` versus repurposing `automation_occurrence_duplicate`.
  This proposal adds the new code to honour "codes are only added; meanings never change".
- The issue cites `go 1.26.10`, but `go.mod` on main says `go 1.26.11`. Same semantics; the
  reproduction uses 1.26.11.
- Whether to tighten the `instant` schema to a strict RFC 3339 pattern. Go accepts a comma decimal
  separator and more than 9 fractional digits (truncated). This proposal only tests and documents
  that behaviour and does not change acceptance.
