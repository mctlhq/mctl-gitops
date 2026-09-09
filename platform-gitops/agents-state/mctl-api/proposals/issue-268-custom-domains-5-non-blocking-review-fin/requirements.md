# Custom domains: close the five non-blocking review findings from #264

## Context

`mctl-api#264` (merged, `e81215b`) made mctl-api the system of record for tenant
custom domains: `internal/domains` (Postgres store + TXT/CNAME verifier) and
`internal/api/handlers_domains.go` (list/add/verify/verify-by-name/delete/patch-status)
replaced the Backstage custom-domains proxy. Five review findings were accepted
during that PR as non-blocking cleanup and deferred to issue #268: a
case-sensitive CNAME comparison in `internal/domains/verify.go:123`, three
handler-test gaps (TXT path, `VerifyDomainByName` happy path, `ListDomains`
response shape), and the divergence between "mctl-api owns the registry row"
and "the `remove-custom-domain` workflow owns the ingress" on delete.

None of these is a live outage, but each one erodes a guarantee the rewrite was
supposed to establish. The case-sensitivity bug silently pushes a correctly
CNAME-configured tenant onto the TXT path (same class of bug already fixed twice
in that PR, in `platformDomain()` and `isPlatformDomain`). The test gaps leave
the endpoint the `add-custom-domain` Argo workflow actually calls
(`POST /api/v1/domains/verify`, see `mctl-gitops#1085`) and the TXT path — the
Cloudflare-proxied case the whole feature exists for — unpinned. And the delete
path is doubly incomplete: `DeleteDomain` (`handlers_domains.go:408`) drops the
row without touching ingress, while the MCP tool `mctl_remove_custom_domain`
(`internal/mcp/server.go:1489`) triggers the workflow without dropping the row —
so neither caller performs a complete teardown, and the freed unique index
(`custom_domains_domain`) lets a second team register a hostname the first
team's `ingress.hosts` still declares.

## User stories

- AS a tenant owner who pointed a correct CNAME at `{team}-{service}.mctl.ai`
  I WANT verification to succeed regardless of the case my team/service or the
  DNS answer is spelled in SO THAT I am not told to create a TXT record I do
  not need.
- AS a platform maintainer I WANT handler-level tests for the TXT verification
  path, for `VerifyDomainByName`'s happy path, and for the `ListDomains`
  response shape SO THAT a refactor cannot silently break the two contracts the
  Argo workflow and the MCP tools depend on.
- AS a tenant reading `GET /api/v1/domains` I WANT the challenge fields to
  describe work that is actually outstanding SO THAT an `active` domain is not
  listed with a TXT challenge it has nothing left to do with.
- AS a tenant owner removing a custom domain I WANT the hostname removed from my
  service's ingress and TLS config as well as from the registry SO THAT the
  platform does not keep serving/claiming a hostname I no longer own, and so
  another team cannot re-register a hostname my ingress still declares.

## Acceptance criteria (EARS)

Case-insensitivity (finding 1)

- WHEN `Verifier.Verify` compares the resolved CNAME against the expected
  target THE SYSTEM SHALL compare case-insensitively after stripping the
  trailing root dot from both sides.
- WHEN `AddDomain` accepts a registration THE SYSTEM SHALL normalize `team` and
  `service` by trimming surrounding whitespace and lowercasing, before the
  tenant-access check, the store write, and any CNAME target construction.
- WHILE rows created before this change may hold mixed-case `team`/`service`
  values THE SYSTEM SHALL still match them in `VerifyDomainByName`'s
  `d.Team != req.Team || d.Service != req.Service` gate by comparing
  case-insensitively.
- IF a domain is registered with `team: "Labs"`, `service: "SVC"` and DNS answers
  `LABS-SVC.MCTL.AI.` for a CNAME lookup THEN THE SYSTEM SHALL report
  `verified: true` with `method: "cname"`.

Test coverage (findings 2, 3, 4)

- WHEN the handler test suite runs against a configured `TEST_DATABASE_URL`
  THE SYSTEM SHALL exercise a handler-level TXT verification success, using the
  `challenge_value` returned by `AddDomain` as the stubbed `LookupTXT` answer,
  and assert the persisted row reaches `status: verified` with `verified_at` set
  and `method: "txt"` in the response.
