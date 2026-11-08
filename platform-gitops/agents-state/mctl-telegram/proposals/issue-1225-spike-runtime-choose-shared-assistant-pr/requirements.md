# Spike: choose the repository boundary for the shared assistant/provider runtime (Glovo rollout)

## Context

Issue mctlhq/mctl-telegram#1225 asks for an executable research companion to the
canonical org-level decision mctlhq/.github#324. It must decide where the shared
assistant runtime and the lower-trust provider adapter (first consumer: the Glovo
assistant from #1184 / PR #1187) live in source control. The candidates are:
A (no new repo: Automation Control Plane in `mctl-api`, Temporal execution in
`mctl-agents`, Telegram commands/UI in `mctl-telegram`, adapter as an isolated
image), B (a new `mctl-assistants` runtime repo) and C (a small
`mctl-provider-adapters` repo). The output is a report under
`docs/reports/` with exactly one verdict
(`REUSE_EXISTING | NEW_ASSISTANTS_RUNTIME_REPO | NEW_PROVIDER_ADAPTER_REPO | DEFER`),
a cross-repo ownership map, dependency-ordered implementation slices and draft
decision text for .github#324.

It matters because the four boundaries that are easy to conflate (Temporal
namespace, Kubernetes namespace, GitHub repository, MCTL tenant) protect
different things. The deployed state shows the Temporal frontend has no client
authentication (`infra-components/data/temporal/networkpolicy.yaml`: "Until client
auth exists ... the network is the only boundary"). A repository split does not
change that. Choosing a repository before that is understood would add release,
CI and permission surface without adding runtime isolation. This proposal is
documentation only. Runtime code, a new repository and GitOps deployment each
need their own later approval.

## AMEND 2026-11-08 — multi-tenant and cross-namespace boundary (normative)

The owner selected **multi-tenant from first usable release** at `https://glovo.mctl.ai/mcp`, a non-Telegram MCP surface. The option-C repository promotion trigger (a second surface/credential trust boundary) MUST be re-evaluated; `REUSE_EXISTING` remains only a **provisional fake-adapter recommendation**, not an approved repository decision on .github#324.

- Control work runs in Temporal namespace `mctl-assistants`; lower-trust Glovo provider work runs in a **different** Temporal namespace `mctl-assistants-provider-glovo` and a separate K8s workload namespace. Stock Temporal authorizer enforces roles per namespace, **not per task queue**. Provider has no identity/role on control or `mctl-agents`. MCTL user/tenant/order authorization belongs to mctl-api.
- Ordinary Temporal Activities cannot jump namespaces. The report MUST select or explicitly BLOCK an inter-namespace bridge: Temporal Nexus (only after proving running OSS server/SDK support, endpoint permissions and negative calls), or a tightly authenticated mctl-api command/results bridge. Specify idempotency, dedupe, timeout, retries, cancellation, token/secret handling, per-user consent and provider->control denial tests. Neither transport can weaken provider least privilege.
- The merged mctl-api contract PR #950 (#948, 2026-11-08) contains **contracts only**. It does NOT implement Glovo connection ownership, tenant selection, per-order index or ActionApprovalRequest integration; create separately approved mctl-api follow-up slices. The public MCP facade cannot fall back to a Telegram OAuth principal or deployment-wide `labs`/`mctl` tenant.
- **This proposal remains DOCS ONLY.** No new repo, image, runtime, Temporal namespace, Glovo API access, GitOps, DNS or deployment is authorized by its approval.

## User stories

- AS the platform owner I WANT one evidence-backed recommendation between A, B and C
  SO THAT I can close .github#324 without a second roadmap epic or a speculative repo.
- AS a security reviewer I WANT the four isolation boundaries kept separate, with
  each control tied to the boundary it actually enforces, SO THAT a lower-trust
  provider adapter cannot reach DevLoop queues, other tenants or platform secrets.
- AS a later implementer I WANT an ownership map and slices with an explicit
  dependency graph SO THAT each slice can be approved and built in order without
  skipping Temporal auth (mctl-gitops#2456) or the connector threat model (#1048).
- AS a reader of the report I WANT every claim labelled source-backed or model-only
  SO THAT I know which conclusions rest on code and GitOps I can check.

## Acceptance criteria (EARS)

- WHEN the implementer delivers this proposal THE SYSTEM SHALL add exactly one new
  report, `docs/reports/assistant-runtime-boundary-spike.md`, and no change outside `docs/`.
- WHEN the report states a verdict THE SYSTEM SHALL state exactly one of
  `REUSE_EXISTING`, `NEW_ASSISTANTS_RUNTIME_REPO`, `NEW_PROVIDER_ADAPTER_REPO` or `DEFER`
  at the top. It SHALL give that verdict as a recommendation to the owner, not as a
  decision.
- WHEN the report compares the alternatives THE SYSTEM SHALL evaluate A, B and C on
  the same axes: queue topology, worker image lifecycle, release governance, runtime
  security, build/release CI, secrets, kill switch, failure modes and cost.
- WHEN the report names an isolation control THE SYSTEM SHALL name which of the four
  boundaries it enforces: Temporal namespace, Kubernetes namespace, GitHub repository
  or MCTL tenant.
- WHILE the Temporal frontend has no client authorizer THE SYSTEM SHALL record any
  shared `mctl-assistants` Temporal namespace as blocked for multi-tenant use. It
  SHALL be allowed only behind Temporal client authorization plus mctl-api
  tenant/user checks.
- WHEN the report makes a claim THE SYSTEM SHALL label it `source-backed` (with the
  file path or tool call) or `model-only`.
- WHEN the report refers to prior decisions THE SYSTEM SHALL link #1184 / PR #1187,
  mctl-api#948, .github#322, .github#324, mctl-gitops#2456, mctl-gitops#2457, #1048
  and .github#173. It SHALL record each one's observed status without upgrading it.
- WHEN the report proposes slices THE SYSTEM SHALL give each slice an owner repo, a
  dependency list and the approval it needs. The dependency graph SHALL contain no
  cycles.
- IF the evidence is insufficient to discriminate between options THEN THE SYSTEM
  SHALL say so in the draft decision text and leave the choice to the owner.
- IF any slice requires a new repository THEN THE SYSTEM SHALL record it as a
  separate later approval naming the exact name, visibility, automation, branch
  protection, CI, release and permission contract, and SHALL NOT create it.
- WHILE this proposal is implemented THE SYSTEM SHALL make no change to Go code,
  `go.mod`, Dockerfiles, CI workflows, GitOps, feature flags or credentials, and
  SHALL perform no Glovo API call, checkout, order, payment or activation.

## Out of scope

- Creating any GitHub repository, Temporal namespace, Kubernetes namespace, Vault path
  or tenant.
- Any GitOps write, including `tenant-namespace-job.yaml` and `networkpolicy.yaml`.
- Runtime code, a Temporal SDK dependency or a provider adapter implementation.
- Real Glovo credentials, endpoints, carts, checkout, payment or order placement.
- Choosing on behalf of the owner: the report recommends and the owner decides on .github#324.
- A second roadmap epic.

## Open questions

- mctl-api#948 was observed as `proposed` in the original 2026-11-07 investigator snapshot; PR #950 merged on 2026-11-08 as a **contract-only** change. The report records dated observations, and requires a new issue for the Glovo-specific APIs.
- #1184 is `status: implemented` with PR #1187, but the clone's `main` (e3ff43c) has
  none of its files (`docs/reports/glovo-assistant-spike.md`,
  `docs/adr/0009-assistant-temporal-tenancy.md`, `test/glovo-poc/`). Whether PR #1187
  has merged was not observed. The report cites its proposal text and marks
  dependence on unmerged artifacts.
- The `mctl-agents` and `mctl-api` source code was not readable in this run. Claims
  about their internal worker structure, queue registration and Temporal client code
  are drawn from GitOps comments only and are labelled model-only where they go further.
- The content of mctl-gitops#2456 (Temporal auth) and #2457 (deployment plan) was not
  read. The report treats Temporal client authorization as an unmet prerequisite,
  consistent with the live NetworkPolicy comment.
- Whether a second provider or a non-Telegram surface will consume the adapter within
  the planning horizon is unknown. It is the main trigger for promoting option C
  later, and the report states that trigger explicitly.
