# Design: issue-82-vault-secrets-stop-returning-plaintext-p

## Current state

**Backend — `plugins/vault-secrets-backend/src/router.ts`**
- `GET /teams/:team/:app/database` (lines 80-106) and
  `GET /teams/:team/:app/secrets` (lines 108-124) both call
  `requireTenantRole(req, ..., team, 'viewer')` (line 82, line 110) — the
  lowest role tier — and then return Vault KV data verbatim, including the
  plaintext `password` field (line 100) and the full `secrets` value map
  (line 119).
- `requireTenantRole` (lines 218-241) delegates to `checkTenantRole` (lines
  243-263), whose `minimumRole` parameter is typed `'viewer' | 'owner'` and
  whose only comparison is `if (minimumRole === 'owner' && member.role !==
  'owner')`. There is no notion of the middle `developer` tier at the
  authorization layer, even though the role itself is three-valued elsewhere
  in the codebase (`plugins/github-app-connect-backend/src/types.ts:64`:
  `role: 'owner' | 'developer' | 'viewer'`).
- `plugins/permission-backend-module-team-policy/src/module.ts:21-33`
  documents the intended model explicitly: `developer` — "Can deploy
  services, view secrets (enforced in tenant-backend API + vault-secrets)";
  `viewer` — "Read-only... NOT run scaffolder tasks." `vault-secrets-backend`
  never implemented the `developer` gate the comment describes.
- `auditSecretRead` (lines 52-71) already logs every successful secret read
  (who, team/app, role, admin-bypass flag, and key names for `/secrets`) but
  has no concept of "masked read" vs. "plaintext reveal" — every call today
  is a plaintext reveal.

**Frontend — three consumers, all in `packages/app/src/components/`**
- `catalog/EntityDatabaseCard.tsx`: `handleLoad` (154-176) fetches
  `/teams/:team/:app/database` and stores the entire response — including
  plaintext `password` — into `creds` state (141, 170) as soon as the user
  clicks "Load Credentials." `MaskedField` (82-132) only toggles a CSS
  class/`revealed` boolean over data that is already in memory; "hide" does
  not clear it.
- `scaffolder/CurrentConfigField.tsx`: the effect at 155-168 calls
  `GET /teams/:team/:app/secrets`, takes `vaultData.secrets` (plaintext), and
  merges it into a `ServiceConfig` object that is JSON-stringified and pushed
  into the scaffolder form via `onChangeRef.current(dataStr)` (176) — i.e.
  into `formContext.formData`, which downstream scaffolder steps and the
  final submitted parameters can see.
- `scaffolder/SecureVarsEditorField.tsx`: the effect at 75-92 reads
  `formContext.formData.currentConfig` (the JSON blob above), parses out
  `config.secrets`, and calls `onChange(lines)` (85) to pre-fill the editable
  `TextField`'s value with `KEY=plaintextValue` lines — before the user has
  typed anything. `maskValues` (33-44) only affects the *displayed* string
  (`displayValue`, line 110); the underlying `formData` driving `onChange`,
  and therefore the submitted form value, is still plaintext.
- The submitted value flows out through
  `plugins/argo-workflows-backend/src/scaffolderActions.ts` (`mctl:workflow:submit`),
  which forwards whatever the template supplies as the `secret_env_vars`
  Argo Workflow parameter (masking only its own log output, lines 124-138) —
  confirming that whatever `SecureVarsEditorField` submits becomes the
  literal payload written toward Vault via the `deploy-service` workflow.

Repo-wide search (`Grep` over `**/*.{ts,tsx}` for the two route paths and
`vault-secrets`) found no other in-repo consumers of these two routes beyond
the three components above — see Open Questions in requirements.md for the
caveat on out-of-repo callers.

## Proposed solution

### 1. Backend: add a `developer` tier to the authorization check
Extend `checkTenantRole`/`requireTenantRole` in
`plugins/vault-secrets-backend/src/router.ts` to a proper rank comparison
instead of the current `viewer`/`owner`-only equality check:

```ts
const ROLE_RANK: Record<string, number> = { viewer: 0, developer: 1, owner: 2 };

function meetsMinimumRole(role: string, minimumRole: 'viewer' | 'developer' | 'owner'): boolean {
  return (ROLE_RANK[role] ?? -1) >= ROLE_RANK[minimumRole];
}
```

