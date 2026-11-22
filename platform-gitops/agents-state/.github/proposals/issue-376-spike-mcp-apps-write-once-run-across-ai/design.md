# Design: issue-376-spike-mcp-apps-write-once-run-across-ai

## Current state

### In this repository (`mctlhq/.github` at `7a0659c`)

- `roadmap/epics/enterprise-mcp.yaml` (lifecycle `paused`) already carries
  MCP Apps as phase `extensions`:
  - work item `mcp-apps` is bound to mctlhq/mctl-telegram#569;
  - `mcp-apps-validation` is bound to mctlhq/mctl-telegram#650 and depends on `mcp-apps`;
  - `enterprise-endpoint-decision` (#128) depends on `mcp-apps`;
  - success criterion: "MCP Tasks and Apps are accepted only after
    end-to-end Portal compatibility is measured".
- `roadmap/spikes/tg-mcp-app-live-validation.yaml` is the SpikeDefinition for
  #650. It is `parked` with outcomes `SUBMIT_READY | SUBMIT_WITH_LIMITATIONS | NOT_READY`.
  Its activation trigger is mctl-telegram#852 plus a scheduled operator session
  with a throwaway identity (`reviewBy: 2026-11-30`). It asks a submission
  question. #376 asks a portability question, so the two must not merge, but
  #376's real-host run must reuse #650's execution.
- `docs/spikes/agent-ui-ag-ui.md` Q8 separates MCP Apps (UI inside an MCP
  host) from AG-UI (run/event projection in mctl-portal). #261 (open,
  "PHASE B GO") builds the AG-UI DevLoop Run Inspector from canonical
  mctl-api facts.
- `docs/spikes/agent-client-compatibility.md` and
  `docs/spikes/agent-client-compatibility/` (`probe.py`, `agents.json`,
  `tests/fake_server.py`) set the house pattern this spike reuses:
  - evidence tags (`[DOC]`, `[OBSERVED date, commit]`, `UNTESTED`);
  - "unknown is never evidence of absence";
  - a stdlib Python reference model with loopback fakes, run by
    `.github/workflows/workflow-tests.yml` as `python3 -I -m unittest discover -s docs/spikes/<name>/tests -v`.
- `docs/spikes/web-platform-unification.md` (decided
  STANDARDIZE_CONTRACTS_KEEP_RUNTIMES) records tg.mctl.ai CSP and the "no CSP
  is relaxed" rule.
- `roadmap/schemas/spike-definition.schema.json` plus
  `roadmap/scripts/validate.py::spike_semantic_errors` validate SpikeDefinitions:
  - outcome pattern `^[A-Z][A-Z0-9_]*$`;
  - `decision` only when `decided`;
  - `parked` requires `activation`.
- `.github/ISSUE_TEMPLATE/spike.yml` requires the title prefix `spike: `, the
  labels `spike:scout` and `agents:intake`, and the
  `Source/Question/Outcomes/Lifecycle/Related/Why mctl` lines.
  Issue #376 has none of the labels and none of the lines (checked with `gh issue view 376`).

### The Telegram prototype (mctlhq/mctl-telegram, `main` at `25e6485`; PR #651, merge `2fdf9af`)

- `internal/mcpui/app.go`:
  - `ExtensionID = "io.modelcontextprotocol/ui"`;
  - `ResourceURI = "ui://mctl-telegram/triage"` (stable, unversioned);
  - `MIMEType = "text/html;profile=mcp-app"`, `Version = "0.1.0"`;
  - `triage.html` is embedded with `go:embed`;
  - `uiResourceMeta()` declares empty `connectDomains/resourceDomains/frameDomains/baseUriDomains`, no `domain`, and `prefersBorder: true`;
  - `ToolMeta()` emits `{"ui":{"resourceUri":..., "visibility":["model","app"]}}`.
  It has no SDK helper: `mark3labs/mcp-go v1.0.0` has none, and the keys are written by hand.
