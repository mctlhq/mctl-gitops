# Repoint the custom-domains plugin at mctl-api's domain registry

## Context

`mctl-api#264` and `mctl-gitops#1085` moved the system of record for custom
domains out of the Backstage `custom-domains` plugin and into mctl-api's own
Postgres-backed registry (`internal/domains`), where verification is done with
a TXT challenge rather than a `dig CNAME` lookup. The mctl-portal side of that
migration — task 14 of the original `issue-262-custom-domains-post-api-v1-domains-alway`
proposal — was never filed or done. The portal therefore still owns a second,
now-orphaned copy of the data: `plugins/custom-domains-backend/src/store.ts`
creates and reads a `custom_domains` table in the Backstage database, and
`packages/app/src/components/catalog/EntityDomainsCard.tsx` renders the
"Domains" tab (mounted at `packages/app/src/components/catalog/EntityPage.tsx:189`)
straight off that table via `discoveryApi.getBaseUrl('custom-domains')`.

The consequence is a UI that is not merely stale but permanently wrong: a domain
registered through mctl-api or the `mctl_add_custom_domain` MCP tool will never
appear in the portal, and a domain added through the portal card is written to a
table that no ingress or TLS machinery reads any more. Per the issue, the old
plugin's list has been empty for every team since before the migration, so there
is no data to migrate — only a UI to repoint. This proposal takes issue option 1:
repoint the portal at mctl-api's registry, keeping the portal's `custom-domains`
plugin as a thin server-side gateway that preserves the existing per-team
authorization boundary (`authorizeForTeam` in
`plugins/custom-domains-backend/src/router.ts`) instead of exposing mctl-api
directly to the browser.

## User stories

- AS a tenant team member I WANT the service "Domains" tab to list the custom
  domains that actually exist in mctl-api's registry SO THAT what I see in the
  portal matches what the platform is really serving.
- AS a tenant team member I WANT to register a custom domain from the portal and
  be shown the exact TXT record mctl-api expects SO THAT I can complete
  verification without switching to the CLI or MCP tooling.
- AS a tenant team member I WANT to trigger verification and removal of a domain
  from the portal SO THAT the whole custom-domain lifecycle has one surface.
- AS a platform operator I WANT the portal to stop maintaining a second copy of
  domain state SO THAT there is exactly one system of record and no divergence
  to reconcile.
- AS a platform operator I WANT the portal's existing team-membership gate to
  still apply to every domain read and write SO THAT repointing does not widen
  who can see or change another team's domains.

## Acceptance criteria (EARS)

- WHEN a user opens the "Domains" tab for a catalog entity carrying the
  `platform.mctl.me/team` annotation THE SYSTEM SHALL render the custom domains
  returned by mctl-api's `GET /api/v1/domains?team=<team>&service=<service>` for
  that entity's team and service.
- WHEN the portal serves `GET /api/custom-domains/domains` THE SYSTEM SHALL
  obtain the result from mctl-api and SHALL NOT read the Backstage
  `custom_domains` table.
- WHILE the plugin is running THE SYSTEM SHALL NOT create, write to, or delete
  rows in the Backstage `custom_domains` table.
- WHEN a user submits a new domain from the "Add Domain" dialog THE SYSTEM SHALL
  forward the registration to mctl-api's domain-create endpoint and SHALL
  display the TXT challenge record name and value returned by mctl-api.
- WHEN a user triggers verification for a domain THE SYSTEM SHALL forward the
  request to mctl-api's verify endpoint and SHALL display the status mctl-api
  returns, without performing any DNS resolution inside the portal process.
- WHEN a user removes a domain from the card THE SYSTEM SHALL forward the
  deletion to mctl-api and SHALL refresh the table from mctl-api afterwards.
- WHILE handling any `/domains*` request THE SYSTEM SHALL continue to require an
  authenticated Backstage user and SHALL authorize that user against the target
  team with the existing `authorizeForTeam` check (tenant membership, with the
  `admins`-tenant owner bypass).
