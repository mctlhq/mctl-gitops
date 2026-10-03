# Design: issue-493-usage-producer-flush-queued-usage-record

## Current state

**The producer.** `orchestrator/usage_ledger.py` holds one process-wide
`_Worker` (`orchestrator/usage_ledger.py:138`) with a `queue.Queue` and one
lazily started daemon thread named `usage-ledger`.
`UsageRecorder.observe` (`orchestrator/usage_ledger.py:253`) is called from
inside the drivers' async message loops, so it only calls `self._submit(...)`
and returns; planning, the `POST /api/v1/usage/records` and the baseline
commit all happen on that thread, in order
(`_record`/`_plan`/`_deliver`/`_commit`, lines 271-400). The module docstring
states the reason: a blocking POST on the loop would push back every anyio
deadline the drivers rely on (`fail_after`, the mctl-agents#366 drain).

**The one exit path today.** `flush(timeout)`
(`orchestrator/usage_ledger.py:177`) waits on
`_Worker.flush` (line 163), which blocks on `queue.all_tasks_done` until
`unfinished_tasks` reaches zero or `FLUSH_TIMEOUT_SECONDS` (25.0, line 79)
elapses, warning on timeout. It is registered exactly once, at import, with
`atexit.register(flush)` (line 189). `tests/test_usage_ledger.py:409`
(`test_a_runner_that_exits_right_after_its_last_turn_still_delivers_it`)
proves that path end to end by running a real subprocess that observes one
`ResultMessage` and exits immediately.

**Who records.** The recorder is built in `tracing.agent_run.__init__`
(`orchestrator/tracing.py:1016`), so usage is produced by exactly the three
call sites that open an `agent_run`:

| Driver | `agent_run` site | Process entrypoint |
|---|---|---|
| implementer | `orchestrator/run_implementer.py:2371` | `_traced_main()` at `orchestrator/run_implementer.py:4926`, called only from `__main__` (line 4937) |
| investigator | `orchestrator/run_issue_investigator.py:1654` | `_traced_main()` at `orchestrator/run_issue_investigator.py:3220`, called only from `__main__` (line 3231) |
| shepherd | `orchestrator/run_shepherd.py:2127` | `main()` at `orchestrator/run_shepherd.py:3736`, called from `__main__` (line 3982) **and directly from `tests/test_run_shepherd.py` (9 call sites)** |

`orchestrator/run_mentor.py`, `orchestrator/run_service_agent.py`,
`orchestrator/run_incident_responder.py` and `orchestrator/run_all.py` run
models but never open an `agent_run`, so they queue nothing — consistent with
the ADR-012 invocation inventory
(`docs/adr/012-model-usage-cost-attribution-contract.md`).

**Signals.** `grep -rn "signal\." --include=*.py orchestrator/` finds signal
handling in exactly one module: `orchestrator/temporal/worker.py:791`, where
`run_until_signalled` calls `loop.add_signal_handler(sig, shutdown.set)` for
SIGINT and SIGTERM to get ADR-008's graceful drain. That process never builds
a `UsageRecorder`. Every other orchestrator process leaves SIGTERM at
`SIG_DFL`: the kernel ends the process, `atexit` hooks do not run, and the
queued batch dies with it.

**Signal reachability.** `entrypoint.sh` ends in `exec "$@"`, so the runner
replaces the shell and is the container's PID 1; the pod's SIGTERM is
delivered to the Python process itself, with no shell in between. The hook
therefore actually fires in production, not just in tests.

**Established local pattern for bounded teardown.**
`orchestrator/tracing_sdk.py:365` (`bounded_shutdown`) already does the shape
this design needs: run the flush on a daemon thread, `join(timeout)`, and if
it is still alive, log once and give up rather than let a pod sit in
Terminating because a collector stopped answering.

## Proposed solution

### 1. A new opt-in hook in `orchestrator/usage_ledger.py`

Add one public function and one constant next to the existing `flush`:

```python
SIGTERM_FLUSH_TIMEOUT_SECONDS = 15.0

def install_sigterm_flush(timeout: float = SIGTERM_FLUSH_TIMEOUT_SECONDS) -> bool:
    """Deliver queued usage records on SIGTERM, then die as SIGTERM means."""
```

`install_sigterm_flush` returns `True` when it installed a handler and
`False` (with a debug/info line, never an exception) when it declined.
It declines in three cases, each a real condition in this repo:

- **Not the main thread.** `signal.signal` raises `ValueError` off the main
  thread. `threading.current_thread() is not threading.main_thread()` -> skip.
- **SIGTERM is already handled.** `signal.getsignal(signal.SIGTERM)` is not
  `SIG_DFL` -> skip. This is the guard that protects
  `orchestrator/temporal/worker.py:791`: a usage flush must never displace
  ADR-008's drain, whatever import order a future refactor produces.
- **Already installed.** A module-level flag makes a second call a no-op, so
  a driver that grows a second entrypoint cannot stack handlers.

The handler itself:

```python
def _on_sigterm(signum, frame):
    if _flushing_already():          # a second SIGTERM: stop waiting
        _die_by_sigterm()
    logger.warning("SIGTERM: flushing queued usage records (up to %.0fs)", timeout)
    try:
        worker = threading.Thread(target=flush, args=(timeout,),
                                  name="usage-ledger-sigterm", daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            logger.warning("usage ledger: SIGTERM flush did not finish in %.0fs", timeout)
    except Exception:                # noqa: BLE001 — must never change how a run ends
        logger.warning("usage ledger: SIGTERM flush failed", exc_info=False)
    _die_by_sigterm()

def _die_by_sigterm():
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.raise_signal(signal.SIGTERM)
```

Three properties are deliberate:

- **The wait runs on a helper thread, joined with a bound.** Not because the
  flush is slow, but because a signal handler runs on the main thread at an
  arbitrary bytecode boundary — possibly inside `observe`'s `queue.put`,
  which holds the very `queue.mutex` that `_Worker.flush` waits on. Waiting
  inline there would self-deadlock on a non-reentrant lock. With the wait on
  another thread and a bounded `join`, the pathological case costs `timeout`
  seconds and a log line instead of a wedged pod. This is the same reasoning,
  and the same shape, as `tracing_sdk.bounded_shutdown`.
- **`raise_signal` after restoring `SIG_DFL`, never `sys.exit`.** The process
  must end exactly as it would have without the handler: killed by signal
  (`WIFSIGNALED`, shell status 143), which is what Argo and Temporal read.
  `sys.exit(143)` would instead raise `SystemExit` in the main thread and
  unwind every live `finally` and `__aexit__` — including, inside the anyio
  loop, `tracing.agent_run.__aexit__` — spending the grace period on git
  pushes, GitHub comments and lifecycle releases, which is the opposite of
  what a terminated pod should do and is adjacent to the loop stall #491
  removed. It would also skip the `_die_by_sigterm` guarantee that a second
  SIGTERM kills instantly.
- **The `atexit` registration stays.** It is what covers normal exit and
  SIGINT/KeyboardInterrupt (which unwinds normally). After
  `raise_signal(SIGTERM)` under `SIG_DFL` the `atexit` hooks do not run, and
  they do not need to: the queue was just drained, or the timeout was logged.

### 2. Installing it at the three process entrypoints

- `orchestrator/run_implementer.py:4926` — first statement of `_traced_main()`.
- `orchestrator/run_issue_investigator.py:3220` — first statement of `_traced_main()`.
- `orchestrator/run_shepherd.py:3982` — in the `if __name__ == "__main__":`
  block, **before** `main()`. Not inside `main()`: nine tests in
  `tests/test_run_shepherd.py` call `run_shepherd.main()` directly, and a
  unit test must not leave a SIGTERM handler installed in the pytest process.
  The other two drivers' `_traced_main` has no non-`__main__` caller, which
  is why the call can sit inside it there.

The rule is therefore uniform and statable: *the function that
`if __name__ == "__main__"` calls, at the point where nothing has started
yet, installs the process's usage signal policy.* Signal policy belongs to
the process, not to a library that happens to be imported.

### 3. Keeping the rule from rotting

Mirroring `tests/test_usage_ledger.py:445`
(`test_every_options_builder_goes_through_the_scrubbing_constructor`), add a
structural AST test: every `orchestrator/run_*.py` that contains a
`tracing.agent_run(...)` call must also contain a call to
`usage_ledger.install_sigterm_flush(...)`. A fourth driver that starts
recording usage then cannot silently ship without the hook.

### 4. Documentation

Amend the "Off the event loop" paragraph of the `usage_ledger` module
docstring (`orchestrator/usage_ledger.py:40-46`) and the matching sentence in
`docs/adr/012-model-usage-cost-attribution-contract.md:352`, both of which
currently say only that `atexit` flushes the queue.

## Alternatives

**A. Flush in `agent_run.__exit__` / `__aexit__`.** Rejected, and explicitly
ruled out by the issue. The implementer and the investigator enter
`agent_run` with `async with`
(`orchestrator/run_implementer.py:2371`,
`orchestrator/run_issue_investigator.py:1654`), so `__aexit__` runs *on the
event loop*. A blocking `flush()` there reintroduces exactly the loop stall
#491 removed, and it would not even solve this issue: SIGTERM at `SIG_DFL`
kills the process without running `__aexit__` at all.

**B. Let the handler `sys.exit(128 + SIGTERM)` and keep one flush path in
`atexit`.** Tempting — one flush path, and it would flush traces too. Dropped
for the reasons above: it unwinds arbitrary driver cleanup inside the
grace period, it converts a signalled death into a normal exit that Argo and
Temporal classify differently, and it makes termination time depend on
whatever `finally` blocks happen to be live. This is worth reconsidering only
as part of a separate, deliberate "graceful runner shutdown" design that also
owns `tracing.shutdown`.

**C. Auto-install at `usage_ledger` import time.** Zero per-driver edits,
which is attractive. Dropped: `usage_ledger` is imported lazily from
`tracing.agent_run.__init__` (`orchestrator/tracing.py:1016`), i.e. from
inside a run and potentially off the main thread, where `signal.signal`
raises; and in any process that also runs the Temporal worker it would be a
race against `loop.add_signal_handler` at
`orchestrator/temporal/worker.py:791` whose loser is either the usage flush
or ADR-008's drain. The `getsignal`/main-thread guards are kept anyway as
defence in depth, but the decision to install stays at the entrypoint.

**D. Make the delivery thread non-daemon, or spool undelivered records to
disk.** Non-daemon does nothing under SIGTERM (the interpreter never reaches
its thread join) and would hang ordinary exits. Disk spooling needs a sweeper
and a retention story, which is far more machinery than "bookkeeping, never
fatal" justifies, and a dead pod's local spool is unreadable anyway.

## Platform impact

- **Migrations:** none. No schema, no `SCHEMA_VERSION` bump, no mctl-api
  change; the ingest contract and its idempotency key are untouched.
- **Backward compatibility:** additive. A process that does not call
  `install_sigterm_flush` behaves exactly as today. The Temporal worker is
  doubly protected: it never builds a recorder, and the `getsignal` guard
  would decline anyway.
- **Resource impact:** one short-lived daemon thread per SIGTERM, plus at
  most `SIGTERM_FLUSH_TIMEOUT_SECONDS` of extra pod-termination time on a
  terminated runner only. Steady-state cost is zero.
- **Risks and mitigations:**
  - *Termination takes longer.* Bounded by the timeout, chosen below the
    assumed 30 s `terminationGracePeriodSeconds`; if a CWFT sets less,
    SIGKILL truncates and we are no worse than today. Both the start of the
    flush and the timeout are logged.
  - *Signal-handler reentrancy on `queue.mutex`.* Mitigated by the helper
    thread plus bounded `join`; worst case is a skipped flush and a warning,
    never a hang.
  - *An impatient operator sends a second SIGTERM.* The handler's first act
    is to detect that a flush is already running and die immediately.
  - *A handler bug changes how a run ends.* Every branch is wrapped and falls
    through to `_die_by_sigterm`, keeping the module's "never fatal" rule.
  - *Records still lost past the timeout.* Accepted and unchanged in kind;
    the difference is that it is now logged instead of silent.
