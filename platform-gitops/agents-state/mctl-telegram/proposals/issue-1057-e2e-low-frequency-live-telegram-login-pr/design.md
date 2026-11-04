# Design: issue-1057-e2e-low-frequency-live-telegram-login-pr

## Current state

Product login code:
- `internal/telegram/loginqr.go` `LoginQR(ctx, apiID, apiHash, store, userID, show, password, cfg)`:
  - Exports tokens through `qrlogin.NewQR(..., qrlogin.Options{Migrate: client.MigrateTo})` and waits on a buffered `updateLoginToken` signal (`loginTokenSignal`).
  - Retries `AUTH_RESTART` once (`retryAuthRestartOnce`) and handles `SESSION_PASSWORD_NEEDED` through `passwordAfterQR`.
  - Runs the account check (`acceptQRAuth` -> `logOutIfMismatch` with `LoginConfig.WantTelegramID`) and settles the buffered `deferredSession` (`settleLogin` / `finishLogin`). `finishLogin` logs out an authorization that was scanned but never settled.
  - `show` receives only the deep-link URL (`tg://login?token=<base64url>`) and ASCII art.
- `internal/telegram/login.go` `Login(...)`:
  - Phone flow: `runPhoneFlow`, `interactiveAuthenticator.signIn` with `LoginCodeAttempts = 3`, `askPasswordChecked` with `LoginPasswordAttempts = 3`, and `isPasswordRejected`.
  - `askCode` / `askPassword` are callbacks invoked inside a single `client.Run`, so the code must arrive within the same process and connection.
  - `loginClientOptions` uses `deviceConfig` (`DeviceModel: "MCTL Assistant"`, `clientpool.go`) and `dcList(cfg.TestDC)`.
  - `LogOutSession(ctx, apiID, apiHash, data, cfg)` ends an authorization from its bytes alone.
- `internal/oauth/enable_access.go`: the web flow's callers. `shortReason` maps login errors to tokens (`code_invalid`, `code_expired`, `flood_wait`, `auth_restart`, `identity_mismatch`, `bad_password`, `timeout`, ...). The function is unexported.
- `cmd/login/main.go`: the operator CLI. It calls the same `telegram.Login` / `telegram.LoginQR` with a real store and a no-echo password prompt (`term.ReadPassword`).

