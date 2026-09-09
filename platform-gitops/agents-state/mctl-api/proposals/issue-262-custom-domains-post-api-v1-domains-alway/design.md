# Design: issue-262-custom-domains-post-api-v1-domains-alway

## Current state

**Routing.** `internal/api/router.go` lines 277-281 register the four domain
routes inside the authenticated group:

```go
// Custom domains (proxied to Backstage custom-domains plugin).
r.Get("/domains", h.ListDomains)
r.Post("/domains", h.AddDomain)
r.Post("/domains/{id}/verify", h.VerifyDomain)
r.Delete("/domains/{id}", h.DeleteDomain)
```

**Handlers.** `internal/api/handlers_domains.go` is a thin proxy to Backstage:

- `authorizeBackstage` (line 39) sets `Authorization: Bearer <BackstageToken>`,
  and is a no-op when the token is empty — the request then goes upstream
  anonymously instead of failing locally.
- `ListDomains` (line 47) and `AddDomain` (line 94) both check
  `user != nil && !user.HasTenantAccess(team)`, i.e. a **nil** user skips the
  check entirely, and then copy the upstream status and body verbatim
  (lines 86-89, 150-153). This is exactly how Backstage's
  `401 {"error":"Authentication required"}` reaches the caller wearing
  mctl-api's clothes.
- `VerifyDomain` (line 262) and `DeleteDomain` (line 301) are stricter: they go
  through `authorizeDomainMutation` (line 204), which fails closed on a nil
  user, short-circuits for admins, and otherwise resolves ownership by listing
  the team's domain IDs from Backstage (`backstageDomainIDs`, line 158).
- The upstream base is `h.opts.BackstageInternalURL`
  (`http://backstage.backstage.svc.cluster.local:7007` by default,
  `cmd/api/main.go` line 548); the credential is `BACKSTAGE_TOKEN`
  (`cmd/api/main.go` line 547, documented in `README.md` line 135).

**Credential topology.** `BackstageToken` is described in `router.go` line 61 as
"optional Backstage integration for immediate catalog sync" and is also used by
`notifyBackstage` (`internal/api/handlers_write.go` line 375) for the tenant
catalog POST. `BackstageGithubAppConnectToken` (line 71) exists as a
deliberately separate credential for the repos proxy, with the same
"no header when unset" behavior and a startup warning at `router.go` line 129 —
a precedent the domains path never got. A third, distinct credential
(`backstage-workflow-token`) is mounted by the add/remove-custom-domain
workflows; `internal/operations/executor.go` lines 89-100 documents that those
two workflows were moved to the `argo-workflows` namespace precisely so tenant
service accounts cannot read that platform credential. So three different
principals talk to one plugin, and only mctl-api's is rejected on writes.

**Workflow trigger.** Registration and workflow submission are two separate
calls. `internal/mcp/server.go` line 1469 POSTs `/api/v1/domains` and then line
1480 POSTs `/api/v1/operations/add-custom-domain/execute`. The operation is
declared in `internal/operations/registry.go` line 349 (`WorkflowTemplate:
"add-custom-domain"`, `ModifiesPaths: platform-gitops/services/{team_name}/{service_name}/`).
`mctl_verify_domain` (`internal/mcp/server.go` line 1534) lists domains and then
POSTs `/api/v1/domains/{id}/verify?team=` for each.

**Persistence precedent.** mctl-api already runs four PostgreSQL stores with an
identical shape: `internal/alerts/store.go` (`NewStore(ctx, connStr)` executing
an idempotent `CREATE TABLE IF NOT EXISTS ...` schema constant, injected as an
optional `Options` field, nil store means the endpoints return 503),
`internal/agentregistry/store.go`, `internal/audit/postgres.go`,
`internal/auth/refreshstore/postgres.go`. `cmd/api/main.go` lines 169-189 shows
the wiring convention: a dedicated `*_DB_URL` env var falling back to
`AUDIT_DB_URL`, through `postgresURL()` / `dburl.EnforceTLS`.

**Authentication classes.** `internal/auth/oidc.go` `Middleware` accepts a
GitHub PAT, a Dex JWT, a locally issued OAuth JWT, or `MCTL_AGENT_SERVICE_TOKEN`
(`staticServiceUser`, line 198, producing the `mctl-agent` principal with
`IsService() == true`). None of these is a Backstage user credential, and the
MCP path has no browser session at all.

**Nothing is stored today.** `GET /api/v1/domains` is empty for every team, so
the Backstage `custom_domains` table has no rows to preserve.

## Proposed solution

Make mctl-api the system of record for custom domains, and move DNS
verification from a shell `dig` in the workflow to a testable Go check based on
a TXT challenge.

### 1. `internal/domains` — a PostgreSQL store

New package modelled directly on `internal/alerts`:

