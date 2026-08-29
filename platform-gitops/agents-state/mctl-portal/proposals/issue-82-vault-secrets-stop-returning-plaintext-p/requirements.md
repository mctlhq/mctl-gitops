# Stop returning plaintext secrets to viewer role; write-only secret fields in UI

## Context
`vault-secrets-backend` exposes two authenticated routes —
`GET /teams/:team/:app/database` and `GET /teams/:team/:app/secrets` — that are
gated by `requireTenantRole(..., 'viewer')`
(`plugins/vault-secrets-backend/src/router.ts:80-124`). Both routes return
plaintext secret material (a database `password` field, and a full
`secrets: Record<string,string>` map of Vault KV values) to any authenticated
member of the team, including members whose role is `viewer`. This directly
contradicts the role model already documented in
`plugins/permission-backend-module-team-policy/src/module.ts:21-33`:

> `developer` — Can deploy services, view secrets (enforced in tenant-backend
> API + vault-secrets)
> `viewer` — Read-only: can see catalog entities but NOT run scaffolder tasks

So the codebase's own design intent is that only `developer` and `owner` can
see secret values — `vault-secrets-backend` just never enforced it.

On the frontend, two scaffolder field extensions compound the problem:
`packages/app/src/components/scaffolder/CurrentConfigField.tsx:155-168` calls
the `/secrets` route and puts the plaintext values into scaffolder
`formContext.formData`, and
`packages/app/src/components/scaffolder/SecureVarsEditorField.tsx:75-92`
reads that plaintext back out and auto-fills it as `KEY=value` lines into an
editable `TextField`. Once there, the plaintext is part of the scaffolder
form's submitted payload (`secret_env_vars`, wired through
`plugins/argo-workflows-backend/src/scaffolderActions.ts`) even if the user
never touches the field — so every config edit silently resubmits existing
secrets, and the values are visible in React state, the DOM, and browser
history/back-forward cache for the life of the form.
`packages/app/src/components/catalog/EntityDatabaseCard.tsx:154-176` has a
related but smaller issue: `handleLoad` eagerly fetches and stores the full
plaintext password in component state before the user ever asks to reveal it
— "masking" is purely a CSS/display toggle over data already resident in
memory and inspectable via React DevTools.

This matters because a read-only viewer can currently exfiltrate live
database and service credentials through the Backstage UI or by calling the
API directly, and because the scaffolder flow can silently round-trip and
resubmit secrets a user never intended to touch.

## User stories
- AS a team `viewer` I WANT to see that a database/service has secrets
  configured WITHOUT being able to read their plaintext values SO THAT I
  cannot exfiltrate credentials I have no operational need for.
- AS a team `developer` or `owner` I WANT an explicit, deliberate way to
  reveal a secret's plaintext value SO THAT I can use it for debugging or
  hand-off, while every reveal is audited.
- AS a team member editing a service's scaffolder config WITHOUT touching its
  secrets I WANT the form to neither display nor resubmit existing secret
  values SO THAT credentials never round-trip through the browser
  unnecessarily.

## Acceptance criteria (EARS)
- WHEN an authenticated user with role `viewer` calls
  `GET /teams/:team/:app/database` THE SYSTEM SHALL respond with connection
  metadata (host, port, database, username) and SHALL NOT include the
  plaintext `password` field.
- WHEN an authenticated user with role `viewer` calls
  `GET /teams/:team/:app/secrets` THE SYSTEM SHALL respond with the set of
  configured secret key names and SHALL NOT include plaintext secret values.
- WHEN an authenticated user with role `developer` or `owner` requests an
  explicit reveal of a database password or a service secret THE SYSTEM
  SHALL return the plaintext value on that dedicated reveal request only.
- IF a user with role `viewer` requests an explicit reveal endpoint THEN THE
  SYSTEM SHALL respond `403 Forbidden` and SHALL NOT include any secret
  value in the response body.
- WHEN a reveal endpoint returns a plaintext secret THE SYSTEM SHALL write an
  audit log entry recording who read it, for which team/app, and that it was
  a reveal (mirroring the existing `auditSecretRead` pattern in
  `plugins/vault-secrets-backend/src/router.ts:52-71`).
- WHILE the `CurrentConfigField` scaffolder extension loads existing service
  configuration THE SYSTEM SHALL fetch and expose only secret key names, not
  values, to the rest of the scaffolder form (`formContext.formData`).
- WHEN `SecureVarsEditorField` mounts for a service that already has secrets
  configured THE SYSTEM SHALL start with an empty (or hint-only) field value
  and SHALL NOT pre-fill any existing plaintext secret value into the
  editable text.
- WHEN a user submits a scaffolder config-edit form without adding or
  changing any line in the secure-variables field THE SYSTEM SHALL NOT
  resubmit any existing secret's plaintext value.
- WHEN `EntityDatabaseCard` loads a database card THE SYSTEM SHALL NOT fetch
  or hold the plaintext password in component state until the user
  explicitly clicks "Reveal" for that field.
- IF a "Reveal" action in `EntityDatabaseCard` is toggled back to hidden THE
  SYSTEM SHALL clear the previously revealed plaintext value from component
  state rather than merely hiding it visually.

## Out of scope
- team-policy default-deny (tracked separately, per the issue).
- Changing how `mctl-api` / the `deploy-service` Argo WorkflowTemplate
  persists `secret_env_vars` into Vault (that logic lives outside
  `mctl-portal`); this proposal only changes what `mctl-portal` fetches,
  stores in browser state, and submits.
- Rotating or re-issuing any credentials currently exposed under the old
  behavior (a separate incident-response action, not a code change).
- Rate limiting or additional throttling of the new reveal endpoints beyond
  the existing per-route auth check and audit log.

## Open questions
- Whether the `deploy-service`/`update-config` workflow (outside this repo,
  in `mctl-api`/`mctl-gitops` WorkflowTemplates) treats an empty or
  key-omitted `secret_env_vars` submission as "leave existing secrets
  unchanged" or as "wipe secrets not listed." This proposal assumes the
  former (the safest and most likely interpretation, consistent with
  `clear_secrets` being a distinct, explicit flag) but that assumption
  should be verified against the WorkflowTemplate/mctl-api before the
  frontend change ships, since it changes what happens when a user submits
  the form without touching secrets. Recorded here rather than blocking the
  proposal.
- Whether the reveal endpoints should require `developer` (matching the
  policy comment in `permission-backend-module-team-policy/src/module.ts`)
  or `owner` (as literally suggested in the issue body). This proposal uses
  `developer` as the minimum, since that matches the role model already
  documented elsewhere in the codebase; if the team intends something
  stricter, tightening the minimum role is a one-line change to the new
  `requireTenantRole(..., 'developer')` calls.
- Whether non-`mctl-portal` consumers of `GET /teams/:team/:app/database` or
  `/secrets` exist (e.g. other platform services calling vault-secrets-backend
  directly rather than through this UI). A repo-wide search found only the
  two frontend components addressed here, but external callers outside this
  clone cannot be ruled out from this repo alone.
