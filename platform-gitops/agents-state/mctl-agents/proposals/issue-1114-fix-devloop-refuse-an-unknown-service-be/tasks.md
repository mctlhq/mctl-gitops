# Tasks: issue-1114-fix-devloop-refuse-an-unknown-service-be

- [ ] 1. Add `EXIT_UNKNOWN_SERVICE = 78`, `UNKNOWN_SERVICE_OUTCOME = "unknown-service"`, `is_known_service(repo)` and `unknown_service_message(repo)` to `config/settings.py`; the message text is byte-identical to today's in `run_issue_investigator.py`. — DoD: helpers exist with docstrings naming the CWFT exit-code contract; `run_issue_poller.py` uses `is_known_service`.
- [ ] 2. (depends on 1) In `orchestrator/run_issue_investigator.py` add `UnknownServiceExit(SystemExit)` (code 78, prints the message to stderr); raise it in `investigate()` from `parse_issue_url(issue_url).repo` before `gh_issue_view`, and keep the post-read check using the same exception. — DoD: an unknown repo exits 78 with the message on stderr and makes no GitHub or model call.
- [ ] 3. (depends on 1) In `orchestrator/temporal/start.py` add `UnknownServiceError(ValueError)` and check at the top of `start_dev_loop_workflow`, `restart_if_restartable` and `dispatch_start_operation`, before any Temporal call; in `orchestrator/temporal/cli.py::start` print it and exit 2; at the dispatcher call site of `dispatch_start_operation` map it to the existing non-retryable request refusal. — DoD: no Temporal client method is called for an unknown repo on any of these paths.
- [ ] 4. (depends on 1) In `orchestrator/temporal/activities/argo.py::_submit_and_wait`, for operation `mctl-agents-investigate` with no resume `workflow_name`, raise `ApplicationError(..., type="UnknownService", non_retryable=True)` for an unknown repo before the POST to mctl-api. — DoD: no HTTP request is made; a resumed attempt with a heartbeated name still polls.
- [ ] 5. Update `CHANGELOG`-relevant docs: add a short note to `docs/` (runbook or the investigator section of `README.md`) describing exit code 78 / outcome `unknown-service` and how to register a service. — DoD: the contract is documented in this repository.
- [ ] 6. (companion, mctl-gitops; depends on 2 being released) In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`, make `run-investigator` write `/tmp/attempt-outcome` (`unknown-service` when RC is 78, else empty) and expose it as output parameter `outcome` with `default: ""`; extend `investigate-fallback`'s `when` to skip on `unknown-service`. — DoD: a canary run on an unknown repo shows `investigate-fallback` Skipped.
- [ ] 7. (companion, mctl-gitops; depends on 6) Pass `primary-outcome` to `assert-attempt` and print the unknown-service text (no quota mention, "a re-run cannot succeed until it is registered") for that outcome; keep the existing text for every other outcome. — DoD: canary log of `assert-produced` names the real reason.
- [ ] 8. File a companion issue in mctlhq/mctl-api: refuse an unknown repo in its `mctl-agents-investigate` operation and DevLoop start before submit, and decide how mctl-api obtains the service list. — DoD: issue exists and is linked from the PR description.

## Tests

- [ ] T1. `tests/test_run_issue_investigator.py`: extend `test_investigate_rejects_unknown_service` to assert `exc.code == EXIT_UNKNOWN_SERVICE`, the message on stderr, and that `gh_issue_view` was never called (monkeypatched to fail). Reverting task 2 makes it fail.
- [ ] T2. `tests/test_settings.py`: pin `EXIT_UNKNOWN_SERVICE == 78`, `UNKNOWN_SERVICE_OUTCOME == "unknown-service"`, and that `unknown_service_message("x")` contains `config/settings.py SERVICES` and `NON_ROTATING_SERVICES`.
- [ ] T3. New test for `start_dev_loop_workflow` / `dispatch_start_operation` / `restart_if_restartable` with a fake client whose every method raises: an unknown repo raises `UnknownServiceError` and the client is never touched; a known repo still reaches the client.
- [ ] T4. CLI test: `cli.start` on an unknown repo exits 2 with the message on stderr and does not call `connect`.
- [ ] T5. `tests/test_temporal_activities.py`: `submit_and_wait` for `mctl-agents-investigate` on an unknown repo raises a non-retryable `ApplicationError` of type `UnknownService` and the HTTP transport records zero requests; with a heartbeated `workflow_name` it resumes polling instead; for a known repo it submits as today.
- [ ] T6. Primary-refuses-fallback-skipped test: a shell-level test (tests/ helper that executes the `run-investigator` wrapper snippet and the `assert-attempt` script extracted from the companion CWFT, or a fixture copy of them) where the primary exits 78: outcome file reads `unknown-service`, the fallback `when` condition evaluates false, and `assert-attempt` output names the unregistered service and contains no "quota". Reverting the `when` change makes it fail. If the CWFT cannot be tested from this repository, this test lands in mctl-gitops with task 6.
- [ ] T7. Regression: existing poller test (`tests/test_run_issue_poller.py`, "not a known service") and directive poller tests pass unchanged.

## Rollback

Revert the mctl-agents PR: the investigator returns to exit 1 for the refusal
and the start/activity gates disappear; nothing persistent was written.
Revert the companion mctl-gitops CWFT PR independently: with exit 78 still in
place the old CWFT simply treats it as a failure (fallback runs, quota text),
which is today's behaviour. Either revert can be done alone in any order.
