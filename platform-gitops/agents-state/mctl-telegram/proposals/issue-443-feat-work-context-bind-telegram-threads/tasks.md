# Tasks: issue-443-feat-work-context-bind-telegram-threads

- [ ] 1. Add the `internal/workitem` port: `Ref`, `SurfaceRef`, `OpenRequest`,
      `ExecRequest`, the `Client` interface, the sentinels `ErrDisabled`,
      `ErrUnauthorized`, `ErrUnavailable`, and the `Disabled{}` implementation.
      — DoD: package compiles with no dependency on `internal/db` or
      `internal/agent`; `Disabled{}` returns `ErrDisabled` from all four
      methods; `go vet` and `golangci-lint` clean.

- [ ] 2. Add `internal/workitem/httpclient` (depends on 1): bounded
      `http.Client` timeout, bearer token, deterministic idempotency key sent on
      create-or-open, retry only on idempotent verbs, status mapping
      (401/403 → `ErrUnauthorized`, 5xx/timeout → `ErrUnavailable`).
      — DoD: the `Authorization` header never appears in a returned error or a
      log line; every error wraps with `fmt.Errorf("context: %w", err)`; no
      panics; context propagated through every call.

- [ ] 3. Add config (depends on 2): `WORK_CONTEXT_ENABLED` (envBool, default
      false), `WORK_CONTEXT_API_BASE_URL`, `WORK_CONTEXT_API_TOKEN`,
      `WORK_CONTEXT_API_TIMEOUT` (envDuration, default 10s),
      `WORK_CONTEXT_OPERATORS` (comma-separated Telegram ids, parsed like
      `TG_LOGIN_ADMINS`) in `internal/config/config.go`, documented in
      `.env.example`.
      — DoD: zero-value config produces the current behaviour; enabling the flag
      without a base URL fails fast at boot with a clear message rather than at
      first command.

- [ ] 4. Add `work_item_bindings` to `internal/db` (independent of 1-3): new
      file `internal/db/work_context_schema.go` with
      `migrateWorkContext(ctx, dbConn, pg)` and the
      `workContextSchemaSQLite()` / `workContextSchemaPG()` statement-list pair
      (both edited together — there is no versioned migration mechanism), the
      two unique indexes, and the `thread_id_norm COALESCE(thread_id, 0)`
      collision column; called from `Migrate` in `internal/db/db.go` next to
      `migrateAgent`.
      — DoD: migration is idempotent across repeated boots on both SQLite and
      Postgres; a pre-existing database gains the table with no `ALTER` on any
      existing table; `store_migration_test.go`-style assertions pass;
      `thread_id` is written as NULL in this slice and no existing thread/topic
      extraction is added to `internal/agent/listener/extract.go`, whose
      `evt:v1:` event-id format must stay byte-identical.

- [ ] 5. Add the store methods (depends on 4) in
      `internal/db/work_context.go`: `Binding` struct,
      `UpsertWorkItemBinding` (`INSERT ... ON CONFLICT DO NOTHING` + read-back,
      returning `created bool`), `GetWorkItemBinding`,
      `GetWorkItemBindingByWorkItem`, `SetWorkItemBindingExecution`,
      `ErrBindingNotFound`, and `purgeWorkItemBindings` registered on the
      per-user purge hook beside `purgeAgentJobs`.
      — DoD: no method accepts or stores message text; every query is scoped by
      `user_id`; concurrent `UpsertWorkItemBinding` for the same key yields one
      row and both callers read the same `work_item_id`.

- [ ] 6. Add `internal/workctx` (depends on 1, 5): `Service`, `Actor`,
      `Authorizer` (allowlist implementation that can only narrow),
      `IdempotencyKey(userID, chatTGID, threadID)`, `OpenOrResume`, `Inspect`.
      Ordering is remote-call-first, local-insert-second.
      — DoD: a `Client` failure writes no binding row; an existing non-terminal
      binding takes the `Resume` path and never `CreateOrOpen`; an unauthorized
      actor produces no outbound call.

