# Reconcile automation/v1 contract with the owner-reviewed amendments before automation-api-store

## Context

mctl-api#948 defined the `automation/v1` contract. Its original, unamended proposal was approved
(`aar_cd3746f1e9d640e5bdb7237c4a567154`, digest `sha256:4a64221b...`) and shipped in merged PR
mctl-api#950 as `docs/automation-contract.md` plus the isolated-model package
`internal/automation/contract`. Three owner-requested amendments (mctl-gitops#2452) were reviewed
but never merged before that approval. They are therefore not part of what #948 approved. This
issue is a new approval boundary. It corrects the merged contract code and document so that they
satisfy those amendments. It does not edit the #948 `.status.yaml`, does not reopen the completed
DevLoop `dev-loop-mctlhq-mctl-api-948`, and does not treat #2452 as consumed.

The merged contract has these gaps:
- The occurrence key includes the definition version, so a replay after an update creates a new
  occurrence.
- A normal retry returns `automation_occurrence_duplicate` (409) instead of idempotent success.
- No durable claim exists once the WorkItem closes.
- The budget wording points at Commerce payer/month payment limits as if they were per-run, per-day
  and per-tenant usage ceilings.
- The Support template's 24h lifetime is never reconciled with the 10m default / 1h max support
  token.
- `run` has no request schema.
- The 403/404 anti-oracle rules and producer-event identity have no negative tests.

Everything in this proposal is contract only (`isolated-model` or `unknown`). Nothing becomes live
enforcement.

## User stories

- AS the platform owner I WANT the merged `automation/v1` contract to match the amendments I
  reviewed SO THAT `automation-api-store` is built against correct dedupe, usage and consent rules.
- AS the future `automation-api-store` implementer I WANT a normative, tested occurrence-claim
  model and a hard gate SO THAT I cannot ship a store that loses dedupe after WorkItem cleanup.
- AS a tenant owner I WANT Support follow-ups to stay disabled and require my live consent plus a
  freshly minted token for every fire SO THAT a 24h template never extends a 1h support token.
- AS a security reviewer I WANT deterministic negative tests for 403/404 precedence, create
  idempotency isolation and event identity SO THAT existence oracles and cross-principal replays
  are caught.

## Acceptance criteria (EARS)

Occurrence identity
- WHEN an occurrence key is derived THE SYSTEM SHALL compute it as `"occ_"` followed by lowercase
  hex of SHA-256. The hash input is a domain-separated (`"mctl.automation.occurrence.v1"`),
  length-prefixed encoding of `(au_id, trigger_kind, occurrence_source_id)`. The definition
  version SHALL NOT be part of the hash input.
- WHEN the trigger kind is `at` or `schedule` THE SYSTEM SHALL use the scheduled instant,
  normalised to UTC (RFC 3339, nanosecond precision), as `occurrence_source_id`.
- WHEN the trigger kind is `event` or `dependency` THE SYSTEM SHALL build `occurrence_source_id`
  from the authenticated `(producer, event_type, stable_producer_event_id)`, each length-prefixed.
  Per-delivery or transport identifiers SHALL NOT be part of it.
- WHEN the trigger kind is `manual` THE SYSTEM SHALL build `occurrence_source_id` from the
  server-bound `(principal, tenant, manual_request_key)`. No client-supplied value SHALL be used
  directly as the occurrence key.
- WHEN an occurrence is admitted THE SYSTEM SHALL record the admitted definition version on the
  claim, separately from the key.
- WHEN the same occurrence is claimed again with an identical binding THE SYSTEM SHALL return the
  original `wi_id`, admitted version and status with `replayed: true`. It SHALL NOT create a
  second `wi_`, a second budget reservation or a side effect.
- IF the same occurrence key is claimed with a conflicting binding (different tenant, `au_id` or
  request hash) THEN THE SYSTEM SHALL return a typed 409 `automation_occurrence_conflict`. Nothing
  SHALL be created.

Durable occurrence claim (isolated model only)
- THE SYSTEM SHALL specify a claim relation `(tenant, au_id, occurrence_key) -> (wi_id,
  admitted_version, status, request_hash)`. The relation SHALL be unique on
  `(tenant, au_id, occurrence_key)`. Writes SHALL be transactional with WorkItem creation or fail
  closed.
- WHEN the claimed WorkItem reaches a terminal state, or its history is cleaned up, THE SYSTEM
  SHALL keep a tombstone that still deduplicates the occurrence until at least the source replay
  horizon has passed.
- IF the claim store is unreadable or a claim is in an indeterminate state (claimed with no
  `wi_`) THEN THE SYSTEM SHALL fail closed with `automation_authority_unavailable`. Crash
  reconciliation SHALL either resolve the claim to the one `wi_` found by its derived
  `external_key` / idempotency key, or mark it failed. It SHALL never mint a second `wi_`.
- THE SYSTEM SHALL record in `docs/automation-contract.md` that `automation-api-store` is
  hard-gated on implementing this claim and tombstone contract.

Usage authority
- THE SYSTEM SHALL distinguish two things in the contract. Commerce payer/payment limits are
  `monthly_limit_minor` and `per_request_max_minor` in `internal/commerce/budget.go`. Verified
  inference/FinOps usage metering is per-run, per-day and per-tenant automated-agent ceilings,
  with idempotent reservation, settlement and release.
- WHILE no verified usage-metering authority exists THE SYSTEM SHALL mark usage authority as
  `unknown`. It SHALL deny with `automation_authority_unavailable` and SHALL NOT model Commerce as
  the usage authority.

Support consent and token
- WHILE `support.diagnostic-followup.v1` is schema-valid THE SYSTEM SHALL keep it out of the
  enabled-template allowlist and refuse it with `automation_trigger_unsupported`.
- THE SYSTEM SHALL require every Support fire to have both of these:
  - an independently verified, live tenant-owner consent;
  - a freshly minted, eligible, tenant-bound `support`-scope token whose lifetime fits within the
    support scope's `MaxTTL` (1h, `internal/auth/agent_scope.go`), obtained through a separately
    approved path.
- IF a Support fire would reuse a token past its expiry, use a token minted by an agent or
  service itself, or rely on an `auth_ref` merely being present THEN THE SYSTEM SHALL refuse with
  `automation_support_constraint`.
- THE SYSTEM SHALL state that the 24h definition TTL never extends any token lifetime, and SHALL
  NOT assume mctl-api#901 is approved.

Manual run request
- THE SYSTEM SHALL define `automation-manual-run-request.v1`. Its client-writable fields are
  `schema_version`, `idempotency_key` (opaque) and `expected_version`. The occurrence identity is
  server-managed and SHALL NOT be client-writable.
- WHEN a manual request is replayed by the same principal, in the same tenant, for the same `au_`
  with the same key and an identical body THE SYSTEM SHALL return the original occurrence with
  `replayed: true`.
- IF the key is reused with a different body THEN THE SYSTEM SHALL return
  `automation_idempotency_key_reused` (409).
- WHEN another principal, tenant or `au_` uses the same opaque key THE SYSTEM SHALL produce a
  different occurrence. It SHALL NOT replay or conflict across that boundary.
- WHILE no execution gate is approved THE SYSTEM SHALL refuse manual execution with
  `automation_trigger_unsupported`.

Authorization and templates
- IF the caller is unlinked, expired, revoked or surface-mismatched THEN THE SYSTEM SHALL return a
  uniform 403 `automation_identity_unlinked` before any resource lookup. The result SHALL be
  independent of whether the target exists.
- IF an authenticated caller addresses an absent resource, a foreign-owner resource or a
  foreign-tenant resource THEN THE SYSTEM SHALL return a byte-identical 404 body.
- THE SYSTEM SHALL scope create idempotency by `(authenticated principal, tenant,
  idempotency_key)`.
- THE SYSTEM SHALL keep the template registry (every schema-defined template) separate from the
  enabled-template allowlist (templates that may currently be created or fired).

Toolchain findings
- THE SYSTEM SHALL include tests showing that `time.Parse(time.RFC3339, ...)` on the repo
  toolchain (`go 1.26.10`) accepts fractional seconds, and that the loop semantics are
  per-iteration.
- IF a zone is offset-only, including `Etc/GMT+N`, `Etc/GMT-N` and `Etc/GMT0`-style aliases, THEN
  THE SYSTEM SHALL return `automation_invalid`.

Scope
- THE SYSTEM SHALL change only these:
  - `docs/automation-contract.md`;
  - `internal/automation/contract/**`, including its schemas, fixtures and tests.
- `go test -race ./internal/automation/...` SHALL pass.

## Out of scope

- Any REST route, MCP tool, storage table or migration, Temporal Schedule, production worker,
  feature flag, Helm value or GitOps release.
- Support enablement, mctl-api#901, and any token-mint path.
- Approving or starting `automation-api-store` or any later slice. Filing downstream issues.
- Editing the #948 proposal or its `.status.yaml`, and re-running its DevLoop.
- Wiring `Decide` to `governance.Revalidate` or to any live store.

## Open questions

- PR mctl-gitops#2452 and PR #950 were not readable in this run, because the clone is shallow and
  the #2452 diff is not in the gitops checkout. These requirements are derived from the issue's
  enumeration of the amendments. The implementer and reviewer must diff the final document
  against #2452 line by line.
- The exact Agy `FAIL:P2` text on #950 was not readable. Reproduction on go1.26.10 shows that
  `time.Parse(time.RFC3339, ...)` accepts `.123456789Z`, `.5+02:00` and also `,5Z`. It rejects a
  lowercase `t`/`z`, which RFC 3339 section 5.6 permits. Proposed resolution: the P2 does not
  reproduce. The lowercase case is recorded as a documented restriction, not loosened.
- Should a bare `UTC`/`Etc/UTC` stay allowed? Proposed: yes, since it is a canonical IANA name.
  Only `Etc/GMT[+-]N` and the GMT0 aliases are rejected as offset-only.
- New code `automation_occurrence_conflict` versus reusing `automation_idempotency_key_reused` for
  conflicting occurrence reuse. Proposed: a new code, added only (vocabulary is append-only).
  `automation_occurrence_duplicate` is kept in the vocabulary and documented as deprecated
  meaning-preserving: it is no longer returned for an identical replay.
- Value of the source replay horizon. Proposed: the contract states horizon >= the catch-up window
  max (86400s) plus the producer's documented redelivery window. Producer windows are `unknown`.
