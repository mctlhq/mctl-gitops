# Tasks: issue-493-usage-producer-flush-queued-usage-record

- [ ] 1. Add `SIGTERM_FLUSH_TIMEOUT_SECONDS = 15.0` next to the existing
      timeout constants in `orchestrator/usage_ledger.py` (near line 79),
      with a comment stating the reasoning: one full delivery cycle
      (`REQUEST_TIMEOUT_SECONDS` x `ATTEMPTS` + `RETRY_DELAY_SECONDS` = 11 s)
      plus slack, kept below the assumed 30 s pod grace period, and
      deliberately shorter than the 25 s `FLUSH_TIMEOUT_SECONDS` used by the
      `atexit` path — DoD: constant exists, comment names both bounds, ruff
      and mypy clean.

- [ ] 2. Implement `_die_by_sigterm()` in `orchestrator/usage_ledger.py`:
      restore `signal.signal(signal.SIGTERM, signal.SIG_DFL)` then
      `signal.raise_signal(signal.SIGTERM)` (depends on 1) — DoD: a process
      that installs the hook and is sent SIGTERM ends with wait status
      "killed by SIGTERM" (`returncode == -signal.SIGTERM`), never a normal
      exit code.

- [ ] 3. Implement the handler `_on_sigterm(signum, frame)` (depends on 2):
      a module-level in-progress flag so a second SIGTERM calls
      `_die_by_sigterm()` at once; one `logger.warning` naming SIGTERM and
      the bound; the `flush(timeout)` wait executed on a
      `name="usage-ledger-sigterm"` daemon thread joined with `timeout`
      (the same shape as `orchestrator/tracing_sdk.py:365`
      `bounded_shutdown`, and for the same reason — the handler may be
      re-entering `queue.mutex` held by the interrupted main thread);
      a warning if the thread is still alive after the join; every branch
      wrapped so nothing escapes, always falling through to
      `_die_by_sigterm()` — DoD: handler cannot raise, cannot block past
      `timeout`, and always terminates the process.

- [ ] 4. Implement the public `install_sigterm_flush(timeout: float =
      SIGTERM_FLUSH_TIMEOUT_SECONDS) -> bool` (depends on 3) with the three
      decline guards, each returning `False` after a single info/debug line:
      not `threading.main_thread()`; `signal.getsignal(signal.SIGTERM)` is
      not `signal.SIG_DFL` (this is what protects
      `orchestrator/temporal/worker.py:791`); already installed in this
      process — DoD: returns `True` exactly once per process, never raises,
      and leaves an existing SIGTERM handler untouched.

- [ ] 5. Keep `atexit.register(flush)` (`orchestrator/usage_ledger.py:189`)
      exactly as it is, and leave `observe`, `_Worker`, `_record`, `_plan`,
      `_deliver`, `_commit` and the baseline semantics untouched (depends on
      4) — DoD: `git diff` over `orchestrator/usage_ledger.py` touches only
      the docstring, the new constant and the new signal functions; the
      existing usage-ledger tests pass unchanged.

- [ ] 6. Call `usage_ledger.install_sigterm_flush()` as the first statement
      of `_traced_main()` in `orchestrator/run_implementer.py:4926` and in
      `orchestrator/run_issue_investigator.py:3220` (depends on 4) — DoD:
      both drivers install the hook before `init_tracing`, and no non-
      `__main__` caller of `_traced_main` exists (verify with a grep over
      `tests/`).

- [ ] 7. Call `usage_ledger.install_sigterm_flush()` in the
      `if __name__ == "__main__":` block of `orchestrator/run_shepherd.py`
      (line 3982), before `main()` — explicitly NOT inside `main()`, because
      `tests/test_run_shepherd.py` calls `run_shepherd.main()` directly at
      nine sites and must not acquire a SIGTERM handler (depends on 4) —
      DoD: the shepherd test suite passes and
      `signal.getsignal(signal.SIGTERM)` is unchanged after those tests run.

- [ ] 8. Do NOT touch `tracing.agent_run.__enter__/__exit__/__aenter__/
      __aexit__` (`orchestrator/tracing.py:994-1050`) — DoD: `git diff` shows
      no change to `orchestrator/tracing.py`; the review notes this
      explicitly, since a flush there would reintroduce the event-loop stall
      #491 removed.

- [ ] 9. Update the "Off the event loop" paragraph of the module docstring
      in `orchestrator/usage_ledger.py` (lines 40-46) to describe both exit
      paths: `atexit` for a normal exit and SIGINT, the SIGTERM handler for a
      terminated pod, and why the handler re-raises the default rather than
      exiting (depends on 4) — DoD: the docstring names both paths and the
      wait-status guarantee.

- [ ] 10. Amend
      `docs/adr/012-model-usage-cost-attribution-contract.md:352`, which
      today says only that "An `atexit` hook flushes what is still queued",
      to mention the SIGTERM path (depends on 9) — DoD: documentation-only
      diff, no contract or schema change.

