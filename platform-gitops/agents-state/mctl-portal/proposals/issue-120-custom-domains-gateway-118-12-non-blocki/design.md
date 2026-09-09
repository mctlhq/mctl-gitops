# Design: issue-120-custom-domains-gateway-118-12-non-blocki

## Current state

The `custom-domains` plugin is a gateway with no local store. Four files carry
all twelve findings.

`plugins/custom-domains-backend/src/mctlApiClient.ts` (245 lines) imports
`fetch, { RequestInit }` from `node-fetch` (line 1) while calling the native
`AbortSignal.timeout(DEFAULT_TIMEOUT_MS)` (line 154) — the exact mixing of
`@types/node-fetch`'s `AbortSignal` with the global one that finding 7 names.
Its private `request<T>(path, options): Promise<T>` (line 144) does three
things the findings target:

- On a network throw it builds `mctl-api request failed at ${path}: ${message}`
  (line 162) where `message` is node-fetch's own text, which embeds the fully
  resolved URL (`request to https://api.mctl.ai/... failed, reason: ...`).
  `router.ts`'s `respondToDomainsError` forwards `MctlApiError.message` verbatim
  to the browser (line 120), so this branch leaks the upstream host — the same
  class of leak the 5xx branch (line 190) and the 401/403 carve-out (line 176)
  were changed to close. Finding 5.
- On a 5xx it reads the body (line 166) and deliberately drops it (line 190).
  Correct for the response, but the client holds no logger, so the body is
  discarded entirely and an operator sees only `mctl-api upstream error 500 at
  /api/v1/domains`. Finding 4.
- On a successful empty body it does `return undefined as T` (line 200). `list()`
  survives it via `data?.domains ?? []` (line 215) — the fix #118 shipped — but
  `verify()` (line 230) and `remove()` (line 238) declare non-optional
  `VerifyResult`/`RemoveResult` and would hand `undefined` to
  `res.json(result)`. Findings 3.

Two comments in the same file assert upstream behaviour that #118 could not
verify: the 401/403 carve-out's premise (lines 167-175, finding 6), and
`router.ts`'s `domainBelongsToTeam` (lines 141-144) assuming
`GET /api/v1/domains?team=` is complete and unpaginated (finding 8). Both were
checked against `mctlhq/mctl-api` at HEAD (2026-09-09) while writing this
design:

- `internal/api/handlers_domains.go` `AddDomain` rejects a reserved hostname
  with `writeError(w, http.StatusBadRequest, platformDomainRejection(...))` —
  a 400, not a 403. So the carve-out's premise holds and no exception is
  needed. The only 403 in that handler is `access denied to team` guarded by
  `user.HasTenantAccess(team)`, and `internal/auth/oidc.go`'s
  `HasTenantAccess` returns true unconditionally for `u.IsAdmin()`. This
  plugin's token is an admin-tier service credential (documented on
  `DomainsClient.verify`), so that 403 is reachable only when
  `customDomains.token` is misconfigured — precisely the case the 502 mapping
  exists for. Finding 6 resolves to "confirm and document", not "carve out".
- `internal/domains/store.go` `ListByTeam` builds
  `SELECT ... FROM custom_domains WHERE lower(team)=lower($1) [AND
  lower(service)=lower($2)] ORDER BY created_at DESC` with no `LIMIT` or
  `OFFSET`, and `ListDomains` in the handler maps the whole slice into
  `{"domains": [...]}`. Unpaginated today. Finding 8 resolves to "document the
  assumption and name the symbol to re-check", not "switch to a per-domain
  lookup" — mctl-api exposes no id-addressable GET at all (`resolveDomainForMutation`
  serves only verify and delete).

`plugins/custom-domains-backend/src/router.ts` (317 lines):
`respondToDomainsError` (line 117) logs everything at `logger.error`, including
a 409 caused by a user typing a domain someone already registered (finding 9).
The POST body-validation comment (lines 189-198) claims Express's query parser
"already guarantees a string or undefined"; with Express pinned at 4.22.1
(`yarn.lock` line 17984) and its default `extended`/`qs` parser,
`?team=a&team=b` yields an array — the query routes are safe only because of
their own `typeof team !== 'string'` checks at lines 162, 235, 284 (finding 10).
`service` is passed through as `service as string | undefined` (line 179), the
one value in the file that is cast rather than checked (finding 11).

`packages/app/src/components/catalog/EntityDomainsCard.tsx` (552 lines):
`handleVerify` (line 225) handles only `!resp.ok` and otherwise calls
`fetchDomains()`. mctl-api's `verifyAndRespond` always ends in
`writeJSON(w, http.StatusOK, result)` and its verifier returns
`Result{Verified:false, Reason:"no TXT record %s with value %q, and no CNAME to
%s"}` rather than an error when DNS has not propagated — so the common case is a
200 whose `reason` this card throws away (finding 1). `canVerify` (line 401) is
`Boolean(d.challenge_record_name && d.challenge_record_value)`, gating both the
Verification column and the Verify button on two `omitempty` fields (finding 2).

