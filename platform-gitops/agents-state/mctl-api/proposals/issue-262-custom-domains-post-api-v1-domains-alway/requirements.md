# Custom domains: own the registry in mctl-api and verify with a TXT challenge

## Context

`POST /api/v1/domains` returns `401 {"error":"Authentication required"}` for an
authenticated admin caller, while `GET /api/v1/domains` for the same caller
returns `200`. Both handlers in `internal/api/handlers_domains.go` proxy to the
Backstage `custom-domains` plugin, attach `Bearer $BACKSTAGE_TOKEN` via
`authorizeBackstage`, and write the upstream status and body through verbatim
(`AddDomain`, lines 94-154). The 401 the caller sees is therefore Backstage's
answer about *mctl-api's* service credential, mis-presented as if the caller had
not authenticated. `authorizeBackstage` also attaches nothing at all when
`BACKSTAGE_TOKEN` is empty (line 40), so a missing credential degrades into an
anonymous upstream call rather than a local failure. Registration is impossible
through the API and through `mctl_add_custom_domain` (`internal/mcp/server.go`
line 1469, which POSTs to the same route), which blocks self-service custom
domains entirely.

The write path cannot be repaired by handing mctl-api a different Backstage
token if the plugin's write route requires a Backstage *user* principal: none of
mctl-api's three caller classes (GitHub PAT, Dex JWT, `MCTL_AGENT_SERVICE_TOKEN`
service principal — `internal/auth/oidc.go`) can produce one, and the MCP tool
has no user session at all. mctl-api already enforces the only authorization
that matters here (`user.HasTenantAccess`, lines 60 and 116) and already owns
four PostgreSQL-backed stores built on the same pattern (`internal/alerts`,
`internal/agentregistry`, `internal/audit`, `internal/auth/refreshstore`). The
Backstage table is empty for every team — no domain has ever been registered —
so moving the registry into mctl-api costs no migration and removes the
cross-service credential handshake instead of renegotiating it.

Separately, `platform-gitops/argo-workflows/cluster-templates/wft-add-custom-domain.yaml`
verifies ownership with `dig +short CNAME "${DOMAIN}"` and fails on an empty
answer. Cloudflare-proxied records answer with edge A records and never a CNAME,
so a correctly configured tenant hostname fails verification, and comparing
resolved addresses proves nothing because every proxied host in the zone shares
the same edge addresses. Ownership must be proven by a record type Cloudflare
does not rewrite: a TXT challenge.

## User stories

- AS a tenant owner I WANT `POST /api/v1/domains` to register my own domain
  SO THAT I can put a custom hostname in front of my service without an operator.
- AS an admin using `mctl_add_custom_domain` I WANT registration to succeed or
  to fail with a reason I can act on SO THAT I am not told "Authentication
  required" while holding a valid admin token.
- AS a tenant owner whose domain is proxied through Cloudflare I WANT DNS
  verification to pass when I have configured the domain correctly SO THAT the
  add-custom-domain workflow can issue a certificate and update ingress.
- AS a platform operator I WANT mctl-api to fail loudly when its domain registry
  is unconfigured SO THAT a missing dependency never degrades into a silently
  unauthenticated or silently empty result.
- AS an operator asked for an `*.mctl.ai` hostname I WANT the API to reject it
  immediately with the GitOps instruction SO THAT I do not spend a debugging
  cycle on a request the platform has decided not to serve.

## Acceptance criteria (EARS)

- WHEN an authenticated caller with tenant access POSTs `/api/v1/domains` with
  `{team, service, domain}` for a domain outside the platform domain THE SYSTEM
  SHALL persist the domain in mctl-api's own PostgreSQL registry with status
  `pending`, a generated verification token, and `created_by` set to the
  caller's user ID, and SHALL return `201` with the domain record, the required
  TXT challenge record name and value, and the CNAME target
  `{team}-{service}.{platform_domain}`.
- WHEN `GET /api/v1/domains?team=X[&service=Y]` is called by a caller with
  access to team X THE SYSTEM SHALL return the registry rows for that team
  (filtered by service when given) from its own store.
- WHILE the caller lacks `HasTenantAccess` for the requested team THE SYSTEM
  SHALL return `403` and SHALL NOT read or write any registry row for that team.
- IF the request carries no authenticated principal THEN THE SYSTEM SHALL
  return `401` for every `/api/v1/domains*` route, including `GET` and `POST`,
  which today skip the check on a nil user.
