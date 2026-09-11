# Tasks: issue-227-architecture-work-context-define-canonic

- [ ] 1. Write `docs/work-context-contract.md`: the canonical ownership model
      (surfaces are adapters, mctl-api owns durable work state), the ID scheme
      (`wi_`/`we_`/`cs_` + the `(engine, engine_ref)` join to
      `agent_executions.temporal_workflow_id` / `.argo_workflow_name` and
      `audit.Entry.WorkflowName`), the lifecycle transition table
      (`active`/`waiting`+`waiting_reason`, terminal `completed`/`superseded`/
      `archived`, `resumed` as an event), the durable-vs-surface-local split, the
      identity/authorization rules, the approval projection rule, and the
      idempotency/optimistic-concurrency conventions — DoD: the doc answers every
      "Required decisions" bullet of issue #227 and every acceptance-criteria
      checkbox has a named section; no code references that do not exist.
- [ ] 2. Add `internal/workitems/types.go`: `WorkItem`, `WorkItemEvent`,
      `WorkItemIntent`, `WorkItemExecution`, `ContextSnapshot`, `WorkItemApproval`,
      `SurfaceRef`, `SurfaceIdentityLink`, state/surface/engine/phase constants,
      the virtual `open` filter (mirroring `alerts.StatusActive`), the exported
      transition map, sentinel errors (`ErrNotFound`, `ErrStateConflict`,
      `ErrVersionConflict`, `ErrExecutionLive`, `ErrInvalidTransition`,
      `ErrForbiddenSurface`) — DoD: `go vet ./...` clean; every JSON tag matches
      the names used in task 1's doc; `schema_version` constant `workitem/v1`
      defined once.
- [ ] 3. Add `internal/workitems/store.go` (depends on 2): `pgxpool`-backed store
      with one `CREATE TABLE IF NOT EXISTS` schema constant for the seven tables
      and their indexes — including the partial unique indexes for
      `(tenant, external_key)` open-dedupe, one live execution per work item, one
      pending approval per work item, and the per-scope idempotency keys — plus
      `NewStore(ctx, connStr)` in the exact shape of `domains.NewStore` — DoD:
      schema applies twice in a row with no error (idempotent); no `CONCURRENTLY`
      index; no method anywhere updates or deletes a `work_item_snapshots` row.
- [ ] 4. Implement store mutations (depends on 3): `Create`, `AppendIntent`,
      `AttachExecution`, `UpdateExecutionPhase`, `AppendSnapshot`,
      `RequestApproval`, `DecideApproval`, `Transition`, `Resume`, `AddSurfaceRef`,
      `LinkSurfaceIdentity`, each in one transaction guarded by
      `pg_advisory_xact_lock(hashtext('workitem:' || id))` and each honouring its
      idempotency key with an idempotent-replay branch — copy the structure of
      `agentregistry.promote` (`internal/agentregistry/store.go:337-425`) — DoD:
      `state_version` increments exactly once per accepted transition; a replayed
      idempotency key returns the stored entity and writes no second
      `work_item_events` row.
- [ ] 5. Implement store reads (depends on 3): `Get`, `GetState` (work item +
      live execution + pending approval + latest snapshot pointers), `List`
      (tenant/state/owner filters, default `open`, limit capped at 100 defaulting
      to 20 like `agentregistry.ListExecutions`), `ListExecutions`,
      `ListSnapshots`, `ListIntents`, `ListEvents`, `ResolveSurfaceIdentity` —
      DoD: every list is deterministically ordered; no read returns
      `verification`-style secret material; limits behave as documented.
- [ ] 6. Add `internal/api/handlers_work_items.go` (depends on 4, 5): handlers for
      the routes in design.md, using `writeJSON`/`writeError`, the acting principal
      from `auth.UserFromContext` only, `user.IsAdmin()`/`user.HasTenantAccess()`
      plus `visibility` on every request, `secretscan.Scan` + 8 KiB cap on intent
      text, `Idempotency-Key` header or body field, and `expected_state_version`
      on state-changing routes (409 with current state/version on mismatch) — DoD:
      a caller-supplied actor/decider that differs from the authenticated identity
      is rejected with 400 (the `ApproveDevLoopWorkflow` rule), not ignored; the
      service principal cannot record an approval decision.
