# Tasks: issue-1057-e2e-low-frequency-live-telegram-login-pr

- [ ] 1. Add `internal/loginproof`. It contains:
  - `Step` constants and the per-mode required-step table;
  - `Recorder` (`Observe`, `Verdict`);
  - `Evidence` with `Line()`, which has no identifier fields;
  - `Classify(err)` mapping to the closed outcome set, with `unknown` as the default.

  DoD: unit tests pass without build tags. `Verdict` returns `pass` only when every required step was observed and there is no error.
- [ ] 2. Add `mcp.(*Server).CallToolInProcess(ctx, id, tool, args)`, which goes through `newMCPServer().HandleMessage` (`initialize` and then `tools/call`). DoD: a unit test calls a registered read tool through it with a stub, and shows that a tool outside the identity's scopes is refused.
- [ ] 3. (depends on 1, 2) Add `cmd/login-proof` with the shared setup:
  - env-only credentials (`TG_PROOF_*`);
  - slog discarded;
  - an in-memory store stamped `db.DCModeProduction` with a throwaway user;
  - a pool and an `mcp.Server` with sending disabled;
  - a single evidence line, and exit 0 only on `pass`;
  - a package doc that states the dedicated-account and no-schedule rules.

  DoD: `go vet` and `golangci-lint` are clean, and no flag accepts a phone number, code, password or session.
- [ ] 4. (depends on 3) Implement `login-proof qr`. Steps:
  - an anchor client from `TG_PROOF_ANCHOR_SESSION`;
  - `telegram.LoginQR`, with a `show` callback that decodes the URL token and calls `AuthAcceptLoginToken` once, keeping the authorization hash;
  - the `persisted` check via `store.LoadSession`, then `SaveSession`;
  - the `mcp_call` check (`list_dialogs`, limit 1, `IsError == false`, result never printed);
  - a deferred cleanup: `LogOutSession`, falling back to the anchor's `AccountResetAuthorization(hash)`, verified with `AccountGetAuthorizations`.

  DoD: with fakes injected through small interfaces, a full fake run yields `pass`, and each mutation in T3 yields non-pass.
- [ ] 5. (depends on 3) Implement `login-proof phone [-expect ok|wrong-password|expired-code]`:
  - `TG_PROOF_PHONE` from env;
  - the code from a no-echo TTY prompt, refusing when stdin is not a terminal;
  - the password from `TG_PROOF_PASSWORD`, a no-echo prompt, or a fixed wrong value in `wrong-password` mode;
  - `telegram.Login` with `WantTelegramID`;
  - for `ok`, the same persisted / MCP / cleanup steps; for the negative modes, pass only on the matching `Classify` outcome AND `LoadSession == nil`;
  - a local lockfile.

  DoD: the mutation tests in T4 pass.
- [ ] 6. (depends on 4) Add `.github/workflows/live-telegram-login.yml`:
  - `workflow_dispatch` only, `environment: live-telegram-login`;
  - `concurrency: live-telegram-login` with `cancel-in-progress: false`;
  - `timeout-minutes: 10` and `contents: read`;
  - `go run ./cmd/login-proof qr`, gated on exit 0 plus exactly one `outcome=pass` evidence line;
  - no artifacts;
  - a header comment covering the dedicated-account, no-schedule and no-release-dispatch rules.

  DoD: the file passes actionlint, and `release-please.yml` is unchanged (no dispatch of the new workflow).
- [ ] 7. (depends on 6) Add a guard test that fails if `live-telegram-login.yml` contains a `schedule`, `pull_request` or `push` trigger, or if any workflow dispatches `live-telegram-login.yml`. DoD: the test runs in ordinary CI and is mutation-verified (T6).
- [ ] 8. Write `docs/runbooks/live-login-proof.md`. It covers:
  - when the proof is required;
  - provisioning the dedicated account and the `live-telegram-login` environment;
  - seeding the anchor with `cmd/ci-anchor` into a separate state dir;
  - phone-mode steps;
  - the evidence format to paste into #1057 or the PR (result, commit SHA, timestamp only);
  - manual cleanup of the "MCTL Assistant" device if the outcome is `cleanup_failed`.

  Add a cross-reference in the `cmd/ci-anchor` package doc. DoD: if `docs/runbook_test.go` indexes runbooks, the new file is covered.
- [ ] 9. (operator, depends on 6, 8) Provision the dedicated account and environment secrets, dispatch the workflow once, run phone mode once with `ok`, once with `wrong-password` and once with `expired-code`, and post the evidence lines on #1057. DoD: all four evidence lines are posted. Any non-pass is reported as-is.
- [ ] 10. (cross-repo) Open a PR in mctlhq/.github that updates the #279 epic success criteria and the roadmap manifest to reference mctl-telegram#1057 instead of test-DC login (#963). DoD: the PR is linked from #1057.

## Tests

- [ ] T1. `loginproof.Classify` table test covers: `PHONE_CODE_EXPIRED` -> `code_expired`, `PHONE_CODE_INVALID` -> `code_invalid`, `auth.ErrPasswordInvalid` and `PASSWORD_HASH_INVALID` -> `bad_password`, `FLOOD_WAIT_30` -> `flood_wait`, `AUTH_RESTART` -> `auth_restart`, `telegram.ErrQRLoginExpired` -> `timeout`, context deadline -> `timeout`, and an arbitrary error -> `unknown`. Nothing maps to `pass`.
- [ ] T2. `Recorder.Verdict`: for each mode and each required step, omitting that step yields a non-pass verdict. A non-nil run error always yields non-pass. `Evidence.Line()` contains only the fixed keys (field-reflection test).
- [ ] T3. QR harness mutation tests use fakes for the login function, the anchor API, the store and the MCP caller. Each of the following yields non-pass:
  - skip session persistence (`LoadSession` returns nil);
  - skip the MCP call, or the MCP call returns `IsError`;
  - logout fails and `resetAuthorization` also fails, or `getAuthorizations` still lists the hash;
  - the anchor never accepts the token (login returns `ErrQRLoginExpired`).
- [ ] T4. Phone harness mutation tests:
  - wrong-password mode with a store that has a session -> non-pass;
  - expected `code_expired` but the error is `code_invalid` -> non-pass;
  - `ok` mode without the MCP call -> non-pass;
  - stdin not a TTY -> refusal;
  - any `-phone`, `-code` or `-password` flag is rejected (flag set has none).
- [ ] T5. `CallToolInProcess` routes through the registered handler and honours tool scopes.
- [ ] T6. The workflow guard test fails when a `schedule:` block or a release-please dispatch of `live-telegram-login.yml` is added (verified by a fixture copy in the test).
- [ ] T7. The existing fake tests in `internal/telegram/login_test.go` and `loginqr_test.go` stay green and unchanged.

## Rollback

Everything is additive: a new package, a new command, one exported read-only helper, a new dispatch-only workflow, and a runbook. To roll back:

1. Delete `.github/workflows/live-telegram-login.yml`, or disable it in the Actions UI.
2. Revert the PR.
3. Revoke the `live-telegram-login` environment secrets, and terminate the anchor session from the dedicated account's Active Sessions.

No product login path, database schema or deployed service config changes, so no service redeploy is needed.
