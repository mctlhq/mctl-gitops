# Tasks: issue-376-feat-unified-identity-represent-agent-ac

Sliced into four groups (review finding 6). Each group is independently
shippable and leaves `main` working. Group C carries the rollout order from
review finding 1 and must not be reordered.

---

## Slice A — agent principal, run tokens, recording

- [ ] A1. Add the agent principal kind to `internal/auth`: `ProviderAgent =
  "agent"` and `AgentPrincipalPrefix = "agent:"` next to `ProviderService` /
  `SurfacePrincipalPrefix` (`internal/auth/principal.go:31-43`,
  `internal/auth/oidc.go:257`); unexported `agent`, `execID`, `workItemID`,
  `runID` fields on `auth.User` (`oidc.go:40-95`); `NewAgentUser`, `IsAgent()`,
  `AgentName()`, `ExecutionID()`, `WorkItemID()`, `AgentRunID()`; and an
  `u.agent != ""` case placed **before** the `u.service` case in
  `User.Identity()` (`principal.go:110-128`) returning `Kind: KindAgent`. —
  DoD: `go test ./internal/auth/...` passes with a case proving an agent user
  has `IsAdmin() == false`, empty `Groups`, `IsService() == false` (so
  `isDirectService` at `handlers_action_approvals.go:52-55` does not start
  matching agents), and `Identity().Kind == auth.KindAgent`; the
  unexported-field forgery argument in the `service` field comment
  (`oidc.go:45-52`) is restated for `agent`.

- [ ] A2. Reserve the `agent` provider name (depends on A1; review finding 4).
  Add a `reservedProviderNames` set in `internal/auth` containing `agent`, with
  a doc comment stating that the #374 federation registry must refuse any
  configured provider claiming it at boot, so no external IdP can mint into the
  `(agent, ...)` namespace. — DoD: a unit test asserts the reservation; a note
  is added to `docs/principals.md` and cross-referenced from the #374 proposal's
  registry-invariant list.

- [ ] A3. Provision agent principals (depends on A1). No schema change —
  `principals.kind` already allows `'agent'` (`internal/principals/store.go:80`)
  and `validIdentity` (`store.go:150-160`) already accepts `auth.KindAgent`.
  Add the caller row to `docs/principals.md:15-23`. — DoD:
  `go test ./internal/principals/...` passes with a test that provisioning an
  agent identity twice is idempotent and yields one `prn_` of kind `agent`.

- [ ] A4. Add the `agent_run_tokens` table and store methods to
  `internal/workitems`, following the inline `CREATE TABLE IF NOT EXISTS`
  convention every store uses (`internal/workitems/store.go:158-180`) — there
  is no migrations directory. Columns exactly per design.md: **no
  `subject_principal_id`** (review finding 3 — the mint binds execution and
  work item only). Methods: `MintAgentRunToken`, `ResolveAgentRunToken` (by
  `token_hash`, joining `work_item_executions` so a terminal phase reads as
  revoked), `RevokeAgentRunToken`, `PurgeExpiredAgentRunTokens`. — DoD:
  `go test ./internal/workitems/...` passes; a resolve returns the bound agent,
  execution and work item and **no subject field exists on the row**; resolve
  returns not-found for expired, revoked and terminal-execution rows.

- [ ] A5. Add `POST /api/v1/agent-run-tokens` in a new
  `internal/api/handlers_agent_run_tokens.go` (depends on A4), gated by
  `isDirectService` (`internal/api/handlers_action_approvals.go:52-55`). It
  validates the agent against `agentregistry.Store` (400 `agent_unknown`),
  loads the execution and refuses a terminal phase (409 `execution_terminal`),
  takes `work_item_id` from the execution, caps `ttl_seconds` at 86400 (default
  3600), and returns the plaintext token once. Register it in
  `internal/api/router.go` inside the write group at `:443-449`. — DoD: the
  route refuses an unknown agent, a terminal execution, any non-direct-service
  caller (403), and any body key naming a subject (400, via
  `forbiddenIdentityFields`, `handlers_work_items.go:66-70`).