- [ ] 7. Enqueue a reference-only envelope on binding create/execution change
      (depends on 6): extend `internal/events` with the work-context envelope
      type and subject (identifiers only), routed through the existing
      `internal/db/event_outbox.go` outbox and `internal/events/relay.go`.
      — DoD: the envelope builder reads no body/meta field; a redelivery
      produces the same envelope id; the relay drains it with no change to its
      lease logic.

- [ ] 8. Add `/mctl work` (depends on 6): `CmdWork` in
      `internal/agent/control/command.go` (argument required for a new request,
      optional for a status read) and `handleWork` in
      `internal/agent/control/router.go`, with a `WorkContext *workctx.Service`
      field on `Router`. Reply renders work id, execution id and canonical state.
      — DoD: when `WorkContext` is nil the subcommand is not offered and `/mctl
      work` yields the existing unknown-command help unchanged; pending-approval
      state is rendered read-only and no `agent_actions` row or approval code is
      created; `/mctl approve|reject` behaviour is byte-identical to today.

- [ ] 9. Add the flag-gated `get_work_context` MCP tool (depends on 5): register
      in `internal/mcp` only when `WORK_CONTEXT_ENABLED`; scope the lookup to
      `Identity.UserID`; return identifiers and surface refs only.
      — DoD: with the flag off, the tool list is byte-identical to today's seven
      tools; with it on, the handler returns no Telegram message content and no
      other user's binding.

- [ ] 10. Wire it in `cmd/server/main.go` (depends on 3, 6, 8, 9): construct
      `workitem.Disabled{}` or the HTTP client from config, build
      `workctx.Service`, attach to the `control.Router` and the MCP server.
      — DoD: with the flag off the wiring is a no-op and boot logs are unchanged;
      with it on, boot logs the base URL host (never the token).

- [ ] 11. Docs (depends on 10): document the flag, the env vars, the new table
      and the one content-bearing field (`Title`) in `README.md`, `.env.example`,
      `SECURITY.md`'s data-flow table, and `docs/runbook.md` (enable, disable,
      what an mctl-api outage looks like). Add `WORK_CONTEXT_API_TOKEN` to the
      redaction field list in `internal/audit/redact.go`.
      — DoD: `docs/runbook_test.go` passes; no emoji; English only.

## Tests

- [ ] T1. `internal/workitem`: `Disabled{}` returns `ErrDisabled` from every
      method; status-to-sentinel mapping table test for the HTTP adapter
      (200, 401, 403, 409, 500, timeout) against `httptest.Server`.
- [ ] T2. `internal/workitem/httpclient`: the bearer token never appears in any
      returned error string or wrapped error chain, asserted by scanning
      `err.Error()` for the token value.
- [ ] T3. `internal/db`: `migrateWorkContext` is idempotent — run `Migrate`
      twice on a fresh SQLite database and once more on a database created by the
      pre-change schema; assert the table and both unique indexes exist and no
      existing table was altered.
- [ ] T4. `internal/db`: `UpsertWorkItemBinding` under concurrency — N goroutines
      for the same `(user_id, chat_tg_id, thread_id)` produce exactly one row;
      exactly one reports `created=true`; all read back the same `work_item_id`.
- [ ] T5. `internal/db`: a NULL `thread_id` binding collides with itself (the
      `thread_id_norm` guard), and two bindings differing only by `thread_id` do
      not collide.
- [ ] T6. `internal/db`: deleting a user cascades away their bindings; the purge
      hook removes them for a retained user.
- [ ] T7. `internal/workctx`: `OpenOrResume` with a fake client — first call
      creates and starts an execution; second call for the same surface ref takes
      the `Resume` path, creates no second WorkItem, and returns the same
      `WorkItemID` with a new `ExecutionID`.
