# Design: issue-259-spike-distribution-make-mctl-deploy-read

## Current state

`mctlhq/.github` is the org-level roadmap and spike repository. Relevant parts:

- **Spike convention.** Each spike is a report under `docs/spikes/<name>.md`
  (e.g. `docs/spikes/agent-ui-ag-ui.md`, `docs/spikes/mcp-gateway-g0.md`) using
  evidence tags (`[CODE]`, `[DEPLOYED]`, `[DOC]`, `[REF]`, `unknown (not observed)`)
  and an "Evidence pins" table of 40-hex commits, plus a `SpikeDefinition` manifest
  under `roadmap/spikes/<name>.yaml` (schema `roadmap/schemas/spike-definition.schema.json`:
  `outcomes` pattern `^[A-Z][A-Z0-9_]*$`, `lifecycle: active` requires `timebox`,
  `decision` allowed only when `lifecycle: decided`). `roadmap/scripts/validate.py`
  (`spike_semantic_errors`, `_spike_corpus_errors`) checks the verdict is one of
  `outcomes`, dates are calendar dates, and that one issue is bound by at most one
  SpikeDefinition. `AGENTS.md` lists every spike under `# Spikes`.
- **Agent deploy (#254).** `roadmap/epics/agent-deploy.yaml` is `lifecycle: proposed`.
  Bound items: `intent-schema` (mctl-gitops#2186), `analyze` (mctl-api#826). Unbound
  (not started): `preconditions`, `plan`, `grants` ("Generalize action_approvals grants
  to deploy operations and remove confirm=\"yes\""), `digest`, `health-gate`,
  `deploy-record` (`get_deployment`), `rollback-revision`, `preview-onboard`,
  `promote-rollback-tools` (gated through .github#237). Its success criteria already
  include "a fresh AI session on a non-admin tenant authenticates through OAuth" and
  "a self-approval attempt is refused and audited".
- **MCP gateway (#236).** `roadmap/epics/mcp-gateway.yaml`: G0a token hardening
  (mctl-api#805), G1 policy (#237) ... G5 non-admin users (#241), all required;
  `docs/plans/mcp-gateway.md` and `docs/spikes/mcp-gateway-g0.md` hold the identity
  and per-tool policy design. G5 is the phase that serves non-admin users.
- **Context efficiency.** `roadmap/spikes/mcp-context-efficient-exposure.yaml`
  (mctl-agents#597) is `parked`; it owns lazy/progressive tool discovery.
- **Support.** `roadmap/epics/tenant-support-agent.yaml` (#243) and
  `docs/spikes/mctl-support-runtime.md`.

Deployed state checked:

- `mctl_whoami` -> principal `agent:issue-investigator`, `Admin: false`, `Teams: []`,
  no namespaces, against `https://api.mctl.ai`.
- Tool list offered to this run's non-admin principal (session tool catalogue) ->
  the full mctl catalogue (well over 100 tools) including admin/destructive tools
  (`mctl_delete_tenant`, `mctl_retire_service`, `mctl_fence_lifecycle_claim`,
  `mctl_promote_agent`, ...), several with a client-supplied `confirm` parameter
  ("Type \"yes\" to confirm"). Whether this is mctl-api `tools/list` filtering or this
  run's connector/policy-checkpoint setup is unknown (not observed); the spike must
  re-test with a real tenant identity. `mctl_deploy_analyze` and `mctl_get_repo_binding`
  are present in that catalogue (consistent with mctl-api#826 having shipped).
  All observed tool names are well under 64 characters.
- `mctl_list_services(team=admins)` -> 8 catalogue services (mctl-agents-worker*,
  mctl-design `ui.mctl.ai`, mctl-docs `docs.mctl.ai`, mctl-support `support.mctl.ai`,
  mctl-web `mctl.ai`, umami); mctl-api is not a catalogue service, so its deployed
  config (OAuth settings, token TTL, tenant authz mode) is unknown (not observed).
  Note: this call succeeded for a principal with `Teams: []`; why is unknown (not
  observed) and is a cross-tenant item for D1/D4.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml` -> `MCTL_AUTH_ISSUER:
  https://api.mctl.ai`, `MCTL_API_URL: https://api.mctl.ai` (api.mctl.ai is the OAuth
  issuer used by other services).
- `$MCTL_GITOPS_ROOT/tenants/` -> tenants `admins, commerce-proof, erpact, karabu, labs,
  mctl, namax66`; no tenant is designated as a Claude-connector test tenant.
- Not observed: `https://api.mctl.ai/mcp` transport behaviour, `/.well-known/oauth-protected-resource`
  and authorization-server metadata, mctl-api source, privacy/terms/support pages on
  mctl.ai/docs.mctl.ai, Anthropic's current directory documentation. All are tasks below.

## Proposed solution

Deliver the spike as three files in `mctlhq/.github`, following the AG-UI and G0
precedents, with no production change:

1. **`docs/spikes/mctl-deploy-claude-directory.md`** — the report, structured D1-D9:
   - *Non-claims and evidence tags*: adds `[LIVE]` for observations in a real Claude
     custom Web connector session; states that nothing is submitted and Claude is a
     client, never an authority.
   - *Evidence pins*: `.github`, `mctl-api`, `mctl-gitops`, `mctl-docs`/`mctl-web` (for
     public pages) at 40-hex commits, plus Anthropic doc URLs with access date.
   - *D1* current-state/duplicate matrix for the twelve Phase A items, read from
     mctl-api code (MCP server registration, tool annotations, OAuth server and
     well-known handlers, audience checks, tenant authz), live-safe unauthenticated
     probes (`initialize`/`401` + `WWW-Authenticate`, well-known metadata), and the
     tool-list observation above.
   - *D2* Anthropic requirements snapshot (OAuth 2.0, Streamable HTTP, tool name <= 64,
     `title`/`readOnlyHint`/`destructiveHint`, error quality, token frugality, submission
     fields), dated.
   - *D3* MCTL Deploy surface: a table of the proposed eight tools mapped to canonical
     #254 names and current mctl-api tools, with annotation, visibility, authority and
     response bound (e.g. logs `lines` capped, no secret fields). Classifies every tool a
     non-admin can discover today into golden-path / optional / hidden / grant-required.
     Records `tools/list` byte size and token estimate (method: serialized JSON length,
     tokens estimated with the Anthropic token-counting endpoint or a stated ratio) for
     current catalogue vs. proposed surface. Recommendation: expose the surface by
     per-principal tool filtering on the existing boundary, implemented by the gateway
     policy (#237, G5 #241) rather than a new endpoint, unless D1 proves filtering cannot
     produce correct metadata.
   - *D4/D5* Claude custom-connector protocol (Phase C 13 steps and the negative tests)
     as a checklist with one row per step: status (`PASS`, `FAIL`, `BLOCKED (#254:<item>)`,
     `unknown (not observed)`) and evidence identifiers. Steps 7-13 map to #254 items
     `plan`, `grants`, `deploy-record`, `preview-onboard`, `health-gate`,
     `promote-rollback-tools`.
   - *D6* Phase D compliance matrix PASS/FAIL/UNKNOWN with owner issue per gap.
   - *D7* draft packet (name MCTL Deploy, value proposition, description, use cases,
     read/write disclosure, auth explanation) with legal/branding/support items as
     explicit gaps where pages do not exist.
   - *Phase E* first-user test script and score sheet (prompts 1-5, metrics), live rows
     unknown until executed.
   - *Plugin bundle* note: defer; recommend only after single-connector UX is measured.
   - *Support*: existing status/log/error tools are the default; `mctl_ask_support`
     (#243 / mctl-api#814) only if Phase E shows unrecoverable errors.
   - *D8* exactly one provisional verdict with reasoning. Given the current evidence
     (#254 `proposed`, plan/grants/deploy-record unbound; `confirm`-style self-approval
     still on consequential tools), the expected provisional verdict is
     `BLOCKED_ON_AGENT_DEPLOY`, with connector-surface findings (tool filtering,
     annotations, `confirm` removal) recorded in D9 against #237/#241 and #254 `grants`.
     The implementer must re-derive it from the gathered evidence, not copy this guess.
   - *D9* follow-up map; new issues proposed only for unowned gaps (likely: public
     privacy/terms/support pages and directory submission packet in mctl-web/mctl-docs;
     Claude published-identity OAuth compatibility in mctl-api if not covered by #805/#237).
2. **`roadmap/spikes/mctl-deploy-claude-directory.yaml`** — `SpikeDefinition`,
   `metadata.owner: mctlhq/.github`, bound to `mctlhq/.github#259`, outcomes the five
   verdicts, `lifecycle: active`, `timebox.decisionBy` (proposed `2026-12-15`),
   `execution.devloop: true`, `evidence.report: docs/spikes/mctl-deploy-claude-directory.md`,
   no `decision` (the owner records it, as in `agent-ui-ag-ui.yaml`).
3. **`AGENTS.md`** — one bullet under `# Spikes` linking the report.

Why this way: the repository already has a validated spike pipeline and evidence
discipline; reusing it keeps status single-sourced (manifest lifecycle + owner decision)
and avoids a second tracker. Keeping the connector surface as a policy view over the
existing `api.mctl.ai/mcp` boundary honours invariants 1-12 and the issue's preference
for filtering over a new server.

## Alternatives

- **Separate MCTL Deploy MCP server/endpoint now.** Gives a clean `tools/list` quickly,
  but duplicates OAuth, audience and tool registration that #236/#237 are building, and
  the issue forbids it unless filtering is proven insufficient. Dropped; kept as a D3
  fallback criterion.
- **Submit the existing `api.mctl.ai/mcp` catalogue as-is.** Exposes admin/destructive
  tools and `confirm` self-approval to external tenants; violates invariants 3 and 4 and
  the issue's product boundary. Dropped.
- **Wait for #254 to finish before running the spike.** Loses the protocol/OAuth/
  annotation/packet findings that are independent of deploy completeness and would leave
  #237/#241 and docs owners without inputs. Dropped: run now, mark #254-dependent steps
  BLOCKED.
- **Plugin bundle with an Agent Skill first.** Would mask poor tool descriptions; issue
  forbids it before measuring single-connector UX. Dropped.

## Platform impact

- No migration, no runtime change, no new endpoint. Only docs and one roadmap manifest.
- `roadmap/scripts/validate.py` gains one more spike to validate; the corpus check
  rejects a second SpikeDefinition for #259, so none may exist (none does today).
- Risk: live Claude steps cannot be executed by the DevLoop implementer -> report marks
  them `unknown (not observed)` and the manifest stays `active`; the owner fills `[LIVE]`
  rows before deciding. Mitigation is the explicit test protocol in D4/D5/Phase E.
- Risk: leaking credentials or tenant data in evidence -> report quotes identifiers and
  status codes only, never tokens, headers with secrets, or log bodies.
- Risk: overclaiming readiness -> every PASS needs a tagged evidence row; anything else is
  FAIL/UNKNOWN.
- Risk: duplicating owned work -> D9 routes gaps to #254 items, #237/#241, #243,
  mctl-agents#597 before proposing any new issue.
