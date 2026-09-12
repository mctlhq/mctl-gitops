# Tasks: issue-364-run-implementer-records-a-quota-exhauste

- [ ] 1. Add `orchestrator/rate_limit.py`: `RateLimitExhaustedError`,
      `RateLimitObservation` dataclass, `is_rate_limit_result(message)`,
      `observe_rate_limit_event(message)`, `account_label()`,
      `build_observation(info, *, detail)`, and an epoch -> RFC 3339 helper
      reusing `orchestrator.proposal_state.now_iso`'s formatting convention.
      — DoD: module contains no module-scope `claude_agent_sdk` import (all
      message inspection is duck-typed via `getattr`); `account_label()` reads
      `CLAUDE_OAUTH_ACCOUNT`, falls back to `primary`/`secondary` derived from
      `auth.detect_auth().env_var`, returns `"unknown"` otherwise, and never
      reads a token value; `uv run ruff check orchestrator` and `uv run mypy`
      pass.
- [ ] 2. Point `orchestrator/run_issue_investigator.py` at the shared module
      (depends on 1) — DoD: `RateLimitExhaustedError` is re-exported from
      `orchestrator.rate_limit` (the name stays importable from
      `run_issue_investigator`, as `tests/test_run_issue_investigator.py:35`
      requires); the raise site at `run_issue_investigator.py:1296-1310` uses
      `is_rate_limit_result`; `tests/test_run_issue_investigator.py` passes
      unchanged.
- [ ] 3. Detect the limit in `_run_implementer_agent`
      (`orchestrator/run_implementer.py:657-680`) (depends on 1) — DoD: the
      stream loop retains the latest `rejected` `RateLimitEvent` info and
      raises `RateLimitExhaustedError` carrying a `RateLimitObservation` when
      the terminal `ResultMessage` has `is_error` and
      `api_error_status == 429`; no other message type changes behaviour.
- [ ] 4. Add the `except RateLimitExhaustedError` branch to `implement_one`
      (depends on 3), placed after `ImplementerOperationTimeout` and before the
      generic `Exception` branch — DoD: writes
      `update_status_yaml(ref, "accepted", attempt=None, failure=None,
      rate_limited=<block>)` with
      `{code: "rate-limited", account, rate_limit_type, resets_at,
      resets_at_epoch, overage_disabled_reason, since, observed_at,
      attempt_id, message}`; never writes `needs-triage` or
      `failure.code: no-commits` on this path; returns
      `ImplementResult(..., rate_limited=True, counts_toward_limit=False)`.
- [ ] 5. Make the `rate_limited` block idempotent and self-clearing (depends on
      4) — DoD: an identical block (same `code`/`account`/`rate_limit_type`/
      `resets_at`) preserves `since` and performs no write, mirroring
      `_mark_blocked` (`run_implementer.py:1252-1288`); every existing write
      that already clears `failure`/`blocked` (the `implemented`, `merged`,
      `rejected` and `in-progress` writes at `run_implementer.py:1348-1417`)
      also passes `rate_limited=None`.
- [ ] 6. Add `ImplementResult.rate_limited: bool = False`, `BatchOutcome`
      trailing field `rate_limited: int = 0`, and classification in
      `_batch_outcome()` before the error/skipped branches (depends on 4) —
      DoD: a rate-limited result is counted in its own bucket, existing
      positional/keyword `BatchOutcome(...)` constructions in
      `tests/test_run_implementer_summary.py` still compile, and the
      `=== Summary ===` totals line reports the new count.
- [ ] 7. Add `EXIT_RATE_LIMITED = 46` beside the sentinels at
      `run_implementer.py:150-168`, map it in `_review_feedback_exit_code()`
      for errors prefixed `"rate limited:"`, and exit with it from `main()`
      when a batch is rate-limited with no success (depends on 6) — DoD: the
      new constant is documented in the same comment block as
      `EXIT_BLOCKED_ONLY`, including the note that it is deliberately absent
      from the shepherd's deterministic set; exit stays non-zero so the CWFT
      `implement-fallback` gate is unaffected.
- [ ] 8. Print one stable, greppable stderr line on the rate-limited path
      (depends on 7) — DoD: exactly
      `error: rate-limited: account=<label> type=<type> resets_at=<iso> proposal=<service>/<slug>`,
      no emoji, no credential material, and a code comment naming
      mctl-gitops#1206 as the consumer that will replace `assert-attempt`'s
      guessing prose.
- [ ] 9. Stop the batch on a rate-limited result in `_implement_refs()`
      (`run_implementer.py:1557-1592`) (depends on 6) — DoD: the loop breaks
      after appending the result, with a comment pointing at the existing
      "auth is workflow-global, not proposal-specific" rationale at
      `run_implementer.py:1398-1404`; `counts_toward_limit=False` keeps the
      `--max-proposals` tally honest.
- [ ] 10. Apply the same detection to `review_feedback_one()`
      (`run_implementer.py:696-790`) (depends on 3) — DoD: the new `except`
      branch returns an error prefixed `"rate limited:"`, writes nothing to
      `.status.yaml` (the shepherd owns status in that mode), and `main()`'s
      review-feedback path exits `EXIT_RATE_LIMITED`.
