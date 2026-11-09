# Tasks: issue-1007-design-devloop-temporal-marker-aware-rol

- [ ] 1. Write `docs/adr/026-worker-rollback-boundary.md`, recording the owner decision of
  2026-11-04 (C baseline, A target under verification, B fallback). It defines
  marker-bearing history, compatible build, rollback boundary, and the M1 release as the hold
  build. — DoD: the ADR is merged, linked from the runbook, and references #1007, #993, #996
  and mctl-api#935 (and notes that #935 does not close B4).
- [ ] 2. Scanner MS-5: add `scanned_at` (UTC ISO-8601, injectable clock) to `render_json` in
  `tools/temporal_marker_scan.py`, bump `VERSION` to `MS-5`, and update
  `docs/runbooks/temporal-patch-marker-scan.md`. — DoD: the JSON contains `scanned_at`, and
  existing tests plus a new assertion pass.
- [ ] 3. `tools/rollback_compat_check.py`: AST patch-id extraction (`patch_ids`), read-only
  `git archive` materialisation of a ref, and `check()`. Verdicts are COMPATIBLE,
  INCOMPATIBLE and UNKNOWN, with stable reason codes, exit codes 0/3/2, and text and `--json`
  output. It makes no network calls. (Depends on 2.) — DoD: the tool runs against this tree
  with `--target a99c888` and a synthetic PRESENT report and gives INCOMPATIBLE for
  `deferred-resume-contract`. All unit tests below pass.
- [ ] 4. `tools/worker_versioning_experiment.py`: disposable dev server only, synthetic probe
  workflows (old/new build, continue-as-new variant), cells E1, E2, E3, E4, R1, F1, F2, S1 and
  S2, plus the version triple. It writes `docs/spikes/1007/versioning-matrix.{json,md}`.
  (Depends on 3 for F2.) — DoD: one recorded run is committed with its versions, each cell has
  a verdict and reason, and no cell is PASS without an assertion behind it.
- [ ] 5. F2 against the real `DevLoopWorkflow`, using the fakes from
  `tests/test_b4_update_outage_e2e.py`: an M1 worker passes the gate, then no compatible
  worker for a bounded window, then an M1 worker returns. (Depends on 4.) — DoD: the run stays
  RUNNING with no `WORKFLOW_TASK_FAILED`, buffered signals are applied once, and
  `deferred_resume_contract` is True after recovery.
- [ ] 6. `docs/spikes/1007-worker-versioning.md`: method, versions, matrix, and answers to
  UNKNOWN 1-4. It states explicitly that production dynamic config remains UNVERIFIED.
  (Depends on 4, 5.) — DoD: every UNKNOWN 1-4 has a LOCAL verdict or a documented reason for
  staying UNKNOWN.
- [ ] 7. Update `docs/runbooks/worker-rollout-forward-only.md` (depends on 1, 3, 6):
  - align the Worker Versioning text and the open-items row with the owner decision;
  - add the "Rollback decision" section (scanner per removed id, then
    `rollback_compat_check`, where INCOMPATIBLE or UNKNOWN means STOP);
  - add the versioning matrix table;
  - relabel "Failed new worker" step 4 from the F2 evidence.

  DoD: no statement in the runbook contradicts ADR 026, every new row carries an evidence
  label, and the PROD/UNVERIFIED caveats are kept.

## Tests

- [ ] T1. `tests/test_rollback_compat_check.py`: the extractor finds every `*_PATCH` constant
  that is passed to `workflow.patched` in `orchestrator/temporal/workflows/`. It must include
  `DEFERRED_RESUME_PATCH`, and it is compared against a grep of the source so a new indirect
  pattern fails.
- [ ] T2. Check verdicts on synthetic trees and reports:
  - removed id with PRESENT gives INCOMPATIBLE (exit 3);
  - all ABSENT and fresh gives COMPATIBLE (exit 0);
  - a missing report, `UNKNOWN > 0`, `listing_complete=false`, an MS-4 undated report, a stale
    report, a query narrowed by `WorkflowId`, or a query for the wrong workflow type each give
    UNKNOWN (exit 2) with the expected reason;
  - an unresolvable `workflow.patched` argument gives UNKNOWN;
  - an empty `removed` set gives COMPATIBLE.
- [ ] T3. Mutation set: removing the PRESENT branch, ranking UNKNOWN below INCOMPATIBLE,
  accepting an undated report, or ignoring `listing_complete` each turns at least one T2 case
  red.
- [ ] T4. A real git ref: `--target a99c888` against this tree reports
  `deferred-resume-contract` in `removed`. The test skips if the object is not in the clone,
  so shallow CI still runs the rest.
- [ ] T5. Scanner MS-5: `render_json` includes `scanned_at` from the injected clock, and
  `scanner_version == "MS-5"`.
- [ ] T6. `tests/test_worker_versioning_experiment.py` (dev server, skips loudly when
  unavailable):
  - F1: RUNNING, backlog grows, no task failure;
  - F2: RUNNING through the window, recovery with the flag True and signals applied once;
  - E3: TMPRL1100 under the old-build override, recovery after the override is removed, and
    `temporal_nondeterminism_scan` classifies the history NONDETERMINISM.
- [ ] T7. Safety: the experiment tool rejects any attempt to use a server it did not start
  (unit test on argument handling).

## Rollback

Everything here is additive tooling and documentation, with no workflow, worker, deploy or
flag change. To roll back:

- revert the PR;
- the scanner returns to MS-4 (the added field is dropped);
- the runbook returns to the draft text.

The forward-only policy itself is not rolled back by reverting this change, because it is the
owner's decision. Without the check, the static `min_tag` floor in mctl-gitops
`release-gates.yaml` remains the only guard.
