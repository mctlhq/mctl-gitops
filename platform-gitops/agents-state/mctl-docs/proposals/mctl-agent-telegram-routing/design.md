# Design: mctl-agent-telegram-routing

## Source commits

- `mctl-agent:f4e8a38` — feat(notify): per-tenant Telegram routing
- `mctl-gitops:1c59903` — chore: bump mctl-agent to 1.6.0 (confirms deployment)

## Current state of documentation

- **Existing page:** `docs/platform/components.md` — "Components"
  - Has a subsection on `mctl-agent` describing its self-healing role (AlertManager webhook →
    GitHub PR fixer).
  - Does **not** document any Telegram configuration.
  - Does **not** mention `TELEGRAM_CHAT_ID`, `TELEGRAM_TENANT_CHAT_IDS`, or the routing logic.
  - **Gap** (not stale): the feature is new; the page simply has no alert-routing section.

## Proposed solution

Add a **"Telegram alert routing"** paragraph to the `mctl-agent` subsection of
`docs/platform/components.md`. The paragraph should:

1. Explain that mctl-agent sends alert notifications to Telegram.
2. Describe the three-tier lookup:
   - Tier 1: `TELEGRAM_TENANT_CHAT_IDS` CSV env var.
   - Tier 2: `TELEGRAM_CHAT_ID_<TENANT>` individual env var (fallback for missing keys).
   - Tier 3: global `TELEGRAM_CHAT_ID` (legacy fallback when no per-tenant vars are set).
3. Show a concrete configuration example for all three tenants.
4. Note the supported tenant names: `admins`, `labs`, `ovk` (lowercase, matching platform
   convention).

Content is short (one paragraph + one code block). No new page needed, no sidebar change.

## Alternatives

1. **New dedicated page `docs/reference/mctl-agent-config.md`** — would be the right place
   if/when mctl-agent grows a larger configuration surface (webhook settings, GitHub config,
   poll interval, etc.). For now a single paragraph inside the existing components page is
   proportionate. Dropped.

2. **Add to `docs/guides/tenants.md`** — that page covers tenant management from the
   platform-admin perspective; Telegram routing is an operational config detail better
   co-located with the component description. Dropped.

## Impact

- **Sidebar / nav config:** no change required.
- **Mermaid diagrams:** not required — the three-tier lookup is best shown as a code block
  (env var examples) rather than a diagram.
- **Documentation versioning:** applies to mctl-agent 1.6.0 (commit `f4e8a38`, deployed
  via mctl-gitops `1c59903`). version-status: unverified.
