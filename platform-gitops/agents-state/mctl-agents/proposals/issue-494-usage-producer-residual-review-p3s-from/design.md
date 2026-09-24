# Design: issue-494-usage-producer-residual-review-p3s-from

## Current state

Three files carry all of this, plus one ADR.

**`orchestrator/usage_ledger.py`** (401 lines) is the producer. Structure as it
stands on `fd7004b`:

- `_Worker` (line 138) is one daemon thread per process. `submit` starts it
  lazily and puts a `Callable[[], None]` on an unbounded `queue.Queue`; `_run`
  drains it in order; `flush` (line 163) waits on `all_tasks_done` and is
  registered with `atexit` at line 189.
- `UsageRecorder.__init__` (line 195) holds `_seen: set[tuple[str, str]]`,
  `_baseline: dict[tuple[str, str], dict[str, int]]` and `_warned: set[str]`.
  The module docstring's "Off the event loop" section states the invariant
  that matters here: the delivery thread "is the only writer of a recorder's
  state".
- `UsageRecorder.from_env` (line 228) reads `MCTL_USAGE_WRITER_TOKEN`,
  `MCTL_API_BASE_URL` and the three `WORKFLOW_*` correlation variables
  (`_CORRELATION_ENV`, line 108), then merges `**correlation` over them. The
  constructor drops any correlation value that is `None` or `""` (line 216), so
  an absent field is omitted from the record rather than written empty — the
  ADR-012 "absent versus zero" rule.
- `observe` (line 253) is called from the drivers' async loops. It filters on
  `type(message).__name__ != "ResultMessage"`, warns once when recording is
  off, and otherwise does exactly one thing: `self._submit(lambda:
  self._record(message))`.
- `_record` (line 271) runs on the delivery thread: `_plan` -> `_deliver` ->
  `_commit`, all inside one `try` that swallows and warns once.
- `_plan` (line 293) builds the `common` dict, and line 313 is the finding:

  ```python
  "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
  ```

  `_plan` runs on the delivery thread, so this timestamp is delivery time. The
  gap is normally milliseconds; with `ATTEMPTS = 2`, `REQUEST_TIMEOUT_SECONDS
  = 5.0` and `RETRY_DELAY_SECONDS = 1.0` (lines 76-78) a queue that is behind
  one retrying batch stamps the next message up to ~11 s late, and an
  arbitrarily long queue is arbitrarily late.
- `records_for` (line 279) is documented "Pure: it neither delivers nor marks
  anything as handled." It calls `_plan`, which can call `_warn_once` (the
  "not-cumulative" branch, line 343) and therefore mutate `_warned`, and which
  reads `_seen` (line 304) and `_baseline` (line 335). Its only caller is
  `tests/test_usage_ledger.py:165` in
  `test_correlation_comes_from_the_runner_pod_environment`.

**`orchestrator/tracing.py`**:

- `AgentRunObserver.observe` (line 845):

  ```python
  def observe(self, message: Any) -> None:
      if self._usage is not None:
          self._usage.observe(message)  # never raises
      if not self._root.recording:
          return
      try:
          ...
      except Exception as exc:
          _warn_once("observe", ...)
  ```

  The recorder call sits outside the `try`. The comment is accurate today
  because `UsageRecorder.observe` guards its own submit, but the guarantee is
  borrowed from another module rather than held here. Rule 2 of the module
  docstring ("A trace can never fail an execution") is what this weakens.
- `agent_run.__init__` (line 1007) builds the recorder:

  ```python
  from orchestrator import usage_ledger
  self._usage = usage_ledger.UsageRecorder.from_env(agent)
  ```

  with no `**correlation`, so `trace_id` / `span_id` are never sent. At
  `__init__` time there is no span yet: the `invoke_agent` span is started in
  `__enter__` (line 1034, `self._span_cm = span(...)`, then
  `self._span_cm.__enter__()`), and `span()` attaches it as current (line 402),
  which is exactly what `current_traceparent()` (line 476) reads.
- `current_traceparent` returns the full `00-<32hex>-<16hex>-<flags>` string,
  or `None` when tracing is off / there is no recording span. `_TRACEPARENT_RE`
  (line 73) already captures the two ids, and `valid_traceparent` (line 465)
  already rejects all-zero ids; nothing exposes the split pair today.
- `_NoopObserver` (line 987) is `AgentRunObserver(NOOP, None, usage)`: with
  tracing off the usage recorder is still fed through the inherited `observe`.

