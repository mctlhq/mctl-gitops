# Design: issue-1044-feat-assistants-m1-trusted-glovo-control

## Current state

mctl-agents (this clone, HEAD `883b3a1`):

- The only Temporal runtime is the DevLoop control plane in
  `orchestrator/temporal/`. `worker.py` connects with
  `Client.connect(address, namespace=namespace, runtime=runtime)` where
  `namespace = os.environ.get("TEMPORAL_NAMESPACE", "mctl-agents")` (line ~850),
  with no credential and no TLS. It selects queues by `--role
  all|control|execution|implementation` (`ROLES`, `worker_plans()`), creates
  schedules (`owns_schedules`) and runs the execution-request dispatcher
  (`start_dispatcher`). Queues are `mctl-dev-loop`, `mctl-dev-loop-exec`,
  `mctl-dev-loop-implement` (`orchestrator/temporal/constants.py`). Slot limits
  are explicit constants (`CONTROL_MAX_CONCURRENT_ACTIVITIES = 100`,
  `EXECUTION_MAX_CONCURRENT_ACTIVITIES = 40`), per ADR-008
  (`docs/adr/008-worker-queue-split-and-capacity.md`).
- Approval waiting: `orchestrator/temporal/workflows/action_approval.py`
  (`ActionApprovalWaitWorkflow`, `run_gated_action`, child id
  `action-approval-aar_X`, signal `action_approval_decided` with the `aar_` id,
  durable poll timer bounded by receipt expiry, outcomes
  `ran|consumed|denied|expired|mismatch|refused|blocked|effect_failed`).
  Temporal state never authorizes; the gated activity redeems the receipt.
- `orchestrator/action_approvals.py`: `ActionIntent`, `intent_hash()` (mirrors
  mctl-api `workitems.IntentHash`), `idempotency_key()`, and
  `ActionApprovalClient` (`create/get/consume/execute`). Pure helpers are
  reusable; the client uses the DevLoop admin identity.
- `orchestrator/temporal/mctl_client.py`: worker calls to mctl-api use the
  static `MCTL_TOKEN` admin service identity. The assistants worker must not
  reuse it.
- `orchestrator/temporal/dispatcher.py`: precedent for a lease/CAS,
  idempotent mctl-api-to-Temporal delivery.
- Tests: `tests/temporal_harness.py` (drop-in `Worker` polling every queue,
  teardown eviction), `WorkflowEnvironment.start_time_skipping()` in e.g.
  `tests/test_action_approval_wait.py`, `start_local()` in
  `tests/test_b4_update_outage_e2e.py`, replay tests in
  `tests/test_workflow_replay.py`, and an import-graph subprocess check in
  `tests/test_worker_isolation.py` (`FORBIDDEN_IN_WORKER`).
- Build/release: one `Dockerfile` (python:3.12-slim + Node 22, gh, gcc, Go)
  for every role; `pr-validation.yml` job `docker-build` (smoke build + run
  checks); `release-please.yml` dispatches mctl-gitops `release-deploy.yaml`
  with `image_name=ghcr.io/mctlhq/mctl-agents` and an explicit `values_path`
  list of the three admins worker deployments.
- `temporalio==1.34.0` (pyproject.toml), which pulls `nexus-rpc==1.4.0`
  (uv.lock). Nothing uses Nexus.
- Nothing named assistants, Glovo or `mctl-assistants` exists in the repo.

Related proposals (read from the gitops checkout):

- mctl-agents#1043 (`agents-state/mctl-agents/proposals/issue-1043-spike-assistants-verify-cross-namespace/`):
  status `proposed`. Plans Nexus gates N1-N7 and bridge gates B1-B4; working
  hypothesis `API_BRIDGE_SELECTED` (mctl-api command outbox with lease,
  `command_id`, `aar_` consume, result post; mctl-api is the only party that
  signals control). Its schemas are `v1alpha1` proposals, not approved APIs.
- mctl-api#953 (status `proposed`): `gcn_` connection registry, install
  revision, facade/worker route gates (`/api/v1/glovo/facade/*`,
  `/api/v1/glovo/worker/*`), fail-closed refusals.