- [ ] A6. Audit every mint and every refused mint (depends on A5; review
  finding 5). `agent_run_token.mint` records `{token_id, agent,
  agent_principal_id, execution_id, work_item_id, ttl_seconds, expires_at,
  permissions, issued_by_principal_id}`; `agent_run_token.mint_refused` records
  the typed code, in the shape of `auditActionApprovalRefusal`
  (`handlers_action_approvals.go:163-175`). While here, add the missing refusal
  audit to `CreateActionApproval`'s 403 (`handlers_action_approvals.go:204-208`),
  the one refusal on that surface with no record. — DoD: a test asserts the
  plaintext token appears in no audit entry, no log line and no response body
  after the first; a test asserts one audit row per mint and per refusal.

- [ ] A7. Authenticate agent run tokens in `auth.Middleware` (depends on A1,
  A4). Add an `AgentRunResolver` interface in `internal/auth` and a
  `WithAgentRunResolver` option mirroring `WithPrincipalResolver`
  (`oidc.go:586`), wired in `cmd/api/main.go` next to the principal resolver.
  Insert the branch after the static/surface/usage-writer matches
  (`oidc.go:518-529`) and run `attachPrincipal` (`oidc.go:594-611`) on the
  result. While here, switch `staticServiceUser` (`oidc.go:446-452`) from `==`
  to `subtle.ConstantTimeCompare`, matching the surface (`:433`) and
  usage-writer (`:392`) paths. — DoD: `go test ./internal/auth/...` covers a
  valid token yielding an agent user, and 401 for unknown/expired/revoked with
  no fallback to any other principal; a disabled agent principal is 403.

- [ ] A8. Record the agent actor (depends on A7). Add the `agent:<name>` case
  to `principalOf` (`handlers_work_items.go:75-83`); add `ViaExecutionID` to
  `workitems.Mutation` (`internal/workitems/inputs.go:15-36`) and `audit.Entry`
  (`internal/audit/logger.go:25-49`), set it in `mutationFor`
  (`handlers_work_items.go:207-252`) and `clientmeta.go:172-191`; persist it as
  `via_execution_id TEXT NOT NULL DEFAULT ''` via `ADD COLUMN IF NOT EXISTS` on
  `work_item_events` and `audit_events` (`internal/audit/postgres.go:47-49`),
  extending the INSERT at `postgres.go:109-118`. — DoD: no new table and no new
  actor column pair; `go test ./internal/audit/... ./internal/workitems/...
  ./internal/api/...` passes.

---

## Slice B — delegation grants

- [ ] B1. Add `internal/delegation` with the `Grant` type and `Resolver`
  (depends on A4). It resolves a ref to a stored subject from
  `work_item_execution_requests.requested_by(_principal_id)`,
  `action_approval_requests.decided_by(_principal_id)`,
  `work_items.owner_principal(_id)` or a `surfaceid` link, then enforces that
  the grant's execution id or work item id equals the run token's. — DoD: unit
  tests prove `grant_not_bound` for a grant from another run,
  `grant_subject_unresolved` for an empty `*_principal_id`, and that no code
  path reads a subject from anything the caller supplied.

- [ ] B2. Add `agentPrincipalGate` middleware in
  `internal/api/handlers_agent_identity.go` (depends on A7, B1), modelled on
  `surfacePrincipalGate` (`handlers_surface_identity.go:121-173`): 400
  `delegation_not_accepted` for a non-agent caller sending
  `X-MCTL-On-Behalf-Of`, 400 `delegation_not_supported` off the allowlist, and
  a context-user swap to `auth.NewDelegatedUser(subject, groups, actingAgent)`
  — a sibling of `NewRelayedUser` (`oidc.go:287-302`) that drops `admins`, sets
  `actingPrincipal = "agent:<name>"` and `viaPrincipalID` to the agent's
  `prn_`. Refusals audit as `agent_identity.delegation_refused`. — DoD:
  table-driven handler tests cover every refusal code and prove a delegated
  request never carries `admins`.

- [ ] B3. Extend `forbiddenIdentityFields` (`handlers_work_items.go:66-70`) to
  every route this proposal touches, adding `on_behalf_of`, `subject`,
  `delegated_actor` and `acting_principal` to the existing set (depends on B2).
  — DoD: a body carrying any of them is 400 on the agent-run-token route, the
  dev-loop approve route and every delegation-allowlisted route.

---

## Slice C — approver retirement, in the finding-1 order

**Do not reorder. C1-C3 ship in mctl-api with the legacy relay ON; C4-C8 ship
from mctl-agents; C9 only after C8 is verified.**

