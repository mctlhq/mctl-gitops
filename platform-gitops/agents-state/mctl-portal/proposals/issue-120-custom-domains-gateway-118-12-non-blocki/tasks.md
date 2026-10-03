# Tasks: issue-120-custom-domains-gateway-118-12-non-blocki

Findings are numbered as in issue #120. Commit boundaries: tasks 1-4 =
commit 1, 5-8 = commit 2, 9-11 = commit 3, 12-15 = commit 4.

- [ ] 1. (Finding 7) Drop `node-fetch` from
  `plugins/custom-domains-backend/src/mctlApiClient.ts`: delete
  `import fetch, { RequestInit } from 'node-fetch'` (line 1) and use the Node 22
  global `fetch` with the native `RequestInit` type. — DoD: no `node-fetch`
  reference remains in the file; `AbortSignal.timeout(DEFAULT_TIMEOUT_MS)`
  type-checks against the same `signal` type the request accepts;
  `yarn tsc` clean.
- [ ] 2. (Finding 7, depends on 1) Remove `node-fetch` from `dependencies` and
  `@types/node-fetch` from `devDependencies` in
  `plugins/custom-domains-backend/package.json`; refresh `yarn.lock`. — DoD:
  neither name appears in that package.json; the lockfile still resolves both
  for the five other plugins that use them; `yarn install --immutable` passes.
- [ ] 3. (Finding 3, depends on 1) Retype `request<T>` as
  `Promise<T | undefined>` and delete `return undefined as T` (line 200) in
  favour of `return undefined`. Add the `verify()` contract check: an
  `undefined`/non-object result throws
  `MctlApiError(502, 'mctl-api returned an empty body at ${path}')`, with an
  inline comment citing `handlers_domains.go` `verifyAndRespond`, which always
  ends in `writeJSON(w, http.StatusOK, result)`. Normalise `remove()`'s
  `undefined` to `{ status: 'deleted' }`. — DoD: `verify` and `remove` still
  return non-optional `VerifyResult`/`RemoveResult`; no `as T` cast anywhere in
  the file; `list()` and `create()` unchanged.
- [ ] 4. (depends on 3) Retarget `mctlApiClient.test.ts`'s transport mock from
  `jest.mock('node-fetch', () => jest.fn())` (line 4) to
  `jest.spyOn(globalThis, 'fetch')` in `beforeEach` with `mockRestore` in
  `afterEach`; update the "does not throw on a 204" case (line 265) from
  `resolves.toBeUndefined()` to the defined `{ status: 'deleted' }` shape. — DoD:
  the full existing suite passes unchanged in intent; no `jest.mock` of
  `node-fetch` remains in this file.
- [ ] 5. (Finding 4) Add a local `ClientLogger` structural type
  (`{ warn(msg: string): void; error(msg: string): void }`) and an optional
  `logger` to `MctlApiDomainsClient`'s constructor options, defaulting to a
  no-op. — DoD: every existing `new MctlApiDomainsClient({ baseUrl, token })`
  call site still compiles unchanged; no
  `@backstage/backend-plugin-api` import is added to `mctlApiClient.ts`.
- [ ] 6. (Finding 4, depends on 5) Wire it in
  `plugins/custom-domains-backend/src/plugin.ts` (line 62):
  `new MctlApiDomainsClient({ baseUrl, token, logger })` using the `logger` the
  init already receives. Log the discarded 5xx body at `error`
  (`mctl-api ${status} at ${path}: ${body}`) and add a distinct 401/403 hint
  naming `customDomains.token`. — DoD: an operator sees the upstream body in the
  backend log for a 500; the body still never reaches
  `MctlApiError.message`.
- [ ] 7. (Finding 5, depends on 5) Stop interpolating the caught network error
  into the thrown message (line 162): log it locally, throw
  `MctlApiError(502, 'mctl-api request failed at ${path}')`. — DoD: no thrown
  message from this branch can contain the resolved upstream host, the token, or
  the driver's `request to <url> failed` text.
