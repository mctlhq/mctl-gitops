# deploy_analyze (Tier 0) and a repo-to-service binding read

## Context

Issue mctlhq/mctl-api#826 is the `analyze` work item of the agent-deploy epic (mctlhq/.github#254,
manifest `roadmap/epics/agent-deploy.yaml`). It builds on the DeployIntent schema delivered by
mctlhq/mctl-gitops#2186 (`platform-gitops/agent-platform/schemas/deploy-intent.schema.json`). An AI
session needs a read-only way to ask mctl "what would it take to run this repository here?" The
answer is either a schema-valid draft `DeployIntent` (Tier 0: a Dockerfile in the repository) or a
reasoned `Unsupported`. The analysis is static: mctl reads a few files at a pinned commit through the
GitHub API. It never clones, builds or runs anything.

Today a repository is tied to a service only in one direction:
`gitops.Reader.ComponentSourceRepo(team, component)` maps a service to its `github.com/source-repo`
annotation. The same issue adds the reverse lookup (repository to services), scoped to the caller's
visible tenants. The analyze result reports it, and DevLoop's `resolve_deploy_target` can later use
it instead of parsing `release-please.yml`. Both reads must fail closed. An unreadable GitHub answer
or gitops checkout is an error, never "absent", "unsupported" or "not bound".

## User stories

- AS an AI session acting for a tenant member I WANT to ask mctl whether a repository at a commit can be deployed as-is SO THAT I get a draft DeployIntent or a precise reason it cannot be deployed, without building anything.
- AS a tenant member I WANT to see which of my tenants' services are built from a given repository SO THAT I know whether a deploy would update an existing service or create a new one.
- AS a platform admin I WANT the same reverse lookup across all tenants SO THAT I can resolve any repository to its services.
- AS a platform operator I WANT every analyze and binding read audited, refusals included SO THAT I can see who probed which repository and what the outcome was.
- AS the DevLoop maintainer I WANT a stable repository-to-service read SO THAT a later change can replace `release-please.yml` parsing in `resolve_deploy_target`.

## Acceptance criteria (EARS)

Input and authorization

- WHEN a caller sends `GET /api/v1/deploy/analyze` with `tenant`, `repository` (`owner/name`) and `revision` THE SYSTEM SHALL validate `repository` against the DeployIntent `source.repository` pattern, `revision` against `^[0-9a-f]{40}$`, and the optional `dockerfile` (default `Dockerfile`) and `context` (default `.`) against the schema's `repoPath` rules (no leading `/`, no `..` segment).
- IF any input is missing, repeated or invalid (a branch or tag name in `revision` included) THEN THE SYSTEM SHALL answer 400 with code `deploy_analyze_invalid_input` and make no GitHub or portal call.
- IF the caller is not a member of `tenant` (`auth.User.HasTenantAccess` is false) THEN THE SYSTEM SHALL answer 403 with code `deploy_tenant_access_denied` and write an audit entry with outcome `denied`.
- IF the repository is bound to the tenant neither in gitops (a service under `services/<tenant>/` whose `github.com/source-repo` annotation equals the repository, case-insensitive) nor in the portal (`repoBoundToTeam` answers `bound: true`) THEN THE SYSTEM SHALL answer 403 with code `deploy_repository_not_bound`, read nothing from GitHub, and write an audit entry with outcome `denied`.
- IF the gitops checkout or a `catalog-info.yaml` cannot be read or parsed, or the portal binding check errors, THEN THE SYSTEM SHALL answer 503 with code `deploy_binding_unavailable` and never treat the repository as "not bound".
- WHILE the repository is public but not bound to the tenant THE SYSTEM SHALL still refuse it: this route serves tenant-owned or connected repositories only.

Reading the repository

