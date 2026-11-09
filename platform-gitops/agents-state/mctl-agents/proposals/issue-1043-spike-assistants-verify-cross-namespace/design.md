# Design: issue-1043-spike-assistants-verify-cross-namespace

## Current state

### mctl-agents (this clone)

- Temporal Python SDK pinned at `temporalio==1.34.0` (`pyproject.toml` line 62). `uv.lock` shows it depends on `nexus-rpc==1.4.0`, so the Nexus operation/handler API ships with the SDK already in the image. Nothing in `orchestrator/` uses Nexus today. The only reference is the trace-attribute allowlist in `orchestrator/tracing_sdk.py` (`NexusService|NexusOperation` keys from `temporalio.contrib.opentelemetry`).
- Every client connects with no credential and no TLS: `Client.connect(address, namespace=namespace, runtime=runtime)` in `orchestrator/temporal/worker.py` (line 871) and `Client.connect(address, namespace=namespace)` in `orchestrator/temporal/start.py` (line 53). All workflows run in one namespace (`TEMPORAL_NAMESPACE=mctl-agents`), on task queues from `orchestrator/temporal/constants.py`.
- There is a working precedent for an authenticated, idempotent mctl-api bridge: `orchestrator/temporal/dispatcher.py` claims an mctl-api execution request under a lease (CAS, lapsed lease reclaimable under a new claim token), delivers it with Update-with-Start using the request id as update id, then fulfils it. Its docstring proves "no order of crashes produces a second run". `orchestrator/work_context/client.py` (`WorkItemClient`) is the HTTP side.
- `orchestrator/action_approvals.py` is the `aar_` receipt client: `create`/`get`/`consume`/`execute` on `/api/v1/action-approvals{,/{id},/{id}/consume,/{id}/execute}`, with `intent_hash()` reproducing mctl-api's `workitems.IntentHash`. Consume is atomic and single-use; that is the consume point the provider fake mutation must reuse.
- `orchestrator/temporal/mctl_client.py`: worker-to-mctl-api calls use a static admin service token (`MCTL_TOKEN`). A provider must NOT reuse that identity.
- `orchestrator/spike_issue.py`: a spike's merged PR must use `Refs`, not `Closes`. Spike deliverables live under `docs/spikes/<issue>-<slug>.md` with an optional `docs/spikes/<issue>/` artifact directory (for example `docs/spikes/807-agent-isolation-k8s.md`, `docs/spikes/791/` with offline tests in `tests/test_hetzner_inference_spike.py`).

### Temporal server and network (mctl-gitops, desired state)

