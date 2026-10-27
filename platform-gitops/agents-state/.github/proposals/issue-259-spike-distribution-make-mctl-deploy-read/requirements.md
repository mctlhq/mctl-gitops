# Spike: make MCTL Deploy ready for Claude directory submission (mctlhq/.github#259)

## Context

mctlhq/.github#259 asks whether a new external user can connect a product-facing
**MCTL Deploy** remote MCP connector to Claude (custom Web connector first, the
unified Claude directory later) and complete one safe repository -> running URL
journey with zero platform-owner intervention, using the existing MCTL governance
chain. It is a distribution/readiness spike, not a deploy implementation:
`mctlhq/.github#254` (`roadmap/epics/agent-deploy.yaml`) stays canonical for the
deploy path, `mctlhq/.github#236/#237` (`roadmap/epics/mcp-gateway.yaml`) for tool
policy and grants, and `mctlhq/.github#243` for tenant support. The spike must end
with exactly one verdict out of `READY_TO_SUBMIT | READY_AFTER_SMALL_GAPS |
BLOCKED_ON_AGENT_DEPLOY | REVISE_CONNECTOR_SURFACE | NO_GO`.

In this repository the deliverable follows the established spike convention
(`docs/spikes/agent-ui-ag-ui.md` + `roadmap/spikes/agent-ui-ag-ui.yaml`, listed in
`AGENTS.md`): an evidence-tagged report under `docs/spikes/`, a `SpikeDefinition`
manifest under `roadmap/spikes/` that validates with `roadmap/scripts/validate.py`,
and an `AGENTS.md` entry. No production code, endpoint, tool or auth path is
changed by this spike, and nothing is submitted to Anthropic.

## User stories

- AS the platform owner I WANT a dated, evidence-tagged readiness report (D1-D9)
  SO THAT I can decide whether and when to submit MCTL Deploy to the Claude
  directory without relying on old MCP/Portal spikes.
- AS a new external Claude user I WANT a small, clearly annotated MCTL Deploy tool
  surface SO THAT Claude picks the right operation and can never deploy without my
  server-side approval.
- AS a security reviewer I WANT every connector claim backed by a tested current
  behaviour or explicitly marked unknown SO THAT submission material never
  overstates MCTL's guarantees.
- AS the agent-deploy (#254) and gateway (#236/#237) owners I WANT gaps routed to
  existing work items SO THAT no second deploy flow, tool registry or auth path
  appears.

## Acceptance criteria (EARS)

- WHEN the spike lands THE SYSTEM SHALL contain `docs/spikes/mctl-deploy-claude-directory.md`
  with sections D1-D9 as named in mctlhq/.github#259, and `AGENTS.md` SHALL link it under `# Spikes`.
- WHEN the spike lands THE SYSTEM SHALL contain `roadmap/spikes/mctl-deploy-claude-directory.yaml`,
  a `SpikeDefinition` bound to `mctlhq/.github#259` whose `spec.outcomes` are exactly the five verdicts,
  with `lifecycle: active`, a `timebox.decisionBy`, `execution.devloop: true` and
  `evidence.report` pointing at the report, and `python roadmap/scripts/validate.py` SHALL pass.
- WHILE the owner has not recorded a decision THE SYSTEM SHALL keep the manifest without a
  `decision` block; the report SHALL state a *provisional* verdict with its reasoning.
- THE report SHALL tag every claim `[CODE]`, `[DEPLOYED]`, `[DOC]`, `[LIVE]` (observed in a real
  Claude connector session) or `unknown (not observed)`, and SHALL pin each read repository at a 40-hex commit.
- IF a source could not be read or a step could not be executed THEN THE report SHALL record it as
  `unknown (not observed)` and SHALL NOT report it as absent, passing or empty.
- THE D1 matrix SHALL cover the twelve Phase A items (endpoint/Streamable HTTP, OAuth metadata,
  Claude published-identity path, audience enforcement, tenant isolation, non-admin tool visibility,
  names/schemas/sizes, annotations, errors, limits, audit, docs/privacy/branding) as
  `requirement | current implementation | evidence | gap | owner/issue`.
- THE D2 snapshot SHALL cite current Anthropic directory/connector documentation URLs with the access date
  and SHALL NOT claim any Anthropic endorsement or Verified status.
- THE D3 tool-surface proposal SHALL classify every tool a non-admin tenant can discover as golden-path,
  optional, admin/internal-hidden, or consequential-grant-required, and SHALL map candidate names to
  canonical #254 names (`mctl_deploy_analyze`, `deploy_plan`, `get_deployment`, `promote_deployment`,
  `rollback_deployment`).