- mctl-api#954 (status `proposed`): owner-scoped order index, immutable basket
  snapshots, `ConnectionAuthority` checkpoints, `Boundary.Dispatch/Report/ReadBack`
  with `ReserveActionApproval` single-use fence, `hir_` has no route in.
- mctl-gitops#2456 (status `merged`, ADR-only): JWT claim mapper + default
  authorizer by namespace role; no task-queue dimension; tasks 3-10 are future
  issues, enforcement is not live.

Deployed state checked:

- `mctl_list_services team=admins`: complete=true; `mctl-agents-worker`,
  `mctl-agents-worker-exec`, `mctl-agents-worker-implement` Synced on
  `ghcr.io/mctlhq/mctl-agents:1.117.0`. No assistants service exists.
- `$MCTL_GITOPS_ROOT/services/admins/`: contains `mctl-agents-worker`,
  `-exec`, `-implement`; no assistants control worker.
- `grep -rl "mctl-assistants"` over `$MCTL_GITOPS_ROOT`: matches only proposal
  documents under `agents-state/`; no service, tenant or namespace job declares
  it.
- Not observed: the live Temporal server namespaces, dynamic config and
  authorizer state (no read access through the mctl tools). Recorded as a gap,
  not as absent.

## Proposed solution

### 1. A separate package, not a new DevLoop role

New package `orchestrator/assistants/` with no import of
`orchestrator.temporal.workflows`, `orchestrator.temporal.worker`,
`orchestrator.temporal.mctl_client`, `orchestrator.auth` or
`claude_agent_sdk`. Allowed imports: `temporalio`, stdlib, and the pure
helpers `orchestrator.action_approvals.ActionIntent/intent_hash` (verified
side-effect free in the isolation test). Adding a fifth `--role` to
`orchestrator/temporal/worker.py` was rejected because that module owns
schedules, the dispatcher and the DevLoop namespace default; the issue requires
DevLoop to stay unchanged.

Files:

- `orchestrator/assistants/contracts.py` — frozen dataclasses with explicit
  validators: `GlovoControlInput` (`schema_version`, `tenant_ref`,
  `principal_ref`, `install_ref`, `install_revision`, `connection_ref` (`gcn_`),
  `order_ref`, `execution_id` (`we_`), `work_item_id` (`wi_`), `limits`),
  `GlovoControlResult` (`schema_version`, `order_status` enum
  `completed|refused|cancelled|expired|unknown|failed`, `reason_code` enum,
  `handoff_ref` opaque, `approval_ref`, `fingerprint`, `command_id`), plus
  activity I/O types. Refs use the opaque-handle patterns from #1043
  (`^(tnr|prr|ordr|gcn|ins)_[A-Za-z0-9]{16,40}$`), lengths <= 64, no free text
  > 256. `SCHEMA_VERSION = "assistants.mctl.ai/glovo-control/v1alpha1"`.
- `orchestrator/assistants/schemas/glovo-control-{input,result}.v1alpha1.json`
  plus `SHA256SUMS` — generated by `tools/assistants_schema.py`; a test
  regenerates and compares (source-pinned contract).
- `orchestrator/assistants/ids.py` — `control_workflow_id(tenant_ref,
  principal_ref, install_ref, order_ref)` ->
  `asst-glovo-<t>-<p>-<i>-<o>`; `command_id(workflow_id, step, attempt)` ->
  `cmd_` + base32(sha256)[:26]. mctl-api is the only caller that starts the
  workflow; the workflow re-derives and compares its own id as defense in depth.
- `orchestrator/assistants/workflow.py` — `GlovoControlWorkflow`.
- `orchestrator/assistants/activities.py` — activities over two ports.
- `orchestrator/assistants/ports.py` — `ControlApiPort` (mctl-api) and
  `ProviderBridgePort` (transport) Protocols.
- `orchestrator/assistants/api_client.py` — HTTP `ControlApiPort` using
  `MCTL_ASSISTANTS_TOKEN` (distinct from `MCTL_TOKEN`), base URL from env,
  no redirects (same pattern as `action_approvals._no_redirect_opener`).
  Route paths are constants mirroring #953/#954 proposals and gated by
  `ASSISTANTS_API_CONTRACT` pin; until those mctl-api routes are merged the
  client is exercised only against a fake.
