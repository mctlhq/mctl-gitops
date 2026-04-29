# Design: openclaw-outbound-security

## Source commits

- `mctl-openclaw:c2d31a5` — fix(outbound): strip internal runtime scaffolding
- `mctl-openclaw:c5c08c0` — fix(agents): mark inter-session prompts
- `mctl-openclaw:1e9faa2` — docs: document inter-session prompt guards
- `mctl-openclaw:98f5fd1` — docs(gateway/security): list system-reminder and previous_response in outbound stripping

## Current state of documentation

- **Existing page:** `docs/platform/openclaw.md` — "OpenClaw Integration"
  - Currently covers OpenClaw's role in the mctl platform at a high level.
  - Has no "Security" section.
  - Does not mention outbound sanitization, scaffolding stripping, or inter-session
    prompt isolation.
  - The page is **stale** relative to the shipped behaviour: openclaw's own docs were
    updated (commits `1e9faa2`, `98f5fd1`), but the mctl integration page was not.

## Proposed solution

Add a new **"Security"** subsection to `docs/platform/openclaw.md`.
The section should cover two guarantees shipped together:

1. **Outbound sanitization** — at the final channel delivery boundary, OpenClaw strips
   `<system-reminder>` and `<previous_response>` tags (including nested content) from every
   outbound message, regardless of which channel it targets. This is a core-layer guarantee,
   not per-channel configuration.

2. **Inter-session prompt isolation** — when one agent routes a message to another via
   `sessions_send` or an A2A reply, the receiving agent's prompt is wrapped with an
   `[Inter-session message … isUser=false]` envelope. This lets the receiving model
   distinguish routed agent-to-agent content from live user input in the same turn.

The section should include:
- A short prose explanation of each guarantee.
- A `mermaid` sequence diagram illustrating the outbound path with the sanitization step.
- A code excerpt showing the format of the inter-session envelope marker.
- A note that both features apply as of commit `c2d31a5` / `c5c08c0` (version: unverified).
- A cross-link to `docs/security/authentication.md`.

No changes to `.vitepress/config` are required if the new section is inside the existing
`openclaw.md` page. If the security content grows, a future proposal could split it into
`docs/platform/openclaw-security.md`, but that is out of scope here.

## Alternatives

1. **New standalone page `docs/security/openclaw-outbound.md`** — would give the content
   its own URL and sidebar entry; dropped because the content is tightly coupled to the
   OpenClaw integration context and its audience is the same as `openclaw.md` readers.
   A page split would be premature at this volume.

2. **One-liner note only, no diagram** — faster to write but the sequence diagram adds
   significant clarity for developers building multi-agent flows. Effort delta is low;
   dropped.

## Impact

- **Sidebar / nav config:** no change needed (content is added inside existing page).
- **Mermaid diagrams:** yes — one sequence diagram for the outbound delivery path.
- **Documentation versioning:** applies to the current deployed version of mctl-openclaw
  (commit `c2d31a5`); version unverified (no mcp__mctl__* check possible this run).
  Patch reviewer should confirm against production before merging.
