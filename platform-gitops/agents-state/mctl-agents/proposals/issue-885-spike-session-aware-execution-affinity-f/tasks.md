# Tasks: issue-885-spike-session-aware-execution-affinity-f

- [ ] 1. Write the current-state map in `docs/spikes/885-execution-affinity.md`. For DevLoop
  (workflow id, run id, `wi_`/`we_`, `aar_`, Argo workflow name, lifecycle row) and for the #757
  attention path (watched-resource key, digest), give identity -> durable state -> routing (task
  queue, sticky cache, Argo pod), citing `orchestrator/temporal/worker.py`, `constants.py`,
  `workflows/dev_loop.py`, `activities/argo.py` and `docs/spikes/757/attention.py`. DoD: every row
  names its file or contract owner. Rows that could not be observed are marked `unknown`.
- [ ] 2. List the implicit same-executor dependencies (`_blob_cache`, implementation admission
  per-process slot limit, usage ledger `_WORKER` queue, Temporal sticky cache, claude-remote pod-local
  transcript), each with an owner and an expected verdict. Depends on 1. DoD: the list is in the
  report, and each item is linked to the fixture scenario that tests it or marked out of scope with a
  reason.
- [ ] 3. Build the two-executor fixture under `docs/spikes/885/`: two Temporal `Worker`s, A and B,
  each with its own `identity` and `max_cached_workflows=0`, built from `tests/temporal_harness.py`
  plans. Fake activities append (scenario, worker identity, attempt, heartbeat_details) to a trace.
  Depends on 1. DoD: a smoke run shows that both identities execute steps of one workflow id.
- [ ] 4. Implement DevLoop scenarios D1 (`submit_and_wait` heartbeat resume on the other worker), D2
  (approve signal after the last worker is stopped) and D3 (merge-watch `continue_as_new` plus a
  duplicate resume request), each with a single-worker baseline. Depends on 3. DoD: each scenario
  emits a JSON line with `result` pass/fail/unknown, the submit count and a field diff against its
  baseline.
- [ ] 5. Implement S1 (`decide_wake_cycle`, shared versus per-instance digest store) and probes P1
  (cold `_blob_cache`), P2 (hard kill before `usage_ledger.flush`) and P3 (two implement workers at
  N=3, recording admissions). Depends on 3. DoD: JSON lines are recorded, and P3 changes no
  production code or values.
- [ ] 6. Add `docs/spikes/885/collect.py` (stdlib only, run with `python -I`) and the collector
  `tests/test_spike_885_affinity.py`, following the `tests/test_spike_757_attention.py` pattern.
  Depends on 4, 5. DoD: `uv run pytest tests/test_spike_885_affinity.py -q` passes and writes a
  scorecard in which a missing record counts as `unknown`.
- [ ] 7. Only if a scenario fails: re-run it with the smallest binding keyed on `execution_id` or the
  workflow id, and document key, owner, TTL (lifetime of the execution), cleanup at a terminal state,
  failover (rebuilt from durable state) and integration point. Depends on 6. DoD: the gap disappears
  with the binding, or the report explains why durable state is the cleaner fix.
- [ ] 8. Write the measurements, the operational cost comparison and exactly one outcome
  (`NO_AFFINITY_NEEDED` | `ADD_EXECUTION_AFFINITY_KEY` | `ADD_SESSION_ROUTING_BINDING`) in the
  report, and file follow-up issues only for proven gaps (for example a P2 loss, or P3 linked to
  mctl-api#337). Depends on 6 (and 7 if run). DoD: one outcome is stated. The PR uses `Refs #885`,
  not `Closes`, because this is a spike and the owner records the verdict.

## Tests

- [ ] T1. Every D1-D3 scenario completes on two workers with results identical to its single-worker
  baseline. D1 shows exactly one submit.
- [ ] T2. Every scenario's trace contains both worker identities. If it does not, the scenario is
  reported `unknown`, and the test asserts that it is not reported `pass`.
- [ ] T3. S1 with a shared digest store gives the same decisions on either instance. The
  per-instance-store variant is recorded as the negative control.
- [ ] T4. The fixture makes no network calls: real Argo, GitHub, mctl-api and model clients are
  monkeypatched to raise if called.
- [ ] T5. `git diff --stat` of the spike PR touches only `docs/spikes/885*` and
  `tests/test_spike_885_affinity.py`.

## Rollback

Research-only. Revert the spike PR, which deletes `docs/spikes/885*` and
`tests/test_spike_885_affinity.py`. Nothing deployed or configured changes. Follow-up issues stay
open or are closed independently.
