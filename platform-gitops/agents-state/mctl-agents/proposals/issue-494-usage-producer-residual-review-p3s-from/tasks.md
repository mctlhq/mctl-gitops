# Tasks: issue-494-usage-producer-residual-review-p3s-from

- [ ] 1. Add `_utc_now_iso()` to `orchestrator/usage_ledger.py` and capture the
      timestamp on the calling thread: in `UsageRecorder.observe`, after the
      `ResultMessage` and `enabled` checks and before `self._submit(...)`, bind
      `observed_at = _utc_now_iso()` and submit
      `lambda: self._record(message, observed_at)` — DoD: no `datetime.now`
      call remains on the delivery thread's path except the `_plan` fallback;
      `observe` still returns without doing any work beyond the queue put.
- [ ] 2. Thread the timestamp through (depends on 1): `_record(self, message,
      recorded_at: str)` passes it to `_plan(self, message, recorded_at: str |
      None = None)`, which uses `recorded_at or _utc_now_iso()` for the
      `"recorded_at"` key of `common` — DoD: the literal
      `datetime.now(UTC).isoformat()` no longer appears inline in `_plan`'s
      `common` dict; `mypy` clean.
- [ ] 3. Add `trace_ids(traceparent)` and `current_trace_ids()` to
      `orchestrator/tracing.py`, beside `current_traceparent`, returning the
      `(trace_id, span_id)` hex pair via `_TRACEPARENT_RE` after a
      `valid_traceparent` check, or `None` — DoD: both return `None` with
      tracing off, for a malformed value, and for all-zero ids; neither raises;
      no new top-level import (the module stays stdlib-only at import time).
- [ ] 4. Move recorder construction in `tracing.agent_run` from `__init__` into
      `__enter__` behind a `_build_recorder()` helper (depends on 3):
      `__init__` sets `self._usage = None` and
      `self._observer = _NoopObserver(None)`; `__enter__` builds the recorder
      after `self._span_cm.__enter__()` when tracing is on and before returning
      the no-op observer when it is off, passing
      `trace_id=`/`span_id=` from `current_trace_ids()` through
      `UsageRecorder.from_env(self._agent, **correlation)` — DoD: the existing
      `_warn_once("usage", ...)` guard and the deferred `usage_ledger` import
      both move with the call; `run_implementer.py:2371`,
      `run_issue_investigator.py:1654` and `run_shepherd.py:2127` are unchanged.
- [ ] 5. Move `self._usage.observe(message)` inside `AgentRunObserver.observe`'s
      existing `try`, still ahead of the `if not self._root.recording: return`
      check — DoD: the whole body of `observe` is inside one `try`/`except
      Exception` that `_warn_once("observe", ...)`s and returns; the
      "never raises" comment is replaced by one stating the guarantee is now
      structural.
- [ ] 6. Delete `UsageRecorder.records_for` from
      `orchestrator/usage_ledger.py` — DoD: no references remain anywhere
      (`grep -rn records_for` is empty except the changelog/ADR if mentioned);
      `_seen` and `_baseline` are read and written only from `_record`'s call
      chain.
- [ ] 7. Rewrite `test_correlation_comes_from_the_runner_pod_environment`
      (depends on 6) to monkeypatch `usage_ledger._default_post` with a
      `FakeApi`, build the recorder with `from_env` and the same env dict,
      `observe` one result, `assert usage_ledger.flush(5)`, and assert
      `agent`, `temporal_workflow_id`, `argo_workflow_name`, `work_item_id` and
      `rec._token` on the delivered record — DoD: the test no longer calls any
      plan-only helper and still passes with no real HTTP request.
- [ ] 8. Amend `docs/adr/012-model-usage-cost-attribution-contract.md`
      ("Amendment 2026-09-24 — the producer") with two paragraphs (depends on
      1-5): `recorded_at` is turn time, captured before the job is queued and
      unaffected by retries, distinct from mctl-api's ingest time, and names the
      turn that carried a possibly-forwarded delta; and the record carries the
      W3C `trace_id`/`span_id` of the `invoke_agent` span, omitted entirely when
      tracing is off, and distinct from `orchestrator/execution_identity.py`'s
      same-named field — DoD: no other ADR section is edited, no field is added
      to the record list (both already exist there).
- [ ] 9. Refresh the docstrings that describe the changed behaviour (depends on
      1-6): the `usage_ledger` module docstring's "Off the event loop"
      paragraph gains one sentence on turn-time stamping; `UsageRecorder.observe`
      says it captures the observation time; `agent_run`'s class docstring says
      the recorder is built when the span opens, so it can carry the trace ids
      — DoD: no docstring still claims a purity or threading property the code
      does not have.
- [ ] 10. Run the full gate (depends on 1-9): `uv run pytest tests/`,
      `uv run ruff check orchestrator config tests`, `uv run mypy` — DoD: all
      three green, with no test skipped or xfailed to get there.

## Tests

All in `tests/test_usage_ledger.py` unless stated. Messages stay the real
`claude_agent_sdk.ResultMessage`, as the module's docstring requires.

