# OpenClaw API Routing and Security Hardening

## Context

In the week of 2026-04-23, `mctl-api` shipped three security hardening commits that change
observable routing behaviour for OpenClaw operations:

1. **`e4f104d`** — Identity workflows (`openclaw-identity-save`, `openclaw-identity-delete`)
   and skill quota evaluation now route to the `argo-workflows` namespace instead of the
   calling tenant's namespace. Users who watch their Argo UI will see identity jobs appear
   in `argo-workflows`, not in `admins/labs/ovk`.

2. **`92fbf9e`** — OpenClaw-specific operations (skill-save, skill-delete, identity-save,
   identity-delete) are now blocked on the generic `POST /api/v1/operations/:name/execute`
   endpoint. Callers that relied on the generic path receive a `400 Bad Request`. Only the
   dedicated OpenClaw API paths accept these operations.

3. **`edba139`** — Identity listing is restricted to a fixed allowlist; callers outside the
   allowlist receive an error. This limits which admin users can enumerate identities.

The `docs/platform/openclaw.md` page and `docs/api/index.md` describe the OpenClaw
integration at a high level but do not document the dedicated API paths, the namespace
routing logic, or the allowlist constraint. Operators who hit the `400` on the generic
`/execute` path have no documentation to consult.

> Note: `docs/platform/openclaw.md` is also targeted by the pre-existing proposal
> `proposals/openclaw-outbound-security/` (outbound sanitization + inter-session isolation).
> This proposal covers different behaviour: endpoint routing, namespace placement, and access
> control — not outbound stripping.

## User stories

- AS a **platform admin** I WANT to know which API paths accept OpenClaw skill and identity
  operations SO THAT I can call the correct endpoint and not receive an unexpected 400.
- AS a **tenant owner** I WANT to understand that identity workflow pods run in the
  `argo-workflows` namespace (not my tenant namespace) SO THAT I can correctly scope my
  monitoring and RBAC policies.
- AS a **developer** integrating with the OpenClaw API I WANT to know about the identity
  allowlist restriction SO THAT I can request the necessary permissions before writing code.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL describe that
  OpenClaw skill and identity operations use dedicated API paths (not the generic
  `/execute` endpoint).
- WHEN the page documents identity operations THE SYSTEM SHALL state that workflow pods
  run in the `argo-workflows` namespace.
- IF a reader wants to call an identity or skill operation THEN THE SYSTEM SHALL provide
  the correct endpoint path (or a reference to `docs/api/index.md` for full path details).
- WHEN the page describes identity listing THE SYSTEM SHALL note that access is subject
  to an allowlist and that non-allowlisted callers receive an error.
- WHILE version-status is unverified (no mcp__mctl__* confirmation) THE SYSTEM SHALL
  cite commit SHAs so a reviewer can verify against production.

## Out of scope

- Full REST API reference for all OpenClaw endpoints (that belongs in `docs/api/index.md`).
- Outbound sanitization / inter-session isolation (covered by `openclaw-outbound-security`).
- RBAC policy configuration for the `argo-workflows` namespace.
- Localisation / i18n.