- [ ] 7. Wire approval projection (depends on 6): granting an approval whose
      `signal_engine` is `temporal` calls `opts.TemporalClient.SignalApprove` and
      marks the row `granted` only on success; a nil `TemporalClient` returns 503;
      denial and expiry never signal — DoD: signal failure leaves the approval
      `pending` and returns 502, matching `ApproveDevLoopWorkflow`'s error mapping.
- [ ] 8. Register routes in `internal/api/router.go` (depends on 6): add
      `WorkItemStore *workitems.Store` to `Options`, the nil-store startup warning
      naming the `/api/v1/work-items*` routes, mutating routes inside the existing
      20/min write group, reads outside it — DoD: all routes present in
      `internal/api/smoke_test.go`'s route walk; nil store yields 503 on every
      work-item route.
- [ ] 9. Wire the store in `cmd/api/main.go` (depends on 3, 8): `WORK_ITEMS_DB_URL`
      with `AUDIT_DB_URL` fallback, through `postgresURL` and `initStore` inside
      the existing shared `initCtx` / `storeInitBudget`, plus a
      `WORK_ITEMS_DISABLED` kill switch checked before store construction so the
      feature can be turned off without disabling the shared `AUDIT_DB_URL`
      fallback other stores rely on — DoD: startup with both vars unset logs the
      warning and stays healthy; `WORK_ITEMS_DISABLED=true` leaves
      `WorkItemStore` nil even when a DB URL is present; startup with a reachable
      DB still completes inside the 8 s budget.
- [ ] 10. Add the retention sweeper (depends on 9): one ticker goroutine honouring
      `WORKITEM_SURFACE_RETENTION_DAYS` (default 90; purges intent text and surface
      refs, keeps the item and its correlations) and `WORKITEM_RETENTION_DAYS`
      (default 365; purges terminal items) — DoD: sweeper is a no-op when the store
      is nil; deletion counts are logged with `slog` at info.
- [ ] 11. Audit integration (depends on 6): `h.logAudit` on every mutating
      work-item operation with `work_item_id` in `Parameters` and the operation
      names `work-item-create`, `work-item-transition`, `work-item-resume`,
      `work-item-approval-decide`, `work-item-surface-link` — DoD: no intent text
      and no surface external ID appears in any audit parameter.
- [ ] 12. Publish the contract in `internal/openapi/openapi.yaml` (depends on 6):
      new paths and `WorkItem`, `WorkItemEvent`, `WorkItemIntent`,
      `WorkItemExecution`, `ContextSnapshot`, `WorkItemApproval`, `SurfaceRef`
      schemas, each with `schema_version` documented as `workitem/v1` — DoD: spec
      parses as valid OpenAPI 3.0; every implemented route and field is present and
      no route is documented that does not exist.
- [ ] 13. Document configuration (depends on 9, 10): add `WORK_ITEMS_DB_URL`,
      `WORK_ITEMS_DISABLED`,
      `WORKITEM_SURFACE_RETENTION_DAYS` and `WORKITEM_RETENTION_DAYS` to
      `README.md`'s env table and `.env.example`, and note the pre-existing gap
      that `ALERT_DB_URL`, `AGENT_REGISTRY_DB_URL` and `OAUTH_DB_URL` are also
      undocumented there — DoD: every env var the new code reads is in both files.
- [ ] 14. Open a follow-up issue for the MCP tool wrappers and the first surface
      adapter (`mctl-telegram`), explicitly listing the coordinated updates any new
      tool requires: `internal/mcp/server_test.go` `TestNewMCPServer_ToolCount`,
      `internal/mcp/annotations_test.go` `recordedHints`, and
      `docs/portal-allowlist.json` guarded by
      `internal/mcp/portal_allowlist_test.go` — DoD: issue filed and linked from
      #227 and from `docs/work-context-contract.md`.

## Tests

- [ ] T1. `internal/workitems/store_test.go` — Postgres-backed, skipped when
      `TEST_DATABASE_URL` is unset (the convention in `alerts/store_test.go:32`,
      `domains/store_test.go:33`, `agentregistry/store_test.go:32`). Covers:
      create -> state `active`; schema applied twice is a no-op.
