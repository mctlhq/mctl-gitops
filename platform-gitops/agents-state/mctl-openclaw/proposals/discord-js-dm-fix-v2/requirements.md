# discord-js-dm-fix-v2

## Context

The `mctl-openclaw` service uses `discord.js` to operate a Discord bot channel
across all three tenants (`admins`, `labs`, `ovk`). A bug present in versions
of `discord.js` prior to v14.26.4 causes `MessageCreateAction` to silently drop
incoming Direct Messages (DMs) when the target `DMChannel` is not present in
the bot's internal channel cache. In that situation the channel object is never
fetched from the Discord API, the `messageCreate` event is never emitted, and
the message is discarded with no error and no log entry.

This silent failure affects all three tenants. For the `ovk` tenant it
constitutes an SLA breach: Discord users who DM the bot receive no reply and no
indication that their message was lost. `discord.js` v14.26.4 (released
2026-05-01, upstream PR #11495) resolves the issue as a patch-level fix with no
breaking API changes and no new runtime dependencies.

## User stories

- AS a Discord user sending a DM to the bot I WANT my message to be reliably
  received and processed SO THAT I receive a timely response and am not left
  waiting in silence.
- AS an operator monitoring message delivery across all tenants I WANT every
  incoming bot DM to produce an observable log event SO THAT I can verify
  message-delivery SLA compliance and detect silent failures immediately.

## Acceptance criteria (EARS)

- WHEN a Discord `MESSAGE_CREATE` gateway event arrives for a `DMChannel` that
  is not present in the discord.js channel cache THE SYSTEM SHALL fetch the
  channel from the Discord API and emit the `messageCreate` event to the skill
  runtime without discarding the message.
- WHEN a DM is received on any tenant THE SYSTEM SHALL produce a log entry
  confirming receipt so that delivery can be verified by operators.
- WHILE the upgraded discord.js is running on any tenant THE SYSTEM SHALL NOT
  discard an incoming DM without either processing it or recording an explicit
  error.
- WHEN discord.js v14.26.4 is deployed to the `labs` tenant and a DM is sent
  from a fresh session (ensuring the channel is uncached) THE SYSTEM SHALL
  receive and process that DM before the change is promoted to `admins` or
  `ovk`.
- IF discord.js is upgraded to v14.26.4 THEN THE SYSTEM SHALL continue to
  handle all `messageCreate` events for already-cached channels without any
  regression in behaviour.
- WHEN the bot process restarts and its channel cache is empty THE SYSTEM SHALL
  correctly receive the first DM sent after restart without requiring a manual
  warm-up step.

## Out of scope

- Upgrading discord.js to any version beyond v14.26.4 (any minor or major
  upgrade requires a separate proposal).
- Changes to Discord channel extension business logic (command handling,
  permission checks, response formatting).
- Modifications to the S3-sync canary or restore-state probe pipelines.
- Implementing application-level DM re-delivery, message queuing, or
  deduplication infrastructure.
- Addressing discord.js CVEs or issues unrelated to the DM receipt bug fixed in
  PR #11495.
