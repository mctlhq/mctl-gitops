# Tasks: issue-585-spike-cloudflare-mcp-execute-44-protocol

- [ ] 1. Add `internal/mcpprobe/` with the Streamable HTTP / JSON-RPC client
  plumbing and a `Report` type — DoD: package compiles; `Report` and its nested
  step structs contain only strings for protocol versions / tool names / error
  codes, plus booleans, ints and status codes. There is no field capable of
  holding a bearer token, authorization code, message body, chat title, peer id
  or phone number. `go vet ./...` clean.

- [ ] 2. Implement the probe steps (depends on 1) — DoD: `Run(ctx, Options)`
  executes, and records independently, `prm` (`/.well-known/oauth-protected-resource`
  and its `+MCPPath` alias), `as_metadata` (`/.well-known/oauth-authorization-server`),
  `unauth_probe` (token-less `initialize`, parsing the `WWW-Authenticate`
  challenge including `resource_metadata` per `internal/auth/middleware.go:26-39`),
  `initialize`, `session`, `discover`, `tools_list`, `tools_call`, `mcp_headers`.
  A failed step never aborts the run; each carries its own `ok` / `error_class`.

- [ ] 3. Session-optional call discipline (depends on 2) — DoD: `tools/list` and
  `tools/call` are attempted **without** any `Mcp-Session-Id` header first; on
  failure the probe retries with the id minted by `initialize` and sets
  `session_required=true`. The report records `mcp_session_id_present` and the
  id's length only, never its value.

- [ ] 4. Read-only precondition on `tools/call` (depends on 2) — DoD: the probe
  reads `tools/list` first and refuses to call any tool whose `readOnlyHint` is
  not `true`, failing that step with an explicit error. Default target is
  `get_my_send_status` (`internal/mcp/tools.go:859-865`; `readOnly=true`,
  `destructive=false`, `openWorld=false`, returns booleans only).

- [ ] 5. `server/discover` and `Mcp-Method` / `Mcp-Name` observation (depends on
  2) — DoD: JSON-RPC error `-32601` on `server/discover` is recorded as
  `unsupported` and does not fail the run; the probe sends `Mcp-Method` and
  `Mcp-Name` request headers and records `echoed` / `ignored` / `rejected`. The
  report notes that `internal/mcp/server.go:310-312` passes a no-op
  `WithHTTPContextFunc`, so no request header currently reaches a tool handler.

- [ ] 6. Add `cmd/mcpprobe/main.go` (depends on 2-5) — DoD: env-only
  configuration in the style of `cmd/canary/main.go:59-100` —
  `MCPPROBE_BASE_URL`, `MCPPROBE_MCP_PATH`, `MCPPROBE_BEARER_TOKEN`,
  `MCPPROBE_PROTOCOL_VERSION` (default `2026-07-28`), `MCPPROBE_LABEL`
  (`direct` | `portal`), `MCPPROBE_TOOL` (default `get_my_send_status`),
  `MCPPROBE_TIMEOUT`, `MCPPROBE_OUT`. Emits JSON and a Markdown matrix row.
  Logs through the `slog` JSON + redaction handler (`internal/audit/redact.go`).
  Missing token degrades to unauthenticated steps with the rest marked
  `skipped`. No credential, no Cloudflare hostname, no production URL as a
  default anywhere in the file.

- [ ] 7. Refactor `cmd/canary` onto `internal/mcpprobe` (depends on 2) — DoD:
  `cmd/canary` uses the shared JSON-RPC plumbing; its env contract, Pushgateway
  metric names, step names, `list_dialogs` target and mandatory-session
  behaviour are byte-for-byte unchanged, so `docs/runbooks/canary.md` stays
  accurate. `cmd/canary/main_test.go` and `renew_test.go` pass unmodified. The
  `2024-11-05` literal (`cmd/canary/main.go:283`, `test/load/main.go:219`) now
  comes from one place.

