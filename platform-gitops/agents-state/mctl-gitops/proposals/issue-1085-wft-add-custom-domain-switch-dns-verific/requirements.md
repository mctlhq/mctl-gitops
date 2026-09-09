# wft-add-custom-domain: verify DNS through mctl-api instead of `dig CNAME`

## Context

`platform-gitops/argo-workflows/cluster-templates/wft-add-custom-domain.yaml`
proves domain ownership at line 155 with
`CNAME_TARGET=$(dig +short CNAME "${DOMAIN}" | sed 's/\.$//' | head -1)` and
fails the run when the answer is empty or does not equal
`{team}-{service}.${PLATFORM_DOMAIN}`. A hostname proxied through Cloudflare
never answers with a CNAME — the edge returns its own A records — so a
correctly configured tenant domain fails verification and no certificate or
ingress entry is ever written. That is the defect `mctl-api#262` reports.

`mctl-api#264` (merged, `e81215b`) shipped the API half: a Postgres-backed
domains registry plus `POST /api/v1/domains/verify` (body `{team, service,
domain}`) and `POST /api/v1/domains/{id}/verify`, which check a TXT ownership
challenge at `_mctl-challenge.<domain>` first — Cloudflare proxying rewrites
A/CNAME answers but never TXT — and fall back to an unproxied CNAME match.
Verification returns `200` with `{verified, method, reason, expected_record,
expected_value}` even on a negative verdict, and `PATCH /api/v1/domains/{id}`
accepts a `{status, error}` callback restricted to the service principal. Those
were tasks 1-9 of
`platform-gitops/agents-state/mctl-api/proposals/issue-262-custom-domains-post-api-v1-domains-alway/`;
tasks 10-11 of that same proposal are this repo's half and were never opened as
a PR. Until they land, the registry is written but the workflow still runs
`dig`, so the reported defect is still live and every registry row that a
successful run should move to `active` stays `pending`.

## User stories

- AS a tenant owner whose domain sits behind Cloudflare I WANT the
  add-custom-domain workflow to accept my TXT challenge SO THAT my custom
  hostname actually gets an ingress entry and a certificate.
- AS a tenant owner whose verification fails I WANT the workflow log to name the
  exact record and value I still have to create SO THAT I can fix my DNS without
  opening a support request.
- AS a platform operator I WANT the workflow to report the run's outcome back
  into mctl-api's domains registry SO THAT `GET /api/v1/domains` and the
  cluster's actual ingress configuration do not silently disagree.
- AS a platform operator I WANT the workflow to fail loudly and legibly when its
  mctl-api credential is missing SO THAT a mis-namespaced run is not mistaken
  for a DNS problem.
- AS a security reviewer I WANT the workflow pod to stop carrying the Backstage
  external-access token once Backstage is no longer in this path SO THAT the
  pod's credential set matches the calls it actually makes.

## Acceptance criteria (EARS)

- WHEN the add-custom-domain workflow reaches the DNS verification step THE
  SYSTEM SHALL obtain its verdict from
  `POST ${MCTL_API_URL}/api/v1/domains/verify` with body
  `{"team":..., "service":..., "domain":...}` and an
  `Authorization: Bearer ${MCTL_API_TOKEN}` header, and SHALL NOT invoke `dig`.
- WHEN the verify response has `.verified == true` THE SYSTEM SHALL continue to
  the git edit and push steps unchanged.
- IF the verify response has `.verified != true` THEN THE SYSTEM SHALL fail the
  step with a non-zero exit code and SHALL print `.reason`, `.expected_record`
  and `.expected_value` from the response body before exiting.
- IF the verify call returns a non-2xx status, times out, or returns a body that
  cannot be parsed THEN THE SYSTEM SHALL fail the step and SHALL print the HTTP
  status and the raw response body, and SHALL NOT treat an unparseable response
  as a negative verdict indistinguishable from a genuine DNS miss.
- IF `MCTL_API_TOKEN` is empty when the script starts THEN THE SYSTEM SHALL fail
  the step immediately with a message naming the missing
  `mctl-api-service-token` secret and the `argo-workflows` namespace, before any
  DNS, git or API call is attempted.
- WHEN the ingress and TLS changes have been pushed successfully (or were
  already present) THE SYSTEM SHALL `PATCH ${MCTL_API_URL}/api/v1/domains/{id}`
  with `{"status":"active"}` for the row whose `.domain` equals the requested
  domain.