- `internal/mcp/server.go` gates everything on `Server.AppsEnabled`, which `internal/config/config.go`
  reads as `envBool("MCP_APPS_ENABLED", false)`. With the flag on, `addToolUI` links
  `list_dialogs`, `list_folders`, `list_topics`, `get_unread_messages`,
  `get_messages`, `prepare_get_media`, **`send_message`** and
  **`prepare_send_message`**. So the prototype as merged is not read-only at
  the UI-link layer. The send gate (`evaluateSendGate`, `ALLOW_SEND`,
  per-account `send_enabled`, one-shot `Confirms.Issue` bound to
  `HashSendPayload`) is the only protection.
- `internal/mcp/apps.go::toolPrepareSendMessage` calls `requireScope(id, "telegram:messages:send")`
  and audits through `s.audit`. The comment states that visibility is never consulted server-side.
- `internal/mcpui/triage.html` hand-rolls a postMessage JSON-RPC bridge and
  renders with `textContent` (no `innerHTML` match). Compared with ext-apps
  `specification/2026-01-26/apps.mdx` (fetched this run):
  1. `callHost("ui/initialize", {})` sends no `protocolVersion`, `appInfo`
     or `appCapabilities`, but the spec says the View "MUST include its
     capabilities in the `appCapabilities` field" (section "App Capabilities in `ui/initialize`").
  2. It then calls `tools/list` from the View. That method is outside the
     spec's "Standard MCP Messages" subset (`tools/call`, `resources/read`,
     `notifications/message`, `ping`). Because the initial
     `get_unread_messages` is chained after it, a conformant host that
     rejects `tools/list` leaves the App on "Could not connect to host".
  3. `onToolResultNotification` dispatches on `params.name`. The spec's
     `ui/notifications/tool-result` params are a plain `CallToolResult`,
     with no tool name.
  4. It does not handle `ui/notifications/host-context-changed`, `ui/notifications/tool-input`,
     `ui/resource-teardown` or display modes. It treats `size-changed` as an
     inbound no-op, but in the spec that notification is the View reporting its
     own size.
  These are reading-based findings. Task 3 turns each into a failing fixture test before any fix.
- The `docs/reports/mcp-apps-spike.md` host matrix has only the in-process
  `mcpprobe` row (`protocol_version 2025-06-18`). Claude and ChatGPT are
  "not measured here", and the matrix is owned by #650.

### Other candidate consumers (repo heads read this run)

| Repo | MCP stack | App resources found |
| --- | --- | --- |
| mctl-api `0809fb4` | Go, `mark3labs/mcp-go v1.0.0` (`go.mod`) | none. `resourceUri` appears only in `internal/mcp/prompts_resources_test.go` (plain resources) |
| mctl-glovo `6620f5b` | Go, `mark3labs/mcp-go v1.0.0` | none found |
| seerrsense `da0c5a3` | TS, `@modelcontextprotocol/server@^2.0.0` | none found |
| mctl-alice `cb276d6` | TS, `@modelcontextprotocol/sdk@^1.32.2` | none found |
| mctl-portal `798fb19`, mctl-web `ec18892` | web | no `ext-apps` dependency in root `package.json` |

Searches: `gh search code --owner mctlhq` for `"io.modelcontextprotocol/ui"`,
`resourceUri`, `"profile=mcp-app"` and `"ui://"`. Only mctl-telegram and its
#569 proposal matched. The code-search index may lag, so "none found" means
not found by search, not proven absent.

### Upstream (fetched this run)

- ext-apps releases: `v2.1.0` (2026-11-10), `v2.0.4`, ... The `v2.0.0` notes
  state that the wire protocol is unchanged: "2.x Views run in 1.x hosts and
  2.x hosts render 1.x Views", backed by an interop test against 1.7.5. Only
  the npm dependencies and the TS API break (`@modelcontextprotocol/client@^2`, zod 4.2+).
  The spec has a `2026-01-26` stable directory and a `draft` directory.
- The spec says `ui.domain` is **host-dependent** (examples
  `{hash}.claudemcpcontent.com` and `www-example-com.oaiusercontent.com`) and,
  when omitted, the host uses its default per-conversation sandbox origin. The
  host MUST reject View `tools/call` for tools whose `visibility` lacks `"app"`.