```go
const domainSchema = `
CREATE TABLE IF NOT EXISTS custom_domains (
    id                 TEXT PRIMARY KEY,          -- uuid
    team               TEXT NOT NULL,
    service            TEXT NOT NULL,
    domain             TEXT NOT NULL,
    status             TEXT NOT NULL,             -- pending|verified|active|failed
    verification_token TEXT NOT NULL,
    created_by         TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL,
    verified_at        TIMESTAMPTZ,
    last_error         TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS custom_domains_domain ON custom_domains (domain);
CREATE INDEX IF NOT EXISTS custom_domains_team ON custom_domains (team, service);
`
```

`Store` exposes `Create` (idempotent on `(team, service, domain)`, returning the
existing row; `ErrDomainConflict` when the same `domain` belongs to another
team — mirroring `alerts.ErrIDConflict`, whose comment already states the rule
that the caller must not learn who owns it), `ListByTeam(team, service)`,
`Get(id)`, `GetByDomain(domain)`, `SetStatus(id, status, err)`,
`MarkVerified(id)`, and `Delete(id)`. Wired in `cmd/api/main.go` from
`DOMAINS_DB_URL` falling back to `AUDIT_DB_URL`, through the same
`initStore` / `postgresURL` helpers used for the alert store, and injected as
`Options.DomainStore` (nil → 503, matching `AlertStore`).

### 2. `handlers_domains.go` — local reads and writes

`ListDomains`, `AddDomain`, `VerifyDomain`, `DeleteDomain` are rewritten
against the store. Behavioural changes beyond the storage swap:

- **Fail closed on a nil user.** `ListDomains` and `AddDomain` adopt the
  `authorizeDomainMutation` rule (line 204): `user == nil` → 401. Today they
  skip the check, which is only survivable because Backstage was doing the
  rejecting.
- **Platform-domain rejection at the edge.** `AddDomain` rejects any host equal
  to or ending in `.<PLATFORM_DOMAIN>` (new env var, default `mctl.ai` — the
  value is hardcoded today at `internal/api/handlers_openclaw.go` line 510)
  with 400 and the wording already shipped in #263. The workflow's own
  rejection stays as the backstop.
- **Verification token.** `Create` mints a 32-byte `crypto/rand` hex token. The
  201 response carries `challenge_record` (`_mctl-challenge.<domain>`),
  `challenge_value` (`mctl-domain-verification=<token>`), and `cname_target`
  (`{team}-{service}.<platform_domain>`), so the MCP tool can print exactly what
  the tenant must create.
- **No upstream status pass-through.** There is no upstream left; local errors
  use `writeError()` per `CLAUDE.md` conventions. `authorizeBackstage`,
  `backstageDomainIDs`, and `backstageDomainsClient` are deleted from this file
  (`notifyBackstage`'s use of `BackstageToken` in `handlers_write.go` is
  untouched).
- Ownership resolution in `authorizeDomainMutation` becomes a store lookup
  (`GetByDomain` / `Get` + `HasTenantAccess`) instead of N Backstage list calls
  across the caller's groups, preserving the existing 404-not-403 leak
  behaviour for ids the caller cannot see.

### 3. `internal/domains/verify.go` — TXT challenge

```go
type Verifier struct { resolver *net.Resolver }   // DNS_RESOLVER_ADDR, default 1.1.1.1:53
func (v *Verifier) Verify(ctx, d Domain, cnameTarget string) (Result, error)
```

Order: look up `TXT _mctl-challenge.<domain>` and accept when any value equals
`mctl-domain-verification=<token>`; otherwise fall back to
`LookupCNAME(<domain>)` and accept when it resolves to `cnameTarget` (the
fast-path for unproxied records, so existing correct setups keep working). A
failed check is **not** an HTTP error: the handler returns 200 with
`{"verified": false, "reason": ..., "expected_record": ..., "expected_value": ...}`.
TXT is the primary because Cloudflare proxying rewrites the A/CNAME answer but
never the TXT RRset, which is precisely the defect the issue reports;
reachability is still proven later by HTTP-01 issuance in the workflow, so the
pair (TXT ownership + ACME reachability) is strictly stronger than the CNAME
check it replaces.

New route `POST /api/v1/domains/verify` with body `{team, service, domain}` for
callers that know the hostname but not the row id (the Argo workflow). No chi
conflict: `/domains/verify` is two segments, `/domains/{id}/verify` is three.

### 4. Status callback for the workflow

`PATCH /api/v1/domains/{id}` accepting `{status, error}`, restricted to
`user.IsService()` (`internal/auth/oidc.go` line 193) so only the
`MCTL_AGENT_SERVICE_TOKEN` principal can move a row to `active`/`failed`.
Human callers get 403.

### 5. mctl-gitops companion (separate repo, tracked here)

In `platform-gitops/argo-workflows/cluster-templates/wft-add-custom-domain.yaml`:
replace the `dig +short CNAME "${DOMAIN}"` step with a `curl` to
`POST $MCTL_API_URL/api/v1/domains/verify` carrying the platform service token,
failing the step when `.verified != true` and echoing `reason` /
`expected_record`; add a final step that PATCHes the row to `active` or
`failed`. The platform-domain rejection step at the top of the template is left
exactly as is. The workflow already runs in `argo-workflows`
(`internal/operations/executor.go` line 100) where platform credentials live, so
mounting the mctl-api service token there introduces no new tenant exposure —
and `backstage-workflow-token` can be dropped from this template once the
Backstage plugin is no longer in the path.

## Alternatives

**A. Forward the caller's credential to Backstage (the issue's "user-delegated"
option).** Rejected: `auth.TokenFromContext` can hand the raw bearer token
downstream, but that token is a GitHub PAT, a Dex JWT, an mctl-api-issued OAuth
JWT, or the static service token — never a Backstage-issued user credential.
The subset of callers it could ever satisfy excludes `mctl_add_custom_domain`
entirely, which is the primary consumer named in the issue, so this design
ships a permanently broken MCP tool.

