# Usage producer: flush queued usage records on SIGTERM

## Context

`orchestrator/usage_ledger.py` is the model-usage producer added for
mctlhq/.github#50 / ADR-012. `UsageRecorder.observe` never blocks the
drivers' anyio loops: it only puts a job on a `queue.Queue` that one daemon
thread (`_Worker`, `orchestrator/usage_ledger.py:138`) drains, delivering
each batch to `POST /api/v1/usage/records`. Whatever is still queued when
the interpreter shuts down is delivered by `flush()`, registered with
`atexit` at `orchestrator/usage_ledger.py:189`.

`atexit` hooks do not run when the process is killed by SIGTERM, and SIGTERM
is exactly how a runner pod is stopped: an Argo `activeDeadlineSeconds`
expiry, a Temporal workflow terminate, a node drain. Nothing in the three
model-running drivers — `orchestrator/run_implementer.py`,
`orchestrator/run_issue_investigator.py`, `orchestrator/run_shepherd.py` —
installs a SIGTERM handler (only `orchestrator/temporal/worker.py:791` does,
for the worker process), so SIGTERM hits Python's default and ends the
process at once. A batch queued or in flight at that moment is lost, and no
log line says so. The window is small, because the worker drains
continuously from the first result, and losing bookkeeping is by design
never fatal — but a killed run is precisely the run whose cost an operator
wants to see, and today it is the one run that silently reports nothing.

## User stories

- AS a platform operator I WANT the usage records of a runner pod that was
  terminated (deadline, node drain, workflow terminate) to still reach
  mctl-api SO THAT the cost of a killed run is attributable instead of
  silently missing from the ledger.
- AS an operator reading an Argo log I WANT a line saying that usage records
  were flushed on SIGTERM, or that the flush ran out of time, SO THAT a gap
  in the ledger is explainable rather than a mystery.
- AS an mctl-agents maintainer I WANT the SIGTERM flush to live at the
  drivers' process entrypoint, not inside `tracing.agent_run`, SO THAT no
  blocking work is reintroduced on the anyio event loop that #491 cleared.
- AS a Temporal worker operator I WANT the usage producer never to replace
  the worker's own graceful-drain SIGTERM handler SO THAT ADR-008's drain
  behaviour is unchanged.

## Acceptance criteria (EARS)

- WHEN a runner process whose entrypoint installed the usage SIGTERM hook
  receives SIGTERM with usage records queued or in flight, THE SYSTEM SHALL
  wait for the delivery thread to finish those records, bounded by a
  configured timeout, before the process terminates.
- WHEN that SIGTERM flush starts, THE SYSTEM SHALL emit one log line naming
  SIGTERM and the bound it will wait for.
- IF the SIGTERM flush does not finish within its timeout, THEN THE SYSTEM
  SHALL log a warning that queued usage records were not delivered and
  terminate anyway.
- WHEN the SIGTERM flush has finished or timed out, THE SYSTEM SHALL restore
  SIGTERM's default disposition and re-raise SIGTERM, so the process ends
  with the conventional killed-by-SIGTERM wait status rather than a normal
  exit.
- IF SIGTERM already has a handler installed when the hook is requested
  (the Temporal worker's `loop.add_signal_handler` in
  `orchestrator/temporal/worker.py:791`), THEN THE SYSTEM SHALL decline to
  install, leave the existing handler in place, and report that it declined.
- IF the hook is requested from a thread other than the main thread, THEN
  THE SYSTEM SHALL decline to install rather than raise, because
  `signal.signal` is main-thread only.
- WHEN the hook is requested more than once in one process, THE SYSTEM SHALL
  install at most one handler and treat later requests as a no-op.
- IF a second SIGTERM arrives while a SIGTERM flush is already running, THEN
  THE SYSTEM SHALL stop waiting and terminate immediately.
- WHILE no SIGTERM has been received, THE SYSTEM SHALL leave
  `UsageRecorder.observe`, the delivery thread, the delivery/retry semantics
  and the delta baseline exactly as they are today.
- WHEN a process exits normally or on KeyboardInterrupt/SIGINT, THE SYSTEM
  SHALL still deliver queued records through the existing `atexit` hook,
  unchanged.
- WHEN the SIGTERM flush runs, THE SYSTEM SHALL NOT execute it on the anyio
  event loop, and SHALL NOT unwind the drivers' `finally` blocks,
  `agent_run.__exit__` or `agent_run.__aexit__` to get there.
- IF anything inside the SIGTERM handler raises, THEN THE SYSTEM SHALL
  swallow it and still terminate by re-raising the default SIGTERM, because
  recording is bookkeeping and must never change how a run ends.

## Out of scope

- Any change to `tracing.agent_run.__enter__/__exit__/__aenter__/__aexit__`
  (`orchestrator/tracing.py:994`). The issue rules this out explicitly.
- Durable on-disk spooling of undelivered usage records for a later sweep.
- Changing the ingest contract, the record schema, `SCHEMA_VERSION`, the
  retry policy (`ATTEMPTS`, `REQUEST_TIMEOUT_SECONDS`,
  `RETRY_DELAY_SECONDS`) or the delta/baseline semantics.
- Flushing OpenTelemetry spans on SIGTERM. `orchestrator/tracing_sdk.py:360`
  registers `tracing.shutdown` with `atexit` and has the identical blind
  spot, but it is a separate subsystem and a separate issue.
- Extending usage recording to the drivers that do not record today
  (`run_mentor.py`, `run_service_agent.py`, `run_incident_responder.py` —
  see the ADR-012 invocation inventory).
- Changing pod `terminationGracePeriodSeconds` or any Argo CWFT, which live
  in `mctl-gitops`, not in this repo.

## Open questions

- The exact `terminationGracePeriodSeconds` of the runner pods is set by the
  Argo CWFTs in `mctl-gitops` and is not readable from this clone. The
  proposal assumes the Kubernetes default of 30 s and therefore picks a
  SIGTERM flush bound comfortably below it rather than reusing the 25 s
  `FLUSH_TIMEOUT_SECONDS` that the `atexit` path uses. If a CWFT sets a
  shorter grace period, SIGKILL simply cuts the flush short and the
  behaviour is no worse than today.
- SIGHUP and SIGQUIT are not handled. No caller in this repo sends them to a
  runner; the proposal keeps the surface to SIGTERM only.
- Whether `docs/adr/012-model-usage-cost-attribution-contract.md:352`
  ("An `atexit` hook flushes what is still queued") should be amended in the
  same PR. The proposal assumes yes, as a documentation-only amendment.
