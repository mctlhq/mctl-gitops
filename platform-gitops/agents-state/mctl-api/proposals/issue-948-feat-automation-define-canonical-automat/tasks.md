# Tasks: issue-948-feat-automation-define-canonical-automat

- [ ] 1. Write `docs/automation-contract.md` with sections 1-12 as listed in design.md. These
  cover claim classes, identity and occurrence keys, the closed operation set, field ownership,
  templates, triggers and policies (including the `UNVERIFIED` Temporal list), authority and
  checkpoints, Support constraints, transport and failure, versioning and redaction, the
  crosswalk, and the proposed follow-up slices (not filed).
  - DoD: every normative statement carries a claim class.
  - DoD: every `proved-source` claim cites an existing file path.
  - DoD: the contract includes a normative immutable occurrence-key grammar
    independent of definition version; stable source event ID vs delivery
    attempt, a distinct manual request identity, and a durable unique
    occurrence-claim/tombstone **required in the next slice**, not claimed
    implemented by this pure harness.
  - DoD: explicitly name automation usage-budget authority as unresolved
    until matched against metering/FinOps; do not describe payment Commerce
    budget as daily inference limits.
  - DoD: Support schema vs enabled-template policy is explicit; 24h
    definition does not extend 1h max support token; every future fire
    requires independent owner consent and eligible fresh token authority.
  - DoD: 403-vs-404 lookup precedence and successful ordinary event replay
    are unambiguous.
  - DoD: the remaining open questions from requirements.md are reproduced,
    and every `unknown` or `assumed` future integration is a follow-up
    gate, not an assertion of current enforcement.
- [ ] 2. (depends on 1) Add the JSON Schemas under `internal/automation/contract/schema/v1/`:
  create-request, **manual-run-request** (with required caller-scoped
  `idempotency_key`), patch, definition, trigger, policies,
  `template-reminder.v1`, `template-support-followup.v1`, read-only
  run view and error. The manual request schema must not accept
  server-issued `occurrence_key`, `wi_`, `we_` or actor fields.
  - DoD: each uses draft 2020-12, has a `$id` under `https://mctl.ai/schemas/automation/v1/`, and
    sets `additionalProperties: false`.
  - DoD: create and patch contain no server-owned property.
  - DoD: the error `code` enum equals the vocabulary in design.md,
    including `automation_occurrence_conflict`. Normal replay is a
    success response with `replayed: true`, not
    `automation_occurrence_duplicate` 409.
  - DoD: a template may be schema-defined but runtime-disabled; the
    Support follow-up schema MUST NOT imply a ready-to-use capability.
- [ ] 3. (depends on 2) Add `internal/automation/contract/schema.go`, which embeds and compiles the
  schemas once (pattern: `internal/deployanalyze/schema.go`). It exposes `ValidateCreate`,
  `ValidatePatch`, `ValidateDefinition` and `ContractError{Code}`, with the server-owned-field
  pre-pass.
  - DoD: `go vet` and `golangci-lint` are clean.
  - DoD: the package has no imports from `internal/` other than standard-library-only helpers.
- [ ] 4. (depends on 3) Add `templates.go` (schema registry separate from
  enabled-template decision; only `reminder.v1 + at` initially),
  `trigger.go` (`ResolveAt` with DST gap/fold and `time/tzdata`),
  `occurrence.go` (stable source ID/version-independent occurrence,
  external and idempotency key derivations), a pure manual-request
  binding helper, and `support.go` (Support scope/TTL/token-renewal
  safety constraints).
  - DoD: all functions are pure and have no I/O.
  - DoD: the doc comments reference `docs/automation-contract.md`.
  - DoD: the harness never treats a valid `auth_ref`, a scheduled
    definition, or an expired support token as authority.
  - DoD: expose a typed pure model of durable claim state/replay and
    tombstone **without adding DB tables**; label its cross-process
    durability as unproved until `automation-api-store`.