- [ ] 11. Run `uv run pytest tests/`, `uv run ruff check orchestrator config
      tests` and `uv run mypy` (depends on 1-10) — DoD: all three green, as
      `.github/workflows/pr-validation.yml` requires.

## Tests

All new tests go in `tests/test_usage_ledger.py`, next to the existing exit
tests.

- [ ] T1. **The SIGTERM flush delivers, end to end.** Mirror
      `test_a_runner_that_exits_right_after_its_last_turn_still_delivers_it`
      (`tests/test_usage_ledger.py:409`): a `subprocess.Popen` child that
      calls `usage_ledger.install_sigterm_flush()`, installs a slow `post`
      writing the body to `tmp_path`, observes a real
      `claude_agent_sdk.ResultMessage`, prints a ready marker and flushes
      stdout, then sleeps. The parent waits for the marker, sends
      `SIGTERM`, and asserts the record file lands with
      `records[0]["output_tokens"] == 4` — DoD: the test fails against
      `main` (nothing is written) and passes with the change.

- [ ] T2. **The process still dies as SIGTERM means.** Same child as T1;
      assert `proc.returncode == -signal.SIGTERM` — DoD: guards against a
      future `sys.exit(143)` regression.

- [ ] T3. **A second SIGTERM kills immediately.** Child with a `post` that
      blocks far longer than the timeout; send SIGTERM twice and assert the
      child is gone well inside `SIGTERM_FLUSH_TIMEOUT_SECONDS` — DoD: an
      impatient operator is never made to wait for the bound.

- [ ] T4. **The timeout is bounded and logged.** Unit test calling the
      handler directly with `flush` monkeypatched to block and
      `_die_by_sigterm` monkeypatched to a sentinel: assert it returns
      within roughly the timeout and that a warning naming undelivered
      records was logged (`caplog`) — DoD: no unbounded wait path.

- [ ] T5. **An existing SIGTERM handler is never displaced.** Install a dummy
      handler with `signal.signal`, call `install_sigterm_flush()`, assert it
      returns `False` and `signal.getsignal(signal.SIGTERM)` is still the
      dummy; restore in a fixture — DoD: the Temporal worker's ADR-008 drain
      (`orchestrator/temporal/worker.py:791`) provably cannot be replaced.

- [ ] T6. **Off the main thread it declines instead of raising.** Call
      `install_sigterm_flush()` from a `threading.Thread` and assert it
      returned `False` and raised nothing — DoD: the lazy
      `tracing.agent_run.__init__` import path can never crash a run.

- [ ] T7. **Idempotent.** Two calls in one process install one handler and
      the second returns `False` — DoD: handlers cannot stack.

- [ ] T8. **Structural: every usage-recording driver installs the hook.**
      AST test in the style of
      `test_every_options_builder_goes_through_the_scrubbing_constructor`
      (`tests/test_usage_ledger.py:445`): for every `orchestrator/run_*.py`
      containing a `tracing.agent_run(...)` call, assert the module also
      contains an `install_sigterm_flush(...)` call. Assert the set of such
      modules is exactly `{run_implementer, run_issue_investigator,
      run_shepherd}` so a fourth recorder is a deliberate change — DoD: a
      new driver that records usage without the hook fails CI.

- [ ] T9. **No regression on the existing paths.** The whole of
      `tests/test_usage_ledger.py`, plus `tests/test_run_shepherd.py` and
      `tests/test_worker_roles.py` (which raises a real SIGTERM at line 491),
      pass unchanged — DoD: the worker's signal test is unaffected.

## Rollback

The change is additive and confined to four files
(`orchestrator/usage_ledger.py`, `orchestrator/run_implementer.py`,
`orchestrator/run_issue_investigator.py`, `orchestrator/run_shepherd.py`)
plus two documentation edits. There is no schema, no migration and no
mctl-api change, so rollback is a code revert only.

1. **Fastest partial kill switch, no revert:** delete the three
   `install_sigterm_flush()` call sites (tasks 6 and 7). SIGTERM returns to
   `SIG_DFL` and the producer behaves exactly as it does today, with the
   `atexit` path still covering normal exits. Task T8 will fail, which is the
   intended loud signal.
2. **Full revert:** `git revert` the merge commit and redeploy. Nothing
   persists across the change — no state file, no queue on disk, no record
   shape difference — so a reverted runner image is byte-equivalent in
   behaviour to the pre-change one.
3. **Symptoms that should trigger a rollback:** runner pods sitting in
   `Terminating` for longer than the grace period; a runner whose exit status
   changed from signalled to a normal code (breaking an Argo or Temporal
   classification); or any log line from the `usage-ledger-sigterm` thread
   that correlates with a hung run rather than a terminated one.
