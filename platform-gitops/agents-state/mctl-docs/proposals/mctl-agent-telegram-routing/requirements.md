# mctl-agent Per-Tenant Telegram Routing

## Context

In commit `f4e8a38` (2026-04-27, mctl-agent 1.6.0), the `mctl-agent` self-healing agent
gained per-tenant Telegram notification routing. Previously all alerts went to a single
global Telegram chat configured via `TELEGRAM_CHAT_ID`. Now platform operators can direct
each tenant's alerts to a separate chat using one of two new configuration options:

- **`TELEGRAM_TENANT_CHAT_IDS`** — a single comma-separated env var:
  `TELEGRAM_TENANT_CHAT_IDS="admins=123,labs=456,ovk=789"`
- **`TELEGRAM_CHAT_ID_<TENANT>`** — per-tenant individual variables (e.g.
  `TELEGRAM_CHAT_ID_ADMINS`, `TELEGRAM_CHAT_ID_LABS`, `TELEGRAM_CHAT_ID_OVK`),
  used as fallback for any tenant absent from the comma-list.

When neither new variable is set, the agent falls back to the existing global
`TELEGRAM_CHAT_ID`. The three supported tenants are `admins`, `labs`, and `ovk`.

This change is deployed in mctl-gitops commit `1c59903` (mctl-agent 1.6.0). The feature
is user-visible to platform operators managing multiple tenants.

The `docs/platform/components.md` page has a section on `mctl-agent` but does not document
any Telegram configuration. There is currently no documentation for this routing capability
anywhere on docs.mctl.ai.

## User stories

- AS a **platform admin** managing multiple tenants I WANT to route each tenant's alerts
  to a separate Telegram chat SO THAT I can keep alert noise separated by team.
- AS a **platform operator** configuring a new mctl deployment I WANT to find the
  Telegram env vars documented in one place SO THAT I can configure routing correctly
  without reading source code.
- AS a **tenant owner** for `labs` I WANT to confirm that my tenant's alerts only appear
  in my chat SO THAT I can trust alert isolation across tenants.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/components.md` THE SYSTEM SHALL show a "Telegram
  alert routing" paragraph under the `mctl-agent` section.
- WHEN the paragraph describes routing configuration THE SYSTEM SHALL document both
  `TELEGRAM_TENANT_CHAT_IDS` (CSV format) and `TELEGRAM_CHAT_ID_<TENANT>` (per-variable
  fallback) with format examples.
- WHEN the paragraph describes fallback behaviour THE SYSTEM SHALL state that the global
  `TELEGRAM_CHAT_ID` is used when no per-tenant override is set.
- IF a reader wants to route `labs` alerts to a specific chat THEN THE SYSTEM SHALL
  provide a concrete config example showing both env var formats.
- WHILE version-status is unverified THE SYSTEM SHALL cite commit SHA `f4e8a38` so a
  reviewer can confirm against the deployed mctl-agent version.

## Out of scope

- Full mctl-agent configuration reference (that would belong in a dedicated reference page
  if one is created in the future).
- Telegram bot setup / BotFather instructions (external dependency, not owned by mctl).
- Non-Telegram notification channels (not part of this commit).
- Localisation / i18n.
