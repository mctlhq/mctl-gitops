# Spike: ngrok MCP server, agent-managed traffic and governance patterns (research only)

## Context

Issue mctlhq/.github#367 asks whether the official ngrok MCP server
(`https://mcp.ngrok.com/mcp`, launched 2026-11-16) could inform a safer,
evidence-backed mctl ingress/MCP operations workflow. Its features are endpoint
and traffic diagnostics, scoped account administration and Traffic Policy
validation. It must not replace mctl's Cloudflare/Traefik/GitOps ownership or
become a second governance authority. The outcomes allowed are
`REFERENCE_ONLY | READ_ONLY_DIAGNOSTICS_PILOT | BOUNDED_PREVIEW_EVAL | REJECT`.
The intake is research only: no ngrok account, no OAuth consent, no PAT, no live
traffic and no mctl ingress change.

This matters because the vendor's own docs say "Access isn't read-only". They
also say "Changes apply to live traffic right away" and that the agent "acts as
you, with your role's permissions". mctl already has canonical authorities:
mctl identity and tenant, policy checkpoint, exact-action approval, release
gates, GitOps apply and Cloudflare OpenTofu. A vendor plane that can mutate
endpoints, IP rules, secrets and AI Gateway settings has to be judged against
those authorities, not added next to them. The deliverable is one spike report
in this repository, following the existing `docs/spikes/*.md` convention, with
a proposed verdict that the owner decides.

## User stories

- AS the platform owner I WANT a source-pinned matrix of ngrok MCP tools,
  scopes and limits SO THAT I can judge vendor claims without connecting an
  account.
- AS an mctl operator I WANT a grounded map of the current mctl ingress state
  (Cloudflare, Traefik, cloudflared, WAF and rate limits, release gates, policy
  checkpoint) with every item tagged by its evidence SO THAT the spike adds
  nothing that already exists.
- AS a security reviewer I WANT a threat model and a fail-closed negative-test
  matrix SO THAT any later pilot is judged on deterministic refusals, not on
  vendor tool annotations.
- AS a DevLoop maintainer I WANT a decision table with one proposed verdict
  and an owner-review gate SO THAT no pilot starts without an explicit
  approval.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL add
  `docs/spikes/ngrok-mcp.md` and add a one-entry index line to `AGENTS.md`
  under `# Spikes`. No other file is changed, except an optional offline
  fixture directory `docs/spikes/ngrok-mcp/`.
- THE SYSTEM SHALL pin every ngrok fact to a source URL and an access date
  (2026-11-18 or later). It SHALL tag each fact `[VENDOR-DOC]` (current docs
  page), `[VENDOR-CLAIM]` (launch blog of 2026-11-16) or `UNKNOWN`.
- THE SYSTEM SHALL tag every mctl capability as `OBSERVED` (read in code or
  gitops at a pinned 40-hex commit), `DOCUMENTED` (issue, plan or ADR text),
  `PROPOSED` or `UNKNOWN`. Issue text SHALL never be tagged `OBSERVED`.
- D1: THE SYSTEM SHALL include a tool/scope/annotation matrix that covers all
  tool groups in https://ngrok.com/docs/mcp-server/tools. It SHALL keep Cloud
  Endpoint administration (`gw_create_cloud_endpoint`,
  `gw_update_cloud_endpoint`) apart from local agent/CLI tunnel sessions
  (`gw_list_agents`, read-only). It SHALL flag annotation and scope anomalies
  as `UNKNOWN`, not trust them. Examples: `gw_create_secret` lists scope
  `vaults:read`, `aigw_add_credits` is annotated read-only, and
  `delete_resource` has a type-dependent scope.
- D2: THE SYSTEM SHALL map mctl state and overlap against .github#35, #43,
  #44, #292, #181, #151, #308, #314, mctl-agents#242 and mctl-gitops#2668.
  Each row SHALL carry a file path or issue reference, and the spike SHALL NOT
  open a new issue or epic.
- D3: THE SYSTEM SHALL describe a diagnostic and policy-proposal sequence in
  which every ingress effect flows through a reviewed GitOps PR and mctl
  exact-action approval. The sequence is: inspect, draft diff, vendor
  validate, mctl policy/evidence check, human decision, GitOps apply, verify.
  The vendor validator output SHALL be recorded as evidence only.
- D4: THE SYSTEM SHALL list a synthetic scenario matrix that covers at least
  the 12 scenarios named in the issue. Each row SHALL carry the expected
  outcome, the expected refusal code or state, the observable evidence and the
  marker `NOT_RUN`.
- D5: THE SYSTEM SHALL include a threat, privacy, cost/limits,
  audit-retention and failure-mode matrix, in which `UNKNOWN` is never counted
  as `PASS`.
- D6: THE SYSTEM SHALL include a decision table comparing options A-D from the
  issue. It SHALL state one proposed verdict and SHALL say that the owner has
  not decided.
- IF a vendor scope, OAuth grant, tool annotation or validator result would
  permit an action that mctl policy, tenant binding or approval does not permit
  THEN THE SYSTEM SHALL specify refusal. Vendor controls may only restrict.
- WHILE the issue is in this intake THE SYSTEM SHALL NOT connect to ngrok,
  create credentials, read live traffic, change any ingress, Cloudflare,
  Traefik, ArgoCD, WAF or RedLoop configuration, or spend money.
- IF a source cannot be read THEN THE SYSTEM SHALL record it as
  `UNKNOWN (not observed)` and SHALL NOT treat it as absent.
- WHEN the report names a follow-up THE SYSTEM SHALL name at most one, under
  existing repository ownership, and only if the evidence justifies it.

## Out of scope

- Any ngrok account, OAuth consent, PAT, Traffic Inspector query, endpoint,
  domain, IP policy, vault/secret or AI Gateway change.
- Any change to mctl Traefik, Cloudflare (`infrastructure/cloudflare/`),
  ArgoCD, release gates (`release-gates.yaml`), the WAF/RedLoop kill switch or
  rate-limit middlewares.
- Implementation code, adapters, MCP server registration and pilots.
- New epics or implementation issues, issue closure and DevLoop approval.
- Migrating any mctl ingress to ngrok.

## Open questions

- Plan-specific limits are not stated on the pages read: Traffic Inspector
  retention, full-capture availability, MCP rate limits and Free-plan tool
  parity. The report records them as `UNKNOWN` until a vendor page states
  them. A pilot must not assume them.
- Several scope annotations look inconsistent (`gw_create_secret` with
  `vaults:read`, `aigw_add_credits` read-only, `aigw_create_provider_key` with
  a read scope). It is unknown whether these are documentation errors or real
  behaviour. Treat them as unsafe until clarified.
- The proposed verdict is `REFERENCE_ONLY`, because mctl runs no ngrok
  resources (none observed in gitops). The owner may prefer `REJECT` if pattern
  notes alone are not wanted. This is recorded, not blocking.
- `infrastructure/cloudflare/` in mctl-gitops was outside the checkout read in
  this run. The Cloudflare WAF and portal state is therefore `DOCUMENTED` (via
  gitops comments) and has not been observed directly.