**`docs/adr/012-model-usage-cost-attribution-contract.md`**: the record section
lists `trace_id / span_id` as nullable (line 152) and the correlation contract
says "Issue/PR/work-item and `trace_id`/`span_id` are carried directly because
they are per-invocation rather than per-execution" (line 195). `recorded_at`
appears in the field list (line 175) with no stated meaning. The
"Amendment 2026-09-24 — the producer" section (line 309) is where the producer's
own semantics are written down.

**`tests/test_usage_ledger.py`** (521 lines) pins the shape: `_recorder()`
(line 97) injects `submit=lambda job: job()` so jobs run inline;
`test_one_record_per_model_posted_with_the_usage_writer_token_only` asserts
`recorded_at` only ends with `Z` (line 132); the driver-level tests at the end
(`ledger` fixture, line 449) monkeypatch `usage_ledger._default_post` and call
`usage_ledger.flush(5)`, which is the pattern the rewritten correlation test
will use.

## Proposed solution

Four changes, two production files plus the ADR and the test module. Each is
small and independently revertible.

### 1. `recorded_at` is captured at observation time

Add a module-level helper and thread the value through:

```python
def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
```

- `UsageRecorder.observe`: capture `observed_at = _utc_now_iso()` after the
  `ResultMessage` / `enabled` checks and before `self._submit(...)`, then
  submit `lambda: self._record(message, observed_at)`. The call is one
  `datetime.now` on the caller's thread — the same cost class as the
  `type(message).__name__` check already there, and far below the queue put.
- `_record(self, message, recorded_at: str)` passes it to
  `_plan(message, recorded_at)`.
- `_plan(self, message, recorded_at: str | None = None)` uses
  `recorded_at or _utc_now_iso()`. The default keeps `_plan` callable without a
  timestamp; with `records_for` removed (change 4) the only caller is
  `_record`, so the default is a safety net, not an API.

Semantics, to be written into the ADR amendment: `recorded_at` is **when the
producer observed the turn in the agent process**, not when the batch was
delivered or stored. Two consequences to state explicitly there: mctl-api's own
ingest time is a separate, server-side fact; and because an undelivered batch
is carried into the next turn's delta (the #491 "certainly not stored"
behaviour), a record's tokens can include usage first observed one turn
earlier, while `recorded_at` is the timestamp of the turn that actually carried
them. That is the correct reading of a delta record and is worth one sentence
so a consumer does not treat it as a bug.

### 2. `trace_id` / `span_id` reach the record

Add to `orchestrator/tracing.py`, next to `current_traceparent`:

```python
def trace_ids(traceparent: str | None) -> tuple[str, str] | None:
    """The (trace_id, span_id) hex pair of a W3C traceparent, or None."""
    if not valid_traceparent(traceparent):
        return None
    match = _TRACEPARENT_RE.match((traceparent or "").strip())
    return (match.group(1), match.group(2)) if match else None


def current_trace_ids() -> tuple[str, str] | None:
    """The (trace_id, span_id) of the current span, or None when there is none."""
    return trace_ids(current_traceparent())
```

`valid_traceparent` already rejects malformed and all-zero values, so the
"omit rather than send zeros" criterion is satisfied by construction, and
`current_traceparent` already returns `None` with tracing off and logs its own
failures once.

Then move recorder construction from `agent_run.__init__` into
`agent_run.__enter__`, which is the first moment the span exists:

```python
class agent_run:
    def __init__(self, agent: str, model: str | None) -> None:
        self._agent, self._model = agent, model
        self._span_cm: Any = None
        self._usage: Any = None
        self._observer: AgentRunObserver = _NoopObserver(None)

    def _build_recorder(self) -> Any:
        # Deferred import: usage_ledger imports httpx, this module stays
        # stdlib-only at import time. Guarded: rule 2.
        try:
            from orchestrator import usage_ledger

            ids = current_trace_ids()
            correlation = {"trace_id": ids[0], "span_id": ids[1]} if ids else {}
            return usage_ledger.UsageRecorder.from_env(self._agent, **correlation)
        except Exception as exc:  # noqa: BLE001
            _warn_once("usage", "usage recording unavailable for this run (%s)", type(exc).__name__)
            return None

    def __enter__(self) -> AgentRunObserver:
        if not _state.enabled:
            self._usage = self._build_recorder()      # no ids: tracing is off
            self._observer = _NoopObserver(self._usage)
            return self._observer
        attributes = {...}                            # unchanged
        self._span_cm = span(f"invoke_agent {self._agent}", attributes, kind="client")
        handle = self._span_cm.__enter__()
        self._usage = self._build_recorder()          # the invoke_agent span is current here
        self._observer = AgentRunObserver(handle, self._model, self._usage)
        return self._observer
```

