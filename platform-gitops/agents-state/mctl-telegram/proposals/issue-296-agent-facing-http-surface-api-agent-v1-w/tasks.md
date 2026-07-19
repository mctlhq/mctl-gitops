# Tasks: issue-296-agent-facing-http-surface-api-agent-v1-w

- [ ] 1. Add `selectAgentProvider(cfg *config.Config, store *db.Store) auth.Provider`
      to `cmd/server/main.go`, structurally mirroring `selectBridgeProvider`
      (`ExpectedAudience: "agent"`, `AudienceRequired: true`, same
      `AUTH_MODE` switch, `rejectAllProvider` fail-closed fallback when
      `OAUTH_JWT_SECRET` is unset, `localdev.New` fallback in `local-dev`
      mode) — DoD: function compiles, unit test covers all four `AUTH_MODE`
      branches (`local-jwt`, `shared-hmac`/`shared-hmac-legacy`,
      `local-dev`, missing secret -> reject-all), matching the coverage
      style of any existing `selectBridgeProvider` test.

- [ ] 2. Add `Store.ListIncomingEventsSince(ctx, userID, sinceID int64, limit int) ([]IncomingEvent, error)`
      to `internal/db/agent_events.go`, ordered by `id ASC`, scoped to
      `user_id`, decrypting `body_encrypted` the same way
      `GetIncomingEvent` does — DoD: SQLite and Postgres both pass a test
      inserting N events across two users and asserting the query returns
      only the target user's rows newer than `sinceID`, in id order, capped
      at `limit`.

- [ ] 3. Create `internal/agentapi/policy.go` with the server-side
      `evaluate(profile *db.AgentProfile, actionType, intent string,
      replyChars int, senderBlocked bool) (decision string, reasons []string)`
      function implementing the rules already promised in
      `agent_actions.go`/`agent_domain.go` doc comments: `mode=="off"` or
      `AutopilotPaused` -> `db.PolicyDeny`; `senderBlocked` -> `db.PolicyDeny`;
      `replyChars > MaxReplyChars` -> `db.PolicyDeny`; `mode=="guarded"` and
      `intent` present in the comma-separated `IntentAllowlist` ->
      `db.PolicyAllow`; else -> `db.PolicyRequireApproval` — DoD: table-driven
      unit test enumerates every `(mode, autopilot_paused, blocked,
      over_length, intent-in-allowlist)` combination against the expected
      decision; each `reasons` entry is a stable, greppable string (no
      message content).

- [ ] 4. Create `internal/agentapi/handlers.go` (depends on 2, 3): a
      `Handlers` struct wrapping `*db.Store`, with `Register(mux)` binding
      the routes listed in design.md under `/api/agent/v1` (`GET /profile`,
      `GET /events`, `GET /conversations/{id}`, `GET
      /conversations/{id}/messages`, `POST /actions`, `GET /actions/{id}`,
      `POST /actions/{id}/execute`, `POST /notifications`). Every handler
      derives `user_id` only from `auth.From(r.Context()).UserID`, never
      from a path/query/body parameter — DoD: handlers compile against the
      existing `web.AccountHandlers`-style `Register(mux)` shape; a test
      asserts every handler 401s when `auth.From` returns nil (defensive
      path, mirrors `NewBridgeTokenHandler`).

- [ ] 5. Wire audit logging into every `agentapi` handler via the same
      `Store.LogToolCall` path `web.AccountHandlers.audit` uses, with tool
      names like `"POST /api/agent/v1/actions"` (depends on 4) — DoD: a
      call through each route produces exactly one audit row visible via
      `Store`'s audit query, with no plaintext `body`/`payload`/`text`
      content in the logged fields.

- [ ] 6. Implement `POST /api/agent/v1/actions` to call `evaluate()` (task
      3), persist via `Store.InsertAgentAction` with the server-computed
      `PolicyDecision`/`PolicyReasons` (never trusting a caller-supplied
      decision field even if present in the request body) (depends on 3,
      4) — DoD: integration test posts an action with a client-supplied
      `policy_decision: "allow"` while the user's profile is `mode=off`,
      and asserts the persisted row is `PolicyDeny`, not the client's
      value.

- [ ] 7. Implement `POST /api/agent/v1/actions/{id}/execute` using
      `Store.UpdateAgentActionStatus`'s compare-and-set
      (`approved -> executing`, then on success `executing -> executed` via
      `Store.SetAgentActionExecuted`) and reject calls against actions in
      `pending_approval`, `executing`, or any terminal state (depends on 4)
      — DoD: test matrix covering every non-`approved` starting status
      asserts the endpoint returns an error and leaves the row's status
      unchanged; a double-execute race test (two concurrent calls on one
      `approved` row) asserts exactly one succeeds.

