# Tasks: issue-82-vault-secrets-stop-returning-plaintext-p

- [ ] 1. Add a `developer` tier to `vault-secrets-backend`'s role check —
      replace the `viewer`/`owner`-only comparison in `checkTenantRole`
      (`plugins/vault-secrets-backend/src/router.ts:243-263`) with a
      `ROLE_RANK`-based `meetsMinimumRole(role, minimumRole)` helper, and
      widen `minimumRole`'s type to `'viewer' | 'developer' | 'owner'`. —
      DoD: existing `checkTenantRole` unit tests in `router.test.ts` still
      pass unmodified (behavior-preserving for `viewer`/`owner` minimums),
      plus new tests assert a `developer`-role member passes a `developer`
      minimum and a `viewer`-role member fails it.

- [ ] 2. Split `/database` into masked base + `/database/reveal`, and
      `/secrets` into masked base + `/secrets/reveal` (depends on 1) —
      `plugins/vault-secrets-backend/src/router.ts:80-124`. Base routes keep
      `minimumRole: 'viewer'` and drop `password`/`secrets` values (add
      `hasPassword: boolean` / return `secretKeys: string[]`). New `/reveal`
      routes require `minimumRole: 'developer'` and return today's full
      plaintext shape. — DoD: a `viewer`-role request to either base route
      returns 200 with no plaintext secret value in the body; a
      `developer`-role request to either `/reveal` route returns 200 with
      the plaintext value; a `viewer`-role request to either `/reveal` route
      returns 403 with no secret value in the body.

- [ ] 3. Extend `auditSecretRead`'s `kind` parameter to
      `'database' | 'database-meta' | 'secrets' | 'secrets-meta'` and call
      it from all four routes in task 2 with the appropriate kind (depends
      on 2) — `plugins/vault-secrets-backend/src/router.ts:52-71`. — DoD:
      every one of the four routes logs exactly one audit line per request,
      with a `kind` that distinguishes a metadata read from a plaintext
      reveal; existing `auditSecretRead` tests continue to pass.

- [ ] 4. Update `EntityDatabaseCard.tsx` (depends on 2) — `handleLoad` fetches
      the masked `/database` route only; add a per-field lazy "Reveal" fetch
      to `/database/reveal` for the password row that stores the plaintext
      in field-scoped state and clears it on "Hide"; surface a 403 as an
      inline "Developer or owner role required" message. —
      `packages/app/src/components/catalog/EntityDatabaseCard.tsx`. — DoD:
      loading a database card never issues a request to `/reveal`; clicking
      "Reveal" on the password row issues exactly one `/reveal` request and
      displays the plaintext; clicking "Hide" clears the plaintext from
      component state (verified via a test asserting the value is gone from
      the rendered output and from state, not just visually masked).

- [ ] 5. Update `CurrentConfigField.tsx` (depends on 2) — switch the Vault
      fetch to read `secretKeys` from the masked `/secrets` response; drop
      the `secrets: Record<string,string>` field from the `ServiceConfig`
      type and all references to it. —
      `packages/app/src/components/scaffolder/CurrentConfigField.tsx`. —
      DoD: no code path in this file references plaintext secret values;
      the chip-rendering branch that already handles `secretKeys` becomes
      the only branch exercised.

- [ ] 6. Update `SecureVarsEditorField.tsx` (depends on 5) — remove the
      auto-fill effect that pre-populates the field with
      `KEY=plaintextValue` lines from `currentConfig.secrets`; add a
      read-only hint listing `currentConfig.secretKeys` with no values;
      leave the field's `formData` empty by default for a service with
      existing secrets. —
      `packages/app/src/components/scaffolder/SecureVarsEditorField.tsx`. —
      DoD: mounting the field for a service with existing secrets renders no
      plaintext value anywhere in the DOM or in `formData`/`onChange` calls;
      the existing-keys hint is visible; submitting without editing the
      field produces an empty/undefined field value.

- [ ] 7. Verify (or explicitly flag for a follow-up) how the `deploy-service`
      / `update-config` Argo WorkflowTemplate interprets an empty or
      key-omitted `secret_env_vars` parameter — confirm it leaves existing
      Vault secrets untouched rather than clearing them (depends on 6, but
      can be investigated in parallel). This may require reading
      `mctl-gitops` WorkflowTemplate definitions, which are outside this
      repo. — DoD: either a confirmed "omitted keys are left alone" finding
      is recorded in the PR description, or a corrective follow-up
      issue/task is filed against the WorkflowTemplate/mctl-api before this
      change is considered fully safe to merge.

## Tests

- [ ] T1. `checkTenantRole`/`meetsMinimumRole`: `developer` passes a
      `developer` minimum; `viewer` fails a `developer` minimum; `owner`
      passes every minimum; admin bypass still resolves to `owner` rank
      regardless of minimum (extends the existing "admin bypass" describe
      block in `router.test.ts`).
- [ ] T2. `GET /teams/:team/:app/database`: `viewer` gets 200 with no
      `password` key present in the JSON body and `hasPassword: true/false`
      set correctly; response still includes host/port/database/username.
- [ ] T3. `GET /teams/:team/:app/database/reveal`: `developer` gets 200 with
      plaintext `password`; `viewer` gets 403 with no secret value in the
      body; a matching audit log line is emitted with `kind: 'database'`.
- [ ] T4. `GET /teams/:team/:app/secrets`: `viewer` gets 200 with
      `secretKeys` array and no `secrets` values in the body.
- [ ] T5. `GET /teams/:team/:app/secrets/reveal`: `developer` gets 200 with
      plaintext `secrets` map; `viewer` gets 403.
- [ ] T6. `auditSecretRead` emits the correct `kind` for each of the four
      routes, including the no-secrets-configured (`undefined`/`{}`) case
      for both the meta and reveal variants of `/secrets`.
- [ ] T7. `EntityDatabaseCard`: loading the card issues no request to
      `/reveal`; clicking "Reveal" on the password field fetches and
      displays the plaintext; clicking "Hide" removes the plaintext from
      rendered output and does not re-display it without a fresh fetch; a
      403 from `/reveal` renders the role-required message and no secret
      value.
- [ ] T8. `CurrentConfigField`: with a mocked masked `/secrets` response
      (`secretKeys` only), the pushed `formContext` config JSON contains no
      plaintext secret values.
- [ ] T9. `SecureVarsEditorField`: given `currentConfig.secretKeys` with
      existing keys and no `secrets`, the field mounts empty, shows the
      existing-key hint, and `onChange` is not called with any pre-filled
      plaintext; typing a new `KEY=value` line and submitting sends exactly
      that line.

## Rollback
All changes are confined to `vault-secrets-backend` (routes + audit helper)
and three frontend components in `mctl-portal`; there are no database
migrations and no changes to Vault's stored data or ACL policies. Rollback is
a plain revert of the merged commit(s)/PR and a redeploy — the previous
build's routes and components come back immediately. Because the base
`/database` and `/secrets` GET routes are gated at the same `viewer` minimum
before and after this change, a rollback does not require any coordinated
change to `tenant_members` roles or to the `deploy-service` workflow. If
task 7's follow-up (WorkflowTemplate `secret_env_vars` semantics) is still
open when this ships, treat that specifically as the first thing to check if
a team reports secrets disappearing after a config edit — reverting the
`SecureVarsEditorField` change (task 6) alone is sufficient to restore the
old (pre-fill) behavior without touching the backend role/masking changes.
