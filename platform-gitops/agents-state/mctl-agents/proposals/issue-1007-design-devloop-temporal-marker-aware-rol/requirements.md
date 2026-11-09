# DevLoop worker rollback boundary: marker-aware rollback check, forward-only emergency path, and a reproducible Worker Versioning experiment (B4)

## Context

Issue mctlhq/mctl-agents#1007 is blocker B4 of the #993 / #996 release safety gate. M1
(`DEFERRED_RESUME_PATCH = "deferred-resume-contract"` in
`orchestrator/temporal/workflows/dev_loop.py`) calls `workflow.patched(...)` unconditionally
right before `_gates_passed` is set. From then on any pre-M1 worker (1.117.0 / a99c888) that
replays the history fails with `[TMPRL1100] Nondeterminism error`. So "roll the image back" is
unsafe as soon as one history carries the marker, and it is silently unsafe for continue-as-new
runs, which carry the contract in their resume payload and have no marker of their own.

The owner decided on 2026-11-04: **C (forward-only)** is the baseline policy, **A (Worker
Deployment Versioning)** is the target, to be verified, and **B (drain before M1)** is a
fallback only. B4 does not close until there is a verified emergency scenario, including the
case where the fixed worker does not start. The repository already has the read-only marker
scanner (`tools/temporal_marker_scan.py`, MS-4), the non-determinism detector
(`tools/temporal_nondeterminism_scan.py`), the pre-M1 fixtures (`tests/test_pre_m1_compat.py`)
and a draft runbook (`docs/runbooks/worker-rollout-forward-only.md`). This proposal adds what is
still missing so the forward-only policy can be enforced and checked, not just written down:

- a record of the decision as an ADR;
- a marker-aware rollback check that refuses any rollback target lacking a patch id that live
  histories have recorded;
- a reproducible local experiment (disposable dev server, synthetic data) that writes down the
  answers to UNKNOWN 1-4 and the emergency cells;
- an updated runbook.

Everything here is design, tooling and local verification. Nothing is released, deployed or
flag-flipped, and nothing touches production Temporal. **B4 remains FAIL** after this proposal
unless a distinct owner-approved release-gate integration and production-compatible evidence
also exist. The standalone check cannot prevent an automated GitOps rollback by itself.

## User stories

- AS the release owner I WANT a rollback to be refused whenever live histories carry a patch
  marker the target build does not know SO THAT the forward-only policy (C) is enforced by a
  tool and not only by memory.
- AS the on-call operator I WANT a verified procedure for "the fixed worker does not start
  either" SO THAT I know workflows wait safely and which actions are forbidden.
- AS the platform owner I WANT a reproducible PASS/FAIL/UNKNOWN matrix for Worker Deployment
  Versioning, with Server, Python SDK and CLI versions recorded SO THAT I can decide whether A
  is viable before any cluster change.
- AS a reviewer of a future patch marker I WANT the same check to work for any
  `workflow.patched` id SO THAT B4-style hazards do not need a new bespoke process each time.

## Acceptance criteria (EARS)

Decision record
- THE SYSTEM SHALL contain `docs/adr/026-worker-rollback-boundary.md`, which records C as the
  baseline, A as the target under verification and B as a fallback. It SHALL define
  "marker-bearing history", "M1-compatible build" and "rollback boundary".

Marker-aware rollback check (`tools/rollback_compat_check.py`)
- WHEN given a current source tree, a target source tree (or git ref) and one or more MS
  scanner JSON reports, THE SYSTEM SHALL compute the patch ids that `workflow.patched(...)`
  calls under `orchestrator/temporal/workflows/` in each tree, resolving module-level string
  constants, and the set `removed = patches(current) - patches(target)`.
- IF any id in `removed` has a report with `counts.MARKER_PRESENT > 0` THEN THE SYSTEM SHALL
  print INCOMPATIBLE, name the id and the workflow ids, and exit 3.
- IF any id in `removed` has no report, or a report with `UNKNOWN > 0`,
  `listing_complete = false`, a query that does not select every running execution of the
  declaring workflow type, an unreadable file, or a report older than `--max-age` (default 30
  minutes) THEN THE SYSTEM SHALL print UNKNOWN with a stable reason code and exit 2.
- IF a tree cannot be parsed, or a `workflow.patched` argument is not a literal or resolvable
  module constant, THEN THE SYSTEM SHALL return UNKNOWN (exit 2) and never COMPATIBLE.
- WHEN `removed` is empty, or every id in it has a complete, fresh report with only
  MARKER_ABSENT, THE SYSTEM SHALL print `PATCH_COMPATIBLE` (exit 0) and state that this is **only an offline necessary-condition check**, valid at the scan instant. It SHALL **NOT** assert that the target worker is replay-safe, that a release/rollback is authorised, or that new markers cannot appear before a rollout.
- THE SYSTEM SHALL NOT connect to Temporal, GitHub or Kubernetes. Its inputs are files and a
  local git repository only.
- WHEN the scanner writes a JSON report THE SYSTEM SHALL include a UTC `scanned_at` timestamp
  (scanner version MS-5), so the check can judge freshness.

Local experiment (`tools/worker_versioning_experiment.py`)
- WHEN run, THE SYSTEM SHALL start a disposable local Temporal dev server in a dedicated
  namespace with synthetic workflows only. It SHALL refuse to run if `--address` points
  anywhere other than a server it started itself.
