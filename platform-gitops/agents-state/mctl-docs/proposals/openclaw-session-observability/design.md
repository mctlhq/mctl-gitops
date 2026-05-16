# Design: openclaw-session-observability

> version-status: unverified, see commit SHAs below

## Source commits

- `mctl-gitops:17a4743` — feat(openclaw): add compaction + telegram session idle limits
- `mctl-gitops:3e792eb` — feat(openclaw): bump ovk/labs to 2026.5.2-mctl.1, switch fallback to haiku
- `mctl-openclaw:4c46cf1` — feat(observability): /metrics endpoint (part 1)
- `mctl-openclaw:b23903e` — feat(observability): per-provider LLM usage metrics

Key diff evidence from the inbox analysis:
- `src/gateway/server-http.ts` exposes a `/metrics` route returning
  `formatLLMMetricsPrometheus()`.
- `src/logging/llm-metrics.ts` (+95 lines) defines `openclaw_llm_*` counters
  with a `provider` label covering `anthropic` and `codex` (OpenAI) transports.
- `mctl-gitops:17a4743` adds `keepRecentTokens` compaction config and idle
  timeout values to the OpenClaw deployment.
- `mctl-gitops:3e792eb` switches the fallback model for `ovk` and `labs` to
  Claude Haiku.

## Current state of documentation

Existing page: `docs/platform/openclaw.md` (OpenClaw Integration)

The page documents the OpenClaw gateway and its supported channels (Telegram,
WhatsApp, etc.), routing, and active-hours scheduling. Based on the inbox
analysis, it does not currently cover:

1. **Session management** — no mention of context compaction, `keepRecentTokens`,
   or Telegram session idle timeouts.
2. **Fallback model** — no mention of the per-tenant fallback model or that it is
   now Claude Haiku for `ovk` and `labs`.
3. **Observability** — no mention of the `/metrics` endpoint or the
   `openclaw_llm_*` Prometheus counter family.

## Proposed solution

Update `docs/platform/openclaw.md` with three new sections appended after the
existing content (or inserted at logical breakpoints within the existing structure):

### New section 1: Session management

Title: `## Session management`

Cover:
- Context compaction: what it is (rolling window of recent tokens to control
  context size), what `keepRecentTokens` controls, and when compaction fires.
- Telegram session idle timeouts: sessions inactive beyond the idle threshold are
  expired; users will start a fresh session on next message.
- Note that both values are configured per-tenant via mctl-gitops; point operators
  to the GitOps guide for how to override them.

### New section 2: Fallback model

Title: `## Fallback model`

Cover:
- When the primary model for a tenant is unavailable or rate-limited, OpenClaw
  routes requests to the configured fallback model.
- Current fallback for `ovk` and `labs`: Claude Haiku (as of mctl-gitops
  `3e792eb`, 2026-05-10).
- Note: the fallback model may differ per tenant and is configured in mctl-gitops.
  This section documents the current shipped state; operators can override via
  their tenant config.

### New section 3: Observability — `/metrics` endpoint

Title: `## Observability`

Cover:
- The `/metrics` endpoint exposed by OpenClaw (Prometheus text format).
- The `openclaw_llm_*` counter family.
- The `provider` label and its current values: `anthropic`, `codex`.
- A Prometheus scrape config example.
- A PromQL example for a per-provider token usage rate query.

<TODO: confirm the full list of `openclaw_llm_*` counter names (e.g.
`openclaw_llm_tokens_total`, `openclaw_llm_requests_total`) and any additional
labels with the author of mctl-openclaw:b23903e — the inbox analysis names the
`provider` label and describes `llm-metrics.ts` but does not enumerate all
counter names.>

<TODO: confirm the exact URL format for the `/metrics` endpoint per tenant —
is it `https://<tenant>-openclaw.mctl.ai/metrics` or a different path pattern?
Confirm with author of mctl-openclaw:4c46cf1.>

### No structural changes

All additions are to an existing page. No new pages, no new sidebar entries, no
nav changes.

## Alternatives

**Option A (adopted): update `docs/platform/openclaw.md` with three new sections.**
Keeps all OpenClaw operational information in one place. Consistent with the
existing page structure (which already covers channels, routing, scheduling as
separate sections).

**Option B: create a new `docs/platform/openclaw-observability.md` page.**
A dedicated observability reference page for OpenClaw. Dropped — the feature
surface is not large enough to warrant a standalone page today. If more
observability features are added (tracing, log aggregation, SLO dashboards), this
can be split out.

**Option C: document `/metrics` under `docs/guides/` as a how-to.**
Dropped — the `/metrics` endpoint is a property of the OpenClaw service; it
belongs in the platform reference page, not a guides how-to.

## Impact

- VitePress sidebar / nav config: no change required (page already in sidebar).
- Mermaid diagrams: a simple flow diagram showing the compaction / idle-timeout
  lifecycle for a Telegram session would be helpful; included in
  `proposed-content.md` as optional.
- Documentation versioning: applies to mctl-openclaw 2026.5.14-beta.1 and
  mctl-gitops changes as of 2026-05-10. The page should carry a beta callout
  since the prod version is tagged beta.
