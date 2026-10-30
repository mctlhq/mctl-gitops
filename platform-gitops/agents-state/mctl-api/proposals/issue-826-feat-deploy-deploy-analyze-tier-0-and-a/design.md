# Design: issue-826-feat-deploy-deploy-analyze-tier-0-and-a

## Current state

Repository bindings today:

- `internal/gitops/reader.go` `(*Reader).ComponentSourceRepo(team, component)` reads the
  `github.com/source-repo` annotation from `platform-gitops/services/<team>/<component>/catalog-info.yaml`.
  It fails closed: if the checkout is unavailable (`revisionLocked`), a path is a symlink or not a
  regular file (`statServiceFileLocked`), or the YAML is bad, it returns an error. Only a read checkout
  without the file or annotation yields `ErrSourceRepoNotRegistered`. Names are checked with
  `serviceNameRe`. The API reaches it through `ComponentSourceRepoReader` (`internal/api/handlers_ci_deploy.go`),
  wired as `Options.ComponentSourceRepos` (`internal/api/router.go:77`, `cmd/api/main.go:1107`).
- `(*Reader).ListServices` (`reader.go:1016`) is lenient. A missing services dir returns `nil, nil`,
  and unreadable team or app dirs are skipped with a warning. It cannot serve a fail-closed reverse lookup.
- `internal/api/build_repo_gate.go` `(*Handlers).repoBoundToTeam(ctx, team, repo)` asks the portal's
  github-app-connect plugin (`/api/github-app-connect/repo-binding`) with
  `BackstageGithubAppConnectToken`. A non-200 answer, a malformed body or a missing `bound` is an error,
  never "not bound". `repoFullNameRE` and `isDotOnly` validate `owner/name`. `repoIsPublic` shows the
  house style for GitHub reads: `h.opts.GitHubAPIBaseURL` (default `https://api.github.com`), a 10 s
  `buildRepoClient`, and only GitHub's documented 404 carries meaning.
- `internal/api/handlers_ci_build_binding.go` exposes `repoBoundToTeam` as
  `GET /api/v1/ci/build-repo-binding` (`router.go:1016`). Only the mctl-gitops `build-image.yaml` CI
  token may call it, so it is not reusable as a tenant read. The underlying function is reusable.

Auth, audit, errors:

- Tenant reads (`GetTenant`, `GetService` in `internal/api/handlers_read.go`) gate on
  `user.IsAdmin() || user.HasTenantAccess(name)` (`internal/auth/oidc.go:239`). That check also covers
  bound and read-all agent scopes.
- Audit: `audit.Entry` (`internal/audit/logger.go:27`) is written with `h.logAudit` /
  `h.logAuditCtx` (`internal/api/clientmeta.go`), which fills in client metadata and principal ids.
  Read-side audit helpers already exist, for example `auditSecurity` in `handlers_security_findings.go`
  and `auditRoleRefusal` in `tenant_role.go`.
- `writeError` / `writeErrorCode(w, status, code, msg, details)` (`handlers_read.go:956`).
- Scoped agent run tokens pass through `agentScopeGate` (`internal/api/agent_scope_gate.go`). Their
  route lists live in `internal/auth`, so a new route is denied to scoped runs unless it is listed there.

GitHub credentials: `cmd/api/main.go` `gitOpsTokenSource()` returns `ghtoken.FirstOf(File(GitHub App
token file), Static(GITOPS_REPO_TOKEN), Static(GITHUB_TOKEN))`. This is the mctlhq installation
token, re-read on every use (`internal/ghtoken/source.go`). Tenant GitHub App installations are held
by the portal plugin (`handlers_repos.go` proxies `ListRepos`/`SyncRepos` to it), not by mctl-api.

MCP: tools in `internal/mcp/server.go` are thin REST wrappers (for example `mctl_get_service_config`
uses `s.apiGet`) with `WithReadOnlyHintAnnotation`. `internal/mcp/annotations_test.go` `recordedHints`
pins the tool set and hints. `server_test.go` `TestAllToolsHaveTitleAnnotation` compares the
`tools/list` count with it. `internal/mcp/portal_allowlist_test.go` requires an explicit entry in
`docs/portal-allowlist.json` for every tool.