- IF the workflow terminates in any phase other than `Succeeded` THEN THE SYSTEM
  SHALL attempt one `PATCH ${MCTL_API_URL}/api/v1/domains/{id}` with
  `{"status":"failed","error":...}` carrying the failure message.
- WHILE the exit handler runs THE SYSTEM SHALL exit `0` regardless of whether
  the domain row exists, the registry is reachable, or the PATCH succeeds, so
  that reporting a failure never masks or replaces the original failure.
- WHILE the domain is already present in `ingress.hosts` (the `ALREADY_PRESENT`
  branch at line 212) THE SYSTEM SHALL skip the git edit and push but SHALL
  still issue the `active` PATCH, preserving today's reconcile-on-rerun
  behaviour.
- WHEN this change is applied THE SYSTEM SHALL remove the `BACKSTAGE_TOKEN`
  environment variable and the Backstage domain-list and `/activate` calls
  (lines 59-81 and 315-353) from `wft-add-custom-domain.yaml` only, and SHALL
  leave the `backstage-workflow-token` ExternalSecret in place because
  `wft-remove-custom-domain.yaml` still consumes it.
- WHILE the platform-domain rejection block (lines 124-150) exists THE SYSTEM
  SHALL leave it byte-for-byte unchanged.
- WHEN the workflow pod needs to reach mctl-api THE SYSTEM SHALL read the base
  URL from the `MCTL_API_URL` key of the `mctl-platform-config` ConfigMap,
  already consumed by this template via `envFrom`.
- WHEN the workflow's verification method changes THE SYSTEM SHALL update the
  three platform-skill copies that still instruct users to create a CNAME
  (`platform-gitops/mcp/mctl-platform/SKILL.md`,
  `platform-gitops/platform-skills/catalog/mctl-platform/references/tools.md`,
  `.github/skills/mctl-platform/SKILL.md`) to describe the TXT challenge with
  the CNAME retained as a fast path, and SHALL leave the platform-domain
  paragraph in those files verbatim.
- WHEN the manifests are validated in CI THE SYSTEM SHALL pass `yamllint` and
  `kubeconform` in `.github/workflows/validate-manifests.yml` and
  `.github/workflows/yamllint.yml` with no new findings.

## Out of scope

- Any change to `wft-remove-custom-domain.yaml`. It still calls Backstage and
  still needs `backstage-workflow-token`; migrating it is a separate issue.
- Any change to mctl-api. Tasks 1-9 of the `issue-262` proposal shipped in
  `mctl-api#264` and are treated as given.
- Retiring the `backstage-workflow-token` ExternalSecret
  (`platform-gitops/argo-workflows/secrets/backstage-workflow-token.yaml`) or
  its Vault path.
- Rewording the platform-domain rejection message; shipped in `mctl-api#263`
  and `mctl-gitops#1080`.
- Changing HTTP-01 issuance, the `custom-domain-cert.yaml` Certificate, or the
  `ingress.hosts` / `ingress.tls` edit logic.
- Moving the workflow between namespaces. That routing decision lives in
  mctl-api's `internal/operations/executor.go`, not in this repo.
- Deleting the mctl-portal `custom-domains` plugin or its table.

## Open questions

- The in-template comment at lines 68-81 says this workflow "today runs in the
  TENANT namespace", while the `issue-262` design cites
  `internal/operations/executor.go` lines 89-100 as having already moved
  add/remove-custom-domain to `argo-workflows`. One of the two is stale.
  Proceeding on the assumption that the executor change has landed and the
  template comment is out of date, but mounting the token with
  `optional: true` plus an explicit empty-token preflight so a tenant-namespace
  run fails with a legible message instead of a `CreateContainerConfigError`.
- `POST /api/v1/domains/verify` is documented to return `{verified, method,
  reason, expected_record, expected_value}`; whether it also echoes the row
  `id` is not stated. Proceeding by resolving the id with
  `GET /api/v1/domains?team=&service=` and selecting the entry whose `.domain`
  matches — structurally identical to today's Backstage lookup at line 329. If
  verify does return `id`, the extra GET can be dropped in a follow-up.
- The Vault path for the service token is assumed to be
  `platform/mctl-agent/tokens` property `mctl-api-token`, the value mctl-api
  itself reads as `MCTL_AGENT_SERVICE_TOKEN`
  (`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`
  lines 39-42). If the platform prefers a distinct token for the workflow tier,
  only the `remoteRef` in the new ExternalSecret changes.
- Whether the `active` PATCH should be issued before or after ArgoCD has
  actually synced the ingress. Proceeding with "after the push succeeds", which
  matches the ordering and the reasoning already written into lines 307-311.
