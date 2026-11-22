# Design: issue-376-spike-mcp-apps-write-once-run-across-ai

Revision 3. It answers the independent evidence-based review of revision 2
(REQUEST_CHANGES, 1 P1 / 4 P2, reviewed blobs: requirements `3146c36d9d73`,
design `b81b3c1891ed`, tasks `ea98a443e402`, all re-hashed this run with
`git hash-object` and matching). Only the impacted parts changed. The
phase 0 boundary is preserved: evidence infrastructure in `mctlhq/.github`
only, after separate owner approval. The read-only PoC defenses (four
isolation layers, fail-closed preflight, T7-T11) and the #650/#852 gates are
unchanged.

## Finding-to-change matrix (revision 3)

| Finding | Change in revision 3 | Negative test | Where |
| --- | --- | --- | --- |
| P1-AP-R2-01 Route-scoped G1 contradicted the immutable-bundle invariant | One canonical `bundle_sha256` per (app, release), declared in a `releases` table, compared across all core hosts and all routes. The digest covers only the `resources/read` content bytes; route- or host-specific `_meta` (including `ui.domain`) and capture evidence are separate fields. A Portal-side transformation is `failed` + `portal_limit` and makes only that route NO-GO; it is never an accepted second digest. A server-side difference is `server_defect`/`bundle_defect` and G1 NO-GO. | T2a-T2d: same app/release, `cf-portal` digest differs -> rejected unless `portal_limit` with route NO-GO; two "supported" digests -> rejected; cross-host mismatch on `direct` -> G1 NO-GO | sec. 2, sec. 6, T2 |
| P2-AP-R2-02 Self-written schema validator not independently validated | The conformance oracle is the pinned `jsonschema==4.25.1` (`Draft202012Validator`), already pinned in `roadmap/requirements.txt` and used by `roadmap/scripts/*.py`. The optional stdlib checker is renamed `lint`, is never cited as conformance, and must agree with the oracle on every fixture. Coverage: every `$defs` entry of the vendored schema gets a generated valid and invalid instance, plus `$ref`, `anyOf`/`oneOf`, `const`/`enum`, `required` and `additionalProperties` cases. The executable browser fixture (B1) stays a separate, mandatory product-repo gate. | T3, T4, T15: oracle rejects each mutated instance; lint/oracle disagreement fails CI; schema keyword the lint does not know -> lint abstains, oracle decides | sec. 1, T3-T4, T15 |
| P2-AP-R2-03 `ui.domain` inferred from CIMD host | Removed. Default is omission. A value is emitted only from an owner-reviewed allowlist entry `{host, documented_format, doc_url, accessed, route_server_url, bound_client}` after a measured cell shows the host needs it. Client identity is a selector only, never proof of the origin. DCR clients (Antigravity uses DCR here) match only an explicit operator binding; zero or multiple matches -> omit and record. | T17: unbound DCR client, CIMD host match without entry, two matching entries, entry without doc URL -> no `ui.domain`; preflight rejects an unreviewed entry | sec. 2 "Sandbox origin", T17, B2 |
| P2-AP-R2-04 mctl-api deployed config search incomplete | Pinned `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` (blob `1f54cb703694935fa34db29262ab7e226a2cfb2d`): Argo app `admins-mctl-api`, project `platform`, chart `mctl-api.git` at `a91f7fb4a92e835f5f562f2cbab3ac2e2519c530` path `helm`, image `ghcr.io/mctlhq/mctl-api:4.173.0`, host `api.mctl.ai`, second source `infra-components/mctl-platform/mctl-api`. Live Argo state separately attempted and not observable; recorded as a gap, not as absence. | n/a (evidence pin; B5 precondition re-observes live state) | Current state, Open questions |
| P2-AP-R2-05 G5 scope inconsistent | A gate scope table fixes the scope of every gate; D1, `matrix.py` and the operator checklist all consume it. G5 is per (app, release): fixture pass plus at least one real core host. `direct` is the required core route; `cf-portal` is optional until independently enabled and never blocks the direct-route verdict. | T16: D1 evaluator fed a `cf-portal` `portal_limit` with all direct gates GO -> ADOPT_* still computed; G5 with fixture pass and zero real hosts -> UNMEASURED | sec. 6, T16 |

Revision 2 changes (P1-01 to P1-05, P2-01 to P2-04, P3-01) are retained as
written in revision 2 and are not repeated here, except where the rows above
supersede them (route-scoped hash rule of P2-04; `ui.domain` selection of
P2-03).