- [ ] 5. (depends on 4) Add `authority.go`, the isolated decision model `Decide(Checkpoint, Inputs)`
  for the create/update, fire and side-effect checkpoints.
  - DoD: an unavailable source always yields `automation_authority_unavailable`.
  - DoD: an `aar_` bound to a different `we_` yields `automation_approval_not_reusable`.
  - DoD: cross-owner and cross-tenant resource access yields uniform
    `automation_not_found` after valid authentication; unknown/unlinked
    caller gets uniform `automation_identity_unlinked` before ID lookup.
  - DoD: unknown/unsupported automation usage-budget authority produces
    `automation_authority_unavailable` even if the caller asserts headroom.
  - DoD: the code is labelled `isolated-model` and has no production caller.
- [ ] 6. (depends on 2) Add `testdata/{valid,invalid}/*.json` plus `testdata/manifest.json`, which
  maps each fixture to its expected code. The fixtures cover every case in Tests below.
  - DoD: every error code in the vocabulary has at least one fixture or a table test.
- [ ] 7. (depends on 3-6) Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
  `go test ./...`, and confirm repository CI is green.
  - DoD: the commands pass, `TestNewMCPServer_ToolCount` is unchanged, and
    `internal/openapi/openapi.yaml` is unchanged.
  - DoD: if any command cannot run, the exact blocker is in the PR body and acceptance is not
    claimed.
- [ ] 8. (depends on 7) In the PR description, list the proposed follow-up slices and rollout
  checkpoints for owner review only.
  - DoD: no downstream issue is filed or activated.

## Tests

- [ ] T1. Malformed JSON, a schema type violation and an unknown field produce
  `automation_invalid` or `automation_unknown_field`.
- [ ] T2. Spoofed server-owned fields in create and patch produce
  `automation_server_owned_field`. One fixture per field: `id`, `tenant`, `owner_principal`,
  `actor`, `surface`, `version`, `state`, `provenance` and `created_by`.
- [ ] T3. Raw Temporal requests produce `automation_server_owned_field` or
  `automation_template_not_allowed`: `workflow_type`, `namespace`, `task_queue`, `signal`, and an
  unknown template id.
- [ ] T4. Identity failures produce `automation_identity_unlinked` at every checkpoint: an
  unknown, unlinked, expired or revoked link; a revoked install; and a surface or tenant mismatch.
- [ ] T5. A cross-owner read in the same tenant, a cross-tenant read and an owner-change patch each
  produce `automation_not_found`. The response is byte-identical to the one for a nonexistent
  `au_`, so there is no existence oracle.
- [ ] T6. The same canonical occurrence inputs yield the same
  `occurrence_key` and `FireIdempotencyKey`, regardless of definition
  version or source delivery-attempt ID; expected duplicate delivery is
  idempotent success with `replayed: true`. Two distinct overlapping
  occurrences yield different `wi_` external keys. Conflicting canonical
  identity under the same claimed key gives 409
  `automation_occurrence_conflict`.
- [ ] T7. Approval misuse produces `automation_approval_not_reusable`: an `aar_` bound to another
  occurrence's `we_`, or a schedule presented as approval. A side effect without approval produces
  `automation_approval_required`.
- [ ] T8. Verified per-run/day/tenant automation **usage** budget headroom
  exhaustion yields `automation_budget_exhausted` (409); an unavailable,
  unknown or payment-only budget source yields
  `automation_authority_unavailable` even when the client claims budget
  is available. No Commerce payment limit masquerades as an inference cap.
- [ ] T9. Policy drift (pinned version differs from live) produces `automation_policy_drift`.
- [ ] T10. Support abuse produces `automation_support_constraint`: definition
  TTL over 24h, >3 fires, write capability, delegated actor, impersonated
  owner, missing tenant, or `auth_ref` without independent live consent.
  A still-valid 24h definition with an expired 1h support run token,
  no eligible fresh-token mint or revoked consent MUST be refused;
  Support template is schema-valid but disabled in MVP.