- `orchestrator/assistants/bridge.py` — `ProviderBridgePort` with
  `create_command`, `read_result`, `request_cancel`; `load_bridge()` reads
  `orchestrator/assistants/bridge_decision.json`. The committed file says
  `{"decision": "BLOCKED_FOR_INTEGRATION", "source": null}`; `load_bridge()`
  raises `BridgeBlocked` for any real transport in that state. An
  `ApiCommandBridge` (mctl-api outbox per #1043 B1-B4) may be added only in a
  follow-up PR that changes the decision file to a verified `API_BRIDGE_SELECTED`
  or `NEXUS_VERIFIED` record with memo path, commit sha and approver. No raw
  cross-namespace Activity and no Nexus endpoint is implemented here.
- `orchestrator/assistants/worker.py` — standalone entrypoint
  `python -m orchestrator.assistants.worker`.
- `Dockerfile.assistants-control` — python:3.12-slim pinned by digest,
  `uv sync --locked --no-dev`, copies only `orchestrator/__init__.py`,
  `orchestrator/action_approvals.py` (and its pure deps, determined by the
  isolation test), `orchestrator/assistants/`; non-root uid; no Node, gh, Go,
  git. Entrypoint is the assistants worker.

### 2. Workflow

```
mctl-api --start(id derived from server scope, GlovoControlInput)--> [mctl-assistants / mctl-assistants-control]
GlovoControlWorkflow
  check schema_version, re-derive workflow id
  resolving:  revalidate_scope -> resolve_connection(gcn_, owner)       (ControlApiPort)
  quoting:    revalidate_scope -> quote_fake_basket -> bind fingerprint+consent_ref (immutable)
  awaiting_approval: revalidate_scope -> request_order_approval -> aar_
              wait signal assistants_approval_decided(aar_) | poll timer (read_approval)
              every revalidate_interval_s: revalidate_scope; bounded by aar_ expiry
  dispatching: revalidate_scope -> bridge.create_command(command_id, aar_, intent_hash, fingerprint)
              (mctl-api performs Reserve/consume at its boundary, #954 step 4)
  settling:   wait signal assistants_provider_result(command_id) | poll read_result
              accept only matching command_id/execution_id/fingerprint; duplicates are no-ops
  completed:  return GlovoControlResult(order_status, handoff_ref)
```

Rules:

- Temporal state never authorizes. Each step that mutates calls mctl-api, which
  re-runs its own checkpoints (#954 `CheckpointSideEffect`). The workflow only
  decides whether to ask.
- `hir_` is not a field of any input type; a test asserts the dataclass
  rejects it.
- Fingerprint and `consent_ref` are set once in workflow state; any later
  mismatch ends in `refused/fingerprint_mismatch`. A retry with a different
  basket requires a new execution (`we_`) and a new `aar_`, matching #954.
- `revalidate_scope` answers `live|revoked|stale_install|not_member|
  tenant_cap_reached`. An activity failure after bounded retries is treated as
  not live; the workflow never proceeds on an unknown answer.
- Cancellation: a `CancelledError` handler runs in a
  `workflow.shield`-equivalent (non-cancellable) scope only
  `bridge.request_cancel(command_id)` if a command exists and
  `release_reservation`. It never calls resolve/activate/approve and never
  reopens a revoked connection.
- Provider `unknown` -> no re-dispatch; result `order_status=unknown`.
- Signals carry ids only (`aar_`, `command_id`), never payloads, so no provider
  data or token enters history. Activities return ids, enums and bounded refs.
- Bounded wait: workflow `execution_timeout` (default 2 h), approval wait capped
  by `aar_` expiry, settle wait capped at `settle_timeout_s` (default 15 min,
  the #1043 command TTL).

### 3. Worker

`orchestrator/assistants/worker.py`:

- Constants `ASSISTANTS_NAMESPACE = "mctl-assistants"`,
  `ASSISTANTS_TASK_QUEUE = "mctl-assistants-control"`.
- `main()` reads `TEMPORAL_NAMESPACE` with no default and refuses
  (`SystemExit`) unless it equals `ASSISTANTS_NAMESPACE`; refuses
  `MCTL_TOKEN` being set (wrong identity) and any provider credential env
  (`GLOVO_*`, `PROVIDER_*`). Temporal auth is passed through only as
  `TEMPORAL_API_KEY`/TLS paths when present; credentials are a #2457 concern.
- Registers exactly `GlovoControlWorkflow` and the assistants activities.
  No schedules, no dispatcher.
- Explicit limits from bounded env: `ASSISTANTS_MAX_CONCURRENT_ACTIVITIES`
  (default 20, range 1-100), `ASSISTANTS_MAX_CONCURRENT_WORKFLOW_TASKS`
  (default 20), activity start-to-close <= 30 s, schedule-to-close <= 5 min.
- At startup logs the bridge decision; if `ASSISTANTS_BRIDGE=real` while the
  decision file is blocked, exits with status `BLOCKED_FOR_INTEGRATION`.
- Noisy-tenant caps are enforced by mctl-api admission (it is the only
  starter); the worker's slot limits cap total parallelism.

### 4. Test harness

`tests/assistants_harness.py`: starts `WorkflowEnvironment.start_local()`
(disposable dev server) with namespaces `mctl-assistants` and a decoy
`mctl-agents`, a fake `ControlApiPort` holding two tenants and two principals
in one tenant, and an in-memory `LocalFakeBridge` (test-only, in `tests/`)
with a write counter keyed by `command_id`. Time-skipping env is used for
timers/revalidation.

### 5. CI

- `pr-validation.yml`: new job `assistants-control-build` builds
  `Dockerfile.assistants-control`, runs the import-graph check inside the image,
  checks non-root uid, and verifies the worker refuses `TEMPORAL_NAMESPACE=mctl-agents`.
- The existing `docker-build` job and `release-please.yml` `values_path` are
  not changed. Image publishing is not added in this proposal (see Open
  questions); when approved it uses a distinct image name and is never added to
  release-deploy `values_path`.

## Alternatives

- **Add an `assistants` role to `orchestrator/temporal/worker.py`.** Reuses
  plumbing, but shares the module that defaults to namespace `mctl-agents`,
  owns schedules and the dispatcher, and ships in the image the DevLoop
  deployments run. Rejected: violates "DevLoop unchanged" and widens blast
  radius.
- **Reuse `ActionApprovalWaitWorkflow` as a child.** Semantics fit, but it
  calls the DevLoop policy-checkpoint gated activities and its registration
  would pull DevLoop workflow modules into the assistants worker. Rejected;
  the control workflow reimplements the bounded signal+poll wait and reuses
  only the pure `intent_hash`.
- **Wire a Nexus operation or a cross-namespace Activity now.** Rejected by
  the issue and by #1043: Nexus gates N2/N5 are unverified on OSS 1.31.0 and a
  raw cross-namespace Activity would require the provider to hold control
  authority. The bridge port allows either transport later.
- **Expose Temporal to the facade/provider, per-user namespaces, queue-only
  isolation, a second scheduler.** Rejected in the issue and by #2456 (no
  task-queue authorization dimension).

## Platform impact

- Migrations: none. New code, new Dockerfile, new CI job. No namespace,
  service, secret, schedule or gitops change; nothing is deployed.
- Backward compatibility: existing DevLoop modules, queues, image and release
  dispatch are untouched; a test asserts `orchestrator/temporal/` does not
  import `orchestrator.assistants` and vice versa.
- Resource impact: CI only (one extra image build, a few minutes). Runtime cost
  is zero until #2457 activates a deployment.
- Risks and mitigations:
  - Contracts drift from mctl-api#953/#954 or #1043, which are unmerged.
    Mitigation: ports plus `v1alpha1` schema pin; integration stays
    `BLOCKED_FOR_INTEGRATION` until those land.
  - Local tests overstate isolation (dev server has no authorizer). Mitigation:
    tests are labelled structural; the live denial matrix (#1043 D1-D6) is a
    precondition of #2457 activation.
  - Someone deploys the image early. Mitigation: no publish step, worker refuses
    a wrong namespace and a DevLoop token, real bridge refuses to load.
  - Workflow determinism: new workflow type with no history; replay tests are
    added from the first commit, and later changes use `workflow.patched()`.
