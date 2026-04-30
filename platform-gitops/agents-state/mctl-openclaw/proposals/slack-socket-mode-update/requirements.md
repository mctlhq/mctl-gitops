# Update @slack/socket-mode to 2.0.7 for reconnection reliability

## Context
`@slack/socket-mode@2.0.7` was released on 2026-04-30. The release introduces earlier termination of stale closing WebSocket connections when a normal close handshake fails. Without this fix, the Slack channel on all three tenants (`labs`, `admins`, `ovk`) accumulates repeated warning log entries and experiences elevated reconnection latency when a WebSocket close handshake stalls. These warnings have been observed in the logs of all three tenants.

This is a patch-level bump with no API changes. It does not increase memory usage and poses no risk to the `labs` tenant's memory limit. The update can be applied rapidly across all three tenants following the standard ADR-0001 rollout order.

## User stories
- AS a platform operator I WANT the stale-WebSocket warning noise eliminated from Slack channel logs SO THAT real alerts are not buried by repeated non-actionable log entries.
- AS the `ovk` customer I WANT Slack channel reconnections to complete faster after a stalled close handshake SO THAT Slack message delivery is not interrupted by extended reconnection delays.
- AS a platform operator I WANT the update validated on `labs` before reaching `ovk` SO THAT any unexpected regression is caught before it affects the production tenant.

## Acceptance criteria (EARS)
- WHEN `@slack/socket-mode` is updated to 2.0.7 and deployed to `labs` THE SYSTEM SHALL no longer emit the repeated stale-closing-connection warning log entries on the Slack channel.
- WHEN a Slack WebSocket close handshake stalls THE SYSTEM SHALL terminate the stale connection and initiate a reconnect within the shorter timeout introduced by 2.0.7, rather than waiting for the previous longer timeout.
- WHILE the rollout is in progress on any tenant THE SYSTEM SHALL maintain the s3-sync canary and restore-state probe guards per ADR-0002.
- WHEN the `labs` rollout is confirmed healthy THE SYSTEM SHALL allow promotion to `admins`; WHEN `admins` is confirmed healthy THE SYSTEM SHALL allow promotion to `ovk`.
- IF the update introduces any unexpected increase in memory usage on `labs` THEN THE SYSTEM SHALL block promotion to `admins` and `ovk` until the cause is understood (though no memory increase is expected for this patch).

## Out of scope
- Upgrading `@slack/socket-mode` beyond 2.0.7.
- Changes to the Slack channel configuration, skill routing, or Slack API scopes.
- Modifications to other channel adapters (Discord, WhatsApp, etc.).
- Changes to the s3-sync canary interval or restore-state probe timeout.
- Resolving any pre-existing Slack connectivity issues unrelated to stale-connection handling.
