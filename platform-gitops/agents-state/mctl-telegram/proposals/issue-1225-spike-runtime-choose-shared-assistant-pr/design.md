# Design: issue-1225-spike-runtime-choose-shared-assistant-pr

## Current state

### In the clone (`mctlhq/mctl-telegram` at e3ff43c)

- **One repo, several images, one release path.** `Dockerfile` builds the server
  (`ghcr.io/mctlhq/mctl-telegram`). `Dockerfile.agent-worker` builds a separate runtime
  image (`ghcr.io/mctlhq/agent-worker`, preview `ghcr.io/mctlhq/agent-worker-preview`)
  from `cmd/agent-worker`. Both are published from `.github/workflows/release-please.yml`
  (lines ~77, ~200) and `.github/workflows/preview-deploy.yml` (lines ~52, ~80, ~113)
  through the centralized `mctl-gitops` release-deploy workflow. The image comment in
  `Dockerfile.agent-worker` records why the worker image is kept separate from the
  public server image. This is the in-repo precedent for an isolated adapter image
  without a new repository.
- **Managed runtime and credential boundary.** `docs/adr/0008-managed-runtime.md`
  (Accepted) gives one pooled platform worker per environment. It holds a claim-only
  `aud=agent-pool` credential and a per-job `aud=agent-job` token (`mintJobToken`,
  `internal/agentapi/events.go`), and never holds a Telegram credential.
  `docs/agent-worker.md` and `docs/agent-runtime/threat-model.md` (T1-T12) describe the
  same boundary. Every effect goes through `internal/agent/policy` and the send gate.
  The `Runner` seam is `NewWorker(client, runner)` in `internal/agentworker/worker.go`.
