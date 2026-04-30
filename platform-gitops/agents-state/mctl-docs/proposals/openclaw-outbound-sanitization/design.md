# Design: openclaw-outbound-sanitization

## Source commits

- `mctl-openclaw:c2d31a5` — fix(outbound): strip internal runtime scaffolding
- `mctl-openclaw:c5c08c0` — fix(agents): mark inter-session prompts
- `mctl-openclaw:1e9faa2` — docs: document inter-session prompt guards
- `mctl-openclaw:98f5fd1` — docs(gateway/security): list system-reminder and previous_response in outbound stripping

> **version-status: unverified** — `mcp__mctl__*` tools unavailable this run.
> Confirm these commits are deployed to production before merging the doc patch.
> Deploy evidence: `mctl-gitops` bumped admins-openclaw to `2026.4.29-beta.2` in commits
> `dc23a5d` / `e609fee` (2026-04-29), which is after `c2d31a5` (2026-04-28). Likely shipped.

## Current state of documentation

- **Existing page:** `docs/platform/openclaw.md` — "OpenClaw Integration"
  - Covers OpenClaw's role as the multi-channel AI gateway (Telegram/Slack/Discord/BlueBubbles),
    tenant isolation, and skill routing at a high level.
  - Has **no Security section** and makes no mention of outbound sanitization, scaffolding
    stripping, or inter-session prompt isolation.
  - The page is **stale** relative to shipped behaviour: openclaw's own docs (`docs/gateway/
    security/index.md`, `docs/reference/transcript-hygiene.md`, `docs/concepts/session-tool.md`)
    were updated in commits `1e9faa2` and `98f5fd1`, but the mctl integration page was not.

## Proposed solution

Add a new **"Security"** subsection to `docs/platform/openclaw.md` after the existing
"Tenant isolation" or "Channel routing" content (whichever appears last before the
conclusion/references). The subsection should contain:

1. **Outbound content sanitization** — brief prose, then a bullet list of stripped tags,
   then a mermaid sequence diagram of the sanitization path.
2. **Inter-session prompt isolation** — one paragraph explaining the `isUser=false` envelope,
   with a short code block showing the marker format.
3. A cross-link to `docs/security/authentication.md`.

No changes to `.vitepress/config` (sidebar/nav) are needed — the new content is inside
the existing page, not a new page.

## Alternatives

1. **New standalone page `docs/security/openclaw-outbound.md`** — gives the content its
   own sidebar entry and URL. Dropped because the audience is identical to `openclaw.md`
   readers and the content volume (one subsection) does not justify a split. A future
   proposal can promote it if the Security section grows significantly.

2. **Update `docs/security/authentication.md` instead of `openclaw.md`** — the auth page
   already covers credential models; outbound sanitization is a delivery-layer concern,
   not an auth concern. Adding it to `openclaw.md` keeps the feature's context (channel
   delivery) intact. Only a cross-link goes in `authentication.md`.

3. **One-liner note only** — faster but loses the mermaid diagram that concisely explains
   the delivery boundary. The diagram adds ~10 lines of markdown and significant clarity
   for developers building multi-agent flows.

## Impact

- **Sidebar / nav config:** no change required.
- **Mermaid diagrams:** yes — one sequence diagram for the outbound delivery path.
- **Documentation versioning:** applies to the current deployed version of mctl-openclaw
  (commit `c2d31a5`). Version unverified (no mcp__mctl__* check possible this run).
- **Overlap:** This proposal duplicates the scope of `openclaw-outbound-security`
  (created 2026-04-29). Both target the same page and same subsection. Implementers
  should treat them as one work item; `proposed-content.md` in this proposal is the
  ready-to-apply patch.
