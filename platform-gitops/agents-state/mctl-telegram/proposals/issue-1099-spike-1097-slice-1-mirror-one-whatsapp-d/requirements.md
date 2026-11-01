# Spike #1097, slice 1: mirror one WhatsApp DM into one private Telegram forum topic

## Context
Issue #1099 is the first vertical slice of spike #1097 (WhatsApp-to-Telegram-forum bridging). An
earlier implementer attempt stopped without commits because the scope was too large, so this
slice is deliberately narrow: an inbound-only, operator-run command in its own Go module under
`spikes/whatsapp-forum/`. An operator pairs a disposable personal WhatsApp account locally
with `go.mau.fi/whatsmeow`. New plain-text messages from exactly one configured, consented DM are
posted by a dedicated Telegram bot into one topic of a private test forum that only the owner and
the bot belong to.

This matters because it tests the riskiest assumptions of #1097 (whatsmeow pairing, event
filtering, verifying that the destination is private, keeping secrets out of logs) without touching the production
`mctl-telegram` module, its dependencies, its Docker image or its CI. Group routing and owner
replies stay in #1097.

## User stories
- AS the spike operator I WANT to pair a disposable WhatsApp account locally by QR code SO THAT I can test
  whatsmeow without any server or shared infrastructure.
- AS the spike operator I WANT plain-text messages from one consented DM to appear in one private
  Telegram forum topic SO THAT I can judge whether the mirroring model works end to end.
- AS the DM counterpart who gave consent I WANT only my DM, and only new text, to be mirrored SO THAT none of my other
  conversations, history or media leave the device.
- AS a maintainer I WANT the spike isolated in its own module SO THAT production builds,
  `go.mod`/`go.sum` and CI are unchanged.

## Acceptance criteria (EARS)
- WHEN the operator runs `go run .` (the single command) in `spikes/whatsapp-forum/` with valid
  configuration and no existing session THE SYSTEM SHALL show a WhatsApp pairing QR code on the
  operator's terminal only, and store the resulting device session in the configured session
  directory.
- IF any required setting (`WAF_SESSION_DIR`, `WAF_WA_PEER`, `WAF_PEER_CONSENT`,
  `WAF_TG_BOT_TOKEN`, `WAF_TG_CHAT_ID`, `WAF_TG_TOPIC_ID`, `WAF_TG_OWNER_ID`) is missing or
  malformed THEN THE SYSTEM SHALL exit non-zero before connecting to WhatsApp or Telegram, naming
  the bad setting but never printing its value.
- IF `WAF_PEER_CONSENT` is not exactly `yes` THEN THE SYSTEM SHALL refuse to start.
- IF the session directory is relative, lies inside the repository checkout, or is
  readable or writable by group or others THEN THE SYSTEM SHALL refuse to start. Group or other
  access means any permission bit in mode `0077`.
- WHEN the system creates the session directory or session database THE SYSTEM SHALL create them
  with mode `0700` and `0600` respectively.
- WHEN the system starts, and again before each forward, THE SYSTEM SHALL verify through the Telegram Bot API that
  the destination chat is a forum supergroup, has exactly 2 members, that `WAF_TG_OWNER_ID` is
  its creator, and that the bot itself is a member. It SHALL refuse to start, or drop
  the message, if any check fails.
- WHEN a new incoming WhatsApp message arrives whose chat is the configured DM, which is not sent
  by the paired account, whose timestamp is not older than the process start time, and whose content is plain text
  (`Conversation` or `ExtendedTextMessage.Text`) THE SYSTEM SHALL post that text, without a parse mode,
  to `WAF_TG_TOPIC_ID` in `WAF_TG_CHAT_ID` using the bot. It SHALL send each WhatsApp message id at most once per process.
- IF an incoming message is from any other chat, a group, a broadcast or status chat, a newsletter,
  is from the paired account itself, is part of history sync, has a timestamp from before the process started,
  or carries media, a reaction, a protocol, edit or poll payload, or otherwise has no plain text, THEN
  THE SYSTEM SHALL ignore it and not contact Telegram.
- WHILE running THE SYSTEM SHALL never call any whatsmeow method that sends content, presence,
  read receipts or chat state to WhatsApp.
- WHILE running THE SYSTEM SHALL not write message text, WhatsApp JIDs or phone numbers, the
  bot token, QR or pairing codes, or session contents to logs. Logs carry only decision reasons,
  counts and error categories.
- IF the Telegram send fails THEN THE SYSTEM SHALL log the failure category, such as the HTTP
  status or Bot API `error_code`, and drop the message. There is no outbox and no retry queue.
- WHEN `go test ./...` is run in `spikes/whatsapp-forum/` THE SYSTEM SHALL run offline tests with
  synthetic messages and a fake Bot API, covering routing, configuration refusal and destination
  verification, with no network access and no WhatsApp session.
- WHILE the spike exists THE SYSTEM SHALL leave the root module unchanged: root `go.mod`, `go.sum`,
  `Dockerfile`, `.dockerignore` and `.github/workflows/*`, and root `go build ./...` and
  `go test ./...` SHALL not compile the spike.

## Out of scope
- Any message sent to WhatsApp (replies, read receipts we initiate, presence, reactions).
- Group chats, multiple DMs, multiple topics, topic auto-creation.
- History sync or backfill, media, stickers, voice, edits, deletions, reactions.
- Outbox, persistence of forwarded messages, retries.
- MCP tools, integration with `internal/` packages, deployment, Helm or gitops changes, new CI
  workflows.
- Owner replies from Telegram back to WhatsApp, which stays in #1097.
- A verified live end-to-end result. The manual checklist ships marked PENDING until a human runs it.

## Open questions
- The DM identifier: WhatsApp increasingly addresses DMs by LID (`<n>@lid`) and not by phone JID
  (`<n>@s.whatsapp.net`). Assumption: `WAF_WA_PEER` accepts either form, and routing matches
  `Info.Chat` or `Info.SenderAlt`/`Info.RecipientAlt` against it after normalising to the non-AD
  user JID. Live behaviour must be confirmed by the manual checklist.
- How consent is recorded. Assumption: an explicit `WAF_PEER_CONSENT=yes` setting plus a
  checklist item stating that the counterpart agreed in writing. No consent artefact is stored.
- whatsmeow automatically sends protocol-level delivery receipts, and may send retry receipts, for
  received messages. Assumption: this counts as transport acknowledgement, not "sending to
  WhatsApp", because the spike never initiates content, read receipts or presence. The reviewer
  should confirm.
- "New" messages: assumption is that messages with `Info.Timestamp` before process start are
  history, including offline messages delivered on reconnect, and are ignored.
- Whether the static "never send" guard test, which greps the spike source, is enough, or whether the
  reviewer wants a narrower wrapper interface. Assumption: both are used. Routing only depends on
  a small interface with no send methods, and a guard test backs it up.
