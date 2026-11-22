# Design: issue-376-spike-mcp-apps-write-once-run-across-ai

Revision 2. It answers the independent review of 2026-11-22
(REQUEST_CHANGES, review snapshot blobs: requirements `eeff8c4ebf1a`,
design `9ebebf751996`, tasks `8232543a9e60`, all re-hashed this run and
matching). The phase 0 boundary is preserved: evidence infrastructure in
`mctlhq/.github` only, after separate owner approval.

## Finding-to-change matrix

| Finding | Change in revision 2 | Where |
| --- | --- | --- |
| P1-01 Read-only isolation is not UI metadata | The PoC instance needs four layers, and a mismatch fails closed: (1) a registration allowlist = `core-readonly` profile, (2) minimum read scope ceilings, (3) `ALLOW_SEND=false` with writes absent, (4) a throwaway account. Raw MCP calls are made to every consequential capability, and `tools/list` is enumerated against the allowlist. This catches mis-annotated tools (evidence: `read-only` filter trusts `readOnlyHint`, which a heuristic grep finds on `draft_reply`, `get_user_audit_log`, `get_acquisition_report`). Tests cover an unknown filter value and the in-package default-to-all (`toolPassesFilter`). Static resource auth is separated from user-data auth. | sec. 5, T7-T11, B2 |
| P1-02 Verdict rule contradicted G2 | A deterministic outcome table covers 3/3, 2/3, fewer, blocked, unmeasured and adapter-needed cases. A full verdict needs all three core hosts and G1-G6 GO. Grok is exploratory only. | sec. 6 |
| P1-03 Second consumer gated on G1-G4 only | The second consumer needs D1 = ADOPT_* (all of G1-G6), owner review and attached security fixture results, before any deployment. Revocation is tested against measured current semantics. Origin hints are untrusted. | sec. 6, B5 |
| P1-04 Task 13 depended on a consumer DEFER prevents | D1 (first-consumer portability) and D2 (shared extraction, only after second-consumer evidence) are split. D2 = `not_reached` under DEFER. Stop conditions and bounded partial results are added. | sec. 6, tasks 9-10, B6 |
| P1-05 Task 0 was implementer work before approval | Task 0 becomes a pre-approval owner check, already partly satisfied: title and body now conform, the label state needs owner confirmation. "No implementer" is reconciled: the implementer runs only after explicit approval and only for phase 0. There is no automatic restart. | sec. "Pre-approval owner check" |
| P2-01 Transcript-only checks | An executable browser fixture in the product repo is a hard prerequisite before any real-host run. It loads the actual bundle bytes under a strict reference host, with event injection, handshake, teardown and no-teardown cases, malformed messages, and DOM and screenshot assertions. Messages are validated against the pinned upstream `schema.json`. Reconstructed transcripts are labelled `static_hypothesis`, and regex scans are advisory. | sec. 3, B1, T3-T5, T12-T13 |
| P2-02 #650 re-scope and Portal ownership | Recorded: #650 is parked on #852 plus an operator session, and Portal moved to #236. #376 does not activate #650 or duplicate Portal work. Offline fixture work is separate from live host tests. | Current state, sec. 4 |
| P2-03 Stale docs, App Tools, Antigravity CLI and teardown, discovery | Vendor pages were re-fetched 2026-11-22 (below). This revision distinguishes Claude View-registered app tools from server `tools/call` and the host approval UX. It records that Antigravity sends no teardown and that its CLI ignores visibility. It defines safe `_meta` selection without sniffing, and separates protocol and SDK versions. | Current state, sec. 2 |
| P2-04 Matrix conflated claim, transport, fixture and observation | Four independent fields per cell. Evidence points to immutable sanitized artifacts with exact endpoint, build, route and account pseudonym. Hash scope is (app, release, route). Untested cells are explicit. | sec. 2 |
| P3-01 Check SDK helpers before choosing a manual bridge | Checked: `mark3labs/mcp-go` offers only the generic `WithExtensions` (already used at `server.go:469`), with no App helper in release notes v1.2.0-v1.6.0. `@modelcontextprotocol/ext-apps` 2.1.0 exports `.`, `./app-with-deps`, `./app-bridge`, `./server`, `./schema.json`. Default: vendor the pinned official `App` browser build, and record a justification for any deviation. | sec. 4 |