- THE SYSTEM SHALL write a result matrix (JSON plus a rendered Markdown table) under
  `docs/spikes/1007/`. Every cell is PASS, FAIL or UNKNOWN, and the matrix records the Server,
  temporalio and CLI versions and states that a local PASS is not proof of the production
  configuration.
- THE SYSTEM SHALL cover at least these cells:
  - E1: unversioned to versioned transition for running unversioned workflows;
  - E2: whether Worker Deployments are available, and how that is observed;
  - E3: a pinned override of a marker-bearing history to the old build;
  - E4: whether a pin is inherited through continue-as-new, and how long a pinned old build
    must stay up;
  - R1: routing rollback for new workflows without handing marker histories to an old worker;
  - F1: the new worker fails to start;
  - F2: the fixed worker also fails to start and no compatible worker is polling;
  - S1: stuck workflow recovery;
  - S2: stopping a rollout.
- IF the dev server cannot be started or reports a version other than the requested one THEN
  THE SYSTEM SHALL mark the affected cells UNKNOWN with the reason and not PASS.

Emergency scenario F2 (verified, not inferred)
- WHILE no worker able to replay a marker-bearing history is polling, THE SYSTEM SHALL be shown
  by test to keep that workflow RUNNING with no `WORKFLOW_TASK_FAILED` and no failed or
  terminated execution, and to keep accepting signals and starts into the backlog.
- WHEN an M1-compatible worker returns after F2, THE SYSTEM SHALL be shown by test to resume
  the workflow with the contract flag intact and to process the buffered signals exactly once.
- WHILE F2 holds, THE SYSTEM SHALL make `rollback_compat_check` refuse the pre-M1 target
  (INCOMPATIBLE).

Runbook
- THE SYSTEM SHALL update `docs/runbooks/worker-rollout-forward-only.md` to match the owner
  decision (A is a target under verification, not "not started by decision"). It SHALL add a
  "Rollback decision" step that runs the scanner for every removed id and then
  `rollback_compat_check`, and it SHALL replace the UNVERIFIED label on the "fixed worker also
  does not start" scenario with the LOCAL evidence from the experiment, or keep it UNVERIFIED
  if a cell did not PASS.

## Required release-gate boundary (separate approval, not this implementer)

- A `PATCH_COMPATIBLE` / exit-0 decision does not prove workflow-code replay compatibility,
  Worker Versioning availability, deployment routing, or ability to start the candidate worker.
  The B4 owner gate remains **FAIL**, not PASS, until those have independent evidence.
- A live rollout/rollback must pin the exact running image digest and Temporal worker/SDK
  version, obtain a **complete live scan** covering all relevant workflow types and
  continue-as-new ancestors, fence starts and marker-producing updates during the decision
  window or revalidate immediately at the point of effect, and prove that the same scan and
  rollback check actually block the GitOps / Argo paths (including direct push, manual
  rollback and other deploy credentials). A stale/partial/unobservable scan is STOP.
- Integrating the checker as a mandatory fail-closed release gate is a **separately reviewed
  implementation**; it is not authorised by this proposal. No release hold is lifted by
  completion of a local experiment or an offline verdict.

## Out of scope

- Any release, deploy, image tag change, `min_tag` change, flag change, or access to production
  Temporal. The M1 deploy PR in mctl-gitops is not part of this.
- Wiring `WorkerDeploymentConfig` into `orchestrator/temporal/worker.py` for production. That
  is a follow-up issue, opened only if the experiment gives E1-E4 PASS and the owner adopts A.
- Option B's drain, and any cancel, terminate, reset or abandon of live workflows.
- The platform alert rule for `failed_workflow_tasks{failure="NonDeterministicError"}`
  (mctl-gitops), Recreate on the control worker (mctl-gitops#2394), and the merge-watch
  deadline-in-gap fix. They stay listed as open items in the runbook.
- The amendment to #993 for the rollback boundary. The owner does that on GitHub.

## Open questions

- The production server is 1.31.0. Whether `WorkflowEnvironment.start_local` can pin a CLI
  build that bundles exactly server 1.31.0 is not established; the runbook's LOCAL rows used
  1.29.1 to 1.32.0. Proceeding: request 1.31.0, record the version actually reported, and mark
  cells UNKNOWN on a mismatch.
- Whether production dynamic config enables Worker Deployments (UNKNOWN 2) cannot be read from
  outside. The experiment answers it only for the dev server; production stays UNVERIFIED.
- The deployed `min_tag` floor is a static tag. Should the rollback check also become a
  required step in mctl-gitops' release-deploy gate (it would need scanner reports as
  artifacts)? Proceeding: the check is a repo tool referenced by the runbook, and gate
  integration is a follow-up.
- F2 has no "earlier M1-compatible image" on the first M1 release. This proposal treats the M1
  release itself as the hold build (the floor) and verifies that waiting is safe. It does not
  build a separate "hold" image.
- DevLoop runs carry no execution or run timeout today (none is set in
  `orchestrator/temporal/start.py`), so waiting is bounded only by the operator. The experiment
  verifies this on the dev server. Whether a timeout should exist is an owner question.