- WHEN the caller is authorized THE SYSTEM SHALL first resolve the commit `GET /repos/{owner}/{name}/commits/{revision}` and require a 200 whose `sha` equals `revision`, and only then read files with `GET /repos/{owner}/{name}/contents/{path}?ref={revision}`.
- WHILE reading repository content THE SYSTEM SHALL use only mctl's own GitHub credentials, read only the Dockerfile path and the four root compose names (`compose.yaml`, `compose.yml`, `docker-compose.yaml`, `docker-compose.yml`), cap every response body, and never clone, build, execute or fetch any URL named by repository content.
- IF a GitHub call fails, times out, answers a status other than 200 or the documented 404 for the path, returns a body over the cap, a malformed body, a base64 payload whose decoded length differs from `size`, or a `truncated`/missing content field THEN THE SYSTEM SHALL answer 502 with code `deploy_github_unavailable` (or `deploy_github_malformed`), never `Unsupported`.
- IF the commit lookup answers 404 or 422 THEN THE SYSTEM SHALL answer 422 with code `deploy_revision_unreadable`, never `Unsupported{no_dockerfile}`.
- WHEN the commit resolved and the contents API answers 404 for the Dockerfile path THE SYSTEM SHALL return `supported: false`, `reason: no_dockerfile`.

Tier 0 detection

- WHEN a Dockerfile exists at the requested path and every detector passes THE SYSTEM SHALL return `supported: true`, `tier: tier0`.
- WHEN the final stage (with stages it is built `FROM` by name) declares exactly one TCP `EXPOSE` port and that port is at least 1024 THE SYSTEM SHALL use it as `runtime.port`.
- IF every declared port is below 1024 THEN THE SYSTEM SHALL return `supported: false`, `reason: privileged_port`.
- IF no port, several distinct ports, or an unresolvable variable is exposed THEN THE SYSTEM SHALL add `runtime.port` to `needs_input` (with the candidate ports of 1024 or more, if any) rather than guess.
- WHEN the final stage's `HEALTHCHECK` is a `curl` or `wget` HTTP GET of `localhost`, `127.0.0.1` or `[::1]` on the detected port, with a path matching the schema's `healthPath` pattern THE SYSTEM SHALL use that path as `runtime.healthPath`.
- IF there is no `HEALTHCHECK`, it is `NONE`, or it is anything else THEN THE SYSTEM SHALL add `runtime.healthPath` to `needs_input` and present no guessed path.
- IF the effective `USER` of the final stage is absent, `root`, `0` (with or without a group) THEN THE SYSTEM SHALL return `supported: false`, `reason: runs_as_root`.
- IF a root compose file declares more than one service THEN THE SYSTEM SHALL return `reason: multi_service`. IF it requests `privileged`, `cap_add`, `devices`, host `network_mode`/`pid`/`ipc` THEN `reason: privileged`. IF it maps a host port THEN `reason: host_ports`. IF it asks for a GPU (`deploy.resources.reservations.devices`, `gpus`, `runtime: nvidia`) THEN `reason: gpu`.
- IF the Dockerfile or a compose file exceeds its size cap, is a directory or symlink, or cannot be parsed within the parser's bounds THEN THE SYSTEM SHALL return `supported: false` with `reason` `dockerfile_too_large`, `dockerfile_not_a_file`, `dockerfile_unparseable`, `compose_too_large` or `compose_unparseable`.
- WHILE a result is unsupported THE SYSTEM SHALL answer HTTP 200 with `supported: false`, a machine-readable `reason` from a closed set, and a fixed-template human `message`.

Result

- WHEN an analysis completes THE SYSTEM SHALL return `supported`, `tier` (when supported), `repository`, `revision` (the SHA that was read), `dockerfile`, `context`, `needs_input[]`, `reason`/`message` (when unsupported), `detected` (port, health path, non-root flag, stage count) and `binding` (`tenant` plus the list of services in that tenant bound to the repository, possibly empty).
- WHEN supported and `needs_input` is empty THE SYSTEM SHALL return `draft_intent`: an `apiVersion: deploy.mctl.ai/v1alpha1`, `kind: DeployIntent` object with `environment: preview`, `exposure.mode: internal`, `replicas: 1`, `detection.tier: tier0`. The SYSTEM SHALL validate it against the vendored schema before returning it.
- IF `needs_input` is non-empty or the analysis is unsupported THEN THE SYSTEM SHALL return `draft_intent: null`.
- IF the built draft fails validation against the vendored schema THEN THE SYSTEM SHALL answer 500 with code `deploy_draft_invalid` and never return an invalid draft.
- WHILE building any result THE SYSTEM SHALL include no raw file content, no secret value, no Vault path, and no image or digest field.

