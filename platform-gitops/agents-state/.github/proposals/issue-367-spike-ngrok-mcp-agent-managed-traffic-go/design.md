# Design: issue-367-spike-ngrok-mcp-agent-managed-traffic-go

## Current state

`mctlhq/.github` pinned at `7eea364ab6ee028884506079bb5179cc12ea8db5`
(2026-11-16).

- Spike reports live in `docs/spikes/<name>.md`. Some have an offline reference
  model next to them (`docs/spikes/mcp-gateway-g0/` in Go,
  `docs/spikes/finance-assistant/` in stdlib Python). Each report is indexed in
  `AGENTS.md` under `# Spikes`. `docs/spikes/mcp-gateway-g0.md` sets the
  evidence-tag convention (`[REF]`, `[CODE]`, `[DOC]`,
  `unknown (not observed)`) and the evidence-pin table with 40-hex commits.
  `docs/spikes/edge-config-kv-instant.md` sets the "Proposed verdict ... the
  owner has not recorded a decision" convention.
- `docs/plans/mcp-gateway.md`: the gateway is deferred (D6, 2026-11-15). The
  current line is that every MCP server accepts only mctl-issued tokens for
  its own audience. A vendor MCP plane is not part of that design.
- `roadmap/epics/enterprise-mcp.yaml` (lifecycle `paused`, root .github#35)
  owns the Cloudflare MCP Portal boundary. `roadmap/epics/cloudflare-iac.yaml`
  (`completed`, root .github#47) owns declarative Cloudflare via OpenTofu
  GitOps.
- `.github/ISSUE_TEMPLATE/spike.yml` defines the Source/Question/Outcomes
  template. The issue follows it.
- A repo-wide grep for `ngrok` in this clone and in the gitops checkout
  returned no matches.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` (mctl-gitops `platform-gitops/`). Commit not pinned in
  this run; the report must pin it.
  - `grep -ril ngrok`: no matches. No ngrok resource is deployed (OBSERVED,
    within this checkout).
  - `bootstrap/templates/core-infra/traefik-origin-pull.yaml`: Authenticated
    Origin Pulls with an account-exclusive CA. Traefik only admits this
    account's Cloudflare (OBSERVED). It references
    `infrastructure/cloudflare/README.md`, which was not read.
  - `services/redloop/redloop-synthetic-staging/values.yaml:96-232`: a Traefik
    `Middleware` rate limit (average 10/s, burst 20) keyed on
    `CF-Connecting-IP`. Its comments note that the header is forgeable from
    inside the cluster (OBSERVED). This is the existing rate-limit pattern.
  - `infra-components/data/valkey/cloudflared.yaml`: the only outbound
    Cloudflare Tunnel connector (events-valkey). Its Access app is declared in
    `infrastructure/cloudflare/account/events-tunnel.tf` (DOCUMENTED, not
    read). The token comes from Vault and is mounted as a file. This is the
    existing tunnel pattern that H3 would compete with.
  - `release-gates.yaml`: release gates fail closed ("an unreadable gate is a
    refusal, never a pass") (OBSERVED). Traffic changes are not releases
    (mctl-gitops#2668).
  - `governance/policy-checkpoint-coverage.yaml`: the policy checkpoint (ADR
    014, .github#181) with `approvals_backend: mctl-api` (OBSERVED). This is the
    canonical approval path any pilot must reuse.
  - `infra-components/observability/` holds blackbox, otel-collector, tracing
    and vm-rules. This is the existing telemetry baseline for option A
    (OBSERVED by directory listing only).
- mctl MCP tools: not called in this run. The gitops checkout was enough to
  establish that no ngrok resource exists. Service hostnames were not needed.
- Vendor docs, read 2026-11-18 via WebFetch, tagged `[VENDOR-DOC]`:
  - https://ngrok.com/docs/mcp-server: endpoint `https://mcp.ngrok.com/mcp`.
    Auth is OAuth (default), a PAT (`Authorization: Bearer ngrok_pat_...`) or
    CIMD (Zed, Goose, OpenCode); "API keys and authtokens don't work". ChatGPT
    "can't connect yet". The agent "acts as you, with your role's
    permissions". "Access isn't read-only". "Changes apply to live traffic
    right away". The agent sees current configuration, "not a history of
    changes". Traffic Inspector retention follows plan retention, and
    headers/bodies appear only with full capture. There is no dedicated
    read-only mode; use a read-scoped PAT. Page date: not shown.
  - https://ngrok.com/docs/mcp-server/tools: about 80 tools in 10 groups
    (account/team, endpoints/agents/traffic, domains/addresses/certs, IP
    policies, vaults/secrets, log exports, cross-resource, docs, AI Gateway,
    feedback). Each is annotated Read-only, Changes or Destructive and mapped to
    scopes. Anomalies: `gw_create_secret` -> `vaults:read`, `gw_update_secret`
    with no scope, `aigw_add_credits` annotated read-only,
    `aigw_create_provider_key`/`aigw_rotate_provider_key` ->
    `ai-gateway:providers:read`, and `delete_resource` with a type-dependent
    scope.
  - Not read: the launch blog (https://ngrok.com/blog/mcp), `/prompts`,
    `/gateway/api-gateway/mcp-gateway` and the RBAC page. They are UNKNOWN
    until the report reads them.

## Proposed solution

Write one research report, `docs/spikes/ngrok-mcp.md`, and add an index line
in `AGENTS.md`. Nothing is deployed. The report contains:

1. **Evidence pins and tags.** A pin table (this repo, mctl-gitops commit,
   vendor URLs with access date). Tags are `OBSERVED`, `DOCUMENTED`,
   `PROPOSED`, `UNKNOWN`, `[VENDOR-DOC]` and `[VENDOR-CLAIM]`.
2. **D1 tool/scope matrix.** Every tool, with its annotation, scope and an mctl
   risk class:
   - R0: docs and validator, no account data.
   - R1: read-only account metadata.
   - R2: read-only traffic content (PII and credential capture risk).
   - W1: reversible config writes (endpoint, domain, IP rule).
   - W2: secret, vault and AI Gateway writes, credits and `delete_resource`.
   The matrix keeps Cloud Endpoint administration apart from local agent
   tunnels, and lists the anomalies above as `UNKNOWN`.
3. **D2 overlap/owner map.** One table row per adjacent issue from the issue
   body. Each row gives the owner repo, the evidence path and "not
   duplicated".
4. **D3 sequence sketch.**
   - Diagnostics: an operator principal asks, then an mctl-side adapter (not
     built) calls only R0/R1/R2 tools with a separate read-scoped service PAT.
     The response is treated as untrusted data and summarised with the source
     timestamp and resource fingerprint.
   - Policy proposal: draft a Traffic Policy diff, then
     `gw_validate_traffic_policy` (evidence only), then the mctl policy
     checkpoint and exact-action approval bound to the diff digest and the
     current HEAD, then a GitOps PR, then apply by the existing owner, then
     verification and rollback reference.
   - No W1 or W2 tool is ever on the path. Vendor OAuth/PAT scopes are an
     extra restriction layer on top of mctl authorization, never a
     replacement for it.
5. **Evidence envelope.** A field list: source timestamp, resource/account
   fingerprint, tenant and principal binding, tool and args hash, policy
   version/digest, diff, validator output, predicted effects, negative
   controls, approval id/version/TTL, PR/commit, apply verification and
   rollback. Vendor Traffic Inspector data is marked as ephemeral and
   plan-retained. The immutable record is the mctl envelope plus git history.
6. **D4 synthetic scenario matrix.** The 12 issue scenarios plus three from
   the doc anomalies: a mis-annotated write, `delete_resource`, and
   `aigw_add_credits` spending. Each row has an expected refusal (for example
   `scope_refused`, `stale_head`, `tenant_mismatch`, `evidence_expired`,
   `provider_unavailable -> UNKNOWN`), the required evidence, a reproduction
   plan against fixtures only, and `NOT_RUN`.
7. **D5 threat/failure matrix.** Covers overbroad consent, a leaked or reused
   PAT, prompt/tool injection from traffic or docs, actor/tenant confusion,
   capture leakage, accidental public exposure, unsafe rate limits,
   destructive live updates, replay/race/stale state, provider outage and
   audit gaps. Each row has a mitigation and a fail-closed test id. `UNKNOWN`
   rows stay `UNKNOWN`.
8. **D6 decision table.** Options A-D, scored on security, cost/limits,
   operator overhead, failure modes, lock-in and the minimum evidence needed
   before expansion.

   Proposed verdict: **REFERENCE_ONLY.** mctl runs no ngrok resources, so a
   diagnostics pilot would have nothing real to diagnose. Ingress is
   Cloudflare + Traefik with origin-pull mTLS and GitOps-owned Cloudflare. The
   reusable patterns are:
   - the read-scoped credential as a default;
   - the vendor validator as evidence, not authority;
   - "current state, not history" as a warning for mctl's own MCP tools.

   These can be adopted in mctl-native work (#181 evidence and the
   approval-binding work) without vendor coupling. BOUNDED_PREVIEW_EVAL (H3)
   stays a later option, gated on the owner. It overlaps the existing
   cloudflared pattern. The report states that the owner has not decided.
9. **Follow-up.** At most one, and only if justified. Candidate: a note under
   the existing #181 evidence work to add "tool annotation is not
   authorization" and "current-state-only provider" negatives. No new issue is
   opened by this spike.

An offline fixture directory, `docs/spikes/ngrok-mcp/`, is optional. Use it
only if the D4 matrix is easier to check as data (a JSON/YAML scenario list
with a stdlib validator, like `finance-assistant/`). It is never run against
ngrok.

## Alternatives

- **Read-only pilot now (READ_ONLY_DIAGNOSTICS_PILOT).** Dropped. It needs an
  ngrok account and a PAT, which are forbidden in this intake. mctl has no
  ngrok traffic to diagnose. It would also create a second telemetry and audit
  source next to the otel/blackbox stack.
- **Merge the findings into `docs/spikes/mcp-gateway-g0.md` or
  `docs/plans/mcp-gateway.md`.** Dropped. Those documents own the mctl
  gateway design, and that design is deferred. Mixing in a vendor evaluation
  would blur ownership. A separate report with cross-links follows the repo
  convention.
- **REJECT without a report.** Dropped. The issue explicitly asks for
  D1-D6. The governance patterns (annotation-is-not-authority,
  current-state-not-history) are useful negatives for #181 even if ngrok is
  never used.

## Platform impact

- Documentation only. There are no migrations, no runtime or resource impact,
  no ingress change and no cost.
- Backward compatibility: there is one new `AGENTS.md` index line and nothing
  else.
- Risk: vendor docs drift (the product launched 2 days ago). Mitigation: pin
  the access date, tag claims, and treat any later change as UNKNOWN until it
  is re-read.
- Risk: the report is read as approval for a pilot. Mitigation: an explicit
  "proposed verdict, owner has not decided" banner, and every pilot gated on a
  separately approved bounded plan.
- Risk: leaking account or traffic data. Not possible here, because no account
  is connected and all scenarios are synthetic.