**B. Change the mctl-portal write route to accept the service token (the
issue's second option), with a distinct `BACKSTAGE_CUSTOM_DOMAINS_TOKEN` in
mctl-api mirroring `BackstageGithubAppConnectToken`.** This is the smallest
diff and was the leading candidate. Rejected because the entire mctl-api-side
change is "send a different bearer token", leaving the actual fix in another
repo and another team's review queue, while keeping three principals
(`BACKSTAGE_TOKEN`, `backstage-workflow-token`, browser session) authorized
against one table whose authorization decision mctl-api already makes locally
via `HasTenantAccess`. It also leaves the fail-open `authorizeBackstage` and the
verbatim upstream-status pass-through in place — the two things that turned a
credential problem into a misleading `401 Authentication required`.

**C. Keep the Backstage store, fix only the diagnosability (fail closed on an
empty token, map upstream 401/403 to 502 "backstage rejected the platform
credential").** Rejected as a complete answer — it makes the failure legible but
still cannot register a domain, so `seerrsense#7` stays blocked. The two
hardening items are folded into the proposed solution instead (nil-user 401,
no pass-through of upstream auth verdicts).

**D. Fix verification with a Cloudflare API lookup instead of TXT.** Rejected:
it requires a Cloudflare API token in the `argo-workflows` namespace, only works
for domains hosted at one provider (tenant domains may sit anywhere), and the
platform gains a secret with zone-read scope over customer zones. TXT is
provider-agnostic and needs no credential.

## Platform impact

- **Migration.** None for data: the Backstage `custom_domains` table is empty
  for every team, confirmed in the issue. Schema creation is the idempotent
  `CREATE TABLE IF NOT EXISTS` pattern already used by `alerts.NewStore`, run at
  startup.
- **Backward compatibility.** Request and response shapes of the four existing
  routes are preserved (`{"domains":[...]}` for list, a domain object for add),
  with additive fields (`challenge_record`, `challenge_value`, `cname_target`,
  `status`). `mctl_verify_domain`'s list-then-verify flow (`server.go` line
  1534) keeps working unchanged. Two additive routes
  (`POST /domains/verify`, `PATCH /domains/{id}`). No MCP tool is added or
  removed, so the `expected 73 tools` assertion in
  `internal/mcp/server_test.go` line 170 is unaffected.
- **Deployment.** Needs `DOMAINS_DB_URL` (or an existing `AUDIT_DB_URL`),
  `PLATFORM_DOMAIN`, and optionally `DNS_RESOLVER_ADDR` in the chart's `env`
  map (`helm/values.yaml` line 42) and in platform-gitops. Until the DB URL is
  set, `/api/v1/domains*` returns 503 with an explicit message — a louder but
  more honest failure than today's 401.
- **Egress.** The verifier makes outbound DNS (UDP/TCP 53) calls from the
  mctl-api pod. If the namespace's NetworkPolicy denies egress, verification
  fails closed with a clear reason; confirm the policy before rollout.
- **Risk: two stores of record during the transition.** mctl-portal's plugin
  keeps its table. Mitigated by it being empty, and by a follow-up mctl-portal
  issue to repoint the UI at `GET /api/v1/domains`.
- **Risk: TXT challenge is a weaker signal than "CNAME points at us".**
  Mitigated by keeping the CNAME fast path, and by HTTP-01 issuance in the
  workflow, which still fails if traffic for the hostname does not reach the
  platform edge — so a TXT record alone cannot attach a hostname that is not
  actually routed here.
- **Risk: the service-token PATCH callback widens what the workflow can do.**
  Mitigated by restricting it to `IsService()` principals, to status
  transitions only, and by the existing decision to keep these two workflow
  templates out of tenant namespaces (`executor.go` lines 89-100).
- **Resource impact.** One additional pgx pool against the existing cluster and
  a handful of DNS lookups per verification. Negligible.
