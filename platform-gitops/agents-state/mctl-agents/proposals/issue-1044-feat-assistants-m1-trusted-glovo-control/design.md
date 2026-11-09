# Design: issue-1044-feat-assistants-m1-trusted-glovo-control

## Amendment 2026-11-09

Resolves the crosswalk mismatches assigned to this slice (M6-M10 in mctl-gitops
`deploy/staged/glovo-m1/CROSSWALK.md`, PR #2545), the re-review request on mctl-agents#1044
(comment 6740430920) and the #1258 carry-overs (comment 6740200693). Sources re-read at
mctl-api `a9ca5814` (merged bridge #968, `docs/bridge.md`, `internal/bridge/schema/`) and
mctl-gitops `4f2d2d76`. Rows marked **(owner)** record owner decisions of 2026-11-09. The
owner decided on 2026-11-09 that #968 is the canonical bridge; the transport question of
mctl-agents#1043 is closed by that decision. Where this section and older text below
disagree, this section wins; the passages it contradicts have been edited.

| # | Finding | Change |
|---|---|---|
| M6 | The workflow waited for `assistants_provider_result(command_id)`; mctl-api sends `bridge-result` with `{command_id, result_digest}` to the stored workflow and run, at least once (`docs/bridge.md` "Signals") | The signal is `bridge-result`, payload `{command_id, result_digest}`. The workflow dedupes on `command_id`, ignores a `command_id` it did not receive from mctl-api, and then reads the result back through `ControlApiPort.read_command_result(command_id)`, accepting it only if the digest equals the signalled `result_digest`. The signal is a wake-up, never the result |
| M6b | Found during this amendment: the workflow also waited for `assistants_approval_decided`, which no mctl-api component sends (the dispatcher sends only `bridge-result`) | The approval wait is poll-only: `read_approval` every `approval_poll_interval_s` (default 15, bounded 5-60), capped by the `aar_` expiry. No approval signal is registered |
| M7 | `ProviderBridgePort.create_command` assumed an HTTP enqueue route; #968 has only in-process `Store.Enqueue(ctx, tx, …)` | **(owner, option b)** The workflow orchestrates only through mctl-api APIs. `ProviderBridgePort`, `bridge.py` and `bridge_decision.json` are removed. Dispatch and cancel are `ControlApiPort.dispatch_order(order_ref, approval_ref, fingerprint)` and `cancel_order(order_ref)`; mctl-api performs the order transition, the `aar_` reserve and `Enqueue` in one transaction (mctl-api#957 design §6a). The HTTP route behind them is not decided (mctl-api#957 OPEN-3); until it is merged and pinned, the client is exercised against a fake only and a real `ControlApiPort` refuses to construct (`BLOCKED_FOR_INTEGRATION`) |
| M8 | `command_id` derived client-side (`cmd_` + base32(sha256)[:26]); #968 generates `cmd_` server-side and dedupes on `(tenant, execution_id, operation_key)` (`internal/bridge/store.go:478-536`) | **(owner)** `ids.command_id` is removed. `dispatch_order` returns the server's `cmd_`, which the workflow stores. An activity retry calls `dispatch_order` again and gets the same `cmd_` back (`created=false`). The operation key is built by mctl-api, not by the workflow |
| M9 | `order_status` vs the bridge's `outcome` × `provider_effect` × `error_code`; `unknown` after a reclaim must survive | "Result mapping (M9)": one total mapping table over the frozen v1alpha1 enums. `provider_effect=unknown` maps to `unknown` in every row, is never `completed` and never re-dispatched. The fake provider reports reclaim-after-permit and `permit_already_issued` as `failed_terminal`/`internal`/`unknown` (mctl-telegram#1262 design, owner decision), which the table maps to `unknown` |
| M10 | Approval binding and refusal reasons (#1258 carry-overs) | The `aar_` is created once, by mctl-api at prepare (mctl-api#957 §6, bound to execution, Target and basket fingerprint). `GlovoControlInput` gains `approval_ref` and `fingerprint`; the `quoting` state and `request_order_approval` are removed, so the workflow never creates a second approval. Dispatch passes the input fingerprint; mctl-api compares it with the `aar_` intent, and a difference ends as `refused`/`basket_changed`, which needs a new `we_` and a new `aar_`. Refusal reasons are distinct: `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `provider_disabled`, `tenant_busy`. `hir_` stays non-authorizing |
| M1 (consumer side) | Ref families | `tnr_`, `prr_`, `ordr_` come from mctl-api's mapping (mctl-api#957 §2a); `connection_ref` is the M1a `gcn_` id and `install_ref` the M1a `gin_` id, both passed through unchanged. The `ins_` prefix is dropped |

### Open items

- **Workflow start.** mctl-api starts `GlovoControlWorkflow` (crosswalk §4). When and in
  which slice is mctl-api#957 OPEN-5; the input contract here does not depend on it.
- **Control route ownership.** mctl-api#957 OPEN-3. No HTTP route constants for dispatch
  or cancel are frozen before it is decided.

### Result mapping (M9)

Applies to the command the workflow dispatched (`place_order_fake`) or cancelled
(`cancel_order_fake`). Rows are evaluated top to bottom; the first match wins.

| `outcome` | `provider_effect` | `error_code` | `order_status` | `reason_code` |
|---|---|---|---|---|
| any | `unknown` | any | `unknown` | `provider_effect_unknown` |
| `succeeded` | `applied` | `none` | `completed` (`place_order_fake`) / `cancelled` (`cancel_order_fake`) | `none` |
| `succeeded` | `none` | any | `unknown` | `result_inconsistent` |
| `failed_retryable`, `failed_terminal`, `cancelled`, `approval_refused` | `applied` | any | `unknown` | `result_inconsistent` |
| `approval_refused` | `none` | any | `refused` | `approval_refused` |
| `cancelled` | `none` | any | `cancelled` | `cancel_requested` |
| `failed_terminal` | `none` | `expired` | `expired` | `command_expired` |
| `failed_terminal` | `none` | `provider_rejected` | `failed` | `provider_rejected` |
| `failed_terminal` | `none` | `none`, `stale_lease`, `approval_refused`, `provider_unavailable`, `internal` | `failed` | the `error_code` (`none` becomes `internal`) |
| `failed_retryable` | `none` | any | `failed` | the `error_code` (`none` becomes `provider_unavailable`) |

- M1 never re-dispatches. A retry after `failed` is a new execution with a new `aar_`.
- Settle timeout (`settle_timeout_s`, no accepted result): `cancel_order(order_ref)`, then
  `read_command_result`. A terminal `expired` or `cancelled` command with effect `none`
  maps by the table; anything else, including a read failure, is `unknown`/`settle_timeout`.
- A test enumerates every (`outcome`, `provider_effect`, `error_code`) triple of the
  vendored enums (5 × 3 × 7 = 105) and asserts exactly one row matches and that no triple
  with `provider_effect=unknown` yields anything but `unknown`.

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
  `principal_ref`, `install_ref` (`gin_`), `install_revision`, `connection_ref` (`gcn_`),
  `order_ref`, `execution_id` (`we_`), `work_item_id` (`wi_`), `approval_ref` (`aar_`),
  `fingerprint`, `limits`; amended 2026-11-09),
  `GlovoControlResult` (`schema_version`, `order_status` enum
  `completed|refused|cancelled|expired|unknown|failed`, `reason_code` enum,
  `handoff_ref` opaque, `approval_ref`, `fingerprint`, `command_id`), plus
  activity I/O types. Refs use the opaque-handle patterns from #1043
  (`^(tnr|prr|ordr|gcn|gin)_[A-Za-z0-9]{16,40}$`, amended 2026-11-09), lengths <= 64, no free text
  > 256. `SCHEMA_VERSION = "assistants.mctl.ai/glovo-control/v1alpha1"`.
- `orchestrator/assistants/schemas/glovo-control-{input,result}.v1alpha1.json`
  plus `SHA256SUMS` — generated by `tools/assistants_schema.py`; a test
  regenerates and compares (source-pinned contract).
- `orchestrator/assistants/ids.py` — `control_workflow_id(tenant_ref,
  principal_ref, install_ref, order_ref)` ->
  `asst-glovo-<t>-<p>-<i>-<o>`. There is no client-side `command_id` (amended
  2026-11-09, M8): `cmd_` ids come from mctl-api. mctl-api is the only caller that
  starts the workflow; the workflow re-derives and compares its own id as defense in depth.
- `orchestrator/assistants/workflow.py` — `GlovoControlWorkflow`.
- `orchestrator/assistants/activities.py` — activities over two ports.
- `orchestrator/assistants/ports.py` — `ControlApiPort` (mctl-api) only. Amended
  2026-11-09 (M7): it carries `dispatch_order`, `cancel_order` and
  `read_command_result`; there is no `ProviderBridgePort`.
- `orchestrator/assistants/api_client.py` — HTTP `ControlApiPort` using
  `MCTL_ASSISTANTS_TOKEN` (distinct from `MCTL_TOKEN`), base URL from env,
  no redirects (same pattern as `action_approvals._no_redirect_opener`).
  Route paths are constants mirroring #953/#954 proposals and gated by
  `ASSISTANTS_API_CONTRACT` pin; until those mctl-api routes are merged the
  client is exercised only against a fake.
- ~~`orchestrator/assistants/bridge.py`~~ — removed by the 2026-11-09 amendment (M7).
  The bridge is mctl-api#968 and the workflow reaches it only through mctl-api APIs.
  The integration gate moves to `api_client.py`: a real `ControlApiPort` refuses to
  construct (`BLOCKED_FOR_INTEGRATION`) until `ASSISTANTS_API_CONTRACT` pins a merged
  mctl-api control route contract (mctl-api#957 OPEN-3). No raw cross-namespace
  Activity and no Nexus endpoint is implemented here.
- `orchestrator/assistants/worker.py` — standalone entrypoint
  `python -m orchestrator.assistants.worker`.
- `Dockerfile.assistants-control` — python:3.12-slim pinned by digest,
  `uv sync --locked --no-dev`, copies only `orchestrator/__init__.py`,
  `orchestrator/action_approvals.py` (and its pure deps, determined by the
  isolation test), `orchestrator/assistants/`; non-root uid; no Node, gh, Go,
  git. Entrypoint is the assistants worker.

### 2. Workflow

```
mctl-api --start(id derived from server scope, GlovoControlInput incl. aar_ + fingerprint)--> [mctl-assistants / mctl-assistants-control]
GlovoControlWorkflow   (amended 2026-11-09)
  check schema_version, re-derive workflow id
  resolving:  revalidate_scope -> resolve_connection(gcn_, owner)       (ControlApiPort)
  awaiting_approval: poll read_approval(aar_) every approval_poll_interval_s
              every revalidate_interval_s: revalidate_scope; bounded by aar_ expiry
  dispatching: revalidate_scope -> dispatch_order(order_ref, aar_, fingerprint) -> cmd_
              (mctl-api: order transition + aar_ reserve + bridge Enqueue in one tx)
  settling:   wait signal bridge-result{command_id, result_digest} | poll read_command_result
              accept only the stored cmd_ and a matching digest; duplicates are no-ops
  completed:  return GlovoControlResult(order_status, reason_code, handoff_ref)  (map: "Result mapping (M9)")
```

Rules:

- Temporal state never authorizes. Each step that mutates calls mctl-api, which
  re-runs its own checkpoints (#954 `CheckpointSideEffect`). The workflow only
  decides whether to ask.
- `hir_` is not a field of any input type; a test asserts the dataclass
  rejects it.
- Fingerprint and `approval_ref` arrive in the input and never change; mctl-api
  compares them with the `aar_` intent at dispatch and a mismatch ends in
  `refused/basket_changed` (amended 2026-11-09, M10). A retry with a different
  basket requires a new execution (`we_`) and a new `aar_`, matching #954.
- `revalidate_scope` answers `live|revoked|stale_install|not_member|
  tenant_cap_reached`. An activity failure after bounded retries is treated as
  not live; the workflow never proceeds on an unknown answer.
- Cancellation: a `CancelledError` handler runs in a
  `workflow.shield`-equivalent (non-cancellable) scope only
  `cancel_order(order_ref)` if a command exists and
  `release_reservation`. It never calls resolve/activate/approve and never
  reopens a revoked connection.
- Provider `unknown` -> no re-dispatch; result `order_status=unknown`. The full
  mapping is "Result mapping (M9)".
- The only signal is `bridge-result` (`command_id`, `result_digest`), never a payload, so no provider
  data or token enters history. Activities return ids, enums and bounded refs.
- Bounded wait: workflow `execution_timeout` (default 2 h), approval wait capped
  by `aar_` expiry, settle wait capped at `settle_timeout_s` (default 15 min, the
  bridge `MaxTTL` of 900 s in the vendored command schema).

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
- At startup logs the `ASSISTANTS_API_CONTRACT` pin; if `ASSISTANTS_API=real` while
  no merged control route contract is pinned, exits with status
  `BLOCKED_FOR_INTEGRATION` (amended 2026-11-09).
- Noisy-tenant caps are enforced by mctl-api admission (it is the only
  starter); the worker's slot limits cap total parallelism.

### 4. Test harness

`tests/assistants_harness.py`: starts `WorkflowEnvironment.start_local()`
(disposable dev server) with namespaces `mctl-assistants` and a decoy
`mctl-agents`, a fake `ControlApiPort` holding two tenants and two principals
in one tenant; the fake's `dispatch_order` mints server-style `cmd_` ids, keeps a
write counter per `cmd_` and can emit `bridge-result` signals with digests (amended
2026-11-09; there is no `LocalFakeBridge`). Time-skipping env is used for
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
