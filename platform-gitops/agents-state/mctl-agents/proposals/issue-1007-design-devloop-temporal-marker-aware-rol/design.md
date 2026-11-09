# Design: issue-1007-design-devloop-temporal-marker-aware-rol

## Current state

Code (clone of mctlhq/mctl-agents at 55b4633, release line 1.117.0 per
`.release-please-manifest.json`):

- `orchestrator/temporal/workflows/dev_loop.py`:
  - `DEFERRED_RESUME_PATCH = "deferred-resume-contract"` (line ~432) is evaluated once in
    `run`: `self._deferred_resume_contract = workflow.patched(DEFERRED_RESUME_PATCH)`, just
    before `self._gates_passed = True` and `_implement(...)` (line ~4419).
  - The flag is carried across continue-as-new in `MergeWatchResume.deferred_resume_contract`,
    so hopped runs record no marker of their own.
  - The workflows package holds 15 `*_PATCH = "..."` constants and 57 `workflow.patched(`
    calls, so the hazard is general, not M1-specific.
- `orchestrator/temporal/worker.py`: `worker_plans(role, ...)` builds one `WorkerPlan` per
  queue (`TASK_QUEUE`, `EXECUTION_TASK_QUEUE`, `IMPLEMENTATION_TASK_QUEUE` from
  `orchestrator/temporal/constants.py`). `_build_worker` constructs `Worker(client,
  task_queue=..., workflows=..., activities=..., **kwargs)` with **no `deployment_config`**, so
  all queues are unversioned. `pyproject.toml` pins `temporalio==1.34.0`, which ships
  `WorkerDeploymentConfig` / `WorkerDeploymentVersion`.
- `orchestrator/temporal/start.py` starts DevLoop workflows with `task_queue=TASK_QUEUE`. It
  sets no execution or run timeout.
- `tools/temporal_marker_scan.py` (MS-4): a read-only three-state scanner (MARKER_PRESENT /
  MARKER_ABSENT / UNKNOWN) for one `--patch-id`, with a continue-as-new chain walk,
  `retention_gap`, and listing completeness. Exit codes are 0/2/3. `render_json` emits
  `scanner_version, patch, listing_complete, query, namespace, counts, unknown_reasons,
  workflows` but **no scan timestamp**. `DEFAULT_QUERY = 'WorkflowType = "DevLoopWorkflow" AND
  ExecutionStatus = "Running"'`.
- `tools/temporal_nondeterminism_scan.py`: a TMPRL1100 detector over histories and metrics
  scrapes.
- `tests/test_pre_m1_compat.py` and `tools/record_pre_m1_histories.py`: pre-M1 fixtures in
  `tests/fixtures/histories/pre_m1/` replay under M1.
- `tests/test_b4_update_outage_e2e.py` and `tests/test_patch_memoization.py`: real-dev-server
  tests via `WorkflowEnvironment.start_local(...)` that skip loudly when no server can start.
  This is the pattern the new experiment follows.
- `docs/runbooks/worker-rollout-forward-only.md`: the draft runbook, with evidence labels
  CODE/LOCAL/KIND/PROD/LIVE/UNVERIFIED. It already states the forward-only rules and the
  LOCAL versioning findings in prose. Two gaps:
  - Step 4 of "Failed new worker" (the fixed worker also does not start) is explicitly
    **UNVERIFIED as a scenario**.
  - The versioning findings have no committed, reproducible harness or matrix, and the
    runbook still says "Worker Versioning ... separate design, not started by decision". That
    contradicts the 2026-11-04 owner decision (A is the target, to be verified).
- There is no tool that, given a rollback target, checks whether that target can replay the
  markers live histories have recorded. The only floor is the static `min_tag`.

Deployed state checked:
- `mctl_get_service_status(admins, mctl-agents-worker)`: ArgoCD Healthy/Synced, imageTag
  `1.117.0`, so no M1 build is deployed. This is consistent with the issue's "no production
  image contains M1".
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  - image `ghcr.io/mctlhq/mctl-agents:1.117.0`;
  - `TEMPORAL_NAMESPACE: mctl-agents`;
  - `EXECUTION_REQUEST_DISPATCHER: "true"`;
  - no `strategy` key (Recreate not applied).
- `services/admins/mctl-agents-worker-exec/values.yaml`: tag `1.117.0`.
- `services/admins/mctl-agents-worker-implement/values.yaml`: tag `1.117.0`, `strategy: type:
  Recreate`.
- `platform-gitops/release-gates.yaml`, group `mctl-agents-workers`: the three paths above,
  `min_tag: "1.117.0"`, `repository: ghcr.io/mctlhq/mctl-agents`, no `requires` yet.
- No worker values file sets any build id or deployment name. A grep for worker-deployment
  dynamic config keys under `platform-gitops/` found only unrelated proposal text, so the
  Temporal server dynamic config is not observable from these sources. That is
  **not observed**, not "disabled".
- Not checked: the live Temporal task queue, pollers and running workflows. Production
  Temporal access is out of scope by owner decision, and the MCP tools here do not expose it.
  The issue's 23-run MS-1 result and the runbook's 25-run result of 2026-11-06 are
  point-in-time and stale.

