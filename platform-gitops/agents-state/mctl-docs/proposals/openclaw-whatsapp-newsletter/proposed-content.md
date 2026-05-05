# Proposed content: openclaw-whatsapp-newsletter

> **Apply to:** `mctl-docs/docs/platform/openclaw.md` (UPDATE)
> **Source:** mctl-openclaw@0fad53a
> **Version gate:** mctl-openclaw ≥ 2026.5.2 (deployed to production 2026-05-04)

---

Find the existing WhatsApp section in `docs/platform/openclaw.md` (or the nearest
"channels" or "configuration" section). Insert the following block immediately after
any existing WhatsApp setup/configuration content. If no WhatsApp section exists yet,
append the block at the end of the page before any footer.

### BEFORE (existing page — no WhatsApp target-format content)

```markdown
<!-- no section on WhatsApp outbound targets currently exists -->
```

### AFTER (add this section)

```markdown
## WhatsApp outbound target formats

> Requires mctl-openclaw ≥ 2026.5.2.

The WhatsApp channel supports three outbound target formats in the `message send`
command and in skill action payloads:

| Target type | Format | Example |
|---|---|---|
| Direct message (DM) | E.164 phone number | `+15551234567` |
| Group chat | Group JID (`@g.us`) | `1234567890-1234567890@g.us` |
| Channel / Newsletter | Newsletter JID (`@newsletter`) | `120363123456789@newsletter` |

**Example — broadcast to a WhatsApp Newsletter:**

```bash
openclaw message send \
  --channel whatsapp \
  --target 120363123456789@newsletter \
  --message "Weekly platform digest"
```

Outbound newsletter sends use channel session metadata
(`agent:<agentId>:whatsapp:channel:<jid>`) rather than DM session semantics.

::: info allowFrom scope
`allowFrom` is a DM-only sender access-control list. It does **not** restrict explicit
outbound sends to group JIDs (`@g.us`) or newsletter JIDs (`@newsletter`). To control
who can trigger outbound newsletter sends, use skill-level action guards or operator
permissions instead.
:::
```

---

> **Cross-link** — also add to `docs/reference/troubleshooting.md` under a
> "WhatsApp" entry:
>
> ```markdown
> **WhatsApp newsletter messages not delivered**
> Confirm you are using the `@newsletter` JID format (e.g.
> `120363123456789@newsletter`) and that mctl-openclaw ≥ 2026.5.2 is deployed.
> See [WhatsApp outbound target formats](/platform/openclaw#whatsapp-outbound-target-formats).
> ```