`checkTenantRole`'s `minimumRole` parameter becomes
`'viewer' | 'developer' | 'owner'`, and the owner-only branch is replaced
with `if (!meetsMinimumRole(member.role, minimumRole)) { ... 403 ... }`. This
is behavior-preserving for every existing call site: `'viewer'` minimum still
accepts everyone with membership, `'owner'` minimum (the two
`/openclaw/intake` routes, line 147 and line 194) still accepts only
`role === 'owner'` because `ROLE_RANK.owner (2) >= ROLE_RANK.owner (2)` and
nothing below it qualifies. The admin bypass (lines 252-254) is untouched —
it already synthesizes `role: 'owner'`, the top rank.

### 2. Backend: mask-by-default, explicit reveal, both audited
Keep the existing route paths but change what the *default* GET returns, and
add two new reveal routes:

- `GET /teams/:team/:app/database` — minimum role stays `viewer` (host,
  port, database, username are connection metadata, not the secret itself).
  Response drops `password` and adds `hasPassword: boolean`. Still calls
  `auditSecretRead` with a new `kind: 'database-meta'` (metadata read, no
  plaintext) so the audit trail can distinguish it from a real reveal.
- `GET /teams/:team/:app/database/reveal` — new route, minimum role
  `developer`. Returns the same shape as today's `/database` (including
  `password`). Audited via `auditSecretRead(..., 'database', ...)` — reusing
  the existing `kind: 'database'` value keeps today's audit semantics
  ("a plaintext database read happened") attached to the route that now
  actually performs one.
- `GET /teams/:team/:app/secrets` — minimum role stays `viewer`. Response
  becomes `{ secretKeys: string[] }` (key names only, no values) —
  structurally identical to what `github-app-connect-backend`'s
  `/service-config` already returns as `secretKeys`, so the two "existing
  config" surfaces the frontend already juggles become consistent. Audited
  as `kind: 'secrets-meta'`.
- `GET /teams/:team/:app/secrets/reveal` — new route, minimum role
  `developer`. Returns `{ secrets: Record<string,string> }` as today's
  `/secrets` does. Audited as `kind: 'secrets'` (same reasoning as above).

