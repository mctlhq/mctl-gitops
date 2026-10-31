# Low-frequency live Telegram login proof on a dedicated service account

## Context

The login-path-observability epic (mctlhq/.github#279) required a full live
login proof on Telegram's test datacenters (#963). That premise was falsified
on 2026-10-31 (#854): test-DC numbers no longer complete `signIn`, and real
numbers on the test DC get no usable code. Today the repository proves login
only with fakes (`internal/telegram/login_test.go`, `loginqr_test.go`), proves
login-path reachability with zero-API synthetic probes (#959), observes real
users through the connect funnel (#960), and proves message tools live with an
already-authorized session (`.github/workflows/live-telegram.yml`,
`internal/telegram/live_integration_test.go`). No path proves the real
`telegram.LoginQR` / `telegram.Login` code against Telegram itself.

This proposal adds a low-frequency, operator-triggered proof on the production
DCs with a dedicated service account. It has two parts. (A) An on-demand QR
login can run unattended in CI, because an already-authorized anchor session of
the same account accepts the login token. (B) An operator-assisted
phone + code + 2FA harness covers the product phone path and its wrong-password
and expired-code outcomes. Both parts go through the product login functions,
store the session through the normal store path, make one read-only MCP call,
clean up the authorization they created, and emit bounded, identifier-free
evidence. Neither part may ever run on a schedule.

## User stories

- AS a platform operator I WANT to dispatch a live QR login proof on demand SO THAT I can show that the product QR path (including DC migration and `updateLoginToken`) still signs in against production Telegram.
- AS a platform operator I WANT an attended phone/code/2FA harness that uses the same `telegram.Login` the web flow uses SO THAT a PR that changes phone login, SRP/2FA, session persistence or error classification can be proven live once before release.
- AS a security reviewer I WANT the proof to use only a dedicated service account, never run on a schedule, and keep secrets out of git, logs, artifacts and argv SO THAT the proof cannot harm a personal account or leak credentials.
- AS the epic owner I WANT the login-path epic to reference this issue instead of test-DC login SO THAT the epic is no longer blocked on an unavailable Telegram facility.

## Acceptance criteria (EARS)

- WHEN an operator dispatches the `live-telegram-login` workflow THE SYSTEM SHALL run `login-proof qr`. That command calls `telegram.LoginQR` with an in-memory store, has the anchor session accept the exported token with `auth.acceptLoginToken`, and then requires all of the following: the session was persisted by the store path (`store.LoadSession` returns non-nil bytes for the proof user); one read-only MCP `tools/call` (`list_dialogs`, limit 1) returns a non-error result through `mcp.Server`; and the new authorization was logged out.
- WHEN any required step of a proof was not observed THE SYSTEM SHALL report verdict `fail` (or a more specific non-pass outcome) and exit non-zero. It SHALL never report `pass`.
- IF Telegram answers FLOOD_WAIT, refuses, or the outcome cannot be determined THEN THE SYSTEM SHALL record the outcome as `flood_wait`, `refused` or `unknown` and exit non-zero. It SHALL never convert that outcome to pass.
- WHEN a proof completes, whatever its result, THE SYSTEM SHALL emit exactly one evidence line (mode, outcome, step reached, commit SHA, UTC timestamp). That line SHALL contain no phone number, Telegram user id, username, display name, session bytes, login code, password or token.
- WHILE a proof is running THE SYSTEM SHALL discard gotd and pool logs that can carry identifiers, as `TestLive_MessageToolsRoundTrip` already does.
- WHEN the QR proof created a new authorization THE SYSTEM SHALL log it out with `telegram.LogOutSession`. IF that logout fails THEN THE SYSTEM SHALL fall back to `account.resetAuthorization` on the anchor, using the authorization hash returned by `auth.acceptLoginToken`. IF neither cleanup succeeds THEN THE SYSTEM SHALL record outcome `cleanup_failed`, which is not a pass.
- THE `live-telegram-login` workflow SHALL have `workflow_dispatch` as its only trigger. It SHALL have no `schedule` and no `pull_request` trigger and SHALL NOT be dispatched by `release-please.yml`. It SHALL run in its own GitHub environment, restricted to `main`.
- WHILE one proof run holds the dedicated account THE SYSTEM SHALL serialize further runs through a single `concurrency` group with `cancel-in-progress: false`.
- WHEN an operator runs `login-proof phone` THE SYSTEM SHALL call `telegram.Login` with an in-memory store. It SHALL read the phone number, login code and 2FA password only from environment variables or a no-echo terminal prompt, never from argv flags. It SHALL write nothing to disk except an optional operator-chosen state directory with mode 0700/0600.
- WHEN `login-proof phone` signs in with correct credentials THE SYSTEM SHALL require a persisted session, one successful read-only MCP call, and a logout of the new authorization before reporting `pass`.
- WHEN `login-proof phone -expect wrong-password` or `-expect expired-code` runs THE SYSTEM SHALL report `pass` only if `telegram.Login` failed with the matching typed outcome (`bad_password` / `code_expired`) AND `store.LoadSession` for the proof user returns no session.
- IF the account signed in by any proof does not match the expected service-account Telegram id from the secret / environment THEN THE SYSTEM SHALL rely on `LoginConfig.WantTelegramID` to log the authorization out, store nothing, and report `identity_mismatch`.
- IF an account is not registered (sign-up required) THEN THE SYSTEM SHALL refuse and SHALL NOT create an account.
- THE workflow file, the `cmd/login-proof` package doc and `docs/runbooks/live-login-proof.md` SHALL state that the proof must use the dedicated login-proof service account and never a personal, operator or canary account.

## Out of scope

- Any scheduled, nightly or per-release automatic full login.
- Automating phone-code delivery or bypassing Telegram code/2FA requirements.
- Using the production canary / `TG_LIVE_SESSION` account as the login account.
- Changing the product login behaviour in `internal/telegram/login.go`, `loginqr.go` or `internal/oauth/enable_access.go` (beyond read-only reuse).
- Replacing the #959 synthetic probes or the #960 funnel alerts.
- Reactivating test-DC login (#963 stays as a future path).
- Uploading the evidence to the issue automatically. The operator pastes the evidence line.

## Open questions

- Account choice: this proposal assumes a new, dedicated "login-proof" Telegram account with its own `live-telegram-login` environment secrets. The existing `TG_LIVE_SESSION` account is shared with the production canary (comment in `live_integration_test.go`), and the issue lists "using the monitoring canary as a disposable login account" as a non-goal. If the existing CI account is NOT the canary account and may be reused, the secrets can be shared. The reviewer should confirm.
- The issue asks for a two-step start/confirm phone harness like `cmd/ci-anchor`. `telegram.Login` asks for the code inside one `client.Run` callback, so a true cross-process two-step would require making the product login resumable, which would change the very path under test. This proposal uses one attended foreground process with a no-echo code prompt (pending state lives only in that process). The reviewer should confirm this is acceptable.
- Proving `code_expired` live requires waiting out the code lifetime or submitting a code from an earlier send. The harness supports it, but Telegram may answer `PHONE_CODE_INVALID` instead. In that case the run records `code_invalid` (not pass), and the deterministic fake test is the authority.
- The epic success criteria and roadmap manifest live in mctlhq/.github (#279), not in this repository. This proposal only drafts that change as a separate PR task.