- [ ] C1. Express the dev-loop approval as an `aar_` (depends on nothing in A
  or B). `ApproveDevLoopWorkflow` (`handlers_dev_loop.go:149-227`): find the
  pending `aar_` for `execution_id = workflow_id` and `action_kind =
  "mctl-agents-approve"`; if none exists, create it server-side with
  `RequestedBy = "service:mctl-agent"`, `target = "<service>/<slug>"`,
  `policy_rule_id = "dev-loop.human-approval"`, `policy_version = "v1"`; then
  decide it through the existing `WorkItems.DecideActionApproval`. Add
  `approval_ref` to the Temporal signal payload beside `approver`, and to the
  response body and `internal/openapi/openapi.yaml`. — DoD: the requester is
  the service and the decider the human, so `ErrApprovalSelfDecision`
  (`action_approvals.go:494-496`) never fires; existing dev-loop tests pass
  with the payload's extra key.

- [ ] C2. Tighten the dev-loop approve endpoint (depends on C1). Change
  `requireTemporalAdmin` (`handlers_dev_loop.go:42-57`) from bare
  `user.IsAdmin()` to `isHumanAdmin` (`handlers_action_approvals.go:59-64`) —
  today the `mctl-agent` service principal carries `admins` and passes. Stamp
  `principalOf(user)` instead of `user.ID` (`:177`). Replace the bare
  `json.NewDecoder` (`:162`) with `decodeWorkItemBodyLimit` plus the
  `forbiddenIdentityFields` check. — DoD: a service-principal call is 403 and
  audited; a body with unknown fields is 400; the recorded approver carries its
  `github:` / `oidc:` namespace.

- [ ] C3. Bind `mctl-agents-approve` to `approval_ref`, legacy relay **ON by
  default** (depends on B1, C1). Replace `handlers_write.go:171-196`:
  - human admin acting directly → `approver = user.ID`,
    `approver_principal_id = user.PrincipalID()`;
  - agent principal → `approval_ref` required (400 `approval_ref_required`);
    load the `aar_`, recompute `IntentHash` from the *submitted* `service` and
    `slug`, and call `WorkItems.ConsumeActionApproval(ctx, ref, intentHash)`
    (the store method, not the HTTP `/consume` route, whose `isDirectService`
    gate would not match an agent); take `approver` /
    `approver_principal_id` from `decided_by` / `decided_by_principal_id`;
    any store refusal → 409 `approval_ref_invalid`, audited;
  - a ref that is not an `aar_` id — in particular an audit event id → 400
    `approval_ref_invalid`;
  - `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` **defaults to `true`**. While on, the
    pre-existing service relay of `input["approver"]` is accepted, logs a
    deprecation warning, and writes an audit entry `approver.legacy_relay`
    recording the relayed string, the calling principal and the operation — on
    **every** use, so the C8 verify step is a query.
  Add `approver_principal_id` and `approval_ref` to the `mctl-agents-approve`
  operation schema (`internal/operations/registry.go:736-744`). — DoD:
  `internal/api/handlers_write_approver_test.go` proves: with the flag at its
  default, today's worker request still succeeds and emits exactly one
  `approver.legacy_relay` row; with the flag `false`, a service caller sending
  `approver` is 400; an agent without `approval_ref` is 400; an agent with a
  pending, denied, expired, consumed or intent-mismatched ref is 409 and
  audited; a second use of a valid ref is 409 `approval_consumed`.

### mctl-agents counterpart (file as a new mctl-agents issue)

No existing mctl-agents issue carries these; they are written to be lifted
verbatim. They ship **after** C1-C3 is in production.

- [ ] C4. Temporal worker: at the start of each agent step, call
  `POST /api/v1/agent-run-tokens` with `MCTL_AGENT_SERVICE_TOKEN` and use the
  returned `art_` token as the bearer for every subsequent mctl-api call in
  that step. — DoD: no agent step calls mctl-api with the static token except
  the mint itself.
- [ ] C5. DevLoopWorkflow: at the approval gate, create the `aar_` via
  `POST /api/v1/action-approvals` with `action_kind = "mctl-agents-approve"`,
  `target = "<service>/<slug>"`, `execution_id = <workflow id>`. — DoD: the
  approval exists before the human is notified, so C1's server-side fallback
  becomes the exception rather than the rule.