- [ ] 11. Optional guard — skip a proposal whose recorded
      `rate_limited.resets_at` is still in the future and whose recorded
      `account` equals `account_label()` (depends on 4) — DoD: skips before the
      clone and the model call, returns `skipped_reason` with
      `counts_toward_limit=False`, performs no `.status.yaml` write, and fails
      open (never skips) when the account is `unknown`, the block is absent, or
      the timestamp does not parse. Droppable without touching tasks 1-10.
- [ ] 12. Documentation (depends on 4, 7) — DoD: `README.md:139-145` states the
      rate-limited exception to "any incomplete/no-commit attempt moves to
      `needs-triage`"; `run_implementer.py`'s module docstring
      (`:1-80`) gains a short paragraph describing the fourth outcome beside
      succeeded / failed / blocked; the `CLAUDE_OAUTH_ACCOUNT` label is
      documented as optional and non-secret.

## Tests

- [ ] T1. `tests/test_run_implementer_rate_limit.py::test_agent_raises_on_429_result`
      — a terminal `ResultMessage(is_error=True, api_error_status=429)` fed
      through a fake client (mirroring `tests/test_run_implementer_timeout.py`'s
      `_fake_client_factory` and monkeypatching
      `run_implementer.ClaudeSDKClient`) raises `RateLimitExhaustedError`.
- [ ] T2. `...::test_agent_does_not_raise_on_clean_result` and
      `...::test_agent_does_not_raise_on_500` — mirrors
      `tests/test_run_issue_investigator.py:430-449`; a 500 must still reach
      the generic failure path.
- [ ] T3. `...::test_rate_limited_run_leaves_status_accepted` — after
      `implement_one` catches the error, `.status.yaml` has
      `status: accepted`, no `attempt`, no `failure`, and a `rate_limited`
      block whose `code` is `rate-limited`.
- [ ] T4. `...::test_rate_limited_run_is_not_recorded_as_no_commits` — the
      regression this issue is about: `failure` is absent and no value anywhere
      in the written file equals `no-commits` or
      `"implementer produced no commits"`.
- [ ] T5. `...::test_rate_limited_result_does_not_count_toward_limit` —
      `ImplementResult.counts_toward_limit is False`, and `_implement_refs`
      with two refs stops after the first and leaves the second untouched.
- [ ] T6. `...::test_repeated_observation_is_idempotent` — a second identical
      observation preserves `since` and leaves the file byte-identical; a
      changed `resets_at` rewrites it.
- [ ] T7. `...::test_rate_limited_block_is_cleared_on_success` — the
      `implemented` write removes the `rate_limited` key.
- [ ] T8. `...::test_review_feedback_rate_limit_exit_code` — the
      `--review-feedback` path returns `EXIT_RATE_LIMITED`, and
      `tests/test_run_shepherd.py` gains a case asserting `apply_followup`
      classifies exit 46 as `transient=True` (no `review_attempts` consumed).
- [ ] T9. `...::test_batch_summary_reports_rate_limited` — `_batch_outcome`
      counts it in its own bucket and `main()` exits `EXIT_RATE_LIMITED` when
      there was no success; a mixed batch with a PR still exits 0.
- [ ] T10. `...::test_no_credential_material_is_recorded` — with
      `CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-<sentinel>` set, neither the written
      `.status.yaml` nor captured stdout/stderr contains the sentinel.
- [ ] T11. `...::test_skip_while_window_open` (for task 11) — a future
      `resets_at` with a matching account skips without a write; `unknown`
      account, absent block, or unparsable timestamp all still run.
- [ ] T12. `uv run pytest tests/test_worker_isolation.py` still passes —
      `orchestrator.rate_limit` must not drag `claude_agent_sdk` into the
      Temporal worker's import graph.
- [ ] T13. Full gate: `uv run pytest`, `uv run ruff check orchestrator config tests`,
      `uv run mypy` — as required by `CONTRIBUTING.md` and
      `.github/workflows/pr-validation.yml`.

## Rollback

Revert the PR. The change is additive and leaves no schema to migrate:

1. `git revert` the merge commit on `mctl-agents` and cut a normal release; the
   implementer returns to today's behaviour (a 429 is recorded as
   `needs-triage` / `no-commits`).
2. Durable artefacts left behind are harmless. Any proposal carrying a
   `rate_limited` block is still `status: accepted`, which the reverted code
   selects and runs normally; `update_status_file` preserves the unknown key
   and no reader keys on it. An operator may delete the key by hand, but does
   not have to.
3. `EXIT_RATE_LIMITED = 46` disappears with the revert. The shepherd already
   treats unknown exit codes as transient (`run_shepherd.py:1596-1605`), so an
   in-flight subprocess that exited 46 against reverted shepherd code is still
   handled as a retryable failure.
4. If only task 11 (the skip guard) misbehaves — for example an incorrect
   `CLAUDE_OAUTH_ACCOUNT` label stalls real work — unset
   `CLAUDE_OAUTH_ACCOUNT` in the workflow environment. `account_label()` then
   degrades to the token-variable-derived label or `unknown`, and the guard
   fails open without any code change or redeploy.
