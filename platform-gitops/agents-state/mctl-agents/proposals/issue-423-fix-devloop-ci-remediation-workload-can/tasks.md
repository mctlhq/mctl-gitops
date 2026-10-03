# Tasks: issue-423-fix-devloop-ci-remediation-workload-can

- [ ] 1. Verify the log-retrieval route against a real failing required check
      (ideally `mctlhq/mctl-telegram#652`'s `test-cross-platform (macos-latest)`):
      confirm the check-run id can be used as the Actions job id for
      `gh api repos/{repo}/actions/jobs/{id}/logs`, and measure the payload size
      and latency of both that and `gh run view <run_id> --log-failed`.
      — DoD: a short note in the PR body recording which route is primary, which
      is fallback, the observed bytes and seconds, and whether a `StatusContext`
      blocker can ever reach either route.

- [ ] 2. Bounded CI-log retrieval in `orchestrator/ci_checks.py` (depends on 1):
      add `CI_LOG_MAX_CHARS`, `CI_LOG_TOTAL_MAX_CHARS`, `CI_LOG_MAX_CHECKS`,
      env-read `SHEPHERD_CI_LOG_TIMEOUT_SECONDS`, `SHEPHERD_CI_LOG_BUDGET_SECONDS`
      and the `SHEPHERD_CI_LOG_FETCH` kill switch; extend `CheckBlocker` with
      defaulted `log_excerpt`/`log_truncated`/`log_bytes`/`log_status`; add
      `_bound_log()` (head+tail with an elision marker) and
      `fetch_failure_logs()`; pass an explicit `timeout=` to the existing
      `_fetch_annotations` `run_capturing` call, which has none today.
      — DoD: every outbound command carries a timeout; no path raises out of
      `read_required_checks`; per-bundle totals cannot exceed the declared caps;
      `ruff` and `mypy` clean.

- [ ] 3. Wire retrieval into the shepherd (depends on 2): call
      `fetch_failure_logs()` in `run_shepherd.apply_followup` (or immediately
      before it, on `Blockers.checks`) so it runs before the implementer
      subprocess is forked; extend `_augment_bundle_with_ci` to emit
      `log_excerpt` (through `_neutralize_findings_tags`), `log_status`,
      `log_truncated`, plus top-level `work_class` and `budget_report`.
      — DoD: a CI-only bundle written to the temp file contains the bounded log
      fields; `skip_subprocess=True` still short-circuits; retrieval never runs
      for a review-only bundle.

- [ ] 4. Render the bounded evidence: update
      `run_implementer._render_ci_failures_section` to print a
      `Log excerpt (bounded, {log_status})` block, marked when truncated, and add
      the CI-variant prompt ground rule in `_build_prompt` forbidding further log
      retrieval and pointing at the refusal marker as the escape.
      — DoD: rendering is deterministic, tolerates every field being absent
      (pre-#423 bundles), and `tests/test_run_implementer_ci_feedback.py` still
      passes unchanged.

- [ ] 5. Work-class envelope in `orchestrator/options.py` (depends on 4): add
      `IMPLEMENTER_CI_ANALYSIS_SECONDS`, `IMPLEMENTER_TIMEOUT_CEILING_SECONDS`,
      `IMPLEMENTER_MUTATION_RESERVE_SECONDS`, `IMPLEMENTER_TEARDOWN_GRACE_SECONDS`
      (all via `_positive_seconds`), `implementer_envelope(work_class, n_checks)`
      and `validate_budget_contract()` which logs and clamps the drain sub-budget
      when `envelope < 2 * drain + mutation reserve`.
      — DoD: review-only class resolves to exactly `IMPLEMENTER_TIMEOUT_SECONDS`;
      the CI class is capped at the ceiling; a hostile env (`nan`, `inf`, `0`,
      non-numeric) falls back loudly, matching `_positive_seconds`' contract.

- [ ] 6. Apply the envelope in `orchestrator/run_implementer.py` (depends on 5):
      add `_bundle_work_class(bundle)`; give `_run_implementer_agent` keyword
      `envelope_s` and `work_class`; use `envelope_s` in `anyio.fail_after` and
      name it in the orphan raise, the post-drain warning and the
      `ImplementerOperationTimeout` message; pass the class through from
      `review_feedback_one`; leave `implement_one`'s plain path on the base
      envelope.
      — DoD: no behaviour change for a review-only bundle; the Argo log prints
      one line naming work class, envelope and the derivation inputs.

- [ ] 7. Containment (depends on 6): add `_ci_log_guard_hook()` in `options.py`,
      composed with (never replacing) `_command_audit_hooks()`, installed by
      `build_implementer_agent_options(..., work_class=...)` for
      `ci-remediation`/`mixed`; deny `gh run view --log|--log-failed`,
      `gh api .../logs`, and `curl`/`wget` of a `.../logs` URL with a reason
      naming the bundle excerpt.
      — DoD: the deny decision shape is confirmed against the installed
      `claude-agent-sdk` version; a denied command never starts; `hooks` stays
      truthy for every driver so `subagent_wait.drain_until_settled`'s
      precondition holds.

- [ ] 8. Shielded bounded teardown (depends on 6): in `_run_implementer_agent`'s
      `TimeoutError` handler, disconnect the SDK client inside
      `anyio.CancelScope(shield=True)` + `move_on_after(IMPLEMENTER_TEARDOWN_GRACE_SECONDS)`,
      terminate the transport child if the SDK exposes it, then re-raise
      `ImplementerOrphanedSubagent` as today.
      — DoD: teardown runs on the cancelled path (proven by test T5), is itself
      bounded, and the exit code stays 46.

- [ ] 9. Bounded deliberate stop (depends on 6): add
      `EXIT_CI_EVIDENCE_INSUFFICIENT = 50` beside the existing sentinels, emit it
      when the agent stops for insufficient bounded evidence, and add it to the
      harness set in `run_shepherd._followup_code_sets()`.
      — DoD: the shepherd classifies 50 as `harness` — `review_attempts`
      unchanged, `harness_failures` +1, bounded by `MAX_HARNESS_FAILURES`.

- [ ] 10. Claim-lease coupling (depends on 5): change
      `run_implementer._review_claim_lease_default()` to derive its bound from
      `IMPLEMENTER_TIMEOUT_CEILING_SECONDS + 2 * IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`,
      and update the `.env.example` note that currently documents the
      `IMPLEMENTER_TIMEOUT_SECONDS`-derived figure.
      — DoD: the computed lease is >= the widest envelope plus clone and push;
      the lengthen-only override semantics are unchanged.

- [ ] 11. Documentation (depends on 3, 6, 7): write
      `docs/adr/011-execution-budget-contract.md` with the operation/budget
      coverage table and the three distinct invariants (#411 ingestion
      correctness, #418 admission must not consume execution budget, #423 work
      added inside execution must fit or negotiate the envelope); add the new
      knobs to `.env.example` and the budget section of `README.md`.
      — DoD: an operator reading the ADR can say, for any operation in the
      remediation path, which budget bounds it and whether it is inside the
      implementer envelope.

## Tests

- [ ] T1. `tests/test_ci_checks_logs.py` (new): per-fetch timeout is passed to
      `run_capturing`; a `subprocess.TimeoutExpired` yields
      `log_status="timeout"` and never raises; the per-bundle budget and
      `CI_LOG_MAX_CHECKS` mark later blockers `skipped-budget`; a 64 KB payload
      is reduced to <= `CI_LOG_MAX_CHARS` with head, tail and the elision marker;
      the sum across a bundle is <= `CI_LOG_TOTAL_MAX_CHARS`;
      `SHEPHERD_CI_LOG_FETCH=0` skips retrieval entirely.
- [ ] T2. `tests/test_run_shepherd.py` (extend): `_augment_bundle_with_ci` emits
      the new fields; the log excerpt is tag-neutralised; `work_class` is
      `ci-remediation` for a findings-free bundle and `mixed` otherwise;
      retrieval is not invoked for a review-only bundle.
- [ ] T3. `tests/test_options.py` (extend): `implementer_envelope` returns the
      base for review, the derived value for CI, the ceiling when the derivation
      would exceed it; hostile env values fall back; every agent-options builder
      still passes a non-empty `hooks` mapping; the CI builder installs the guard
      hook and the review builder does not.
- [ ] T4. `tests/test_run_implementer_ci_budget.py` (new): the
      `#652`-shaped reproduction — a bundle with 3 actionable checks carrying
      64 KB-sourced bounded excerpts drives `review_feedback_one` with a fake SDK
      client; assert `_run_implementer_agent` received the CI envelope and work
      class, that the rendered prompt is under the declared size cap, and that
      the run reaches a commit decision without any log-fetch command being
      attempted.
- [ ] T5. `tests/test_run_implementer_timeout.py` (extend): with a fake client
      whose stream stalls and a live `local_agent` in the ledger, assert exit 46
      is still raised, that `disconnect()` was awaited on the cancelled path
      (shield works), and that teardown itself cannot exceed
      `IMPLEMENTER_TEARDOWN_GRACE_SECONDS`.
- [ ] T6. Guard-hook unit test: each denied command shape returns a deny decision
      with a reason mentioning the bundle excerpt; an ordinary
      `pytest`/`npm test`/`git` command is allowed; the audit hook still logs.
- [ ] T7. `tests/test_run_shepherd.py` (extend): exit 46 and exit 50 both
      classify as `harness` — `review_attempts` unchanged, `harness_failures`
      incremented, `review-stuck` still reached at `MAX_HARNESS_FAILURES`.
- [ ] T8. Budget-contract invariant test: for every work class,
      `implementer_envelope() >= 2 * IMPLEMENTER_DRAIN_TIMEOUT_SECONDS +
      IMPLEMENTER_MUTATION_RESERVE_SECONDS`, and
      `_review_claim_lease_default() >= implementer_envelope(widest) +
      2 * IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`.
- [ ] T9. `tests/test_worker_isolation.py` (verify, not extend): `ci_checks`
      stays import-light — no `claude_agent_sdk`, no `run_implementer`, no
      `run_shepherd` at module scope after the retrieval additions.

## Rollback

Three levels, cheapest first.

1. **Env only, no deploy.** `SHEPHERD_CI_LOG_FETCH=0` disables retrieval and the
   bundle reverts to the #411 annotation-only shape (the guard hook then has
   nothing to protect but is harmless). `IMPLEMENTER_CI_ANALYSIS_SECONDS=0.001`
   collapses the derived envelope back to `IMPLEMENTER_TIMEOUT_SECONDS` for
   every work class. Both are read per process, so the next shepherd tick picks
   them up.
2. **Revert the agent release.** The change is confined to `mctl-agents`;
   `mctl_rollback_agent`/`mctl_rollback_agent_binding` on the `implementer` and
   `shepherd` agents restores the previous published version. Nothing in
   `.status.yaml` was migrated, so in-flight proposals read identically under the
   old image; the extra bundle keys are ignored by it.
3. **Revert the commit.** `git revert` of the PR merge. `CheckBlocker`'s new
   fields are defaulted and additive, `EXIT_CI_EVIDENCE_INSUFFICIENT = 50` is
   unused by the old shepherd (it would fall into the `transient` arm, which
   retries without charging `review_attempts` — degraded but not harmful), and
   `_review_claim_lease_default` returns to the narrower, still-valid lease.

Leading indicator to watch after rollout: the per-tick budget report line. If
`harness_failures` on CI-remediation follow-ups does not fall, or
`log_status="timeout"` dominates, prefer level 1 and revisit alternative 3 in
design.md (split retrieval and mutation into two executions) rather than raising
the ceiling.
