# Channels adapter (Option A, experimental/feature-flagged) for communication agent

## Context
Issue #305 asks for an experimental, feature-flagged Go stdio MCP server (`cmd/agent-channel`)
that bridges Anthropic's research-preview "Channels" transport to the same agent-facing JSON API
(`internal/agentapi`, mounted at `/api/agent/v1` behind `AGENT_ENABLED`) that the production
Option C worker (issue #298, which lives outside this repo) already consumes. The work was split
out of #298 on 2026-07-22 specifically so it does not sit on the MVP critical path: Channels is a
research-preview feature with an unresolved headless-launch problem (the
`--dangerously-load-development-channels` confirmation dialog cannot be answered non-interactively
without an `allowedChannelPlugins` org policy that requires a Team/Enterprise/managed-Console
claude.ai org mctlhq does not have — see mctl-claude-remote#32). The issue is explicit that this
must not become an always-on entrypoint dependency; its only sanctioned deliverable is a one-time,
manually-run, PTY-driven proof that the full event -> Claude -> reply-tool round trip works end to
end over the Channels transport.

This matters because `internal/agentapi/server.go`'s own package doc already anticipates this
adapter ("a headless Option-C worker today, an experimental Channels bridge later") — the JSON API
surface was deliberately built worker-agnostic. #305 is the first concrete consumer of that
worker-agnostic contract other than #298, and it doubles as a design check: if a second, structurally
different worker (stdio MCP server driven by Claude Code's Channels runtime instead of a headless
CLI loop) can reuse `/api/agent/v1` unchanged, the abstraction boundary is validated.

## User stories
- AS the mctl-telegram maintainer I WANT an experimental Channels-based agent worker gated behind
  its own feature flag SO THAT I can validate the Channels transport end-to-end without adding a
  standing production dependency on a research-preview Anthropic feature.
- AS the mctl-telegram maintainer I WANT `cmd/agent-channel` to expose the same agent tools as the
  Option C worker, proxying 1:1 onto `internal/agentapi` SO THAT the two workers stay behaviorally
  interchangeable and neither one accretes worker-specific policy logic that belongs server-side.
- AS the mctl-telegram maintainer I WANT a one-off PTY harness (not part of the adapter binary) that
  drives `claude --dangerously-load-development-channels server:agent-channel` and answers the local
  development confirmation SO THAT I can execute and document the single round-trip proof the issue
  requires without building permanent automation around an unstable confirmation dialog.
- AS a future contributor reading the README SO THAT I understand this adapter is experimental,
  off by default, and not part of the production Communication Agent path, with a pointer to the
  Channels spike write-up and the plan's Transport decision.

## Acceptance criteria (EARS)
- WHEN `cmd/agent-channel` starts THE SYSTEM SHALL read `AGENT_API_URL`, `AGENT_API_TOKEN`, and a
  poll-timeout setting from the environment and refuse to start with a clear error if
  `AGENT_API_URL` or `AGENT_API_TOKEN` is empty.
- WHEN `cmd/agent-channel` starts THE SYSTEM SHALL exit immediately with a non-zero status and a
  clear log message unless its feature flag (`AGENT_CHANNEL_ENABLED`) is set to true, so an
  accidental deploy cannot bring the adapter up.
- WHILE the feature flag is enabled and the adapter is running THE SYSTEM SHALL long-poll
  `GET {AGENT_API_URL}/api/agent/v1/events` using `AGENT_API_TOKEN` as the bearer credential, honoring
  the poll-timeout config value.
- WHEN a long-poll response contains one or more claimed jobs THE SYSTEM SHALL emit one
  `notifications/claude/channel` MCP notification per job, carrying a short wake-up text and the
  job's `event_id` in the notification's `meta`, and SHALL NOT embed the event body itself in the
  notification (the event body is fetched separately via `GET /api/agent/v1/event/{eventID}`, same
  as the JSON API's existing wake-up/fetch split).
- WHEN a long-poll response contains zero jobs (poll window elapsed) THE SYSTEM SHALL treat it as a
  normal empty tick and immediately re-poll, matching the JSON API's documented long-poll contract
  (`internal/agentapi/events.go`: an empty `jobs` array is not an error).
- WHEN the agent API returns a 5xx status to any adapter request THE SYSTEM SHALL apply exponential
  backoff with jitter before the next retry, and SHALL NOT tight-loop against a failing backend.
- WHEN the agent API returns a 4xx status (other than an expected empty-poll 200) THE SYSTEM SHALL
  log the failure with the status code and SHALL NOT retry that specific request as if it were a
  transient error.
- WHEN a Claude tool call arrives over the `claude/channel` capability THE SYSTEM SHALL proxy it 1:1
  onto the corresponding `/api/agent/v1` endpoint (policy, propose_reply, request_owner_approval,
  notify/summary, autopilot/pause, leads, recruiter profile, conversation context, job complete) and
  return the JSON API's response (or its error) back to Claude without adding independent policy
  logic in the adapter.
- IF `AGENT_API_TOKEN` would otherwise be logged (request errors, structured log fields, panics)
  THEN THE SYSTEM SHALL redact it, consistent with `internal/audit/redact.go`'s existing rule that
  secrets and session material are never logged.
- WHEN a unit test exercises the adapter against a fake agent API (`httptest.Server`) THE SYSTEM
  SHALL verify: (a) tool calls are proxied to the correct endpoint with the correct payload, (b) a
  claimed job on long-poll produces exactly one `notifications/claude/channel` emission with the
  right `event_id`, and (c) a sequence of 5xx responses triggers backoff before a successful retry.
- WHERE the one-off PTY harness is used to run the manual proof, THE SYSTEM SHALL log or otherwise
  durably record one successful event -> Claude -> reply-tool cycle as the acceptance artifact for
  #305; THE SYSTEM SHALL NOT treat the harness as part of `cmd/agent-channel`'s normal (non-manual)
  operation, and THE SYSTEM SHALL NOT wire the harness into CI, systemd units, Docker, or any other
  standing entrypoint.
- WHERE the README documents this feature, THE SYSTEM SHALL mark it explicitly as experimental and
  non-production, and SHALL link to `docs/claude-channels-spike.md` (mctl-claude-remote#32) and to
  the plan's (tranquil-sleeping-map) Transport decision.

## Out of scope
- Any change to `internal/agentapi` itself — the adapter is a pure client of the existing,
  worker-agnostic JSON API surface built for #298/#296; if a genuine gap is found, that is a
  follow-up issue against `agentapi`, not part of this proposal.
- Deploying `cmd/agent-channel` as a standing service (systemd unit, Docker image entry, Kubernetes
  deployment/cronjob, `docker-compose.yml` service). The issue is explicit that this is not on the
  production critical path.
- Solving the `--dangerously-load-development-channels` non-interactive confirmation problem in
  general (e.g. lobbying for or acquiring `allowedChannelPlugins` org policy access). The PTY harness
  works around it for one manual run only; it is not a durable fix.
- Any change to the production Option C worker (#298) or to how it is deployed.
- Multi-account / multi-tenant Channels support — the harness and adapter target a single account
  end-to-end proof, matching the issue's acceptance bar.
- Building automated CI coverage for the PTY harness itself (TUI timing makes this unreliable per
  the issue's own account of six defeated `expect`-driven attempts in the spike).

## Open questions
- Exact MCP capability/notification schema for `claude/channel` (field names beyond "short wake-up
  text" and `event_id` in `meta`) is not fully specified by Anthropic's public docs at the time of
  writing, since Channels is a research-preview feature. Interpretation used here: model the
  notification after the JSON API's own wake-up/fetch split (`jobEnvelope` in
  `internal/agentapi/events.go`) and keep the payload minimal, matching the issue's "short wake-up
  text" wording. Revisit if Anthropic's Channels protocol changes before the harness run.
- Whether `cmd/agent-channel` should get its own `go.mod`-level build tag or just live as an
  ordinary `cmd/` package gated at runtime by `AGENT_CHANNEL_ENABLED`. Interpretation used here:
  runtime flag only (consistent with how `AGENT_ENABLED` gates `/api/agent/v1` today), since a build
  tag would also block `go build ./...` / `go vet ./...` from covering it in CI, and the issue asks
  for unit tests via `go test`.
- Whether the PTY harness should live under `cmd/agent-channel-harness` (a second small binary) or
  as a script under `test/` or `docs/`. Interpretation used here: a separate `cmd/agent-channel-harness`
  Go binary excluded from Docker/production builds, since the repo's convention (`cmd/local`,
  `cmd/login`, `cmd/canary`) is small purpose-built Go binaries rather than shell scripts, and Go
  gives the PTY driver (`github.com/creack/pty` or similar) proper process control.
- The precise poll-timeout env var name/default. Interpretation used here: `AGENT_CHANNEL_POLL_TIMEOUT`
  (duration string, default matching `internal/agentapi`'s own `defaultLongPollTimeout` of 20s) to
  avoid colliding with `AGENT_JOB_VISIBILITY`/`AGENT_APPROVAL_TTL` naming already used in
  `internal/config/config.go`.
- Where the round-trip proof gets recorded (a markdown doc under `docs/`, a comment on issue #305, or
  both). Interpretation used here: a `docs/agent-channel-harness-run.md` artifact checked into the
  repo (dated, with the harness transcript/log excerpt), since the issue says "logged/documented"
  and a repo-tracked doc is more durable than an issue comment alone.