Why `__enter__` and not `__init__`: the issue's own prescription ("pass the
pair through the `**correlation` kwargs of `UsageRecorder.from_env`") requires
the pair to be known at construction, and it is only known once `span()` has
attached the `invoke_agent` span to the context. `from_env` merges
`**correlation` over the environment-derived fields, and the constructor drops
`None`/`""`, so with tracing off the two keys simply do not appear — no new
branch needed in `usage_ledger.py` at all. Every existing call site
(`run_implementer.py:2371`, `run_issue_investigator.py:1654`,
`run_shepherd.py:2127`) uses `agent_run` as a context manager, sync or async,
so nothing observes the recorder before `__enter__`; `__init__` keeping
`_observer = _NoopObserver(None)` preserves a safe value for an un-entered
instance.

The `span_id` sent is the `invoke_agent` span's. That is the span whose
children are the `chat <model>` spans a record's tokens came from, so a
consumer can pivot from a row to the run; per-turn `chat` span ids are out of
scope (see Alternatives).

### 3. The recorder call moves inside the observer's own `try`

```python
def observe(self, message: Any) -> None:
    try:
        if self._usage is not None:
            self._usage.observe(message)
        if not self._root.recording:
            return
        kind = type(message).__name__
        ...
    except Exception as exc:  # noqa: BLE001
        _warn_once("observe", "could not trace an SDK message (%s)", type(exc).__name__)
```

Ahead of the `recording` check, as the issue requires, so a run with tracing
off still records usage through `_NoopObserver`'s inherited `observe`. The
guarantee stops depending on `UsageRecorder.observe`'s internals and becomes a
property of this method. The existing `_warn_once("observe", ...)` key is
reused: one line per process for a repeated failure, whichever of the two
sources it comes from.

### 4. `records_for` is removed

Delete `UsageRecorder.records_for` and rewrite
`test_correlation_comes_from_the_runner_pod_environment` to read the record
that was actually queued, delivered and captured — the pattern the driver
tests in the same file already use:

```python
def test_correlation_comes_from_the_runner_pod_environment(monkeypatch):
    env = {...}                                  # unchanged
    api = FakeApi()
    monkeypatch.setattr(usage_ledger, "_default_post", api)
    rec = usage_ledger.UsageRecorder.from_env("issue-investigator", env)
    rec.observe(_result("u1", {OPUS: _usage(1, 2)}))
    assert usage_ledger.flush(5)
    (record,) = api.records
    assert record["agent"] == "investigator"
    ...
```

`from_env` with this env yields the default `https://api.mctl.ai` base URL and
the real `_default_post`, which the monkeypatch replaces, so nothing leaves the
process. This is the stronger of the two options the issue offers (narrowing
the docstring is the other): it deletes the cross-thread read instead of
documenting it, and it makes the test assert the delivered record rather than a
plan the delivery path might diverge from. After the deletion, `_seen` and
`_baseline` have exactly one reader and one writer again — the delivery thread
— which is what the module docstring already claims.

### 5. ADR-012 amendment

Extend the "Amendment 2026-09-24 — the producer" section with:

- **`recorded_at` is turn time.** Captured in `UsageRecorder.observe` on the
  driver's thread before the job is queued, so queue delay and delivery
  retries cannot shift it. mctl-api's ingest time is a separate server-side
  fact. A delta record's tokens may include usage first observed one turn
  earlier when a batch was carried forward; `recorded_at` names the turn that
  carried them.
- **Trace correlation.** The record carries `trace_id` and `span_id` from the
  W3C traceparent of the `invoke_agent` span, taken when `tracing.agent_run`
  opens. Both are omitted when tracing is off or no recording span exists —
  never written as empty or zero ids. These are the OTel ids, not
  `orchestrator/execution_identity.py`'s same-named execution-identity field.

## Alternatives