- `mark3labs/mcp-go` latest release is `v1.6.0` (2026-11-19). All three Go
  consumers pin `v1.0.0`. Whether 1.6 adds MCP Apps helpers was not checked.

Deployed state checked:

- `mctl_get_service_status(labs, mctl-telegram)`: Argo `Synced` and `Healthy`, image `0.141.0`, host `tg.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - `tag: "0.141.0"`, `ALLOW_SEND: "true"`;
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS` includes `claude.ai`, `chatgpt.com` and `antigravity.google` plus Google `oauth-redirect` prefixes;
  - `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`;
  - no `OAUTH_PREREGISTERED_CLIENTS` (the Portal uses DCR);
  - **no `MCP_APPS_ENABLED`**, so the App surface is off in production (default false in `config.go`).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: `tag: "main-25e6485"`, host `tg-preview.mctl.ai`, `ALLOW_SEND: "true"`, `AGENT_ENABLED`/`MANAGED_RUNTIME_ENABLED: "true"`, **no `MCP_APPS_ENABLED`**. Antigravity redirect hosts are allowlisted, and CIMD hosts were not read in this file.
- Neither values file lists ChatGPT, Claude or Antigravity sandbox origins, and none is needed while the App makes no network call.
- mctl-api is not under `$MCTL_GITOPS_ROOT/services/` (tenants admins, karabu, labs, namax66, redloop). Its deployed revision and MCP tool set were **not observed** by this run (gap; see Open questions in requirements.md).
- No real host was exercised. Every host cell is `documented` or `unknown` today.

## Proposed solution