## Current state

### In this repository (`mctlhq/.github` at `7a0659c`)

- `roadmap/epics/enterprise-mcp.yaml` (paused) carries MCP Apps in phase
  `extensions`:
  - `mcp-apps` is bound to mctl-telegram#569;
  - `mcp-apps-validation` is bound to #650;
  - success criterion: Apps are accepted only after Portal compatibility is measured.
- `roadmap/spikes/tg-mcp-app-live-validation.yaml`: re-scoped 2026-10-27.
  - The portal half moved to the mcp-gateway epic (.github#236).
  - `lifecycle: parked`, outcomes `SUBMIT_READY | SUBMIT_WITH_LIMITATIONS | NOT_READY`.
  - Activation: mctl-telegram#852 closes with a position that permits submission, and an operator session with a throwaway identity is scheduled. `reviewBy: 2026-11-30`.
  - GitHub state this run: #650 OPEN, last updated 2026-10-23; #852 OPEN; #236 OPEN.
  - #376 asks a portability question and #650 a submission question. #376 reuses #650's runbook and session and does not activate it.
- `docs/spikes/agent-ui-ag-ui.md` separates MCP Apps (in-host UI) from AG-UI
  (run and event projection). #261 is open.
- `docs/spikes/agent-client-compatibility/` is the house pattern this spike follows:
  - stdlib Python run with `python3 -I`;
  - evidence tags;
  - "unknown is never absence";
  - wired into `.github/workflows/workflow-tests.yml`.
- `roadmap/schemas/spike-definition.schema.json` and
  `roadmap/scripts/validate.py` validate SpikeDefinitions (`decision` only
  when `decided`; `parked` requires `activation`).
- `.github/ISSUE_TEMPLATE/spike.yml`: title `spike: `, labels
  `spike:scout`, `agents:intake`, and the `Source/Question/Outcomes/Lifecycle/Related/Why mctl` lines.
  - Issue #376 re-read this run (`gh issue view`, updatedAt 2026-11-22T01:38:57Z).
  - The title and all six lines conform, with `Source: https://antigravity.google/docs/mcp-apps/`.
  - `gh search issues` for that Source finds only #376.
  - Labels: `spike:scout` only.

### Telegram prototype (mctlhq/mctl-telegram; PR #651; read at `25e6485`, `main` now `b11b8a2`, 4 commits ahead, none touching `internal/mcp/server.go`, `internal/mcpui/` or `internal/config/config.go`)

- `internal/mcpui/app.go` declares the App surface:
  - `ExtensionID "io.modelcontextprotocol/ui"`;
  - `ResourceURI "ui://mctl-telegram/triage"`;
  - `MIMEType "text/html;profile=mcp-app"`;
  - `Version "0.1.0"`;
  - the embedded `triage.html`, whose SHA-256 is identical at both revisions: `390a03383cafc2a0272f5fac87e462306a365a07953f267f0760b999c7a50e88`.
- `internal/mcp/server.go` registers the App and filters tools:
  - Line 469 declares the extension via `mcpserver.WithExtensions(mcpui.ExtensionCapability())`.
  - Line 478 is `AddResource(mcpui.Resource(), s.handleReadAppResource)`.
  - Lines 332-339 hold `toolPassesFilter`. Any filter other than `"read-only"` registers everything ("An unrecognised filter is treated as all"). `read-only` keeps tools whose `ReadOnlyHint` is true, so it trusts each tool's own annotation.
  - Lines 343-361: `addTool` and `addToolUI`. Registration does not depend on the UI link. `addToolUI` is used for `list_dialogs`, `list_folders`, `list_topics`, `get_unread_messages`, `get_messages`, `send_message`, `prepare_get_media`, `prepare_send_message` and one more at line 633. About 40 tools are registered in total, including `send_message`, `pin_message`, `delete_messages`, `forward_messages`, `set_access`, `mint_worker_token`, `revoke_session` and `delete_account`.
  - Lines 364-374, `handleReadAppResource`, checks only `auth.From(ctx) != nil`. The static bundle holds no user data, so authentication-only access to it is acceptable. User data arrives only through tool calls, which carry `requireScope` and account filters.
- A heuristic grep of `NewTool` and `WithReadOnlyHintAnnotation(true)` adjacency in `internal/mcp/*.go` at `b11b8a2` lists, beyond the core reads, `draft_reply`, `get_media`, `get_user_audit_log`, `get_acquisition_report`, `list_telegram_identities`, `list_assistants`, `list_broadcasts`, `get_broadcast` and `get_my_notification_preferences`. These are grep-derived and must be confirmed by the enumeration test (T7). The point stands: `MCP_TOOL_FILTER=read-only` is not a sufficient PoC boundary.
- `internal/config/config.go` (at `b11b8a2`) holds the relevant settings:
  - `MCP_TOOL_FILTER` defaults to `all`, and any value other than `all`/`read-only` is rejected at startup (lines 950-962). So config fails closed, while the in-package default does not.
  - `MCP_APPS_ENABLED` defaults to false.
  - `ALLOW_SEND` defaults to false.
  - `MCP_CLIENT_PROFILES` holds per-`client_id` and per-`redirect_uri` profile bindings plus a `scope_ceiling` (#1326). A malformed table aborts startup. An empty table "restricts no client", so a host whose client id is not bound is not restricted by this layer.
- `internal/toolprofile/toolprofile.go`: `CoreReadonly = "core-readonly"`.
  `docs/tool-descriptors.core-readonly.json` lists exactly `get_messages`,
  `get_my_audit_log`, `get_my_identity`, `get_my_send_status`,
  `get_unread_messages`, `list_dialogs`, `list_folders`, `list_topics` and
  `search_messages`. This is the registration allowlist reused in B2.
- `internal/mcpui/triage.html` (read at `b11b8a2`):
  - line 595: `callHost("ui/initialize", {})`, with no `protocolVersion`, `appInfo` or `appCapabilities`;
  - line 598: View `tools/list` to the host;
  - line 204: dispatches on `params.name`;
  - line 196: treats `size-changed` as inbound;
  - lines 408 and 464: a send affordance gated on `tools/list` seeing `prepare_send_message`.
  These are reading-based `static_hypothesis` findings until the browser fixture (B1) observes them.
- No Node toolchain in mctl-telegram (no `package.json`). Its CI is Go
  (`.github/workflows/build.yml`), and it has `cmd/mcpprobe` as an in-process
  probe.

### Other candidate consumers (repo heads from revision 1, not re-read)

The revision 1 inventory stands:
- mctl-api `0809fb4` and mctl-glovo `6620f5b`: Go, `mark3labs/mcp-go v1.0.0`;
- seerrsense `da0c5a3`: TS, `@modelcontextprotocol/server@^2`;
- mctl-alice `cb276d6`: TS, `@modelcontextprotocol/sdk@^1.32.2`;
- mctl-portal and mctl-web: no `ext-apps` dependency.
None has App resources. "Not found by code search" is not proof of absence.

### Upstream and vendor sources (fetched 2026-11-22 this run)

- ext-apps releases: `v2.1.0` (2026-11-10), `v2.0.4`, `v2.0.3`.
  - The spec directories are `2026-01-26` and `draft`.
  - The `package.json` (2.1.0) exports `.`, `./app-with-deps`, `./react`, `./react-with-deps`, `./app-bridge`, `./server` and `./schema.json`.
  - Revision 1 recorded the 2.0.0 note "wire protocol unchanged; 2.x Views run in 1.x hosts".
- Version vocabulary: four numbers are in play, and they are not interchangeable. The matrix records them separately.
  - MCP core protocol revision: extensions were formalised in `2026-07-28`, per the `mark3labs/mcp-go` `WithExtensions` doc comment.
  - Telegram `mcpprobe` negotiated `2025-06-18` (revision 1 reading of `docs/reports/mcp-apps-spike.md`).
  - Apps spec revision `2026-01-26`.
  - ext-apps SDK version `2.1.0`.
- `mark3labs/mcp-go`: latest `v1.6.0` (2026-11-19). Release notes v1.2.0-v1.6.0 do not mention Apps, `ui://`, `resourceUri` or SEP-1865. `server/server.go` has a generic `WithExtensions` only. No App helper was found, and `modelcontextprotocol/go-sdk` was not inspected for helpers (gap).
- Antigravity (`antigravity.google/docs/mcp-apps/`):
  - It renders `ui://` only in the App `v2.34.0+`, and needs the client to advertise `capabilities.extensions["io.modelcontextprotocol/ui"]`.
  - Entry points are `_meta["com.google.antigravity/ui"].entrypoints` of type `aux_pane`, `global` or `file`. File entry tools are hidden from the model.
  - The CLI renders no iframe, reads plain `content`, and "Ignores `_meta.ui.visibility`".
  - "Antigravity does not send `ui/resource-teardown` on close".
  - The iframe CSP is default-deny, with no persistent storage.
  - Limits: 10 MiB HTML, 1 MiB persisted results, 4 concurrent `tools/call` per view.
- Claude app tools (`claude.com/docs/connectors/building/mcp-apps/app-tools`):
  - App tools are View-registered (`app.registerTool`, ext-apps >= 1.7.0). The host calls `tools/list` and `tools/call` on the View, which is the opposite direction to server tools.
  - Claude prompts for approval before an app tool runs, but "When your view calls your own server's tools with `app.callServerTool`, the user doesn't see the prompt".
  - App tools are available to a limited set of organizations, need the unified Chat and Cowork experience, and need a remote connector.
- Claude entry points: global entry is `_meta["openai/ui"].entrypoints: [{type: "global"}]` plus `ui.resourceUri`.
  - Visibility must include `model`.
  - Limited organizations; Verified or custom connectors only, never Community.
  - Up to about two hours to propagate.
  - The `fullscreen` display mode is used if declared.
  - Starting from `{}` is required.
- ChatGPT (`developers.openai.com/plugins/build/chatgpt-ui`):
  - It "implements the open MCP Apps standard" over a postMessage JSON-RPC bridge (`ui/initialize`, `tool-input`, `tool-result`, `ui/message`, `ui/update-model-context`).
  - `openai/outputTemplate`, `openai/widgetCSP` and `openai/toolInvocation/*` are compatibility aliases.
  - Its guidance: "Feature-detect each extension", "Avoid branching on a host or product name".
  - Display modes: inline card, carousel, fullscreen, PiP.
  - `openai/ui` is not mentioned on this page (gap).
- Grok Bot (`docs.x.ai/grok-bot/computer-and-apps`) and Grok connectors (`docs.x.ai/grok/connectors`):
  - Grok Bot accepts a remote HTTPS custom connector (URL, headers, OAuth client id) or a command MCP server.
  - "Apps are account-wide. A connected app is available to every Bot you run".
  - MCP Apps or interactive UI for custom servers is not mentioned on either page, so it is `unknown`.
  - The connectors page does not name Grok Chat versus Grok Bot.
  - The Grok Bot overview, approvals and changelog pages were not fetched (gap).
- Not re-fetched this run: the ext-apps spec text (carried from revision 1), the OpenAI extensions page, Claude getting-started and the rollout article. They stay `claim: documented (issue snapshot 2026-11-22)` until task 3.

Deployed state checked:

- `mctl_get_service_status(labs, mctl-telegram)`: Synced and Healthy, image `0.141.0`, host `tg.mctl.ai`.
- `mctl_get_service_status(labs, mctl-telegram-preview)`: Synced and Healthy, image `main-b11b8a2`, host `tg-preview.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - `tag "0.141.0"`, `AUTH_REQUIRED "true"`, `ALLOW_SEND "true"`;
  - `MCP_CLIENT_PROFILES` binds only `https://www.town.com/.well-known/oauth-client-id` to `core-reply`;
  - no `MCP_APPS_ENABLED`, no `MCP_TOOL_FILTER` (so `all`).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  - `tag "main-b11b8a2"`, `AUTH_REQUIRED "true"`, `ALLOW_SEND "true"`;
  - no `MCP_APPS_ENABLED` and no `MCP_TOOL_FILTER` matched by grep.
  - Neither existing instance qualifies as the PoC instance.
- mctl-api: no `services/*/mctl-api` path under the tenants `admins`, `karabu`, `labs`, `namax66` and `redloop`. Its deployed revision and MCP surface were not observed (gap).
- No real host was exercised. Every host cell is `claim` or `untested` today.

## Proposed solution

### Pre-approval owner check (not implementer work)

Before approving this proposal, the owner re-reads #376 against the
current `.github/ISSUE_TEMPLATE/spike.yml` on `main`. The title and body
already conform, and only `spike:scout` is present. The owner either
confirms that `agents:intake` was consumed by intake, or restores it
deliberately. No workflow is restarted automatically by this proposal.
Approval then scopes the implementer to phase 0 (tasks 1-8) in this
repository only.

### 1. Phase 0 artifacts in `mctlhq/.github`

- `docs/spikes/mcp-apps-portability.md`: the report, with these sections:
  - Question; Non-claims; Evidence model;
  - the matrix, rendered from JSON;
  - the existing-work inventory with repo@revision and path;
  - static findings (labelled `static_hypothesis`);
  - ADR; PoC plan; security model; outcome table; backlog; risks; operator runbook;
  - an empty owner decision block.
- `roadmap/spikes/mcp-apps-portability.yaml`: as in revision 1 (`lifecycle: proposed`,
  outcomes `ADOPT_STANDARD_ONLY | ADOPT_WITH_THIN_HOST_ADAPTERS | DEFER`, github issue 376,
  `evidence.report`, no `decision`, no `epic`). The question is the issue's Question line verbatim.
- `docs/spikes/mcp-apps-portability/` (stdlib Python, `python3 -I`):
  - `host_matrix.json` (schema in section 2) and `matrix.py`, a validator and renderer;
  - `schema/ext-apps-2.1.0.schema.json`: the vendored upstream `schema.json` with its SHA-256 and source tag recorded in a sidecar `SOURCE` file;
  - `conformance.py`: validates a recorded message log against the pinned schema, plus lifecycle ordering rules (initialize result before `initialized`, no View-to-host `tools/list`, allowed method set). It validates JSON Schema with a minimal stdlib subset; unsupported keywords make it fail rather than pass. Its input is a log produced by an executable fixture or a real host's devtools. Logs are tagged `source: fixture|real_host|static_hypothesis`, and only the first two count as evidence.
  - `bundle_scan.py`: an advisory static scan (`innerHTML`, `eval`, external `src`, `navigator.userAgent`, unguarded `window.openai`, host-name string branches). It prints the SHA-256 and never sets a gate by itself.
  - `fixtures/`: valid and invalid matrices; a conformant and a non-conformant message log; the Telegram `static_hypothesis` log reconstructed from `triage.html` at `b11b8a2` (expected to fail, labelled as non-evidence); and a sanitisation-violation artifact.
  - `tests/`: unittest, wired into `workflow-tests.yml` like `agent-client-compatibility`.
- `AGENTS.md` `# Spikes` gets one bullet.

### 2. Host contract matrix schema

`rows` are contract points (the issue's list, plus "View-registered app
tools" and "teardown" as separate rows). `columns` are `chatgpt-web`,
`chatgpt-mobile`, `claude-web`, `claude-desktop`, `claude-mobile`,
`antigravity-app`, `codex`, `claude-code`, `agy-cli` and `grok-bot`
(exploratory). The route is a separate key: `direct`
(`https://<poc-host>/mcp`) or `cf-portal`. Each (row, column, route) cell
holds these fields:

```
claim:    {status: documented|not_documented|unknown, url, accessed, quote?}
transport:{status: observed|untested, mcp_protocol_revision?, apps_spec_revision?, sdk_version?}
fixture:  {status: pass|fail|untested, test_id?, repo_commit?}
observed: {status: real_host_verified|failed|blocked|untested,
           cause?: host_gating|server_defect|bundle_defect|portal_limit|unknown,
           evidence?: {artifact_path, artifact_sha256, endpoint, route, host_build, plan,
                       account_pseudonym, app_id, release, bundle_sha256, date, operator_pseudonym}}
```

`matrix.py` enforces these rules:
- complete `evidence` for `real_host_verified` and `failed`;
- `cause` for `failed` and `blocked`;
- no field derived from another;
- `bundle_sha256` equal within one (app, release, route) across browser columns, but never compared across releases or routes;
- a sanitisation scan of `artifact_path` contents for token-shaped strings, `Bearer `, `code=`, email and phone patterns.

Selection of `_meta` without host sniffing:
- When the client advertised the UI extension in `initialize`, the server always emits the standard `_meta.ui.resourceUri`.
- Vendor keys (`openai/ui`, `com.google.antigravity/ui`) are additive and namespaced, so other hosts ignore them. If a measured cell needs them, they are emitted statically to every client, with no per-host selection.
- The only per-host value is `ui.domain`. It is omitted by default. If a measured host requires it, the server selects it from the authenticated OAuth client identity (the CIMD `client_id` host, already validated against `OAUTH_CIMD_ALLOWED_HOSTS`), never from user agent or `clientInfo.name`.
- Capability negotiation cannot reveal vendor key needs, which is why those keys are static and additive.

### 3. Executable browser fixture (backlog B1, hard prerequisite)

This test runs in the product repository: mctl-telegram first, then each
consumer. It works as follows:
- It loads the exact embedded `triage.html` bytes, asserting their SHA-256, into a sandboxed iframe in headless Chromium.
- The parent page is a strict reference host built on the pinned ext-apps `app-bridge` (2.1.0). It answers `ui/initialize` and refuses `tools/list` and any method outside the pinned schema. It injects `tool-input`, `tool-result` (no `name`), `host-context-changed` (theme, dimensions, display modes) and malformed, unknown-method, wrong-source and oversized messages. It runs `ui/resource-teardown`, and separately closes without teardown, which is the Antigravity case.
- `tools/call` is served by an in-process fake backed by synthetic dialogs, with no Telegram network access.
- Assertions cover DOM state (rows rendered with `textContent`, script-like payloads inert, degraded controls absent), the message log (run through `conformance.py`) and a screenshot artifact with its SHA-256.

Recommended toolchain: a test-only Playwright job, because `app-bridge` is the
upstream reference host. The alternative is Go `chromedp` with the vendored
schema. Either is CI-only and adds no runtime sidecar. The bridge fix is
written only after this fixture fails on the static findings.

### 4. ADR (the owner decides; recorded in the report)

- **A. Reuse the Telegram implementation directly** (copy `internal/mcpui`). It copies the bridge defects. It is dropped as a template, but kept as the first consumer.
- **B. Shared frontend package plus language-native helpers now.** This adds a package or repository before two real consumers exist. Dropped for now, and revisited at D2.
- **C (recommended). Product-local code against a shared contract.**
  - The contract is the matrix, the pinned schema, `conformance.py` and the browser fixture pattern.
  - View: vendor the pinned official `@modelcontextprotocol/ext-apps` `App` browser build (`app-with-deps`, SHA-256 recorded) inline in the bundle, instead of the hand-rolled bridge. If the measured size or CSP cost of the official build is unacceptable, a conformed hand-rolled bridge is allowed with a written justification, and it must pass the same fixture. This also enables View-registered app tools later (ext-apps >= 1.7).
  - Server: Go products use `mcp-go` `WithExtensions` plus a local `mcpui` package. TS products use ext-apps `./server` `registerAppTool`.
  - No Node sidecar, no new ingress: the bundle is served by `resources/read` from the existing server.

### 5. Read-only PoC and security model

The PoC instance (backlog B2 and B3) is a separate deployment (for example
`labs/mctl-telegram-appspoc`, name subject to an owner-approved mctl-gitops
PR). It is never `tg.mctl.ai` or `tg-preview.mctl.ai`. Four layers, all required:

1. **Registration allowlist.** A product change adds `MCP_TOOL_FILTER=core-readonly`, which registers exactly the `toolprofile.CoreReadonly` names. `config.go` already rejects unknown values, and `toolPassesFilter`'s in-package default-to-all becomes default-deny (refuse to build the server) for any unrecognised value. The App link set is a subset of that allowlist: `list_dialogs`, `list_folders`, `list_topics`, `get_unread_messages` and `get_messages`. The entry tool is `get_unread_messages {}`.
2. **Scope ceiling.** `MCP_CLIENT_PROFILES` binds each core host's measured client id to `core-readonly`, with a read-only `scope_ceiling`. Because an unbound client is unrestricted by this layer, layer 1 is what covers unknown clients.
3. **Writes off.** `ALLOW_SEND=false`, and no send, pin, admin or token tool is registered.
4. **Account.** Only a throwaway or synthetic Telegram identity is linked.

Startup and a preflight script (B3) assert the declared profile:
- registered tools = the allowlist;
- resources = `{ui://mctl-telegram/triage}`;
- `ALLOW_SEND=false`;
- the scope ceilings.
Any mismatch aborts before a host connects.

Authorization model:
- The static App resource requires authentication only, because it contains no user data (`server.go:364-374`). All user data flows through tool calls with `requireScope` and account filtering.
- UI-originated and model-originated calls share the host's OAuth session. Audit records them identically, and an origin hint is an untrusted annotation that never changes a decision.
- Correlation uses the existing `trace_id` and work-item id (#306).
- Revocation and fencing: the tests use mctl-telegram's current `revoke_session` and session-store behaviour as measured. If revocation is eventually consistent, the test records the observed bound and asserts the bound, not immediacy. #375 receives the measured semantics and does not get new assumptions.
- CSP stays empty. No token is held by the View. Telegram text is rendered via `textContent`, and it never goes into `ui/message` or `ui/update-model-context`.
- Visibility is never authorization. agy is documented to ignore it.
- Writes are excluded. A future write spike keeps `prepare_*` with a one-shot `confirmation_id` bound to the payload hash, MFA or fresh sign-in, and idempotency.

Second consumer (B5, gated by D1 below): a read-only mctl-api DevLoop Run
Inspector on existing tenant-scoped read tools (`mctl_get_work_item`,
`mctl_list_work_item_executions`, `mctl_list_work_item_snapshots`). No
approve, decide, abandon or trigger tool is linked or registered on its
App profile, and it reuses #261's canonical facts.

### 6. Gates, outcome table and decisions

Gates, per core host and route:
- **G1** Immutable bundle: one `bundle_sha256` per (app, release, route), equal to the release hash.
- **G2** Render and refresh: launch with `{}` renders, refresh and filter re-call read tools, detail opens, and the result is `real_host_verified`.
- **G3** Identical read semantics: the `structuredContent` of the same calls is equal after timestamp normalisation.
- **G4** Headless unchanged: Codex, Claude Code and agy `content[].text` is byte-equal to flag-off.
- **G5** Degradation: unadvertised capabilities and missing teardown leave no broken UI, shown by the fixture and at least one real host.
- **G6** Security: T7-T11 pass on the PoC instance, and the audit for a UI-originated call equals that of a model-originated call apart from the untrusted annotation.

Each gate records GO, NO-GO (our defect), BLOCKED_BY_HOST or UNMEASURED.

Outcome table for D1 (first-consumer portability; the owner confirms):

| Core-host result (ChatGPT, Claude, Antigravity) | Adapter need | Recommended D1 |
| --- | --- | --- |
| 3/3 all G1-G6 GO | none beyond standard `_meta.ui` | ADOPT_STANDARD_ONLY |
| 3/3 all G1-G6 GO | additive static vendor `_meta` keys and/or client-identity `ui.domain` only, same bundle | ADOPT_WITH_THIN_HOST_ADAPTERS |
| 3/3 measured but G1 fails (a bundle fork is needed) or G6 NO-GO | any | DEFER (portability or security not achieved) |
| Any NO-GO (our defect) on G2-G5 | any | not a verdict: fix and re-run, up to 2 re-runs, then DEFER |
| 2/3 GO, 1 BLOCKED_BY_HOST or UNMEASURED | any | DEFER with a bounded partial result ("portable on X, Y; Z host-gated") and a revisit trigger |
| 1/3 or 0/3 GO | any | DEFER |
| No operator session possible (#650 still parked at `reviewBy`) | n/a | stays `proposed`; record UNMEASURED, no verdict |

The Grok Bot row is exploratory and never enters this table.

Stop conditions:
- any real-account exposure, write call or token in an artifact (stop the run and record an incident);
- the PoC preflight mismatches;
- a host requires a bundle fork (record and stop that host);
- 2 failed re-runs.

D2 (shared extraction): taken only after the second consumer has its own
gate evidence, by measuring the diff between the two products' App code. It
is recorded as `not_reached` when D1 is DEFER or B5 never starts.

### 7. Product order after evidence

Telegram validation (#650), then the DevLoop Run Inspector (mctl-api),
Glovo, SeerrSense and Alice (TS SDK 1.x, which needs an SDK decision
first). None of these commits to production or a directory submission.

### 8. Optional Grok Bot row

- Bounded isolated test against the PoC instance, from a throwaway Grok account the owner already holds: no new paid spend, no account linking to real services.
- Steps: initialize and discover, `tools/list`, one harmless read, then check for the extension capability and `ui://` MIME.
  - If the UI renders, check render and refresh.
  - Otherwise, record the text fallback.
- Connectors are account-wide ("available to every Bot you run"), so the test account must have no other bots or team members.
- The cloud-computer and command-MCP path is out of the boundary.
- Catalog cards are not taken as evidence.
- OAuth and personal-assistant interoperability stays in mctl-telegram#1379.

## Alternatives

- **Fold #376 into #650.** Dropped: #650 answers a submission question for one product and is parked on #852. #376 reuses its runbook and session.
- **A generic MCTL MCP Apps SDK or Node sidecar now.** Dropped: no second consumer yet, two server languages, extra ingress. Revisited at D2.
- **Real-host matrix first with the merged bundle.** Dropped: unobserved bridge defects would be misread as host gating. The executable fixture comes first.
- **Host-specific bundles or host sniffing.** Dropped: they break G1 and contradict vendor guidance ("Avoid branching on a host or product name").
- **Use `MCP_TOOL_FILTER=read-only` as the PoC boundary.** Dropped: it trusts per-tool `readOnlyHint`, which includes admin and draft tools.

## Platform impact

- Migrations: none in phase 0 (docs, JSON, stdlib Python, one CI step in `mctlhq/.github`).
- Backward compatibility: no runtime change. `tg.mctl.ai` and `tg-preview.mctl.ai` are untouched. The B2 `core-readonly` filter value is additive, and changing the in-package default-to-all only affects values `config.go` already rejects.
- Resources: a few CI seconds in phase 0. B1 adds a test-only headless browser job in mctl-telegram CI. B3 adds one small isolated deployment for the operator window, which is removed afterwards.
- Cost and maintenance: under option C, each product owns one bundle that embeds a pinned official SDK build, and that build needs an upgrade cadence. One shared contract and schema snapshot lives in this repository.
- Risks:
  - P1: a mis-annotated tool exposed through the hint-based filter. Mitigation: the allowlist filter, enumeration (T7) and the fail-closed preflight.
  - P1: host gating (limited organizations, unified experience, Verified or custom only, the two-hour propagation, Antigravity v2.34+) is misread as a defect, or the reverse. Mitigation: the separate `claim`/`observed` fields and `cause`.
  - P1: a real-account or token leak in screenshots or logs. Mitigation: a throwaway identity, synthetic data, the sanitisation validator and the stop condition.
  - P2: #650 stays parked past `reviewBy 2026-11-30`. Mitigation: phase 0 and B1-B2 proceed offline, and D1 stays UNMEASURED.
  - P2: spec or SDK drift between capture and decision. Mitigation: pin spec `2026-01-26`, ext-apps `2.1.0` and the schema hash per cell.
  - P2: the Portal strips `_meta.ui` or `resources/read`. Mitigation: record `portal_limit`; Portal work stays with #236.
  - P3: the official SDK build is large or needs CSP changes. Mitigation: a measured, justified hand-rolled fallback.
  - P3: Alice's TS SDK 1.x lags. Mitigation: it is last in product order.
- Rollback: revert the phase 0 PR. Product slices roll back by unsetting `MCP_APPS_ENABLED` or `MCP_TOOL_FILTER`, and the PoC deployment is removed by reverting its mctl-gitops PR.