`auditSecretRead`'s `kind` parameter type grows from
`'database' | 'secrets'` to `'database' | 'database-meta' | 'secrets' |
'secrets-meta'`; the function body is otherwise unchanged (it already just
stamps whatever `kind` string it's given into the log line).

This two-tier design (viewer sees existence/metadata only; developer+ can
explicitly reveal) satisfies both the acceptance criteria (no plaintext to
viewer) and the issue's stated preference for "a masked response plus an
explicit one-time reveal endpoint that is audited" — while keeping the
authorization tier aligned with the model `permission-backend-module-team-policy`
already documents.

### 3. Frontend: `EntityDatabaseCard.tsx`
- `handleLoad` calls the masked `/database` route only; `creds` state holds
  `{ host, port, database, username, hasPassword }` — no plaintext password
  ever enters component state on load.
- The password `MaskedField` row gets its own lazy load: clicking "Reveal"
  (when `hasPassword` is true) triggers a fetch to `/database/reveal`,
  stores the returned password in a small piece of local state scoped to
  that field, and flips to revealed. Clicking "Hide" clears that state
  (`setPassword(undefined)`) rather than only toggling a boolean, so the
  plaintext does not linger in memory/React DevTools after the user hides
  it. A 403 from `/reveal` (viewer role) is surfaced as an inline message
  ("Developer or owner role required to reveal this value") instead of a
  silent failure.
- Non-secret fields (host/port/database/username) keep today's copy/observe
  behavior unchanged.

### 4. Frontend: `CurrentConfigField.tsx`
- Switch the Vault fetch from `/teams/:team/:app/secrets` to the same route
  (now masked) and read `secretKeys` instead of `secrets` from the response.
- `ServiceConfig`'s `secrets: Record<string, string>` field is dropped
  entirely; the type becomes `{ envVars: string; secretKeys: string[] }`.
  The render path (227-255) already has a `config.secretKeys.length > 0`
  fallback branch for exactly this shape (it previously only ran when
  `config.secrets` was empty but `secretKeys` was populated) — that branch
  becomes the only branch, so no plaintext ever reaches the chip display or
  the `formContext.formData` JSON blob other fields read from.

### 5. Frontend: `SecureVarsEditorField.tsx`
- Remove the auto-fill effect (75-92) that reads `config.secrets` and calls
  `onChange(lines)` with plaintext `KEY=value` pairs before the user has
  typed anything — that data source no longer exists after change 4, but the
  effect is also rewritten (not just left to silently no-op) so the field is
  explicitly write-only by construction.
- Add a read-only hint line above the field, sourced from
  `currentConfig.secretKeys` (available with no fetch needed — it rides in
  on the same `formContext.formData.currentConfig` blob `CurrentConfigField`
  already writes): "Existing keys (values hidden): API_KEY, DATABASE_PASSWORD.
  Leave blank to keep them unchanged; add a `KEY=value` line only for a key
  you want to set or change."
- `formData` starts `''`/`undefined` for a service with existing secrets
  (today it starts pre-filled). `onChange` is therefore only ever called
  with lines the user actually typed, so submitting the form without
  touching this field submits no `secret_env_vars` lines at all — see Open
  Questions in requirements.md on how the downstream workflow should
  interpret that.
- The existing masked-display toggle (`masked`/`maskValues`, still useful
  while typing a real value to prevent shoulder-surfing) is kept as-is; it
  was never the source of the plaintext leak.

## Alternatives

1. **Gate the existing routes at `owner` instead of introducing a
   `developer` tier**, per the issue's literal wording ("require at least
   `owner`"). Dropped because it contradicts the role model the codebase
   already documents in `permission-backend-module-team-policy/src/module.ts`
   ("developer — ... view secrets"), and would silently break the (intended,
   if previously unenforced) ability of `developer`-role users to see
   secrets — a bigger behavior change than the issue's evidence supports.
   Recorded as an open question in case the team actually wants `owner`-only.

2. **Keep one route per resource and add a `?reveal=true` query parameter**
   instead of a separate `/reveal` path. Dropped because it makes the
   masked/plaintext distinction less visible in logs, routing tables, and
   audit `kind` values, and makes it easy to accidentally default
   `reveal=true` somewhere. A distinct path is also easier to rate-limit or
   alert on later if that's ever needed (out of scope here, but the shape
   shouldn't preclude it).

3. **Have the frontend redact secrets client-side only** (fetch full
   plaintext as today, just don't render it) instead of changing the
   backend response shape. Dropped outright: plaintext would still cross the
   network to every `viewer`'s browser and sit in `fetch`/network-tab
   history, defeating the purpose. The issue explicitly evidences this
   exact bypass ("read-only viewers can exfiltrate credentials").

4. **Encrypt secret values in transit with a client-held key instead of a
   role gate.** Dropped as disproportionate: there is no existing key
   distribution mechanism in this codebase, Vault already is the source of
   truth and access control point, and the simpler role-gate + audit
   approach directly satisfies the issue's acceptance criteria.

## Platform impact

- **Backward compatibility / breaking change:** the response shape of the
  two existing GET routes changes (password/secrets values removed). The
  only in-repo consumers are the two components updated in this same change
  (`EntityDatabaseCard.tsx`, `CurrentConfigField.tsx`); see the open question
  on possible out-of-repo consumers.
- **No database migrations.** No changes to `tenant_members` or any schema —
  role values (`viewer`/`developer`/`owner`) already exist as stored strings.
- **No new external dependencies or resource impact** — the reveal routes
  reuse the existing `vaultFetch`/`VaultTokenProvider` machinery
  (`plugins/vault-secrets-backend/src/vaultAuth.ts`) and Vault KV paths
  unchanged.
- **Risk: downstream workflow semantics for omitted secrets.** As recorded
  in requirements.md's Open Questions, this change means "no edits to
  secrets" now submits an empty `secret_env_vars`. If the `deploy-service`
  WorkflowTemplate / `mctl-api` update-config path treats that as "clear all
  secrets" rather than "no-op," this proposal would introduce a functional
  regression (accidental secret wipe) alongside the security fix. Mitigation:
  verify that behavior (or add an explicit "no changes" sentinel/flag in the
  submitted parameters) before the frontend change ships; call this out
  loudly in code review and in the task list below.
- **Risk: silent behavior change for `developer`-role users**, who gain the
  ability to reveal secrets/passwords for the first time in a way that's
  actually gated (today they could already do this via the unguarded viewer
  path, so this is a tightening, not a widening, for them) — no action
  needed, noted for completeness.
- **Audit log volume** increases slightly (one audit line per masked
  metadata read, in addition to the existing one per reveal) — negligible
  volume given these are low-frequency, human-triggered UI actions.
