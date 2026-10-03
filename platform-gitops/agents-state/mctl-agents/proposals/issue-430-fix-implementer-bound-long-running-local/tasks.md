# Tasks: issue-430-fix-implementer-bound-long-running-local

- [ ] 1. Add `orchestrator/exec_budget.py` with `CommandBudgetLedger`
      (`clamped`, `denied_background`, `denied_exhausted`, `last_bound_s`,
      `last_command`, `exhausted`, `describe()`, `as_dict()`),
      `command_budget()`, `is_detached()`, `DETACH_PATTERNS`, and
      `wrap_bounded()`. Move `_normalize_shell_command` here and re-export it
      from `orchestrator/options.py` so #427's CI-log patterns keep their exact
      current behaviour. No `claude_agent_sdk` import at any scope.
      — DoD: module imports with the SDK absent; `uv run mypy .` clean;
      `tests/test_worker_isolation.py` still green.

- [ ] 2. Add the knobs in `orchestrator/options.py` via `_positive_seconds`:
      `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS` (120.0),
      `IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS` (20.0),
      `IMPLEMENTER_COMMAND_KILL_GRACE_SECONDS` (5.0), and the
      `IMPLEMENTER_BOUND_COMMANDS` break-glass flag. Reuse the existing
      `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS` as the per-command ceiling — do not
      add a new ceiling knob. (depends on 1)
      — DoD: each knob clamps a hostile value loudly and honours a valid env
      override, matching `test_new_budget_knobs_clamp_hostile_env_values`.

- [ ] 3. Extend `options.validate_budget_contract()` with the second assertion
      `envelope >= TEARDOWN_RESERVE + MIN_COMMAND_BUDGET + MUTATION_RESERVE`
      for every work class, clamping `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS`
      (never the ceiling, never the mutation reserve) and logging to stderr.
      (depends on 2)
      — DoD: defaults satisfy it for `review`/`ci-remediation`/`mixed`; a tight
      env combination produces one warn line and a clamped reserve, never a
      raise.

- [ ] 4. Implement `options._deadline_guard_hook(deadline_monotonic, ledger, *,
      timeout_available)` as a factory returning the async `PreToolUse` hook:
      deny detached/`run_in_background` calls, deny when
      `command_budget(...)` is `None`, otherwise allow with `updatedInput`
      carrying the `timeout`-wrapped command and a NARROWED millisecond
      `timeout`. Non-`Bash` tools pass through untouched. Add
      `_deadline_guard_hooks()` mirroring `_ci_log_guard_hooks()`.
      (depends on 1, 2)
      — DoD: every branch returns a well-formed
      `PreToolUseHookSpecificOutput`; the ledger reflects each decision; the
      hook never raises on malformed `input_data`.

- [ ] 5. Thread the deadline through `build_implementer_agent_options()`: new
      `deadline_monotonic` and `budget_ledger` params defaulting to `None`,
      composed with `_compose_hooks` for EVERY work class when supplied, never
      replacing `_command_audit_hooks()` or `_ci_log_guard_hooks()`.
      (depends on 4)
      — DoD: `tests/test_options.py::test_hooks_are_what_hold_stdin_open_for_every_drainable_builder`
      and the `always_load` tests stay green; omitting the new params yields
      options byte-identical to today's.

- [ ] 6. In `orchestrator/run_implementer.py:_run_implementer_agent()`, compute
      `deadline = anyio.current_time() + envelope_s` immediately before
      `anyio.fail_after(envelope_s)`, probe `shutil.which("timeout")` once
      (loud warn + clamp-only fallback when absent), accept a
      `budget_ledger` param, and pass all three into the options builder.
      (depends on 5)
      — DoD: the deadline is monotonic and on the same clock as `fail_after`;
      the existing timeout/orphan/teardown tests in
      `tests/test_run_implementer_timeout.py` are unchanged and green.

- [ ] 7. Add `EXIT_VERIFICATION_BUDGET_EXHAUSTED = 51` and
      `VERIFICATION_BUDGET_EXHAUSTED_ERROR_PREFIX`; map it in
      `_review_feedback_exit_code()`; add the `verification_budget_exhausted`
      boolean to `RefusalMarker` / `_read_refusal_marker()`; in
      `review_feedback_one()` create the ledger, pass it in, and on
      "no commits + no ordinary refusal + `ledger.exhausted`" return the
      prefixed, orchestrator-derived error; print `ledger.describe()` on the
      success path too. Extend `main()`'s `--refusal-out` ladder with the 51 arm
      writing `ledger.as_dict()` as JSON. Wire the same ledger through
      `implement_one()`. (depends on 6)
      — DoD: exit 51 is reachable end-to-end; the JSON at `--refusal-out` is
      machine-readable and contains no model prose; exits 42/44/46/47/50 are
      unchanged.

- [ ] 8. Pin the SDK contract: assert the `claude-agent-sdk` version in
      `pyproject.toml`/`uv.lock` exposes `updatedInput` on
      `PreToolUseHookSpecificOutput`, and record in the hook's docstring the
      documented fallback (deny + hand the agent the wrapped command in the deny
      reason) if a future CLI stops honouring it. (depends on 4)
      — DoD: a test fails loudly if `updatedInput` disappears from the SDK's
      types, in the same spirit as `tests/test_subagent_wait.py`'s
      `AWAITED_TASK_TYPES` drift guard.

