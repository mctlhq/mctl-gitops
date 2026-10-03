# Design: issue-117-custom-domains-plugin-repoint-at-mctl-ap

## Current state

The portal owns a complete, self-contained custom-domains implementation whose
storage is the Backstage database. Four pieces make it up.

**Storage.** `plugins/custom-domains-backend/src/store.ts` defines
`CustomDomainStore` over knex. `initialize()` creates a `custom_domains` table
(columns `id`, `team`, `service`, `domain`, `auto_domain`, `status` enum
`pending|verified|active|failed`, `verified_at`, `created_by`, timestamps, index
on `[team, service]`) and the class exposes `list`, `getByDomain`, `getById`,
`create`, `updateStatus`, `delete`, `deleteByDomain`.

**Routes.** `plugins/custom-domains-backend/src/router.ts` exposes, under the
plugin id `custom-domains` (so `/api/custom-domains/...`):

- `GET /domains?team=&service=` — lists from the store.
- `POST /domains` — validates the FQDN with `isValidCustomDomain()` (rejects
  `*.mctl.ai` / `*.mctl.me`), checks uniqueness via `store.getByDomain`, mints a
  `crypto.randomUUID()` id, computes `auto_domain` as the hardcoded
  `` `${team}-${service}.mctl.ai` ``, inserts with `created_by` forced to the
  authenticated caller, and returns CNAME instructions.
- `POST /domains/:id/verify` — `verifyDns()` calls Node's `dns.resolve` (aliased
  `resolveCname`) and flips the row to `verified` if the CNAME matches
  `auto_domain`. This is exactly the `dig CNAME` mechanism the migration
  replaced.
- `POST /domains/:id/activate` — sets status `active`; documented as the call
  made by the Argo `wft-add-custom-domain.yaml` workflow after it updates
  ingress.
- `DELETE /domains/:id`, plus a public `GET /health`.

**Authorization.** Also in `router.ts`: `resolveCallerId()` pulls the GitHub
username out of `ownershipEntityRefs`, and `authorizeForTeam()` reuses
`getTenantMember` / `isAdminUser` from `../../tenant-backend/src/membershipLookup`
so any tenant role authorizes and an `admins`-tenant owner bypasses membership.
`isWorkflowCaller()` adds a narrow service tier gated on a subject allowlist
`WORKFLOW_CALLER_SUBJECTS = {'external:mctl-api', 'mctl-api'}`, deliberately not
a bare `allow: ['service']` check — the in-file comment records that a bare check
would also admit every other plugin's `plugin:<id>` credential. That subject is
minted by `backend.auth.externalAccess` in `app-config.production.yaml`, a static
token with `accessRestrictions: [{ plugin: custom-domains }]`.
`plugins/custom-domains-backend/src/plugin.ts` registers only `/health` as
unauthenticated via the exported `registerAuthPolicies()`, and `plugin.test.ts`
is a regression guard asserting `/domains*` never regains an unauthenticated
policy.

**Frontend.** `packages/app/src/components/catalog/EntityDomainsCard.tsx` reads
the team from the `platform.mctl.me/team` annotation and the service from
`entity.metadata.name`, resolves the backend with
`discoveryApi.getBaseUrl('custom-domains')`, and calls the four routes with
`fetchApi.fetch`. It renders the auto-generated domain from
`usePlatformConfig().domain` (`packages/app/src/platformConfig.ts`), a table of
`CustomDomain` rows keyed off the snake_case store shape (`auto_domain`,
`created_at`), a `statusConfig` map for the four statuses, and an "Add Domain"
dialog whose instructions are CNAME-only. `EntityPage.tsx:189` mounts it as
`<EntityLayout.Route path="/domains" title="Domains" if={hasTeamAnnotation}>`.
The plugin is wired into the backend at `packages/backend/src/index.ts` via
`backend.add(import('@internal/plugin-custom-domains-backend'))`.