- [ ] 8. (Findings 6 and 8) Replace the two speculative comments with verified
  statements: the 401/403 carve-out (lines 167-175) cites `handlers_domains.go`
  `AddDomain` rejecting `isPlatformDomain` with `http.StatusBadRequest` and
  `internal/auth/oidc.go` `HasTenantAccess` returning true for `IsAdmin()`, so
  no carve-out is needed; `router.ts`'s `domainBelongsToTeam` (lines 141-144)
  records that `internal/domains/store.go` `ListByTeam` has no `LIMIT`/`OFFSET`
  and names it as the symbol to re-check. — DoD: both comments state a verified
  fact with the file and symbol to re-verify, and neither says "assumes" or
  "could plausibly".
- [ ] 9. (Finding 9) Split the log level in `respondToDomainsError`
  (`router.ts` line 117): `logger.warn` for an `MctlApiError` with
  `status >= 400 && status < 500`, `logger.error` otherwise and for any
  non-`MctlApiError`. — DoD: a 409 on `POST /domains` produces exactly one
  `warn` and zero `error` log calls; a 502 still produces an `error`.
- [ ] 10. (Finding 11) Replace `service as string | undefined` (`router.ts`
  line 179) with an explicit guard: a present, non-string `service` answers 400
  before any upstream call. — DoD: no `as` cast of a request value remains in
  `router.ts`; `?service=a&service=b` answers 400 with no `domains.list` call.
- [ ] 11. (Finding 10) Correct the POST `/domains` body-validation comment
  (`router.ts` lines 189-198): the query-param routes are safe because of their
  own `typeof` checks (lines 162, 235, 284), not because Express 4.22.1's
  default `qs` parser guarantees a string — it returns an array for a repeated
  key. — DoD: the comment no longer claims a framework guarantee and explicitly
  marks the `typeof` guards as load-bearing.
- [ ] 12. (Finding 2) Create
  `packages/app/src/components/catalog/domainsCardLogic.ts` exporting
  `hasChallenge(d)` and
  `canVerifyDomain(d) = hasChallenge(d) || d.status === 'pending' || d.status === 'failed'`.
  — DoD: both are pure functions over a `Pick<CustomDomain, ...>` and import
  nothing from React or Backstage.
- [ ] 13. (Finding 1, depends on 12) Add
  `verifyMessageFrom(body: unknown): string | null` to the same module:
  returns `body.reason` (or a generic "DNS check has not passed yet" when
  `reason` is absent) when `body.verified === false`, `null` otherwise and for
  any non-object body. — DoD: matches mctl-api's
  `internal/domains/verify.go` `Result` shape (`verified`, `reason` omitempty).
- [ ] 14. (depends on 12, 13) Rewire
  `packages/app/src/components/catalog/EntityDomainsCard.tsx`: `handleVerify`
  (line 225) parses the 2xx body with `.catch(() => null)` and calls
  `setVerifyError(verifyMessageFrom(body))` before `fetchDomains()`; the row
  render (line 401) uses `canVerifyDomain(d)` for the Verify button and
  `hasChallenge(d)` for the Verification column. — DoD: a `verified:false`
  200 shows its reason in the existing `verifyError` `Typography` (line 339);
  a `verified:true` 200 clears it; a row with no challenge fields but status
  `pending`/`failed` shows the button and an em dash in the Verification cell.
- [ ] 15. (Finding 12) Add `POST /domains` (with a JSON body) and
  `POST /domains/:id/verify` rows to the `rejectingDb` `it.each` table in
  `router.test.ts` (line 569). — DoD: the table has four rows; all four assert
  500 and that no `domains.*` mock was called.
- [ ] 16. File a follow-up issue for the repo-wide `node-fetch@2` to global
  `fetch` migration of the remaining five plugins. — DoD: issue exists and links
  back to #120 finding 7.

## Tests

