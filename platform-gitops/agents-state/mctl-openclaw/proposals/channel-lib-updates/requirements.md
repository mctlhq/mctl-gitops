# Channel Library Updates: discord.js 14.26.4 and @slack/socket-mode 2.0.7

## Context

Two channel client libraries used by mctl-openclaw have received point-release updates that fix silent correctness regressions:

1. **discord.js 14.26.4** (released 2026-05-01): Restores DM delivery in DMChannels that are not currently cached in memory (PR #11495). Without this fix, direct messages sent to the bot while the channel is uncached are silently dropped — a correctness issue invisible to end users but causing message loss on `ovk`.

2. **@slack/socket-mode 2.0.7** (released 2025-04-30): Force-terminates WebSocket connections when Slack does not respond to a close frame. Without this fix, stale zombie connections accumulate, causing "pong wasn't received" warnings and reconnect delays that can stall Slack message delivery.

Both are point releases with no breaking API changes and no expected memory footprint increase, making them safe to apply to `labs` first.

## User stories

- AS a Discord channel user I WANT DMs to the bot to be reliably delivered even when the DMChannel is not cached SO THAT I do not experience silent message loss.
- AS a Slack channel user I WANT the bot to reconnect quickly after a Slack-side network interruption SO THAT message delivery resumes within seconds, not minutes.
- AS a platform operator I WANT both library bumps to be validated in `labs` before rolling to `ovk` SO THAT any unexpected regression is caught early.

## Acceptance criteria (EARS)

- WHEN a Discord user sends a DM to the bot while the DMChannel is not in the in-memory cache THE SYSTEM SHALL receive and process the message without error.
- WHEN Slack does not respond to a WebSocket close frame within the socket-mode timeout THE SYSTEM SHALL force-terminate the connection and initiate a clean reconnect within 10 seconds.
- WHILE the library upgrades are deployed to `labs` THE SYSTEM SHALL show no increase in pod memory usage beyond 20 MB of the pre-upgrade baseline.
- WHEN the upgrades are applied THE SYSTEM SHALL not change any existing skill routing, allowlist, pairing, or onboarding flow.
- IF a regression is detected in `labs` after the upgrade THEN THE SYSTEM SHALL roll back to the previous library version and block promotion to `admins` and `ovk`.
- WHEN both upgrades are applied across all three tenants THE SYSTEM SHALL report the updated library versions in the next dependency audit output.

## Out of scope

- Upgrading discord.js to a major version (v15+) — breaking API changes require separate planning.
- Upgrading other `@slack/*` packages beyond `socket-mode`.
- Baileys v7 major-version upgrade (release candidate; deferred until stable release).
- Any changes to the Discord or Slack extension business logic.
