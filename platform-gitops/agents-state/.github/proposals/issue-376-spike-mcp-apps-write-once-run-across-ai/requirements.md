# MCP Apps portability spike: one standard bundle across ChatGPT, Claude and Antigravity (revision 3)

## Context

Issue mctlhq/.github#376 asks whether MCTL can ship MCP-native UI once per
app. That means one domain implementation and one immutable HTML/JS/CSS
bundle per app release, rendered by ChatGPT, Claude and Antigravity through
the standard MCP Apps extension (`io.modelcontextprotocol/ui`, ext-apps spec
`2026-01-26`). Only minimal, capability-driven, server-side `_meta` may
differ between hosts and routes, and headless clients (Codex, Claude Code,
agy) must keep equivalent plain text. Portability must be proven, not
assumed. Existing work comes first:
- the merged Telegram prototype (mctlhq/mctl-telegram#569, PR #651);
- the parked operator validation (#650, SpikeDefinition
  `roadmap/spikes/tg-mcp-app-live-validation.yaml`, activation on #852);
- the Portal and gateway boundary (#35, #44, #236);
- the AG-UI Run Inspector (#258, #261);
- authority and audit (#373, #375);
- the Grok Bot interoperability evidence (mctl-telegram#1379).

This is revision 3. It answers the independent evidence-based review of
revision 2 (REQUEST_CHANGES: 1 P1, 4 P2, against blobs requirements
`3146c36d`, design `b81b3c18`, tasks `ea98a443`, re-hashed this run and
matching). Only the impacted requirements changed; design.md opens with a
revision 3 finding-to-change matrix. The phase 0 boundary is unchanged:
phase 0 is evidence infrastructure (docs, schema snapshot, matrix,
offline fixtures) in `mctlhq/.github` only, and it needs a separate explicit
owner approval. Everything in another repository is a backlog slice with its
own issue and approval. This run is investigator only: nothing is
implemented, deployed, submitted, write-enabled, linked or restarted. The
read-only PoC defenses and the #650/#852 gates of revision 2 are preserved.

## User stories

- AS the platform owner I WANT a deterministic outcome table over measured gates with an explicit scope per gate SO THAT ADOPT_STANDARD_ONLY, ADOPT_WITH_THIN_HOST_ADAPTERS or DEFER follows from evidence, including for partial and host-blocked results, and a deferred gateway route does not silently block the direct-route verdict.
- AS the platform owner I WANT exactly one canonical bundle digest per (app, release) across every core host and every supported route SO THAT "write once" cannot be satisfied by two builds under one release label.
- AS a product engineer I WANT an executable browser fixture that runs my actual immutable bundle against a strict reference host SO THAT I find bridge defects before an operator spends a real-host session.
- AS a reviewer I WANT message conformance checked by a pinned, real JSON Schema validator over the upstream schema SO THAT a self-written subset checker cannot be the only conformance evidence.
- AS an operator extending mctl-telegram#650 I WANT a runbook, an isolated read-only instance with a fail-closed preflight, and a capture format SO THAT host gating and code defects are recorded separately and no real account or write path is exposed.
- AS a security reviewer I WANT read-only isolation enforced at server registration, scope and instance configuration, and verified by raw MCP calls, SO THAT neither UI metadata, visibility nor OAuth client identity is ever treated as a boundary it is not.
- AS a headless user (Codex, Claude Code, agy) I WANT App-linked tools to return the same plain text SO THAT the App adds presentation without removing capability.

## Acceptance criteria (EARS)

Approval boundary

- WHILE this proposal is not approved by the owner THE SYSTEM SHALL run no implementer, no product change, no deployment and no workflow restart. The issue conformance check (design.md, "Pre-approval owner check") SHALL be a pre-approval owner action, not an implementer task.
- WHEN the owner approves this proposal THE SYSTEM SHALL scope the implementer to the phase 0 tasks (docs, schema snapshot, matrix, offline fixtures and tests) in `mctlhq/.github` only. Each backlog slice SHALL need its own issue and explicit approval.

Report and matrix

- WHEN `docs/spikes/mcp-apps-portability.md` is merged THE SYSTEM SHALL contain the host contract matrix (design.md section 2) covering:
  - every contract point the issue lists;
  - the core hosts ChatGPT, Claude and Antigravity;
  - the headless columns Codex, Claude Code and agy;
  - an optional exploratory Grok Bot row;
  - a separate route dimension: `direct` (required core route) and `cf-portal` (optional until independently enabled under #236).
- THE SYSTEM SHALL record four independent fields per matrix cell: `claim` (vendor documentation, with URL and access date), `transport` (the MCP route and protocol revision actually used), `fixture` (fixture coverage, with test id and commit) and `observed` (real-host execution). No field SHALL be inferred from another.
- IF `observed` is `real_host_verified` THEN THE SYSTEM SHALL carry:
  - an immutable sanitized artifact (path plus SHA-256);
  - the exact endpoint, route, host build and plan;
  - a host-account pseudonym (never a real handle or email);
  - app id, release and the observed bundle SHA-256;
  - the date and an operator pseudonym.
  The validator SHALL reject the cell otherwise.
- THE SYSTEM SHALL declare exactly one canonical `bundle_sha256` per (app, release) in a `releases` table, and SHALL compare every observed `bundle_sha256` for that (app, release) against it across all core hosts and all routes. Route-specific transport and capture evidence SHALL be recorded separately from the bundle digest and SHALL NOT create a second accepted digest.
- IF an observed digest for an (app, release) differs from the canonical digest on any route THEN THE SYSTEM SHALL record the cell as `failed`. When the server-side served digest equals the canonical digest and only the `cf-portal` route differs, `cause` SHALL be `portal_limit` and that route SHALL be NO-GO for the release; otherwise `cause` SHALL be `server_defect` or `bundle_defect` and G1 SHALL be NO-GO. A distinct digest SHALL never be accepted as a permitted release variant.
- THE SYSTEM SHALL mark every untested cell `untested` explicitly.
- WHILE no operator evidence exists THE SYSTEM SHALL contain zero `real_host_verified` cells, and the SpikeDefinition SHALL stay `lifecycle: proposed` with no `decision`.
- WHEN a host fails a contract point THE SYSTEM SHALL record `cause` as one of `host_gating`, `server_defect`, `bundle_defect`, `portal_limit` or `unknown`. A Portal limitation SHALL be a measured result and SHALL NOT trigger a workaround.
- THE SYSTEM SHALL NOT write tokens, cookies, OAuth codes, message text, phone numbers or real chat titles into any artifact. The capture checklist and a validator scan SHALL enforce this.

Bundle conformance

- WHEN a View starts THE SYSTEM SHALL send `ui/initialize` with `protocolVersion`, `appInfo` and `appCapabilities`, and SHALL send `ui/notifications/initialized` only after the result.
- THE SYSTEM SHALL validate every View-to-Host and Host-to-View message against the pinned upstream `@modelcontextprotocol/ext-apps` `schema.json` (version and SHA-256 recorded) using a pinned, independently maintained JSON Schema validator (`jsonschema==4.25.1`, already pinned in `roadmap/requirements.txt`) as the conformance oracle. Any local stdlib checker SHALL be labelled structural lint and SHALL NOT be cited as conformance evidence.
- WHEN the oracle and a local lint disagree on any fixture THE SYSTEM SHALL fail the test and report the disagreement.
- THE SYSTEM SHALL keep regex scans advisory; they SHALL NOT be the sole proof of any security property.
- THE SYSTEM SHALL NOT call `tools/list` from the View to the host. View-registered app tools, where Claude's host calls `tools/list` on the View, are a different direction and SHALL be recorded separately.
- WHEN the View receives `ui/notifications/tool-result` THE SYSTEM SHALL treat `params` as a `CallToolResult` and SHALL NOT dispatch on `params.name`.
- WHEN host context reports theme, dimensions or display mode THE SYSTEM SHALL adapt by feature detection only, and SHALL NOT branch on host name or user agent.
- WHEN the entry tool is called with `{}` THE SYSTEM SHALL render a useful default view. Refresh, filter and detail SHALL use only existing read tools, and app-local actions SHALL affect display only.
- IF a host capability is not advertised, or a host never sends `ui/resource-teardown` (documented for Antigravity), THEN THE SYSTEM SHALL hide the dependent control and keep the view working without a broken frame.
- THE SYSTEM SHALL serve byte-identical `resources/read` contents (the `text` or decoded `blob` of the App resource) to every host on every route for one (app, release). Host- or route-specific values SHALL appear only in tool or resource `_meta`, which is outside the bundle digest.

Sandbox origin (`ui.domain`)

- THE SYSTEM SHALL omit `_meta.ui.domain` by default, so the host uses its default sandbox origin.
- IF a measured `real_host_verified` or `failed` cell shows that a core host requires `ui.domain` THEN THE SYSTEM SHALL emit it only from an owner-reviewed, host-documentation-backed allowlist entry that names the host, the documented format (with doc URL and access date), the route's exact server URL, and the explicitly bound OAuth client registration it applies to.
- THE SYSTEM SHALL treat the OAuth client identity (CIMD `client_id` URL, pre-registered id, or DCR-issued id) only as a selector for a reviewed allowlist entry, never as proof of the sandbox origin; the origin is chosen by the host renderer.
- IF the client is a DCR client not explicitly bound by the operator, matches no entry, or matches more than one entry THEN THE SYSTEM SHALL omit `ui.domain` and record the ambiguity; it SHALL NOT infer a value from the CIMD host, user agent or `clientInfo.name`.

Executable fixture (hard prerequisite for any real-host run)

- WHEN the browser fixture runs THE SYSTEM SHALL load the actual immutable bundle bytes, identified by SHA-256, in a headless browser under a strict reference host. The host SHALL refuse `tools/list` and any method outside the pinned schema, inject `tool-input`, `tool-result` and `host-context-changed`, perform the handshake and the teardown and the no-teardown cases, and capture DOM assertions and a screenshot.
- IF the View receives a malformed, unknown-method, wrong-origin or oversized message THEN THE SYSTEM SHALL ignore it without rendering its content or calling a tool. The fixture SHALL assert this.
- THE SYSTEM SHALL label transcripts reconstructed by reading code as `static_hypothesis`, and SHALL never count them as observed runtime.

Read-only isolation and security

- WHILE the PoC runs THE SYSTEM SHALL use an isolated instance (not `tg.mctl.ai` and not `tg-preview.mctl.ai`) with all of the following:
  - an explicit server registration allowlist equal to the `core-readonly` tool profile;
  - client scope ceilings limited to the minimum read scopes;
  - `ALLOW_SEND=false`;
  - a throwaway or synthetic Telegram account only.
- IF the instance configuration does not match the declared PoC profile (an unknown filter value, an extra registered tool or resource, `ALLOW_SEND` not false, a wider scope ceiling, an unreviewed `ui.domain` entry) THEN THE SYSTEM SHALL fail closed: startup refused, or the operator preflight aborts before any host connects.
- WHEN any raw MCP client, whatever its origin, calls a consequential capability on the PoC instance THE SYSTEM SHALL refuse it. That covers every tool outside the allowlist, including tools whose `readOnlyHint` is wrong, and every unregistered method. The test SHALL enumerate `tools/list` and `resources/list` against the allowlist.
- THE SYSTEM SHALL authorize the static App resource (no user data, authentication only, as at `server.go:364-374`) separately from user-data tool calls (authentication, `requireScope` and tenant or account filter). Tests SHALL cover both.
- WHEN a UI-originated or model-originated call reaches the server THE SYSTEM SHALL apply the same OAuth validation, scope check, tenant isolation and audit. Any origin hint SHALL be stored as an untrusted annotation and SHALL never change an authorization decision.
- IF a request is cross-tenant, stale, replayed or unauthorized, or uses a revoked session THEN THE SYSTEM SHALL deny it. Revocation and fencing tests SHALL assert the measured current semantics of the product (for mctl-telegram, `revoke_session` and the session store) and SHALL NOT assume immediate revocation.
- THE SYSTEM SHALL place no bearer token, backend credential or tenant selector in the View. CSP SHALL stay empty unless a reviewed origin is required, and `_meta.ui.visibility` SHALL never be treated as authorization.
- WHEN a headless client calls an App-linked tool THE SYSTEM SHALL return byte-equal `content[].text` with `MCP_APPS_ENABLED` on and off.

Gates and decisions

- THE SYSTEM SHALL evaluate each gate at the scope fixed in design.md section 6 (gate scope table), and the D1 outcome table, the matrix validator and the operator checklist SHALL use that same scope:
  - G1 per (app, release) across all core hosts and all measured routes;
  - G2 and G3 per core host on the `direct` route;
  - G4 per configured headless client;
  - G5 once per (app, release): browser fixture pass plus at least one `real_host_verified` core host;
  - G6 once per PoC instance (T7-T11) plus an audit-equivalence trace per core host that passed G2.
- WHEN the operator run completes THE SYSTEM SHALL compute D1 from the outcome table in design.md section 6. No full portability verdict SHALL be issued unless all three core hosts are `real_host_verified` on `direct` with G2 and G3 GO, and G1, G4, G5 and G6 are GO.
- WHILE `cf-portal` is not independently enabled THE SYSTEM SHALL treat it as optional: its result SHALL be recorded per route, a `portal_limit` SHALL make only that route NO-GO, and it SHALL NOT block the direct-route D1.
- IF fewer than three core hosts are measured, or any is host-blocked or unmeasured, THEN THE SYSTEM SHALL record a bounded partial result and recommend DEFER with a named revisit trigger. It SHALL NOT recommend ADOPT_*.
- WHILE D1 is not ADOPT_* and owner-reviewed, with security fixture results attached, THE SYSTEM SHALL NOT start, deploy or link the second consumer.
- WHEN a second consumer has produced its own gate evidence THE SYSTEM SHALL take the shared-extraction decision D2 separately. If D1 is DEFER, D2 SHALL be recorded as `not_reached`.
- THE optional Grok Bot row SHALL NOT change any core gate or decision.

## Out of scope

- Any implementer run before owner approval, and any implementer work outside the phase 0 docs/schema/matrix/fixture slice. Any production deployment, `MCP_APPS_ENABLED=true` on `tg.mctl.ai` or `tg-preview.mctl.ai`, connector or directory submission, operator host linking, or bypass of the #650 and #852 legal and submission gate.
- Write enablement from an App, and any payment. A future write phase needs its own spike, with exact-payload confirmation, MFA or fresh sign-in, and idempotency.
- A generic platform MCP Apps SDK, a new repository, a Node sidecar, new ingress, or a Portal passthrough workaround (Portal work belongs to #236).
- Live customer data, the owner's real Telegram account, new paid host plans, account linking on Grok, policy widening.
- Replacing AG-UI (#261), or a broad redesign of the Telegram triage view.
- Asserting mctl-api live state from GitOps alone.

## Open questions

- Issue conformance: the title and body matched `.github/ISSUE_TEMPLATE/spike.yml` when re-read in revision 2 (2026-11-22T01:38:57Z); the labels showed `spike:scout` only, without `agents:intake`. The issue body has since gained the revision 2 review section. The owner re-checks conformance before approval. No workflow is restarted automatically.
- Live-run ownership: #650 is `parked` (activation: #852 resolved plus a scheduled operator session, `reviewBy: 2026-11-30`). Default: #376 waits for that activation; the offline phase 0 and B1-B2 proceed independently. The owner may instead scope a portability-only session under #650's runbook with no submission.
- Browser harness toolchain: mctl-telegram has no Node toolchain. Recommendation: a test-only Playwright job that uses the pinned ext-apps `app-bridge` as the strict reference host. Alternative: Go `chromedp`. Either is CI-only. The owner picks in B1.
- Bridge implementation: default is to vendor the pinned official ext-apps `App` browser build (`app-with-deps`); the ext-apps `./server` helpers (`registerAppTool`, `registerAppResource`) are documented by Claude as generating "each host's metadata for you", which matters for TS consumers but not for the Go Telegram server.
- `ui.domain`: omitted by default (the Telegram View makes no network calls). Claude documents `<first 32 hex of SHA-256(server URL)>.claudemcpcontent.com`; the spec cites URL-derived `*.oaiusercontent.com` as another host's example; Antigravity's format was not found. Because one resource carries one `ui.domain` and formats differ per host and per server URL (route), any emitted value needs a reviewed per-host, per-route entry. Antigravity authenticates via DCR (its redirect `https://antigravity.google/*` is allowlisted, but `antigravity.google` is not in `OAUTH_CIMD_ALLOWED_HOSTS`), so it can only be selected by an explicit operator binding or not at all.
- mctl-api live state: GitOps pins `admins-mctl-api` (bootstrap template blob `1f54cb70`, chart `a91f7fb4` described as the 4.171.0 release commit, image `4.173.0`), but the live Argo application was not observable from this run (`mctl_get_service_status` found no `admins-mctl-api`; sync-window reads are outside this run's scope). This must be observed before backlog slice B5.

## Non-blocking adjacent-UI research (owner screenshots, 2026-11-22)

This is a comparison appendix within Phase 0 task 7, **not** a fourth MCP Apps
host, new renderer implementation or an additional G1–G6 acceptance gate.
The core three-host MCP Apps portability contract above is unchanged.

- WHEN the Phase 0 report is written THE SYSTEM SHALL briefly distinguish
  MCP Apps SEP-1865 (pre-built sandboxed HTML/JS bundle), A2UI 1.0 (agent-authored
  declarative component tree rendered by a host-owned trusted catalog),
  A2UI-over-MCP (`application/a2ui+json` / `a2ui://` resource or tool
  response requiring an A2UI-capable renderer), A2UI *inside* an MCP App
  (the App bundle hosts the renderer), AG-UI (#258/#261: agent↔user event,
  state and action transport), and GPUI (Rust desktop rendering engine).
- THE SYSTEM SHALL pin the A2UI protocol version and each actual renderer
  version separately and record undocumented AI-host support as `unknown`;
  MCP Apps compatibility SHALL NOT imply A2UI-over-MCP rendering support.
- THE SYSTEM SHALL identify one later **synthetic read-only** Personal
  Assistant/DevLoop status-or-choice-card evaluation, including catalog
  allowlisting, schema validation, accessibility, state/replay handling,
  host-vs-app render options, and a plain-text fallback. This is a backlog
  hypothesis only, coordinated with #258/#261; no product runtime or agent
  approval path changes are authorized here.
- THE SYSTEM SHALL document GPUI as `DEFER_NATIVE_DESKTOP`: it cannot
  replace an MCP Apps iframe, run as an AI-host transport, or establish
  cross-host portability. Any desktop GPUI/Tauri/Electron benchmark needs a
  separate explicit owner gate and MCTL workload measurements.
- A generated component action SHALL never be treated as authorization.
  Consequential tool calls retain existing canonical identity, tenant
  policy, exact-payload approval, fencing, idempotency and audit controls.

Sources to record in the report:
- Google A2UI 1.0 (2026-11-11):
  https://developers.googleblog.com/en/a2ui-10-build-delightful-fast-reliable-agentic-experiences/
- A2UI + MCP Apps design patterns (2026-06-17):
  https://developers.googleblog.com/en/a2ui-and-mcp-apps/
- Official A2UI source: https://github.com/a2ui-project/a2ui
- GPUI: https://gpui.rs/examples/
- Owner screenshots of Better Stack's A2UI (2026-11-21) and GPUI
  (2026-11-20) videos are discovery context, not a watched transcript or
  reproduced benchmark.