## Proposed solution

Four deliverables. Production code paths stay unchanged.

### 1. ADR 026: worker rollback boundary

New file: `docs/adr/026-worker-rollback-boundary.md`. It records the owner decision. It
defines:

- **Marker-bearing history**: a run, or any `continued_from` ancestor of a run, that records a
  `core_patch` marker with id X.
- **Compatible build for a fleet**: a build whose `orchestrator/temporal/workflows/` calls
  `workflow.patched(X)` for every X recorded by a running history.
- **Rollback boundary**: the lowest build compatible with the fleet at decision time. Under C
  the boundary only moves up. Under A it is per-workflow (the pinned version). B keeps the
  boundary at pre-M1 until the first marker is written.

The ADR states that the M1 release itself serves as the "M1-compatible hold" build. No
separate hold image is built. It also states what C cannot do: a defect in the M1 replay path
cannot be reverted below M1.

### 2. Marker-aware rollback check

New file: `tools/rollback_compat_check.py`. It is stdlib-only and offline, in the same style as
`temporal_marker_scan.py`.

- `patch_ids(tree: Path) -> PatchSet` walks `orchestrator/temporal/workflows/**/*.py` with
  `ast`:
  - It collects module-level `NAME = "literal"` assignments.
  - For each `workflow.patched(arg)` and `workflow.deprecate_patch(arg)` call, it resolves
    `arg` (a literal, a local constant, or a constant imported from a sibling module in the
    package).
  - It records the id and the declaring workflow class, meaning the `@workflow.defn` class
    whose body contains the call. The class name is the workflow type unless `name=` is given.
  - Anything unresolvable becomes an `UNKNOWN(unresolved_patch_arg)` entry.
- A git ref target is materialised read-only with `git archive <ref> orchestrator/temporal/
  | tar -x` into a temp dir. There is no checkout of the working tree.
- `check(current, target, reports, max_age, now)`:
  - `removed = ids(current) - ids(target)`.
  - For each removed id, the first matching rule wins:
    - INCOMPATIBLE if a report for it shows `MARKER_PRESENT > 0`.
    - UNKNOWN if there is no report, the report is stale or malformed, `listing_complete` is
      false, `UNKNOWN > 0`, or the query does not contain `WorkflowType = "<declaring type>"`
      and `ExecutionStatus = "Running"`, or contains `WorkflowId`.
    - COMPATIBLE otherwise.
  - The overall verdict is the worst of the per-id verdicts, with UNKNOWN ranked above
    INCOMPATIBLE. Exit codes are 0/2/3, matching the scanner.
- Text and `--json` output list the per-id verdict, reason code, scanner version, `scanned_at`,
  and the PRESENT workflow ids. As in the scanner, output contains no payloads.
- `tools/temporal_marker_scan.py` moves to **MS-5**, a minimal change: `render_json` adds
  `"scanned_at": <UTC ISO-8601>`, taken once at scan start through an injectable clock, and
  `VERSION = "MS-5"`. The check treats an MS-4 report (no `scanned_at`) as UNKNOWN
  (`report_undated`).

Why compare the code's patch ids rather than tags: the hazard is "a recorded id the target
does not call". Tags only encode it indirectly, and the next marker after M1 would need another
hand-maintained floor. Comparing ids also covers a target above `min_tag` that removed or
renamed a patch.

### 3. Reproducible local experiment

New file: `tools/worker_versioning_experiment.py`. Results go under `docs/spikes/1007/`
(`versioning-matrix.json` plus `versioning-matrix.md`) with a short `docs/spikes/1007-worker-
versioning.md`.

- It starts its own server with `WorkflowEnvironment.start_local(namespace="b4-versioning-
  <random>", dev_server_download_version=<requested>, ...)`. It records the server version
  (from `GetSystemInfo`), `temporalio.__version__` and the CLI version. It has no
  `--address`-to-anything-else mode, so it cannot reach production.
- The workflows are synthetic and live in the tool:
  - `ProbeWorkflowOld` and `ProbeWorkflowNew` share one workflow type name. `New` calls
    `workflow.patched("b4-probe-marker")` at a signal-gated site, mirroring the M1 shape.
  - There is a continue-as-new variant that carries the flag in its input.
  - Old and new workers are two `Worker` instances in the same process on one task queue, with
    or without `deployment_config=WorkerDeploymentConfig(version=WorkerDeploymentVersion(
    deployment_name="b4", build_id=...), use_worker_versioning=True,
    default_versioning_behavior=PINNED|AUTO_UPGRADE)`.
- Version routing and overrides go through the `client.workflow_service` RPCs
  (set-current-version, describe deployment, update-workflow-execution-options). The CLI
  equivalents are recorded in the matrix for the runbook.
