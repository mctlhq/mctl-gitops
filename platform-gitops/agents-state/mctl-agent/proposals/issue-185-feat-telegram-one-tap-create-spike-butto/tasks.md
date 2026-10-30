# Tasks: issue-185-feat-telegram-one-tap-create-spike-butto

- [ ] 1. Add `TelegramCallbackQuery`, `InlineKeyboardMarkup` and `InlineKeyboardButton`, plus
  `TelegramUpdate.CallbackQuery`, in `internal/notify/telegram.go` — DoD: a real Bot API
  callback_query JSON fixture, including an inaccessible message with `date: 0`, unmarshals
  into the expected fields.
- [ ] 2. Factor a private `callAPI(ctx, method, payload)` out of `doSendTo`, and add
  `AnswerCallbackQuery` and `EditMessageReplyMarkup` (depends on 1) — DoD: `doSendTo`
  behaviour is unchanged (existing `telegram_test.go` passes), the new methods post the right
  JSON to `WithAPIBase` stubs, and no error string contains the bot token.
- [ ] 3. Add `ownerUserID` plus `WithOwnerUserID` and `OwnerUserAllowed` to `notify.Telegram`
  — DoD: returns false when unset (no open mode), true only for an exact match.
- [ ] 4. Config: `TELEGRAM_OWNER_USER_ID` (int64, invalid value fails startup) and
  `SCOUT_SPIKE_REPOS` (comma list, validated names, `.` and `..` rejected) in
  `internal/config/config.go` — DoD: table tests in `config_test.go` cover valid, empty and
  invalid values.
- [ ] 5. Add `SearchIssues(ctx, query, page)` and `CreateIssue(ctx, repo, title, body, labels)`,
  and a repo-accessibility check (`GetRepo`), to `internal/fixer/github.go` — DoD: they use
  `f.client` (rotating token) and `f.owner`, and are exercised against an httptest server via
  `SetBaseURL`.
- [ ] 6. New package `internal/scoutspike` with `ParseCallbackData`, `FindDraft`, `ParseDraft`,
  `NormaliseURL` and `Service.Create`, which runs the per-source lock, the 10-minute memo,
  the repo check, the search (fail closed on error, incomplete results or page cap), compare,
  then create (depends on 5) — DoD: unit tests T1-T8 pass, and `NormaliseURL` matches the
  mctl-agents `dedupe.normalise_url` test vectors copied in as a table.
- [ ] 7. Route `callback_query` in `telegramWebhookHandler` before the `Message == nil` return,
  and implement `handleTelegramCallback`: auth order, answer, then row replacement through
  `EditMessageReplyMarkup`. Add `Options.ScoutSpikes` (depends on 2, 3, 6) — DoD: handler tests
  T9-T14 pass, and text commands and `/start` tests are unchanged.
- [ ] 8. Wire it up in `cmd/agent/main.go`: `telegram.WithOwnerUserID`, `scoutspike.NewService`,
  `Options.ScoutSpikes`, and a startup log line with `scout_spike_enabled` and the repo count
  (depends on 4, 7) — DoD: `go build ./...`, `go vet ./...` and `go test ./...` are green.
- [ ] 9. Docs: update the `POST /api/v1/telegram` line in CLAUDE.md, add the two env vars to
  README — DoD: docs name the callback, the auth requirements and the fail-closed defaults.
- [ ] 10. Release through a branch and a `chore: release x.y.z` PR, then tag the merge commit
  (no `v` prefix) (depends on 8, 9) — DoD: image built by `build.yml`.
- [ ] 11. Follow-ups outside this repo, not done by the implementer here: set
  `TELEGRAM_OWNER_USER_ID` and `SCOUT_SPIKE_REPOS` in mctl-agent's mctl-gitops deployment
  values, then ship the mctl-agents `render.py` button. Optionally, narrow the mctl-agent token
  mint — DoD: tracked as linked issues.

## Tests

Each regression test must fail when its guard is removed. Note in the test comment which
guard it pins.

- [ ] T1. `ParseCallbackData`: accepts `scout:create:1` and `scout:create:12`. Rejects
  `scout:create:0`, `scout:create:01`, `scout:create:100`, `scout:create:`,
  `scout:create:1x` and `scout:other:1`.
- [ ] T2. `FindDraft`: finds `Draft spike 3` among several rows. A missing button, a button
  without a URL, and two `Draft spike 3` buttons each return `ErrDraftNotFound`.
- [ ] T3. `ParseDraft` refusals (table): `http://` scheme, `github.com.evil.io`,
  `gist.github.com`, `github.com:443`, `user@github.com`, owner `other`, repo outside the
  allowlist, repo `..`, path `/mctlhq/r/issues/new/x`, path `/mctlhq/r/pulls/new`, title not
  starting with `spike:`, missing `Source:` line, oversize title or body.
- [ ] T4. `ParseDraft` success: owner, repo, title and body are decoded correctly (percent
  encoding, newlines), and `labels=bug,spike:scout` in the URL still yields exactly
  `["spike:scout"]`.
- [ ] T5. `NormaliseURL` table, using vectors from mctl-agents `dedupe`.
- [ ] T6. `Service.Create` with a fake GitHub where search returns an issue with a matching
  `Source:` (different case or trailing slash): returns AlreadyExists, and `CreateIssue` is
  never called.
- [ ] T7. `Service.Create` with search failures, one case each for an error, a 5xx,
  `incomplete_results: true` and the page cap reached: returns `ErrSearchFailed`, and
  `CreateIssue` is never called.
- [ ] T8. `Service.Create` double tap: two concurrent calls for the same draft, with search
  always returning empty (index lag), produce exactly one `CreateIssue` call. The second call
  returns AlreadyExists from the memo.
- [ ] T9. Handler happy path: an httptest Telegram stub plus a fake GitHub. One
  `POST /repos/mctlhq/<repo>/issues` call with label `spike:scout`, `answerCallbackQuery`
  text `Created <repo>#<n>`, and `editMessageReplyMarkup` with the target row replaced by
  `#<n> ->` linking to `html_url` and the other rows unchanged.
- [ ] T10. Handler second tap: answer text `Already exists: <repo>#<n>`, no create.
- [ ] T11. Handler auth: a non-allowlisted chat, a non-owner `from.id`, an unset owner id, an
  unset webhook secret and an empty chat allowlist each make zero GitHub calls and zero
  create calls. A non-allowlisted chat or user also makes zero Telegram calls, and the log
  output contains neither id.
- [ ] T12. Handler URL outside `github.com/mctlhq/<allowed repo>/issues/new`: answer
  `Failed: draft target not allowed`, no GitHub calls.
- [ ] T13. Handler search failure: answer `Failed: could not check for duplicates`, no
  create, keyboard not edited.
- [ ] T14. Handler: the callback path never calls `getUpdates`, `deleteWebhook` or
  `setWebhook` (the stub records method names), and always returns HTTP 200 once the secret
  is valid.

## Rollback

- Fast: unset `SCOUT_SPIKE_REPOS` (or `TELEGRAM_OWNER_USER_ID`) in mctl-agent's deployment
  values. Every `scout:create` press is then refused and nothing is created, and other
  Telegram behaviour is unaffected.
- Full: revert the PR and release the previous image tag (bump the gitops manifest back). If
  the mctl-agents render change already shipped, revert it too or accept that the `Create`
  buttons are dead. The `Draft spike N` URL fallback keeps working throughout.
- Issues already created are ordinary GitHub issues labelled `spike:scout`. Close them by hand
  if needed. There is no state to clean up in mctl-agent.
