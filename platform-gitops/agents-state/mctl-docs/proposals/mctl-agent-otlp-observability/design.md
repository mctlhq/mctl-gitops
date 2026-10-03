# Design: mctl-agent-otlp-observability

## Source commits
- mctl-agent:0c9e8f2 — feat(telemetry): trace ticket processing over OTLP and count LLM tokens

## Current state of documentation
- `docs/platform/components.md` — mctl-agent block (confirmed via live
  fetch) lists capabilities (AlertManager subscription, ticket/incident
  state, Claude-based analysis, skill execution, OpenClaw dispatch,
  `mctl-gitops` PRs, Telegram notifications, full incident lifecycle) but
  has no mention of tracing or metrics at all.
- `docs/reference/troubleshooting.md` — confirmed via live fetch: has
  Authentication / MCP Connection / Deployment / Databases / Domains /
  Preview Environments / Self-Healing Agent / Getting Help sections. No
  "Observability" or "Metrics" section exists anywhere on the page.
- `docs/reference/telemetry-attributes.md` — **already exists** (confirmed
  via live fetch), evidently written to close `mctlhq/mctl-docs#120` ahead
  of any producer shipping. It already reserves every attribute name
  `0c9e8f2` emits, in its "Span attributes — incident agent" table
  (`mctl.ticket.id`, `mctl.ticket.type`, `mctl.skill.name`,
  `mctl.diagnosis.confidence`, `mctl.diagnosis.fixable`,
  `mctl.ticket.outcome`) and its `gen_ai.*` table, all still marked
  `reserved`. Its opening paragraph states "no MCTL service has a tracer,
  exporter or propagator installed yet" — now stale for `mctl-agent`. This
  is a stronger, higher-confidence finding than the inbox item alone: a
  live doc page contradicts a live commit, not just a missing page.

## Proposed solution
1. **Update** `docs/platform/components.md` — add one bullet to the
   mctl-agent capability list: OTLP tracing via the standard `OTEL_*`
   variables, off by default, plus the two Prometheus counters.
2. **Update** `docs/reference/troubleshooting.md` — add a new
   `## Observability` section (top-level, after `## Self-Healing Agent`,
   before `## Getting Help`) covering: which `OTEL_*` variables to set,
   what a span carries (ids, model, token counts — never prompt, completion,
   or provider response body, per the commit body), and the two Prometheus
   counters with their exact names/labels and the redaction caveat.
3. **Update** `docs/reference/telemetry-attributes.md` — promote the
   specific rows `0c9e8f2` ships from `reserved` to `shipped`, naming
   `mctl-agent` / `internal/telemetry/telemetry.go` as producer (per the
   page's own stated promotion rule), and correct the opening paragraph's
   blanket "no tracer installed yet" claim to note `mctl-agent` as the
   first exception. This is a natural-fit page for this update since it
   already owns exactly this catalog; it is additive to the existing
   inbox-suggested scope (components.md + troubleshooting.md) and was
   found by fetching the live page during authoring, not invented.
4. No `docs/reference/observability.md` yet — deferred per the analyst's
   own rationale (single-service feature; premature to seed a whole new
   page for one producer).

## Alternatives
1. **New `docs/reference/observability.md` page instead of a
   troubleshooting subsection.** Rejected for now, matching the analyst's
   stated rationale: effort/impact balance favors the low-cost addition to
   an existing page until a second service ships tracing, at which point a
   dedicated page becomes worth the sidebar/nav churn.
2. **Skip the `telemetry-attributes.md` correction and only do the
   inbox-suggested two files.** Rejected: shipping a page that says
   "reserved" and "no tracer installed" while a live commit contradicts
   both is a worse state than not having found it; the page's own
   "Changing this catalog" section requires exactly this kind of
   promotion-with-producer-named edit when code ships a reserved name.

## Impact
- No `.vitepress/config.ts` sidebar change — both target pages already have
  sidebar entries (`Components` and `Troubleshooting`); `telemetry-attributes.md`
  already has its own entry too.
- No mermaid diagram required for this scope.
- `<TODO: confirm with author of 0c9e8f2 which mctl-agent release tag first
  shipped this commit>` — mctl-agent has no entry in `mcp__mctl__mctl_list_services`
  (per today's inbox), so "confirmed live" here rests on the commit itself
  plus the fact that `internal/telemetry/telemetry.go` is a no-op with no
  `OTEL_*` set, which is the reason this can be documented now without a
  separate release-tag confirmation (same reasoning the researcher used).
- Applies to the current `main` branch of `mctl-docs`; no versioning split
  needed.