- IF the requested domain is inside the platform domain (any hostname ending in
  `.<platform_domain>`, and the bare platform domain itself) THEN THE SYSTEM
  SHALL return `400` with the rejection wording already shipped in mctl-api#263,
  pointing the caller at `ingress.hosts` / `ingress.tls[].hosts` in
  `platform-gitops/services/{team}/{service}/values.yaml`.
- IF the same `(team, service, domain)` is registered twice THEN THE SYSTEM
  SHALL return the existing record with `200` rather than creating a duplicate,
  and IF the domain is already registered to a different team THEN THE SYSTEM
  SHALL return `409` without disclosing the owning team.
- WHEN `POST /api/v1/domains/{id}/verify` or `POST /api/v1/domains/verify`
  (body `{team, service, domain}`) is called THE SYSTEM SHALL resolve TXT
  records for `_mctl-challenge.<domain>` through a recursive resolver and SHALL
  mark the domain `verified` only if one value equals
  `mctl-domain-verification=<token>` for that row.
- WHEN verification is attempted and the TXT challenge is absent or does not
  match THE SYSTEM SHALL leave the row unverified and return `200` with
  `{"verified": false, "reason": ..., "expected_record": ..., "expected_value": ...}`
  rather than an error status, so the workflow and the MCP tool can report the
  exact record the tenant still has to create.
- WHILE a domain is proxied through Cloudflare (no CNAME in the public answer,
  edge A records only) THE SYSTEM SHALL still be able to verify it, because
  verification reads TXT and never requires a CNAME answer.
- WHEN a CNAME for `<domain>` does resolve to `{team}-{service}.{platform_domain}`
  THE SYSTEM SHALL accept that as proof of control as a fast path, without
  requiring the TXT record.
- WHEN the add-custom-domain Argo workflow runs THE SYSTEM SHALL obtain its
  verification verdict by calling mctl-api's verify endpoint with the
  platform service token instead of running `dig +short CNAME`, and SHALL fail
  the workflow when the verdict is `verified: false`.
- WHEN the workflow finishes updating ingress and TLS THE SYSTEM SHALL accept a
  status callback (`PATCH /api/v1/domains/{id}`) from the service principal only
  and SHALL record the resulting status (`active` or `failed`).
- IF the domains store is not configured THEN THE SYSTEM SHALL return `503`
  with an explicit "domains registry not configured" error on every
  `/api/v1/domains*` route and SHALL log a startup warning, instead of
  proxying an unauthenticated request anywhere.
- WHILE the platform-domain rejection path exists in
  `wft-add-custom-domain.yaml` THE SYSTEM SHALL leave it unchanged.

## Out of scope

- Any admin-only registration path for `*.mctl.ai` hostnames. Settled in the
  issue: platform-domain hostnames stay GitOps-only via `ingress.hosts`.
- Rewording the platform-domain rejection message in the workflow, the
  `mctl_add_custom_domain` tool description, or the platform-skill copies —
  shipped in mctl-api#263 and mctl-gitops#1080.
- Changing the Backstage `custom-domains` plugin's auth policy in mctl-portal.
  This proposal makes that plugin non-load-bearing for the API path instead.
- Any Cloudflare API credential in the cluster. Verification stays
  provider-agnostic (public recursive resolver + TXT).
- ACME/TLS issuance changes. HTTP-01 issuance in the workflow is untouched and
  remains the reachability proof that complements the TXT ownership proof.
- Retiring `BACKSTAGE_TOKEN` itself: it is still used by `notifyBackstage`
  (`internal/api/handlers_write.go` line 375) for tenant catalog sync.

## Open questions

- The motivating request in the issue is `seerrsense.mctl.ai`, which is inside
  the platform domain and is therefore rejected by policy regardless of the 401
  fix. Fixing writes does not by itself unblock `mctlhq/seerrsense#7`; that
  hostname needs the GitOps `ingress.hosts` edit. Proceeding on the assumption
  that the API path must work for genuine tenant-owned domains and that
  seerrsense is handled separately in GitOps.
- mctl-portal's `custom-domains` plugin keeps its own (empty) table. Whether its
  UI is repointed at `GET /api/v1/domains` or left showing an empty list is a
  mctl-portal decision; this proposal assumes a follow-up issue there and does
  not delete the plugin.
- Exact recursive resolver to query (`1.1.1.1:53` vs. cluster CoreDNS forward).
  Proceeding with a configurable `DNS_RESOLVER_ADDR`, defaulting to a public
  resolver so results do not depend on cluster split-horizon DNS.
- Whether the TXT challenge label should be `_mctl-challenge` or
  `_mctl-domain-verification`. Proceeding with `_mctl-challenge`; it is
  referenced consistently across all three files and in the API response, so a
  rename is a single-constant change.