- WHEN the handler test suite runs THE SYSTEM SHALL exercise a
  `VerifyDomainByName` happy path (positive verdict, row marked verified) and a
  case where the stored row's `service` differs from the request's, asserting
  404.
- WHEN `ListDomains` returns a `pending` domain THE SYSTEM SHALL include
  `challenge_record`, `challenge_value` and `cname_target` in the list body, and
  the test suite SHALL assert on those field names, not only on the hostname.

Challenge-field honesty (finding 4, second half)

- WHILE a domain's status is `pending` or `failed` THE SYSTEM SHALL include
  `challenge_record` and `challenge_value` in every response that renders it.
- WHILE a domain's status is `verified` or `active` THE SYSTEM SHALL omit
  `challenge_record` and `challenge_value` from the rendered response, while
  still returning `cname_target`.

Delete/ingress convergence (finding 5)

- WHEN `DeleteDomain` is called for a registry row AND a workflow executor is
  configured THE SYSTEM SHALL submit the `remove-custom-domain` operation for
  the row's `(team, service, domain)` before deleting the row, and SHALL include
  the resulting `workflow_name` in the response body.
- IF submitting `remove-custom-domain` fails THEN THE SYSTEM SHALL leave the
  registry row in place and return an error, so that the registry never claims a
  hostname is free while its ingress entry still exists.
- IF no workflow executor is configured (`Options.Executor == nil`, as in unit
  tests and local runs) THEN THE SYSTEM SHALL delete the row as it does today
  and report `ingress_cleanup: "skipped"` in the response.
- WHEN the MCP tool `mctl_remove_custom_domain` runs THE SYSTEM SHALL perform a
  single complete teardown: resolve the registry row for the hostname and call
  `DELETE /api/v1/domains/{id}?team=...`, so that both the row and the ingress
  entry are removed exactly once.
- IF the hostname has no registry row (a legacy registration predating #264)
  THEN THE MCP tool SHALL fall back to submitting `remove-custom-domain`
  directly, preserving today's behavior.
- WHEN a caller reads the `DELETE /api/v1/domains/{id}` and
  `mctl_remove_custom_domain` documentation THE SYSTEM SHALL state the teardown
  contract explicitly, the way `mctl_verify_domain`'s description documents its
  own workflow trigger.

## Out of scope

- Any change to the `add-custom-domain` / `remove-custom-domain` Argo workflow
  templates themselves — those live in `mctl-gitops` (`mctl-gitops#1085` tracks
  the workflow-side gap).
- A SQL migration that rewrites existing mixed-case `team`/`service` values in
  `custom_domains`. Compatibility is handled by case-insensitive comparison
  instead.
- Closing the "verified but workflow still running" re-trigger window documented
  at `internal/mcp/server.go:1582-1603` — that needs a new status or trigger
  timestamp and is explicitly its own piece of work.
- Changing the verification order (TXT first, CNAME fallback) or adding new
  verification methods.
- Adding the `/api/v1/domains*` routes to `internal/openapi/openapi.yaml` (they
  are absent today; not a regression introduced here).

## Open questions

- Does any consumer (Backstage UI card, portal) read `challenge_record` /
  `challenge_value` from a non-`pending` list entry? Nothing in this repo does
  (`internal/mcp/server.go:1561` decodes only `id`/`domain`/`status`), so the
  proposal gates them on `pending`/`failed` and treats the risk as accepted;
  if a consumer surfaces, the gate is a one-line revert.
- Should `DeleteDomain` trigger `remove-custom-domain` only for rows that ever
  reached `active` (i.e. those whose hostname actually made it into ingress)?
  Proceeding with "always trigger when an executor is configured" because the
  workflow is idempotent on a hostname it does not find, and because a row can
  be `verified` with the workflow mid-flight.
- Which namespace should the executor-submitted `remove-custom-domain` run in?
  Proceeding with the team name as the `namespace` argument, since
  `internal/operations/executor.go:92-100` already forces add/remove-custom-domain
  into `argo-workflows` regardless of the tenant passed.
