# OpenClaw Outbound Sanitization and Inter-Session Isolation

## Context

In the week of 2026-04-22 to 2026-04-28, `mctl-openclaw` shipped a two-part security
hardening that changes what mctl tenants can rely on about message delivery:

1. **Outbound sanitization** (`c2d31a5`): OpenClaw now strips `<system-reminder>` and
   `<previous_response>` XML tags at the final channel delivery boundary before any message
   reaches an end user via Discord, Telegram, or any other registered channel. Degraded harness
   replies or plugin-injected scaffolding can no longer leak internal runtime framing to users.

2. **Inter-session prompt isolation** (`c5c08c0`): Agent-to-agent (`sessions_send`) and A2A
   follow-up prompts now carry an explicit `[Inter-session message … isUser=false]` envelope
   at the time of the model call, not just as provenance metadata appended to the transcript.
   The receiving agent can now distinguish routed internal messages from live end-user input
   in the same turn.

OpenClaw's own reference documentation was updated in commits `1e9faa2` and `98f5fd1`.
The `docs.mctl.ai` integration page `docs/platform/openclaw.md` has not been updated and
does not mention either guarantee.

## User stories

- AS a **tenant owner** I WANT to know that outbound channel messages are sanitized of
  internal scaffolding SO THAT I can trust that my users never see raw `<system-reminder>`
  or `<previous_response>` fragments, even after a model failure or plugin hook anomaly.
- AS a **platform admin** I WANT to understand the inter-session isolation model SO THAT I
  can correctly interpret agent transcripts and audit logs when one agent routes prompts to
  another.
- AS a **developer** integrating a multi-agent flow I WANT to understand how `isUser=false`
  affects model context SO THAT I can design my agent prompts knowing that A2A inputs are
  explicitly marked as non-user content.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL show a "Security"
  section that describes the outbound sanitization guarantee and names `<system-reminder>`
  and `<previous_response>` as stripped tags.
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL explain the
  `[Inter-session message isUser=false]` envelope and its purpose (distinguishing A2A
  routed input from live end-user input).
- IF a reader wants to know which channels apply the outbound sanitizer THEN THE SYSTEM
  SHALL state that it applies at the core delivery boundary (all channels), not per-channel.
- WHEN a reader opens the Security section THE SYSTEM SHALL cross-link to
  `docs/security/authentication.md` or `docs/security/authorization.md` where relevant.
- WHILE version-status is unverified (no mcp__mctl__* confirmation available) THE SYSTEM
  SHALL note the commit SHA so a reviewer can verify against production.

## Out of scope

- Per-channel sanitization configuration (not yet exposed as a user knob).
- Full transcript hygiene reference (that belongs in openclaw's own docs, not docs.mctl.ai).
- Localisation / i18n of the new section.
- Video tutorial on multi-agent routing.
