# Tasks: issue-1097-spike-reply-to-personal-whatsapp-dms-and

- [ ] 1. Scaffold the nested module `spikes/whatsapp-forum/`: `go.mod` (module
  `github.com/mctlhq/mctl-telegram/spikes/whatsapp-forum`, go 1.26.10, requires
  `go.mau.fi/whatsmeow`, `modernc.org/sqlite`, and the root module via
  `replace github.com/mctlhq/mctl-telegram => ../..`), `README.md`, and a `.gitignore` for
  `*.db`, `*.sqlite*`, `.env*`. Add `spikes/` to the root `.dockerignore`. DoD: root
  `go build ./...`, `go test ./...` and `go.mod`/`go.sum` are unchanged. `go build ./...`
  succeeds inside the nested module.
- [ ] 2. Add `internal/logx` (depends on 1): an slog JSON handler wrapped in
  `audit.NewRedactingHandler`, plus `ChatRef(key, jid)` (truncated HMAC-SHA256). DoD: a unit
  test shows `text`, `phone` and JID-shaped values never reach output.
- [ ] 3. Add `internal/store` (depends on 1): schema for `mapping`, `link`, `inbound`,
  `tg_update`, `outbox`, with the composite keys and UNIQUE constraints from design.md.
  Transition functions: `AcceptInbound`, `AcceptUpdate`, `EnqueueOutbound`,
  `BeginSend` (recheck plus `pending`->`sending` in one tx), `FinishSend`,
  `RecoverSending` (`sending`->`uncertain`), `MarkReconciled`. Pending text is sealed with
  `internal/crypto.AESGCM` and purged on terminal states. The DB is created 0600 under a
  0700 `$WABRIDGE_HOME` that is refused if it lies inside the git worktree. DoD: store
  tests cover every transition and every illegal transition.
- [ ] 4. Add `internal/tg` (depends on 1): a minimal Bot API client (`getUpdates`,
  `sendMessage` with `message_thread_id` and `reply_parameters`, no parse mode, `getChat`,
  `getChatMember`, `getChatMemberCount`) that strips the token from errors the way
  `internal/botapi/botapi.go` does, plus an in-memory fake. DoD: httptest-based tests,
  including token-redaction.
- [ ] 5. Add `internal/wa` (depends on 1): `Source` and `Sender` interfaces, a whatsmeow
  adapter (sqlstore under `$WABRIDGE_HOME`, `GenerateMessageID`, `SendMessage` with
  `SendRequestExtra{ID}`, mapping of `events.Message`/`Receipt`/`LoggedOut`, plain-text
  extraction only), and a fake with fault injection (timeout, lost response, block until
  cancel, crash point). Also a `spikefault` build tag for the real binary. DoD: the adapter
  compiles, and fake tests exercise each fault.
- [ ] 6. Add `internal/bridge` inbound mirror (depends on 2, 3, 4, 5): drop unmapped or
  unlinked; dedupe on (chat, sender, msg ID); suppress own outbox echoes; attribute native
  phone sends as "you (other device)"; post to the mapped topic; retry posts with a NULL
  `tg_msg_id`. DoD: offline tests T1-T4, T9 pass.
- [ ] 7. Add the `internal/bridge` outbound gate and dispatcher (depends on 6): the ordered
  checks from design.md with `rejected_*` outcomes, the dispatch-time recheck inside
  `BeginSend`, the outcome classification into sent/failed/uncertain, startup
  `RecoverSending`, receipt-driven `uncertain`->`sent`, and the fixed "delivery uncertain"
  topic notice. DoD: offline tests T5-T8, T10-T12 pass.
- [ ] 8. Add `cmd/wabridge` (depends on 6, 7): `pair` (QR on TTY only, human-run, no QR in
  logs), `run` (startup forum invariants: is_forum, member count 2, owner is creator, bot is
  admin), `map`, `unmap`, `list` (labels and chat refs only), `unlink` (Logout, delete
  device store, set link=unlinked), and `reconcile [--mark sent|failed <id>]`. DoD:
  `wabridge --help` documents every command. `run` refuses a forum that breaks an invariant
  (test T13).
- [ ] 9. Add `testdata/` synthetic fixtures (depends on 6): two chats (a DM and a group) with
  overlapping message IDs, duplicate events, native phone sends, own-echo events, and
  Telegram updates from the owner and a non-owner, in the right and wrong topics. Use
  personas Alice/Bob/Carol/Dana and fictional `555` numbers, checked with `git grep`. DoD:
  every fixture is used by at least one test, and T14 passes.
- [ ] 10. Add `.github/workflows/spike-whatsapp.yml` (depends on 1): `pull_request` and
  `push` path filter `spikes/whatsapp-forum/**`, pinned actions as in `live-telegram.yml`,
  `go vet`, `go test -race`, `govulncheck` with `working-directory: spikes/whatsapp-forum`,
  `permissions: contents: read`, no secrets. DoD: the workflow passes on the PR.
