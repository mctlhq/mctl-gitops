# Tasks: issue-443-feat-work-context-bind-telegram-threads

Ordered so every step is independently reviewable and the tree stays green.
Tasks 1-4 are dark (nothing calls them); the surface only lights up at task 8,
and only behind `WORK_CONTEXT_ENABLED`.

- [ ] 1. Add `work_item_bindings` to the schema — append the SQLite statements
  to `agentSchemaSQLite()` (`internal/db/agent_schema.go:278`) and the
  byte-parallel Postgres twin to `agentSchemaPG()` (`:527`), following the
  `bot_updates` template (`internal/db/db.go:703` / `:948`): prose comment on
  the SQLite copy, "see the sqliteSchema comment" on the PG copy.
  Columns: `id`, `user_id` (`REFERENCES users(id) ON DELETE CASCADE`),
  `chat_tg_id`, `root_tg_message_id`, `work_item_id`, `external_key`,
  `last_state`, `last_state_version`, `last_execution_id`, `created_at`,
  `updated_at`. Two unique indexes: `idx_work_item_bindings_thread` on
  `(user_id, chat_tg_id, root_tg_message_id)` and
  `idx_work_item_bindings_item` on `(user_id, work_item_id)`.
  — DoD: `Migrate` succeeds on a fresh SQLite DB and on an existing Postgres
  DB; the table has no column that can hold message text, a title or a peer
  handle; `INTEGER`/`BIGINT` and `DATETIME`/`TIMESTAMPTZ` split matches the
  house convention.

- [ ] 2. Add the binding store (depends on 1) — new
  `internal/db/work_item_bindings.go` in the `agent_saved_commands.go` style:
  `GetWorkItemBinding`, `LatestWorkItemBinding`, `UpsertWorkItemBinding`,
  `TouchWorkItemBindingState`. `$N` placeholders only, `time.Now().UTC()`
  written from Go rather than `DEFAULT CURRENT_TIMESTAMP`, `sql.ErrNoRows`
  translated to a `found bool`, errors wrapped `fmt.Errorf("verb noun: %w", err)`.
  — DoD: methods compile, are `*Store` receivers, and pass the dual-dialect
  tests from T1.

- [ ] 3. Add `Store.TelegramIDByUserID` (independent of 1-2) — the reverse of
  `UserIDByTelegramID` (`internal/db/store.go:244`), returning a `found bool`
  rather than an error for a user with no Telegram id.
  — DoD: returns the id for a user created via `EnsureUserByTelegramID`, and
  `found=false` (not an error) for a user without one.

- [ ] 4. Add `internal/workctx` — the mctl-api client, modelled on
  `internal/agentworker/client.go:41-98`. `client.go` with `Client` and the
  unexported `relay(ctx, method, path, actorTGID, idemKey, body, out)` setting
  exactly `Authorization`, `X-MCTL-Surface-Actor` and `Idempotency-Key`;
  the six public methods `RedeemLink`, `CreateWorkItem`, `GetWorkItem`,
  `AppendIntent`, `Resume`, `AddSurfaceRef`. `envelope.go` with the
  `workitem/v1` types and a decoder that rejects any other `schema_version`.
  `errors.go` with the sentinels (`ErrLinkNotFound`, `ErrLinkRevoked`,
  `ErrLinkExpired`, `ErrRelayRequired`, `ErrChallengeInvalid`,
  `ErrLinkConflict`, `ErrActorNotAccepted`, `ErrStateVersionConflict`).
  Request structs carry no actor-shaped field and no caller-settable
  `origin_surface`.
  — DoD: the package builds standalone; `go doc ./internal/workctx` shows only
  the six routes from `docs/contracts/mctl-api-work-context.md:39-46`; no
  method constructs a path containing `executions`, `snapshot`, `snapshots`,
  `events` or `approvals`.

- [ ] 5. Add the deterministic key helpers (depends on 4) — `ExternalKey(chatTGID,
  rootMsgID) string` returning `tg:v1:<chat>:<msg>`, and `IdempotencyKey(externalKey,
  op string, stateVersion int64) string`.
  — DoD: pure functions with no I/O, stable across process restarts, covered by
  table tests.

- [ ] 6. Widen the Saved Messages router context (depends on 3) — introduce
  `control.SavedMeta{UserID, SelfTGID, ChatTGID, TGMessageID}`, change
  `listener.CommandRouter` and `Router.HandleSavedText`
  (`internal/agent/control/router.go:44`) to take it, and thread the values the
  listener already has (`internal/agent/listener/extract.go:63`,
  `db.IncomingEvent.MessageID`) through the dispatch path. Update the fakes in
  `listener_test.go` and `router_test.go`.
  — DoD: `go build ./...` and `go test ./...` pass; the nine existing `/mctl`
  subcommands are untouched in parsing and reply text; `SelfTGID` is non-zero
  for a Saved Messages command in an integration-shaped listener test.

