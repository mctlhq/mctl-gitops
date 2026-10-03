# Tasks: issue-428-feat-unified-identity-delegation-grants

Slice B of the accepted proposal
`issue-376-feat-unified-identity-represent-agent-ac` (tasks.md B1-B3). Slice A
landed in #423; Slices C and D are out of scope. Every task leaves `main`
working: nothing below changes the behaviour of a request that does not send
`X-MCTL-On-Behalf-Of`, except task 6's body-key refusal.

## B1 — the grant resolver

- [ ] 1. Add `internal/delegation/delegation.go`: the `Grant`, `Record`,
  `Resolver`, `WorkItemSource` and `SurfaceLinkSource` types, the four `Kind*`
  constants keyed on the `xr_` / `aar_` / `wi_` / `sil_` prefixes, and
  `ErrNotBound` / `ErrSubjectUnresolved` / `ErrUnavailable`. The package imports
  `internal/auth` (for `auth.AgentRun`) and nothing else from `internal/`; it
  holds no SQL and no pool, the same posture `auth.AgentRunResolver`
  (`internal/auth/agent.go:63-69`) takes. — DoD: `go build ./...` clean;
  `Resolve(ctx, ref string, bound auth.AgentRun) (Grant, error)` is the only
  entry point and takes no third argument through which a caller-supplied
  subject could enter.

- [ ] 2. Add the four narrow store projections (depends on 1):
  `workitems.Store.ExecutionRequestGrant(ctx, itemID, id)`,
  `ActionApprovalGrant(ctx, id)`, `WorkItemGrant(ctx, id)` and
  `SurfaceRefBound(ctx, itemID, surface, actorExternalID)`, each a purpose-built
  `SELECT` returning only `delegation.Record`'s fields. Do **not** touch
  `executionRequestColumns` (`internal/workitems/execution_requests.go:161-164`),
  `actionApprovalColumns` (`action_approvals.go:135-137`) or `itemColumns`
  (`store.go:137`) — widening those is D1 and changes public read payloads.
  Add `surfaceid.Store.LinkByID(ctx, id)` returning
  `(surface, externalID, principal, error)` and reusing the existing
  revoked/expired checks so it yields `ErrLinkRevoked` / `ErrLinkExpired` /
  `ErrLinkNotFound` like `Resolve` (`internal/surfaceid/store.go:459-483`). —
  DoD: `go test ./internal/workitems/... ./internal/surfaceid/...` passes, every
  existing read payload is unchanged, and each projection returns the
  `*_principal_id` column verbatim including `''`.

- [ ] 3. Add `delegation.StoreResolver` implementing `Resolver` (depends on 1,
  2). Dispatch on the ref prefix; an unrecognised prefix is `ErrNotBound` with
  no store call. Load `xr_` with `bound.WorkItemID` as `itemID` so
  `getExecutionRequest`'s `AND work_item_id=$2` narrowing
  (`execution_requests.go:216-224`) carries half the binding. Map a not-found
  row and a revoked/expired link to `ErrNotBound`, and any other store error to
  `ErrUnavailable`. Enforce binding as
  `(rec.ExecutionID != "" && rec.ExecutionID == bound.ExecutionID) ||
  (rec.WorkItemID != "" && rec.WorkItemID == bound.WorkItemID)`; for `sil_`
  enforce it via `SurfaceRefBound(bound.WorkItemID, link.surface,
  link.externalID)` instead. Refuse `rec.SubjectPrincipalID == ""` with
  `ErrSubjectUnresolved` and write no fallback branch to `rec.Subject`. — DoD:
  `go test ./internal/delegation/...` passes with fakes; `grep` shows no code
  path in the package that assigns `SubjectPrincipalID` from anything but a
  source `Record`.

## B2 — the gate

- [ ] 4. Add `auth.NewDelegatedUser(login string, groups []string, acting
  *User) *User` in `internal/auth/oidc.go` next to `NewRelayedUser`
  (`:334-349`) (depends on nothing). Returns nil unless `acting.AgentName()` is
  true and `login != ""`. Filters `admins` out of groups. Sets `ID`, `Groups`,
  `githubLogin: true`, `actingPrincipal = AgentPrincipalPrefix + name`,
  `viaPrincipalID = acting.principalID`, and carries `execID`, `workItemID`,
  `runID` from `acting`. Sets neither `agent` nor `relaySurface`. — DoD:
  `go test ./internal/auth/...` passes with cases proving the result has
  `IsAgent() == false`, `Identity().Kind == auth.KindHuman`, no `admins` in
  `Groups` even when the input has it, `ActingPrincipal() == "agent:<name>"`,
  and a non-empty `ExecutionID()`.