## Current state

### In this repository (`mctlhq/.github` at `60e9db5`, 2026-11-22)

- `roadmap/epics/enterprise-mcp.yaml` (paused) carries MCP Apps in phase
  `extensions`: `mcp-apps` bound to mctl-telegram#569, `mcp-apps-validation`
  bound to #650; success criterion: Apps are accepted only after Portal
  compatibility is measured.
- `roadmap/spikes/tg-mcp-app-live-validation.yaml`: re-scoped 2026-10-27.
  The portal half moved to the mcp-gateway epic (.github#236).
  `lifecycle: parked`, outcomes `SUBMIT_READY | SUBMIT_WITH_LIMITATIONS | NOT_READY`.
  Activation: mctl-telegram#852 closes with a position that permits
  submission, and an operator session with a throwaway identity is
  scheduled. `reviewBy: 2026-11-30`. #376 reuses #650's runbook and session
  and does not activate it.
- `docs/spikes/agent-ui-ag-ui.md` separates MCP Apps (in-host UI) from AG-UI
  (run and event projection). #261 is open.
- `docs/spikes/agent-client-compatibility/` is the house pattern (stdlib
  Python run with `python3 -I`, evidence tags, "unknown is never absence",
  wired into `.github/workflows/workflow-tests.yml`).
- `roadmap/requirements.txt` pins `jsonschema==4.25.1` and `PyYAML==6.0.2`.
  `.github/workflows/workflow-tests.yml` already runs
  `python3 -m pip install --disable-pip-version-check -r roadmap/requirements.txt`
  before the spike test steps, and `roadmap/scripts/publish.py`,
  `ready.py` and `github_graph.py` import `jsonschema.Draft202012Validator`.
  So a real, pinned validator is available in this repo's CI with no new
  dependency. Note: `python3 -I` implies `-s` (no user site-packages), so the
  oracle test step runs as `python3 -m unittest` like the existing
  security-finding steps, or asserts the import first and fails rather than
  skips.
- `roadmap/schemas/spike-definition.schema.json` and
  `roadmap/scripts/validate.py` validate SpikeDefinitions.
- `.github/ISSUE_TEMPLATE/spike.yml`: title `spike: `, labels `spike:scout`,
  `agents:intake`, and the `Source/Question/Outcomes/Lifecycle/Related/Why mctl`
  lines. In revision 2 #376 conformed on title and body with `spike:scout`
  only. Not re-read in revision 3; the owner re-checks before approval.

### Telegram prototype (mctlhq/mctl-telegram; PR #651; read in revision 2 at `25e6485` and `b11b8a2`, not re-read in revision 3)

- `internal/mcpui/app.go`: `ExtensionID "io.modelcontextprotocol/ui"`,
  `ResourceURI "ui://mctl-telegram/triage"`, `MIMEType "text/html;profile=mcp-app"`,
  `Version "0.1.0"`, embedded `triage.html` with SHA-256
  `390a03383cafc2a0272f5fac87e462306a365a07953f267f0760b999c7a50e88` at both
  revisions. This is the candidate canonical digest for (mctl-telegram-triage,
  0.1.0); a fixed bundle in B1 gets a new release and a new digest.
- `internal/mcp/server.go`: line 469 `mcpserver.WithExtensions(mcpui.ExtensionCapability())`;
  line 478 `AddResource(mcpui.Resource(), s.handleReadAppResource)`; lines
  332-339 `toolPassesFilter` (unrecognised filter treated as all; `read-only`
  trusts `ReadOnlyHint`); lines 343-361 `addTool`/`addToolUI` (registration
  independent of the UI link; about 40 tools including `send_message`,
  `delete_messages`, `set_access`, `mint_worker_token`, `revoke_session`,
  `delete_account`); lines 364-374 `handleReadAppResource` checks only
  `auth.From(ctx) != nil`. The resource is served from one embedded constant,
  so a server-side per-route byte difference would be a server defect.
- A heuristic grep found `WithReadOnlyHintAnnotation(true)` on `draft_reply`,
  `get_media`, `get_user_audit_log`, `get_acquisition_report` and others;
  `MCP_TOOL_FILTER=read-only` is not a sufficient PoC boundary (to be
  confirmed by T7).
- `internal/config/config.go`: `MCP_TOOL_FILTER` defaults to `all`, unknown
  values rejected at startup (lines 950-962); `MCP_APPS_ENABLED` and
  `ALLOW_SEND` default false; `MCP_CLIENT_PROFILES` binds `client_id`/`redirect_uri`
  to a profile and `scope_ceiling`, and an empty table restricts no client.
- `internal/toolprofile/toolprofile.go` `CoreReadonly = "core-readonly"`;
  `docs/tool-descriptors.core-readonly.json` lists `get_messages`,
  `get_my_audit_log`, `get_my_identity`, `get_my_send_status`,
  `get_unread_messages`, `list_dialogs`, `list_folders`, `list_topics`,
  `search_messages`.
- `internal/mcpui/triage.html` `static_hypothesis` findings: line 595
  `ui/initialize` with `{}`; line 598 View `tools/list` to the host; line 204
  dispatch on `params.name`; line 196 `size-changed` treated as inbound;
  lines 408/464 send affordance gated on `prepare_send_message`.
- No Node toolchain in mctl-telegram; Go CI (`.github/workflows/build.yml`),
  `cmd/mcpprobe` in-process probe.

### Other candidate consumers (revision 1 inventory, not re-read)

mctl-api `0809fb4` and mctl-glovo `6620f5b` (Go, `mark3labs/mcp-go v1.0.0`);
seerrsense `da0c5a3` (TS, `@modelcontextprotocol/server@^2`); mctl-alice
`cb276d6` (TS, `@modelcontextprotocol/sdk@^1.32.2`); mctl-portal and mctl-web
(no `ext-apps` dependency). None has App resources. "Not found by code
search" is not proof of absence.

### Upstream and vendor sources

Fetched in revision 3 (2026-11-22):
- ext-apps spec `specification/2026-01-26/apps.mdx` (main): `ui.domain` is
  "Optional domain for the view's sandbox origin"; "The format and validation
  rules for this field are determined by each host"; "Servers MUST consult
  host-specific documentation"; examples "Hash-based subdomains (e.g.,
  `{hash}.claudemcpcontent.com`)" and "URL-derived subdomains (e.g.,
  `www-example-com.oaiusercontent.com`)"; "If omitted, Host uses default
  sandbox origin (typically per-conversation)". "The Host and the Sandbox MUST
  have different origins." If `ui.csp` is omitted the host uses a restrictive
  default.
- Claude getting-started: for Claude, `ui.domain` is "the first 32 hex
  characters of the SHA-256 of your server URL, followed by
  `.claudemcpcontent.com`"; a wrong value makes Claude show an error instead
  of the app. Server helpers `registerAppTool()`/`registerAppResource()`
  "generate each host's metadata for you"; `App.connect()` without a
  transport "detects the host and picks the transport". App tools, entry
  points and embedded websites need a remote server; entry points and
  embedded sites need a Verified listing for directory connectors.

Fetched in revision 2 (2026-11-22), unchanged: ext-apps releases `v2.1.0`
(exports `.`, `./app-with-deps`, `./react`, `./react-with-deps`,
`./app-bridge`, `./server`, `./schema.json`); version vocabulary kept
separate (MCP core revision, negotiated `2025-06-18` in Telegram `mcpprobe`,
Apps spec `2026-01-26`, SDK `2.1.0`); `mark3labs/mcp-go` `v1.6.0` with generic
`WithExtensions` only; Antigravity (`v2.34.0+`, `com.google.antigravity/ui`
entrypoints `aux_pane`/`global`/`file`, CLI ignores `_meta.ui.visibility`, no
`ui/resource-teardown`, default-deny CSP, 10 MiB HTML, 4 concurrent
`tools/call`); Claude app tools (View-registered, host calls the View; no
prompt for `app.callServerTool`); Claude entry points (`openai/ui`
global entry); ChatGPT UI page (standard bridge, `openai/*` aliases,
"Avoid branching on a host or product name"); Grok Bot connectors
(account-wide apps; MCP Apps for custom servers not documented). Still not
fetched: OpenAI extensions page, Claude rollout article, Grok overview,
approvals and changelog pages, Antigravity `ui.domain` format (gap, task 3).

Deployed state checked:

- `mctl_get_service_status(labs, mctl-telegram)` (revision 2): Synced and Healthy, image `0.141.0`, host `tg.mctl.ai`.
- `mctl_get_service_status(labs, mctl-telegram-preview)` (revision 2): Synced and Healthy, image `main-b11b8a2`, host `tg-preview.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: `tag "0.141.0"`, `AUTH_REQUIRED "true"`, `ALLOW_SEND "true"`, `MCP_CLIENT_PROFILES` binds only `https://www.town.com/.well-known/oauth-client-id` to `core-reply`, no `MCP_APPS_ENABLED`, no `MCP_TOOL_FILTER`; re-read in revision 3: `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com` (no Antigravity host).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` (revision 2): `tag "main-b11b8a2"`, `ALLOW_SEND "true"`. Neither existing instance qualifies as the PoC instance.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` (revision 3, `git hash-object` `1f54cb703694935fa34db29262ab7e226a2cfb2d`, 924 lines): Argo `Application` `admins-mctl-api` in project `platform`; source 1 `https://github.com/mctlhq/mctl-api.git` `targetRevision a91f7fb4a92e835f5f562f2cbab3ac2e2519c530` (commented as the 4.171.0 release commit) `path: helm`; values `image.repository ghcr.io/mctlhq/mctl-api`, `tag "4.173.0"`; ingress host `api.mctl.ai`; `OAUTH_CIMD_ACCEPT "true"`, `OAUTH_CIMD_ADVERTISE "true"`, `OAUTH_CIMD_ALLOWED_HOSTS "chatgpt.com,claude.ai,vscode.dev,glovo.mctl.ai"`; `OAUTH_ALLOWED_REDIRECT_URIS` includes `https://claude.ai/api/mcp/auth_callback`, `https://chatgpt.com/connector/oauth/*` and `https://antigravity.google/*` (so Antigravity connects via DCR, not CIMD). Source 2 `mctl-gitops.git` `main` path `platform-gitops/infra-components/mctl-platform/mctl-api` (directory lists `c2-machine-users.yaml`, `oidc-zitadel.yaml`, `orchestrator-devloop.yaml`, `zitadel-hook.yaml`; not read). The chart pin (4.171.0 commit) and image tag (4.173.0) differ; this is GitOps intent only.
- `mctl_get_service_status(admins, mctl-api)` (revision 3): "ArgoCD application not found: admins-mctl-api". `mctl_list_services(admins)` (complete: true) lists 8 catalogue apps and not `admins-mctl-api`, consistent with it living in project `platform` outside the catalogue view. `mctl_get_sync_windows(platform, admins-mctl-api)` was refused as outside this run's scope. Live mctl-api state is therefore not observed (gap), and is not inferred from GitOps.
- No real host was exercised. Every host cell is `claim` or `untested` today.

## Proposed solution

### Pre-approval owner check (not implementer work)

Before approving, the owner re-reads #376 against the current
`.github/ISSUE_TEMPLATE/spike.yml` on `main` (title, six lines, labels;
confirm `agents:intake` consumed or restore it deliberately). No workflow is
restarted automatically. Approval scopes the implementer to phase 0
(tasks 1-8) in this repository only.

### 1. Phase 0 artifacts in `mctlhq/.github`

- `docs/spikes/mcp-apps-portability.md`: Question; Non-claims; Evidence
  model; matrix (rendered from JSON); existing-work inventory with
  repo@revision and path; static findings (`static_hypothesis`); ADR; PoC
  plan; security model; gate scope table and outcome table; backlog; risks;
  operator runbook; empty owner decision block.
- `roadmap/spikes/mcp-apps-portability.yaml`: `lifecycle: proposed`,
  outcomes `ADOPT_STANDARD_ONLY | ADOPT_WITH_THIN_HOST_ADAPTERS | DEFER`,
  github issue 376, `evidence.report`, no `decision`, no `epic`; question is
  the issue's Question line verbatim.
- `docs/spikes/mcp-apps-portability/`:
  - `host_matrix.json` (schema in section 2) and `matrix.py` (validator,
    renderer and D1 evaluator over the gate scope table);
  - `schema/ext-apps-2.1.0.schema.json`: the vendored upstream `schema.json`
    from tag `v2.1.0`, with `SOURCE` (repo, tag, path, SHA-256);
  - `conformance.py`: validates a recorded message log. Message validation
    uses `jsonschema.Draft202012Validator` over the vendored schema (the
    oracle; `check_schema` runs first so a schema the validator cannot load
    fails). Lifecycle ordering rules (initialize result before
    `initialized`, no View-to-host `tools/list`, allowed method set) are
    separate, explicit checks. Logs are tagged
    `source: fixture|real_host|static_hypothesis`; only the first two count
    as evidence.
  - `lint.py` (optional): a stdlib structural lint for fast local feedback
    with `python3 -I`. It is never cited as conformance evidence. On a
    keyword it does not implement it abstains (exit code distinct from
    pass/fail); CI fails on any fixture where lint and oracle disagree.
  - `bundle_scan.py`: advisory static scan (`innerHTML`, `eval`, external
    `src`, `navigator.userAgent`, unguarded `window.openai`, host-name
    branches). Prints the SHA-256; never sets a gate.
  - `fixtures/`: valid and invalid matrices (including the route digest
    cases of T2); conformant and non-conformant message logs; a generated
    schema corpus (one valid and one mutated instance per `$defs` entry,
    generated by a deterministic script and committed with the schema
    SHA-256); the Telegram `static_hypothesis` log from `triage.html` at
    `b11b8a2`; a sanitisation-violation artifact; `ui.domain` allowlist
    cases.
  - `tests/`: unittest, wired into `workflow-tests.yml` after the existing
    `pip install -r roadmap/requirements.txt` step.
- `AGENTS.md` `# Spikes` gets one bullet.

The executable browser fixture is not part of phase 0. It remains the
mandatory product-repo gate B1 and the only source of `fixture: pass` for a
bundle.

### 2. Host contract matrix schema

`rows` are contract points (the issue's list, plus "View-registered app
tools" and "teardown"). `columns` are `chatgpt-web`, `chatgpt-mobile`,
`claude-web`, `claude-desktop`, `claude-mobile`, `antigravity-app`, `codex`,
`claude-code`, `agy-cli` and `grok-bot` (exploratory). `routes` are `direct`
(`https://<poc-host>/mcp`, required) and `cf-portal` (optional, status
`not_enabled` until #236 enables it).

A top-level `releases` table holds the one canonical digest per app release:

```
releases: [{app_id, release, bundle_sha256, source_repo, source_commit,
            resource_uri, mime_type}]
```

`bundle_sha256` is the SHA-256 of the App resource's `resources/read`
content bytes (`text`, or decoded `blob`), excluding `_meta`. Each
(row, column, route) cell holds:

```
claim:    {status: documented|not_documented|unknown, url, accessed, quote?}
transport:{status: observed|untested, mcp_protocol_revision?, apps_spec_revision?,
           sdk_version?, route_server_url?, meta_digest?}
fixture:  {status: pass|fail|untested, test_id?, repo_commit?}
observed: {status: real_host_verified|failed|blocked|untested,
           cause?: host_gating|server_defect|bundle_defect|portal_limit|unknown,
           evidence?: {artifact_path, artifact_sha256, endpoint, route, host_build, plan,
                       account_pseudonym, app_id, release, bundle_sha256,
                       server_served_sha256, date, operator_pseudonym}}
```

Route-specific values (`route_server_url`, the digest of the emitted `_meta`,
capture artifacts) live in `transport` and `evidence`, never in the release
digest.

`matrix.py` rules:
- complete `evidence` for `real_host_verified` and `failed`; `cause` for
  `failed` and `blocked`; no field derived from another;
- every `evidence.bundle_sha256` for (app, release) equals the
  `releases` entry, on every core host and every route. A mismatch is valid
  only as `observed: failed`:
  - `route == cf-portal`, `server_served_sha256 == releases.bundle_sha256`,
    `cause == portal_limit`: accepted; the route is NO-GO for that release
    and is listed under "unsupported routes";
  - any other mismatch (`direct`, or a server-served digest that differs):
    `cause` must be `server_defect` or `bundle_defect`, and G1 is NO-GO;
  - a mismatching digest on a cell marked `real_host_verified`, or two
    digests for one (app, release) both on supported routes: rejected;
- more than one `releases` entry for the same (app, release): rejected;
- `grok-bot` never counted toward a gate;
- a sanitisation scan of artifact contents for token-shaped strings,
  `Bearer `, `code=`, email and phone patterns.

Selection of `_meta` without host sniffing:
- When the client advertised the UI extension in `initialize`, the server
  emits the standard `_meta.ui.resourceUri`.
- Vendor keys (`openai/ui`, `com.google.antigravity/ui`) are additive and
  namespaced. If a measured cell needs them, they are emitted statically to
  every client.
- Capability negotiation cannot reveal vendor key needs, which is why those
  keys are static and additive.

Sandbox origin (`ui.domain`), replacing the revision 2 CIMD rule:
- Default: omit. The host then uses its default (typically per-conversation)
  sandbox origin. The Telegram View makes no network calls, so nothing in
  the current design needs a stable origin.
- `ui.domain` is single-valued per resource and its format is host-defined
  (Claude: SHA-256 of the server URL; another host: URL-derived), so one
  static value cannot serve all hosts and its Claude value differs between
  `direct` and `cf-portal` because the server URL differs. A static value is
  therefore not adopted.
- Only after a measured cell shows a core host refuses to render (or
  misbehaves) without it, the owner may add an allowlist entry
  `{host, documented_format, doc_url, accessed, route_server_url, value, bound_client}`
  where `bound_client` is an exact registration the operator bound in the
  product's client profile table (a CIMD `client_id` URL, a pre-registered
  id, or a specific DCR-issued id). The value is computed from the
  documented formula and the route's exact server URL, and recorded in the
  matrix.
- The OAuth client identity selects an entry; it is not evidence of the
  sandbox origin, which only the host renderer determines. The CIMD host
  allowlist (`OAUTH_CIMD_ALLOWED_HOSTS`) is an authentication control and is
  not reused as a `ui.domain` mapping.
- DCR clients have no stable public identity; Antigravity connects via DCR
  on both mctl-api and mctl-telegram configuration. An unbound DCR client,
  a client matching no entry, or matching more than one entry gets no
  `ui.domain`, and the server logs the ambiguity. The preflight rejects an
  entry without `doc_url`, `accessed` or a measured-need reference.
- A `ui.domain` entry is an adapter; it moves D1 from ADOPT_STANDARD_ONLY to
  ADOPT_WITH_THIN_HOST_ADAPTERS and never changes the bundle digest.

### 3. Executable browser fixture (backlog B1, hard prerequisite)

Unchanged from revision 2: in the product repo, load the exact embedded
`triage.html` bytes (SHA-256 asserted) into a sandboxed iframe in headless
Chromium under a strict reference host built on the pinned ext-apps
`app-bridge` 2.1.0; refuse `tools/list` and any method outside the schema;
inject `tool-input`, `tool-result` (no `name`), `host-context-changed`, and
malformed, unknown-method, wrong-source and oversized messages; run teardown
and the no-teardown case; serve `tools/call` from an in-process synthetic
fake; assert DOM, message log (run through `conformance.py`, i.e. the
`jsonschema` oracle) and a screenshot with SHA-256. Recommended toolchain: a
test-only Playwright job; alternative Go `chromedp`. CI-only.

### 4. ADR (the owner decides; recorded in the report)

- **A. Reuse the Telegram implementation directly.** Copies the bridge defects. Kept as first consumer, dropped as template.
- **B. Shared frontend package plus language-native helpers now.** Dropped until D2.
- **C (recommended). Product-local code against a shared contract** (matrix, pinned schema, `conformance.py`, browser fixture pattern). View: vendor the pinned official `App` browser build (`app-with-deps`, SHA-256 recorded); a conformed hand-rolled bridge only with written justification and the same fixture. Server: Go products use `mcp-go` `WithExtensions` plus a local `mcpui`; TS products use ext-apps `./server` `registerAppTool`/`registerAppResource`, whose generated host metadata must still pass the same digest and `_meta` rules. No Node sidecar, no new ingress.

### 5. Read-only PoC and security model

Unchanged from revision 2. The PoC instance (B2, B3) is a separate
deployment, never `tg.mctl.ai` or `tg-preview.mctl.ai`, with four required
layers: (1) registration allowlist `MCP_TOOL_FILTER=core-readonly` with
default-deny for unknown values in `toolPassesFilter`; (2) `MCP_CLIENT_PROFILES`
scope ceilings for each measured client; (3) `ALLOW_SEND=false`, no send,
pin, admin or token tool registered; (4) throwaway or synthetic account.
Startup and the preflight assert registered tools = allowlist, resources =
`{ui://mctl-telegram/triage}`, `ALLOW_SEND=false`, scope ceilings, and (new)
that every `ui.domain` allowlist entry is reviewed and well-formed; any
mismatch aborts before a host connects.

Authorization model: static resource authentication-only (no user data);
user data only through tool calls with `requireScope` and account filters;
UI- and model-originated calls share OAuth, scope, tenant checks and audit;
origin hints are untrusted annotations; correlation via `trace_id` and
work-item id (#306); revocation and fencing tested against measured current
`revoke_session` semantics; CSP empty; no token in the View; Telegram text
via `textContent` and never in `ui/message` or `ui/update-model-context`;
visibility is never authorization; writes excluded.

Second consumer (B5, gated by D1): read-only mctl-api DevLoop Run Inspector
on `mctl_get_work_item`, `mctl_list_work_item_executions`,
`mctl_list_work_item_snapshots`; no approve, decide, abandon or trigger tool.
B5 additionally requires that the live `admins-mctl-api` revision is
observed (not inferred from the bootstrap template pin above).

### 6. Gates, scope, outcome table and decisions

Gate scope table (single source for D1, `matrix.py` and the operator
checklist):

| Gate | Definition | Scope | Evidence required |
| --- | --- | --- | --- |
| G1 Immutable bundle | Every observed digest equals the one `releases` digest | per (app, release), all core hosts, all measured routes | `evidence.bundle_sha256` per cell; `server_served_sha256` |
| G2 Render and refresh | `{}` launch renders, refresh and filter re-call read tools, detail opens | per core host, `direct` route | `real_host_verified` cell |
| G3 Identical read semantics | `structuredContent` of the same calls equal after timestamp normalisation | per core host, `direct` route | capture artifact |
| G4 Headless unchanged | `content[].text` byte-equal to flag-off | per configured headless client (Codex, Claude Code, agy) | T14 plus capture |
| G5 Degradation | unadvertised capabilities and missing teardown leave no broken UI | once per (app, release): B1 fixture pass AND at least one `real_host_verified` core host | T12 result plus one capture |
| G6 Security | T7-T11 pass on the PoC instance; audit for a UI-originated call equals a model-originated call apart from the untrusted annotation | once per PoC instance, plus an audit-equivalence trace per core host that passed G2 | T7-T11 results; per-host trace |

Each gate records GO, NO-GO (our defect), BLOCKED_BY_HOST or UNMEASURED.
`cf-portal` results are recorded per route but are not inputs to G2, G3 or
D1 while the route is `not_enabled`; a Portal transformation of the bundle
is `portal_limit` on that route (see section 2) and does not make G1 NO-GO.
Once #236 independently enables `cf-portal`, the owner may add it as a
required route by an explicit decision recorded in the report.

Outcome table for D1 (first-consumer portability; the owner confirms). "3/3"
means ChatGPT, Claude and Antigravity each have G2 and G3 GO on `direct`,
with G1, G4, G5 and G6 GO:

| Core-host result | Adapter need | Recommended D1 |
| --- | --- | --- |
| 3/3 | none beyond standard `_meta.ui` | ADOPT_STANDARD_ONLY |
| 3/3 | additive static vendor `_meta` keys and/or reviewed `ui.domain` entries only, same digest | ADOPT_WITH_THIN_HOST_ADAPTERS |
| G1 NO-GO (a bundle fork would be needed on `direct`) or G6 NO-GO | any | DEFER (portability or security not achieved) |
| Any NO-GO (our defect) on G2-G5 | any | not a verdict: fix and re-run, up to 2 re-runs, then DEFER |
| 2/3, one core host BLOCKED_BY_HOST or UNMEASURED | any | DEFER with a bounded partial result ("portable on X, Y; Z host-gated") and a revisit trigger |
| 1/3 or 0/3 | any | DEFER |
| G5 has fixture pass but no real host yet | any | UNMEASURED for G5; no verdict |
| No operator session possible (#650 still parked at `reviewBy`) | n/a | stays `proposed`; record UNMEASURED, no verdict |
| 3/3 on `direct`, `cf-portal` `portal_limit` | as above | as the matching row above; report lists `cf-portal` as unsupported for the release |

The Grok Bot row is exploratory and never enters this table.

Stop conditions: any real-account exposure, write call or token in an
artifact (stop and record an incident); preflight mismatch; a host requires
a bundle fork (record and stop that host); 2 failed re-runs.

D2 (shared extraction): only after the second consumer has its own gate
evidence, by measuring the diff between the two products' App code;
`not_reached` when D1 is DEFER or B5 never starts.

### 7. Product order after evidence

Telegram validation (#650), then the DevLoop Run Inspector (mctl-api),
Glovo, SeerrSense and Alice (TS SDK 1.x needs an SDK decision first). No
commitment to production or directory submission.

### 8. Optional Grok Bot row

Unchanged from revision 2: bounded isolated test against the PoC instance
from a throwaway Grok account the owner already holds; initialize/discover,
`tools/list`, one harmless read, extension capability and `ui://` MIME check,
render/refresh if supported else text fallback; account-wide connectors mean
the test account has no other bots or members; cloud-computer and
command-MCP paths out of boundary; catalog cards are not evidence; OAuth and
personal-assistant interoperability stays in mctl-telegram#1379.

## Alternatives

- **Fold #376 into #650.** Dropped: #650 answers a submission question for one product and is parked on #852.
- **A generic MCTL MCP Apps SDK or Node sidecar now.** Dropped: no second consumer yet; revisited at D2.
- **Real-host matrix first with the merged bundle.** Dropped: unobserved bridge defects would be misread as host gating.
- **Host-specific bundles, route-specific bundles or host sniffing.** Dropped: they break G1 and contradict vendor guidance ("Avoid branching on a host or product name").
- **Per-route bundle digests (revision 2 rule).** Dropped in revision 3: it let two builds pass G1 under one release.
- **Self-written stdlib JSON Schema subset as the conformance check.** Dropped as evidence: kept only as optional lint behind the pinned `jsonschema` oracle.
- **Infer `ui.domain` from the CIMD `client_id` host.** Dropped: DCR clients (Antigravity) have no CIMD identity, and OAuth identity is not proof of the renderer's sandbox origin.
- **Use `MCP_TOOL_FILTER=read-only` as the PoC boundary.** Dropped: it trusts per-tool `readOnlyHint`.

## Platform impact

- Migrations: none in phase 0 (docs, JSON, Python, one CI step in `mctlhq/.github`).
- Dependencies: none new. The oracle uses `jsonschema==4.25.1` already pinned in `roadmap/requirements.txt` and installed by `workflow-tests.yml`.
- Backward compatibility: no runtime change. `tg.mctl.ai`, `tg-preview.mctl.ai` and `api.mctl.ai` are untouched. The B2 `core-readonly` filter value and the `ui.domain` allowlist are additive and empty by default.
- Resources: a few CI seconds in phase 0; B1 adds a test-only headless browser job; B3 adds one small isolated deployment for the operator window, removed afterwards.
- Cost and maintenance: under option C each product owns one bundle embedding a pinned official SDK build; one shared contract and schema snapshot lives in this repo. The vendored schema and generated corpus must be re-pinned on each ext-apps upgrade.
- Risks:
  - P1: a mis-annotated tool exposed through the hint-based filter. Mitigation: allowlist filter, T7 enumeration, fail-closed preflight.
  - P1: host gating misread as a defect, or the reverse. Mitigation: separate `claim`/`observed` fields and `cause`.
  - P1: a real-account or token leak in artifacts. Mitigation: throwaway identity, synthetic data, sanitisation validator, stop condition.
  - P1: a second bundle accepted under one release. Mitigation: one `releases` digest, cross-route comparison, T2a-T2d.
  - P2: #650 stays parked past `reviewBy 2026-11-30`. Mitigation: phase 0 and B1-B2 proceed offline; D1 stays UNMEASURED.
  - P2: spec or SDK drift. Mitigation: pin spec `2026-01-26`, ext-apps `2.1.0`, schema hash per cell.
  - P2: the oracle and the vendored schema disagree with the TS types the browser SDK enforces. Mitigation: B1 runs the official `app-bridge` and the oracle on the same log; a disagreement is recorded, not resolved by editing the schema.
  - P2: a wrong `ui.domain` makes a host show an error. Mitigation: omit by default; entries only after measurement and owner review; ambiguity omits.
  - P2: the Portal strips `_meta.ui` or rewrites `resources/read`. Mitigation: `portal_limit` on the optional route; Portal work stays with #236.
  - P3: the official SDK build is large or needs CSP changes. Mitigation: measured, justified hand-rolled fallback.
  - P3: Alice's TS SDK 1.x lags. Mitigation: last in product order.
- Rollback: revert the phase 0 PR. Product slices roll back by unsetting `MCP_APPS_ENABLED` or `MCP_TOOL_FILTER` or emptying the `ui.domain` allowlist; the PoC deployment is removed by reverting its mctl-gitops PR.
