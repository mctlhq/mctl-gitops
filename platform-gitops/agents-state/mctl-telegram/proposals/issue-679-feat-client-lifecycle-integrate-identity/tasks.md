# Tasks: issue-679-feat-client-lifecycle-integrate-identity

- [ ] 1. Create `internal/lifecycle` with `Facts`, `Step`, `Status`, the exported status, step and reason-code constants, and a pure `Derive(Facts) Status` that follows design.md section 1. Add `FromIdentityRow(db.IdentityRow) Facts`. — DoD: the package has no I/O and full table-driven unit coverage, and `go vet` passes.
- [ ] 2. Add `Store.GetClientLifecycleFacts(ctx, userID)` in `internal/db/client_lifecycle.go`. It reuses `getBotReachability` and `ResolveNotificationPrefs` and reads `identity_captured_at`, `onboarding_completed_at` and the active-session flag. — DoD: it works on SQLite and Postgres test paths and returns nil reachability when no row exists, without inserting one.
- [ ] 3. (depends on 1, 2) Add `GET /api/account/lifecycle` to `AccountHandlers.Register` in `internal/web/account.go`. It returns `lifecycle.Status` plus `remedies`. — DoD: returns 401 without identity and 200 JSON with `Cache-Control: no-store`, and the call is audited like `getNotifications`.
- [ ] 4. Add the optional `TelegramLoginBotUsername` (`TELEGRAM_LOGIN_BOT_USERNAME`) to `internal/config/config.go`. Validate it, and ignore an invalid value with a warning. — DoD: config tests cover set, unset and invalid values.
- [ ] 5. (depends on 1, 2, 4) Add a "Getting started" checklist to `HandleManage` (`internal/web/manage.go`) and the manage template. Each remedy links to connect, to the t.me bot link or text, or to the `#notifications` anchor, and the section also links to `/docs/product-updates`. — DoD: the section renders for connected and disconnected users, and a failed lifecycle read hides the section without breaking the page.
- [ ] 6. (depends on 1, 2) Add the MCP tool `get_my_onboarding_status` to `internal/mcp/tools.go` with read-only annotations and `outputSchema`. Regenerate `docs/tool-descriptors.json` and update `docs/portal-allowlist.json`. — DoD: the descriptor, annotation, output-schema and allowlist tests pass.
- [ ] 7. (depends on 1) Add the omitempty `IdentityRow.LifecycleStage` field and fill it in the `list_telegram_identities` handler through `lifecycle.FromIdentityRow`. — DoD: existing identity tests pass unchanged and a new assertion covers the stage.
- [ ] 8. Refactor the `RecordBotReachability` upsert into an `execer`-based helper. Add `RecordBotReachabilityTx` and a tx-scoped Telegram-id-to-user lookup. — DoD: the behaviour of `RecordBotReachability` is unchanged (existing `reachability_test.go` passes), and the Tx variant writes inside the caller's transaction.
- [ ] 9. (depends on 8) Add `bot.ReachabilityHandler` in `internal/bot/reachability.go` for `db.KindMessage`. It records `reachable` / `inbound_message` / `bot_inbound` through the dispatch tx and returns the outcome `reachability_recorded`. Register it in `cmd/server/main.go`. — DoD: no message is sent, no text is decoded, and the callback kind is still unregistered.
- [ ] 10. (depends on 9) Update the package docs in `internal/notify/classify.go` and `internal/bot/update.go` and the comment in `cmd/server/main.go` to describe inbound evidence. Add a "Client lifecycle" section to `docs/runbook.md` covering stages, reason codes and `TELEGRAM_LOGIN_BOT_USERNAME`. — DoD: the docs tests (`docs/runbook_test.go`) pass.
- [ ] 11. Run `go fmt`, `go vet` and `golangci-lint`. — DoD: all clean, and test fixtures use only the existing personas (Alice, Bob, Carol, Dana) with ids checked with `git grep`.

## Tests

- [ ] T1. `lifecycle.Derive` table test. Cases: a fresh user (stage `identity`); identity captured but not connected; connected with no reachability row (`bot_reachable` unknown, `never_observed`); `blocked` and `cannot_initiate` (`action_required`, reason copied); reachable with `product_updates` defaulted (stage `notifications_decided`); explicitly unsubscribed (counts as decided, stage `complete`); onboarded but disconnected (`connected` done with `session_disconnected`).
- [ ] T2. `GetClientLifecycleFacts` on SQLite: no rows, all rows, and a revoked session. Verify that no `client_bot_reachability` row is created by the read.
- [ ] T3. `/api/account/lifecycle`: 401 without identity, and 200 with the expected JSON shape and `no-store`.
- [ ] T4. Manage page: renders the checklist; renders the t.me link only when the username is configured; and still renders disconnect when the lifecycle read fails (inject a failing store).
- [ ] T5. MCP `get_my_onboarding_status`: matches the REST output for the same user, has no admin scope requirement, and is present in the descriptor snapshot with `readOnlyHint=true`.
- [ ] T6. `list_telegram_identities` includes `lifecycle_stage`, and every other field is byte-identical to the existing golden output.
- [ ] T7. Bot handler: a message from a known private chat records `reachable` with source `bot_inbound`. An unknown, negative or ambiguous chat records nothing. A handler error rolls back the row and the done mark together. A redelivered update is not dispatched twice (`DispatchOnce`).
- [ ] T8. Inbound `reachable` overwrites a prior `blocked`, and a later non-conclusive outbound outcome (429) leaves it unchanged.
- [ ] T9. Regression: `broadcast.Evaluate` tests are unchanged and pass. The lifecycle `bot_reachable` status and the broadcast `SkipUnreachable` decision agree for every reachability state.
- [ ] T10. Redaction: the new handlers log no chat id, phone or message content (assert on captured slog output).

## Rollback

All changes are additive and need no schema migration. To roll back, revert the PR and
redeploy the previous image tag (`mctl_rollback_service`). To disable only the inbound
reachability writes without a deploy, unset `BOT_RECEIVER_ENABLED`, which stops the
receiver and therefore the handler. Rows already written with `source = bot_inbound` are
valid reachability observations and can stay. If they must be removed, run
`DELETE FROM client_bot_reachability WHERE source = 'bot_inbound'`. That returns those users
to `unknown` and has no other effect. Unsetting `TELEGRAM_LOGIN_BOT_USERNAME` removes the
t.me link from the manage page.
