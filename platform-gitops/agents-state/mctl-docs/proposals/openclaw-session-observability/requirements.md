# OpenClaw Session Management and Observability — Compaction, Idle Timeouts, Fallback Model, and `/metrics`

> version-status: unverified, see commit SHAs 17a4743, 3e792eb (mctl-gitops), 4c46cf1, b23903e (mctl-openclaw 2026.5.14-beta.1 confirmed via mctl-gitops 4272f71 2026-05-13)

## Context

Between 2026-05-10 and 2026-05-13, four commits across the `mctl-openclaw` and
`mctl-gitops` repositories shipped features that change how OpenClaw manages
long-running sessions and how operators can monitor gateway activity. Context
compaction was added (commit `17a4743`): when a Telegram session's context grows
large, OpenClaw now keeps a rolling window of recent tokens (configurable via
`keepRecentTokens`) and discards older history to control latency and cost.
The same commit introduced session idle timeouts: Telegram sessions left inactive
beyond a configurable threshold are expired automatically. Commit `3e792eb`
changed the fallback model for the `ovk` and `labs` tenants from the previous
fallback to Claude Haiku — affecting the quality and cost profile of responses
when the primary model is unavailable or rate-limited. Commits `4c46cf1` and
`b23903e` added a Prometheus-compatible `/metrics` endpoint to the OpenClaw
gateway with `openclaw_llm_*` counters partitioned by a `provider` label
(`codex` and `anthropic`).

The current `docs/platform/openclaw.md` page documents the OpenClaw gateway and
its channels but covers none of these features. An operator wanting to set up
custom Grafana dashboards or Alertmanager rules against the `/metrics` endpoint
has no reference. A tenant owner wondering why their Telegram sessions end
unexpectedly has no documentation explaining idle timeouts or compaction. The
fallback model change affects cost planning for ovk and labs tenants and should
be documented to set expectations.

## User stories

- AS a platform operator managing ovk or labs tenants I WANT to know that OpenClaw
  now exposes a Prometheus `/metrics` endpoint with `openclaw_llm_*` counters and
  a `provider` label SO THAT I can add it to my Prometheus scrape config and build
  dashboards or alerts.
- AS a platform operator I WANT to know the counter names and label values for the
  `openclaw_llm_*` metric family SO THAT I can write correct PromQL queries
  without guessing.
- AS a Telegram user of the OpenClaw gateway I WANT to know that long-idle sessions
  are expired automatically SO THAT I understand why my session context was reset
  and can plan accordingly.
- AS a tenant owner I WANT to know that context compaction is active and what the
  `keepRecentTokens` parameter controls SO THAT I understand the cost and latency
  trade-off for long conversations.
- AS an ovk or labs tenant owner I WANT to know that the fallback model is now
  Claude Haiku SO THAT I can plan for the quality and cost profile of degraded
  responses and not be surprised by a change in response quality.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL describe the
  Prometheus `/metrics` endpoint, its URL pattern, and the `openclaw_llm_*`
  counter family with the `provider` label and its values (`codex`, `anthropic`).
- IF a reader wants to scrape the `/metrics` endpoint THEN THE SYSTEM SHALL
  provide a Prometheus scrape config example.
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL describe the
  session idle timeout behaviour for Telegram sessions and state that idle sessions
  are expired automatically.
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL describe
  context compaction and the role of the `keepRecentTokens` configuration
  parameter.
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL state that
  the fallback model for `ovk` and `labs` tenants is Claude Haiku.
- WHILE the OpenClaw version in production is tagged as beta (2026.5.14-beta.1)
  THE SYSTEM SHALL note this status where relevant so readers understand these
  features are not yet in a stable release.

## Out of scope

- Documentation of the OpenClaw `/v1/chat/completions` HTTP endpoint for labs —
  that feature is labs-only and tagged beta; it should be a separate proposal
  once promoted beyond beta.
- Documenting the internal Grafana dashboards provisioned in mctl-gitops — those
  are internal observability, not user-facing docs.
- Documenting the Bybit trading skill added for labs — out of scope for platform
  docs.
- Configuration guide for setting `keepRecentTokens` per tenant — values are
  operator-controlled via mctl-gitops; the doc should name the parameter and its
  purpose without prescribing specific values.
- Video tutorial or localisation.