1. **Keep building the recorder in `agent_run.__init__` and push the ids in
   afterwards** with a small `UsageRecorder.correlate(**correlation)` mutator
   called from `__enter__`. Dropped: it adds a second writer to recorder state
   (even if only before the first `observe`), which is exactly the class of
   fuzziness P3 #4 asks to remove, and the issue explicitly prescribes the
   `from_env(**correlation)` path. Deferring construction by a few statements
   costs nothing — no call site touches the recorder before `__enter__`.

2. **Send the raw `traceparent` string as one field** instead of a split pair.
   Simpler producer-side, and it preserves the sampled flag. Dropped: ADR-012's
   record names `trace_id` and `span_id` as separate nullable fields and the
   OTel mapping table joins on them; a consumer would have to parse the string
   to do any join, and mctl-api would have to learn a field the contract does
   not define.

3. **Use the per-turn `chat <model>` span id** rather than the run's
   `invoke_agent` span id, for a tighter join. Dropped: the chat span exists
   only inside `AgentRunObserver._assistant`, there is one per model message
   (not one per record), and it is already closed by the time the
   `ResultMessage` arrives (`_result` ends every open chat). Wiring that would
   mean per-message correlation plumbed through the observer into
   `UsageRecorder.observe` — a much larger change than a P3 warrants, and the
   run-level span already answers "which execution spent this".

4. **Narrow the `records_for` docstring** to "for inspection off the hot path"
   and keep the method (the issue's first option). Dropped in favour of
   deletion: the method has exactly one caller, that caller can assert
   something strictly better (the delivered record), and a documented
   thread-safety caveat is weaker than not having the hazard.

5. **Stamp `recorded_at` in `observe` but keep `_plan`'s signature** by storing
   the timestamp on the recorder (e.g. `self._pending_at`). Dropped: that is
   shared mutable state between the driver thread and the delivery thread for
   no benefit; a closure argument is the natural carrier and is already how the
   message itself travels.

## Platform impact

**Migrations.** None in this repo. Two new nullable fields appear on records
sent to `POST /api/v1/usage/records`; ADR-012 already defines them as part of
schema v1, so `schema_version` does not change.

**Backward compatibility.**

- Consumers reading `recorded_at` see the same format (`...Z`) with a more
  accurate value. No consumer exists in this repo today (the only references to
  the producer outside `orchestrator/` are its tests and the ADR).
- `records_for` is removed from `UsageRecorder`'s public surface. Its only
  caller is one test in this repo; nothing in `orchestrator/` or `tools/` uses
  it, so no external contract breaks.
- `agent_run`'s constructor no longer builds the recorder. Behaviour at every
  call site is unchanged because all three enter the context manager
  immediately. `test_a_recorder_that_cannot_be_built_never_fails_the_run`
  monkeypatches `UsageRecorder.from_env` to raise and drives the real
  investigator; it keeps passing because the guard moves with the call.

**Resource impact.** One extra `datetime.now(UTC)` per `ResultMessage` on the
driver thread (nanosecond-scale next to the existing queue put), one regex
match per `agent_run` entry, and two short strings per record on the wire.
Nothing new is allocated per message.

**Risks and mitigations.**

- *mctl-api rejects the new fields.* If `/api/v1/usage/records` validates
  strictly, batches would come back 4xx. Blast radius is bounded by the
  existing design: a client error is not retried (`_deliver`, line 389), the
  failure is logged with a running undelivered count, and recording is never
  fatal to a run. Mitigation: confirm against the mctl-api usage schema
  (mctl-api#385) before merge; if it does not yet accept them, ship changes
  1, 3 and 4 and hold change 2 behind the ADR follow-up rather than shipping a
  producer whose every batch fails.
- *A leaked secret through a new field.* Not possible here: both values are
  hex ids matched by `_TRACEPARENT_RE`, and `test_a_record_carries_no_cost_no_id_and_no_text`
  keeps asserting no prompt marker appears anywhere in the body.
- *Ordering regression from deferring construction.* Covered by a test that
  asserts a recorded run carries the ids of the `invoke_agent` span actually
  exported, and by the existing "recorder cannot be built" test.
- *`trace_id` name collision* with `orchestrator/execution_identity.py:390`.
  Mitigated by documentation only: the ADR amendment states that the usage
  record's `trace_id` is the OTel/W3C id.
- *Timestamp now reflects a carried-forward delta.* Inherent to delta records,
  not introduced here; documented in the amendment so no consumer reads it as
  a defect.
