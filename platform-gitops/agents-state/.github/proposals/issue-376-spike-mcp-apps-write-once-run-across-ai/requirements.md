# MCP Apps portability spike: one standard bundle across ChatGPT, Claude and Antigravity

## Context

Issue mctlhq/.github#376 asks whether MCTL can ship MCP-native UI (MCP Apps,
SEP-1865, `io.modelcontextprotocol/ui`) once per app: one domain
implementation and one versioned HTML/JS/CSS bundle. The same bundle would
render in ChatGPT, Claude and Antigravity, and only capability-driven
server-side metadata would differ between hosts. The issue requires that
portability is proven with evidence rather than assumed. It also requires
that existing work is reused first: the merged Telegram prototype
(mctlhq/mctl-telegram#569, PR #651), its operator validation spike
(mctlhq/mctl-telegram#650), the Portal boundary (#35, #44) and the AG-UI Run
Inspector (#258, #261). Authority and audit must also be wired into #373 and
#375. The run is investigator-only. Nothing is implemented, deployed,
submitted to a directory or write-enabled without separate owner approval.

This matters because the shipped prototype has only in-process fixture
evidence: the `mcpprobe` row in `docs/reports/mcp-apps-spike.md`, Claude and
ChatGPT "not measured here". Read against the ext-apps specification
`specification/2026-01-26/apps.mdx`, its View bridge (`internal/mcpui/triage.html`)
diverges in three places. Each would break initialisation or rendering in a
conformant host. Running a real-host matrix against that bundle first would
measure our defects, not host gating. This proposal defines the contract
matrix, the ADR options, a bounded read-only PoC, security tests, measurable
GO/NO-GO gates and a phased backlog. Its deliverables stay in this
repository: a spike report, a SpikeDefinition and a stdlib conformance and
matrix reference model.

## User stories

- AS the platform owner I WANT an evidence-tagged host contract matrix SO THAT I can choose ADOPT_STANDARD_ONLY, ADOPT_WITH_THIN_HOST_ADAPTERS or DEFER from measured facts rather than vendor marketing.
- AS a product engineer (Telegram, mctl-api, Glovo, SeerrSense, Alice) I WANT one conformance contract and fixture host to test my App bundle against SO THAT I find spec defects before an operator spends a real-host session.
- AS an operator running mctlhq/mctl-telegram#650 I WANT a runbook that produces sanitized screenshots, protocol transcripts and audit traces per host SO THAT host gating and code defects are recorded separately.
- AS a security reviewer I WANT every UI-originated call to pass the same server-side OAuth, scope, tenant and audit path as a model-originated call SO THAT app-only visibility or a browser token is never a security boundary.
- AS a headless user (Codex, Claude Code, agy) I WANT the same tools to keep returning equivalent plain text SO THAT the App adds presentation without removing capability.

## Acceptance criteria (EARS)

Report and matrix

- WHEN the spike report `docs/spikes/mcp-apps-portability.md` is merged THE SYSTEM SHALL contain a host contract matrix with one row per contract point (discovery and `initialize` extension negotiation, `tools/list` `_meta.ui.resourceUri`, `resources/read` with `text/html;profile=mcp-app`, `ui/initialize` lifecycle, `structuredContent` plus text fallback, View `tools/call`, app-only tools, `ui/update-model-context` and `ui/message`, theme, size and display modes, global/side/file entry points, remote OAuth mode, CSP and `ui.domain`, mobile versus desktop/CLI, packaging and plan/rollout limits) and one column per host (ChatGPT, Claude web/desktop, Antigravity app, Codex, Claude Code, agy headless).
- THE SYSTEM SHALL tag every matrix cell with exactly one of `documented`, `fixture_tested`, `real_host_verified`, `unavailable`, `unknown`.
- IF a cell is tagged `real_host_verified` THEN THE SYSTEM SHALL carry an evidence reference: date, host build/plan, endpoint, bundle SHA-256, a sanitized screenshot path or protocol transcript path, and an operator handle. The matrix validator SHALL reject the cell otherwise.
- IF a cell is tagged `documented` THEN THE SYSTEM SHALL carry the vendor URL and access date, and SHALL NOT be counted toward any gate.
- WHILE no operator evidence has been captured THE SYSTEM SHALL contain zero `real_host_verified` cells and the spike manifest SHALL stay at `lifecycle: proposed` with no `decision` block.
- WHEN a host fails a contract point THE SYSTEM SHALL record whether the cause is host gating (plan, rollout, allowlist, Portal), a server defect or a bundle defect. A Portal limitation SHALL be recorded as a measured result and SHALL NOT trigger a workaround.

Bundle conformance (applies to any App bundle, starting with Telegram triage)

- WHEN a View starts THE SYSTEM SHALL send `ui/initialize` carrying `protocolVersion`, `appInfo` and `appCapabilities` (including `availableDisplayModes`) and SHALL send `ui/notifications/initialized` only after the result.
- THE SYSTEM SHALL issue only the View-to-Host methods the pinned spec permits (`tools/call`, `resources/read`, `notifications/message`, `ping`, and the `ui/*` requests). In particular it SHALL NOT call `tools/list` from the View.
- WHEN the View receives `ui/notifications/tool-result` THE SYSTEM SHALL treat `params` as a `CallToolResult` and SHALL correlate it to a tool via `ui/notifications/tool-input` or the `toolInfo` in host context, never via a `params.name` field.
- WHEN host context reports theme, container dimensions or display mode THE SYSTEM SHALL adapt by feature detection, and SHALL NOT branch on host name or user-agent.
- WHEN the App is launched from an entry tool called with `{}` THE SYSTEM SHALL render a useful default view, and refresh, filter and detail SHALL use only existing read tools.
- IF a host capability (display mode, model context, `ui/message`, global entry) is not advertised THEN THE SYSTEM SHALL hide the dependent control and keep the remaining view working.
- THE SYSTEM SHALL render untrusted text only through `textContent` or equivalent escaping. A test SHALL fail if `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or `eval` appear in the bundle.
- THE SYSTEM SHALL serve byte-identical resource contents to every host. Host-specific values (for example `ui.domain`, `openai/*` or `com.google.antigravity/ui` keys) SHALL appear only in `_meta`, and the bundle SHA-256 SHALL be recorded per release.

Read-only PoC and security

- WHILE the PoC is running THE SYSTEM SHALL link `_meta.ui` only to read tools. `send_message`, `prepare_send_message`, pin and any other write tool SHALL NOT be App-linked or App-callable, and the instance SHALL use a throwaway or synthetic Telegram account.
- WHEN a UI-originated `tools/call` or `resources/read` reaches the server THE SYSTEM SHALL apply the same OAuth token validation, `requireScope` check, tenant isolation and audit record as for a model-originated call.
- IF a request names another tenant's object, presents a stale `state_version`, replays an expired confirmation, or lacks the scope THEN THE SYSTEM SHALL deny it with the same answer a missing object or missing scope gets. Isolated tests SHALL cover each case for both call origins.
- THE SYSTEM SHALL NOT place a bearer token, backend credential or tenant selector in the View. The CSP declared in `_meta.ui.csp` SHALL stay empty unless a reviewed origin is required.
- THE SYSTEM SHALL NOT treat `_meta.ui.visibility` as authorization. Antigravity is documented to ignore it, and the spike must state this.
- WHEN a headless client (Codex, Claude Code, agy) calls an App-linked tool THE SYSTEM SHALL return the same semantic plain-text content as with `MCP_APPS_ENABLED=false`.

Gates

- WHEN the operator run completes THE SYSTEM SHALL evaluate gates G1-G6 (design.md) and record GO, NO-GO or BLOCKED_BY_HOST per gate. The verdict SHALL be chosen by the owner from `ADOPT_STANDARD_ONLY`, `ADOPT_WITH_THIN_HOST_ADAPTERS`, `DEFER`.

## Out of scope

- Any implementer run, production deployment, `MCP_APPS_ENABLED=true` on `tg.mctl.ai`, or GitOps change without a separate owner approval.
- Connector or directory submission (Claude, ChatGPT, Antigravity). That remains mctlhq/mctl-telegram#650's positioning and #852's policy question.
- Write enablement from an App (send, pin, approve DevLoop, deploy). A future write phase needs its own spike and must keep exact-payload confirmation, MFA/fresh-sign-in and idempotency.
- A generic platform MCP-Apps SDK, a new repository, a Node sidecar or new ingress.
- Live customer data, and the owner's real Telegram account.
- Building a Portal (Cloudflare) passthrough workaround.
- Broad UI redesign of the Telegram triage view.
- Replacing AG-UI (#261). MCP Apps is in-host presentation, and AG-UI is the run/event projection in mctl-portal.

## Open questions

- Issue #376 itself does not follow `.github/ISSUE_TEMPLATE/spike.yml`. It has no `Source:`, `Question:`, `Outcomes:` or `Lifecycle:` lines, the title prefix is `spike(mcp-apps):` rather than `spike: `, and the `spike:scout` and `agents:intake` labels are missing. AGENTS.md requires the issue to be conformed before DevLoop. This proposal treats that as task 0 and a precondition for approval. Proposed values: `Source: mctlhq/.github#376 (owner-filed 2026-11-22)`, outcomes as listed above.
- The Telegram prototype hand-rolls the bridge with no JS build. Should the fix keep the hand-rolled bridge, conformed to the spec, or vendor the pinned `@modelcontextprotocol/ext-apps` App browser build? Proposal: vendor a pinned, hash-recorded build only if the conformance fixture shows the hand-rolled bridge cannot cover the lifecycle cheaply. Decide in task 3.
- Which instance and account does the operator run use? `tg-preview.mctl.ai` runs the owner's account and agent features, and `tg.mctl.ai` is production with `ALLOW_SEND: "true"`. Proposal: a dedicated preview or throwaway deployment, with the existing read-only tool profile and a throwaway Telegram identity, decided under #650.
- Claude `ui.domain` (documented as derived from a SHA-256 prefix of the server URL) and ChatGPT's `oaiusercontent` form are host-specific. Proposal: omit `ui.domain`, because the Telegram App makes no network calls and needs no stable origin. Add it only if a host refuses to render without it, which would be a measured G-result.
- The ChatGPT, Claude and Antigravity documentation pages listed in the issue were not re-fetched by this run. Their claims (Antigravity v2.34+, `com.google.antigravity/ui` `aux_pane`/`global`/`file`, `openai/ui` global entry, the Claude Nov 10 rollout) are carried as `documented (issue snapshot 2026-11-22)` until task 2 re-reads them with access dates.
- Can the server tell a UI-originated call from a model-originated call? The spec routes both through the host's single MCP session, so the server may not be able to. If it cannot, audit records the call identically and any origin hint stays an untrusted annotation. Measured in T9.
- mctl-api's deployed revision and its MCP surface were not observed in GitOps by this run (see design.md). They must be confirmed before phase 4.