- [ ] T1. `mctlApiClient.test.ts`: `verify()` on a 200 with an empty body
  rejects with `MctlApiError` status 502 (pins finding 3's contract check).
- [ ] T2. `mctlApiClient.test.ts`: `verify()` on a 200 with
  `{verified:false, reason:'...', expected_record, expected_value}` resolves to
  that exact object, unchanged.
- [ ] T3. `mctlApiClient.test.ts`: `remove()` on a 204 with an empty body
  resolves to a defined object with a `status` field (replaces the current
  `toBeUndefined` assertion).
- [ ] T4. `mctlApiClient.test.ts`: a network rejection whose message is
  `request to https://api.mctl.ai/api/v1/domains failed, reason: ECONNREFUSED`
  produces an `MctlApiError` whose `message` contains neither `api.mctl.ai` nor
  `ECONNREFUSED` (pins finding 5).
- [ ] T5. `mctlApiClient.test.ts`: a 500 with body
  `Traceback: internal db connection string` calls the injected logger's
  `error` with the body, while the thrown message still does not contain it
  (pins finding 4 without regressing #118's leak fix).
- [ ] T6. `mctlApiClient.test.ts`: a 400 platform-domain rejection body from
  mctl-api is forwarded as status 400 with the body in the message (pins
  finding 6's verified conclusion).
- [ ] T7. `mctlApiClient.test.ts`: the whole suite runs against
  `jest.spyOn(globalThis, 'fetch')` with no `node-fetch` mock (pins finding 7).
- [ ] T8. `router.test.ts`: an upstream 409 on `POST /domains` calls
  `logger.warn` once and `logger.error` zero times; an upstream 502 on
  `GET /domains` calls `logger.error` (pins finding 9). The existing `noopLogger`
  (line 150) already carries both jest mocks.
- [ ] T9. `router.test.ts`: `GET /domains?team=acme&service=a&service=b`
  answers 400 with no `domains.list` call (pins finding 10/11).
- [ ] T10. `router.test.ts`: the four-row `rejectingDb` `it.each` all answer 500
  (pins finding 12).
- [ ] T11. `domainsCardLogic.test.ts`: `canVerifyDomain` is true for a `pending`
  row with no challenge fields, true for a `failed` row **with** both challenge
  fields populated (the fixture finding 2 asks for), true for an unknown status
  carrying both fields, and false for an `active` row with neither.
- [ ] T12. `domainsCardLogic.test.ts`: `verifyMessageFrom` returns the `reason`
  for `{verified:false, reason:'no TXT record ...'}`, a non-empty generic string
  for `{verified:false}`, and `null` for `{verified:true}`, `null`, `undefined`,
  and a string body.
- [ ] T13. `yarn tsc` and `yarn lint` clean across the repo (guards the
  `node-fetch` removal and the `Promise<T | undefined>` retype).
- [ ] T14. The existing `gateway migration guard` suite (`router.test.ts`
  line 588) still passes — no `dns` import, no `custom_domains` string in the
  plugin's non-test sources.

## Rollback

Every change is source-level in one plugin plus one frontend module; there is no
schema, GitOps manifest, or `app-config` change to unwind.

1. Full rollback: revert the merge commit and redeploy. The plugin returns to
   #118's behaviour exactly, including `node-fetch@2` (still in the lockfile for
   five other plugins, so no `yarn install` churn).
2. Partial rollback: the commits are independent. Revert commit 4 alone to
   restore the previous card behaviour while keeping the backend fixes; revert
   commit 1 alone to restore `node-fetch` (commits 2 and 3 do not depend on the
   transport).
3. Monitoring after deploy: watch the backend logs for a rise in `warn`-level
   `custom-domains` entries — that is the finding-9 level change, expected, not a
   regression. A rise in 502s on `POST /domains/:id/verify` would mean mctl-api
   is answering verify with an empty body, contradicting the verified contract
   in task 3; in that case revert commit 1 and reopen finding 3.
