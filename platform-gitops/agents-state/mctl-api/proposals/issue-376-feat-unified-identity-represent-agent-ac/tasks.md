# Tasks: issue-376-feat-unified-identity-represent-agent-ac

- [ ] 1. Add the agent principal kind to `internal/auth`: `ProviderAgent =
  "agent"` and `AgentPrincipalPrefix = "agent:"` next to `ProviderService` /
  `SurfacePrincipalPrefix` (`internal/auth/principal.go:31-43`,
  `internal/auth/oidc.go:257`); an unexported `agent string` plus
  `execID`/`runID` fields on `auth.User` (`oidc.go:40-95`);
  `NewAgentUser`, `IsAgent()`, `AgentName()`, `ExecutionID()`,
  `AgentRunID()`; and an `u.agent != ""` case placed **before** the
  `u.service` case in `User.Identity()` (`principal.go:110-128`) returning
  `Kind: KindAgent`. — DoD: `go test ./internal/auth/...` passes with a new
  case proving an agent user has `IsAdmin() == false`, empty `Groups`,
  `IsService() == false`, and `Identity().Kind == auth.KindAgent`; the
  unexported-field forgery argument in the `service` field comment
  (`oidc.go:45-52`) is restated for `agent`.

- [ ] 2. Provision agent principals (depends on 1). No schema change —
  `principals.kind` already allows `'agent'`
  (`internal/principals/store.go:80`). Confirm `validIdentity`
  (`store.go:150-160`) accepts `{Provider: "agent", Subject: "agent:<name>"}`
  and add the row to the caller table in `docs/principals.md:15-23`. — DoD:
  `go test ./internal/principals/...` passes with a test that provisioning an
  agent identity twice is idempotent and yields one `prn_` of kind `agent`.

- [ ] 3. Add the `agent_run_tokens` table and store methods to
  `internal/workitems` (columns per design.md; `token_hash BYTEA UNIQUE`,
  plaintext never stored), following the inline
  `CREATE TABLE IF NOT EXISTS` convention every store in this repo uses
  (`internal/workitems/store.go:16-131`) — there is no migrations directory.
  Methods: `MintAgentRunToken`, `ResolveAgentRunToken` (by hash, joining
  `work_item_executions` so a terminal phase reads as revoked),
  `RevokeAgentRunToken`, `PurgeExpiredAgentRunTokens`. — DoD:
  `go test ./internal/workitems/...` passes; a resolve returns the bound
  agent, execution, work item and `subject_principal_id`, and returns
  not-found for expired, revoked and terminal-execution rows.

- [ ] 4. Add `POST /api/v1/agent-run-tokens` in a new
  `internal/api/handlers_agent_run_tokens.go` (depends on 3), gated by
  `isDirectService` (`internal/api/handlers_action_approvals.go:51-55`). It
  validates the agent against `agentregistry.Store`, loads the execution,
  **derives the subject server-side** from `work_items.owner_principal_id`
  falling back to `work_item_execution_requests.requested_by_principal_id`,
  caps `ttl_seconds` at 86400 (default 3600), and returns the plaintext
  token once. Register it in `internal/api/router.go` inside the 120/min
  write group. — DoD: the route refuses an unknown agent (400
  `agent_unknown`), a terminal execution (409 `execution_terminal`), any
  non-direct-service caller (403), and any body key naming a subject (400);
  the mint is audited with `issued_by_principal_id`.

- [ ] 5. Authenticate agent run tokens in `auth.Middleware` (depends on 1, 3).
  Add an `AgentRunResolver` interface in `internal/auth` and a
  `WithAgentRunResolver` option mirroring `WithPrincipalResolver`
  (`internal/auth/oidc.go:586`), wired in `cmd/api/main.go` next to the
  principal resolver (`cmd/api/main.go:197-223`). Insert the branch after
  the static/surface/usage-writer matches (`oidc.go:518-529`) and run
  `attachPrincipal` (`oidc.go:594-611`) on the result. While here, switch
  `staticServiceUser` (`oidc.go:446-452`) from `==` to
  `subtle.ConstantTimeCompare`, matching the surface (`:433`) and
  usage-writer (`:392`) paths. — DoD: `go test ./internal/auth/...` covers
  a valid token yielding an agent user, and 401 for unknown/expired/revoked
  with no fallback to any other principal; a disabled agent principal is
  403.