- [ ] 5. Add `internal/api/handlers_agent_identity.go` with `OnBehalfOfHeader
  = "X-MCTL-On-Behalf-Of"`, the five typed codes, `delegationRoutes`, the
  `refuseDelegation` audit helper, and `agentPrincipalGate` (depends on 3, 4).
  Follow `surfacePrincipalGate`'s order
  (`handlers_surface_identity.go:121-171`): pass through with no user or no
  header; 400 `delegation_not_accepted` when `user.AgentName()` is false; 400
  `delegation_not_supported` off `delegationRoutes`; 503
  `delegation_unavailable` when `h.opts.Delegation == nil`; resolve, mapping
  `ErrNotBound` -> 403 `grant_not_bound`, `ErrSubjectUnresolved` -> 403
  `grant_subject_unresolved`, `ErrUnavailable` -> 503; strip `github:` as
  `relaySubject:208-211` does and refuse anything else as
  `grant_subject_unresolved`; resolve tenants with a failed lookup granting
  none (`relaySubject:213-221`); build the subject with `NewDelegatedUser`; run
  `auth.AttachPrincipal` and **fail closed** on every error (403 for
  `ErrPrincipalDisabled` / `ErrIdentityRefused`, 503 otherwise); cross-check
  `subject.PrincipalID()` against `grant.SubjectPrincipalID` and refuse a
  mismatch as `grant_subject_unresolved`; then
  `next.ServeHTTP(w, r.WithContext(auth.WithUser(ctx, subject)))`. Every refusal
  writes exactly one `agent_identity.delegation_refused` audit entry carrying
  `acting_principal`, `agent`, `grant_ref`, `route` and `reason`. Add the
  `Delegation delegation.Resolver` field to `api.Options`
  (`router.go:113-122`), mount `r.Use(h.agentPrincipalGate)` immediately after
  `r.Use(h.surfacePrincipalGate)` (`router.go:321`), and wire the resolver in
  `cmd/api/main.go` beside the principal resolver. — DoD: table-driven tests in
  `handlers_agent_identity_test.go` cover every refusal code, prove a delegated
  request never carries `admins`, prove an agent without the header is
  unaffected, and prove one audit row per refusal.

## B3 — body-field refusal