- [ ] T1. `test_recorded_at_is_the_turn_time_not_the_delivery_time`: build a
      recorder with the real `_WORKER` submit and a `post` that blocks on a
      `threading.Event` for ~1 s (the `test_observe_returns_at_once_while_delivery_is_slow`
      pattern), capture `before`/`after` wall-clock around `observe`, release,
      `flush(5)`, and assert the delivered `recorded_at` parses (as an aware
      UTC datetime) into `[before, after]` — i.e. strictly before the POST ran.
- [ ] T2. `test_a_retried_batch_keeps_the_timestamp_of_its_turn`:
      `FakeApi(503)` so one retry happens with a counted `sleep`; assert both
      request bodies carry the identical `recorded_at`, extending the existing
      `test_a_redelivered_batch_is_byte_for_byte_the_same_identity` key set.
- [ ] T3. `test_recorded_at_stays_an_iso_utc_z_timestamp`: format
      non-regression — `datetime.fromisoformat` round-trips it and the string
      ends with `Z` (keeps the existing line 132 assertion honest).
- [ ] T4. `test_the_trace_and_span_ids_of_the_run_reach_the_record` (in
      `tests/test_usage_ledger.py`, using the `exported`-style tracing fixture
      from `tests/test_tracing_agents.py`): with tracing on, drive
      `_run_investigator_agent`, flush, and assert the record's `trace_id` /
      `span_id` equal the exported `invoke_agent issue-investigator` span's
      `trace_id` / `span_id` formatted as 32- and 16-digit lowercase hex.
- [ ] T5. `test_no_trace_ids_are_sent_when_tracing_is_off`: the existing
      `ledger` fixture already asserts `tracing.enabled() is False`; assert
      `"trace_id" not in record and "span_id" not in record` — absent, never
      empty or zero (ADR-012 "absent versus zero").
- [ ] T6. `test_current_trace_ids_rejects_malformed_and_zero_traceparents` (in
      `tests/test_tracing.py`): parametrised over `None`, `""`,
      `"not-a-traceparent"`, an all-zero trace id and an all-zero span id;
      `trace_ids` returns `None` for each and raises for none.
- [ ] T7. `test_a_usage_recorder_that_raises_on_observe_does_not_break_the_stream`
      (in `tests/test_tracing_agents.py`): replace the observer's `_usage` with
      an object whose `observe` raises, drive a full stream with tracing ON and
      again with tracing OFF, and assert neither raises, the `invoke_agent`
      span is still exported in the ON case, and exactly one
      "could not trace an SDK message" warning is logged. This is the
      regression test for the `try` placement.
- [ ] T8. `test_every_sdk_message_still_reaches_the_recorder_with_tracing_off`:
      assert the recorder sees the result through `_NoopObserver` (the
      recorder call must stay ahead of the `recording` check) — the existing
      `test_each_sdk_driver_records_its_usage_with_tracing_off` covers this;
      confirm it still passes unchanged rather than adding a duplicate.
- [ ] T9. Structural check that no public method of `UsageRecorder` claims
      purity: assert `not hasattr(usage_ledger.UsageRecorder, "records_for")`,
      so a future revert of the deletion is caught by a test rather than by a
      reviewer.
- [ ] T10. Re-run the whole `tests/test_usage_ledger.py` and
      `tests/test_tracing_agents.py` suites unchanged otherwise: deltas,
      dedupe, "may have landed" stickiness, https-only, the `atexit`
      subprocess test, the options-scrubbing AST test, and the shepherd path
      must all pass untouched.

## Rollback

Every change is additive or local, in three files plus one ADR, with no state
outside the process and no schema version bump.

1. **Full revert.** `git revert <merge commit>` restores
   `orchestrator/usage_ledger.py`, `orchestrator/tracing.py`,
   `tests/test_usage_ledger.py` and the ADR. Nothing persists between runs: an
   agent pod builds its recorder fresh, so the next run is on the reverted
   behaviour with no cleanup. Records already stored keep their `trace_id` /
   `span_id`; because both fields are nullable in ADR-012's schema v1, a mix of
   rows with and without them is a valid ledger.
2. **Partial rollback, change 2 only** (the likely case, if mctl-api turns out
   to reject the new fields): delete the `trace_id`/`span_id` keys from
   `_build_recorder`'s `correlation` dict — one line — or revert task 4 alone.
   Tasks 1, 3, 5, 6 and 7 are independent of it and can stay.
3. **No kill switch is added.** Recording is already fail-soft: an HTTP error
   answer is not retried past `ATTEMPTS`, every failure is logged with a
   running undelivered count, `_record` swallows everything, and unsetting
   `MCTL_USAGE_WRITER_TOKEN` in the CWFT disables the producer entirely
   without a code change. Adding a second switch for a P3 batch would be more
   surface than the change itself.
4. **Signal that a rollback is needed:** repeated
   `usage records not delivered (HTTP 4...` warnings in an agent pod's logs
   immediately after the deploy, or a rising "N record(s) undelivered so far in
   this process" count where there was none before.
