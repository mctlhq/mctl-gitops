# Upgrade discord.js to v14.26.4 (DM Reception Fix in Uncached Channels)

## Context

discord.js v14.26.4 was released with a targeted bug fix: bots no longer silently drop incoming direct messages when the destination `DMChannel` is not yet present in the internal channel cache. Before this fix, a DM sent to a bot immediately after startup or after a reconnect — before the `DMChannel` cache entry was hydrated — would be processed by `MessageCreateAction` without the channel object, causing the event to be swallowed silently.

OpenClaw uses `discord.js` as the underlying library for its Discord channel integration across all three tenants. The affected scenario (DM arriving on a cold-start or post-reconnect bot) is directly relevant to openclaw: restarts caused by rollouts, the restore-state readiness probe, or OOMKill on `labs` all produce the cold-start window during which DMs would be dropped under discord.js < 14.26.4.

The primary task under this proposal is **verification**: confirm whether the upstream openclaw 2026.4.29 bundle already depends on discord.js ≥ 14.26.4. If yes, the fix is delivered automatically by the planned upgrade and this proposal closes with a verification note. If not, a targeted patch is required.

## User stories

- AS a Discord user I WANT my direct messages to a bot to be received even immediately after the bot restarts SO THAT I am not silently ignored during the post-restart window.
- AS an operator I WANT to confirm the exact discord.js version bundled in openclaw 2026.4.29 SO THAT I know whether the DM fix is included before completing the upgrade verification checklist.
- AS a developer I WANT the openclaw Discord extension's dependency declaration to specify `discord.js >= 14.26.4` SO THAT future patch upgrades are applied automatically.

## Acceptance criteria (EARS)

- WHEN a DM is received on a bot while the `DMChannel` is not yet in cache THEN THE SYSTEM SHALL process and deliver the message without dropping it.
- WHEN the openclaw 2026.4.29 upstream `package.json` is inspected THEN THE SYSTEM SHALL confirm that the declared `discord.js` version satisfies `>= 14.26.4`; if it does not, a patch PR SHALL be opened.
- WHILE any tenant is running discord.js < 14.26.4 THEN THE SYSTEM SHALL document this as an open known issue in the tenant's runbook.
- IF a patch PR to the openclaw fork is required THEN THE SYSTEM SHALL apply the patch to the Discord extension only, with no changes to other channels or core, and SHALL pass all existing Discord integration tests.

## Out of scope

- New Discord features or API changes introduced in any discord.js version beyond the DM fix.
- Changes to Slack, WhatsApp, Telegram, or any other channel.
- Memory or performance profiling of discord.js v14.26.4 (the update contains no new runtime dependencies and is not expected to increase memory usage in `labs`).