- [ ] 7. Parse the new subcommands (depends on 6) — add `CmdWork` and `CmdLink`
  to `internal/agent/control/command.go` plus a `Sub string` field on `Command`
  populated only for `work` (`status`, `note`, `resume`, or empty meaning
  create/open). Keep `ParseCommand` pure.
  — DoD: existing `command_test.go` cases pass unchanged and the parse result
  for all nine old subcommands has an empty `Sub`; `/mctl work`, `/mctl work
  status`, `/mctl work note <text>`, `/mctl work resume`, `/mctl link <code>`
  parse as specified; `/mctl work note` with no argument returns `ErrMissingArg`.

- [ ] 8. Add the work handlers (depends on 2, 4, 5, 7) — new
  `internal/agent/control/work.go` with `WorkHandler{Store, Client, Notifier}`
  and one method per subcommand. Actor resolution: use `SavedMeta.SelfTGID`,
  cross-check against `Store.TelegramIDByUserID`, and fail closed with no
  mctl-api call on mismatch or absence. Create/open reuses the binding when
  `last_state` is `active` or `waiting` and creates a fresh item otherwise.
  Resume does `GetWorkItem` → `Resume` with `expected_state_version`, and on
  `ErrStateVersionConflict` re-reads and retries exactly once. Errors are
  rendered as owner-facing text in the style of `approverErrText`
  (`router.go:359`). Add a nilable `Work *WorkHandler` field to `Router` and
  dispatch to it; when nil, fall through to the existing unknown-command reply.
  — DoD: every branch replies to the owner exactly once; no handler ever
  returns an error that would stall the listener; no code path reads
  `TGLoginAdmins`, `TGLoginClients` or `AutoApproveClients` for attribution.

- [ ] 9. Add config and redaction (depends on 4) — `WorkContextEnabled`
  (`envBool("WORK_CONTEXT_ENABLED", false)`), `MCTLAPIBaseURL`
  (`MCTL_API_BASE_URL`, default `https://api.mctl.ai`),
  `MCTLSurfaceTelegramToken` (bare `os.Getenv`, like `TG_API_HASH` at
  `config.go:288`) and `WorkItemTenant` (`MCTL_WORK_ITEM_TENANT`) in
  `internal/config/config.go`, with an inline `Load` validation block in the
  style of `config.go:345-349`. Add `mctl_surface_telegram_token` to
  `sensitiveKeys` (`internal/audit/redact.go:30`). Document all four
  commented-out in `.env.example` with defaults shown.
  — DoD: `Load()` errors when the flag is on and the token or tenant is empty,
  and succeeds unchanged when the flag is off; a `slog` attr named
  `mctl_surface_telegram_token` renders redacted.

- [ ] 10. Wire it up (depends on 8, 9) — in `cmd/server/main.go`, next to the
  `cfg.AgentEnabled` block (`:566`), construct the `workctx.Client` and assign
  `agentRouter.Work` only when `cfg.WorkContextEnabled`. Log the flag state
  alongside the existing `slog.Info` startup summary (`:940`). Add
  `WorkContextRequestsTotal{route,outcome}` and
  `WorkContextBindingsTotal{result}` to `internal/metrics/metrics.go`.
  — DoD: with the flag off, the server starts with no client constructed and
  `/mctl work` returns today's unknown-command reply; with it on and a token
  set, the client is constructed and the startup log names the flag.

- [ ] 11. Document it (depends on 10) — add a short `docs/work-context.md`
  covering the one-time `/mctl link` flow, the four `/mctl work` forms, the
  four env vars, and the manual cross-surface verification procedure. Link it
  from `AGENTS.md` / `.claude/CLAUDE.md` key paths, and note in
  `docs/contracts/mctl-api-work-context.md` that the adapter now exists.
  — DoD: a reviewer can enable the flag and run the pilot from the doc alone.

## Tests

- [ ] T1. Store round-trip, dual-dialect — `TestWorkItemBindings` with
  `t.Run("sqlite")` using `newTestStore` (`internal/db/store_test.go:198`) and
  `t.Run("postgres")` skipped unless `TEST_DATABASE_URL` is set, sharing one
  assertion body. Covers upsert-then-get, the thread uniqueness constraint, the
  work-item uniqueness constraint, `TouchWorkItemBindingState`, and
  `ON DELETE CASCADE` when the user row goes away.
