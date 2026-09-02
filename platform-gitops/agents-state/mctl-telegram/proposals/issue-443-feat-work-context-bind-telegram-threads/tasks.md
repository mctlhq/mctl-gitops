# Tasks: issue-443-feat-work-context-bind-telegram-threads

- [ ] 1. Add `internal/workcontext` package: `PlatformClient` interface,
      `OpenWorkItemRequest`/`WorkItemRef` types, `ErrPlatformNotConfigured`
      sentinel, and a no-op client returned when unconfigured — DoD: package
      compiles standalone with no dependency on `internal/db` or
      `internal/agent/*`; unit tests cover the no-op client's error path.
- [ ] 2. Implement `httpPlatformClient` in `internal/workcontext` following
      `internal/agentworker/client.go`'s shape (constructor trims trailing
      slash, injectable `*http.Client`, typed `APIError` for non-2xx,
      explicit request timeout) — DoD: `OpenWorkItem`/`GetWorkItem` build
      requests against a documented (assumed) `mctl-api` route shape behind
      the interface from task 1; httptest-server unit tests cover 2xx,
      4xx/`APIError`, and timeout/context-cancellation behavior. Marked
      explicitly in code comments as pending confirmation against the real
      `mctl-api#227` contract once published.
- [ ] 3. Add `MCTL_API_BASE_URL` and `MCTL_API_WORKER_TOKEN` to
      `internal/config/config.go` (both optional, empty default) (depends on
      1) — DoD: `config_test.go`-style coverage confirms both empty by
      default and both required together (one set without the other is a
      config validation error, not a half-configured client).
- [ ] 4. Add `work_context_bindings` table to both SQLite and Postgres blocks
      in `internal/db/agent_schema.go`'s `migrateAgent`, additive only
      (depends on nothing, can land independently) — DoD: `go test
      ./internal/db/...` passes against both drivers (see existing
      `agent_schema_test.go` pattern for dual-dialect migration tests);
      running `migrateAgent` twice is still a no-op (`IF NOT EXISTS`).
- [ ] 5. Add `internal/db/work_context.go`: `WorkContextBinding` struct,
      `UpsertWorkContextBinding` (upsert on `(user_id, idempotency_key)`,
      also enforcing the `(user_id, chat_tgid, saved_peer_tgid)` uniqueness),
      `GetWorkContextBindingByThread`, `GetWorkContextBindingByWorkItemID`
      (depends on 4) — DoD: unit tests cover create, idempotent re-upsert
      with the same key (no duplicate row, fields refreshed), and the
      not-found path returning a typed error (mirrors
      `db.ErrConversationNotFound`).
- [ ] 6. Compute the deterministic idempotency key (hash of
      `user_id, chat_tgid, saved_peer_tgid`, normalized topic text) reusing
      the hashing approach already used by
      `internal/agent/listener/extract.go`'s `eventIDForMessage` (depends on
      nothing) — DoD: pure function, table-driven tests confirm same inputs
      always produce the same key and distinct topics/threads never collide
      for realistic inputs.
- [ ] 7. Thread the resolved `*auth.Identity` (not just `userID`) through
      `listener.CommandRouter.HandleSavedText` so the router can read
      `TelegramID`/`Subject` for the `Actor` field, updating
      `internal/agent/listener/listener.go`'s call site and the
      `control.Router` and any test fakes implementing `CommandRouter`
      (depends on nothing, but should land before 8 to avoid rework) — DoD:
      existing `/mctl` commands (status/leads/show/continue/pause/takeover/
      approve/reject) unaffected; `listener_test.go` and
      `router_test.go` updated and passing.
- [ ] 8. Add `CmdInvestigate` and `CmdWork` to
      `internal/agent/control/command.go`'s `ParseCommand` (topic/id as
      trailing arg, `CmdWork` argument optional) and extend the
      unknown-command help text (depends on 7) — DoD: `command_test.go`
      covers both new subcommands, case-insensitivity, missing-arg behavior
      for `investigate` (required) vs. optional-arg behavior for `work`.