- [ ] T2. Lifecycle table test: every allowed transition succeeds and bumps
      `state_version` by exactly one; every disallowed transition returns
      `ErrInvalidTransition` and leaves state and version untouched; `resume`
      moves `waiting` -> `active` and writes a `resumed` event.
- [ ] T3. Immutability: append snapshots v1 and v2 across two executions, assert
      v1's `snapshot_json`, `content_hash` and `created_at` are byte-identical
      afterwards, and assert by reflection over the store's method set that no
      exported method name mutating snapshots exists.
- [ ] T4. Idempotency: replaying the same `Idempotency-Key` on create, intent
      append, execution attach, snapshot append and resume returns the original
      entity with no duplicate row and no extra `work_item_events` row.
- [ ] T5. Optimistic concurrency: a stale `expected_state_version` returns 409
      with the current state and version; two concurrent goroutines transitioning
      the same item produce exactly one success and one 409.
- [ ] T6. Cross-surface dedupe: two creates with the same `(tenant, external_key)`
      from different surfaces converge on one work item; the same pair after the
      first item reaches a terminal state creates a new one.
- [ ] T7. One-live-execution invariant: attaching a second execution while one is
      non-terminal returns 409 carrying the live execution's `(engine, engine_ref)`.
- [ ] T8. `internal/api/handlers_work_items_test.go` authorization matrix: admin,
      same-tenant member, other-tenant member, owner of a `private` item, and the
      service principal, across read / intent / transition / approval-decision;
      asserts the service principal is forbidden from deciding approvals and that
      a body-supplied decider mismatching the caller yields 400.
- [ ] T9. Surface identity: an unlinked `(surface, external_id)` cannot be used to
      attribute or resume work; linking requires an authenticated call from the
      principal; `telegram_owner_ids` values grant nothing.
- [ ] T10. Content gates: intent text over the 8 KiB cap returns 400, a snapshot
      over the 256 KiB cap returns 413, and text containing a `secretscan` pattern
      returns 400 without being persisted.
- [ ] T11. Approval projection: a fake `DevLoopClient` returning an error leaves
      the approval `pending` with a 502; success flips it to `granted` with
      `decided_by` equal to the authenticated caller.
- [ ] T12. Nil store: every `/api/v1/work-items*` route returns 503 and the startup
      warning names those routes (extend `internal/api/smoke_test.go`).
- [ ] T13. Retention sweeper: intents and surface refs past the surface cutoff are
      deleted while the work item, its executions and its snapshots survive;
      terminal items past the item cutoff are deleted.
- [ ] T14. Guardrails: `go test ./...`, `go vet ./...`, `golangci-lint run`, and
      confirm `internal/mcp/server_test.go` `TestNewMCPServer_ToolCount` and
      `internal/mcp/portal_allowlist_test.go` still pass unchanged (no MCP tools
      added by this proposal).

## Rollback

The change is additive and gated at three independent levels, so rollback needs no
data migration:

1. **Config-level (fastest, no deploy).** Set `WORK_ITEMS_DISABLED=true` (a single
   guard checked before store construction in task 9, added precisely so the
   feature can be switched off without also disabling the shared `AUDIT_DB_URL`
   fallback that alerts, domains and the agent registry depend on).
   `WorkItemStore` becomes nil, every `/api/v1/work-items*` route returns 503 with
   the startup warning, and no other route or store is affected.
2. **Deploy-level.** Roll the mctl-api image back one tag
   (`mctl_rollback_service`). The new tables remain but are unreferenced; nothing
   else reads them.
3. **Schema-level (only if the tables must go).** Drop `work_item_snapshots`,
   `work_item_approvals`, `work_item_executions`, `work_item_intents`,
   `work_item_events`, `work_item_surface_refs`, `surface_identity_links`, then
   `work_items`, in that order (children first — they carry the FKs). No existing
   table is altered by this proposal, so nothing else needs reverting.

Partial rollback is also possible: keep the store and routes but revert task 7
(approval projection) so approvals stay purely informational records, leaving the
existing `POST /api/v1/agents/dev-loop/{workflow_id}/approve` path as the only way
to grant a dev-loop approval — exactly the behaviour before this change.
