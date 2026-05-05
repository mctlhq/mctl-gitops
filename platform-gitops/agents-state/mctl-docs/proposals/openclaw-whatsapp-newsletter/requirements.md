# Document WhatsApp Channel/Newsletter Outbound Target Support

## Context
mctl-openclaw 2026.5.2 (released 2026-05-02, deployed to production via mctl-gitops
`532bd16` on 2026-05-04) added support for WhatsApp Channel/Newsletter JIDs as explicit
outbound message targets. Previously the WhatsApp channel only recognised DM targets
(E.164 phone numbers like `+15551234567`) and group targets (`...@g.us`). Newsletter
JIDs (`...@newsletter`) were not handled, so broadcasts to WhatsApp Channels/Newsletters
would silently fail or route incorrectly.

Commit `0fad53a` in mctl-openclaw added:
1. A new outbound routing path for `@newsletter` JIDs using channel session metadata
   (`agent:<agentId>:whatsapp:channel:<jid>`) instead of DM session semantics.
2. A clarification that `allowFrom` is a DM-only access-control list; it does **not**
   gate outbound sends to group or newsletter JIDs.
3. Updated CLI reference in the upstream openclaw docs (`docs/channels/whatsapp.md`,
   `docs/cli/directory.md`, `docs/cli/message.md`).

`docs.mctl.ai/platform/openclaw.md` covers the OpenClaw integration at the platform
level but has no mention of WhatsApp outbound target formats. Operators who rely on
the MCTL platform to deliver messages to WhatsApp newsletters have no platform
documentation to guide them.

## User stories
- AS a **platform admin** I WANT to know all supported WhatsApp outbound target formats
  SO THAT I can configure skill actions and automation that broadcast to WhatsApp
  Channels/Newsletters without trial and error.
- AS a **tenant owner** using the WhatsApp channel I WANT to understand that `allowFrom`
  restricts only inbound DMs SO THAT I do not accidentally assume it protects outbound
  newsletter sends.
- AS a **developer** testing OpenClaw integrations I WANT to find a single table of
  WhatsApp target ID formats in the MCTL docs SO THAT I can write correct `--target`
  values for `openclaw message send` commands.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL list all three
  WhatsApp outbound target formats: DM (`+15551234567`), group
  (`1234567890-1234567890@g.us`), and Channel/Newsletter (`120363123456789@newsletter`).
- WHEN a reader consults the WhatsApp target table THE SYSTEM SHALL include a note
  clarifying that `allowFrom` applies only to DM senders and does not gate outbound
  group or newsletter sends.
- WHEN a reader wants to send to a WhatsApp Newsletter THE SYSTEM SHALL provide a
  ready-to-use CLI example using the `@newsletter` JID format.
- IF the feature is documented THE SYSTEM SHALL attribute it to mctl-openclaw ≥ 2026.5.2
  so readers know it is not available on older deployments.
- WHILE no session metadata for `@newsletter` JIDs exists THE SYSTEM SHALL note that
  a new session key (`agent:<agentId>:whatsapp:channel:<jid>`) is used rather than
  the DM session semantics.

## Out of scope
- Documenting WhatsApp local model configuration or hardware floors (openclaw
  operator-level, not a platform doc concern).
- Updating the upstream openclaw docs (already done in the mctl-openclaw repo).
- Adding a dedicated WhatsApp channel guide page (the existing `openclaw.md` update
  is sufficient for the platform audience).
- i18n / localisation of the documentation.
