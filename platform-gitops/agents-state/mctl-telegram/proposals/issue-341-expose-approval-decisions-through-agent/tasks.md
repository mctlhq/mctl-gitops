# Tasks: issue-341-expose-approval-decisions-through-agent

- [ ] 1. Add `agent_approval_audit_events` schema (PG + SQLite) to
      `internal/db/agent_schema.go`, plus `Store.InsertAgentApprovalAuditEvent`
      and `Store.ListAgentApprovalAuditEvents(tenantID, approvalID)` in a new
      `internal/db/agent_approval_audit.go`, hash-chained following
      `internal/db/audit_chain.go`'s `hashAuditEntry` pattern extended with
      the new correlation fields (`workflow_id`, `approval_id`,
      `approval_revision`, `operation_id`, `tenant_id`, `account_id`,
      `agent_profile_id`, actor, `request_id`, `policy_version`,
      `proposal_hash`) — DoD: `go test ./internal/db/...` covers insert,
      chain-continuity, and tenant-scoped listing; both dialects migrate
      cleanly from an existing dev DB (idempotent re-run, no error).
- [ ] 2. Add `agent_actions.revision` column (idempotent `addColumnIfMissing`,
      default 1, incremented by every existing status-transition store
      method) (depends on 1) — DoD: `Store.UpdateAgentActionStatus` and all
      other transition methods bump `revision`; existing tests updated to
      assert monotonic increment; no behavior change to current transition
      legality rules.
- [ ] 3. Define `internal/agentapproval` package: `ApprovalView`, `Decision`,
      `Cursor`, `SignalOutcome`, `ApprovalReader`, `DecisionSignaler`
      interfaces, `ErrWorkerUnavailable`, `ErrStaleRevision`,
      `ErrTerminal`, `ErrUnknownEditField` sentinel errors (depends on 1, 2)
      — DoD: package compiles standalone with no Temporal/HTTP dependency;
      doc comments state the #340 contract assumption explicitly (mirroring
      `agentapi.OwnerProfileProvider`'s doc-comment style).
- [ ] 4. Implement the legacy `DecisionSignaler`/`ApprovalReader` adapter over
      `internal/agent/executor` and `internal/db` (agent_actions-backed) in
      `internal/agentapproval/legacy.go` (depends on 3) — DoD: `approve`/
      `reject` delegate to existing `executor.Approve`/`Reject`; `cancel`
      maps to `UpdateAgentActionStatus(..., ActionDenied)` with an audit
      note; `edit` returns a clear "not supported pre-Temporal-migration"
      422-mapped error; every call writes an audit event via task 1's store
      methods; table-driven tests cover all four decisions plus the
      stale-revision and duplicate-request-id paths against a `newTestStore`
      sqlite instance (existing test pattern).
- [ ] 5. Define the shared edit-payload schema registry
      (`action_type -> strict decode struct`, `DisallowUnknownFields`)
      reusable by both this proposal and #340, in
      `internal/agent/editvalidate` (depends on 3) — DoD: registry covers at
      least `propose_reply`'s payload shape (from
      `internal/agentapi/actions.go`'s `handleProposeReply` decode struct);
      unit tests assert unknown-field rejection and valid-payload acceptance.
- [ ] 6. Implement `internal/agentapprovalapi` HTTP layer: handlers for
      `GET /approvals/{approval_id}`, `GET /approvals`,
      `POST /approvals/{approval_id}/decision`; ownership resolution via
      `auth.From(ctx).UserID`; the full validation order from design.md
      (rate limit -> scope check -> ownership -> terminal check ->
      request_id idempotency -> revision check -> edit-schema validation ->
      signal) (depends on 3, 4, 5) — DoD: `httptest`-based tests (matching
      `internal/agentapi/server_test.go`'s style) cover 200/404/409/422/429
      cases; cross-tenant read/decision attempts return 404, not 403 or 200.
- [ ] 7. Add `agent:approvals:decide` scope support and wire the new
      per-approval rate limit via `internal/audit.RateLimiter.AllowPeerN`
      keyed on `approval_id` (depends on 6) — DoD: a caller without the
      scope gets 403 before any DB read; repeated decision attempts past the
      configured cap get 429 without reaching the signaler.
- [ ] 8. Add `AGENT_APPROVALS_API_ENABLED` config flag
      (`internal/config/config.go`, `envBool`, default false, following
      `AGENT_ENABLED`/`AGENT_KILL_SWITCH` precedent) and mount
      `/api/v1/approvals` behind it and the standard user
      `auth.Middleware(provider, true, m)` in `cmd/server/main.go`, next to
      the existing `/api/account` mount (depends on 6) — DoD: flag off by
      default leaves the route unmounted (404, not 401/403); flag on exposes
      it behind normal user auth, never the `aud=agent`/`aud=bridge`
      providers.
- [ ] 9. Wire audit events into every read path (`viewed`) in addition to the
      decision path (depends on 6) — DoD: `GET` handlers write an audit
      event; verified by a test asserting a read produces exactly one
      `viewed` row per call, scoped to the correct tenant.
- [ ] 10. Documentation: update
       `docs/plans/communication-agent.md` with a new PR entry under
       Workstream A referencing #341's implementation once merged (mirroring
       the existing PR log style), and add an `agentapprovalapi` section to
       the operational runbook (kill switch behavior, feature flag, rollout
       steps) (depends on 6, 8) — DoD: doc PR reviewed alongside the code PR,
       not deferred.