- [ ] 8. Add `OAUTH_PREREGISTERED_CLIENTS` (depends on nothing) — DoD:
  `internal/config` parses a list of `client_id` + one or more exact
  `redirect_uris`; `cmd/server/main.go` seeds them into `s.clients` beside the
  existing `ConnectClientID` seeding (`internal/oauth/server.go:671-676`), with
  a zero `CreatedAt` so the registration sweeper never evicts them — unlike a
  DCR client, which expires after `ClientRegistrationTTL` (24h). Unset, server
  behaviour is identical to today. Startup logs the count, never the URIs' query
  strings.

- [ ] 9. Add `OAUTH_EXTRA_IMPLICIT_HOSTS` (depends on nothing) — DoD: parsed
  with the same `parseStringCSV` used at `internal/config/config.go:323` and
  **appended** to whatever `AllowedImplicitHosts` resolves to, including the
  built-in defaults at `internal/oauth/server.go:534-542`.
  `OAUTH_ALLOWED_IMPLICIT_HOSTS` keeps its existing replace semantics, so
  `TestRegister_ConfiguredImplicitHostsReplaceDefault`
  (`internal/oauth/server_test.go:919`) still passes unchanged.

- [ ] 10. Document both new vars in `.env.example` (depends on 8, 9) — DoD:
  `OAUTH_PREREGISTERED_CLIENTS` and `OAUTH_EXTRA_IMPLICIT_HOSTS` are present and
  commented, and the pre-existing gap is closed by also documenting
  `OAUTH_ALLOWED_IMPLICIT_HOSTS`, which the code reads but the example file
  never mentioned. Values are placeholders; no Cloudflare hostname.

- [ ] 11. Write `docs/cloudflare-portal-compat.md` (depends on 6, 8, 9) — DoD:
  contains (a) the mctl-side configuration contract with the callback URI
  described as "paste the value Cloudflare displays", never guessed; (b)
  `Require user auth=ON` stated as mandatory, with the reason; (c) the Phase A+B
  matrix with the direct row filled from the CI artifact and Portal cells marked
  `PENDING-OPERATOR`; (d) a numbered, bounded operator procedure per pending
  cell, including the two-user check that the JWT `sub` reaching the upstream
  differs per end user; (e) the affinity caveat from `docs/hpa.md` — MTProto
  clients are per-pod (`internal/telegram/clientpool.go`) and a collapsed `sub`
  degenerates the consistent-hash ring and triggers Telegram "New login" events;
  (f) an explicit statement that `session_required` and the negotiated protocol
  version are *observations of current behaviour* and that changing them belongs
  to `mctl-telegram#568`; (g) a note that `TOOL_FILTER=read-only`
  (`internal/mcp/server.go:160-175`) is the supported way to narrow a
  Portal-facing surface.

- [ ] 12. Link the artifact back to `#44` (depends on 11) — DoD: the generated
  Markdown row and the doc are referenced from the issue thread; the checked-in
  matrix and the CI artifact agree.

## Tests

- [ ] T1. `internal/mcpprobe` unit tests against `httptest` fakes for four
  upstream shapes: stateful (mints `Mcp-Session-Id`, rejects session-free
  `tools/call`), stateless (no session header, accepts calls directly), `401`
  with a full `WWW-Authenticate` challenge carrying `resource_metadata`, and
  `server/discover` answering `-32601`. Each asserts the corresponding report
  cell, including `session_required` true vs false.

- [ ] T2. Redaction test: run the probe against a fake whose tool result
  contains a synthetic chat title and message body, with a fixture bearer token,
  then assert the serialized JSON report contains neither the token string, nor
  the body, nor the title. Fixtures use the existing synthetic personas
  (`Alice`, `Bob`, `Carol`, `Dana`) and synthetic Telegram ids per `CLAUDE.md`.

- [ ] T3. Read-only guard test: configure `MCPPROBE_TOOL=send_message` and
  assert the probe refuses to issue `tools/call` and reports an explicit error,
  proving the `readOnlyHint` precondition is structural.