- [ ] 6. Add `internal/delegation` with the `Grant` type and `Resolver`
  (depends on 3). It resolves a ref to a stored subject from
  `work_item_execution_requests.requested_by(_principal_id)`,
  `action_approval_requests.decided_by(_principal_id)`,
  `work_items.owner_principal(_id)` or a `surfaceid` link, then enforces
  that the grant's execution or work item equals the run token's. — DoD:
  unit tests prove `grant_not_bound` for a grant from another run,
  `grant_subject_unresolved` for an empty `*_principal_id`, and that no code
  path reads a subject from anything the caller supplied.

- [ ] 7. Add `agentPrincipalGate` middleware in
  `internal/api/handlers_agent_identity.go` (depends on 5, 6), modelled on
  `surfacePrincipalGate` (`internal/api/handlers_surface_identity.go:121-173`):
  400 `delegation_not_accepted` for a non-agent caller sending
  `X-MCTL-On-Behalf-Of`, 400 `delegation_not_supported` off the allowlist,
  and a context-user swap to `auth.NewDelegatedUser(subject, groups,
  actingAgent)` — a sibling of `NewRelayedUser` (`oidc.go:287-302`) that
  drops `admins`, sets `actingPrincipal = "agent:<name>"` and
  `viaPrincipalID` to the agent's `prn_`. Refusals are audited as
  `agent_identity.delegation_refused`, the shape `relaySubject` uses
  (`handlers_surface_identity.go:180-186`). — DoD: table-driven handler
  tests cover every refusal code and prove a delegated request never carries
  `admins`.

- [ ] 8. Record the agent actor (depends on 7). Add the `agent:<name>` case
  to `principalOf` (`internal/api/handlers_work_items.go:75-83`); add
  `ViaExecutionID` to `workitems.Mutation`
  (`internal/workitems/inputs.go:15-36`) and `audit.Entry`
  (`internal/audit/logger.go:25-49`), set it in `mutationFor`
  (`handlers_work_items.go:207-252`) and in `clientmeta.go:172-191`; persist
  it as `via_execution_id TEXT NOT NULL DEFAULT ''` via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on `work_item_events`
  (`internal/workitems/store.go:121-130`) and `audit_events`
  (`internal/audit/postgres.go:47-49`), extending the INSERT at
  `postgres.go:109-118`. — DoD: no new table and no new actor column pair;
  `go test ./internal/audit/... ./internal/workitems/... ./internal/api/...`
  passes and an integration test shows one delegated agent write producing a
  single event row with subject in `actor_principal_id`, agent in
  `via_principal_id`, and the execution in `via_execution_id`.

- [ ] 9. Retire `input["approver"]` (depends on 6, 8). Replace
  `internal/api/handlers_write.go:171-196`: reject a body-supplied
  `approver` for every caller kind; derive it from `user.ID` +
  `user.PrincipalID()` for a human admin acting directly; require
  `approval_ref` for an agent principal and resolve it through
  `delegation.Resolver` to a decided `aar_` (state `approved`/`consumed`) or
  the audit event of a dev-loop approve, taking `approver` and
  `approver_principal_id` from `decided_by(_principal_id)` /
  `user_id`/`user_principal_id`. Add `approver_principal_id` to the
  `mctl-agents-approve` operation schema. Gate the old behaviour behind
  `MCTL_AGENTS_APPROVE_LEGACY_APPROVER`, default unset, auditing
  `approver.legacy_relay` on each use. — DoD:
  `internal/api/handlers_write_approver_test.go` extended to prove a service
  principal can no longer name an arbitrary approver with the flag unset,
  that `approval_ref_required` / `approval_ref_invalid` are returned and
  audited, and that the legacy flag path logs a deprecation warning.

- [ ] 10. Carry the approval reference through the dev-loop signal (depends
  on 9). `ApproveDevLoopWorkflow`
  (`internal/api/handlers_dev_loop.go:139-183`) keeps taking the approver
  from its own authenticated caller and keeps rejecting a body-supplied one
  (`:168`), but also returns the id of the audit entry it writes and adds
  `approval_ref` to the signal payload beside the existing `approver` key
  (`:177-178`). — DoD: the payload carries both keys; existing dev-loop
  tests pass unchanged; the returned body gains `approval_ref` in
  `internal/openapi/openapi.yaml`.