Binding read

- WHEN a caller sends `GET /api/v1/deploy/bindings?repository=owner/name` THE SYSTEM SHALL return every `{tenant, service}` whose `catalog-info.yaml` annotation `github.com/source-repo` equals the repository (case-insensitive), limited to tenants the caller can see: all tenants for an admin, and the caller's own tenants (`HasTenantAccess`) for anyone else.
- IF any service directory, `catalog-info.yaml` or the checkout cannot be read or parsed THEN THE SYSTEM SHALL answer 503 with code `deploy_binding_unavailable` and never return a partial list as complete.

MCP, audit, docs

- THE SYSTEM SHALL expose both reads as MCP tools `mctl_deploy_analyze` and `mctl_get_repo_binding`, annotated read-only and non-destructive, calling the REST routes.
- WHEN any analyze or binding read finishes, refused or not, THE SYSTEM SHALL write one audit entry with the caller, `tenant`, `repository`, `revision` (analyze), and outcome (`succeeded`, `unsupported:<reason>`, `denied:<code>`, `error:<code>`).
- THE SYSTEM SHALL document both routes in `internal/openapi/openapi.yaml` and add no new write path.

## Out of scope

- `deploy_plan`, grants, builds, image digests and previews (later items of mctlhq/.github#254).
- Tier 1 (buildpacks) and Tier 2 (an agent-written Dockerfile).
- Switching mctl-agents `resolve_deploy_target` to the new lookup (a separate follow-up issue).
- Accepting a branch or tag in `revision` (v1 accepts only a 40-hex SHA; see Open questions).
- Caller-supplied `port`/`healthPath` overrides on analyze (they belong to `deploy_plan`).
- Reading repositories that mctl's own credentials cannot read (see Open questions).
- Enabling the new MCP tools on the shared Cloudflare portal (`docs/portal-allowlist.json` records them as disabled).

## Open questions

- Credentials for repositories outside `mctlhq`: mctl-api's GitHub credential (`gitOpsTokenSource()` in `cmd/api/main.go`: the GitHub App installation token file, then `GITOPS_REPO_TOKEN`/`GITHUB_TOKEN`) is the mctlhq installation. Tenant repositories such as `mashkovd/payment-llm-pipelines` or `NaMax66/sales-with.ai` live in other accounts, and their GitHub App installations are held by the portal's github-app-connect plugin, not by mctl-api. This proposal reads with mctl's token. A private repository outside its reach therefore fails closed with `deploy_revision_unreadable`, never `Unsupported`. A portal-minted read token per installation is a follow-up decision.
- Ref resolution: the issue allows a ref if it is resolved to a SHA. v1 accepts only a SHA, which is the stricter reading. Ref resolution can be added later without changing the result shape.
- Ambiguous or absent port: the issue asks to pick `needs_input` or `Unsupported`. This proposal uses `needs_input` for absent or ambiguous ports and `Unsupported{privileged_port}` only when every declared port is below 1024.
- Service name in the draft: the schema requires `metadata.service`. This proposal uses the bound service when the tenant has exactly one. Otherwise it uses the repository name normalised to the schema's `name` pattern, or adds `metadata.service` to `needs_input` if normalisation fails. When the tenant has several bound services it adds `metadata.service` to `needs_input` with those services as candidates.
- Schema drift check: the CI step that compares the vendored schema with mctl-gitops `main` needs read access to mctl-gitops. If mctl-gitops is private, the existing `GITOPS_*` CI secret or an App token must be used. The step fails closed when the source cannot be fetched.