`plugins/custom-domains-backend/src/router.test.ts` (606 lines): the
`rejectingDb` `it.each` at line 569 has rows for `GET /domains` and
`DELETE /domains/:id` only, though `POST /domains` (line 212) and
`POST /domains/:id/verify` (line 244) `await authorizeForTeam` identically
outside any try (finding 12). `mctlApiClient.test.ts` mocks the transport with
`jest.mock('node-fetch', () => jest.fn())` (line 4). There is no test file for
`EntityDomainsCard.tsx`; `packages/app/package.json` already carries
`@testing-library/react` ^14 and `@testing-library/jest-dom` ^6.

## Proposed solution

One PR, four commits, no behavioural change to any route's status codes except
the two the findings ask for (a 400 on a non-string `service`, and a 502 on an
empty verify body). Ordered so each commit is independently revertable.

**Commit 1 — client transport and types.**
Delete the `node-fetch` import and use the Node 22 global `fetch`, typing
`options` as the native `RequestInit` from `undici-types`/lib.dom as exposed by
`@types/node` (finding 7). Drop `node-fetch` and `@types/node-fetch` from
`plugins/custom-domains-backend/package.json`; the plugin keeps `express`,
`express-promise-router`, and `knex`. Retype `request<T>` as
`Promise<T | undefined>` and delete `undefined as T` (finding 3). `list()` is
unchanged (`data?.domains ?? []` already handles it). `create()` passes
`undefined` into `toPortalDomain`, which already tolerates it (its
`(raw ?? {})` guard, pinned by an existing test). `verify()` gains an explicit
contract check — an `undefined` or non-object result becomes
`MctlApiError(502, 'mctl-api returned an empty body at ${path}')`, justified
inline by mctl-api's `verifyAndRespond` always writing JSON. `remove()`
normalises `undefined` to `{ status: 'deleted' }` so a 204 stays a success
(the existing "does not throw on a 204" test is updated from
`resolves.toBeUndefined()` to the defined shape) and the router never answers
`200` with an empty body. `mctlApiClient.test.ts` swaps
`jest.mock('node-fetch')` for `jest.spyOn(globalThis, 'fetch')` in a
`beforeEach`, restored in `afterEach`.

**Commit 2 — client logging and error hygiene.**
Add an optional `logger?: ClientLogger` to `MctlApiDomainsClient`'s constructor
options, where `ClientLogger` is a local structural type
`{ warn(msg: string): void; error(msg: string): void }` — satisfied by
Backstage's `LoggerService` without importing `@backstage/backend-plugin-api`
into the client, and defaulting to a no-op object so every existing
construction site and test still compiles (finding 4). `plugin.ts` passes the
`logger` it already receives from `coreServices.logger` (line 50) into
`new MctlApiDomainsClient({ baseUrl, token, logger })`. The 5xx branch logs
`mctl-api ${status} at ${path}: ${body}` at `error` before throwing the
body-free `MctlApiError`; the 401/403 branch logs a distinct
"check customDomains.token" hint. The network branch logs the raw driver
message locally and throws `MctlApiError(502, 'mctl-api request failed at
${path}')` with no interpolated driver text, closing the URL leak (finding 5).
The carve-out comment is rewritten from a stated assumption into a verified
statement citing `handlers_domains.go` `AddDomain` and `internal/auth/oidc.go`
`HasTenantAccess` (finding 6), and `domainBelongsToTeam`'s comment gains the
verified `ListByTeam`-is-unpaginated note naming the symbol to re-check
(finding 8).

**Commit 3 — router.**
`respondToDomainsError` gains a level split: `err.status >= 400 && < 500` logs
via `logger.warn`, everything else via `logger.error` (finding 9). `GET /domains`
gets `if (service !== undefined && typeof service !== 'string')` → 400 before
the upstream call, and the cast disappears (finding 11). The POST body comment
is corrected to say the query-param routes are safe because of their own
`typeof` guards, not because of any framework guarantee, with the Express 4.22.1
`qs` array behaviour named explicitly so the guards read as load-bearing
(finding 10).

**Commit 4 — frontend and tests.**
The two pieces of card logic the findings target are pure, and the card has no
test harness today (mocking `useEntity`, `useApi`, `discoveryApiRef`,
`fetchApiRef`, and `usePlatformConfig` for a render test is a disproportionate
lift for two predicates). Extract them into a new
`packages/app/src/components/catalog/domainsCardLogic.ts`:

- `canVerifyDomain(d: Pick<CustomDomain,'status'|'challenge_record_name'|'challenge_record_value'>): boolean`
  returning `hasChallenge(d) || d.status === 'pending' || d.status === 'failed'`
  (finding 2). The card keeps a separate `hasChallenge` for the Verification
  column, so a row with no challenge fields still renders the em dash while its
  Verify button appears — the two concerns the single `canVerify` conflated.