## Tests

- [ ] T1. Cross-tenant access: user A cannot `GET`/`POST decision` on user
      B's approval (404 in both cases); covered in
      `internal/agentapprovalapi` httptest suite.
- [ ] T2. Duplicate `request_id`: two identical decision submissions return
      byte-identical JSON responses and produce exactly one
      `decision_accepted`-class audit event, not two.
- [ ] T3. Stale `expected_revision`: decision against an outdated revision
      returns 409, produces a `decision_rejected_stale` audit event, and does
      not call `DecisionSignaler.Signal` (assert via a spy signaler).
- [ ] T4. Worker/backend unavailable: `DecisionSignaler` returning
      `ErrWorkerUnavailable` maps to a retryable error status (503), not 200,
      and the approval's stored state is unchanged.
- [ ] T5. Timeout: a decision request whose signal call times out is not
      silently treated as success; the audit trail reflects the ambiguous
      outcome, not a false "accepted."
- [ ] T6. Concurrent decisions: two goroutines submitting conflicting
      decisions (e.g. approve + reject) against the same revision — exactly
      one succeeds, the other gets 409, verified against the legacy adapter's
      CAS (extends existing `agent_actions.go` CAS test patterns).
- [ ] T7. Terminal-state idempotence: decisioning an already-terminal
      approval returns its terminal state and writes no new state-changing
      audit event beyond the read/attempt record.
- [ ] T8. Edit-payload schema: unknown field in `edited_payload` is rejected
      (422) before any signal is sent; valid payload for a known
      `action_type` is accepted.
- [ ] T9. Rate limiting: repeated decision attempts beyond the configured cap
      return 429 and do not reach the signaler (spy assertion).
- [ ] T10. Feature-flag-off: with `AGENT_APPROVALS_API_ENABLED=false`, the
      route is unmounted (404 at the router level), matching how
      `/api/agent/v1` is conditionally mounted today
      (`cmd/server/main.go:442-450`).
- [ ] T11. Legacy/API consistency: an approval decided via `/mctl approve`
      (Saved Messages) is correctly reflected as terminal when read via
      `GET /v1/approvals/{id}` immediately after, with no race window that
      returns stale `pending` state.

## Rollback

- The new surface is additive and flag-gated
  (`AGENT_APPROVALS_API_ENABLED`, default false): rollback is flipping the
  flag off, which unmounts the route entirely — no code revert required for
  an incident.
- The new `agent_approval_audit_events` table is append-only and has no
  foreign-key or trigger dependency from existing tables/paths — it can be
  dropped or left empty without affecting `agent_actions`/`agent_jobs`
  behavior; the Saved Messages control plane and executor are untouched by
  this proposal and continue working regardless of this table's state.
- `agent_actions.revision` is additive with a default; no existing query or
  transition logic depends on it before task 2 lands, so it is safe to leave
  in place even if the rest of the feature is rolled back.
- If the legacy `DecisionSignaler` adapter (task 4) is found to have decided
  something incorrectly, the underlying `agent_actions` row and its
  transition are still governed by the same CAS the executor and Saved
  Messages path already rely on — no new terminal state is reachable through
  the API that the existing state machine did not already define, except
  `edit` (blocked pre-#340, returns 422) and `cancel` (maps to the existing
  `ActionDenied` terminal state). Worst case is reverting the API package
  mount; no data migration/backfill is required to undo it.
- Once #340 ships and the Temporal-backed `DecisionSignaler` is wired in,
  rollback of *that specific* implementation (reverting to the legacy
  adapter) is a config/flag change per design.md's per-action selection
  mechanism, not a code rollback of #341 itself.