**Precedent for outbound calls.** The repo already has the pattern this change
needs: `plugins/argo-workflows-backend/src/argoClient.ts` is a `class
ArgoWorkflowsClient` constructed from `{ baseUrl, token? }`, normalizing the base
URL with `.replace(/\/$/, '')`, building bearer headers in a private `headers()`,
funnelling everything through a private `request<T>()` that throws a
status-and-body-bearing `Error` on non-2xx, using `node-fetch`. Its base URL
comes from `config.getString('argoWorkflows.baseUrl')`
(`scaffolderActions.ts:103`); `plugins/resource-usage-backend/src/plugin.ts`
shows the same `coreServices.rootConfig` + `getOptionalString` idiom. No
`config.d.ts` exists anywhere in the repo, so plugin config is read without a
declared schema — this change follows that existing (if unfortunate) convention.

A second precedent is `plugins/proposals-backend/src/gitops-client.ts`, the only
client in the repo that resolves its base URL from config rather than hardcoding
it, built by a `buildGitopsClient(config, logger)` factory.

Nothing in the repo currently calls mctl-api outbound; the only mctl-api
references are the inbound external-access token and its allowlist. There is no
`proxy.endpoints` entry anywhere (both app-configs leave the block commented
out), no `mctlApi.*` config key, and no shared outbound HTTP helper.

Two existing inconsistencies are worth naming because this change resolves them
by deferring to mctl-api. First, `auto_domain` is computed three ways: hardcoded
`` `${team}-${service}.mctl.ai` `` at `router.ts:205`, hardcoded again in
`isValidCustomDomain`'s `.mctl.ai`/`.mctl.me` rejection list at `router.ts:110`,
and derived from `platform.domain` config in `EntityDomainsCard.tsx:145` — so a
config override of `platform.domain` silently desynchronizes the card from the
backend. Second, `packages/app` has `@backstage/test-utils` as a devDependency
but zero component tests use it: `App.test.tsx` is the only `.test.tsx` in the
app package and it mocks no APIs, so there is no in-repo precedent for mocking
`discoveryApiRef`/`fetchApiRef`.

## Proposed solution

Take issue option 1, implemented as **the portal plugin becomes a thin,
authenticated gateway to mctl-api** rather than the browser talking to mctl-api
directly. The plugin id, the route paths, and the frontend's
`discoveryApi.getBaseUrl('custom-domains')` all stay exactly as they are; only
what sits behind the router changes — from a knex table to an HTTP client.

**1. New `plugins/custom-domains-backend/src/mctlApiClient.ts`.** A
`MctlApiDomainsClient` modelled directly on `ArgoWorkflowsClient`: constructed
from `{ baseUrl, token }`, trailing-slash-normalized, bearer auth in a private
`headers()`, one private `request<T>()` that maps non-2xx into a typed
`MctlApiError { status, message }` (so 409 duplicate-domain stays a 409 to the
browser instead of collapsing into a 500), and an explicit timeout via
`AbortSignal.timeout`. It exposes the operations the router needs:
`list(team, service?)`, `create({ team, service, domain, actor })`,
`verify(id)`, `remove(id)`. It targets mctl-api's
`GET|POST /api/v1/domains` and the corresponding per-domain write endpoints.

All schema risk is concentrated in one exported pure function in that file,
`toPortalDomain(raw)`, which maps a registry record into the `CustomDomain`
shape the card already consumes (`id`, `team`, `service`, `domain`,
`auto_domain`, `status`, `verified_at`, `created_by`, `created_at`,
`updated_at`) and adds the two new TXT challenge fields
(`challenge_record_name`, `challenge_record_value`). Because it is pure and
exported, unit tests pin the mapping against a recorded mctl-api payload, and
the open question about mctl-api's exact field names has a blast radius of one
function.

**2. `router.ts` swaps its dependency.** `RouterOptions.store: CustomDomainStore`
becomes `RouterOptions.domains: DomainsClient` (an interface the client
implements). `verifyDns()` and the `dns`/`util` imports are deleted outright —
verification is mctl-api's TXT challenge now, and the portal must not do its own
DNS resolution. `isValidCustomDomain()` and the uniqueness pre-check are also
deleted: mctl-api is the system of record and owns validation and uniqueness;
duplicating them here is how the two sources drift. Every handler keeps its
current shape — resolve caller, authorize for team, then call the client instead
of the store — so the authorization ordering that `router.test.ts` asserts
(401/403 raised *before* any downstream call) is preserved verbatim.