- [ ] 9. Shepherd side: add 51 to the **harness** set in
      `run_shepherd._followup_code_sets()` with the rationale in the docstring,
      and extend the `refusal_reason` gate (`run_shepherd.py:~2414`) to
      `| {EXIT_VERIFICATION_BUDGET_EXHAUSTED}` so the structured reason reaches
      the log line, `FollowupSubprocessError.reason`, and the `review-stuck`
      note. (depends on 7)
      — DoD: exit 51 never charges `review_attempts`, increments
      `harness_failures`, and its reason appears in the shepherd's output.

- [ ] 10. Prompt + docs: add the bounded-command ground rules to both branches
      of `_build_prompt()` (bounded by remaining envelope; backgrounding,
      `nohup`/`setsid`/`disown` and polling loops are blocked; commit what is
      proven; marker field for the exhausted case), and amend
      `docs/adr/011-execution-budget-contract.md` with the fourth invariant plus
      the new coverage-table row. Do not supersede the ADR. (depends on 7)
      — DoD: the coverage table has no unbounded row left; the ADR names
      mctl-agents#430 and states that `EXIT_ORPHANED_SUBAGENT` remains the
      safety net, not the normal path.

## Tests

- [ ] T1. `tests/test_exec_budget.py` — `command_budget()` table: early
      envelope clamps to the 300s ceiling; mid-envelope clamps to
      `remaining - reserve`; below the floor returns `None`. Never widens above
      a caller-supplied value.
- [ ] T2. `tests/test_exec_budget.py` — `is_detached()` matches
      `go test -race ./... > /tmp/test-race.log 2>&1 &` (the production shape),
      `nohup ...`, `setsid ...`, `... & disown`, a backslash-continued trailing
      `&`; and does NOT match `a && b`, `cmd 2>&1`, `cmd 1>&2`,
      `grep '&' file`.
- [ ] T3. `tests/test_exec_budget.py` — `wrap_bounded()` round-trips heredocs,
      pipelines, `&&` chains and multi-line scripts through
      `bash -c`+`shlex.quote`, and always carries `--kill-after`.
- [ ] T4. `tests/test_options.py` — the deadline guard denies
      `run_in_background: true` and each detachment form with a reason naming
      it; allows an ordinary command with `updatedInput` whose `timeout` is the
      derived bound in ms; denies once the budget floor is crossed with a reason
      naming the marker field; leaves non-`Bash` tools untouched.
- [ ] T5. `tests/test_options.py` — the guard is composed WITH
      `_command_audit_hooks()` and (on `ci-remediation`) with
      `_ci_log_guard_hooks()`; `hooks` stays truthy for every drainable builder;
      `validate_budget_contract()` clamps the teardown reserve on a tight
      envelope.
- [ ] T6. **Regression fixture reproducing #652** in
      `tests/test_run_implementer_timeout.py`: a fake client whose scripted
      stream launches a `local_agent` task and then issues a Bash call whose
      natural runtime exceeds the remaining budget, under a short envelope.
      Asserts, per the issue's acceptance list: the call is bounded to
      `remaining - reserve`; the command is terminated before outer expiry; the
      ledger records `exhausted`; the driver returns WITHOUT raising
      `ImplementerOrphanedSubagent`; `ledger.live` is empty at return.
- [ ] T7. Same file — a normal short verification early in a long envelope is
      allowed with its bound intact and completes with `EXIT_OK` and no
      cancellation (acceptance criterion 8).
- [ ] T8. `tests/test_run_implementer_refusal.py` — the ledger-derived and the
      marker-derived exhausted paths both map to exit 51 and write
      machine-readable JSON to `--refusal-out`; an ordinary refusal still maps
      to 47 and an insufficient-evidence marker still to 50.
- [ ] T9. `tests/test_run_shepherd.py` — exit 51 classifies as
      `FollowupKind = "harness"`, leaves `review_attempts` unchanged,
      increments `harness_failures`, surfaces the structured reason, and
      converges to `review-stuck` at `MAX_HARNESS_FAILURES`.
- [ ] T10. `tests/test_run_implementer_timeout.py` — the `timeout`-binary-absent
      fallback: one loud warning, tool-input clamping still applied, detachment
      denials still enforced, no crash.
- [ ] T11. Full gate: `uv run pytest`, `uv run ruff check .`, `uv run mypy .`.

## Rollback

Two levels, no migration to undo.

1. **Runtime, no deploy.** Set `IMPLEMENTER_BOUND_COMMANDS=0` on the implementer
   CWFT to stop rewriting commands (clamping and detachment denials remain), or
   raise `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS`/lower
   `IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS` to loosen the boundary. All knobs
   clamp loudly rather than fail.
2. **Code.** Revert the PR. The deadline/ledger parameters default to `None`,
   so the previous behaviour is exactly the `None` path; exit 51 simply stops
   being produced, and a shepherd that still knows about it never sees it.
   Nothing persistent was written: no `.status.yaml` field, no GitOps state, no
   schema.

Watch after deploy: `harness_failures` ticks attributed to 46 versus 51 across
CI-remediation runs, and the `clamped`/`denied_exhausted` counters in the Argo
logs. A rise in 51 with no fall in 46 means the guard is not on the path that
orphans; a rise in `denied_exhausted` early in envelopes means the reserve is
too large. Re-run the mctlhq/mctl-telegram#652 live-acceptance path before
considering #423/#411 live-proven.
</content>
</invoke>