Libraries: `gopkg.in/yaml.v3` is direct. `github.com/santhosh-tekuri/jsonschema/v6` is already in
`go.mod` as an indirect dependency. There is no Dockerfile parser dependency.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/agent-platform/schemas/deploy-intent.schema.json`: present. draft-07, everything
  `additionalProperties: false`. Requires `metadata.{tenant,service}` (pattern
  `^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$`) and `spec.{environment,source,detection,runtime,exposure}`.
  `runtime.port` must be 1024..65535 and `runtime.healthPath` is required. `detection.tier` is
  `tier0` only. There are no image or digest fields. SHA-256 is
  `cd2e6f1d6dd07a47b878b54ebc47999aafb1890a77a140ccc74b400429e386c4`.
- `$MCTL_GITOPS_ROOT/services/*/*/catalog-info.yaml`: 28 files across tenants `admins`, `karabu`,
  `labs` and `namax66`, with 29 service dirs (one has no catalog-info). `mctlhq/mctl-telegram` and
  `mctlhq/mctl-agents` are each the source of 3 services and `mashkoffdmitry/pelican-libertex-social`
  of 2, so one repository maps to several services. Many sources are outside `mctlhq`
  (`mashkovd/*`, `NaMax66/sales-with.ai`, `EmiliiaMashkova/draw-with-friends`, `umami-software/umami`).
- `mctl_list_services(team=admins)`: 7 catalogue services, all synced. mctl-api itself is not a
  tenant catalogue service, so it has no `services/<tenant>/mctl-api/values.yaml` to read. Its runtime
  env (which GitHub credential is mounted) was therefore not observed. It is inferred only from
  `cmd/api/main.go` and recorded under Open questions in requirements.md.

## Proposed solution

### New package `internal/deployanalyze`

It has no HTTP-handler or auth knowledge, so it can be tested on fixtures alone.

- `github.go`: interface `ContentReader { Commit(ctx, repo, sha) error; File(ctx, repo, sha, path) (FileResult, error) }`.
  `FileResult` is `{Absent bool; Kind string; Data []byte; TooLarge bool}`. The HTTP implementation
  takes the base URL (`Options.GitHubAPIBaseURL`), a `ghtoken.Source`, and a client with a 10 s timeout:
  - `Commit`: `GET /repos/{o}/{n}/commits/{sha}` with `Accept: application/vnd.github+json`. The body is
    capped at 1 MiB (read cap+1 and refuse when over). It requires 200 and `sha == revision`. A 404 or
    422 becomes `ErrRevisionUnreadable`. Anything else becomes `ErrGitHubUnavailable` /
    `ErrGitHubMalformed`.
  - `File`: `GET /repos/{o}/{n}/contents/{escaped path}?ref={sha}`, which is only called after `Commit`
    succeeded. A 404 becomes `Absent`. A 200 must be a JSON object; an array (a directory) becomes
    `Kind: dir`. `type` must be `file` (otherwise `Kind: symlink|submodule`). If `size` is over the cap
    (256 KiB for the Dockerfile, 128 KiB for compose) the result is `TooLarge` and the content is not
    decoded. Otherwise `encoding` must be `base64` and the decoded length must equal `size`; a mismatch
    or missing content is `ErrGitHubMalformed`, the truncation guard. The JSON body itself is capped at
    `4/3*cap + 16 KiB`.
  - Each path segment is escaped with `url.PathEscape`. The token comes from `ghtoken.Resolve` per call
    and never appears in errors (errors carry status and code only).
- `dockerfile.go`: a hand-written bounded parser. Limits are 256 KiB input, 4,000 logical
  instructions, 64 KiB per logical line and 64 stages. It handles comments, `# escape=` and
  `# syntax=` parser directives, line continuations, and heredocs (`<<EOF` / `<<-EOF` bodies are
  skipped up to their terminator within the same bounds). Only `FROM`, `ARG`, `ENV`, `EXPOSE`, `USER`
  and `HEALTHCHECK` are interpreted. Variables `$X` / `${X}` / `${X:-d}` are expanded from the stage's
  `ARG`/`ENV` defaults (and global `ARG`s before the first `FROM`). An unresolvable variable is marked
  "unresolved", never guessed. Stage inheritance: `FROM <earlier stage name or index>` inherits
  `EXPOSE`, `USER`, `HEALTHCHECK` and `ENV`. `FROM <external image>` starts from nothing, because the
  image is never fetched.
- `detect.go`: one detector function per rule over the parsed final stage:
  - `detectUser`: an absent, unresolved, `root` or `0` user part (before `:`) gives `runs_as_root`.
  - `detectPort`: TCP ports, deduplicated. Exactly one port at or above 1024 is used. A set where every
    port is below 1024 gives `privileged_port`. Zero ports, several ports, or an unresolved port add
    `needs_input{field: "runtime.port", candidates: ports >= 1024}`.
  - `detectHealth`: the `HEALTHCHECK CMD` in exec or shell form, tokenised without a shell. It accepts
    `curl` (no `-X`/`--request` other than GET, and no `-d`/`--data*`/`-F`/`-T`/`--upload-file`) or
    `wget` (no `--post-*`/`--method` other than GET), with one `http://(localhost|127.0.0.1|[::1]):<port><path>`
    URL. The port must equal the detected port, and the path must match `^/[A-Za-z0-9._~/-]{0,255}$`
    with no query string. Anything else adds `needs_input{field: "runtime.healthPath"}`.
  - `detectCompose(files)`: decoded into a `yaml.Node` with at most 20,000 nodes and depth 64. Anchors
    and aliases are refused (`compose_unparseable`), which defuses alias bombs. More than one entry
    under `services` gives `multi_service`. `privileged: true`, `cap_add`, `devices`, `network_mode: host`,
    `pid: host` or `ipc: host` give `privileged`. Any `ports` entry with a host part (`"8080:3000"`,
    long syntax `published`) gives `host_ports`. `gpus`, `runtime: nvidia` or
    `deploy.resources.reservations.devices` give `gpu`.
  - Precedence is fixed and documented: Dockerfile availability first, then compose, user, port and
    health. Reasons form a closed enum `Reason` with fixed message templates. No message interpolates
    repository content; only validated numbers are allowed in them.
- `intent.go`: `BuildDraft(tenant, service, repo, sha, dockerfile, context, port, healthPath)` returns
  `map[string]any` with `environment: preview`, `exposure.mode: internal`, `runtime.replicas: 1`,
  `detection.tier: tier0`. `Validate(draft)` compiles the vendored schema once (`sync.Once`) with
  santhosh-tekuri/jsonschema v6, promoted to a direct dependency.
- `schema/deploy-intent.schema.json` is a byte-identical vendored copy, embedded with `//go:embed`.
  `schema.go` holds `SchemaSHA256 = "cd2e6f1d..."` and `SchemaSource = "mctlhq/mctl-gitops:platform-gitops/agent-platform/schemas/deploy-intent.schema.json"`.
- `analyze.go`: `Analyze(ctx, reader, Request) (*Result, error)`. It orchestrates `Commit`, then
  `File(dockerfile)`, then the four root compose names (each a separate `File`; absent is fine), then
  the detectors and the draft. `error` is returned only for read failures or an invalid draft; every
  content verdict is a `Result`.

### Gitops reverse lookup

`(*Reader).ServicesBySourceRepo(repo string) ([]SourceRepoBinding, error)` in `internal/gitops/reader.go`.
`SourceRepoBinding` is `{Tenant, Service string}`. Under one `RLock` it:

1. calls `revisionLocked()` and errors if the checkout is unavailable,
2. reads `platform-gitops/services`; a read error, or the dir being absent in a read checkout, is an error,
3. errors on any team or app entry that is not a regular directory (symlink included). Names that do not
   match `serviceNameRe` are an error too, never a skip,
4. reads each `catalog-info.yaml` through the same steps as `ComponentSourceRepo`, refactored into a
   shared `sourceRepoLocked(team, component)`. A missing file or annotation is skipped; any other error
   is returned,
5. matches with `strings.EqualFold`, then sorts by tenant and service.

`ComponentSourceRepo` keeps its behaviour and calls the shared helper. A new interface
`SourceRepoBindingReader` in `internal/api` is wired as `Options.SourceRepoBindings` from `gitReader`
in `cmd/api/main.go`. Filtering by visible tenant happens in the handler, not the reader.

### HTTP handlers: `internal/api/handlers_deploy_analyze.go`

Both routes are registered in `router.go` next to the other authenticated `/api/v1` reads.

- `GET /api/v1/deploy/analyze?tenant&repository&revision[&dockerfile][&context]`. It is a GET because
  it is a read: it stays outside every write gate and adds no write path.
  1. Validate inputs: exactly one value each, `ciNameRe`-style tenant, the schema's repository pattern
     plus `isDotOnly`, 40-hex revision, and `repoPath` rules for the paths (Go RE2 plus explicit
     leading-`/` and `..` checks). Failure is 400 `deploy_analyze_invalid_input`.
  2. `HasTenantAccess(tenant)` false gives 403 `deploy_tenant_access_denied`.
  3. Binding: call `ServicesBySourceRepo(repo)` and keep the entries for `tenant`. An error gives 503
     `deploy_binding_unavailable`. If there are none, call `repoBoundToTeam(ctx, tenant, repo)`; an error
     gives 503, and false gives 403 `deploy_repository_not_bound`. There is no public-repository
     fallback, unlike `checkBuildRepos`.
  4. `deployanalyze.Analyze` maps `ErrRevisionUnreadable` to 422 `deploy_revision_unreadable`,
     `ErrGitHubUnavailable` to 502 `deploy_github_unavailable`, `ErrGitHubMalformed` to 502
     `deploy_github_malformed`, and an invalid draft to 500 `deploy_draft_invalid`. Error details go to
     `slog` only.
  5. 200 with the `Result` JSON and `binding: {tenant, services: [...]}`.
- `GET /api/v1/deploy/bindings?repository=owner/name` validates the input, calls `ServicesBySourceRepo`,
  and keeps rows where `user.IsAdmin() || user.HasTenantAccess(row.Tenant)`. An error gives 503
  `deploy_binding_unavailable`. It returns `{repository, items, count}`.
- Audit: a helper `auditDeployRead(r, user, op, params, status)` writes one `audit.Entry` per request
  through `h.logAudit`, with `Operation` `deploy.analyze` or `deploy.bindings` and `RiskLevel` low.
  `Parameters` are `tenant`, `repository`, `revision`, `dockerfile`, `context`, `outcome`. `Status` is
  `succeeded`, `denied` or `error`. `Message` is the reason or code. It runs from a `defer` so every exit
  path writes exactly one row. Input-validation refusals are audited too, with the raw input truncated
  to 256 bytes.
- Result JSON shape (Go struct with snake_case tags):
  `supported, tier?, repository, revision, dockerfile, context, draft_intent (object|null), needs_input:[{field, reason, candidates?}], reason?, message?, detected:{port?, health_path?, non_root, stages}, binding:{tenant, services:[]}`.
  The result carries no image, digest, Vault or secret fields; a test asserts the absent key set.
- Draft service name: if the tenant has exactly one bound service, use it. If it has several, add
  `metadata.service` to needs_input with those services as candidates. If it has none, use the
  repository name lowercased, with each run of non-`[a-z0-9-]` characters replaced by `-`, trimmed of
  `-`, and cut to 63; if that still fails the name pattern, add `metadata.service` to needs_input.

### MCP: `internal/mcp/server.go`

- `mctl_deploy_analyze` (title "Analyze Repository For Deploy") takes the required `tenant`,
  `repository` and `revision` and the optional `dockerfile` and `context`, and calls
  `s.apiGet("/api/v1/deploy/analyze?" + url.Values{...}.Encode())`.
- `mctl_get_repo_binding` (title "Get Repository Service Binding") takes the required `repository`.
- Both carry `ReadOnlyHint(true)`, `DestructiveHint(false)` and `IdempotentHint(true)`. The descriptions
  say that Unsupported is a normal answer, that errors are never "absent", that only a 40-hex SHA is
  accepted, and that only tenant-bound repositories are analyzed.
- Add both to `recordedHints` in `annotations_test.go`. Add both to `docs/portal-allowlist.json` with
  `enabled: false` and a reason; enabling them on the portal is a separate owner decision.

### OpenAPI

Add `/api/v1/deploy/analyze` and `/api/v1/deploy/bindings` to `internal/openapi/openapi.yaml` with the
response schemas and every error code. `embed_test.go` already checks that the spec parses.

### Schema drift guard

- Unit test `TestVendoredSchemaPinned`: the SHA-256 of the embedded file equals `SchemaSHA256`.
- Unit test `TestVendoredSchemaMatchesSource`: when `DEPLOY_INTENT_SCHEMA_SOURCE` (a file path) is set,
  it must be byte-identical; when unset, `t.Skip`.
- A `.github/workflows/validate.yml` step fetches the file from mctl-gitops `main` (`gh api ... -H
  'Accept: application/vnd.github.raw'`), sets the env var and runs that test. A failed fetch fails the
  step.

## Alternatives

1. **Clone the repository and use buildkit's Dockerfile parser.** It is more complete, but it breaks the
   no-clone rule, adds a large dependency, and buildkit's parser has no input bounds of its own. Dropped
   in favour of the Contents API plus a small bounded parser that only interprets six instructions.
2. **Reuse `ListServices` or `GET /ci/build-repo-binding` for binding.** `ListServices` skips unreadable
   entries, so a broken checkout would read as "not bound", which the issue forbids. The CI route is
   pinned to the build-image workflow token. Dropped in favour of a new fail-closed reader method and a
   direct call to `repoBoundToTeam`.
3. **Return a draft intent with placeholder port or healthPath when unknown.** This would make
   `draft_intent` always present, but it would either violate the schema (both fields are required) or
   present a guess as fact. Dropped: `draft_intent` is null whenever `needs_input` is non-empty.
4. **Allow public unbound repositories, as `checkBuildRepos` does.** Dropped, because the epic's rule
   until `preconditions` lands is tenant-owned repositories only.

## Platform impact

- **Migrations:** none. There is no database or gitops change, only new read routes and two MCP tools.
- **Backward compatibility:** purely additive. `ComponentSourceRepo` behaviour is unchanged by the
  refactor, and its existing tests (`internal/gitops/source_repo_test.go`) must stay green. The MCP tool
  count rises by 2, updated in `recordedHints`. The portal allowlist adds 2 disabled entries.
- **Resource impact:** at most 6 GitHub API calls per analyze (1 commit, 1 Dockerfile, 4 compose
  probes), against the mctlhq installation's 5,000 requests per hour. Memory is bounded by the caps
  (about 1.5 MB per request worst case). The reverse lookup reads at most N catalog-info files from
  the local checkout.
- **Risks and mitigations:**
  - *Untrusted content (parser DoS, YAML alias bombs):* hard caps, refused aliases, node and depth
    limits, and a fuzz test for the Dockerfile parser.
  - *A read failure reported as Unsupported:* the commit must resolve before any 404 means "absent", and
    the size and length check catches truncation. Each case has a fake-client test.
  - *Information disclosure:* messages are fixed templates. Errors from GitHub or the portal are logged,
    not returned. The binding read is filtered by visible tenants.
  - *Probing other tenants' repositories:* the membership and binding checks run before any GitHub
    call, and refusals are audited.
  - *Private repositories outside mctlhq:* they are unreadable with mctl's token and fail closed as 422
    `deploy_revision_unreadable`. This is documented in the tool description and as an open question.
  - *Schema drift:* the hash pin plus the CI comparison against the source. At runtime the draft is
    validated, so a bug yields 500, never an invalid draft.
  - *Scoped agent runs:* the routes are not added to any `auth.AgentScope` route list, so scoped runs
    are refused by `agentScopeGate`. Adding them for DevLoop is part of the follow-up.