- [ ] C6. Worker: read `approval_ref` off the approve signal payload and submit
  `mctl-agents-approve` with `approval_ref` and **no** `approver`. — DoD: no
  `approver.legacy_relay` audit entry is produced by a DevLoop approval.
- [ ] C7. Worker: send `X-MCTL-On-Behalf-Of: <grant_ref>` on calls made for a
  human, using the `xr_` / `aar_` / `wi_` the run is already bound to. — DoD: a
  delegated write records subject ≠ actor.
- [ ] C8. Verify, then stop. Query `audit_events` for
  `operation = 'approver.legacy_relay'` over a full DevLoop cycle (a week of
  the Saturday cron plus at least one issue-triggered loop). — DoD: the count is
  zero; the result is recorded on the issue.

- [ ] C9. mctl-api follow-up release (depends on C8): flip
  `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` to default `false`, keeping the env var
  as an escape hatch for exactly one release, then delete it and the branch. —
  DoD: the legacy branch and its audit operation are gone from
  `handlers_write.go`; README, `.env.example` and
  `helm/templates/deployment.yaml` no longer mention the flag.

---

## Slice D — `identity/self` and the approval actor fields

- [ ] D1. Serve the principal ids that are already stored (depends on A8).
  Extend `actionApprovalColumns` (`action_approvals.go:135-137`) with
  `requested_by_principal_id, via_principal_id, decided_by_principal_id,
  decided_via_principal_id` — written since #373 and never read back — and add
  the matching fields to `ActionApprovalRequest` (`:139-163`) and
  `scanActionApproval` (`:273-293`). — DoD:
  `GET /api/v1/action-approvals/{id}` returns `decided_by_principal_id`;
  existing action-approval tests pass with the wider payload.