- THE D3 proposal SHALL state that no MCTL Deploy tool accepts a client-supplied `confirm` or equivalent
  self-approval, and SHALL list each currently exposed tool with a `confirm` parameter as a gap routed to
  the #254 `grants` work item.
- THE report SHALL record the serialized `tools/list` byte size and an estimated schema token footprint for
  both the current catalogue and the proposed MCTL Deploy surface, with the measuring method.
- WHEN Phase C/E steps are executed by a human with a non-admin tenant and a real Claude custom Web connector
  THE report SHALL record each step as PASS/FAIL with `[LIVE]` evidence (identifiers only, no tokens, no secret
  values, no payload bodies).
- IF a Phase C step depends on an unimplemented #254 work item (plan, grants, deploy-record, preview-onboard,
  promote-rollback-tools) THEN THE report SHALL mark it `BLOCKED (#254:<work-item>)` and SHALL NOT build or
  simulate a shadow deploy flow.
- THE D6 matrix SHALL give PASS/FAIL/UNKNOWN for every Phase D item with an owner issue for every FAIL/UNKNOWN.
- THE D7 packet SHALL be a draft only; missing privacy, terms, support, branding-rights or legal pages SHALL be
  listed as gaps, never invented.
- THE D8 section SHALL state exactly one verdict, and THE D9 map SHALL list
  `gap | owning repo | existing issue | extend/create | blocks custom connector? | blocks directory submission?`
  and propose a new issue only for gaps not already owned by #254, #236/#237, #243 or existing docs/auth work.
- WHILE writing the report THE SYSTEM SHALL NOT include secrets, access tokens, OAuth client secrets or tenant
  log bodies.

## Out of scope

- Implementing any #254 work item, a second MCP server, a deploy control plane, or a shadow deploy flow.
- Changing mctl-api tool registration, OAuth, gateway policy or gitops values.
- Submitting to Anthropic, creating a plugin/skill bundle, MCP Apps, or claiming Verified status.
- Writing legal text (privacy policy, terms).
- Opening implementation issues inside this spike's PR (the D9 map proposes them; the owner opens them).

## Open questions

- Live Claude custom-connector testing (Phase C, Phase E) needs a human with a Claude account and a fresh
  non-admin tenant identity; a DevLoop implementer cannot perform it. Proceeding: the implementer writes the
  executable test protocol and evidence template, records live steps as `unknown (not observed)`, and the
  provisional verdict is derived from code/deployed evidence; the owner (or a delegated tester) fills `[LIVE]`
  rows before recording the decision.
- Which tenant is the non-admin test tenant (an existing one such as `commerce-proof`, or a fresh one)? Not
  decided by the issue; the report recommends a fresh starter tenant and leaves the choice to the owner.
- Whether mctl-api supports Claude's published OAuth client identity (client ID metadata document) or only
  dynamic client registration was not observable from this repository; it is a Phase A item to verify against
  mctl-api code.
- The investigator principal (non-admin, no teams per `mctl_whoami`) was offered the full mctl catalogue,
  including destructive tools with `confirm` parameters. Whether that reflects mctl-api `tools/list` for any
  non-admin principal or only this run's connector configuration must be re-tested with a real tenant identity.
- Expected provisional verdict is `BLOCKED_ON_AGENT_DEPLOY` (agent-deploy epic is `proposed`; plan, grants,
  deploy-record, preview and promote/rollback items are unbound), possibly with `REVISE_CONNECTOR_SURFACE`
  findings recorded as gaps; the final verdict is the owner's.
