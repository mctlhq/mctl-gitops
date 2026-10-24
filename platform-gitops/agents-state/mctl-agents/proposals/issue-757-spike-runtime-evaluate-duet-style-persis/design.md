# Design: issue-757-spike-runtime-evaluate-duet-style-persis

## Current state

What exists in this repository today, read in the clone at `8b89458`:

- **Policy checkpoint (authorization).** `orchestrator/policy_checkpoint.py` (ADR `docs/adr/014-policy-checkpoint.md`) is the single decision point before a side effect: `ActionRequest -> decide() -> ALLOW | DENY | REQUIRE_APPROVAL`. It is stdlib-only, fails closed, and emits one `POLICY_DECISION` record per decision. This answers "is this action permitted", not "should the user be interrupted". The issue forbids changes here.
- **Exact-action approvals.** `orchestrator/action_approvals.py` mirrors mctl-api's `actionapproval/v1` (`ID_PREFIX = "aar_"`, `intent_hash()` byte-compatible with mctl-api `workitems.IntentHash`, single-use consume). `orchestrator/approval_evidence.py` already has `GRANT_REF_RE = re.compile(r"aar_[A-Za-z0-9_-]{1,124}")`. `orchestrator/decision_records.py` already treats `approval_ref` as a pointer. An attention decision can reuse that regex, so it only points at an existing `aar_` record.
- **Durable watch (Temporal).** In `orchestrator/temporal/workflows/dev_loop.py`, `DevLoopWorkflow` parks on approval with `wait_condition`. After implement it runs a merge watch that polls `orchestrator/temporal/activities/pr_state.py` every `MERGE_POLL_INTERVAL = 15 min`. That module's header says it uses "polling, not a webhook", so it has no event ingress. History is bounded with `continue_as_new` at `MERGE_WATCH_HISTORY_FLOOR = 4096` and `MERGE_WATCH_MAX_HOPS = 16`. This is run- and work-item-scoped continuity. A wake is a timer, and no attention decision exists.
- **Gated merge.** `MERGE_GATE_ACTIVITY = "merge_pull_request_gated"` (ADR 016) is the existing consequential action behind policy plus approval. It is the action that a `REQUIRE_APPROVAL` attention decision for "ready to merge" would point a human at, without invoking it.
- **WorkItem / context.** `orchestrator/work_context/contract.py` mirrors mctl-api `workitem/v1` (ADR 011), with closed vocabularies and `from_payload` refusing unknown shapes. `context_snapshot.py` (ADR 009) holds immutable snapshots. These hold durable, work-item-scoped context. No session-scoped state exists.
- **Lifecycle ownership.** `orchestrator/lifecycle/` (ADR 010) records who owns a PR phase. `policy.py` names mctl-claude-remote's pr-steward as the owner of some repos. This matters for D8: the attention prototype must not create a third PR owner.
- **Spike conventions.** `docs/spikes/746-portable-runtime.md` and `docs/spikes/746/measurements/` set the shape of the report and the evidence directory. `docs/spikes/707/` keeps runnable code under `docs/spikes/<n>/`. `tests/test_sdd_capabilities_661.py` shows how a spike's artifacts under `docs/spikes/661/` are exercised from the default test collection. `pyproject.toml` sets `testpaths = ["tests"]` and pins `PyYAML==6.0.3`, so YAML rules need no new dependency.
- **No `mctl.events` code in this repo.** A grep for `mctl.events|mctl_events` finds nothing in `orchestrator/`. The envelope lives only in mctlhq/mctl-claude-remote `events/mctl_events/envelope.py`, which is not in this clone.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` `services/labs/claude-remote/values.yaml`:
  - Image tag `0.14.1`.
  - `MCTL_EVENTS_ENABLED: "true"`, using Valkey `valkey.platform-events.svc.cluster.local:6379` and policy file `/etc/mctl-events/policy.json`.
  - The `mctl-events-policy` ConfigMap holds a deny-by-default route list:
    - `mctl:events:telegram`: `telegram.message.created|edited` for one account;
    - `mctl:events:github`: source `mctl-api`, types `github.pull_request.*` and `github.pull_request_review.submitted`, subject `repository: mctlhq/*`.
  - `max_inflight: 5`.
  - `pr-steward-config` has `merge_mode: "never"`.
  - Conclusion: GitHub PR events already reach the claude-remote session natively, through events not polling. No check-run or check-suite type is routed.
- The `services/labs/claude-remote/` directory listing shows the service lives in tenant `labs`.
- mctl MCP tools were not called. The gitops checkout answered the deployed-config questions, and the spike makes no runtime claim beyond them.
- Not observed: the source of `envelope.py` and `channel.py` in mctlhq/mctl-claude-remote (another repository, not cloned), mctl-telegram 0.93.0 behavior (#760 slice 2), and the #712 event producer. These are recorded under Open questions in requirements.md. The implementer must read them on their default branches and cite SHAs.

## Proposed solution

Add fixture-only artifacts under `docs/spikes/757/`, one thin test collector under `tests/`, and the report. No orchestrator, workflow, or deployed config changes.

### Layout

```text
docs/spikes/757/
  README.md                  # how to run; source commit of the copied envelope shape
  attention.py               # AttentionDecision v1 + decide() + decide_wake_cycle(); stdlib + PyYAML
  envelope_v1.py             # cited copy of the mctl.events/v1 closed shape + validate()
  rules/github_pr.yaml       # deterministic attention rules
  fixtures/*.json            # envelopes: unchanged, ci_failed, ready_to_merge, burst_a, burst_b, oversize, unknown_key
  test_attention.py          # D-C scenarios + per-rule mutation tests
tests/test_spike_757_attention.py   # loads docs/spikes/757/test_attention.py by path so CI collects it
docs/spikes/757-duet-sessions.md    # D-D report
```

`attention.py` is loaded by file path (`importlib.util.spec_from_file_location`), not added to the `orchestrator` package. This keeps the prototype out of the runtime import graph, matching "no runtime wiring".

### D-A: `AttentionDecision v1`

A frozen dataclass with `SCHEMA = "attentiondecision/v1"`:

| Field | Type | Notes |
|---|---|---|
| `decision_id` | str | `atd_` + first 24 hex of sha256 over (`subject_ref`, sorted `coalesced_event_ids`, `observed_state_digest`, `rule_id`). Deterministic, so a replayed wake cycle gives the same id. This is the idempotency key for the race path. |
| `subject_ref` | str | Event id, or the correlation id when coalesced. |
| `session_or_workitem_ref` | str | Opaque reference, for example the watched resource key `github:pr:mctlhq/x#123` or a `wi_` id. It is never a session object. |
| `decision` | closed enum | `IGNORE`, `CONTINUE`, `NOTIFY`, `REQUIRE_APPROVAL`. |
| `basis` | closed enum | `rule`, `model`. |
| `rule_id` | str | Matching rule, or `unmatched` when basis is model. |
| `observed_state_digest` | str | `sha256:` over the canonical JSON of the state-bearing reference fields. |
| `coalesced_event_ids` | tuple[str, ...] | Sorted and unique. |
| `approval_ref` | str or None | Must match `aar_[A-Za-z0-9_-]{1,124}`, the same pattern as `approval_evidence.GRANT_REF_RE` (copied, with a test asserting the two strings are equal). |
| `decided_at` | str | RFC 3339, taken from an injected clock, so `decide()` stays pure. |

The vocabulary uses `CONTINUE`, as the activation text names it. The report explains that this is the issue body's `CONTINUE_AUTONOMOUSLY`. `REQUIRE_APPROVAL` means "surface to a human who may then use the existing approval path". It is not the policy checkpoint verdict with the same name, and the report states that difference explicitly (attention, authorization and approval are three separate things).

### D-B: `decide()`

```python
def decide(envelope, last_observed_digest, rules, *, classifier=None, clock=None, approval_ref=None) -> AttentionDecision
```

Steps:
1. `envelope_v1.validate(envelope)` checks the closed key set, the required keys and `len(canonical_json) <= 4096`. A failure raises `EnvelopeRefused`, which is never `IGNORE` (invariant 9).
2. Compute the digest from reference fields only: type, subject, and the revision or state ref the envelope carries. Payload text is never read as instructions, and free text is not hashed into rule matching (invariant 4).
3. If the digest equals `last_observed_digest`, return `IGNORE` with `basis=rule` and `rule_id=no_state_change`. The classifier is not touched.
4. Otherwise apply the YAML rules in file order, first match wins. Matching uses only the event type plus typed fields of the subject or state ref.
5. If no rule matched and a `classifier` was injected, call it once with the validated envelope, then validate and return its decision as `basis=model`. A classifier answer outside the closed enum is refused. With no classifier, return `NOTIFY` with `basis=model` and `rule_id=unmatched`.

`decide_wake_cycle(envelopes, last_observed_digests, rules, ...)` does the following:
- deduplicates by event id;
- groups by watched-resource key;
- calls `decide()` per envelope;
- folds each group to one decision by severity `REQUIRE_APPROVAL > NOTIFY > CONTINUE > IGNORE`, with ties broken by rule order;
- sets `coalesced_event_ids` to every non-refused envelope in the group, and `observed_state_digest` to the digest of the last event in canonical order.

Because the output depends only on the set of inputs, two concurrent wakeups that see the same events produce the same `decision_id`. A consumer that writes it idempotently cannot double-notify. That is the race-path evidence available without a session store.

`rules/github_pr.yaml`, sketch only. Field names are fixed against the copied envelope:

```yaml
version: 1
rules:
  - id: ci_failed
    match: {type: "github.pull_request.*", state.checks: failure}
    decision: NOTIFY
  - id: ready_to_merge
    match: {type: "github.pull_request.*", state.mergeable: clean, state.checks: success}
    decision: REQUIRE_APPROVAL
  - id: review_comment_p1
    match: {type: github.pull_request_review.submitted, state.max_severity: P1}
    decision: NOTIFY
  - id: review_comment_p3
    match: {type: github.pull_request_review.submitted, state.max_severity: P3}
    decision: CONTINUE
```

`no_state_change` is implicit in step 3 but is also listed as a rule in the YAML, so removing it is observable. If the real envelope carries no CI or mergeability state, the fixture adds a typed `observed` sidecar that stands in for the re-observation `channel.py` must do. The report records this as a gap. See Open questions in requirements.md.

### D-C: tests

Four scenario tests, plus a mutation test per rule: load the rules, drop the rule by id, re-run the scenario, and assert the outcome changes. The mutation tests make each scenario provably red without its rule. A `CountingClassifier` fake records calls.

### D-D: report

`docs/spikes/757-duet-sessions.md` follows the 746 structure: Environment, current-state map (Q1, re-verified with SHAs across mctl-agents, mctl-claude-remote, mctl-api and mctl-telegram), then Q2 to Q10. Measurements are each tagged measured, fixture, or not-measured. Examples:
- LLM calls avoided: the count of fixture events decided with `basis=rule`;
- notifications before and after coalescing: N events vs 1 decision;
- durable state size: one digest per watched resource;
- event-to-wake latency: not measurable in a fixture, so it is stated as such.

The report then has the D8 table, which checks #712, #703, #197, .github#181/#182, #746 and #760 before proposing any follow-up, and ends with exactly one verdict token. The proposal does not pre-select it. The evidence above is expected to bear on whether a typed `AttentionDecision` composed over the existing claude-remote Channel, the DevLoop and approvals is enough, which would point to `NO_NEW_CONTRACT` or `EXTEND_DEVLOOP_SESSION` rather than a new session contract or epic. The report must argue from its measurements. The proposed follow-up is wiring `decide()` into mctl-claude-remote `channel.py`, filed in that repository and not done here.

## Alternatives

1. **Put the contract in `orchestrator/` (for example `orchestrator/attention.py`) now.** Dropped: the activation says fixtures first and no runtime wiring. A module in the runtime package invites premature adoption, and its first consumer is in a different repository (claude-remote `channel.py`).
2. **Extend `policy_checkpoint.Decision` with attention outcomes.** Dropped: it violates "attention is not authorization", and the activation forbids changes to `policy_checkpoint`.
3. **Prototype as a Temporal workflow with signals (a session per PR).** Dropped for this run: it builds the session and execution machinery owned by #760 and the issue's non-goals, and cannot be tested purely. The report evaluates it on paper under Q7, using the existing merge watch's `continue_as_new` bounds as the measured reference.
4. **Import the envelope from mctl-claude-remote.** Dropped: the activation forbids cross-repo imports. A cited copy plus a validation test is enough for a spike.

## Platform impact

- No migrations, no deployed change, no new dependency (PyYAML is already pinned). The `orchestrator/` package and Temporal workers are untouched, and worker images are unaffected apart from the doc files.
- CI cost: a few hundred milliseconds of extra pytest.
- Risk: the copied envelope drifts from the producer. Mitigation: `README.md` and the report cite the source commit, and the follow-up wiring issue must re-validate the fixtures against the producer's own tests.
- Risk: readers mistake `REQUIRE_APPROVAL` (attention) for the checkpoint verdict. Mitigation: the docstring and report state that `approval_ref` is pointer-only, and a test asserts that the module imports no approval client.
- Risk: fixture `observed` sidecars hide a real gap. Mitigation: the report lists it as an explicit D8 gap and does not claim it is solved.
