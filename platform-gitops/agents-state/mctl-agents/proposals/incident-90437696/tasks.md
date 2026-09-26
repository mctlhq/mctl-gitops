# Tasks: incident-90437696

1. [ ] Re-read `orchestrator/run_implementer.py` and
   `orchestrator/run_issue_investigator.py` on current `main` and confirm the
   line numbers, exception ordering, and surrounding contracts (exit codes
   42-45, `ImplementResult.counts_toward_limit`, the in-progress lease,
   `tests/test_worker_isolation.py`) still match the design in
   `platform-gitops/agents-state/mctl-agents/proposals/issue-364-run-implementer-records-a-quota-exhauste/design.md`.
2. [ ] Check why `https://github.com/mctlhq/mctl-agents/pull/409` was closed
   without merging (review comments, CI, or a change of direction) before
   resubmitting the same design unchanged.
3. [ ] Add `orchestrator/rate_limit.py` (SDK-free: `RateLimitExhaustedError`,
   `RateLimitObservation`, `is_rate_limit_result()`,
   `observe_rate_limit_event()`, `account_label()`, `build_observation()`).
4. [ ] In `_run_implementer_agent`, raise `RateLimitExhaustedError` on a
   terminal `ResultMessage` with `is_error=True` and `api_error_status == 429`.
5. [ ] In `implement_one()`, add an `except RateLimitExhaustedError` branch
   that writes `status: accepted` with a `rate_limited` block instead of
   `status: needs-triage` / `failure.code: no-commits`, and clears the
   in-flight `attempt` lease.
6. [ ] Add `EXIT_RATE_LIMITED` exit code, batch classification, and the stable
   stderr line; ensure a rate-limited result does not count toward
   `--max-proposals` or the shepherd's `review_attempts` budget.
7. [ ] Add/port the regression tests mirroring
   `tests/test_run_issue_investigator.py` (429 raises, clean result does not
   raise, non-429 error does not raise) for the implementer path, plus a test
   asserting no credential value reaches `.status.yaml` or logs.
8. [ ] Run the full `mctl-agents` test suite, including
   `tests/test_worker_isolation.py`, to confirm the new module does not pull
   `claude_agent_sdk` into the Temporal worker's import graph.
9. [ ] Verify no dependent-image-tag bump is needed for this change (Python
   orchestrator source change only, picked up on next image build/deploy).
