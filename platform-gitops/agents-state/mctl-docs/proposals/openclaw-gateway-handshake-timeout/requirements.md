# OpenClaw Gateway WebSocket Handshake Timeout Configuration

## Context

Commit `bcc6a24` (mctl-openclaw, 2026-04-28) exposed a new configuration option,
`gateway.handshakeTimeoutMs`, that controls the pre-authentication WebSocket handshake
timeout for the OpenClaw gateway. The default is `15000` ms (15 seconds). The existing
environment variable `OPENCLAW_HANDSHAKE_TIMEOUT_MS` still takes precedence when set.

This knob was added specifically for loaded or low-powered hosts where startup warmup
causes local clients to time out during the handshake phase, even when the host is
otherwise healthy. Kubernetes nodes under the mctl platform can experience exactly this
condition during rolling restarts or on resource-constrained tenants.

OpenClaw's own configuration reference (`docs/gateway/configuration-reference.md`) and
the gateway configuration how-to (`docs/gateway/configuration.md`) were updated in the
same commit. `docs.mctl.ai/platform/openclaw.md` has no configuration reference section
and does not mention this option.

## User stories

- AS a **platform admin** experiencing WebSocket handshake timeouts on a freshly started
  OpenClaw pod I WANT to find the `gateway.handshakeTimeoutMs` knob documented on
  docs.mctl.ai SO THAT I can tune it without searching the upstream configuration reference.
- AS a **tenant owner** on a resource-constrained node I WANT to understand the default
  timeout and how to override it SO THAT I can prevent transient client disconnects during
  node warmup.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL list
  `gateway.handshakeTimeoutMs` in a configuration reference or troubleshooting section
  with its default value (15000 ms) and the precedence rule (`OPENCLAW_HANDSHAKE_TIMEOUT_MS`
  env var overrides the config value).
- IF a reader wants a JSON5 example of setting the timeout THEN THE SYSTEM SHALL provide
  one (matching the openclaw config schema).
- WHEN the section is displayed THE SYSTEM SHALL note when to prefer fixing startup/event-loop
  stalls over increasing the timeout (defensive guidance per upstream docs).
- WHILE version-status is unverified THE SYSTEM SHALL note the commit SHA.

## Out of scope

- A full gateway configuration reference (that is openclaw's own docs).
- Other `gateway.*` timeout options not related to handshake (e.g. `channelHealthCheckMinutes`).
- Helm chart templating for the config value (mctl-gitops is private; no commit signal).
