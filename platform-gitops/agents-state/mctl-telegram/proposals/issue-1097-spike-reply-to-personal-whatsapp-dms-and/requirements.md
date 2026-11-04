# Spike: reply to personal WhatsApp DMs and groups from a private Telegram forum

## Context

Issue mctlhq/mctl-telegram#1097 asks one question: can the owner reliably use Telegram to
receive and reply to existing personal WhatsApp conversations, well enough to justify an
opt-in pilot? The answer must be a runnable, isolated Go proof of concept, an operator
runbook and an evidence-backed go/no-go report. The proof of concept links one disposable
WhatsApp account as a whatsmeow linked device. It mirrors new plain text from one consented
test DM and one test group into their own topics of an owner-only Telegram test forum. Only
an explicit Telegram reply from the owner to a mirrored message may send as that WhatsApp
account. This spike ships nothing to production. It never touches the deployed
`labs/mctl-telegram` service, its database or its login bot.

This matters because sending as someone's personal account is the most damaging action
this repository's products can take. ADR 0002 (`docs/adr/0002-send-gate.md`) treats an
unwanted send as unrecoverable. An unofficial WhatsApp client also brings account-ban and
maintenance risks that a pilot decision has to weigh. So the spike's main deliverable is
evidence: no double-send, no cross-routing, no echo, rejection of unauthorized replies, and
a clear way to reconcile sends whose outcome is unknown. That evidence carries more weight
than the feature itself.

## User stories

- AS the account owner I WANT new plain-text messages from an allowlisted WhatsApp chat to
  appear, with the sender named, in that chat's own topic of my private Telegram forum SO
  THAT I can follow the conversation without opening WhatsApp.
- AS the account owner I WANT my explicit Telegram reply to a mirrored message to be sent to
  exactly that WhatsApp chat SO THAT I can answer from Telegram.
- AS the account owner I WANT any send whose outcome is unknown to be shown to me rather
  than retried SO THAT a recipient never gets the same message twice.
- AS an operator I WANT a runbook, offline fixtures and a separate live checklist SO THAT
  I can repeat the experiment and judge the go/no-go report.
- AS a reviewer I WANT logs and committed evidence free of QR payloads, phone numbers, chat
  content and credentials SO THAT the public repository never leaks private data.

## Acceptance criteria (EARS)

Inbound (WhatsApp to Telegram)
- WHEN a new plain-text message arrives in a WhatsApp chat that is mapped and allowlisted
  THE SYSTEM SHALL post it once, with sender attribution, into that chat's mapped topic of
  the configured forum.
- IF a WhatsApp message arrives from a chat that is not mapped THEN THE SYSTEM SHALL drop it
  without posting anything, and only increment an outcome counter.
- IF a WhatsApp message is not plain text (media, sticker, reaction, poll, edit, revoke)
  THEN THE SYSTEM SHALL not mirror its content. It SHALL post at most a fixed placeholder
  that the message type is unsupported.
- WHEN the same WhatsApp event is delivered more than once (replay, reconnect, restart)
  THE SYSTEM SHALL mirror it at most once. Deduplication uses the composite key
  (chat JID, sender JID, message ID), so equal message IDs in different chats never collide.
- WHEN a WhatsApp event is the bridge's own outbound message, identified by a message ID
  recorded in the outbox before sending, THE SYSTEM SHALL not mirror it as a new message.
- WHEN the owner sends a message natively from the phone or another linked device THE
  SYSTEM SHALL never dispatch it back to WhatsApp. It SHALL mirror it only as an attributed
  "you (other device)" entry, so the topic shows the whole conversation.

Outbound (Telegram to WhatsApp)
- WHEN the authorized owner sends a Telegram message that explicitly replies to a mirrored
  message, in the topic mapped to that message's WhatsApp chat, THE SYSTEM SHALL send its
  plain text once to that WhatsApp chat as the linked account.
- IF a Telegram message is from anyone other than the configured owner's user ID THEN THE
  SYSTEM SHALL not send, and SHALL record a `rejected_not_owner` outcome.
- IF a Telegram message is not a reply, or replies to a message the bridge did not mirror,
  THEN THE SYSTEM SHALL not send (`rejected_not_reply` / `rejected_unknown_target`).
- IF a reply is posted in a topic other than the one mapped to the replied-to message's
  chat, or in a chat other than the configured forum, THEN THE SYSTEM SHALL not send
  (`rejected_wrong_topic` / `rejected_wrong_chat`).
