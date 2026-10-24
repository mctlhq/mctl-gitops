# Tasks: issue-757-spike-runtime-evaluate-duet-style-persis

- [ ] 1. Read mctlhq/mctl-claude-remote `events/mctl_events/envelope.py` and `channel.py` on the default branch, and record the commit SHA. Write `docs/spikes/757/envelope_v1.py` as a cited copy of the closed `mctl.events/v1` shape (key set, required keys, 4096-byte limit) with a `validate()` that raises `EnvelopeRefused`. Do not import across repositories. — DoD: the module header cites repo, path and SHA, and validation rejects unknown keys, missing keys and oversize envelopes.
- [ ] 2. (depends on 1) Write `docs/spikes/757/attention.py` with the frozen `AttentionDecision` (`attentiondecision/v1`), closed `decision` and `basis` enums, the `aar_` pattern equal to `orchestrator/approval_evidence.py` `GRANT_REF_RE`, and the deterministic `decision_id`. — DoD: invalid enum values or a non-`aar_` `approval_ref` raise, and there is no I/O or approval-client import.
- [ ] 3. (depends on 2) Implement pure `decide(envelope, last_observed_digest, rules, *, observed=None, classifier=None, clock=None, approval_ref=None)` (see requirements.md amendments A1-A3) and `decide_wake_cycle(...)` as described in design.md: digest-first IGNORE, first-match YAML rules, classifier only on unmatched input, NOTIFY/`unmatched` fallback, dedupe by event id, and per-resource severity fold. — DoD: identical inputs give identical output, including `decision_id`.
- [ ] 4. (depends on 1) Write `docs/spikes/757/rules/github_pr.yaml` with `no_state_change`, `ci_failed`, `ready_to_merge`, `review_comment_p1` and `review_comment_p3`, and fixtures under `docs/spikes/757/fixtures/` using only event types routed today (`github.pull_request.*`, `github.pull_request_review.submitted`). If state is not in the envelope, add a typed `observed` sidecar. — DoD: every fixture passes `validate()` except the deliberate refusal fixtures.
- [ ] 5. (depends on 3, 4) Write `docs/spikes/757/test_attention.py` and the collector `tests/test_spike_757_attention.py`, which loads the former by path. — DoD: `uv run pytest` (default testpaths) runs and passes all T-tests below.
- [ ] 6. (depends on 5) Write `docs/spikes/757/README.md` (how to run, source SHA, what is fixture-only). — DoD: a reader can reproduce the measurements with one command.
- [ ] 7. (depends on 5) Write `docs/spikes/757-duet-sessions.md`. It needs:
  - Q1 to Q10, with the shared current-state map from the issue comments re-verified on default branches (SHAs cited);
  - measurements, each tagged measured, fixture or not-measured;
  - the D8 ownership map, checking #712, #703, #197, .github#181/#182, #746 and #760;
  - the `channel.py` wiring as a proposed follow-up only;
  - exactly one final verdict token.
  
  DoD: the verdict is one of the four tokens and appears exactly once in the Decision section.
- [ ] 8. (depends on 7) Open the PR with commits using `Refs #757` (never `Closes`). — DoD: the PR touches only `docs/spikes/757*`, `docs/spikes/757-duet-sessions.md` and `tests/test_spike_757_attention.py`.

## Tests

- [ ] T1. Unchanged digest: the fixture decided with `last_observed_digest` equal to its own digest gives `IGNORE`, `basis=rule`, `rule_id=no_state_change`, and `CountingClassifier.calls == 0`.
- [ ] T2. CI failure: gives `NOTIFY` with `rule_id=ci_failed`.
- [ ] T3. Ready to merge: with `approval_ref="aar_fixture_0001"` gives `REQUIRE_APPROVAL`, and `approval_ref` is echoed unchanged.
- [ ] T4. Coalescing: two envelopes for the same PR in one `decide_wake_cycle` call give exactly one decision with `decision == NOTIFY` and both event ids in `coalesced_event_ids`.
- [ ] T5. Mutation: for each of T1 to T4, re-running with the relied-on rule removed changes the outcome (each test is red without its rule).
- [ ] T6. Duplicate and race: the same event twice, and the same two events in reversed order, give the same single decision and the same `decision_id`.
- [ ] T7. Refusals: an envelope with an unknown key, a missing required key, or more than 4096 bytes raises `EnvelopeRefused`, and none of these yields `IGNORE`.
- [ ] T8. Authority separation: a non-`aar_` `approval_ref` is rejected, the `aar_` pattern string equals `approval_evidence.GRANT_REF_RE.pattern`, and `attention.py` imports neither `orchestrator.action_approvals` nor `orchestrator.policy_checkpoint`, nor any network module.
- [ ] T10. (amendment A1/A2) Same PR and same `head_sha`, `checks` pending -> failure: different `observed_state_digest`, decision `NOTIFY` with `rule_id=ci_failed`, never `IGNORE`. `observed=None` or any `unknown` field never yields `no_state_change`.
- [ ] T11. (amendment A3) With `no_state_change` removed from the loaded rules, the unchanged-digest fixture does not yield `IGNORE`/`no_state_change` (the mutation proof for T1).
- [ ] T9. Unmatched input: with no classifier the result is `NOTIFY`, `basis=model`, `rule_id=unmatched`. With a classifier it is called exactly once, and an out-of-enum answer is refused.

## Rollback

Everything is additive documentation, fixtures and tests, and nothing is imported by `orchestrator/` or deployed. To roll back, revert the PR (or delete `docs/spikes/757/`, `docs/spikes/757-duet-sessions.md` and `tests/test_spike_757_attention.py`). No runtime, gitops or data state needs to change.
