# Design: openclaw-whatsapp-newsletter

## Source commits
- `mctl-openclaw:0fad53a` — feat(whatsapp): support newsletter targets in message tool
  (2026-05-02; shipped in mctl-openclaw 2026.5.2-mctl.1 deployed 2026-05-04 via
  mctl-gitops `532bd16`)

## Current state of documentation
- Existing page: `docs/platform/openclaw.md` — covers OpenClaw at the platform
  integration level (what OpenClaw is, how it connects to the MCTL platform, tenant
  configuration). It does not describe outbound target formats for any channel, and
  the WhatsApp channel is not called out with any capability detail.
- There is no dedicated `docs/guides/whatsapp.md` or `docs/mcp/whatsapp.md` page.
- The gap: operators who want to broadcast to a WhatsApp Channel/Newsletter via the
  MCTL platform find zero mentions of `@newsletter` JIDs or target format guidance.

## Proposed solution
Update `docs/platform/openclaw.md` with a new **"WhatsApp outbound target formats"**
subsection under the existing WhatsApp/channel coverage (or, if none exists yet, a
new "Channel-specific notes" section). The subsection contains:

1. A small table (or three-item list) of supported target formats:
   | Format | Type | Example |
   |---|---|---|
   | E.164 phone number | DM | `+15551234567` |
   | Group JID | Group chat | `1234567890-1234567890@g.us` |
   | Newsletter JID | Channel/Newsletter | `120363123456789@newsletter` |

2. A NOTE callout: `allowFrom` is a DM-only allow-list — it does not restrict outbound
   sends to group or newsletter JIDs.

3. A one-liner CLI example:
   ```bash
   openclaw message send \
     --channel whatsapp \
     --target 120363123456789@newsletter \
     --message "Weekly platform digest"
   ```

4. A version note: requires mctl-openclaw ≥ 2026.5.2.

No sidebar / nav config changes are needed — `openclaw.md` is already in the nav.

## Alternatives

### A. New standalone page `docs/guides/whatsapp-channel.md`
Pros: room for a full how-to (setup, pairing, target formats, `allowFrom`).
Cons: overkill for a single new target format; creates nav maintenance overhead;
the existing `openclaw.md` is the right first stop for platform-level WhatsApp
configuration. **Dropped** — the update to `openclaw.md` is proportionate.

### B. Add to `docs/reference/glossary.md`
Pros: central reference for JID formats.
Cons: glossary is for definitions, not how-to; a CLI example does not belong there.
**Dropped**.

## Impact
- **VitePress sidebar / nav config:** No change needed.
- **Diagrams:** Not required; a simple table and code block are sufficient.
- **Documentation versioning:** Applies to mctl-openclaw ≥ 2026.5.2
  (confirmed in production on `admins` tenant as of 2026-05-04).
- **Cross-links:** Consider a cross-reference from `docs/reference/troubleshooting.md`
  ("WhatsApp newsletter messages not delivered → confirm `@newsletter` JID format and
  mctl-openclaw ≥ 2026.5.2").
