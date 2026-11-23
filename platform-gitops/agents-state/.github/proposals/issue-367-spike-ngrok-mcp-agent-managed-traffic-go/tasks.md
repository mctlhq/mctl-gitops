# Tasks: issue-367-spike-ngrok-mcp-agent-managed-traffic-go

- [ ] 1. Pin the evidence. Record the HEAD of `mctlhq/.github` and the
  mctl-gitops commit (40-hex). Re-read https://ngrok.com/docs/mcp-server,
  `/tools`, `/prompts`, `/gateway/api-gateway/mcp-gateway`, the RBAC page and
  https://ngrok.com/blog/mcp, with the access date. — DoD: a pin table at the
  top of `docs/spikes/ngrok-mcp.md`. Every unread source is listed as
  `UNKNOWN (not observed)`.
- [ ] 2. D1 tool/scope matrix (depends on 1). — DoD: every tool on the tools
  page appears once, with annotation, scope, risk class (R0/R1/R2/W1/W2) and
  tag. Cloud Endpoint administration is kept apart from local agent tunnels.
  The anomalies are listed as UNKNOWN: `gw_create_secret`, `gw_update_secret`,
  `aigw_add_credits`, `aigw_create_provider_key`, `aigw_rotate_provider_key`
  and `delete_resource`. ChatGPT is shown as unsupported for connecting to
  ngrok's MCP.
- [ ] 3. D2 mctl state and overlap map (depends on 1). — DoD: one row each
  for:
  - `traefik-origin-pull.yaml`;
  - the redloop-staging rate-limit `Middleware`;
  - `infra-components/data/valkey/cloudflared.yaml`;
  - `release-gates.yaml`;
  - `governance/policy-checkpoint-coverage.yaml`;
  - `infra-components/observability/`;
  - `roadmap/epics/enterprise-mcp.yaml`, `cloudflare-iac.yaml` and
    `docs/plans/mcp-gateway.md`;
  - the issues .github#35, #43, #44, #292, #181, #151, #308, #314,
    mctl-agents#242 and mctl-gitops#2668.
  Each row is tagged OBSERVED, DOCUMENTED, PROPOSED or UNKNOWN. No new issue or
  epic is opened.
- [ ] 4. D3 sequence sketch and evidence envelope (depends on 2, 3). — DoD: a
  diagnostic sequence and a policy-proposal sequence (text or mermaid). No
  W1/W2 tool appears on any path. The vendor validator is labelled
  evidence-only. The envelope field list matches requirements D3, and vendor
  traffic data is marked ephemeral and distinct from git and mctl audit.
- [ ] 5. D4 synthetic scenario matrix (depends on 4). — DoD: at least 15
  rows: the 12 issue scenarios plus a mis-annotated write, `delete_resource`
  and a credits spend. Each row has the expected refusal or state, the
  observable evidence, a fixture-only reproduction plan and `NOT_RUN`.
  Optionally, `docs/spikes/ngrok-mcp/scenarios.yaml` plus a stdlib validator.
- [ ] 6. D5 threat, privacy, cost and failure matrix (depends on 2, 4). —
  DoD: all threats listed in the issue are covered, each with a mitigation and
  a test id from task 5. Unknown limits stay UNKNOWN, never PASS.
- [ ] 7. D6 decision table and verdict (depends on 3-6). — DoD: options A-D
  are compared on security, cost/limits, overhead, failure modes, lock-in and
  minimum evidence. The proposed verdict is `REFERENCE_ONLY` with its
  rationale, a banner that the owner has not decided, and at most one
  follow-up under existing ownership.
- [ ] 8. Index the report (depends on 7). — DoD: one entry under `# Spikes` in
  `AGENTS.md` linking `docs/spikes/ngrok-mcp.md` for mctlhq/.github#367 with
  the proposed verdict. Commits carry the `Agent:` trailer.

## Tests

- [ ] T1. `grep -ri ngrok` over the PR diff touches only `docs/spikes/ngrok-mcp*`
  and `AGENTS.md`.
- [ ] T2. Every tool on the vendor tools page (as pinned in task 1) is present
  in the D1 matrix. Count the rows and compare.
- [ ] T3. Every D4 row carries `NOT_RUN` and an expected refusal. No row
  claims PASS.
- [ ] T4. No D5 row has an `UNKNOWN` input with a `PASS` result.
- [ ] T5. Every `OBSERVED` tag cites a path at a pinned commit, and no issue
  text is tagged OBSERVED.
- [ ] T6. If an offline fixture exists, its validator runs offline (no
  network) and passes. This is fixture-only.
- [ ] T7. Markdown links resolve, and the `AGENTS.md` entry matches the
  existing index format.

## Rollback

This is documentation only. To roll back, revert the PR that adds
`docs/spikes/ngrok-mcp.md` (and `docs/spikes/ngrok-mcp/`, if present) and its
`AGENTS.md` line. No account, credential, ingress or runtime state is created,
so there is nothing else to undo.