- `verifyMessageFrom(body: unknown): string | null` returning `body.reason` when
  `body.verified === false` (falling back to a generic "DNS check has not passed
  yet" when `reason` is absent), and `null` otherwise, including for an
  unparseable body (finding 1).

`handleVerify` becomes: on `!resp.ok`, unchanged; on ok, `await resp.json()`
guarded by `.catch(() => null)`, feed through `verifyMessageFrom`, and
`setVerifyError(msg)` when non-null before `fetchDomains()`. The existing
`verifyError` `Typography` (line 339) renders it with no markup change.
`domainsCardLogic.test.ts` covers both helpers including the `failed`-with-
challenge-fields fixture the issue asks for. `router.test.ts`'s `rejectingDb`
table gains the two missing rows, with a `body` field on the `POST /domains` row
(finding 12).

## Alternatives

**Render-test the card with `@testing-library/react` instead of extracting
helpers.** The deps exist and it would exercise `handleVerify` end to end.
Dropped: it needs mocks for five hooks/APIs and would be the first component
test in `packages/app` besides `App.test.tsx`, making commit 4 the largest and
riskiest part of a P3 cleanup. The extraction keeps the tested logic pure and
leaves the door open to add a render test later without rework.

**Migrate all six plugins off `node-fetch@2` in one sweep.** `node-fetch` is
the repo-wide convention (`argo-workflows-backend`, `github-app-connect-backend`,
`proposals-backend`, `tenant-backend`, `vault-secrets-backend`), so fixing only
this plugin creates a local inconsistency. Dropped: a six-plugin transport swap
is a change of a different size and blast radius than a P3 batch, and each of
those plugins has its own `jest.mock('node-fetch')` test surface. Finding 7 is
scoped to this file because it is this file that mixes the two `AbortSignal`
types. Filing the sweep as a follow-up issue is part of the task list.

**Thread `LoggerService` into the client instead of a structural
`{warn, error}`.** More conventional for a Backstage backend plugin. Dropped:
it drags `@backstage/backend-plugin-api` into a module that is otherwise a plain
HTTP client and forces every one of the ~15 `new MctlApiDomainsClient` /
constructor uses in `mctlApiClient.test.ts` to supply a five-method logger stub.
The structural type is satisfied by `LoggerService` at the one real call site in
`plugin.ts`, so nothing is lost.

**Switch `domainBelongsToTeam` to a per-domain lookup (finding 8's second
option).** Dropped as impossible without an mctl-api change: `handlers_domains.go`
exposes no `GET /api/v1/domains/{id}`; `resolveDomainForMutation` is reachable
only through verify and delete, and calling either as a probe has side effects.

## Platform impact

- **Migrations:** none. No schema, no GitOps manifest, no `app-config` key
  changes. `customDomains.baseUrl`/`token` are untouched.
- **Backward compatibility:** all route paths, methods, and success shapes are
  unchanged. Three observable deltas, all intended: `GET /domains` with a
  repeated `?service=` now answers 400 instead of forwarding the first value
  (no known caller — the card sends exactly one, line 175); `verify` on an
  empty upstream body now answers 502 instead of 200-with-empty-body
  (unreachable per mctl-api's handler, which is the point of the check); and
  4xx now appears at `warn` in the backend logs, which any log-level-based
  alert on this plugin must account for.
- **Dependency impact:** `node-fetch` and `@types/node-fetch` leave
  `plugins/custom-domains-backend/package.json` only; they stay in the lockfile
  because five other plugins depend on them. No new dependency is added.
- **Resource impact:** none. Same request count, same 10s timeout.
- **Risks and mitigations:**
  - *Global-`fetch` behaviour differs from node-fetch@2 in error text, header
    casing, and body handling.* The client only reads `resp.ok`, `resp.status`,
    and `resp.text()`, all identical across both. Mitigated by the existing
    `mctlApiClient.test.ts` suite, which is retargeted rather than rewritten,
    plus new cases for the empty-verify-body and no-URL-in-message contracts.
  - *`AbortSignal.timeout()` type friction moves rather than disappears.* With
    node-fetch gone, `signal` is the native one on both sides — the mismatch is
    removed at the source, and `yarn tsc` in CI is the check.
  - *Logging the 5xx body could itself log something sensitive.* It goes to the
    backend log only, never to a response; a new test asserts the body still
    does not appear in `MctlApiError.message`, keeping #118's fix pinned.
  - *Widening `canVerify` shows a Verify button on a row with no challenge
    record.* Intended: clicking it calls mctl-api, which re-derives the expected
    record and returns it in `expected_record`/`expected_value`. The Verification
    column still shows an em dash, so nothing is fabricated in the UI.