- [ ] 9. Implement `Router.handleInvestigate` and `Router.handleWork` in
      `internal/agent/control/router.go`: resolve/create binding (task 5),
      call `PlatformClient.OpenWorkItem`/`GetWorkItem` (task 1/2), map
      `ErrPlatformNotConfigured` and platform 401/403 to distinct
      owner-facing replies, render `WorkItemRef` (id, execution id, status,
      resume URL) via `Notifier.Reply` (depends on 5, 6, 8) — DoD:
      `router_test.go` covers: fresh thread creates a binding; repeated
      identical command on the same thread reuses it (no second
      `OpenWorkItem` call assumed-new, same idempotency key sent); unconfigured
      client produces the "not configured" reply; simulated 403 produces the
      authorization-failure reply without setting any local approval state.
- [ ] 10. Wire `workcontext.New` construction and `Router` field in
      `cmd/server/main.go` next to the existing agent wiring (depends on 2,
      3, 9) — DoD: server boots with `MCTL_API_BASE_URL` unset (feature
      inert) and with it set against a fake server in an integration-style
      test; no change to any other route registration.
- [ ] 11. Update `docs/plans/communication-agent.md` or add a short
      `docs/plans/work-context.md` pointer noting this pilot's status and
      linking back to issue #443 and the roadmap issue `mctlhq/.github#21`
      (depends on 9) — DoD: doc committed, cross-links resolve, matches the
      status-log style already used in the communication-agent plan doc.

## Tests

- [ ] T1. Unit: `workcontext` no-op and `httpPlatformClient` paths (2xx,
      4xx, timeout) — covers task 1-2.
- [ ] T2. Unit: `migrateAgent` idempotent re-run and dual-dialect coverage
      for `work_context_bindings` — covers task 4.
- [ ] T3. Unit: `db.UpsertWorkContextBinding`/getters, including the
      idempotent-upsert-does-not-duplicate case — covers task 5.
- [ ] T4. Unit: idempotency-key determinism and collision-avoidance
      table tests — covers task 6.
- [ ] T5. Unit: `ParseCommand` for `investigate`/`work` — covers task 8.
- [ ] T6. Unit: `Router.handleInvestigate`/`handleWork` against a fake
      `PlatformClient`, including the "repeated command, same thread, no
      duplicate WorkItem" scenario called out in the acceptance criteria —
      covers task 9.
- [ ] T7. Integration: full path from a synthetic Saved Messages update
      through `listener` → `Router` → fake platform server → binding row in
      SQLite, asserting exactly one binding row and one `OpenWorkItem` call
      after two duplicate deliveries of the same message id — covers
      tasks 4-10 together and the "already-open work items idempotently"
      acceptance criterion end to end within this repo's boundary.
- [ ] T8. Regression: existing `router_test.go`/`command_test.go`/
      `listener_test.go` suites for the pre-existing `/mctl` subcommands
      pass unchanged in behavior (only the `HandleSavedText` signature
      changes per task 7) — covers backward compatibility.

## Rollback

- The feature is gated by `MCTL_API_BASE_URL`/`MCTL_API_WORKER_TOKEN`: unset
  either in the deployment config to instantly disable `/mctl investigate`
  and `/mctl work` (they revert to the "not configured" reply) without a
  code rollback or redeploy, and without affecting any other `/mctl`
  command.
- If a code rollback is needed anyway, reverting the PR(s) for tasks 6-11 is
  safe on its own: task 4's migration is additive-only and can be left in
  place (an unused empty table) even if the rest is reverted, avoiding a
  destructive down-migration on a shared database. If the table must be
  removed, `DROP TABLE IF EXISTS work_context_bindings` is safe since no
  other table has a foreign key into it (correlation ids are stored as
  opaque strings, not joined against).
- No data migration/backfill was performed, so rollback never has to
  reconcile diverged state — the table is either empty (never used) or
  contains only correlation rows that are safe to lose (the canonical
  WorkItem state lives in `mctl-api`, not here).
