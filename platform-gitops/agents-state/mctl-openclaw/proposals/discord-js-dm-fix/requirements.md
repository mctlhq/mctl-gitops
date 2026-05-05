# Bump discord.js to v14.26.4 to restore DM receipt in uncached DMChannels

## Context

The mctl-openclaw Discord channel extension depends on `discord.js`. The version currently in use (v14.26.3 or earlier, per `context/architecture.md` dependency tracking) contains a correctness bug in `MessageCreateAction`: when a `MESSAGE_CREATE` gateway event arrives for a `DMChannel` that is not present in the internal channel cache, the event is silently discarded instead of being delivered. This means incoming Discord DMs sent during the cold-start window — or after a reconnection event — are permanently lost with no error, no log entry, and no retry.

discord.js v14.26.4 resolves this in a single targeted fix (upstream PR #11495): the handler now fetches or constructs the missing `DMChannel` object before emitting the `messageCreate` event. The fix is a patch release with no breaking API changes and no new runtime dependencies. Because mctl-openclaw pods restart on every image rollout (and the `restore-state` readiness probe fires before the pod is declared ready), every deployment cycle creates an exposure window. The fix is low-effort (effort score: 1) and carries no memory risk.

## User stories

- AS an `ovk` end user I WANT Discord DMs I send immediately after an openclaw pod restart to be received SO THAT my messages are not silently dropped.
- AS a platform operator I WANT Discord DM delivery to be reliable across pod restarts for all three tenants SO THAT correctness regressions in the Discord channel are eliminated.
- AS a platform operator I WANT the fix delivered in the standard labs → admins → ovk rollout order SO THAT any unexpected regression is caught before reaching the production tenant.

## Acceptance criteria (EARS)

- WHEN a Discord `MESSAGE_CREATE` gateway event arrives for a `DMChannel` that is not yet in the bot's internal channel cache THE SYSTEM SHALL deliver the `messageCreate` event to the openclaw skill runtime without discarding it.
- WHEN a Discord DM is sent to the bot during the post-restart cold-start window THE SYSTEM SHALL receive and process the DM within the normal message-handling latency bounds.
- WHEN discord.js is upgraded to v14.26.4 THE SYSTEM SHALL continue to handle `messageCreate` events for cached channels without any change in behaviour.
- WHILE the upgraded discord.js is running THE SYSTEM SHALL not introduce any increase in steady-state pod RSS memory compared to the pre-upgrade baseline.
- IF the discord.js version in the installed dependency tree is confirmed to be v14.26.4 or higher via `npm ls discord.js` THE SYSTEM SHALL be considered compliant with this requirement.
- IF the upgrade to openclaw v2026.5.3 (tracked in `upgrade-to-2026-5-3`) already bundles discord.js >= v14.26.4 THEN THE SYSTEM SHALL treat this proposal as satisfied by the upstream upgrade and close it with a verification note.
- WHEN the fix is deployed to `labs` and the 24-hour soak completes without regression THE SYSTEM SHALL allow promotion to `admins`.
- WHEN the fix is deployed to `admins` and verification completes without regression THE SYSTEM SHALL allow promotion to `ovk`.

## Out of scope

- Changes to any Discord channel extension logic beyond the discord.js version bump.
- Upgrading discord.js beyond v14.26.4 (any minor or major version bump requires a separate proposal).
- Implementing application-level DM retry or message deduplication logic.
- Changes to the 3-layer skills architecture or YAML skill content.
- Changes to the s3-sync canary or restore-state probe configuration.
- Addressing any discord.js CVEs unrelated to the DM receipt bug.