- [ ] 11. Write `docs/runbooks/whatsapp-forum-spike.md` (depends on 8): prerequisites
  (disposable number, second device, consented partner, test group, dedicated test bot,
  never `@MCTL_AI_bot`), forum setup, human-only pairing, mapping, the separately marked
  **Live checklist** (L1-L10 below), reconcile procedure, unlink and teardown, and what
  must never be pasted into evidence. Link it from `docs/runbooks/` and the spike README.
  DoD: a reviewer can follow it end to end without reading code.
- [ ] 12. Write `docs/reports/whatsapp-forum-spike.md` (depends on 7-11), styled after
  `docs/reports/mcp-apps-spike.md`. It contains an acceptance matrix, with each row tied to
  a test name, a live check ID with its result, or `pending` / "not measured here". It also
  contains the evaluation: unofficial-client terms and ban risk, observed restrictions,
  linked-device constraints, protocol churn and whatsmeow maintenance cadence, MPL-2.0, the
  plaintext device store, and mautrix-whatsapp as a reference. It ends with an explicit
  go / no-go / go-with-conditions decision and the conditions for a pilot. DoD: no claim
  lacks evidence or a "not measured" marker. T14 passes over the report.

## Tests

Offline tests (fake transports, run in the nested module's CI):
- [ ] T1. A mapped DM and a mapped group each mirror one plain-text message, with sender
  attribution, into their own topic.
- [ ] T2. An unmapped chat's message is dropped. Nothing is posted and the outcome counter
  is incremented.
- [ ] T3. The same WhatsApp event replayed 3 times, including across a store reopen, is
  mirrored once.
- [ ] T4. Equal message IDs in the DM and the group mirror as two distinct messages into
  their respective topics. A reply to each routes back to its own chat.
- [ ] T5. A non-owner reply, a non-reply, a reply to a non-mirrored message, a wrong-topic
  reply and a wrong-chat message are each rejected with their `rejected_*` outcome and zero
  sends.
- [ ] T6. A duplicate Telegram update produces one outbox row and one send.
- [ ] T7. Unmapping or unlinking between enqueue and dispatch causes rejection at
  `BeginSend` (TOCTOU).
- [ ] T8. Ambiguous outcomes (timeout, lost response, cancel) lead to `uncertain`, no
  resend, and one topic notice.
- [ ] T9. Own-echo suppression: a message event carrying an outbox `wa_msg_id` is not
  mirrored. A native phone send is mirrored as "you (other device)" and never dispatched.
- [ ] T10. Crash after the `sending` commit and before the call: after restart the row is
  `uncertain` and the fake records zero or one send, never two.
- [ ] T11. A receipt for an `uncertain` row's message ID moves it to `sent`. `reconcile
  --mark` records the resolution and does not resend.
- [ ] T12. `LoggedOut` or `unlink` stops forwarding in both directions and deletes the
  device store files.
- [ ] T13. `run` refuses a forum that breaks an invariant: not a forum, member count other
  than 2, owner not creator, or bot not admin.
- [ ] T14. `TestEvidenceHygiene`: logs captured during T1-T13, `testdata/` and the report
  contain no phone-number-like runs, real JID shapes, bot-token shapes, QR payload prefixes
  or fixture message text.

Live checklist (separately marked in the runbook; human pairs; each item recorded as `pass`,
`fail` or `pending`):
- [ ] L1. A human pairs the disposable account through `pair`. The QR appears only on the
  terminal.
- [ ] L2. DM and group to Telegram: messages appear in the correct topics with attribution.
- [ ] L3. Telegram to DM and to group: verify receipt on the partner's external device.
- [ ] L4. Overlap and cross-routing: interleaved messages in both chats; no
  misrouted message on either device.
- [ ] L5. Restart the bridge during an outbound send (with `spikefault`): no duplicate on
  the external device, and the uncertain row is reconciled by hand.
- [ ] L6. A native phone send shows as "you (other device)" and is not echoed back to
  WhatsApp.
- [ ] L7. A second Telegram account (temporarily added, then removed) replying is rejected,
  and `run` refuses to start while it is a member.
- [ ] L8. A wrong-topic reply and an unmapped chat are rejected or dropped.
- [ ] L9. `unlink`: the device disappears from WhatsApp's linked devices, and new messages
  are not forwarded.
- [ ] L10. Note any account warnings or restrictions seen during the run.

## Rollback

The spike changes nothing that ships. To roll back, revert the PR, or delete
`spikes/whatsapp-forum/`, `.github/workflows/spike-whatsapp.yml`, the two docs and the
`.dockerignore` line. No root module, image, database or gitops change needs undoing. On
the operator side, run `wabridge unlink`, check that the device is gone from WhatsApp's
"Linked devices", delete `$WABRIDGE_HOME`, revoke the test bot through @BotFather, and
delete the test forum.