`POST /domains/:id/activate` becomes a `410 Gone` returning a message pointing at
mctl-api, because activation is now a registry-side transition. It is not
deleted, so a stale caller gets a diagnosable answer rather than a 404 that looks
like a routing bug.

The `db` and `isPostgres` options stay: `authorizeForTeam` still needs the
Backstage database for the `tenant_members` lookup. Only the domain data moves.

**3. `plugin.ts` stops touching the table.** The `CustomDomainStore` construction
and `await store.initialize()` are removed, so the plugin no longer creates
`custom_domains` on boot. `coreServices.database` stays (membership lookup),
`coreServices.rootConfig` is added, and the plugin reads
`customDomains.baseUrl` (falling back to `https://api.mctl.ai`) and
`customDomains.token`. A missing base URL throws at init rather than degrading
to an empty list. `registerAuthPolicies()` is untouched, so `plugin.test.ts`
stays green unchanged. `store.ts` is deleted.

**4. Frontend `EntityDomainsCard.tsx`.** Route URLs and the discovery call are
unchanged. What changes is the verification story: the "Add Domain" dialog's
CNAME-only instructions become a two-record instruction (the CNAME to
`{team}-{service}.{platform.domain}` for traffic, plus the TXT challenge record
mctl-api returns on create), and a post-create panel renders the returned
`challenge_record_name` / `challenge_record_value` with the existing
copy-to-clipboard affordance. The table gains a "Verification" cell surfacing the
challenge for rows still pending. `statusConfig` is widened to cover whatever
status vocabulary mctl-api returns, keeping the existing four labels and falling
back to a neutral chip for an unknown status instead of silently rendering
"Pending DNS" for everything. The two `catch {}` blocks in `handleVerify` and
`handleDelete` that currently swallow failures are replaced with the same error
surface `fetchDomains` uses — with a live upstream, a silent failure is now a
real correctness problem rather than a cosmetic one.

**5. Config.** `customDomains.baseUrl` and `customDomains.token` are added to
`app-config.yaml` (local dev, token commented) and `app-config.production.yaml`
(`${MCTL_API_URL}` / `${MCTL_API_TOKEN}`, sourced from Vault like the existing
`${VAULT_TOKEN}` / `${BACKSTAGE_TOKEN}` entries), and both env vars are added to
`.env.example` — which today is already missing `${BACKSTAGE_TOKEN}`, so this
change should not repeat that omission. Keys are read in `plugin.ts` via
`coreServices.rootConfig`, matching `plugins/resource-usage-backend/src/plugin.ts`;
no `config.d.ts` is added, since no plugin in the repo declares one and
introducing the first schema file is a separate concern.

Note that `customDomains.baseUrl` is deliberately a *backend* key, never read
through `usePlatformConfig()`. The browser keeps talking to the portal's own
plugin, so no mctl-api address or credential is exposed to the frontend config.

