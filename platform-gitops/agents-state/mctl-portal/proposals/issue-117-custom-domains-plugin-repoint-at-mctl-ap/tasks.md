# Tasks: issue-117-custom-domains-plugin-repoint-at-mctl-ap

- [ ] 1. Confirm the direction before writing code: read mctl-api's
      `internal/domains` (repo `mctlhq/mctl-api`, PR #264) and record, in the PR
      description, the exact request/response shape of `GET /api/v1/domains`, the
      create endpoint, the verify endpoint, and the delete endpoint — field
      names, status vocabulary, the identifier used in per-domain paths (id vs
      domain), the TXT challenge field names, and how it authenticates a
      portal-originating call. If the answer is that domains are meant to stay
      API/MCP-only, stop and switch to the option-2 fallback in task 12 instead.
      — DoD: a written schema note in the PR body that tasks 2 and 7 can be
      implemented against without further guessing.

- [ ] 2. Add `plugins/custom-domains-backend/src/mctlApiClient.ts` (depends on 1)
      — a `DomainsClient` interface (`list`, `create`, `verify`, `remove`) and a
      `MctlApiDomainsClient` implementing it, modelled on
      `plugins/argo-workflows-backend/src/argoClient.ts`: `node-fetch`,
      constructor `{ baseUrl, token }` with `baseUrl.replace(/\/$/, '')`, private
      `headers()` attaching `Authorization: Bearer`, private `request<T>()`
      throwing a typed `MctlApiError { status, message }` on non-2xx, and an
      explicit request timeout. Export a pure `toPortalDomain(raw)` that maps a
      registry record to the card's `CustomDomain` shape plus
      `challenge_record_name` / `challenge_record_value`. — DoD: file compiles
      under `strict: true`; the token never appears in a log line or a thrown
      message; every mctl-api field assumption lives in `toPortalDomain`.

- [ ] 3. Rewrite `plugins/custom-domains-backend/src/router.ts` to use the client
      (depends on 2) — replace `RouterOptions.store: CustomDomainStore` with
      `domains: DomainsClient`; keep `db` and `isPostgres` (still needed by
      `authorizeForTeam` for the `tenant_members` lookup). Delete `verifyDns()`,
      the `dns`/`util` imports, `isValidCustomDomain()`, the hardcoded
      `` `${team}-${service}.mctl.ai` `` auto-domain, and the
      `store.getByDomain` uniqueness pre-check — mctl-api owns validation,
      uniqueness, and the auto-domain now. Keep every handler's
      resolve-caller-then-authorize-then-act ordering unchanged. Map
      `MctlApiError` to its upstream status for 4xx and to 502 for 5xx/network
      failures. — DoD: no `dns` import remains; no route reads or writes
      `custom_domains`; a 401/403 still short-circuits before any upstream call.

- [ ] 4. Turn `POST /domains/:id/activate` into a `410 Gone` (depends on 3) with
      a body pointing at mctl-api as the owner of activation. Keep the route
      registered rather than deleting it, so a stale caller gets a diagnosable
      answer instead of a 404. Leave `isWorkflowCaller` and
      `WORKFLOW_CALLER_SUBJECTS` in place for now. — DoD: the route returns 410
      for both user and workflow callers and mutates nothing.

- [ ] 5. Update `plugins/custom-domains-backend/src/plugin.ts` (depends on 2) —
      drop the `CustomDomainStore` construction and `await store.initialize()`
      so the plugin stops creating the `custom_domains` table; add
      `coreServices.rootConfig`; read `customDomains.baseUrl` (default
      `https://api.mctl.ai`) and `customDomains.token`; construct
      `MctlApiDomainsClient` and pass it to `createRouter`. Throw at init if the
      base URL resolves to empty. Do not touch `registerAuthPolicies()`. — DoD:
      backend boots with the config present; boots-and-throws with an explicitly
      empty base URL; `plugin.test.ts` passes unmodified.

- [ ] 6. Delete `plugins/custom-domains-backend/src/store.ts` (depends on 5) and
      any now-dead imports. Do NOT drop the `custom_domains` table — leave it in
      place, unread, so the change is revertible by code alone. — DoD: no
      reference to `CustomDomainStore` remains; `yarn tsc` is clean.

- [ ] 7. Update `packages/app/src/components/catalog/EntityDomainsCard.tsx`
      (depends on 2) — keep `discoveryApi.getBaseUrl('custom-domains')` and all
      four route URLs unchanged. Extend the `CustomDomain` interface with the
      challenge fields; render the TXT challenge name/value returned on create in
      the "Add Domain" dialog alongside the existing CNAME instruction, with the
      existing `handleCopy` affordance; add a verification cell for pending rows;
      widen `statusConfig` to mctl-api's status vocabulary with a neutral
      fallback chip for an unknown status instead of defaulting to "Pending DNS";
      replace the silent `catch {}` blocks in `handleVerify` and `handleDelete`
      with the same visible error surface `fetchDomains` uses. — DoD: a pending
      domain shows the exact TXT record to create; a failed verify or delete
      shows an error rather than appearing to succeed.

- [ ] 8. Add config (depends on 5) — `customDomains.baseUrl` / `customDomains.token`
      to `app-config.yaml` (localhost default, token commented) and to
      `app-config.production.yaml` as `${MCTL_API_URL}` / `${MCTL_API_TOKEN}`;
      add both to `.env.example`, and while there add the currently-missing
      `BACKSTAGE_TOKEN`. — DoD: a fresh checkout following `.env.example` can
      boot the backend and load the Domains tab against a reachable mctl-api.

- [ ] 9. Verify whether `mctl-gitops`'s `wft-add-custom-domain.yaml` still calls
      the portal's `/api/custom-domains/domains/:id/activate` after
      `mctl-gitops#1085` (depends on 4). If it no longer does: delete
      `isWorkflowCaller`, `WORKFLOW_CALLER_SUBJECTS`, their tests, and the
      `backend.auth.externalAccess` block in `app-config.production.yaml`, and
      note the `BACKSTAGE_TOKEN` retirement in the PR body. If it still does:
      leave all of it and file a follow-up issue against mctl-gitops. — DoD: the
      PR states which branch was taken and cites the workflow file that was read.

- [ ] 10. Update docs (depends on 7) — `README.md:97`'s plugin-table row and
      `CLAUDE.md`'s plugin list to describe `custom-domains-backend` as a gateway
      to mctl-api's registry rather than a store; correct the stale
      "custom domains unusable" comment block in `app-config.production.yaml`
      (lines 15-26) to reflect the new call direction. — DoD: no doc still
      describes the portal as the system of record for custom domains.

- [ ] 11. Manual verification against a real environment (depends on 7, 8) —
      register a domain for a test team via the portal card, confirm it appears
      in `mctl_list_domains` / `GET /api/v1/domains` for that team, confirm the
      TXT record shown matches what mctl-api expects, complete verification, and
      confirm the card reflects the status change. Then confirm a domain created
      out-of-band via MCP appears in the card. — DoD: both directions observed;
      screenshots or transcript in the PR.

- [ ] 12. Fallback, only if task 1 concludes domains stay API/MCP-only: delete
      `EntityDomainsCard.tsx`, the `/domains` route at `EntityPage.tsx:189`, the
      `custom-domains` plugin directory, its `backend.add(...)` line in
      `packages/backend/src/index.ts`, and the `externalAccess` block, and record
      the decision in `CHANGELOG.md`. — DoD: mutually exclusive with tasks 2-11;
      the PR body states which path was taken and why.

## Tests

- [ ] T1. Port the existing `router.test.ts` gating suite from the `store` mock
      to the `domains` client mock. The harness already injects the data layer as
      a plain object of jest mocks through `RouterOptions`
      (`startApp({ store: ... })`), so this is a rename plus renaming the asserted
      call. All of T1-T5 must still hold: member lists 200, non-member 403 with
      no upstream call, anonymous 401 with no upstream call, `admins`-tenant
      owner bypass 200, non-member POST 403 with no upstream call.
- [ ] T2. `plugin.test.ts` passes unmodified — `/health` is the only
      unauthenticated policy and no `/domains*` unauthenticated policy is
      reintroduced.
- [ ] T3. New `mctlApiClient.test.ts`: `toPortalDomain()` maps a recorded
      mctl-api payload (captured in task 1) to the card's shape, including both
      challenge fields, and tolerates a missing optional field without throwing.
- [ ] T4. `mctlApiClient.test.ts`: `request()` error mapping — mock `node-fetch`
      at module level (`jest.mock('node-fetch', () => jest.fn())`, the pattern
      used in `plugins/vault-secrets-backend/src/router.test.ts`) and assert a
      409 upstream surfaces as a 409-bearing `MctlApiError`, a 500 upstream and a
      thrown network error both surface as retryable/502-class, and the bearer
      token appears in no thrown message.
- [ ] T5. Router test: an upstream 5xx or network failure on `GET /domains`
      yields a 502 with a readable message, not a 200 with an empty `domains`
      array — this is the regression that would otherwise read to a user as
      "you have no domains".
- [ ] T6. Router test: an upstream 409 on `POST /domains` reaches the caller as
      409 with mctl-api's message, not a generic 500.
- [ ] T7. Router test: `POST /domains/:id/activate` returns 410 and calls no
      client method, for both a user caller and a workflow-subject caller.
- [ ] T8. Grep-style guard test (or a lint assertion in CI): the plugin source
      contains no `from 'dns'` import and no reference to `custom_domains`,
      pinning that verification and storage have genuinely left the portal.
- [ ] T9. Optional, and the first of its kind in this repo: a component test for
      `EntityDomainsCard` using `@backstage/test-utils` `TestApiProvider` to stub
      `discoveryApiRef`/`fetchApiRef`, asserting the TXT challenge renders and
      that a failing verify surfaces an error. `@backstage/test-utils` is already
      a devDependency of `packages/app` but currently unused, and
      `App.test.tsx` is the only `.test.tsx` there — so budget for setup friction,
      and drop this test rather than block the PR on it.

## Rollback

The change is code-only and carries no schema migration, so rollback is a plain
revert of the PR and a redeploy of the previous portal image tag
(`mctl_rollback_service team=<team> component_name=mctl-portal target_tag=<prev>`).

Reverting restores `store.ts` and the `store.initialize()` call, which recreates
the `custom_domains` table on next boot if it was ever removed out-of-band —
which is precisely why task 6 leaves the table physically in place and why no
`DROP TABLE` appears anywhere in this proposal. The table's contents are empty
per the issue, so nothing is lost either way and the old CNAME-based flow returns
exactly as it was.

If task 9 removed the `externalAccess` block and something turns out to still
depend on it, that block is restored by the same revert; the Vault-held
`BACKSTAGE_TOKEN` should not be rotated or deleted until this change has been
stable in production for at least one release.

Partial rollback is also available without a revert: pointing
`customDomains.baseUrl` at an unreachable address degrades the Domains tab to a
visible error state while leaving the rest of the portal untouched, which is the
safe failure mode to reach for if mctl-api itself is the thing misbehaving.