- IF the replied-to message's WhatsApp chat is no longer mapped or allowlisted, or the
  device is unlinked, THEN THE SYSTEM SHALL not send (`rejected_unmapped` /
  `rejected_unlinked`).
- WHILE a send is being dispatched THE SYSTEM SHALL recheck owner, forum, topic, mapping,
  allowlist and link state inside the same transaction that moves the outbox row to
  `sending`, immediately before the network call.
- WHEN the same Telegram update is delivered more than once THE SYSTEM SHALL create at most
  one outbox row for it. The row is keyed on the update ID and on (forum chat ID,
  Telegram message ID).
- THE SYSTEM SHALL commit the outbox row in state `sending`, with a WhatsApp message ID
  generated beforehand, before it calls WhatsApp.
- IF the send call times out, the connection drops mid-send, or the process restarts while
  a row is `sending` THEN THE SYSTEM SHALL move the row to `uncertain` and SHALL NOT retry
  it automatically.
- WHEN a server ack or delivery receipt for an `uncertain` row's WhatsApp message ID is
  observed THE SYSTEM SHALL move the row to `sent`. Otherwise it SHALL list the row through
  the `reconcile` command and post a fixed "delivery uncertain" notice in the topic.
- WHEN the operator resolves an uncertain row (`reconcile --mark sent|failed`) THE SYSTEM
  SHALL record the resolution. Even then it SHALL never resend without a new explicit
  owner reply.

Lifecycle and data protection
- WHEN the operator runs `unlink`, or WhatsApp reports the device logged out, THE SYSTEM
  SHALL stop forwarding in both directions and delete the local WhatsApp device keys.
- WHEN the operator runs `unmap` for a chat THE SYSTEM SHALL stop mirroring that chat and
  reject further replies into its topic.
- THE SYSTEM SHALL keep the WhatsApp device store and the bridge database in a directory
  outside the repository, with mode 0700 and files 0600. Pending outbound text SHALL be
  encrypted at rest and purged when the row reaches a terminal state.
- THE SYSTEM SHALL never write QR payloads, phone numbers, JIDs, message text, bot tokens
  or session keys to logs or committed evidence. Chats are logged only as a keyed hash.
- THE SYSTEM SHALL render the pairing QR only on an interactive terminal, and only while a
  human runs `pair`.
- THE SYSTEM SHALL run ingestion as a standalone process, without any MCP client or
  assistant session.

Evidence
- THE SYSTEM SHALL ship offline tests that use fake WhatsApp and Telegram transports and
  synthetic identifiers, and that cover every criterion above.
- THE SYSTEM SHALL ship a separately marked live checklist. Every live item that has not
  been run with a human-paired test account SHALL be recorded as `pending`, never as passed.
- THE SYSTEM SHALL ship a go/no-go report covering unofficial-client compatibility,
  account-restriction risk, licence and ongoing maintenance, and SHALL tie each claim to a
  test, a live check, or an explicit "not measured here".

## Out of scope

- Any production rollout: no change to `cmd/server`, `internal/*` runtime behaviour, the
  Docker image, the `labs/mctl-telegram` deployment or `@MCTL_AI_bot`.
- Media, reactions, edits, deletes, read receipts sent to WhatsApp, history import or
  backfill.
- Viber, the WhatsApp Business / Cloud API, Matrix or mautrix deployment.
- New production services, multi-tenant or multi-account support.
- Autonomous or AI-generated replies. MCP integration is optional and not built here.
- Pairing a real account in CI or by an agent. Only a human pairs.

## Open questions

- Native phone sends: the issue says "no echo" but does not say whether they should be
  shown. This proposal mirrors them as "you (other device)" entries and never dispatches
  them. Hiding them instead is a one-line change.
- Owner-only forum: interpreted as a supergroup with topics enabled whose only members are
  the owner and the dedicated test bot. The bridge checks this at startup and at every
  dispatch, and refuses to run otherwise.
- At-rest protection of whatsmeow's own device store: whatsmeow's SQL store keeps identity
  keys in plaintext columns. The spike relies on file permissions and a dedicated
  directory, and the report must state this. Whether a pilot needs encryption at rest
  (an encrypted volume or a custom store) is for the report to answer.
- Hardware and test accounts: one disposable WhatsApp number, one second device for the
  consented DM partner and test group, and one Telegram test bot. Who provides these is not
  stated. Until they exist, every live check stays `pending`.
- Whether CI should run the nested spike module. This proposal adds a path-filtered
  workflow. Leaving it out keeps the spike entirely outside CI.