Phase 0 (this proposal's implementable slice) is evidence infrastructure only, in
this repository. Product changes are listed as gated follow-ups in other repos.

### 1. Spike artifacts in `mctlhq/.github`

- `docs/spikes/mcp-apps-portability.md`: the report, with sections Question,
  Non-claims, Evidence tags, Host contract matrix (rendered from the JSON
  below), Existing-work inventory (the table above with revisions), ADR,
  PoC plan, Security model, Gates, Backlog, Risks.
- `roadmap/spikes/mcp-apps-portability.yaml` (SpikeDefinition):

  ```yaml
  apiVersion: roadmap.mctl.ai/v1alpha1
  kind: SpikeDefinition
  metadata: {name: mcp-apps-portability, owner: mctlhq/.github}
  spec:
    title: MCP Apps write once, run across ChatGPT, Claude and Antigravity
    question: >-
      Can one immutable MCP Apps bundle per app, served by the existing
      product server, render and refresh with identical read semantics in
      ChatGPT, Claude and Antigravity, with at most server-side metadata
      adaptation and unchanged plain-text behaviour in headless clients?
    lifecycle: proposed
    github: {issue: {repository: mctlhq/.github, number: 376}}
    outcomes: [ADOPT_STANDARD_ONLY, ADOPT_WITH_THIN_HOST_ADAPTERS, DEFER]
    execution: {devloop: true}
    evidence: {report: docs/spikes/mcp-apps-portability.md}
  ```

  No `epic` binding is added. `enterprise-mcp` is paused and its items are
  already bound to #569 and #650, so linking happens in the report's Related
  section to avoid a second binding of the same work.
- `docs/spikes/mcp-apps-portability/` (stdlib Python, run with `-I`):
  - `host_matrix.json`: rows = contract points, columns = hosts
    (`chatgpt-web`, `chatgpt-mobile`, `claude-web`, `claude-desktop`,
    `claude-mobile`, `antigravity-app`, `codex`, `claude-code`, `agy-cli`,
    `cf-portal-route`). Each cell is
    `{status, source_url?, accessed?, evidence?{date, host_build, plan, endpoint, bundle_sha256, artifact, operator}, cause?}`,
    where `status` ∈ {documented, fixture_tested, real_host_verified, unavailable, unknown}
    and `cause` ∈ {host_gating, server_defect, bundle_defect, portal_limit}.
  - `matrix.py`: a validator. It refuses a `real_host_verified` cell without
    a complete `evidence`, refuses `documented` without a URL and date, and
    refuses mixed bundle hashes within one app column set (gate G1). It also
    renders the Markdown table.
  - `bridge_check.py`: a conformance checker for a View's JSON-RPC
    transcript (a list of messages recorded by a fixture host or a real host's
    devtools). It checks:
    - the `ui/initialize` params shape and order;
    - the allowed View-to-Host method set from the pinned spec revision (`2026-01-26`);
    - that `tool-result` is handled as a `CallToolResult`;
    - that no `tools/list` comes from the View;
    - that `size-changed` is emitted by the View.
  - `bundle_scan.py`: a static scan of an HTML bundle. It flags `innerHTML`,
    `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`,
    `new Function`, any `http(s)://` fetch or `<script src>` outside the
    declared CSP, host-name/user-agent sniffing (`navigator.userAgent`,
    `chatgpt`, `claude`, `antigravity` string branches) and `window.openai`
    use not guarded by feature detection. It prints the SHA-256 of the bundle.
  - `fixtures/`:
    - `telegram-triage-0.1.0.transcript.json`, reconstructed from `triage.html` as merged. It is expected to FAIL findings 1-3;
    - a minimal passing transcript;
    - matrix fixtures (valid, a forged `real_host_verified`, mixed hashes).
  - `tests/`: unittest for all three scripts. Wired into `workflow-tests.yml` paths and steps like `agent-client-compatibility`.
- `AGENTS.md` `# Spikes` gets one bullet linking the report. `README.md` is not touched.

### 2. Host contract model

Portability rests on one rule: **the bundle bytes are host-independent, and
only `_meta` may vary**. The server decides `_meta` from what the host
negotiates in `initialize` (the `capabilities.extensions["io.modelcontextprotocol/ui"]`
entry and its `mimeTypes`), never from a host-name string. Concretely:

| Concern | Standard-only behaviour | Thin adapter, only if a measured cell requires it |
| --- | --- | --- |
| Rendering | `_meta.ui.resourceUri` plus `resources/read` | none |
| Sandbox origin | omit `ui.domain` (default origin, since the App makes no network calls) | per-host `ui.domain` computed server-side (Claude: documented server-URL SHA-256 prefix) |
| Global/side/file entry | not used, launched from an entry tool | `openai/ui` global entry (ChatGPT, Claude) and `com.google.antigravity/ui` `aux_pane`/`global`/`file`, as additive `_meta` keys |
| Host-specific JS API | none, only the standard bridge | `window.openai` only behind feature detection, never required |
| Headless | `content[].text` semantic equivalent of `structuredContent` | none |

If the measured matrix shows no row needing the right-hand column, the
verdict is ADOPT_STANDARD_ONLY. If only additive `_meta` keys are needed,
the verdict is ADOPT_WITH_THIN_HOST_ADAPTERS. If no two of the three
browser hosts reach G2, the verdict is DEFER.

### 3. ADR (recorded in the report; the owner decides)

- **Option A: reuse the Telegram implementation directly as the template.**
  Copy `internal/mcpui` per product. It is cheap, but it copies three spec
  defects and has no build step for a vendored bundle.
- **Option B: a small shared frontend package plus language-native helpers now.**
  Two server languages are in play (Go: telegram, api, glovo; TS: seerrsense, alice).
  This needs a new package or repository and violates "no generic SDK until two real consumers".
- **Option C (recommended): product-local code against a shared contract.**
  - Telegram fixes its bridge in place.
  - The shared artifact is the *contract* (`bridge_check.py`, `bundle_scan.py`, `host_matrix.json`), not code.
  - TS consumers use upstream `@modelcontextprotocol/ext-apps` server helpers directly.
  - Go consumers keep a local `mcpui`-style package.
  - Extraction of a Go helper (for example `internal/mcpapps` copied into a shared module) is reconsidered only after mctl-api's Run Inspector is the second real consumer and the diff between the two Go packages is measured.
  - No Node sidecar and no new ingress: the bundle is served by the existing MCP server via `resources/read`.

### 4. Bounded read-only PoC (gated, other repos)

1. **Telegram conformance fix** (mctl-telegram, behind `MCP_APPS_ENABLED`):
   - `ui/initialize` with `protocolVersion: "2026-01-26"`, `appInfo` and `appCapabilities{availableDisplayModes:["inline"]}`;
   - remove the View `tools/list` call. Write affordances are not shown at all in the PoC, so there is nothing to detect;
   - correlate results via `tool-input` / host context;
   - emit `size-changed` and apply theme CSS variables from host context;
   - handle teardown.
   - **Read-only link set**: a new `MCP_APPS_READONLY` default-true check, or reuse of the existing `core-readonly` tool profile (`docs/tool-descriptors.core-readonly.json`). Either way, `send_message` and `prepare_send_message` are not passed to `addToolUI`.
   - The entry tool is `get_unread_messages` with `{}`.
   - Bump `Version`, record the bundle SHA-256 in `_meta.ui` under an `mctl.bundleSha256` key and in the content-hash test.
2. **Fixture proof** (mctl-telegram CI plus this repo's checker):
   - the transcript from an in-process fixture host passes `bridge_check.py`, and `bundle_scan.py` is clean;
   - the `mcpprobe` Apps step is unchanged;
   - headless golden test: `content[].text` is byte-equal with the flag on and off.
   - The MCP Inspector or a mock host stays `fixture_tested`, never real-host.
3. **Operator run under #650** (human, throwaway identity, separate deployment or preview with the flag on, approved via a mctl-gitops PR):
   - ChatGPT, Claude web/desktop and Antigravity on real accounts;
   - Codex, Claude Code and agy for headless;
   - optional `cf-portal-route` row.
   - Captures per host: sanitized screenshot, devtools JSON-RPC transcript (run through `bridge_check.py`), `resources/read` bytes hash, and server audit lines for the same `trace_id`.
4. **Second consumer (separate issue, after G1-G4 GO): mctl-api DevLoop Run Inspector App.**
   - Read-only, linking only tenant-scoped read tools that already exist: `mctl_get_work_item`, `mctl_list_work_item_executions` and `mctl_list_work_item_snapshots`, plus `mctl_get_dev_loop` for admins only.
   - No approval, decide, abandon or trigger tool is linked. It reuses the canonical facts #261 projects, and no new store is added.

### 5. Security model

- The authority is the host's existing OAuth session to the product server
  (tg.mctl.ai: DCR/CIMD per `OAUTH_CIMD_ALLOWED_HOSTS`; mctl-api: its OAuth).
  The View holds no token: it only posts JSON-RPC to the host.
- Every handler keeps `auth.From(ctx)`, `requireScope` and its tenant filter.
  The UI link changes none of them. Visibility is a host hint only (and is
  documented as ignored by agy).
- Origin: UI-originated and model-originated calls arrive on the same session.
  Audit therefore records them identically, and any origin hint is stored as
  an untrusted annotation. Correlation uses the existing `trace_id` /
  work-item id (#306 REUSE_WORK_ITEM_ID) so that #375 revocation and fencing
  apply to the session, not to the UI.
- CSP stays empty (`default-src 'none'` baseline). Untrusted Telegram text
  goes through `textContent` only, enforced by `bundle_scan.py`.
  `ui/update-model-context` and `ui/message` never carry Telegram text,
  following the existing comment in `triage.html`, and T8 asserts it.
- Data minimisation: the App renders the same fields the tools already
  return. No new field is added for the UI.
- The write phase is explicitly excluded. When it comes, it reuses
  `prepare_*` plus the one-shot `confirmation_id` bound to the payload hash,
  fresh-sign-in/MFA, and idempotency, under its own spike.

### 6. Gates (GO/NO-GO, evaluated in the report)

- **G1 Immutable bundle**: the same SHA-256 of `resources/read` text across all browser hosts, and equal to the release hash.
- **G2 Render and refresh**: in each of ChatGPT, Claude and Antigravity, launch with `{}` renders, refresh and filter re-call read tools, and detail opens. Each is `real_host_verified`.
- **G3 Identical read semantics**: per host, the `structuredContent` of the same call against the same throwaway fixture is equal after normalising timestamps.
- **G4 Headless unchanged**: Codex, Claude Code and agy text output is byte-equal to flag-off.
- **G5 Graceful degradation**: an unadvertised capability hides its control without a console error or blank frame (fixture plus at least one real host).
- **G6 Security**: T7-T10 pass, and the audit trace for a UI-originated call matches a model-originated one.

Each gate records GO, NO-GO (our defect) or BLOCKED_BY_HOST (plan, rollout or Portal), with evidence refs.

### 7. Product order after evidence

Telegram validation (#650), then the DevLoop Run Inspector (mctl-api, Go),
then Glovo (Go, same SDK, which tests helper extraction), then SeerrSense (TS
SDK 2, which can use upstream ext-apps helpers), then Alice (TS SDK 1.x, which
needs an SDK decision first). None of these commits to production or a
directory submission.

## Alternatives

- **Fold #376 into #650.** Dropped because #650 answers a submission question (`SUBMIT_*` outcomes), is parked on #852 policy, and covers one product. #376 needs a cross-product portability verdict. #376 therefore reuses #650's operator session instead of duplicating it.
- **Write a generic MCTL MCP-Apps SDK or Node sidecar that serves bundles for every product.** Dropped: no second consumer exists, there are two server languages, and it adds ingress and a deployment. Upstream ext-apps already supplies the TS side.
- **Go straight to the real-host matrix with the merged bundle.** Dropped because the three reading-based spec divergences would fail in conformant hosts and be misattributed to host support. A cheap fixture conformance gate must come first.
- **Host-specific bundles (a ChatGPT build with `window.openai` and a Claude build).** Dropped because they break G1 and the "write once" goal, and multiply review surface.

## Platform impact

- Migrations: none. Phase 0 adds docs, JSON, stdlib Python and CI wiring in this repository only.
- Backward compatibility: no runtime change anywhere. `MCP_APPS_ENABLED` stays false in `tg.mctl.ai` and `tg-preview.mctl.ai` values, and the tool surface with the flag off is unchanged (existing mctl-telegram tests).
- Resource impact: CI runs a few extra unittest seconds. The later operator run needs a throwaway Telegram identity and the host plans (ChatGPT, Claude, Antigravity). Their plan and rollout eligibility is itself a measured cell.
- Cost and maintenance: Option C costs one product-local bridge per product (about 600 lines of HTML/JS today), plus a shared contract checker. Extraction is deferred until measured duplication justifies it.
- Risks:
  - P1: the merged App links write tools (`send_message`, `prepare_send_message`) while prod has `ALLOW_SEND: "true"`. Mitigation: the read-only link set is a precondition of any flag flip, and T7 asserts it.
  - P1: a host-gated rollout (plan, region, allowlist, "preview is not access") is misread as a code defect, or the reverse. Mitigation: the `cause` field and separate fixture evidence.
  - P1: issue #376 non-conformance to the spike template. Mitigation: task 0 before approval.
  - P2: a spec or host revision drifts between capture and decision. Mitigation: pin the spec revision `2026-01-26` and ext-apps `2.1.0` in the matrix, and record the access date per cell.
  - P2: Portal (#44, #35) strips `_meta.ui` or `resources/read`. Mitigation: record it as `portal_limit`, with no workaround.
  - P2: screenshots leak Telegram data. Mitigation: a throwaway identity, synthetic dialogs and a sanitisation checklist.
  - P3: `mark3labs/mcp-go` upgrades (v1.0.0 to v1.6.0) change `_meta` serialisation. Mitigation: the existing content-hash and `apps_surface_test.go` guard it.
  - P3: Alice's TS SDK 1.x lags. Mitigation: it is last in product order.
- Rollback: revert the Phase 0 PR. Product slices roll back by unsetting `MCP_APPS_ENABLED` (already a documented env-only drop-back in `config.go`).
