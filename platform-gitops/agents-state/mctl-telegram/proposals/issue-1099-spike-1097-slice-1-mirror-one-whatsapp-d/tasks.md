# Tasks: issue-1099-spike-1097-slice-1-mirror-one-whatsapp-d

- [ ] 1. Create the isolated module `spikes/whatsapp-forum/` with its own `go.mod`
  (`module github.com/mctlhq/mctl-telegram/spikes/whatsapp-forum`, `go 1.26.10`). Add
  `go.mau.fi/whatsmeow`, `modernc.org/sqlite` and `github.com/mdp/qrterminal/v3`, then run
  `go mod tidy` inside the spike only. DoD: `git diff --stat` shows no change to root `go.mod`,
  `go.sum`, `Dockerfile`, `.dockerignore` or `.github/`. `go list ./...` from the repo root lists
  no `spikes/` package.
- [ ] 2. `config.go`: `Config` and `Load(getenv func(string) string, repoRoot string)`. Validate the
  7 `WAF_*` variables as in design.md, with errors that name the variable but never the value
  (depends on 1). DoD: config_test covers each refusal.
- [ ] 3. `session.go`: find the repo root by walking up to `.git`. Refuse a relative path, a path
  inside the checkout (after symlink resolution) or `0077` permission bits. Create the dir with `0700`. Open
  `sqlstore` with modernc `sqlite` and `waLog.Noop`, then chmod the db files to `0600` (depends on 2).
  DoD: unit test for the refusal and permission cases using `t.TempDir()`.
- [ ] 4. `route.go`: the `Inbound` struct, `Route(cfg, in, startedAt) Decision` with the reason set
  from design.md, and a bounded seen-id set (depends on 2). DoD: pure function with no imports
  of whatsmeow client types (only `types.JID`).
- [ ] 5. `wa.go`: an adapter from `*events.Message` to `Inbound`, extracting text from
  `Conversation`/`ExtendedTextMessage.Text` and setting `HasNonText` for anything else
  (depends on 4). DoD: it only reads event fields.
- [ ] 6. `telegram.go` and `verify.go`: a `net/http` Bot API client (`getMe`, `getChat`,
  `getChatMemberCount`, `getChatMember`, `sendMessage` without `parse_mode`, with 4096-unit
  chunking) and token-free error values. Add `VerifyDestination` (forum supergroup, member count
  2, owner is creator, bot is member/administrator) (depends on 2). DoD: verify_test passes
  against httptest.
- [ ] 7. `main.go`: load the config, verify the destination (fatal on failure), open the session,
  pair by QR to stdout if no device id is stored, then connect. The handler runs Route, then
  re-verify, then send, and logs only `reason`/`count`/`method`/`status`/`error_code`. Shut down
  gracefully on signals. There are no WhatsApp send calls (depends on 3, 5, 6). DoD: `go build .`
  and `go vet ./...` succeed in the spike dir.
- [ ] 8. `README.md`: purpose and link to #1097, the disposable-account and consent
  requirements, the Telegram setup (create bot via BotFather, private supergroup with topics enabled, add
  only the bot, find chat/topic/owner ids), an env file kept outside the checkout, the single
  command `go run .`, the test command, the no-send guarantee, the delivery-receipt caveat, the
  MPL-2.0 note, and teardown (unlink the device on the phone, delete the session dir) (depends on 7).
  DoD: a reviewer can follow it without reading the code.
- [ ] 9. `CHECKLIST.md`: a manual QR and end-device checklist. Pair by QR. Confirm the linked device appears
  on the phone. Send text from the consented DM and see it in the topic. Confirm that a message
  from another DM, a group message, an image, the operator's own message and history are not
  mirrored. Confirm that a third member in the forum causes refusal. Check logs for text, JIDs and
  token. Confirm nothing appears as sent or read on the WhatsApp side. Unlink. Every item and the
  overall result are marked `PENDING (human verification)` (depends on 8).
- [ ] 10. Run `go vet ./... && go test ./...` inside `spikes/whatsapp-forum/` and paste the
  output in the PR description. Run root `go build ./... && go test ./...` to confirm nothing
  changed (depends on 7). DoD: both pass. The PR states that the live result is pending.

## Tests
- [ ] T1. `route_test.go` (offline, synthetic JIDs such as `10000000001@s.whatsapp.net` and
  `20000000002@lid`; never real numbers): table cases cover a forwarded plain text from the peer
  (`Conversation`), a forwarded extended text, a peer matched through `SenderAlt` (LID), and
  ignores for `other_chat`, `group` (`@g.us`), `broadcast` (`status@broadcast`), `own`
  (`IsFromMe`), `history` (timestamp before start), `non_text` (image with caption), `empty`
  and `duplicate` (same id twice).
- [ ] T2. `config_test.go`: each missing variable, consent other than `yes`, a group JID as peer,
  a non-supergroup chat id, a malformed token, a relative session dir, a session dir inside the
  repo root and a `0755` session dir are all refused. Error strings never contain the supplied
  value.
- [ ] T3. `verify_test.go`: a fake Bot API on httptest. The happy path passes. A non-forum chat,
  a member count of 3, an owner who is not creator, a missing bot and an HTTP 401 all fail. The
  error text never contains the token.
- [ ] T4. `nosend_test.go`: parse the non-test `.go` files in the package and fail if any
  references `SendMessage` on a whatsmeow client, `MarkRead`, `SendPresence`,
  `SendChatPresence`, `RevokeMessage` or `Upload`.
- [ ] T5. Manual: run `CHECKLIST.md`. The result stays PENDING until a human verifies it.

## Rollback
The spike is self-contained. Revert the merge commit, or `git rm -r spikes/whatsapp-forum`.
No production code, dependency, image, CI workflow or deployment depends on it. Operators
should also unlink the WhatsApp linked device from the phone and delete `WAF_SESSION_DIR`.