- [ ] T11. DST cases. In `America/New_York`, 2026-03-08 02:30 is a gap: `shift_forward` gives
  03:30 EDT and `reject` produces `automation_time_ambiguous`. In `Europe/Berlin`, 2026-10-25
  02:30 is a fold: `earlier` and `later` resolve to different instants and `reject` produces
  `automation_time_ambiguous`. An unknown zone or an offset-only zone produces
  `automation_invalid`.
- [ ] T12. `event` triggers for `check_run` or `workflow_run`, and `schedule` and `dependency`
  triggers in the MVP, produce `automation_trigger_unsupported`.
- [ ] T13. A `v0` spike document produces `automation_invalid`.
- [ ] T14. Every valid fixture passes, and `automation-definition` (the response schema) rejects a
  create-request body. This demonstrates that the request and response schemas are separate.
- [ ] T15. Reminder text over 2 KiB produces `automation_invalid`.
- [ ] T16. `OccurrenceKeyStableAcrossVersionChange`: source event ID
  (and scheduled UTC instant) remain identical when `definition_version`
  is incremented between first fire and replay; replay preserves the
  original `wi_`, version-provenance, reservation and side-effect count.
- [ ] T17. `ClosedWorkItemReplayNeedsDurableClaim`: model terminal
  WorkItem and simulate deletion of `external_key`/WorkItem idempotency
  rows. A unique occurrence claim/tombstone must still prevent a new
  `wi_`; mark durability as a future DB acceptance gate, not a
  harness-proved production guarantee.
- [ ] T18. `ManualRunIdempotencyAndActorScope`: same principal, tenant,
  `au_` and manual key replays exactly one run; new key creates a
  distinct occurrence; changed body on same key gives 409; another
  principal/tenant cannot hijack a prior key; unsupported manual
  execution is refused before the later rollout gate.
- [ ] T19. `StableProducerEventIDVersusDeliveryAttempts`: different
  webhook delivery IDs carrying the same verified canonical event ID
  do not create a second occurrence; the same event ID reused by a
  different producer or event type DOES create a distinct occurrence,
  as does a truly distinct source event ID.
- [ ] T20. `UniformAccessRefusals`: an unlinked caller receives 403
  independent of arbitrary target ID; authenticated cross-tenant,
  cross-owner and nonexistent ID reads have the same 404 response
  shape with no existence oracle; list counts exclude hidden objects.
- [ ] T21. `SupportFreshTokenAndOwnerConsent`: a 24h definition
  cannot reuse an expired 1h token; only an eligible, independently
  authorized future mint path can issue a fresh per-fire token. With
  unknown delegation/owner consent Support remains disabled.
- [ ] T22. `BudgetSourceUnprovenDenies`: simulated Commerce monthly
  payment limits do NOT satisfy automation per-day LLM usage limits;
  unknown/revoked metering authority refuses before any spend.
- [ ] T23. `TemplateSchemaVersusEnablement`: a structurally valid
  Support template and non-`at` trigger remain runtime-disabled
  despite valid schemas, `auth_ref` and caller-selected overrides.
- [ ] T24. `CrashAfterOccurrenceClaim` (isolated model): after a
  claim but before `wi_`/`xr_` creation, retry must reconcile or
  fail closed without a second reservation; report that live
  transaction/failure-injection proof is mandatory in next slice.
- [ ] T25. `ReplayVsConflictCodes`: routine duplicate returns
  idempotent success; incompatible reuse returns
  `automation_occurrence_conflict` 409; internal divergent-state
  `automation_occurrence_duplicate` is not returned for normal
  webhook retry.

## Rollback

The slice is additive and has no runtime effect: docs, embedded schemas and a package imported only
by tests. To roll back, revert the PR. There is no data, migration, flag or deployment to undo.
