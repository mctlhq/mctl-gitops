# Tasks: issue-902-reduce-one-day-drop-off-phone-step-chann

Amended 2026-10-28: the `list_dialogs` broadcast flag is dropped (channels are readable since 0.98.0) and the onboarding reminder (former tasks 10-14) is split out to #912.

- [ ] 1. Phone-number retention check, end to end (design §1): `enableSession` / `loginFlow`, `internal/telegram/login.go`, `telegram_accounts` including the contents of `session_encrypted` (gotd session data, any stored `tg.User`), `users`, `audit_logs`, digest, `bot_updates`, metric labels, `slog` calls and wrapped error strings. Also verify the session encryption scheme and the Active Sessions name. DoD: the PR description lists each place with a code reference and the finding; if the number is kept anywhere, the copy in task 2 says so, and `/privacy` is corrected or the PR says why not.
- [ ] 2. Phone-step explanation in `enablePhoneTemplate` (`internal/oauth/enable_access_page.go`) covering why the number is needed, what is and is not retained (only as proven by task 1), the session, how to disconnect, and links to `/privacy` and `/security`. Shown in both wizard and non-wizard modes, with no JS or CSP change (depends on 1). DoD: the page renders the block in both modes, and the form is unchanged.
- [ ] 3. "Connect funnel" section in `docs/runbook.md` with portable SQL: the share of `connect:oidc_callback` users reaching `connect:phone_submitted`, the "success but no tool call" users split by connect flow where the data allows it, and the one-day-active share. DoD: the queries run on SQLite in a test or a doc snippet, and `docs/runbook_test.go` still passes.
- [ ] 4. Extend the `CHANNEL_INVALID` action in `internal/mcp/errorcatalog.go`: retrying the same id fails again; use an id from `list_dialogs`. DoD: catalog test asserts the new text.
- [ ] 5. Rewrite `broadcastContentError.Error()` (`internal/telegram/broadcast_content.go`), used only while `BROADCAST_CONTENT_ENABLED` is off, to say retrying will not change the refusal and what still works. No mention of a `list_dialogs` flag. Keep `ErrBroadcastContent` and `ReasonRefused`. DoD: existing refusal tests updated, `errors.Is` still holds.
- [ ] 6. Regenerate `docs/tool-descriptors*.json` and add a `docs/product-updates/*.yaml` entry only if tasks 4-5 change a descriptor or the gate requires it (depends on 4, 5). DoD: `cmd/productupdates` gate and `internal/mcp/descriptors_test.go` pass; the PR says which artifacts were needed.
- [ ] 7. Wizard success page (`internal/web/connect.go` `connectSuccessTemplate`): per-client setup for Claude, ChatGPT and other MCP clients, with the MCP URL, `/docs` anchors and a "try: list my recent Telegram chats" line. Add matching anchors in `internal/web/docs.html`. DoD: the page renders all three sections, and the CSP is unchanged.
- [ ] 8. OAuth interstitial (`internal/oauth/enable_access_page.go` `connectSuccessTemplate`): neutral first-request hint with a link to setup help; no "add the connector" wording. DoD: the redirect script and timing are unchanged.

## Tests
- [ ] T1. `enable_access` page test: the phone screen contains the why, retention and disconnect text and the `/privacy` and `/security` links in both wizard and non-wizard modes, and the form action and fields are unchanged.
- [ ] T2. `broadcast_content` test: with the switch off, the refusal text says retrying will not help and mentions "get_unread_messages without peer", contains no `broadcast: true` reference, and `errors.Is(err, ErrBroadcastContent)` holds. With the switch on, nothing is refused (existing test still passes).
- [ ] T3. MCP test (`internal/mcp`): a kill-switch refusal from `get_messages` yields an error result with audit reason `refused`, and the `CHANNEL_INVALID` catalog text contains the no-retry guidance.
- [ ] T4. Connect success page tests (`internal/web/connect_test.go`): the Claude, ChatGPT and other-client sections, their `/docs` links and the MCP URL are present. The OAuth interstitial test checks the hint line and setup-help link, the absence of "add the connector" wording, and that the redirect script is still present.
- [ ] T5. Product-update gate and descriptor snapshot tests pass.

## Rollback
- All changes are copy and error text: revert the release commit, or roll back the image tag with `mctl_rollback_service` to the previous tag. No data or schema depends on them.