- **Assistant model.** `assistants/` (embedded definitions, `hr-recruiter`, JSON schemas),
  `internal/assistant`, `internal/assistantregistry` (the definition is fetched from
  mctl-api's assistant catalog) and `docs/assistants/spec.md`
  (`assistants.mctl.ai/v1alpha1`, install `runtime: own | managed`).
- **Egress safety.** `internal/netsafe/netsafe.go` is the SSRF-safe HTTP client that
  #1184's adapter contract requires.
- **No Temporal and no Glovo here.** `go.mod` has no `go.temporal.io` dependency (grep
  count 0). No `.go`/`.md` file mentions Temporal outside `docs/contracts/mctl-api-*.md`.
  No file in the clone mentions Glovo.
- **Report precedent.** `docs/reports/mcp-apps-spike.md` labels each claim as code
  fact, probe or "not measured here". The new report follows it.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/networkpolicy.yaml`: the header says
  the Temporal frontend "has no client authentication ... the network is the only
  boundary". Ingress to 7233 is allowed from mctl-api, from
  `admins-mctl-agents-worker{,-exec,-implement}` and from `labs-kuptsi-app`.
  mctl-telegram is not a client.
- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/tenant-namespace-job.yaml`: a PostSync
  Job registers Temporal namespaces `kuptsi` (7d) and `mctl-agents` (30d) plus search
  attributes. The header notes that the Temporal namespace is independent of the
  Kubernetes namespace. There is no `mctl-assistants` namespace.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker*/values.yaml`: one
  `ghcr.io/mctlhq/mctl-agents` image runs as three Deployments split by
  `--role control|execution|implementation`. They share `TEMPORAL_NAMESPACE: mctl-agents`
  and hold a GitHub token (`GITHUB_TOKEN_FILE`).
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` (lines ~350-356):
  mctl-api is a Temporal client of `mctl-agents`.
- `$MCTL_GITOPS_ROOT/services/labs/kuptsi-app/values.yaml`: this tenant service uses its
  own Temporal namespace `kuptsi`, with a sidecar worker on the same image.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image `0.134.0`,
  `AGENT_ENABLED "true"`, `AGENT_KILL_SWITCH "false"`, `ASSISTANT_REGISTRY_ENABLED "true"`.
  The kill switch semantics are documented inline.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-managed-preview/values.yaml`:
  `replicaCount: 1`, image `agent-worker-preview:main-4ccb257`, per-service Vault paths
  under `secret/data/platform/labs/agent-worker-managed-preview/*`, and an ordered
  rollback recipe in its comments.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-telegram/proposals/issue-1184-.../`: `status:
  implemented`, `pr: .../pull/1187`, approved 2026-11-07. Its design (D2) recommends a
  shared `mctl-assistants` Temporal namespace, with only mctl-api as a Temporal client,
  queues `assistants-control` and `assistants-provider-glovo`, and a provider worker in
  its own Kubernetes namespace. Expected decision: `MOCK_ONLY_PENDING_CONNECTOR`.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-948-...`: `status: proposed`
  (contract-only AutomationDefinition v1, part of .github#322).
- mctl MCP tools were not called in this run. Everything above comes from the GitOps
  checkout. Live Temporal state (which namespaces actually exist, whether an authorizer
  is configured) was **not observed**.
- Source code of `mctl-agents` and `mctl-api` was **not observed**: no checkout in this run.

## Proposed solution

Documentation only. One new file: `docs/reports/assistant-runtime-boundary-spike.md`.

### Recommended verdict: `REUSE_EXISTING` (option A), with a hard gate and a promotion trigger

The report recommends A, conditional on the owner's review. The reasoning:

1. **The boundary that isolates lower-trust provider calls is a runtime boundary, not a
   repository boundary.** The controls that keep a provider worker away from DevLoop
   are, by boundary:
   - Temporal namespace + client authorization: separate `mctl-assistants` namespace and
     an authorizer or claim mapper per worker identity (mctl-gitops#2456);
   - Kubernetes namespace: own namespace, NetworkPolicy, egress allowlist, no Vault token;
   - MCTL tenant: mctl-api derives the workflow ID and checks tenant/owner (#1184 D2).

   A GitHub repository only controls who can change the code and who can publish the
   image. Source-backed: the networkpolicy header says the network is the only Temporal
   boundary today. Moving code to a new repo leaves that unchanged.
2. **The isolated-image pattern already exists in this repo.** `Dockerfile.agent-worker`
   is a separate image with a separate runtime and dependency set, published through the
   same release-please and centralized release-deploy path (source-backed). A provider
   adapter can be the same: its own `cmd/`, its own Go module (as #1184 D4 does with
   `test/glovo-poc/go.mod`, so the server never gains `go.temporal.io/sdk`), its own
   Dockerfile and image name, and its own Kubernetes namespace and Vault path.
3. **B duplicates or fragments platform ownership.** The scheduler and Temporal workers
   are in `mctl-agents`. The registry, ledger, identity links and the Automation Control
   Plane (.github#318 outcome `EXTEND_MCTL_API`, mctl-api#948) are in `mctl-api`. The
   assistant definitions and Telegram UX are in `mctl-telegram`. A runtime repo would
   either copy one of these or become a fourth owner of workflow code with no unique
   asset of its own (model-only on the internals of mctl-api/mctl-agents).
4. **C is the right shape later, not now.** A provider-only repo becomes worth its cost
   when one of these holds: (a) a second provider or a non-Telegram surface consumes the
   adapter; (b) the owner wants a different set of people to be able to merge provider
   code or publish its image, distinct from the mctl-telegram maintainers; (c) the
   adapter's dependency or license profile must not enter this repo. None is true today:
   there is one mock provider and no sanctioned Glovo API. The report records these as
   explicit promotion triggers. If one fires, a separate repo-creation approval names the
   name, visibility, automation, branch protection, CI, release and permissions.
5. **Runtime remains DEFERred regardless of repo.** Whatever repo is chosen, no shared
   `mctl-assistants` Temporal namespace serves real tenants until all of these exist:
   Temporal client auth (mctl-gitops#2456), the narrowed NetworkPolicy entries, the #1048
   connector threat model and a sanctioned provider API. This matches #1184's
   `MOCK_ONLY_PENDING_CONNECTOR`.

If the owner judges that point 3 cannot be confirmed without reading mctl-api and
mctl-agents source, the draft decision text offers `DEFER` with the exact evidence
needed to settle it.

### Report structure (what the implementer writes)

1. Verdict, status ("Recommendation, owner decides on .github#324") and blockers, at the top.
2. Boundary glossary: Temporal namespace, Kubernetes namespace, GitHub repository, MCTL
   tenant. For each: what it isolates, what it does not, and today's state (source-backed).
3. Inventory of the current topology: the deployed-state list above, each item labelled.
4. A/B/C comparison table on these axes: queue topology, worker image lifecycle, release
   governance, runtime security, build/release CI, secrets, kill switch, failure modes, cost.
   Each cell is labelled source-backed or model-only.
5. Queue topology: shared `mctl-assistants` namespace; `assistants-control` (trusted
   worker); `assistants-provider-<provider>` (low-trust worker); per-tenant semaphore and
   per-provider circuit breaker; per-tenant queues only on measured noisy-neighbour
   impact. This is the same as #1184 D2 and is repo-independent.
6. Kill switches by layer: install `runtime` back to `own`; `AGENT_KILL_SWITCH` /
   `AGENT_ENABLED` (mctl-telegram); provider worker `replicaCount: 0`; revoke the worker
   credential; Temporal namespace deny via the authorizer. Pattern from
   `agent-worker-managed-preview/values.yaml`.
7. Cross-repo ownership map (below).
8. Implementation slices and dependency graph (below).
9. Promotion triggers for option C, and the contract a later repo-creation approval must specify.
10. Draft decision text for .github#324.
11. References with observed status: #1184/PR #1187 (implemented, merge not observed),
    mctl-api#948 (proposed), .github#322, #324, #173, mctl-gitops#2456, #2457, #1048.

### Cross-repo ownership map (proposed)

| Concern | Owner repo | Notes |
| --- | --- | --- |
| Automation Control Plane, order index, identity links, tenant/owner checks, the only Temporal client for start/signal/query/list | mctl-api | .github#318/#322, mctl-api#948 |
| Temporal workflow host for assistant control workflows (`assistants-control`) | mctl-agents (separate worker role, separate namespace `mctl-assistants`) | model-only: role-split precedent `--role` |
| Provider adapter interface plus mock and Glovo implementations; adapter image | mctl-telegram (own Go module + `Dockerfile.provider-adapter`, own image) | moves to C if a promotion trigger fires |
| Telegram commands, preview UI, callbacks | mctl-telegram | |
| Claude/ChatGPT MCP tool surface for orders | mctl-api (or mctl-telegram MCP) calling mctl-api | open in #1184 |
| Temporal namespace, authorizer, NetworkPolicy, Kubernetes namespace, Vault paths, Deployments | mctl-gitops | #2456, #2457 |
| Commerce/payment | .github#173 | out of scope here |

### Slices and dependency graph

- S0 (this proposal): the report and the draft decision. mctl-telegram, docs only.
- S1: owner decision recorded on .github#324. Depends on S0.
- S2: Temporal client authorization plus per-identity namespace/queue scoping
  (mctl-gitops#2456). Depends on S1.
- S3: mctl-api#948 contract accepted and its control-plane endpoints. Depends on S1.
- S4: #1048 connector threat model accepted. Depends on S1.
- S5: provider-adapter module and image in mctl-telegram, mock provider only. Depends on
  S1 and S4, with separate runtime-coding approval.
- S6: assistant control workflows in mctl-agents. Depends on S3 and S5.
- S7: mock deployment (`mctl-assistants-poc` namespace, provider Kubernetes namespace,
  NetworkPolicy) per mctl-gitops#2457. Depends on S2, S5 and S6, with GitOps approval.
- S8 (conditional): a C repo-creation approval. Only if a promotion trigger fires, and
  never before S1.

The graph is acyclic. No slice past S0 is part of this proposal.

## Alternatives

- **B — new `mctl-assistants` runtime repo.** Rejected for now. It adds a fourth
  workflow-code owner, an extra release pipeline, a new GitHub App installation and a
  new branch-protection surface. It isolates nothing at runtime that A cannot isolate by
  image, Kubernetes namespace and Temporal authorizer. It also risks duplicating the
  scheduler (mctl-agents) or the registry/ledger/identity (mctl-api).
- **C — `mctl-provider-adapters` repo now.** Deferred, not rejected. It gives least
  privilege over who can change and publish provider code, but with one mock provider,
  no sanctioned API and no second consumer, the cost (CI, release-please, GitOps image
  wiring, permissions review) comes before any benefit. It is kept as the documented
  promotion path.
- **DEFER the whole decision.** Offered in the draft text only as the owner's fallback.
  The repository question can be answered today because it does not depend on the
  runtime blockers. Deferring it would hold up S5 planning without reducing risk.
- **Put assistant workflows in the existing `mctl-agents` Temporal namespace.** Rejected,
  as in #1184. It mixes provider I/O with the privileged DevLoop queues and 30-day history.

## Platform impact

- Migrations: none. Backward compatibility: unaffected. One Markdown file is added.
- Resource impact: none. No image, workflow, Deployment or namespace changes.
- Risks and mitigations:
  - *The report is read as approval to build or deploy.* The status line says
    "Recommendation". Every slice past S0 names its own approval.
  - *Model-only claims about mctl-api/mctl-agents are taken as fact.* Every claim is
    labelled, and the gaps are listed in the report's open questions.
  - *Stale references* (#1187 unmerged, #948 proposed). The observed status is recorded
    with the date (2026-11-07).
  - *Sensitive data in docs.* Synthetic personas only (Alice, Bob, Carol). No
    credentials, real Glovo endpoints or account IDs.
- Existing docs tests (`docs/*_test.go`) must keep passing. The report adds no link or
  file those tests pin.