- The cells:
  - E1: start unversioned runs, then add versioned pollers. Observe whether they progress on
    unversioned pollers, stall, or get pinned.
  - E2: describe or list deployments right after the first versioned poll. FAIL or UNKNOWN on
    an error, recording the error text.
  - E3: a marker history with a pinned override to the old build gives TMPRL1100 (expected
    FAIL), and recovery after the override is removed.
  - E4: a pinned run continues-as-new and keeps its version. Record whether the old version
    reaches Draining or Drained while a pinned run is alive.
  - R1: set current back to old. New runs go to old, and marker-pinned runs stay on new.
  - F1: the new worker raises at startup. Assert RUNNING, backlog grows, no task failure.
  - F2: the new worker writes the marker and stops, and the replacement also fails to start.
    Assert RUNNING, signals and starts are accepted, no `WORKFLOW_TASK_FAILED` over a bounded
    window (default 120 s), and `rollback_compat_check` against a synthetic "old" tree returns
    INCOMPATIBLE. Then a compatible worker returns, and the run completes with the flag True
    and every buffered signal applied once.
  - S1: run `temporal_nondeterminism_scan.classify` on the E3 history (NONDETERMINISM), and
    CLEAN after recovery.
  - S2: stop mid-rollout (both builds polling, current unchanged). Assert there is no movement
    of existing runs.
- Each cell is PASS, FAIL or UNKNOWN with a reason. An exception inside a cell is UNKNOWN,
  never PASS.
- A thin pytest wrapper (`tests/test_worker_versioning_experiment.py`) runs F1, F2 and E3 in
  CI when a dev server can start, and skips loudly otherwise, like
  `tests/test_b4_update_outage_e2e.py`. The full matrix is a manual, recorded run.

F2 also runs once against the real `DevLoopWorkflow`, with the fakes from
`tests/test_b4_update_outage_e2e.py`: an M1 worker passes the gate, then no worker for the
bounded window, then an M1 worker returns. This shows that the synthetic result holds for the
real workflow's waiting shape.

### 4. Runbook and ADR alignment

Edits to `docs/runbooks/worker-rollout-forward-only.md`:

- In the Worker Versioning bullet and the "Open items" row, replace "separate design, not
  started by decision" with "target (A), under verification, see ADR 026 and
  docs/spikes/1007".
- Add a section **Rollback decision**, required before any rollback:
  1. Run the scanner (MS-5) once per patch id removed by the target, for the declaring type.
  2. Run `rollback_compat_check --current <deployed tag> --target <tag> --report ...`.
  3. INCOMPATIBLE or UNKNOWN is a STOP.
- In "Failed new worker", step 4, cite the F2 result (LOCAL) or keep UNVERIFIED if F2 did not
  PASS.
- Fill a "Versioning matrix" table with cell, verdict, versions and a link to the JSON.
- Keep every PROD/UNVERIFIED caveat.

## Alternatives

- **Keep only the static `min_tag` floor (status quo).** It is cheap. But it is maintained by
  hand per marker, it cannot see a removed or renamed patch above the floor, and it says
  nothing about whether markers exist yet (so before the first marker it blocks a rollback
  that is still safe). Rejected as the only guard. It stays as the coarse gate in mctl-gitops.
- **Wire Worker Deployment Versioning into `worker.py` now (A directly).** Rejected for this
  proposal. UNKNOWN 1-2 are open, production dynamic config is unobservable, and a behaviour
  declared without versioning enabled makes the server reject tasks. The owner also limited B4
  to design and verification. It becomes a follow-up once E1-E4 PASS.
- **Implement the B drain gate.** Rejected. The owner made B a fallback, the 14-day merge-watch
  makes the drain long, and abandoning or cancelling live runs is not authorised.
- **Make the rollback check talk to Temporal directly.** Rejected. It would duplicate the
  scanner's connection, TLS and secret handling. Keeping it offline over scanner reports keeps
  one audited reader of production histories.

## Platform impact

- **Migrations / compatibility:** none. No workflow code, patch, activity or task queue changes.
  The scanner's JSON gains one field (`scanned_at`) and its version string. Existing consumers
  of MS-4 JSON keep working (additive). `tests/test_temporal_marker_scan.py` gets an assertion
  for the new field.
- **Resources:** the experiment downloads a Temporal CLI dev server (~100 MB, cached) and runs
  locally or in CI only. The CI wrapper adds about 2-4 minutes when the server is available and
  skips otherwise.
- **Risks and mitigations:**
  - A local PASS is mistaken for proof about production. Mitigation: every matrix and runbook
    row keeps the LOCAL label and the version triple, and production dynamic config stays
    UNVERIFIED.
  - The AST patch extraction misses an indirect call (for example a patch id built at
    runtime). Mitigation: an unresolvable argument is UNKNOWN. A unit test asserts the
    extractor finds every `*_PATCH` constant in the current tree, so a new indirect pattern
    fails CI.
  - A stale scan is used for a rollback. Mitigation: `scanned_at` plus `--max-age`, and an
    undated MS-4 report is UNKNOWN.
  - The experiment tool is pointed at production. Mitigation: it only targets the server it
    started, and it has no external address flag.
  - The F2 bounded window does not prove indefinite waiting. Mitigation: the runbook states
    the window measured, and the missing run timeout is raised as an open question.