- [ ] D2. Add the actor/subject fields to `ActionApprovalRequest` (depends on
  B2, D1): `actor_kind`, `actor_name`, `subject_principal_id`, `subject_kind`,
  `agent_run_id`, stored as `ADD COLUMN IF NOT EXISTS` and populated from the
  authenticated caller at create and decide. — DoD: the names are exactly the
  ones the policy checkpoint (#197 / ADR 014) and the evidence envelope
  (mctl-agents#199) read, and are listed in `internal/openapi/openapi.yaml`.

- [ ] D3. Add `GET /api/v1/identity/self` (`identity/v1`) returning
  `{actor: {principal_id, kind, name}, subject: {...} | null, execution_id,
  work_item_id, agent_run_id, grant: {kind, ref} | null}` (depends on B2).
  Register it outside the write group, like the dev-loop liveness read
  (`router.go:519-524`). — DoD: `subject` is `null` — not a copy of `actor` —
  when the request is not delegated; no MCP tool is added, so
  `internal/mcp/server_test.go` (`TestNewMCPServer_ToolCount`) stays untouched.

- [ ] D4. Documentation and config (depends on A-D). Update
  `docs/principals.md` (caller table, dual-write table, an "agent actor and
  subject" section stating explicitly that `actor_principal_id` holds the
  subject and `via_principal_id` the carrier, and the `agent` provider
  reservation), `docs/work-context-contract.md`, a new `docs/agent-identity.md`
  carrying the single subject-derivation rule and the C1-C9 release order, the
  README env table (`AGENT_RUN_TOKENS_DISABLED`,
  `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` with its default of `true`),
  `.env.example` and `helm/templates/deployment.yaml`. Add a runbook note that
  delegated agent work fails closed during a principal-store outage, unlike
  every other path. — DoD: `go vet ./...`, `go fmt`, `golangci-lint` clean;
  `cd e2e && go test -v` passes.

---

## Tests

- [ ] T1. `internal/auth`: an agent user is not admin, has no groups, is not
  `IsService()`, and produces `KindAgent`; `IsAgent()` cannot be forged from a
  GitHub login or Dex username spelled `agent:implementer` (the
  unexported-field argument at `oidc.go:45-52`).
- [ ] T2. `internal/workitems`: minting stores only a hash; the row has no
  subject column; resolve fails for expired, revoked and terminal-execution
  tokens; two concurrent mints for one execution both succeed and are
  independently revocable.
- [ ] T3. `internal/delegation` — **the security tests.**
  - T3a. A run token for execution A presenting a grant bound to execution B is
    `grant_not_bound`. Property-style table over all four grant kinds.
  - T3b. **Mint context vs. grant disagreement (review finding 3).** A run
    token minted on work item `wi_X` — whose `owner_principal_id` is Alice —
    presenting an `xr_` bound to `wi_X` but `requested_by` Bob records **Bob**
    as the subject, and the test asserts Alice's principal id appears nowhere in
    the resulting `Mutation` or audit row. The grant is the authority; the work
    item is only the binding scope.
  - T3c. A grant whose `*_principal_id` is `''` is `grant_subject_unresolved`,
    never a string fallback.
  - T3d. No resolver path reads a principal from a header or body value
    (asserted structurally: the `Resolve` signature takes a ref and the token
    binding, and nothing else).
- [ ] T4. `internal/api`: `X-MCTL-On-Behalf-Of` from a human, a surface, the
  service principal and the usage writer is 400; from an agent on a
  non-allowlisted route is 400; every refusal writes an audit row.
- [ ] T5. `internal/api`: a delegated agent write records subject in
  `actor_principal_id`, `agent:<name>` in `acting_principal` /
  `via_principal_id`, and `we_...` in `via_execution_id` — on both
  `work_item_events` and `audit_events`, in exactly one row each.
- [ ] T6. `internal/api`: every mint writes exactly one `agent_run_token.mint`
  audit row carrying agent, execution, work item, TTL and minting principal;
  the plaintext token appears in no audit row, log line or later response.
- [ ] T7. `handlers_write_approver_test.go`, both flag states:
  - default (`true`): today's worker request — `{approver: "alice"}` under the
    service token — still succeeds and emits exactly one `approver.legacy_relay`
    audit row. **This is the finding-1 regression guard.**
  - `false`: a service caller sending `approver` is 400; an agent without
    `approval_ref` is 400 `approval_ref_required`; an agent with a pending,
    denied, expired, consumed or intent-mismatched ref is 409
    `approval_ref_invalid` and audited; a valid ref yields approver and
    `approver_principal_id` from `decided_by` / `decided_by_principal_id`; a
    **second** use of the same ref is 409, proving single-use.
  - an `approval_ref` that is an audit event id is 400, never resolved.
- [ ] T8. `internal/api`: `requireTemporalAdmin` refuses the `mctl-agent`
  service principal and any relayed or surface admin on the dev-loop approve
  route, and the refusal is audited.
- [ ] T9. Regression: every existing surface-relay test
  (`handlers_surface_identity`), action-approval test and
  `internal/workitems/principal_ids_test.go` passes unchanged — the agent path
  must not alter the surface contract.
- [ ] T10. `e2e`: mint a run token, call a delegated route, read
  `GET /api/v1/identity/self`, and assert actor ≠ subject in the response and in
  the resulting audit row.

## Rollback

Every change is additive and flag-gated, so rollback is staged and needs no
data migration.

1. **Fastest, no deploy:** set `AGENT_RUN_TOKENS_DISABLED=true`. The middleware
   branch (A7) stops matching, every run token answers 401, and agents fall
   back to `MCTL_AGENT_SERVICE_TOKEN`, which A7 never removes. If C9 has
   already shipped, set `MCTL_AGENTS_APPROVE_LEGACY_APPROVER=true` in the same
   step to restore the pre-C3 relay — this is precisely why C9 keeps the env
   var for one release after flipping its default.
2. **Revert the image.** The new table (`agent_run_tokens`) and the new columns
   (`via_execution_id`, the slice-D approval columns) are additive and
   defaulted, so an older binary ignores them and keeps running against the
   same database. Nothing was dropped, renamed or backfilled;
   `docs/principals.md:73-77` already establishes that a `''` principal column
   is a normal value.
3. **Clean up, optional and last.** `DELETE FROM agent_run_tokens` and, only if
   the feature is abandoned rather than paused, drop `via_execution_id` from
   `audit_events` and `work_item_events`. Agent principals may be left in
   `principals` — inert rows of kind `agent` that nothing resolves once the
   middleware branch is off — or disabled with `principals.Store.SetStatus`.

Two steps are not cleanly reversible and should be weighed at approval.
`aar_` rows created for dev-loop approvals (C1) persist; they are strictly more
information than the old free-text approver, remain readable by the old binary,
and an old binary simply ignores them. And C2's tightening of
`requireTemporalAdmin` is a genuine behaviour change: reverting it restores a
path where the service principal can perform the human approval act. If a
rollback is needed for an unrelated reason, prefer reverting C3 alone over
reverting C2.