- [ ] 11. Surface actor/subject to policy (depends on 7, 8). Add
  `actor_principal_id`, `actor_kind`, `actor_name`, `subject_principal_id`,
  `subject_kind`, `agent_run_id` and `execution_id` to the
  `ActionApprovalRequest` payload (`internal/workitems/action_approvals.go`,
  `internal/api/handlers_action_approvals.go`), and add
  `GET /api/v1/identity/self` (`identity/v1`) returning actor, subject (null
  when not delegated), execution, work item and grant. — DoD: the route is
  documented in `internal/openapi/openapi.yaml` and a new
  `docs/agent-identity.md`, and the field names are the ones the policy
  checkpoint (#197 / ADR 014) and evidence envelope (mctl-agents#199) read.
  No MCP tool is added, so `internal/mcp/server_test.go`
  (`TestNewMCPServer_ToolCount`) stays untouched.

- [ ] 12. Documentation and config (depends on 1-11). Update
  `docs/principals.md` (caller table, dual-write table, an "agent actor and
  subject" section stating explicitly that `actor_principal_id` holds the
  subject and `via_principal_id` the carrier), `docs/work-context-contract.md`
  (identity section), `README.md` env table
  (`AGENT_RUN_TOKENS_DISABLED`, `MCTL_AGENTS_APPROVE_LEGACY_APPROVER`),
  `.env.example` and `helm/templates/deployment.yaml`. Add a runbook note
  that delegated agent work fails closed during a principal-store outage,
  unlike every other path which degrades. — DoD: `go vet ./...`,
  `go fmt`, `golangci-lint` clean; `cd e2e && go test -v` passes.

## Tests

- [ ] T1. `internal/auth`: an agent user is not admin, has no groups, is not
  `IsService()`, and produces `KindAgent`; `IsAgent()` cannot be forged from
  a GitHub login or Dex username spelled `agent:implementer` (the
  unexported-field argument at `oidc.go:45-52`).
- [ ] T2. `internal/workitems`: minting stores only a hash; resolve fails for
  expired, revoked and terminal-execution tokens; two concurrent mints for
  one execution both succeed and are independently revocable.
- [ ] T3. `internal/delegation`: **the security test.** A run token for
  execution A presenting a grant bound to execution B is
  `grant_not_bound`; a grant whose `*_principal_id` is `''` is
  `grant_subject_unresolved`; no resolver path reads a principal from a
  header or body value. Property-style table over all four grant kinds.
- [ ] T4. `internal/api`: `X-MCTL-On-Behalf-Of` from a human, a surface, the
  service principal and the usage writer is 400; from an agent on a
  non-allowlisted route is 400; every refusal writes an audit row.
- [ ] T5. `internal/api`: a delegated agent write records subject in
  `actor_principal_id`, `agent:<name>` in `acting_principal` /
  `via_principal_id`, and `we_...` in `via_execution_id` — on both
  `work_item_events` and `audit_events`, in exactly one row each.
- [ ] T6. `handlers_write_approver_test.go`: with the legacy flag unset, a
  service caller sending `approver` is 400; an agent without `approval_ref`
  is 400 `approval_ref_required`; an agent with a pending, denied, expired
  or mismatched ref is 409 `approval_ref_invalid` and audited; an agent with
  a valid ref gets the approver and `approver_principal_id` from the record.
- [ ] T7. Regression: every existing surface-relay test
  (`handlers_surface_identity`), action-approval test and
  `internal/workitems/principal_ids_test.go` passes unchanged — the agent
  path must not alter the surface contract.
- [ ] T8. `e2e`: mint a run token, call a delegated route, read
  `GET /api/v1/identity/self`, and assert actor ≠ subject in the response and
  in the resulting audit row.

## Rollback

Every change is additive and flag-gated, so rollback is staged and needs no
data migration:

1. **Fastest, no deploy:** set `AGENT_RUN_TOKENS_DISABLED=true`. The
   middleware branch (task 5) stops matching, every run token answers 401,
   and agents fall back to `MCTL_AGENT_SERVICE_TOKEN`, which task 5 never
   removes. Set `MCTL_AGENTS_APPROVE_LEGACY_APPROVER=true` to restore the
   pre-existing `mctl-agents-approve` service relay in the same step.
2. **Revert the image.** The new table (`agent_run_tokens`) and the two new
   columns (`via_execution_id`) are additive and defaulted, so an older
   binary ignores them and keeps running against the same database. Nothing
   was dropped, renamed or backfilled; `docs/principals.md:73-77` already
   establishes that a `''` principal column is a normal, expected value.
3. **Clean up, optional and last.** `DELETE FROM agent_run_tokens` and, only
   if the feature is abandoned rather than paused,
   `ALTER TABLE audit_events DROP COLUMN via_execution_id` and the same on
   `work_item_events`. Agent principals may be left in `principals` — they
   are inert rows of kind `agent` that nothing resolves once the middleware
   branch is off — or disabled with `principals.Store.SetStatus`.

The irreversible step is any real approval recorded through task 9's new
path: those rows carry `approver_principal_id`. They are strictly more
information than the old free-text approver and remain readable by the old
binary, so they do not block a revert.