Why a gateway rather than a direct browser call: it keeps the fetch same-origin,
so production CSP needs no `connect-src` widening (production only overrides
`img-src`; the local dev config's permissive `connect-src` does not apply there)
and mctl-api needs no CORS entry for the portal origin. It keeps the mctl-api
credential server-side. And critically, it keeps `authorizeForTeam` — with its
admin bypass, its case-mismatch handling, and its ten-case test suite — as a real
enforcement point rather than deleting the portal's only team boundary and
assuming mctl-api replicates it.

## Alternatives

**A. Frontend calls mctl-api directly** (`fetch('https://api.mctl.ai/api/v1/domains?...')`
from `EntityDomainsCard`). The most literal reading of the issue and the smallest
diff — delete the backend plugin, change one base URL. Dropped: it needs CORS on
mctl-api for the portal origin, a `connect-src` change in
`app-config.production.yaml`, and a credential the browser can hold; and it
deletes `authorizeForTeam` outright, moving the team boundary into a service we
cannot inspect from this repo and cannot test here. If mctl-api's own
authorization turns out to be equivalent and user-scoped, this becomes viable as
a later simplification, but not as the migration step.

**B. Backstage `proxy-backend` endpoint.** `@backstage/plugin-proxy-backend` is
already registered in `packages/backend/src/index.ts`; a
`proxy.endpoints['/mctl-api']` entry would forward with a header credential and
require no new plugin code. Dropped: the repo configures zero proxy endpoints
today (both app-configs have the block commented out), and more importantly a
generic proxy forwards *any* path under the prefix carrying a service-level
token, with no per-team check. Any authenticated portal user could then read or
mutate another team's domains — a privilege escalation the current plugin
specifically prevents.

**C. Issue option 2 — retire the portal surface.** Delete
`EntityDomainsCard.tsx`, the `/domains` route at `EntityPage.tsx:189`, the plugin
and its backend registration; custom domains become an API/MCP-only workflow.
This is the cheapest option and genuinely defensible, since the MCP tooling
(`mctl_add_custom_domain`, `mctl_list_domains`, `mctl_verify_domain`) already
covers the lifecycle. Dropped because it removes a shipped user-facing surface
with no replacement: a tenant owner completing a TXT challenge has nowhere in the
portal to see whether verification succeeded, and the portal's stated purpose is
to be that surface. It remains the documented fallback — if reviewers choose it,
`tasks.md` task 1 records the decision and the work collapses to deletions.

## Platform impact

**Migrations.** None. The `custom_domains` table is left physically in place and
simply stops being read or written; per the issue it has never held a
successfully registered domain for any team, so there is no data to move and no
backfill. Because `store.initialize()` is removed rather than replaced with a
drop, the change is reversible by reverting code alone — no schema state to
restore. Dropping the table is deliberately deferred to a follow-up.

**Backward compatibility.** The plugin id, the four route paths, and the
frontend's discovery lookup are unchanged, so nothing outside the plugin has to
move in lockstep. The one deliberate break is `POST /domains/:id/activate`,
which starts returning 410. Its only known caller is the Argo
`wft-add-custom-domain.yaml` workflow, which `mctl-gitops#1085` is believed to
have already repointed at mctl-api. Because that cannot be verified from this
clone, the `isWorkflowCaller` tier and the `app-config.production.yaml`
`externalAccess` entry are **kept** in this change; their removal is a separate
task gated on confirming the workflow no longer calls Backstage. If the workflow
does still call `/activate`, the 410 makes that visible immediately in its logs
rather than corrupting state.

**Resource impact.** One fewer table maintained in the Backstage Postgres; a new
outbound HTTP dependency from the portal backend to mctl-api. Per-request cost is
one upstream call on tab open, plus one per user action — negligible, and no
polling is added. The portal namespace must be able to reach mctl-api's
in-cluster or public address; if egress is restricted, that is a deployment-side
prerequisite, which is why the base URL is configurable rather than hardcoded.

**Risks and mitigations.**

- *Schema mismatch with mctl-api's registry* (the largest risk, given the open
  question). Mitigated by concentrating every field assumption in the exported
  pure `toPortalDomain()`, pinning it with a fixture test recorded from a real
  mctl-api response, and requiring the implementer to read
  mctl-api `internal/domains` before writing the mapping.
- *mctl-api availability becomes a hard dependency of the Domains tab.* Mitigated
  by mapping upstream failures to a 502 with a readable message and rendering it
  in the card's existing error state — a degraded tab, never a blank table that
  reads as "you have no domains", and never a crashed page.
- *Credential exposure.* The mctl-api token is read from config server-side,
  attached only in `MctlApiDomainsClient.headers()`, and never logged or echoed;
  the existing router logging pattern logs domains and ids, not headers.
- *Silently widening access.* Mitigated by keeping every authorization check and
  its test coverage, retargeted from the store mock to the client mock. The
  existing `router.test.ts` harness already injects the data layer as a plain
  object of jest mocks through `RouterOptions`, so the T1-T5 gating tests port
  with a rename and continue to assert that no downstream call happens on 401/403.
- *Losing the anti-regression guard on auth policies.* `plugin.ts`'s
  `registerAuthPolicies()` and `plugin.test.ts` are untouched by design.
