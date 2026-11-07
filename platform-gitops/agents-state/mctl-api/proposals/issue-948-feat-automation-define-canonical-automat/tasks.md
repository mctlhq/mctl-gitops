# Tasks: issue-948-feat-automation-define-canonical-automat

- [ ] 1. Write `docs/automation-contract.md` with sections 1-12 as listed in design.md. These
  cover claim classes, identity and occurrence keys, the closed operation set, field ownership,
  templates, triggers and policies (including the `UNVERIFIED` Temporal list), authority and
  checkpoints, Support constraints, transport and failure, versioning and redaction, the
  crosswalk, and the proposed follow-up slices (not filed).
  - DoD: every normative statement carries a claim class.
  - DoD: every `proved-source` claim cites an existing file path.
  - DoD: the open questions from requirements.md are reproduced.
- [ ] 2. (depends on 1) Add the JSON Schemas under `internal/automation/contract/schema/v1/`:
  create-request, patch, definition, trigger, policies, `template-reminder.v1`,
  `template-support-followup.v1`, run and error.
  - DoD: each uses draft 2020-12, has a `$id` under `https://mctl.ai/schemas/automation/v1/`, and
    sets `additionalProperties: false`.
  - DoD: create and patch contain no server-owned property.
  - DoD: the error `code` enum equals the vocabulary in design.md.
- [ ] 3. (depends on 2) Add `internal/automation/contract/schema.go`, which embeds and compiles the
  schemas once (pattern: `internal/deployanalyze/schema.go`). It exposes `ValidateCreate`,
  `ValidatePatch`, `ValidateDefinition` and `ContractError{Code}`, with the server-owned-field
  pre-pass.
  - DoD: `go vet` and `golangci-lint` are clean.
  - DoD: the package has no imports from `internal/` other than standard-library-only helpers.
- [ ] 4. (depends on 3) Add `templates.go` (the closed allowlist with server-side bindings),
  `trigger.go` (`ResolveAt` with DST gap/fold, embedding `time/tzdata`), `occurrence.go` (the
  occurrence, external and idempotency key derivations) and `support.go` (Support constraints).
  - DoD: all functions are pure and have no I/O.
  - DoD: the doc comments reference `docs/automation-contract.md`.
- [ ] 5. (depends on 4) Add `authority.go`, the isolated decision model `Decide(Checkpoint, Inputs)`
  for the create/update, fire and side-effect checkpoints.
  - DoD: an unavailable source always yields `automation_authority_unavailable`.
  - DoD: an `aar_` bound to a different `we_` yields `automation_approval_not_reusable`.
  - DoD: cross-owner access yields `automation_not_found`.
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
- [ ] T6. The same occurrence inputs give the same `occurrence_key` and `FireIdempotencyKey`; a
  second delivery produces `automation_occurrence_duplicate`. Two overlapping instants give
  different keys and so different `wi_` external keys.
- [ ] T7. Approval misuse produces `automation_approval_not_reusable`: an `aar_` bound to another
  occurrence's `we_`, or a schedule presented as approval. A side effect without approval produces
  `automation_approval_required`.
- [ ] T8. Exhausted budget headroom (per run, per day or per tenant) produces
  `automation_budget_exhausted`, and a budget source marked unavailable produces
  `automation_authority_unavailable`.
- [ ] T9. Policy drift (pinned version differs from live) produces `automation_policy_drift`.
- [ ] T10. Support abuse produces `automation_support_constraint`: a TTL over 24h, more than 3
  fires, a write capability, a delegated actor or impersonated owner, a missing tenant binding, or
  an `auth_ref` presented without live authorization.
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

## Rollback

The slice is additive and has no runtime effect: docs, embedded schemas and a package imported only
by tests. To roll back, revert the PR. There is no data, migration, flag or deployment to undo.