- [ ] T8. `internal/workctx`: a `Client` returning `ErrUnavailable` leaves zero
      rows in `work_item_bindings`; a `Client` returning `ErrUnauthorized`
      produces a refusal and zero rows.
- [ ] T9. `internal/workctx`: an actor excluded by `WORK_CONTEXT_OPERATORS` makes
      no outbound call at all (fake client asserts zero invocations); an actor in
      the allowlist still receives the platform's 403 verbatim when the fake
      client refuses — the local list narrows and never grants.
- [ ] T10. `internal/workctx`: `IdempotencyKey` is deterministic and stable across
      process restarts for the same inputs, and differs when any input differs.
- [ ] T11. `internal/agent/control`: `ParseCommand` table test for
      `/mctl work <text>`, `/mctl work`, mixed case, and the untouched existing
      subcommands; plus a golden assertion that with a nil `WorkContext` the
      reply for `/mctl work` equals today's unknown-command help string.
- [ ] T12. `internal/agent/control`: a pending-approval canonical state renders
      read-only and asserts zero `agent_actions` rows were written.
- [ ] T13. `internal/events`: the work-context envelope builder rejects any
      attempt to include body/meta, and a redelivery yields the same envelope id.
- [ ] T14. `internal/mcp`: with the flag off the registered tool list is
      unchanged; with it on, `get_work_context` returns only identifiers and
      refuses a binding belonging to another `user_id`.
- [ ] T15. Cross-surface acceptance test (the issue's pilot path), end to end
      against the contract fake: `/mctl work` creates a WorkItem and execution A
      with snapshot v1 → `get_work_context` returns those references → a resume
      call produces execution B with snapshot v2 against the same WorkItem, with
      no Telegram message content read at any step.
- [ ] T16. Regression: with `WORK_CONTEXT_ENABLED` unset, an existing-shape
      integration test of the `agent_jobs` claim/complete path and the seven MCP
      tools passes unchanged.

Test conventions to follow, as established in this repo: standard library only
(no testify, no gomock), hand-written `if got != want { t.Fatalf(...) }`
assertions, table-driven `t.Run` subtests, and in-memory SQLite stores built the
way `newTestStore` (`internal/db/store_test.go:198`) and `newToolsTestStore`
(`internal/mcp/tools_test.go:20`) build them — switching to a file-backed DSN
with `busy_timeout` for the concurrency tests T4 and T5, as
`store_access_tier_test.go:165` does.

Fixtures must use the synthetic personas already in the tests (`Alice`, `Bob`,
`Carol`, `Dana`) and synthetic numeric ids checked with `git grep` before use,
per `.claude/CLAUDE.md`. No real Telegram account, handle or id in any fixture.

## Rollback

1. **Immediate, no deploy:** set `WORK_CONTEXT_ENABLED=false` and restart. The
   MCP tool disappears from the tool list, `/mctl work` falls back to the
   existing unknown-command help, `workitem.Disabled` short-circuits every call,
   and no outbound request is made. All pre-existing behaviour returns because
   nothing else in the service reads `work_item_bindings`.
2. **Binary rollback:** revert the feature commits and redeploy the previous
   image. `work_item_bindings` is a standalone table that no prior code path
   reads or writes, so an old binary runs against the new schema unchanged. The
   table is left in place deliberately — dropping it would discard the
   correlation records that let an operator find the WorkItems already created,
   which is exactly the information needed to reconcile after a failed rollout.
3. **Data cleanup (only after reconciliation):** delete
   `work_item_bindings` rows and drop the table in a separate, explicitly
   reviewed change, after confirming the corresponding canonical WorkItems have
   been closed or re-parented in mctl-api. Nothing in this rollback path touches
   `conversations`, `incoming_events`, `agent_jobs`, `agent_actions` or the
   outbox.
4. **If the outage is mctl-api, not us:** no rollback is required. The adapter
   already degrades to a "work tracking temporarily unavailable" reply and every
   other `/mctl` subcommand, the agent job pipeline and the MCP tools keep
   working.
