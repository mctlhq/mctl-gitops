# Proposed content: mctl-agent-telegram-routing

> **Apply to:** `mctl-docs/docs/platform/components.md` (UPDATE)
> **Source:** mctl-agent@f4e8a38

---

Locate the `mctl-agent` subsection in `docs/platform/components.md` and append the
following paragraph after the existing description of the self-healing agent.

---

**Before** (existing mctl-agent section ends with something like):

> mctl-agent receives AlertManager webhooks, opens GitHub pull requests to fix the
> underlying issue, and notifies the team via Telegram.

---

**After** — append this block immediately after the description above:

---

### Telegram alert routing

mctl-agent routes alert notifications to Telegram. From version 1.6.0
(commit `mctl-agent@f4e8a38`, deployed in mctl-agent 1.6.0), each tenant can receive
alerts in its own chat via per-tenant routing:

**Option A — single CSV env var (recommended):**

```bash
TELEGRAM_TENANT_CHAT_IDS="admins=-100123456789,labs=-100987654321,ovk=-100111222333"
```

**Option B — per-tenant individual env vars (fallback):**

```bash
TELEGRAM_CHAT_ID_ADMINS=-100123456789
TELEGRAM_CHAT_ID_LABS=-100987654321
TELEGRAM_CHAT_ID_OVK=-100111222333
```

Both formats can be combined: the CSV variable is checked first; any tenant absent from
the CSV list falls back to the corresponding `TELEGRAM_CHAT_ID_<TENANT>` variable.

**Legacy fallback:** when no per-tenant variables are set, all alerts go to the global
`TELEGRAM_CHAT_ID` (the single-chat behaviour from earlier versions).

Supported tenant names (lowercase): `admins`, `labs`, `ovk`.

> _version-status: unverified — confirm mctl-agent 1.6.0 is deployed to production
> before relying on this documentation._

---