- [ ] T4. In-process integration test (`internal/mcpprobe/integration_test.go`):
  mount `mcp.New(...).HTTPHandler()` behind the same chain `cmd/server` uses,
  following the existing pattern at `cmd/local/e2e_cli_daemon_test.go:123-137`,
  run the probe, and assert the report is well-formed and complete. It asserts
  *shape*, not a specific `protocolVersion` value — the value is recorded as the
  golden direct row so that when `#568` changes it, the diff is visible.

- [ ] T5. Pre-registered-client OAuth test: a client configured via
  `OAUTH_PREREGISTERED_CLIENTS` with redirect `https://portal.example.test/servers-callback`
  is accepted at `/oauth/authorize` through the exact-match branch of
  `validateClient` (`internal/oauth/server.go:2648`) with **no** `/oauth/register`
  call and with `AllowImplicitClient=false`.

- [ ] T6. Exact-match negative test: the same client presenting
  `https://portal.example.test/servers-callback2`,
  `.../servers-callback?x=1`, `.../servers-callback/`, or the same host on a
  different port is rejected.

- [ ] T7. Additive-allowlist regression test: with
  `OAUTH_EXTRA_IMPLICIT_HOSTS=portal.example.test` set and
  `OAUTH_ALLOWED_IMPLICIT_HOSTS` unset, assert the accepted host set is the
  union — `claude.ai`, `claude.com`, `chatgpt.com`, `localhost`, `127.0.0.1`
  **and** `portal.example.test`. This is the test that stops a Portal rollout
  from silently dropping existing client redirects.

- [ ] T8. Unchanged-invariants gate: `go test -race ./...` passes with no edits
  to any existing test, in particular `internal/oauth/redirect_hardening_test.go`,
  `internal/oauth/server_test.go` (PKCE, replace-semantics, registration caps),
  `cmd/server/protected_resource_test.go`, `internal/mcp/annotations_test.go` and
  `internal/auth/middleware_test.go`. Any required edit to one of those files is
  a signal that this spike changed behaviour it promised not to change.

- [ ] T9. No-deprecated-mechanism guard: a test or `go vet`-adjacent check
  asserting the change introduces no HTTP+SSE endpoint, no new `Mcp-Session-Id`
  requirement in new code, and no Roots / Sampling / MCP-Logging registration.

- [ ] T10. Grep-style guard test asserting no Cloudflare production hostname
  (`mcp-enterprise.mctl.ai`) appears in any `.go` file.

## Rollback

Every change is additive and configuration-gated, so rollback is graduated
rather than all-or-nothing:

1. **Operational, no deploy.** Unset `OAUTH_PREREGISTERED_CLIENTS` and
   `OAUTH_EXTRA_IMPLICIT_HOSTS` and restart. Both are read at config load and
   both default to today's behaviour, so the OAuth surface returns to its
   pre-change state immediately. `OAUTH_ALLOWED_IMPLICIT_HOSTS` was never
   modified, so no existing redirect host can have been lost.
2. **Stop probing.** `cmd/mcpprobe` is a standalone binary with no runtime
   coupling to the server, no image, no CronJob and no alert rule. Simply not
   running it removes all Portal-facing activity. Nothing in the server depends
   on it.
3. **Revert the commit.** The only file with existing runtime behaviour touched
   is `cmd/canary`, and only its internals. If the shared-plumbing refactor is
   suspected in a canary alert, revert task 7 alone — `internal/mcpprobe`,
   `cmd/mcpprobe` and the OAuth config additions are independent of it and can
   stay. The pre-change `cmd/canary` is restorable from git history without
   touching anything else.
4. **No data to unwind.** There is no schema migration and no persisted state:
   pre-registered clients live in the in-memory `s.clients` map, exactly like
   `ConnectClientID` (`internal/oauth/server.go:671-676`). Removing the config
   removes the client; no rows, no cleanup, no orphaned registrations.
5. **Docs.** `docs/cloudflare-portal-compat.md` is additive; deleting it removes
   the matrix and nothing else. `docs/runbooks/canary.md` is intentionally
   unchanged by this work and needs no rollback.
