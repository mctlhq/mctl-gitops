# Design: issue-314-spike-evaluate-dapr-as-an-optional-secur

## Current state

### Repository conventions (mctlhq/.github at `dc359d44f25bbe3cd9d6d23a865eb89773ee1cf0`)

- Spike reports live in `docs/spikes/<name>.md` and are indexed under `# Spikes`
  in `AGENTS.md`. Each established report opens with "Non-claims and evidence
  tags" and an "Evidence pins" table of 40-hex commits
  (`docs/spikes/mcp-gateway-g0.md`, `docs/spikes/journey-intent-correlation.md`,
  `docs/spikes/edge-config-kv-instant.md`), and closes with a proposed verdict
  and limitations.
- Each spike has a manifest `roadmap/spikes/<name>.yaml` validated against
  `roadmap/schemas/spike-definition.schema.json`. Required fields: `title`,
  `question`, `lifecycle`, `github.issue`, `outcomes` (at least two, pattern
  `^[A-Z][A-Z0-9_]*$`). A `decision` block is allowed only with
  `lifecycle: decided`, and the owner records it
  (`roadmap/spikes/journey-intent-correlation.yaml` comment: "an agent does not
  record its own approval"). Validation: `roadmap/scripts/validate.py`
  (`DEFAULT_SPIKES = ROOT / "spikes"`), tests in
  `roadmap/tests/test_validate_spike.py` (including `test_committed_corpus`).
- Prior decisions this spike must not contradict:
  - `docs/plans/mcp-gateway.md` (epic `roadmap/epics/mcp-gateway.yaml`,
    .github#236, `lifecycle: proposed`). Per-principal, per-tenant tool policy
    is decided by an mctl-owned gateway with policy in mctl-api (Postgres) and a
    ceiling in mctl-gitops. Every downstream re-checks its own authz. "The edge
    may deny more, never grant more than mctl permits."
  - `docs/spikes/mcp-gateway-g0.md` (decided REVISE). mctl-api tokens are HS256
    with no `aud` (`verifyJWT` ignores audience), and the RFC 8693 exchange
    gives downstreams a token bound to their own audience with `act.sub` = the
    gateway. Downstream membership checks are `PrincipalAuthz.Apply` and
    `authorizeSubject`.
  - `docs/spikes/agent-governance-decision-assurance.md`. Approval binding is
    `workitems#IntentHash` (single CAS spend), and `ActionRequest.action_digest`
    is the policy-checkpoint input. Execution identities are `we_`, `aar_`,
    `wi_`.
  - `docs/plans/agent-commerce.md`. Execution requests use leases and fencing
    (mctl-api#366/#368), and budgets use reserve/capture/release with an
    outbox.
- Related epics: `roadmap/epics/agent-runtime-assurance.yaml` (.github#151,
  active, adversarial boundary suites) and
  `roadmap/epics/telegram-managed-runtime.yaml` (mctl-telegram#1088).

### Service-to-service trust boundary as declared in GitOps

- Tenant namespaces are default-deny for ingress and egress, with optional
  intra-namespace and scoped cluster egress
  (`helm-charts/tenant/templates/networkpolicy.yaml`, `default-deny-all`,
  `allow-intra-namespace`, `allow-cluster-egress`). Enforcement is k3s'
  embedded kube-router (cited in the Temporal policy comment).
- The Temporal frontend has **no client authentication**. Its policy says:
  "Until client auth exists (separate follow-up) the network is the only
  boundary." Clients are mctl-api, the three `admins/mctl-agents-worker*`
  deployments and `labs/kuptsi-app`
  (`infra-components/data/temporal/networkpolicy.yaml`).
- Agent step pods reach the internet only through the egress proxy, and the
  proxy accepts only pods labelled `app.kubernetes.io/name: mctl-agents` from
  `argo-workflows`
  (`infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`).
- Valkey uses a per-user ACL (producers `XADD` only, `default off`) plus a
  NetworkPolicy (`infra-components/data/valkey/networkpolicy.yaml`, summarised
  in `docs/spikes/edge-config-kv-instant.md`).
- No service mesh, SPIFFE/SPIRE or Dapr is declared anywhere in the gitops
  checkout (grep for `dapr|linkerd|istio|cilium|spiffe|spire` outside
  `agents-state/` found no deployment manifests). Workload identity between
  services is therefore network position plus application bearer tokens; no
  mTLS workload identity is declared.

### Resource headroom

`docs/plans/mcp-gateway.md` "Current state" records three cx43 workers with
CPU 11-16% used, memory 60-73% used, limits over-committed (112-125%), and "no
new node is needed or allowed". `services/admins/mctl-agents-worker/values.yaml`
requests 50m/320Mi with limits 500m/576Mi. Per-pod sidecar memory is therefore
the binding cost dimension for any sidecar option.

Deployed state checked:
- `mctl_list_services(team=labs)`: 21 catalogue services, all Synced.
  Includes MCP-serving downstreams `coolify-mcp` (coolify.mctl.ai),
  `projects-mcp` (projects.mctl.ai), `seerrsense`, `mctl-alice`,
  `mctl-telegram` (tg.mctl.ai, 0.123.2), plus `agent-worker-managed-preview`
  (`main-4ccb257`) and `agent-worker-preview`. No Dapr component or sidecar
  image appears in any listed image.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-managed-preview/values.yaml`:
  managed-runtime pool worker, 1 replica, ingress disabled, reaches an
  OpenAI-compatible model through a Cloudflare AI Gateway. Live since
  2026-11-03 with no account on the managed runtime yet.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api
  image tag `4.154.0`, `TEMPORAL_ADDRESS
  temporal-frontend.temporal.svc.cluster.local:7233`, `TEMPORAL_NAMESPACE
  mctl-agents`.
- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/networkpolicy.yaml`,
  `.../mctl-agents-egress-proxy/networkpolicy.yaml`,
  `helm-charts/tenant/templates/networkpolicy.yaml`: as above.
- Not observed: mctl-api deployed `TENANT_AUTHZ_MODE`, whether audience
  enforcement from mctl-api#805 is deployed, and mctl-api, mctl-agents and
  mctl-telegram source code (not in this clone). These are recorded under Open
  questions and must be re-checked or marked unknown in the report.

## Proposed solution

Add three files to `mctlhq/.github`. Nothing else changes.

1. `docs/spikes/dapr-mctl.md`, the decision report.
2. `roadmap/spikes/dapr-mctl.yaml`, the SpikeDefinition with
   `lifecycle: proposed`, outcomes `ADOPT_BOUNDARY`, `ADOPT_ADAPTER`,
   `ADOPT_BOTH_OPTIONAL`, `REFERENCE_ONLY`, `NO_GO`, issue mctlhq/.github#314,
   `execution.devloop: true`, `evidence.report: docs/spikes/dapr-mctl.md`, and
   no `decision`.
3. One `AGENTS.md` index line under `# Spikes`.

### Report structure (`docs/spikes/dapr-mctl.md`)

1. **Header, non-claims, evidence tags.** No Dapr deployment, nothing written
   outside this repository, recommendation is not approval. Tags: `[CODE]`,
   `[CONFIG]`, `[LIVE]`, `[DOC]`, `[DAPR-DOC]`, and `unknown (not observed)`.
2. **Evidence pins.** 40-hex commits for each MCTL repository read and the
   mctl-gitops commit. For Dapr: the runtime release and the Dapr Agents
   release the cited pages describe, the page URLs (the four upstream references
   in the issue plus the service invocation ACL and middleware/OPA pages), and
   the read date.
3. **D1 trust-boundary diagram** (Mermaid flowchart). MCP client, Cloudflare,
   mctl-api `/mcp` (stateless Streamable HTTP with a REST re-check under the
   caller bearer), planned mcp-gateway, the downstreams, Temporal frontend,
   workers, Argo CWFT pods, egress proxy, Valkey, managed-runtime worker and
   bridge. Each edge is annotated with its control (NetworkPolicy, bearer,
   ACL, none).
4. **D2 capability/duplication matrix.** One row per boundary listed in the
   requirements. Columns: current control and owner, cited file, overlapping
   Dapr capability (service invocation, App-ID ACL, mTLS/Sentry, middleware/OPA,
   API allowlist, component scoping, secrets, pub/sub, state, workflow, actors,
   Dapr Agents), classification (`closed-by-existing`, `gap-dapr-could-close`,
   `gap-better-closed-otherwise`, `out-of-scope`) and duplication risk. Two rows
   the investigation already expects, to be confirmed or refuted:
   - Temporal frontend without client auth: `gap-better-closed-otherwise`.
     Temporal's own mTLS/authorizer is the native fix, and routing Temporal gRPC
     through Dapr service invocation is not a supported Temporal client path. To
     confirm against both docs.
   - Valkey, Temporal/Argo and outbox against Dapr pub/sub, state, workflow and
     actors: duplication only. Any adoption would create a second state or
     orchestration authority, which is a hard no-go.
5. **D3 H1 analysis: tool boundary.** What a Dapr ACL actually matches (caller
   App-ID from the Sentry-issued SPIFFE identity, trust domain, namespace,
   operation path, HTTP verb, with default action deny). MCP Streamable HTTP
   puts every tool call on one path (`POST /mcp`) with the tool in the JSON-RPC
   body, so the ACL cannot tell `api_list_services` from `api_delete_service`.
   Per-tool mediation therefore needs body-aware middleware (OPA HTTP
   middleware) or stays in the MCTL gateway. The report weighs a second policy
   point at the sidecar against D3 of `docs/plans/mcp-gateway.md` ("decided by
   mctl-api policy"). OPA in the sidecar holding tool rules would be a second
   policy store, so it is NO_GO under the issue's constraint unless it is
   strictly deny-only and derived from the gitops ceiling. Also analysed:
   whether caller tenant context is cryptographically bound (Dapr mTLS binds the
   workload, not the user or tenant; the user/tenant binding remains the
   exchanged token from G0), forwarded-identity spoofing (headers set by the
   app), and bypass when a pod reaches the app port directly (needs
   NetworkPolicy or app-side checks anyway). The candidate incremental value is
   workload-level mTLS admission between trusted backends, which the current
   stack lacks.
6. **D4 H2 analysis: executor adapter.** An adapter contract sketch (fields and
   semantics, no code) with these operations:
   - `Submit(execution_id we_, work_item_id wi_, principal, tenant, grant_ref aar_, intent_hash, caps{tokens, wallclock, spend_reservation_id}, idempotency_key)`
   - `Status/Stream(execution_id)` returning MCTL phases
   - `Cancel(execution_id, fence_epoch)`
   - `Retry`, where the idempotency key is per `(intent, attempt)` as in
     `action_approvals.py#idempotency_key`
   - `EvidenceRef(execution_id)`

   A mapping table from MCTL execution and lease states (pending, claimed under
   lease, fenced, running, cancel-requested, terminal phases, unknown outcome
   that needs reconciliation per `docs/plans/agent-commerce.md`) to Dapr
   workflow/agent states. Unsupported cases are listed explicitly, for example
   lease fencing epoch, "unknown remote outcome is not failure", grant spend
   exactly once, and tool calls made by a Dapr agent outside MCTL's policy
   checkpoint. Each has an abort condition (the adapter refuses submission when
   the case cannot be mapped). Invariant: Temporal DevLoop remains the
   orchestrator. A Dapr Agents run is at most one leaf activity whose tool calls
   all go through the MCTL gateway with the exchanged token, and which holds no
   credentials beyond that.
7. **D5 H3: actors.** Reference only unless evidence shows atomic
   single-owner transitions equal to the bridge state machine. Actor
   turn-based concurrency is not a process isolation boundary.
8. **D6 threat model.** Assets, actors (external caller, compromised agent
   subprocess, compromised sidecar, tenant pod), trust boundaries and policy
   owner per boundary. Paired allow/deny table (see Tests in tasks.md). It
   includes the two mandatory proofs: MCTL denies a forbidden write although
   the ACL allows the App-ID, and Dapr denies an unapproved caller with zero
   handler invocations. It also covers sidecar API exposure to untrusted agent
   code (`APIAllowList`, `dapr-api-token`) and control-plane (Sentry/injector)
   outage behaviour.
9. **D7 disposable experiment design.** An isolated throwaway kind/k3d cluster,
   never the production cluster. Two MCP endpoints (read-only and governed write
   stub), two tenants, two caller identities, Dapr with default-deny ACL. The
   baseline runs first: direct path with NetworkPolicy plus bearer re-check.
   Variables: path (direct vs sidecar), payload size, concurrency.
   Pre-registered thresholds, for example: added p95 latency of at most 5 ms
   in-cluster, sidecar memory of at most 64 Mi per pod, and zero unexpected
   allows in the refusal suite. These are proposals for the owner to agree, not
   results. Operability estimate covers the control-plane components, upgrade
   cadence, certificate rotation and debugging hops.
10. **D8 owner decision table.** One row per capability (service invocation,
    ACL, mTLS, OPA middleware, Dapr Agents, workflow, actors, pub/sub, state,
    secrets) with the proposed decision (`useful-now`, `possible-later`,
    `non-goal`), prerequisites, no-go conditions and the recommended next small
    action, or an explicit no-action.
11. **Verdict.** Independent H1, H2 and H3 verdicts and the overall
    recommendation, labelled "proposed, not approved".
12. **Limitations.**

Expected direction, stated as a hypothesis the report must test rather than
assume: H1 is unlikely to beat NetworkPolicy plus the planned gateway on
per-tool or per-tenant value. Its only plausible increment is workload mTLS,
and that has to be weighed against a mesh-free cluster on tight memory. H2
risks a second orchestrator. The likely overall outcome is `REFERENCE_ONLY` or
`NO_GO`, but the verdict follows the evidence.

## Alternatives

- **Run the disposable experiment inside this spike.** Dropped. The issue limits
  this spike to a design ("design for a disposable, isolated proof"), forbids
  presenting unmeasured numbers, and requires thresholds agreed before
  execution. Running it needs a separate owner-approved issue.
- **Add a reference model in code (as `docs/spikes/mcp-gateway-g0/` did in Go).**
  Dropped for now. A model of Dapr ACL semantics would only restate the docs and
  would not be evidence about the Dapr runtime. The refusal tests are meaningful
  only against real sidecars in the later experiment. The report may include
  the ACL example YAML as a quoted fixture.
- **Fold the evaluation into `docs/plans/mcp-gateway.md`.** Dropped. The issue
  says the overlap is architectural only and forbids implementation
  authorization. Editing an accepted plan would blur ownership.
- **Bind the spike to an epic work item.** Dropped. The issue states "NOT a new
  required work item". The manifest therefore omits `spec.epic`, as
  `journey-intent-correlation.yaml` does.

## Platform impact

- Migrations: none. Documentation and one roadmap manifest only. No runtime,
  gitops or cluster change.
- Backward compatibility: the new manifest must pass
  `roadmap/scripts/validate.py` and `test_committed_corpus`. A spike that is not
  bound to an epic does not change epic readiness or publication output.
- Resource impact: none now. The report quantifies only the projected sidecar
  cost, against the memory-constrained cluster recorded in
  `docs/plans/mcp-gateway.md`.
- Risks and mitigations:
  - The report is read as authorization. Mitigation: a non-claims header,
    `lifecycle: proposed`, no `decision` block and no follow-up issues.
  - Dapr docs drift. Mitigation: pin versions and read dates, and give re-open
    triggers.
  - MCTL source unavailable to the implementer. Mitigation: rows become
    `unknown (not observed)`, and the verdict is weakened explicitly, never
    inferred.
  - Secrets leak into the report. Mitigation: cite file paths and key names
    only, as `edge-config-kv-instant.md` does ("no secret values quoted").
