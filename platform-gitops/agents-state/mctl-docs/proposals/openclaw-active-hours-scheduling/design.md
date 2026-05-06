# Design: openclaw-active-hours-scheduling

## Source Commits

- `mctl-openclaw:10448a0` — fix(heartbeat): make phase scheduling active-hours-aware
  (shipped in 2026.5.2-mctl.1; deployed 2026-05-04 via `mctl-gitops:532bd16`)

## Current State of Documentation

- **Existing page:** `docs/platform/openclaw.md` — title "OpenClaw Integration".
  The docs-tree snapshot describes it simply as "OpenClaw Integration" with no detail
  on per-agent configuration. It is likely a high-level overview page.
- **Gap:** No mention of `active-hours` configuration, scheduling windows, timezones,
  or heartbeat behaviour anywhere on `docs.mctl.ai`.
- A user wanting to configure time-bounded agent availability would need to read the
  upstream OpenClaw changelog or source code — both are inaccessible to typical tenants.

## Proposed Solution

**Update `docs/platform/openclaw.md`** by adding a new subsection titled
**"Agent scheduling: active hours"** after the existing content. The subsection should:

1. Explain what `active-hours` is: a per-agent configuration that restricts when the
   agent fires its heartbeat (and therefore when it processes queued work / sends
   messages).
2. Show the configuration block (YAML example) with a placeholder TODO for the exact
   key name pending author confirmation.
3. Explain the quiet-hours skip behaviour: heartbeat periods (e.g. `4h`) are aligned
   to in-window slots; quiet-hours slots are skipped rather than accumulated into a
   burst upon resumption.
4. Add a one-liner cross-link from `docs/reference/troubleshooting.md` ("Agent appears
   silent → check active-hours config") so troubleshooters find the feature.

**No new page is needed.** The active-hours feature is one subsection of the OpenClaw
platform integration, and the volume of content (one config block + two paragraphs) does
not justify a standalone page.

**VitePress sidebar / nav config:** No change needed — the existing `openclaw.md` entry
in the sidebar remains; only the page body grows.

**Mermaid diagram:** Optional — a simple state diagram showing `active → quiet → active`
transitions could clarify the scheduling model if the subsection grows, but it is not
required for MVP.

## Alternatives

1. **New standalone `docs/guides/scheduling.md` page** — covers heartbeat, cron triggers,
   and active hours together. Dropped: too broad for a single fix commit; would require
   inventying heartbeat/cron docs not yet signalled by code changes.
2. **Add to `docs/reference/glossary.md`** — defines `active-hours` as a term.
   Dropped: a glossary entry alone does not show how to configure the feature; users
   need an example.

## Impact

- Touches: `docs/platform/openclaw.md` (body only, no frontmatter change needed).
- Cross-link: `docs/reference/troubleshooting.md` (one bullet point added).
- VitePress sidebar/nav: no change.
- Mermaid diagrams: optional, not required.
- Documentation versioning: applies to mctl-openclaw ≥ 2026.5.2 (current stable);
  no older-version branching needed (docs.mctl.ai is single-version per ADR 0001).
- **One TODO marker required:** `<!-- TODO: confirm activeHours key syntax with author
  of mctl-openclaw@10448a0 before merging -->` — the exact YAML key name
  (`activeHours`, `active_hours`, or nested object) is not confirmed from the commit
  message alone.
