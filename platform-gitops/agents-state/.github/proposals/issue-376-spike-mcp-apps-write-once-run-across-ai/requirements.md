# MCP Apps portability spike: one standard bundle across ChatGPT, Claude and Antigravity (revision 2)

## Context

Issue mctlhq/.github#376 asks whether MCTL can ship MCP-native UI once per
app. That means one domain implementation and one immutable HTML/JS/CSS
bundle per app release, rendered by ChatGPT, Claude and Antigravity through
the standard MCP Apps extension (`io.modelcontextprotocol/ui`, ext-apps spec
`2026-01-26`). Only minimal, capability-driven, server-side `_meta` may
differ between hosts, and headless clients (Codex, Claude Code, agy) must
keep equivalent plain text. Portability must be proven, not assumed.
Existing work comes first:
- the merged Telegram prototype (mctlhq/mctl-telegram#569, PR #651);
- the parked operator validation (#650, SpikeDefinition
  `roadmap/spikes/tg-mcp-app-live-validation.yaml`);
- the Portal and gateway boundary (#35, #44, #236);
- the AG-UI Run Inspector (#258, #261);
- authority and audit (#373, #375);
- the Grok Bot interoperability evidence (mctl-telegram#1379).

This is revision 2. It answers the independent review of 2026-11-22
(REQUEST_CHANGES: 5 P1, 4 P2, 1 P3, against blobs `eeff8c4`, `9ebebf7`,
`8232543`). The phase 0 boundary is unchanged. Phase 0 is evidence
infrastructure in `mctlhq/.github` only, and it needs a separate explicit
owner approval of this proposal. Everything in another repository is a
backlog slice with its own issue and approval. This run is investigator
only: nothing is implemented, deployed, submitted, write-enabled or
restarted. design.md opens with a finding-to-change matrix.

## User stories

- AS the platform owner I WANT a deterministic outcome table over measured gates SO THAT ADOPT_STANDARD_ONLY, ADOPT_WITH_THIN_HOST_ADAPTERS or DEFER follows from evidence, including for partial and host-blocked results.
- AS a product engineer I WANT an executable browser fixture that runs my actual immutable bundle against a strict reference host SO THAT I find bridge defects before an operator spends a real-host session.
- AS an operator extending mctl-telegram#650 I WANT a runbook, an isolated read-only instance with a fail-closed preflight, and a capture format SO THAT host gating and code defects are recorded separately and no real account or write path is exposed.
- AS a security reviewer I WANT read-only isolation enforced at server registration, scope and instance configuration, and verified by raw MCP calls, SO THAT neither UI metadata nor visibility is ever the boundary.
- AS a headless user (Codex, Claude Code, agy) I WANT App-linked tools to return the same plain text SO THAT the App adds presentation without removing capability.

## Acceptance criteria (EARS)

Approval boundary

- WHILE this proposal is not approved by the owner THE SYSTEM SHALL run no implementer, no product change, no deployment and no workflow restart. The issue conformance check (design.md, "Pre-approval owner check") SHALL be a pre-approval owner action, not an implementer task.
- WHEN the owner approves this proposal THE SYSTEM SHALL scope the implementer to the phase 0 tasks in `mctlhq/.github` only. Each backlog slice SHALL need its own issue and explicit approval.

Report and matrix

- WHEN `docs/spikes/mcp-apps-portability.md` is merged THE SYSTEM SHALL contain the host contract matrix (design.md section 2) covering:
  - every contract point the issue lists;
  - the core hosts ChatGPT, Claude and Antigravity;
  - the headless columns Codex, Claude Code and agy;
  - an optional exploratory Grok Bot row;
  - a separate route dimension (`direct`, `cf-portal`).
- THE SYSTEM SHALL record four independent fields per matrix cell: `claim` (vendor documentation, with URL and access date), `transport` (the MCP route and protocol revision actually used), `fixture` (fixture coverage, with test id and commit) and `observed` (real-host execution). No field SHALL be inferred from another.
- IF `observed` is `real_host_verified` THEN THE SYSTEM SHALL carry:
  - an immutable sanitized artifact (path plus SHA-256);
  - the exact endpoint, route, host build and plan;
  - a host-account pseudonym (never a real handle or email);
  - app id, release and bundle SHA-256;
  - the date and an operator pseudonym.
  The validator SHALL reject the cell otherwise.
- THE SYSTEM SHALL scope bundle-hash equality to a single (app, release, route) tuple, never globally, and SHALL mark every untested cell `untested` explicitly.
- WHILE no operator evidence exists THE SYSTEM SHALL contain zero `real_host_verified` cells, and the SpikeDefinition SHALL stay `lifecycle: proposed` with no `decision`.
- WHEN a host fails a contract point THE SYSTEM SHALL record `cause` as one of `host_gating`, `server_defect`, `bundle_defect`, `portal_limit` or `unknown`. A Portal limitation SHALL be a measured result and SHALL NOT trigger a workaround.
- THE SYSTEM SHALL NOT write tokens, cookies, OAuth codes, message text, phone numbers or real chat titles into any artifact. The capture checklist and a validator scan SHALL enforce this.

Bundle conformance

- WHEN a View starts THE SYSTEM SHALL send `ui/initialize` with `protocolVersion`, `appInfo` and `appCapabilities`, and SHALL send `ui/notifications/initialized` only after the result.
- THE SYSTEM SHALL validate every View-to-Host and Host-to-View message against the pinned upstream `@modelcontextprotocol/ext-apps` `schema.json`, with version and SHA-256 recorded. Regex scans SHALL be advisory and SHALL NOT be the sole proof of any security property.
- THE SYSTEM SHALL NOT call `tools/list` from the View to the host. View-registered app tools, where Claude's host calls `tools/list` on the View, are a different direction and SHALL be recorded separately.
- WHEN the View receives `ui/notifications/tool-result` THE SYSTEM SHALL treat `params` as a `CallToolResult` and SHALL NOT dispatch on `params.name`.
- WHEN host context reports theme, dimensions or display mode THE SYSTEM SHALL adapt by feature detection only, and SHALL NOT branch on host name or user agent.
- WHEN the entry tool is called with `{}` THE SYSTEM SHALL render a useful default view. Refresh, filter and detail SHALL use only existing read tools, and app-local actions SHALL affect display only.
- IF a host capability is not advertised, or a host never sends `ui/resource-teardown` (documented for Antigravity), THEN THE SYSTEM SHALL hide the dependent control and keep the view working without a broken frame.
- THE SYSTEM SHALL serve byte-identical resource contents to every host for one (app, release). Host-specific values SHALL appear only in tool or resource `_meta`.

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
- IF the instance configuration does not match the declared PoC profile (an unknown filter value, an extra registered tool or resource, `ALLOW_SEND` not false, a wider scope ceiling) THEN THE SYSTEM SHALL fail closed: startup refused, or the operator preflight aborts before any host connects.
- WHEN any raw MCP client, whatever its origin, calls a consequential capability on the PoC instance THE SYSTEM SHALL refuse it. That covers every tool outside the allowlist, including tools whose `readOnlyHint` is wrong, and every unregistered method. The test SHALL enumerate `tools/list` and `resources/list` against the allowlist.
- THE SYSTEM SHALL authorize the static App resource (no user data, authentication only, as at `server.go:364-374`) separately from user-data tool calls (authentication, `requireScope` and tenant or account filter). Tests SHALL cover both.
- WHEN a UI-originated or model-originated call reaches the server THE SYSTEM SHALL apply the same OAuth validation, scope check, tenant isolation and audit. Any origin hint SHALL be stored as an untrusted annotation and SHALL never change an authorization decision.
- IF a request is cross-tenant, stale, replayed or unauthorized, or uses a revoked session THEN THE SYSTEM SHALL deny it. Revocation and fencing tests SHALL assert the measured current semantics of the product (for mctl-telegram, `revoke_session` and the session store) and SHALL NOT assume immediate revocation.
- THE SYSTEM SHALL place no bearer token, backend credential or tenant selector in the View. CSP SHALL stay empty unless a reviewed origin is required, and `_meta.ui.visibility` SHALL never be treated as authorization.
- WHEN a headless client calls an App-linked tool THE SYSTEM SHALL return byte-equal `content[].text` with `MCP_APPS_ENABLED` on and off.

Gates and decisions

- WHEN the operator run completes THE SYSTEM SHALL evaluate G1 to G6 per core host and route, and the first-consumer decision D1 SHALL follow the outcome table in design.md section 6. No full portability verdict SHALL be issued unless all three core hosts are `real_host_verified` and G1 to G6 are GO.
- IF fewer than three core hosts are measured, or any is host-blocked or unmeasured, THEN THE SYSTEM SHALL record a bounded partial result and recommend DEFER with a named revisit trigger. It SHALL NOT recommend ADOPT_*.
- WHILE D1 is not ADOPT_* and owner-reviewed, with security fixture results attached, THE SYSTEM SHALL NOT start, deploy or link the second consumer.
- WHEN a second consumer has produced its own gate evidence THE SYSTEM SHALL take the shared-extraction decision D2 separately. If D1 is DEFER, D2 SHALL be recorded as `not_reached`.
- THE optional Grok Bot row SHALL NOT change any core gate or decision.

## Out of scope

- Any implementer run before owner approval. Any production deployment, `MCP_APPS_ENABLED=true` on `tg.mctl.ai` or `tg-preview.mctl.ai`, connector or directory submission, or bypass of the #650 and #852 legal and submission gate.
- Write enablement from an App. A future write phase needs its own spike, with exact-payload confirmation, MFA or fresh sign-in, and idempotency.
- A generic platform MCP Apps SDK, a new repository, a Node sidecar, new ingress, or a Portal passthrough workaround (Portal work belongs to #236).
- Live customer data, the owner's real Telegram account, new paid host plans, account linking on Grok, policy widening.
- Replacing AG-UI (#261), or a broad redesign of the Telegram triage view.

## Open questions

- Issue conformance: the title and body now match `.github/ISSUE_TEMPLATE/spike.yml` (re-read at 2026-11-22T01:38:57Z). The labels show `spike:scout` only, and `agents:intake` is absent. That is probably because intake consumes the label on pickup, but this run could not verify it. The owner confirms this before approval. No workflow is restarted automatically.
- Live-run ownership: #650 is `parked` (activation: #852 resolved plus a scheduled operator session, `reviewBy: 2026-11-30`, last updated 2026-10-23). Should #376 wait for that activation, or may the owner schedule a portability-only operator session under #650's runbook with no submission? Proposal: wait by default. The offline fixture work (phase 0 and the T-series in the product repo) proceeds independently.
- Browser harness toolchain: mctl-telegram has no Node toolchain. Recommendation: a test-only Playwright job that uses the pinned ext-apps `app-bridge` as the strict reference host. Alternative: Go `chromedp` with the pinned `schema.json`. Either is CI-only, not a runtime sidecar. The owner picks in the backlog slice B1.
- Bridge implementation: should the hand-rolled bridge be conformed, or should the pinned ext-apps `App` browser build (`app-with-deps` export) be vendored? Default: vendor the official build unless its size or CSP needs are measured as unacceptable (design.md section 4, P3-01).
- `ui.domain`: it is omitted by default because the Telegram View makes no network calls. If a measured host refuses to render without it, the value is selected by the authenticated OAuth client identity (CIMD `client_id` host), never by user agent. That remains an owner-reviewed adapter.
- ChatGPT `openai/ui` global entry: the Claude entry-points page documents `_meta["openai/ui"].entrypoints` and attributes it to the OpenAI MCP extensions. The ChatGPT UI page fetched this run does not mention it, so its ChatGPT `claim` is `unknown` until the extensions page is read.
- mctl-api's deployed revision and MCP surface were not observed in GitOps (no `services/*/mctl-api` path). This must be confirmed before backlog slice B5.