- [ ] 8. Add an in-process token-minting helper,
      `agentapi.MintToken(issuer *localjwt.Issuer, tgID int64, tgUsername
      string, ttl time.Duration) (string, error)`, producing a
      `Claims{Audience: []string{"agent"}, ...}` token via the same
      `localjwt.Issuer` construction pattern `registerOAuth`/bridge minting
      use (depends on 1) — DoD: unit test mints a token and round-trips it
      through `localjwt.Verify` + `CheckAudience(..., "agent", true)`
      successfully, and confirms a token minted with a different (or no)
      audience is rejected by `selectAgentProvider`'s provider.

- [ ] 9. Mount `/api/agent/v1` in `cmd/server/main.go` immediately after
      the existing `/api/account` mount, using
      `auth.Middleware(agentProvider, true, m)` (always required, no
      `cfg.AuthRequired` opt-out) (depends on 1, 4) — DoD:
      `go build ./...` succeeds; a smoke test hits `GET
      /api/agent/v1/profile` with no `Authorization` header and gets `401`;
      with a valid `aud=agent` token for a user with no `agent_profiles`
      row it gets a well-formed "not configured" response rather than a
      500.

- [ ] 10. Cross-account isolation tests (depends on 9): mint `aud=agent`
      tokens for two distinct users A and B; assert user A's token cannot
      read user B's events/conversations/actions (expect `404`, not a
      cross-tenant row) — DoD: test passes and is added to
      `internal/agentapi` (or wherever the project's existing
      cross-provider isolation tests for `/bridge` live, for consistency).

- [ ] 11. Update `docs/runbooks/` (or add a new short runbook alongside
      `docs/runbooks/canary.md`) documenting the new `AUTH_MODE`-driven
      `aud=agent` provider, the `evaluate()` policy rules, and how to
      manually mint a test token for local development (depends on 1-9) —
      DoD: a developer following the doc can `curl` every route locally
      against `AUTH_MODE=local-dev`.

- [ ] 12. Update `AGENTS.md`/`.claude/CLAUDE.md` "Key paths" section to add
      `internal/agentapi/` once it exists, matching how `internal/bridge/`
      is already listed — DoD: both files updated identically (already
      near-duplicates today).

## Tests

- [ ] T1. Unit: `selectAgentProvider` across all `AUTH_MODE` values
      (task 1).
- [ ] T2. Unit: `Store.ListIncomingEventsSince` pagination + user scoping,
      SQLite and Postgres (task 2).
- [ ] T3. Unit: `evaluate()` table-driven policy matrix (task 3).
- [ ] T4. Integration: full auth chain — no token -> 401; wrong audience
      (e.g. an MCP or bridge token) -> 401; valid `agent` token -> 200
      (tasks 1, 4, 9).
- [ ] T5. Integration: `POST /actions` ignores client-supplied policy
      decision and persists the server-evaluated one (task 6).
- [ ] T6. Integration: `execute` compare-and-set rejects invalid starting
      states and is race-safe under concurrent calls (task 7).
- [ ] T7. Integration: cross-account isolation on every read/write route
      (task 10).
- [ ] T8. Integration: token minted via `agentapi.MintToken` verifies and
      is rejected when given the wrong audience (task 8).
- [ ] T9. Regression: existing `/mcp`, `/bridge`, `/api/account`,
      `/api/bridge/token` test suites still pass unchanged (this PR must
      not touch their behavior).

## Rollback

All changes are additive (new package `internal/agentapi`, one new `Store`
method, one new provider selector, one new route mount) with no schema
migration and no change to existing route behavior. Rollback is a plain
revert of the PR:

1. Revert the commit(s) that added `internal/agentapi`, the
   `selectAgentProvider` function, and the `/api/agent/v1` mount in
   `cmd/server/main.go`.
2. No data migration to undo — `ListIncomingEventsSince` is a read-only
   query against existing tables/columns; removing it drops no data.
3. Because nothing in this milestone yet mints `aud=agent` tokens outside
   of this PR's own `agentapi.MintToken` helper (task 8) and no production
   caller depends on `/api/agent/v1` until the future agent-listener PR
   lands, rollback carries no in-flight-request risk: at worst, an
   already-issued agent token stops being accepted (401), which is the
   same fail-safe behavior as if the token had simply expired.
4. If task 11's runbook or task 12's `CLAUDE.md`/`AGENTS.md` edits already
   merged separately, leave them — stale documentation referencing a
   reverted feature is a cheap follow-up fix, not a rollback blocker.