Existing live harness (#854):
- `cmd/ci-anchor/main.go`: seeds the CI service account session in two steps (`send` / `confirm`). It calls gotd `client.Auth().SignIn` directly, so it does NOT exercise `internal/telegram/login.go`. It also takes the code as an argv flag (`-code`).
- `internal/telegram/live_integration_test.go` (`//go:build livetg`): `TestLive_MessageToolsRoundTrip` runs on `TG_LIVE_SESSION`. Its comments say that account "is shared with the production canary". It silences slog (`io.Discard`) and masks the @username because Actions logs are public. `newLiveStore` builds an in-memory store stamped `db.DCModeProduction`.
- `.github/workflows/live-telegram.yml`:
  - Triggers: `workflow_dispatch` only, plus a dispatch from `release-please.yml` (job `live-telegram`, line ~148).
  - Runs in the `live-telegram` environment under concurrency group `live-telegram`.
  - Fails on any `--- SKIP` and requires the exact `--- PASS:` line.

MCP surface:
- `internal/mcp`: `(&Server{...}).newMCPServer()` is unexported. In-process tests call `srv.HandleMessage(ctx, raw)` with `auth.With(ctx, &auth.Identity{UserID, Scopes})` (`apps_surface_test.go` `callRPC`).
- `list_dialogs` is a reviewer-read tool (`internal/mcp/reviewer.go`) and borrows a pool client (`tools.go` ~L236).

Deployed state checked:
- `mctl_list_services(team=mctl)`: returned 0 items (complete=true). mctl-telegram is not in a tenant named `mctl`.
- `mctl_get_service_config(team=labs, service=mctl-telegram)`: image `0.114.0`, host `tg.mctl.ai`, port 8080, base-service, hasDatabase=true.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.114.0`. A grep for `TG_TEST_DC` found no match, so the deployed server is on production DCs, which matches the DCs this proof uses.
- Not observed: the GitHub environments and secrets of mctlhq/mctl-telegram, including whether a separate dedicated login account exists. These cannot be read from this run (recorded under Open questions). The proof runs in GitHub Actions or on an operator machine, not in the deployed service, so no deployed config changes.

## Proposed solution

### 1. `internal/loginproof` (new package): verdict logic, no Telegram I/O

- `type Step string` with constants: `login`, `persisted`, `mcp_call`, `cleanup`, plus `expect_outcome` and `no_session` for the negative modes.
- `type Evidence struct{ Mode, Outcome, Reached, Commit, At string }` with `Line()` rendering one `key=value` line.
  - The type has no field that can hold an identifier.
  - `Outcome` is drawn from the closed set: `pass`, `fail`, `bad_password`, `code_expired`, `code_invalid`, `flood_wait`, `auth_restart`, `identity_mismatch`, `refused`, `cleanup_failed`, `timeout`, `unknown`.
- `Classify(err error) string`: mirrors `oauth.shortReason` for the telegram-level reasons. It matches on `tgerr` messages, `auth.ErrPasswordInvalid` / `PASSWORD_HASH_INVALID`, `telegram.ErrQRLoginExpired` and context errors. Anything unrecognised is `unknown`, never `pass`.
- `type Recorder`: each harness step calls `Observe(step)` only after it has checked its own postcondition. `Verdict(mode, runErr)` returns `pass` only if every step required for the mode was observed and `runErr == nil`.
  - Positive modes require `login`, `persisted`, `mcp_call` and `cleanup`.
  - `wrong-password` / `expired-code` require `expect_outcome` and `no_session`.
- Required steps are listed in one table, so a mutation that drops a step makes the verdict `fail`. Ordinary unit tests (no build tag) prove this.

### 2. `mcp.(*Server).CallToolInProcess` (small exported helper)

`func (s *Server) CallToolInProcess(ctx context.Context, id *auth.Identity, tool string, args map[string]any) (*mcplib.CallToolResult, error)`

- Builds `s.newMCPServer()`, sends `initialize` and then one `tools/call` through `HandleMessage`, the same path as the existing `callRPC` test helper.
- The proof needs it because `newMCPServer` is unexported. It only reads and adds no behaviour to the HTTP surface. A unit test pins that it goes through the registered handler, so scope filtering applies.

### 3. `cmd/login-proof` (new command)

Common setup:
- Reads `TG_PROOF_API_ID`, `TG_PROOF_API_HASH` and `TG_PROOF_EXPECT_TG_ID` from env. The expected id is passed as `LoginConfig.WantTelegramID`, so a wrong account is logged out by product code.
- Silences slog to `io.Discard`, like the live test.
- Builds an in-memory `db.Store` with `EnsureDCMode(db.DCModeProduction)` and a throwaway `EnsureUser`, like `newLiveStore`.
- Builds `telegram.NewClientPool` and `mcp.New(store, pool, false)` (sending disabled).
- Prints exactly one `Evidence.Line()` to stdout and exits 0 only on `pass`.
- The package doc states: dedicated login-proof service account only; never personal, operator or canary; never scheduled.

`login-proof qr` (unattended, used by CI):
1. Opens the anchor client with gotd on `TG_PROOF_ANCHOR_SESSION` (env; written to a 0600 temp `session.FileStorage` or an in-memory storage) under the product `deviceConfig` and production DCs.
2. Calls `telegram.LoginQR(ctx, apiID, apiHash, store, uid, show, password, telegram.LoginConfig{WantTelegramID, QRWait: 60s})`.
   - `show` decodes the token from the URL (base64url after `token=`).
   - It calls `anchor.API().AuthAcceptLoginToken(ctx, token)` once per run, guarded by a `sync.Once`, and keeps the returned `tg.Authorization.Hash` for the cleanup fallback.
   - `password` reads `TG_PROOF_PASSWORD` when the account has 2FA.
   - This exercises the product's `updateLoginToken` / `Migrate` handling whenever the new client's DC differs from the account's home DC.
3. Persisted step: `store.LoadSession(uid)` is non-nil. That is the bytes `settleLogin` wrote through `SessionStore`. The command then calls `store.SaveSession(uid, data, tgID, ...)`, as `cmd/login` does after login.
4. MCP step: `srv.CallToolInProcess(ctx, &auth.Identity{UserID: uid, Scopes: readScopes}, "list_dialogs", {"limit": 1})` must return `IsError == false`. The result body is never printed.
5. Cleanup step:
   - `pool.Shutdown()`, then `telegram.LogOutSession(ctx, apiID, apiHash, data, cfg)` on a `telegram.DetachedLogOutContext`.
   - If that fails, `anchor.API().AccountResetAuthorization(ctx, hash)`.
   - Then `account.getAuthorizations` on the anchor must no longer list `hash`. Only then is `cleanup` observed.
   - Cleanup runs in a `defer` so it also covers failures after the scan.

`login-proof phone [-expect ok|wrong-password|expired-code]` (attended, operator machine only):
- Phone number from `TG_PROOF_PHONE` (env), never argv.
- `askCode` uses a no-echo terminal prompt (`term.ReadPassword`, like `cmd/login`). It refuses to run when stdin is not a terminal, so it cannot become a CI loop.
- `askPassword` reads `TG_PROOF_PASSWORD` or a no-echo prompt.
  - `-expect wrong-password`: a fixed known-wrong value is returned for every attempt (`LoginPasswordAttempts`), so the real password is never needed.
  - `-expect expired-code`: the prompt instructs the operator to wait past the code lifetime, or to enter the code from a previous send.
- Calls `telegram.Login(ctx, ..., store, uid, phone, askCode, askPassword, LoginConfig{WantTelegramID})`, the same function the web flow reaches through `enable_access.go`.
- `ok`: the same persisted / MCP / cleanup steps as QR. Cleanup is `LogOutSession` only, because there is no anchor. If logout fails, the outcome is `cleanup_failed` and the runbook tells the operator to terminate the "MCTL Assistant" device from another session.
- Negative modes: pass only if `Classify(err)` equals the expected outcome AND `store.LoadSession(uid)` is nil. Product `finishLogin` already logs out a code-submitted authorization that did not settle.
- Pending state (the phone code hash and auth key) lives only in the process: nothing is written to disk. The two-step shape asked in the issue is the operator prompt-and-confirm within one run (see Alternatives).
- A lockfile in `$XDG_RUNTIME_DIR` stops two local runs. The runbook tells the operator not to dispatch the QR workflow during a phone proof.

### 4. `.github/workflows/live-telegram-login.yml` (new)

- Triggers: `on: workflow_dispatch` only. A header comment says it must never gain `schedule`, `pull_request` or a release-please dispatch, and must never use a personal or canary account.
- `environment: live-telegram-login`: a new environment restricted to `main`. Its secrets are `TG_PROOF_API_ID`, `TG_PROOF_API_HASH`, `TG_PROOF_ANCHOR_SESSION`, `TG_PROOF_EXPECT_TG_ID` and optionally `TG_PROOF_PASSWORD`.
- `concurrency: { group: live-telegram-login, cancel-in-progress: false }`, `timeout-minutes: 10`, `permissions: contents: read`.
- Step: `go run ./cmd/login-proof qr` with `COMMIT=${{ github.sha }}`. The step fails unless the exit code is 0 AND stdout contains exactly one line starting `login-proof mode=qr outcome=pass`.
- No artifact upload.
- A guard step (or a `build.yml` lint) fails if this workflow file contains `schedule:`. That check is a mutation-tested shell or Go test in `docs` or `cmd/login-proof`.

### 5. Docs

- `docs/runbooks/live-login-proof.md` covers:
  - when the proof is required: a PR that materially changes phone login, SRP/2FA, session persistence or login error classification;
  - how to seed the anchor session with `cmd/ci-anchor` into a separate state dir;
  - how to run phone mode;
  - how to paste the evidence line (result, commit SHA, timestamp only) into #1057 or the PR;
  - the safety invariants.
- `cmd/ci-anchor` doc: add a note that it also seeds the login-proof anchor (no code change required; the env var names are mapped in the runbook).
- Cross-repo follow-up (separate PR in mctlhq/.github): update the #279 epic success criteria and the roadmap manifest to reference mctl-telegram#1057 instead of test-DC login (#963).

## Alternatives

1. **Extend `TestLive_*` under the existing `live-telegram` workflow and account.** Dropped:
   - that account is shared with the production canary, and the issue forbids using the canary as a login account;
   - the workflow is dispatched by release-please after every release, which would make full login automatic per release (invariant 2).
2. **Cross-process two-step phone harness (start/confirm like `cmd/ci-anchor`) driving gotd's `SignIn` directly.** Dropped: it would not exercise `internal/telegram/login.go` (`runPhoneFlow`, `askPasswordChecked`, `finishLogin`, `settleLogin`), which is the whole point of the proof. Splitting `telegram.Login` into resumable steps would change the product path under test. A single attended process keeps the product code byte-identical.
3. **Live QR proof as a `livetg` Go test in `internal/mcp`.** This would avoid exporting `CallToolInProcess`. Dropped in favour of one command for both modes:
   - the phone mode cannot be a `go test` (it needs a terminal);
   - sharing the `loginproof` recorder, classifier and evidence format between modes keeps outcomes identical and mutation-testable without build tags.

## Platform impact

- No database migration, no change to the deployed service (`labs/mctl-telegram` 0.114.0 is untouched), and no product login behaviour change. The only exported addition is `mcp.(*Server).CallToolInProcess`.
- New GitHub environment `live-telegram-login` and its secrets must be created by a repo admin. A dedicated Telegram account must be provisioned and its anchor session seeded once with `cmd/ci-anchor`.
- Telegram cost: one QR authorization per dispatch, and one phone authorization per material login change. Both are logged out immediately. The account's flood budget is separate from the canary's.
- Risks and mitigations:

| Risk | Mitigation |
| --- | --- |
| Leaking identifiers in public Actions logs | slog discarded; evidence type has no identifier fields; MCP result never printed; no artifacts. |
| Stray authorizations | Deferred `LogOutSession` plus the anchor `resetAuthorization` fallback, verified with `getAuthorizations`; failure is `cleanup_failed`. |
| AUTH_KEY_DUPLICATED | Single concurrency group; the anchor session is used only by this workflow. |
| Someone adds a schedule | Guard test fails CI on `schedule:` in the workflow file. |
| Telegram terminates the anchor session | Proof fails closed (`refused` / `unknown`); the runbook re-seeds with `cmd/ci-anchor`. |