- [ ] 6. Add `"acting_principal"` to `forbiddenIdentityFields`
  (`internal/api/handlers_work_items.go:64-70`) — `on_behalf_of`, `subject` and
  `delegated_actor` are already in the list — and add
  `refuseIdentityFields(w, r, limit) bool` next to it, modelled on
  `refuseExecutionIdentity` (`handlers_execution_requests.go:58-76`): read with
  `readWorkItemBody`, check the keys, `restoreBody(r, raw)`, tolerate an empty
  body, and on a non-object body restore and return true so the existing
  decoder still produces today's error (depends on 5 for the allowlist). Call
  it at the top of `ApproveDevLoopWorkflow` (`handlers_dev_loop.go:320`) and
  `RespondHumanInput` (`handlers_human_input_response.go:490`); every other
  route named in this proposal already decodes through
  `decodeWorkItemBodyLimit` (`handlers_agent_run_tokens.go:118` included) and
  needs no call site. Change nothing else on those two routes — the approve
  route's `approver == user.ID` tolerance (`handlers_dev_loop.go:325-329`), its
  `requireTemporalAdmin` check and its EOF tolerance all belong to Slice C. —
  DoD: a body carrying any of the four keys is 400 on
  `POST /api/v1/agent-run-tokens`, on
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` and on every route in
  `delegationRoutes`; existing dev-loop and human-input tests pass unchanged.

- [ ] 7. Document and finish (depends on 1-6). Add the delegation section to
  `docs/agent-identity.md` (or create it if Slice A did not): the one
  subject-derivation rule, the `delegationRoutes` allowlist verbatim, the five
  refusal codes with their statuses, and a runbook note that delegated agent
  work fails closed during a principal-store outage while every other path
  degrades. Add the header and the refusal codes to the allowlisted paths in
  `internal/openapi/openapi.yaml` (no new path). — DoD: `go fmt`, `go vet
  ./...` and `golangci-lint` clean; `internal/mcp/server_test.go`'s
  `TestNewMCPServer_ToolCount` untouched; `cd e2e && go test -v` passes.

## Tests

- [ ] T1. `internal/delegation`: a run token bound to execution A presenting a
  grant bound to execution B is `ErrNotBound`. Table over all four kinds
  (`xr_`, `aar_`, `wi_`, `sil_`), each with a bound and an unbound case.
- [ ] T2. `internal/delegation`: **mint context vs. grant disagreement.** A run
  token minted on `wi_X` whose `owner_principal_id` is Alice, presenting an
  `xr_` bound to `wi_X` but `requested_by` Bob, resolves to **Bob**; the test
  asserts Alice's principal id appears nowhere in the returned `Grant`. The
  work item is the binding scope, the grant is the authority.
- [ ] T3. `internal/delegation`: a grant whose `*_principal_id` is `''` is
  `ErrSubjectUnresolved`, never a fallback to the adjacent principal string.
  One case per kind.
- [ ] T4. `internal/delegation`: an unknown ref, an unrecognised prefix, and a
  ref whose row exists but belongs to another run all return the **same**
  `ErrNotBound`, so the route is not an existence oracle. A source returning an
  unexpected error returns `ErrUnavailable`, never `ErrNotBound`.
- [ ] T5. `internal/delegation`: a `sil_` grant is bound only when
  `SurfaceRefBound` is true for the run token's work item; a revoked link and an
  expired link are both `ErrNotBound`.
- [ ] T6. `internal/auth`: `NewDelegatedUser` returns nil for a non-agent
  acting user and for an empty login; drops `admins`; yields `IsAgent() ==
  false`, `IsAdmin() == false`, `Identity().Kind == KindHuman`,
  `ActingPrincipal() == "agent:<name>"`, `ViaPrincipalID()` equal to the
  agent's `prn_`, and a preserved `ExecutionID()` / `WorkItemID()` /
  `AgentRunID()`.
- [ ] T7. `internal/api`: `X-MCTL-On-Behalf-Of` sent by a human, a surface
  principal, a relayed subject, the `mctl-agent` service principal, the usage
  writer and the evidence writer is 400 `delegation_not_accepted`; sent by an
  agent on a non-allowlisted route it is 400 `delegation_not_supported`. Every
  refusal writes exactly one `agent_identity.delegation_refused` audit row
  carrying the typed reason.
- [ ] T8. `internal/api`: a disabled subject principal is 403, a refused
  identity is 403, and an otherwise-failing `AttachPrincipal` is 503 — proving
  delegation fails closed where `relaySubject:236` degrades.
- [ ] T9. `internal/api`: a successful delegated write records the subject's
  `prn_` in `actor_principal_id`, `agent:<name>` in `acting_principal` and the
  agent's `prn_` in `via_principal_id`, and the bound `we_...` in
  `via_execution_id` — on both `work_item_events` and `audit_events`, in exactly
  one row each.
- [ ] T10. `internal/api`: `h.opts.Delegation == nil` makes a request **with**
  the header 503 and a request **without** it succeed unchanged.
- [ ] T11. `internal/api`: a body carrying `on_behalf_of`, `subject`,
  `delegated_actor` or `acting_principal` is 400 on
  `POST /api/v1/agent-run-tokens`, on the dev-loop approve route and on every
  `delegationRoutes` entry that takes a body; an empty approve body and a
  `{"approver": "<caller>"}` approve body still behave exactly as they do today.
- [ ] T12. Regression: every existing test in
  `internal/api/handlers_surface_identity_test.go`,
  `handlers_surface_relay_test.go`, `handlers_action_approvals_test.go`,
  `handlers_agent_run_tokens_test.go`, `handlers_dev_loop_test.go`,
  `handlers_human_input_response_test.go` and
  `internal/workitems/principal_ids_test.go` passes unchanged — the delegation
  path must not alter the surface, approval or agent-run-token contracts.
- [ ] T13. `e2e`: mint an `art_` run token for an execution, create an `xr_`
  requested by a linked human on the same work item, call an allowlisted route
  with `X-MCTL-On-Behalf-Of: <xr_>`, and assert the resulting `audit_events`
  row has `user_principal_id` = the human and `via_principal_id` = the agent
  (actor != subject).

## Rollback

Every change is additive and reachable only by a request that sends
`X-MCTL-On-Behalf-Of`, so rollback is staged and needs no data migration.

1. **Fastest, no deploy.** Unset the `Delegation` wiring in `cmd/api/main.go`
   via config, or roll the previous image: with `h.opts.Delegation == nil`
   every delegated request is 503 `delegation_unavailable` and every
   undelegated request — which is all traffic today, since the worker-side
   sender is C7 and out of scope — is untouched.
2. **Remove the gate.** Delete the single `r.Use(h.agentPrincipalGate)` line at
   `router.go:321+`. The header then reaches handlers, which ignore it, and
   behaviour returns exactly to #423's. `internal/delegation` and
   `NewDelegatedUser` become dead code with no runtime effect.
3. **Revert B3 alone** if the body check is what breaks a client: drop
   `"acting_principal"` from `forbiddenIdentityFields` and remove the two
   `refuseIdentityFields` call sites. Nothing else depends on them.
4. **Full revert.** `git revert` the slice. No schema was created and no column
   was added, so there is nothing to migrate back: the four `*_principal_id`
   columns the resolver reads predate this work (#373) and keep being written by
   Slice A. Audit rows with `operation = 'agent_identity.delegation_refused'`
   remain as history, which is the intended behaviour for an append-only trail.
