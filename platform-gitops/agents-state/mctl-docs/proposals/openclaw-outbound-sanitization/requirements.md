# OpenClaw Outbound Content Sanitization

## Context

In the 2026-04-28 release cycle, `mctl-openclaw` shipped two related security features:

1. **Outbound scaffolding stripping** (`c2d31a5`) — the final channel delivery boundary now strips
   `<system-reminder>` and `<previous_response>` XML tags (and their content) from every outbound
   message across all channel adapters (Telegram, Discord, Slack). This prevents internal runtime
   scaffolding injected by the harness from leaking to end users.

2. **Inter-session prompt marking** (`c5c08c0`) — when the agent runtime routes a message between
   sessions (A2A relay, embedded runner), the receiving session's prompt is wrapped in an
   `[Inter-session message … isUser=false]` envelope so the model can distinguish routed
   agent-to-agent content from live user input.

OpenClaw's own documentation was updated in the same cycle (`1e9faa2`, `98f5fd1`), but
`docs.mctl.ai/platform/openclaw.md` still has no Security section and makes no mention
of either guarantee. Platform operators and developers building multi-agent workflows on
the admins/labs/ovk tenants cannot discover these guarantees without reading the upstream
source.

> **Note:** The overlapping proposal `openclaw-outbound-security` (created 2026-04-29)
> covers the same commits (`c2d31a5`, `c5c08c0`, `1e9faa2`, `98f5fd1`) in greater
> architectural detail. This proposal focuses on the user-facing documentation deliverable
> (the ready-to-apply markdown). Implementers should treat both proposals as a single
> work item and apply either `proposed-content.md`.

## User stories

- AS a **platform operator** I WANT to know which XML tags OpenClaw strips from outbound
  channel messages SO THAT I can verify that internal scaffolding does not leak to my
  tenant's end users.
- AS a **developer** building a multi-agent flow on the mctl platform I WANT to understand
  how inter-session messages are marked SO THAT I can design my agent prompts to
  distinguish routed content from live user input.
- AS a **security reviewer** I WANT a single documentation page that describes the channel
  delivery sanitization guarantee SO THAT I can include it in threat-model assessments.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL show a "Security"
  subsection that lists `<system-reminder>` and `<previous_response>` as tags stripped
  at the final channel delivery boundary.
- WHEN a reader wants to understand the outbound sanitization flow THE SYSTEM SHALL
  provide a mermaid sequence diagram illustrating the sanitization step between the
  agent runtime and the channel adapter.
- WHEN a reader asks what happens to inter-session prompt content THE SYSTEM SHALL
  explain the `[Inter-session message … isUser=false]` envelope and its purpose.
- WHILE the production version of mctl-openclaw cannot be confirmed THE SYSTEM SHALL
  include a note stating "version-status: unverified — verify against the live
  mctl-openclaw deployment before publishing."

## Out of scope

- Per-channel configuration of the stripping behaviour (not exposed to operators).
- Documentation of all stripped tags beyond `<system-reminder>` and `<previous_response>`
  (the proposal is scoped to what landed in `c2d31a5`/`98f5fd1`).
- Migration guide for integrations that relied on the previous (unstripped) behaviour.
- Localisation or i18n of the new section.