- `platform-gitops/bootstrap/templates/data/temporal.yaml`: chart `temporal` 1.2.0, server appVersion 1.31.0, one replica, frontend `ClusterIP`. The values contain no `dynamicConfig`, no TLS block and no `authorization` block. So: no Nexus-specific dynamic config (for example `system.enableNexus`, `component.callbacks.allowedAddresses`) and no frontend HTTP address override are declared.
- `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`: header states "the Temporal frontend has no client authentication"; the network allowlist (mctl-api namespace, the three admins workers, labs kuptsi-app) is the only boundary on 7233. Only port 7233 (gRPC) and 9090 (metrics) are admitted; the frontend HTTP port used by Nexus is not.
- `platform-gitops/infra-components/data/temporal/tenant-namespace-job.yaml`: creates `kuptsi` and `mctl-agents` with `temporalio/admin-tools:1.31.0`, unauthenticated. No `mctl-assistants*` namespace and no `temporal operator nexus endpoint create` exist.
- `platform-gitops/agents-state/mctl-gitops/proposals/issue-2456-security-temporal-authenticate-and-autho/` (status `implemented`, PR mctl-gitops#2467): ADR for JWT `claimMapper: default` + `authorizer: default`, namespace-by-role permissions, no task-queue dimension, future `temporal-provider-<name>` identity with `["mctl-assistants-provider-<name>:write"]` only. It states "Control-to-provider handoff crosses namespaces through mctl-api or Nexus, as the ADR decides" — this spike is that decision.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api image tag 4.154.0, `TEMPORAL_NAMESPACE: mctl-agents`.

Deployed state checked:

- `mctl_list_services team=admins`: complete=true; `mctl-agents-worker`, `-exec`, `-implement` all Synced on `ghcr.io/mctlhq/mctl-agents:1.117.0`. No assistants or provider service exists in `admins`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml` and `.../mctl-agents-worker-exec/values.yaml`: `TEMPORAL_ADDRESS=temporal-frontend.temporal.svc.cluster.local:7233`, `TEMPORAL_NAMESPACE=mctl-agents`, no Temporal credential.
- `grep -ri assistants` over `$MCTL_GITOPS_ROOT/services` and `$MCTL_GITOPS_ROOT/tenants`: no match. No `mctl-assistants*` service or tenant is declared.
- Not observed: the live Temporal server image and its dynamic config, the registered namespaces and Nexus endpoints (no read access to the `temporal` namespace through the mctl tools). Not observed: the mctl-api Go SDK version (mctl-api source not in this run). These are recorded as gaps, not as absent.

## Proposed solution

### AMEND 2026-11-08 — independent reviewer test integrity

The Nexus operator permission gate tests `temporal-system:admin` and the real source-backed namespace role/RPC matrix. A `system:admin` JWT example is invalid and MUST NOT appear in fixtures. The offline `tests/test_spike_1043_contracts.py` validation **cannot skip** when `jsonschema` is absent. If the pinned test dependency is missing, fail and require an explicitly reviewed dependency update; record the number of positive and negative cases actually validated. A green job with all schema tests skipped is a review failure. No production Nexus or API bridge is implemented by this proposal.



The spike delivers documentation and contract artifacts in mctl-agents, no runtime code:

1. `docs/spikes/1043-cross-namespace-dispatch.md` — decision memo.
2. `docs/spikes/1043/command.schema.json`, `docs/spikes/1043/result.schema.json` — bridge contracts (JSON Schema 2020-12).
3. `docs/spikes/1043/fixtures/*.json` — positive and negative examples.
4. `tests/test_spike_1043_contracts.py` — offline schema validation (uses `jsonschema` with a required import; missing dependency FAILS CI rather than silently skipping).

### Decision procedure

The memo answers every gate with `verified` / `assumed` / `not-observed` and pinned evidence, then applies this rule:

- `NEXUS_VERIFIED` only if N1-N5 are all `verified`, and N6-N7 have a documented plan.
- `API_BRIDGE_SELECTED` if any of N1-N5 fails or stays unverified, and the bridge gates B1-B4 are satisfiable on current versions.
- `BLOCKED_NEEDS_SDK_OR_SERVER_UPGRADE` if neither option is satisfiable without a server/SDK upgrade (name the exact version and verification steps).
- `DEFER` only if #324 runtime ownership or #2456 namespace authorization is withdrawn.

Nexus gates (all against server 1.31.0, chart 1.2.0, Python SDK 1.34.0 / nexus-rpc 1.4.0, mctl-api Go SDK at a pinned commit):

| Gate | Question | Expected evidence |
|---|---|---|
| N1 | Is Nexus available and enabled by default in OSS 1.31.0, or does it need dynamic config (`system.enableNexus`) and a frontend HTTP address? | Server release notes and `common/dynamicconfig` constants at tag v1.31.0; chart 1.2.0 values for the frontend HTTP port |
| N2 | Can a caller namespace be restricted per endpoint in OSS (an allowlist of `mctl-assistants` only), or is that Temporal Cloud only? | Server source for endpoint registry and the authorizer call on Nexus dispatch; Cloud vs OSS docs |
| N3 | Which identity and role can create/update endpoints, and is that operator API covered by the #2456 `temporal-system:admin` model? | `OperatorService` Nexus endpoint RPCs and their authorizer role |
| N4 | Does the provider worker need any permission on the control namespace to receive tasks and complete operations? (It must not.) | Worker poll RPC (`PollNexusTaskQueue`) and completion target namespace; callback delivery path |
| N5 | Does the default authorizer (#2456) evaluate Nexus dispatch against the target namespace with the caller's claims, so the provider identity cannot be used to call back into control? | Authorizer API list for Nexus HTTP and gRPC handlers |
| N6 | Cancellation, retries, timeouts and error propagation (`OperationError`, `HandlerError` retryable vs non-retryable; schedule-to-close) on both SDKs | SDK source at the pinned versions |
| N7 | Network and callback requirements: frontend HTTP port admitted by `networkpolicy.yaml`, `component.callbacks.allowedAddresses` | Chart and dynamic config docs |

Working hypothesis, to be confirmed or overturned by the memo: N1, N4 and N6 are likely satisfiable on 1.31.0 / 1.34.0, but N2 and N5 are likely not satisfiable with the stock OSS authorizer (endpoint caller allowlists are documented as a Cloud feature), and the frontend currently has no authentication at all. The expected outcome is therefore `API_BRIDGE_SELECTED`, with Nexus recorded as a later swap once a reviewed authorizer exists. The memo must not state this outcome without the evidence.

Bridge gates:

| Gate | Requirement |
|---|---|
| B1 | Provider worker reaches only mctl-api (bridge routes), never the control namespace; its Temporal identity (if it is a Temporal worker at all) carries only `mctl-assistants-provider-glovo:write` |
| B2 | Commands are issued only by the control workflow through mctl-api; mctl-api signs/binds them to an `execution_id` it created |
| B3 | Every command is idempotent by `command_id` and single-use for mutation by `aar_` consume |
| B4 | Results are accepted only from the worker identity the command was leased to, under the current lease token, before expiry |

### Bridge contract (selected-path sketch; schemas are the normative form)

Command (mctl-api -> provider, via lease):

- `schema_version` (`bridge.mctl.ai/v1alpha1`), `command_id` (`cmd_` + 26 chars, dedupe key), `execution_id` (`we_`), `work_item_id` (`wi_`), `kind` (enum: `quote`, `place_order_fake`, `cancel_order_fake`, `read_status`), `attempt` (int >= 1).
- `tenant_ref`, `principal_ref`, `order_ref`, `connection_ref`: opaque mctl-api handles (pattern `^(tnr|prr|ordr|gcn)_[A-Za-z0-9]{16,40}$`), never raw identifiers or secrets.
- `approval_ref` (`aar_`, required for mutation kinds), `intent_hash` (`sha256:<64 hex>`, as `orchestrator/action_approvals.intent_hash`).
- `issuer` (const `mctl-api`), `audience` (const provider worker identity, for example `provider:glovo`), `nonce` (128-bit, base64url), `issued_at`, `expires_at` (max TTL 15 min), `lease_token` (opaque, set on claim), `cancel_requested` (bool).
- `payload`: bounded object with per-kind `oneOf` schemas, `additionalProperties: false`, every string `maxLength`.

Result (provider -> mctl-api):

- `command_id`, `execution_id`, `lease_token`, `attempt`, `worker_identity`, `outcome` (enum: `succeeded`, `failed_retryable`, `failed_terminal`, `cancelled`, `approval_refused`), `provider_effect` (enum: `none`, `applied`, `unknown`), `result_ref` (opaque), `error_code` (enum, no free text over 256 chars), `completed_at`.

Authentication: the provider worker authenticates to mctl-api with its own short-lived workload token (Kubernetes SA projected token or Vault-issued JWT, `aud` pinned to mctl-api bridge), scoped to two routes only: `POST /api/v1/bridge/commands/claim` and `POST /api/v1/bridge/commands/{command_id}/result`. These route names are proposals for the later mctl-api issue, not existing routes.

### Call diagram

```
user/MCP facade --(OAuth, no Temporal creds)--> mctl-api
mctl-api --start/signal (control identity)--> [mctl-assistants] AssistantOrderWorkflow (mctl-agents-owned code)
AssistantOrderWorkflow --activity: create_bridge_command(execution_id, refs, aar_)--> mctl-api outbox (status=pending)
provider worker --claim (provider identity, lease)--> mctl-api  => command + lease_token
provider worker --consume aar_ (intent_hash)--> mctl-api  => granted | refused
provider worker --fake mutation (idempotency key = command_id)--> synthetic Glovo fake
provider worker --result (lease_token)--> mctl-api  => accepted | stale | duplicate
mctl-api --signal result (control identity)--> AssistantOrderWorkflow
```

The provider never holds a control-namespace credential; only mctl-api signals control.

### Failure, retry and cancellation matrix

| Case | Behaviour | Provider writes |
|---|---|---|
| Provider crash after claim, before consume | Lease lapses; reclaim under new lease token, same `command_id` | 0 then 1 |
| Crash after consume, before mutation | Reclaim; consume answers already-consumed for same `command_id`+`intent_hash`; mutation keyed by `command_id` | 1 |
| Crash after mutation, before result | Reclaim; fake keyed by `command_id` reports existing effect; result `provider_effect=applied` | 1 |
| Duplicate result post | mctl-api returns `duplicate`, no signal | 0 extra |
| Result with stale lease token | Refused `stale_lease` | 0 extra |
| Command expired (`expires_at` passed) | Claim refuses; control gets `expired` and decides | 0 |
| Stale or rejected approval | Consume refused; result `approval_refused` | 0 |
| Cancellation before claim | Outbox row cancelled; never claimable | 0 |
| Cancellation after claim | `cancel_requested=true` visible on heartbeat; before consume -> `cancelled`; after mutation -> compensating `cancel_order_fake` command | 1 + compensation |
| mctl-api unavailable | Provider backs off (exponential, cap 60 s, jitter); control activity retries create with same `command_id` | 0 extra |
| Control workflow retry of create activity | Same `command_id` (derived from workflow id + step) -> existing row returned | 0 extra |

### Denial tests (planned; executed in the later implementation issue)

- D1-D6: with the provider identity, `StartWorkflowExecution`, `SignalWorkflowExecution`, `QueryWorkflow`, `ListWorkflowExecutions`, `TerminateWorkflowExecution`, `DescribeWorkflowExecution` against `mctl-assistants` and `mctl-agents` are all denied (requires #2456 authorizer).
- D7: provider calls any mctl-api route other than claim/result -> 403.
- D8: result whose `tenant_ref`/`execution_id` differs from the leased command -> refused, no signal.
- D9: forged command (not issued by mctl-api, bad nonce or replayed nonce) -> provider refuses before consume.
- D10: duplicate callback -> zero additional provider writes (fake write counter unchanged).
- D11: stale approval (`aar_` expired or already consumed for another intent) -> zero provider writes.
- D12: MCP facade deployment has no Temporal address, token or CA mount (static gitops check).

### Ownership map

| Party | Owns | Must not hold |
|---|---|---|
| mctl-api | Only Temporal client for start/signal/query/list on `mctl-assistants`; user/tenant/principal/approval authority; bridge outbox, leases, nonce store, `aar_` consume | Provider session secrets |
| mctl-agents | Trusted control workflow code and worker on `mctl-assistants` | Provider credentials |
| Provider worker | Its namespace `mctl-assistants-provider-glovo` (if Temporal is used for its own retries), bridge claim/result | Any role on `mctl-assistants` or `mctl-agents`; mctl-api admin token |
| MCP facade | OAuth front door, delegates everything to mctl-api | Any Temporal credential |

### Migration, rollback and cost

- Migration: greenfield; nothing deployed uses either transport. Bridge first; if a later spike verifies N2/N5 (custom or upstream authorizer), the control activity `create_bridge_command` can be replaced by a Nexus operation behind the same command schema, so the provider handler logic is reused.
- Eventual handoff on retries: `command_id` is stable across control retries and lease reclaims, so a switch of transport mid-flight is not needed; in-flight commands drain on the old transport.
- Cost per workflow: one outbox row, about 3-5 mctl-api requests (claim, consume, result, signal) and one control activity; negligible next to Temporal history storage. No model cost.

## Alternatives

- **Temporal Nexus now.** Native cancellation, retries and callbacks, and the provider worker would never touch control. Dropped as the default because the memo's likely evidence (N2/N5) is that OSS 1.31.0 offers no caller-namespace allowlist per endpoint without a custom authorizer, the frontend is unauthenticated today, and the Nexus HTTP port and callback config are not declared. Kept as the future swap.
- **One namespace, two task queues.** Rejected by ADR 0010 and #2456: the default authorizer has no task-queue dimension, so a provider writer could start or terminate control workflows.
- **Provider worker with a write role on the control namespace (plain Activities).** Rejected: grants exactly the authority the issue forbids.
- **Direct provider -> control signal with a scoped token.** Rejected: no stock Temporal role allows "signal one workflow only".

## Platform impact

- No runtime, migration or resource impact: documentation, JSON Schemas and one offline test are added. No namespace, endpoint, secret or permission change.
- Backward compatibility: none affected; nothing existing reads the new files.
- Risk: the memo concludes from documentation instead of observed behaviour. Mitigation: every claim is labelled `verified`/`assumed`/`not-observed`; any `assumed` Nexus gate forces the non-Nexus outcome.
- Risk: bridge schemas get treated as an approved API. Mitigation: memo states they are `v1alpha1` proposals, and implementation needs its own approved DevLoop proposal in mctl-api and mctl-agents.
- Dependency: denial tests D1-D6 require mctl-gitops#2456 enforcement; the memo states that M1 activation is held until then, whichever transport is chosen.