- [ ] T2. No-actor invariant — a reflection test over every exported request
  struct in `internal/workctx` asserting no field (and no JSON tag) matches
  `actor`, `actor_subject`, `created_by`, `principal` or `on_behalf_of`.
- [ ] T3. Route allowlist — a test asserting every path any client method can
  build matches the six permitted routes, and that none contains `executions`,
  `snapshot`, `snapshots`, `events`, `approvals`, or is a bare
  `GET /api/v1/work-items` or a `PATCH`.
- [ ] T4. Header discipline — an `httptest` server asserting the bearer is the
  surface token, `X-MCTL-Surface-Actor` is digits-only and equals the expected
  Telegram id, `Idempotency-Key` is present on every mutating call and stable
  across a repeat, and `origin_surface` in the create body is always `telegram`
  regardless of what the caller passed.
- [ ] T5. Error mapping — `httptest` cases for `403 link_not_found`,
  `link_revoked`, `link_expired`, `relay_required`, `400 actor_not_accepted`,
  `403 challenge_invalid`, `409 link_conflict` and a `409` state-version
  mismatch, each producing its sentinel and a distinct owner-facing reply.
- [ ] T6. Idempotent open — calling the create/open handler twice for the same
  `(user_id, chat_tg_id, root_tg_message_id)` issues exactly one
  `POST /work-items`, and the second reuses the binding. A third call after the
  binding's `last_state` is set to `completed` issues a new create.
- [ ] T7. Resume concurrency — a fake returning `409` once then `200` proves a
  single re-read-and-retry; a fake returning `409` twice proves the handler
  stops and tells the owner instead of looping.
- [ ] T8. Schema-version rejection — a response with
  `"schema_version": "workitem/v2"` is rejected, no binding row is written, and
  the owner is told the platform version is incompatible.
- [ ] T9. Flag-off no-op — with `WorkContextEnabled` false, `/mctl work` and
  `/mctl link` produce byte-identical output to today's unknown-command reply,
  and a client whose transport fails the test on any request is never called.
- [ ] T10. Existing-command regression — the full `command_test.go` and
  `router_test.go` suites pass unchanged after the `SavedMeta` widening.
- [ ] T11. Actor fail-closed — when `TelegramIDByUserID` returns `found=false`,
  or disagrees with `SavedMeta.SelfTGID`, no HTTP request is made and the owner
  is told the account is not linked.
- [ ] T12. No transcript persisted — after a full create/note/status/resume
  cycle with distinctive message text, a `SELECT *` over `work_item_bindings`
  contains none of that text in any column.

All fixtures use the existing synthetic personas (`Alice`, `Bob`, `Carol`,
`Dana`) and reuse existing synthetic numeric ids per the repository safety
rules; no real Telegram id, handle or name appears anywhere.

## Rollback

The adapter is designed so rollback is a config change, not a revert.

1. **Immediate (seconds, no deploy):** set `WORK_CONTEXT_ENABLED=false` and
   restart. The client is not constructed, no outbound request is made, and
   `/mctl work` / `/mctl link` fall back to the existing unknown-command reply.
   Every other `/mctl` subcommand, the listener, the executor and the notifier
   are untouched. This is the full rollback for anything wrong in the adapter.
2. **If the platform side is the problem:** leave the flag off and revoke the
   `surface:telegram` token at mctl-api. Already-created work items remain
   valid canonical state and stay reachable from other surfaces — nothing in
   Telegram is needed to reach them, which is the point of the feature.
3. **If the code must come out:** revert tasks 4-11 as one range. Leave task 1
   (the table) in place — an empty or stale `work_item_bindings` costs nothing,
   holds no user content, and dropping it is a destructive migration this
   codebase has no mechanism for. If it must go, add a one-shot
   `dropTableIfPresent` pass mirroring `dropLegacyColumns`
   (`internal/db/db.go:406`).
4. **Task 6 caveat:** the `SavedMeta` signature change is the only edit that
   touches existing code paths, so it is the one thing a revert of 4-11 must
   either keep or undo wholesale. Keeping it is safe (it is pure plumbing of
   values the listener already had) and is the recommended choice, so that a
   later retry of #443 does not have to redo it.
5. **Verification after rollback:** run `/mctl status`, `/mctl conversations`
   and one `/mctl approve` cycle in Saved Messages and confirm the replies match
   the pre-change behaviour; confirm `work_context_requests_total` stops
   incrementing.