- IF the authenticated caller is not a member of the requested team and is not
  an `admins`-tenant owner THEN THE SYSTEM SHALL respond 403 and SHALL NOT issue
  any request to mctl-api.
- IF an unauthenticated caller requests any `/domains*` route THEN THE SYSTEM
  SHALL respond 401 and SHALL NOT issue any request to mctl-api.
- IF mctl-api is unreachable, times out, or returns a non-2xx response THEN THE
  SYSTEM SHALL respond with a 502-class error carrying a human-readable message
  and THE CARD SHALL render that message as an error state rather than an empty
  domain table.
- IF mctl-api returns a 4xx client error for a write (for example a duplicate
  domain or a rejected FQDN) THEN THE SYSTEM SHALL surface that status and
  message to the caller rather than replacing it with a generic 500.
- WHILE issuing requests to mctl-api THE SYSTEM SHALL attach its configured
  service credential from configuration and SHALL NOT log that credential or
  return it to the browser.
- WHEN the plugin starts and no mctl-api base URL is configured THE SYSTEM SHALL
  fail fast at initialization with an explicit configuration error rather than
  silently serving an empty domain list.
- WHEN `POST /api/custom-domains/domains/:id/activate` is called THE SYSTEM
  SHALL NOT mutate any portal-local state, because activation is now owned by
  mctl-api's registry.

## Out of scope

- Any change inside mctl-api itself (`internal/domains`), including its schema,
  its TXT challenge implementation, or its authorization model.
- Any change to `mctl-gitops` workflow templates (for example
  `wft-add-custom-domain.yaml`) or to the ingress/TLS provisioning path.
- Migrating data out of the Backstage `custom_domains` table. The issue states
  it has never held a successfully registered domain for any team; this proposal
  reads and writes nothing from it and leaves the table physically in place.
- Dropping the `custom_domains` table from the Backstage database. That is a
  separate cleanup once this change has been stable in production.
- Issue option 2 (retiring the portal domain surface entirely). It is recorded
  in `design.md` as the considered-and-rejected alternative and remains the
  documented fallback if reviewers decide domains stay API/MCP-only.
- Building a new domains view outside the catalog entity page (no standalone
  domains page, no team-level aggregate view).

## Open questions

- The exact response schema of mctl-api's `GET /api/v1/domains` and its write
  endpoints is not visible from this repository (the investigation clone is
  mctl-portal only). Field names, the status vocabulary, the id used by the
  verify/delete routes, and the TXT challenge field names must be read out of
  mctl-api's `internal/domains` before coding. The design isolates every such
  assumption in a single mapping function so the blast radius of getting it
  wrong is one file. Proceeding on the assumption that the registry exposes at
  minimum: domain, team, service, status, created timestamp, and challenge
  record name/value.
- How mctl-api authenticates a call originating from the portal backend, and
  whether it expects an acting-user identity in addition to a service
  credential. This proposal assumes a bearer service credential plus the portal
  enforcing team membership itself; if mctl-api can accept and enforce a
  user-scoped identity, the portal's own check becomes defence in depth rather
  than the only gate, which is still correct.
- Whether `mctl-gitops#1085` already repointed `wft-add-custom-domain.yaml` off
  the portal's `POST /domains/:id/activate`. This determines whether the
  external-access entry in `app-config.production.yaml` (static token, subject
  `mctl-api`, restricted to plugin `custom-domains`) and the
  `WORKFLOW_CALLER_SUBJECTS` tier in `router.ts` can be deleted now or must be
  kept for one release. The design keeps them, with removal as a separate
  verified task.
- Whether tenant-facing domain writes should stay in the portal at all, or
  whether the portal should become read-only with registration driven by MCP/CLI.
  The issue explicitly names "and the write endpoints", so writes are kept.
