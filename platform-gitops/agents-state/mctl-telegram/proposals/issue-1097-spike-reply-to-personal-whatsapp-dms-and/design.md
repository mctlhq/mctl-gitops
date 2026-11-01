# Design: issue-1097-spike-reply-to-personal-whatsapp-dms-and

## Current state

mctl-telegram is a Go 1.26 MCP server (`go.mod`, module `github.com/mctlhq/mctl-telegram`)
for Telegram user accounts, built on `gotd/td`. Nothing in the repository talks to
WhatsApp, and `go.mod` has no whatsmeow dependency. The parts that matter for this spike:

- **Spike conventions.** The only prior spike report is `docs/reports/mcp-apps-spike.md`
  (issue #569). It ties every claim to merged code, an automated probe, or an explicit
  "not measured here". It also keeps live-host testing as a separate, explicitly deferred
  concern. `.github/ISSUE_TEMPLATE/spike.yml` frames a spike as a question with outcomes.
  Runbooks live in `docs/runbook.md` and `docs/runbooks/*.md`.
- **Live tests are segregated.** Live Telegram checks run behind the `livetg` build tag and
  only through the manual `workflow_dispatch` workflow `.github/workflows/live-telegram.yml`.
  That workflow fails if the live test skipped ("a run that tested nothing must not look
  like a pass"). The spike reuses this "pending is not passed" rule.
- **Send safety.** ADR 0002 (`docs/adr/0002-send-gate.md`) sends only when deployment,
  token scope and owner consent all agree (`evaluateWriteGate` in `internal/mcp/tools.go`),
  and adds a per-recipient cap (`internal/audit/ratelimit.go`). The spike's outbound gate
  has the same shape: several independent conditions, all rechecked at dispatch.
- **Exactly-once update handling.** `internal/bot/receiver.go` long-polls the Bot API.
  Through its `Store` interface (`AcceptUpdate`, `NextOffset`, `ListPendingUpdates`,
  `DispatchOnce`) it persists each update ID before dispatching and dispatches inside a
  transaction. Drops are counted (`Counter.CountUpdate`) rather than logged with content.
  The spike copies this pattern for Telegram updates.
- **Bot sends.** `internal/botapi/botapi.go` is the one Bot API sender. It sends plain text
  with no parse mode and strips the token from transport errors. It has no
  `message_thread_id` or reply support, so the spike needs its own small client.
- **Redaction.** `internal/audit/redact.go` provides `NewRedactingHandler`, which redacts
  `sensitiveKeys` (`text`, `body`, `phone`, ...) case-insensitively, plus `ScrubText`.
- **Encryption.** `internal/crypto/aesgcm.go` provides `AESGCM.Seal/Open` and
  HKDF-derived per-user keys (`SealForUser`, `BlindIndexForUser`).
- **Build scope.** `Dockerfile` copies the whole tree but builds only `./cmd/server`,
  `./cmd/login` and `./cmd/canary`. `.github/workflows/build.yml` runs `go vet ./...`,
  `go build ./...`, `go test -race ./...` and `govulncheck ./...` from the root. A nested
  Go module is outside all of these.

Deployed state checked:
- `mctl_list_services(team=mctl)` returned an empty list. No `mctl` tenant hosts this
  service.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, image tag
  `0.121.1`, `ALLOW_SEND: "true"`, login bot `MCTL_AI_bot`. The comment there says
  `BOT_RECEIVER_ENABLED` "must NEVER be set to true", because `@MCTL_AI_bot`'s updates are
  webhook-owned by mctl-agent. So the spike must not use the login bot: a second consumer of
  its updates would break mctl-agent.
- `mctl_get_service_status(team=labs, service=mctl-telegram)`: ArgoCD Healthy/Synced,
  host `tg.mctl.ai`, port 8080, database present, image `0.121.1`.
- `services/labs/mctl-telegram-preview/` also exists. The spike touches neither service.
- No WhatsApp-related configuration appears in either gitops values file.

## Proposed solution

### Placement: an isolated nested module

`spikes/whatsapp-forum/` is a separate Go module
(`github.com/mctlhq/mctl-telegram/spikes/whatsapp-forum`) with its own `go.mod`. It
requires `go.mau.fi/whatsmeow` and `modernc.org/sqlite`, which is CGO-free and already used
by the root module. To reuse `internal/audit` (redaction) and `internal/crypto` (AES-GCM),
it requires the root module through `replace github.com/mctlhq/mctl-telegram => ../..`.
Go's `internal` rule is path-based, and the nested module's path is under the root.
Consequences:

- The root `go.mod`, `go.sum`, Docker image and root CI are untouched. whatsmeow, licensed
  MPL-2.0, never enters the shipped binary.
- `.dockerignore` gains `spikes/`, so the spike is not even in the build context.
- A path-filtered workflow, `.github/workflows/spike-whatsapp.yml`, runs `go vet`,
  `go test -race` and `govulncheck` inside the nested module on `pull_request` paths
  `spikes/whatsapp-forum/**`. It has no secrets and makes no live calls.

### Components (all under `spikes/whatsapp-forum/`)

```
cmd/wabridge/main.go      pair | run | map | unmap | list | unlink | reconcile
internal/store/           SQLite schema + transitions (bridge.db, separate from whatsmeow's store)
internal/wa/              Sender/Source interfaces; whatsmeow adapter; fake for tests
internal/tg/              minimal Bot API client (getUpdates, sendMessage w/ message_thread_id
                          + reply_parameters, getChat, getChatMember, getChatMemberCount); fake
internal/bridge/          inbound mirror, outbound gate, dispatcher, reconciler
internal/logx/            slog JSON handler wrapped in audit.NewRedactingHandler; chat-hash helper
testdata/                 synthetic event fixtures (JSON) — no real ids, numbers or text
README.md                 points to the runbook and report
```

`run` is a single standalone process. It holds one whatsmeow client and one long-poll loop
against a **dedicated test bot**, which is never `@MCTL_AI_bot`. Ingestion needs no MCP
client and no assistant session. MCP stays optional and is not built.

### Configuration

The configuration is environment plus a 0600 file in `$WABRIDGE_HOME`, which must be
outside the repo with mode 0700:
- `WABRIDGE_TG_BOT_TOKEN`: the test bot's token.
- `WABRIDGE_OWNER_TG_ID`: the one Telegram user ID allowed to reply.
- `WABRIDGE_FORUM_CHAT_ID`: the test forum supergroup.
- `WABRIDGE_KEY`: 32 bytes, used for AES-GCM over pending text and for HMAC over chat-hash
  log keys.

At startup, `run` refuses to start unless all of these hold:
- `getChat` says the forum has `is_forum=true`;
- `getChatMemberCount == 2`;
- `getChatMember(owner)` is `creator`;
- the bot is an administrator.

### Data model (`bridge.db`)

- `mapping(wa_chat_jid PK, topic_id UNIQUE, label, active, created_at)`. The mapping is
  explicit: `map --wa-chat <jid> --topic <thread_id>`. Nothing is auto-created. A chat
  without an active row is unmapped. The allowlist is exactly this set of active rows.
- `link(state: linked|unlinked, changed_at)`.
- `inbound(wa_chat_jid, wa_sender_jid, wa_msg_id, tg_msg_id, is_from_me, PK(wa_chat_jid,
  wa_sender_jid, wa_msg_id))`. This table is the dedupe key and the lookup for
  reply-to-target. `UNIQUE(tg_msg_id)` maps a mirrored Telegram message back to its WhatsApp
  chat. The composite key keeps equal WhatsApp message IDs in different chats apart.
- `tg_update(update_id PK, outcome)`: the same idea as `AcceptUpdate` in
  `internal/bot/receiver.go`, with the offset derived from it.
- `outbox(id, tg_update_id UNIQUE, tg_msg_id UNIQUE, wa_chat_jid, wa_msg_id UNIQUE,
  text_sealed, state, outcome, created_at, updated_at)`. `state` is one of `pending`,
  `sending`, `sent`, `uncertain`, `failed`, `rejected`. `text_sealed` is set to NULL when
  the row reaches a terminal state.

No message text is stored except sealed pending outbound text. JIDs stay inside the local
DB. They contain phone numbers and are never logged or committed.

### Inbound flow

whatsmeow delivers an `events.Message`. Then:
1. If `link != linked`, drop the event.
2. If the chat is unmapped, drop it with outcome `unmapped`.
3. If the message is not `Conversation` or `ExtendedTextMessage.Text`, post a fixed
   placeholder or drop it.
4. Insert into `inbound` with `ON CONFLICT DO NOTHING`. A conflict means a duplicate: stop.
5. If `wa_msg_id` matches an `outbox.wa_msg_id`, it is our own echo: mark `is_from_me` and
   do not post.
6. Otherwise post `"<sender display name>: <text>"`, or `"you (other device): <text>"` for
   a native `IsFromMe` send. The post goes to the mapped `topic_id` with no parse mode.
   Then store `tg_msg_id`.

If the post fails after the insert, the row keeps `tg_msg_id` NULL and a retry loop posts
it. A Telegram duplicate is the lesser risk on this side and is counted as such.

whatsmeow `events.Receipt` and server acks for an outbox `wa_msg_id` move `sending` or
`uncertain` rows to `sent`. `events.LoggedOut` triggers the unlink path.

### Outbound flow (the gate)

A Telegram update arrives. The bridge first inserts `tg_update`; a duplicate update ID is a
no-op. Then it evaluates conditions in order and records the first failure as a `rejected_*`
outcome. A rejection is only counted. It never echoes content and never notifies anyone
other than the owner. The conditions:
1. the update's chat is `WABRIDGE_FORUM_CHAT_ID`;
2. `from.id == WABRIDGE_OWNER_TG_ID`, and the message is not from a bot;
3. `reply_to_message` is present and its `message_id` is an `inbound.tg_msg_id`;
4. `message_thread_id == mapping.topic_id` for that inbound row's chat;
5. the mapping is active and `link == linked`;
6. the text is plain and non-empty.

If all of these pass, the bridge inserts an outbox row as `pending`, with `wa_msg_id`
pre-generated by `client.GenerateMessageID()` and the text sealed. All of this happens in
one transaction.

The dispatcher then runs one transaction that re-reads mapping, link and owner config and
moves the row to `sending`. Two things are checked again at this point: the forum
member-count invariant, through a short-cached `getChatMember`, and the owner's continued
membership. Only after that commit does it call
`SendMessage(chatJID, msg, whatsmeow.SendRequestExtra{ID: wa_msg_id})`. The result:
- Success: `sent`, and the text is purged.
- Definite pre-send error (not connected, validation): `failed`.
- Timeout, context cancel, connection drop or any other ambiguous error: `uncertain`.

Startup recovery turns every `sending` row into `uncertain`. Nothing ever resends
automatically. An `uncertain` row produces one fixed notice in its topic ("delivery
uncertain, check WhatsApp; ref <outbox id>") and appears in `wabridge reconcile`. The
operator checks the external device and runs `reconcile --mark sent|failed <id>`. A
`failed` row still needs a new owner reply to send again.

### Fault injection

`internal/wa.Sender` is an interface. The test fake can:
- drop the response after "sending";
- return a timeout;
- block until the context is cancelled;
- simulate a process kill between the `sending` commit and the call, by stopping the
  dispatcher with an injected panic recovered in the test harness.

A `spikefault` build tag exposes the same injections in the real binary for live
restart-around-send checks. The tag is off by default.

### Logging and evidence hygiene

All logging goes through `audit.NewRedactingHandler`. Attributes are limited to:
- outcome codes;
- outbox IDs;
- `chat_ref = hex(HMAC(WABRIDGE_KEY, jid))[:12]`;
- counts.

`pair` renders the QR only when stdout is a TTY, prints nothing to the log, and records only
"paired" or "timeout". The `testdata/` fixtures use synthetic JIDs in the reserved
fictional `555` range. Telegram IDs and display names reuse the repo's personas (`Alice`,
`Bob`, `Carol`, `Dana`), checked with `git grep` per `.claude/CLAUDE.md`. A test,
`TestEvidenceHygiene`, scans `docs/reports/whatsapp-forum-spike.md` and `testdata/` for
phone-number-like digit runs, `@s.whatsapp.net`, `@g.us` with non-fixture IDs, bot-token
shapes and the QR prefix `2@`, and fails if it finds any.

### Deliverables

1. The proof-of-concept module above.
2. `docs/runbooks/whatsapp-forum-spike.md`, covering prerequisites, human-only pairing,
   forum and bot setup, map/unmap, the live checklist, reconcile, unlink and teardown.
3. `docs/reports/whatsapp-forum-spike.md`, styled after `mcp-apps-spike.md`. It contains:
   - an acceptance matrix where each row is backed by an offline test name or a live
     check (`pending` until a human runs it);
   - a risk section: WhatsApp's terms prohibit unofficial clients, the ban/restriction
     history of whatsmeow and mautrix-whatsapp users, linked-device limits (a 14-day
     phone-offline unlink), protocol churn, whatsmeow's release cadence, MPL-2.0
     obligations, and whatsmeow's plaintext device store;
   - an explicit go / no-go / go-with-conditions recommendation.

## Alternatives

- **Use the Telegram user account (gotd, as the server does) instead of a bot to post into
  the forum.** Dropped for two reasons. Mirrored posts would come from the owner's own
  account, so "a reply by the owner" and "a mirrored message" would be indistinguishable by
  sender. That weakens the owner check. It would also need a live Telegram user session on
  the spike host. A dedicated bot keeps the sender roles separate and needs only a token.
- **Build inside the root module (`cmd/wabridge`, `internal/whatsapp`).** Dropped. It would
  pull whatsmeow and its transitive dependencies into the shipped module's `go.sum`,
  govulncheck surface and Docker build context, which conflicts with "no production
  rollout" and "isolated". A nested module can be deleted without trace.
- **Run mautrix-whatsapp with a Matrix homeserver and a Telegram bridge.** Dropped. The
  mautrix bridge is a strong reference for double-puppeting and echo handling, but the
  stack (homeserver plus two bridges) is far heavier than the question needs. Its
  idempotency would also be Matrix's, not something this spike can verify end to end.
- **Use the WhatsApp Business / Cloud API.** Explicitly deferred by the issue. It cannot
  act as an existing personal account in existing personal chats anyway.

## Platform impact

- **Migrations:** none in the root module. `bridge.db` is a local SQLite file created by the
  spike, outside the repo.
- **Backward compatibility:** no change to any shipped binary, tool surface
  (`docs/tool-descriptors*.json`), API or deployment. `labs/mctl-telegram` and
  `labs/mctl-telegram-preview` are untouched, and `@MCTL_AI_bot` is not used.
- **Resources:** one local process on operator hardware. No cluster resources.
- **Risks and mitigations:**
  - Account ban or restriction of the test number: use only a disposable number, and
    report any restriction as evidence.
  - Double-send: send-once state machine, pre-generated message ID, no automatic retry,
    manual reconcile.
  - Cross-routing: composite dedupe key, reply-target lookup, and a topic equality check
    at dispatch.
  - Data leakage into a public repository: redacting handler, chat hashing, the hygiene
    test, `$WABRIDGE_HOME` outside the repo, and an added `.gitignore` entry for `*.db`
    under `spikes/`.
  - Key exposure: 0700/0600 permissions, `unlink` deletes the device store, and the report
    states the plaintext-at-rest limitation.
  - Dependency risk: confined to the nested module and scanned by its own govulncheck job.
