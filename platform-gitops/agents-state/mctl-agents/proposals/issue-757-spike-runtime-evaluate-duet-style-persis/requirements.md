# Spike #757: AttentionDecision v1 contract, fixture-only decide() prototype, and Duet-sessions evidence report

## Context

Issue mctlhq/mctl-agents#757 is a spike. It asks whether MCTL needs a first-class persistent
proactive agent session with attention routing, measured against Anthropic's Claude Duet. The
owner activated it on 2026-10-24 (SpikeDefinition `roadmap/spikes/duet-sessions.yaml` in
mctlhq/.github, `decisionBy: 2026-11-30`) and narrowed this run to four deliverables. All four are
fixtures first, with no runtime wiring:
D-A, the `AttentionDecision v1` contract. D-B, a pure `decide()` prototype under `docs/spikes/757/`
that consumes the real `mctl.events/v1` envelope shape from mctlhq/mctl-claude-remote. D-C,
fixture tests that each fail when their rule is removed. D-D, the evidence report
`docs/spikes/757-duet-sessions.md`, which ends with exactly one verdict and the D8 ownership map.

This matters because MCTL already has most of the primitives involved, spread across several places:
- the Temporal DevLoop merge watch and approval park (`orchestrator/temporal/workflows/dev_loop.py`);
- exact-action approvals (`orchestrator/action_approvals.py`, `aar_` ids);
- the policy checkpoint (`orchestrator/policy_checkpoint.py`, ADR 014);
- WorkItems (`orchestrator/work_context/`, ADR 011);
- the claude-remote inbound events Channel, already deployed with a deny-by-default route policy for `github.pull_request.*` events.

What is missing is one auditable decision that separates attention ("interrupt the user? keep
working?") from authorization and approval. The spike has to prove or disprove that this decision
is the smallest new contract, without building a session store or a second workflow engine.

## User stories

- AS the #757 spike owner I WANT a typed `AttentionDecision v1` contract and a deterministic prototype SO THAT I can record a verdict from measured evidence, not from Duet's product shape.
- AS an operator of the claude-remote session I WANT unchanged-state and duplicate GitHub PR events to be filtered before any model call SO THAT I am not interrupted and no model budget is spent on non-events.
- AS a reviewer of governance I WANT every attention decision to carry at most a pointer to an existing `aar_` approval record SO THAT attention can never grant or write approval state.
- AS the implementer of the follow-up channel wiring I WANT the envelope fixtures to be a cited copy of the real `mctl.events/v1` shape SO THAT the prototype's assumptions can be checked against the producer at a known commit.

## Acceptance criteria (EARS)

Contract (D-A)
- THE SYSTEM SHALL define `AttentionDecision v1` with exactly these fields: `decision_id`, `subject_ref`, `session_or_workitem_ref`, `decision`, `basis`, `rule_id`, `observed_state_digest`, `coalesced_event_ids` (list), optional `approval_ref`, and `decided_at`, plus a `schema` label `attentiondecision/v1`.
- THE SYSTEM SHALL restrict `decision` to the closed set `IGNORE | CONTINUE | NOTIFY | REQUIRE_APPROVAL` and `basis` to the closed set `rule | model`. IF either value is outside its set THEN constructing or parsing the decision SHALL raise a typed error and not fall back to a default.
- IF `approval_ref` is present THEN THE SYSTEM SHALL accept it only when it matches the `aar_` id pattern already used by `orchestrator/approval_evidence.py` (`GRANT_REF_RE`), and it SHALL be a reference only.
- THE SYSTEM SHALL NOT expose any code path in `docs/spikes/757/` that creates, decides, consumes or writes an approval (no import of `orchestrator.action_approvals` client routes, no network I/O).

Prototype (D-B)
- THE SYSTEM SHALL provide a pure function `decide(envelope, last_observed_digest, rules) -> AttentionDecision`. It performs no I/O, reads no clock or randomness except through injected parameters, and gives the same output for the same input.
- WHEN an envelope does not validate against the copied `mctl.events/v1` shape (unknown key, missing required key, or serialized size over 4096 bytes) THE SYSTEM SHALL refuse it with a typed error and SHALL NOT produce `IGNORE`.
- WHEN the envelope's computed `observed_state_digest` equals `last_observed_digest` THE SYSTEM SHALL return `IGNORE` with `basis=rule` and `rule_id` of the no-change rule, without invoking the model classifier.
- WHEN no YAML rule matches an envelope THE SYSTEM SHALL return `basis=model` only by calling the injected classifier. IF no classifier is injected THEN it SHALL return `NOTIFY` with `basis=model` and a sentinel `rule_id` (unknown is surfaced, never treated as nothing changed).
- WHEN a wake cycle contains several envelopes for the same watched resource THE SYSTEM SHALL, via `decide_wake_cycle(envelopes, last_observed_digests, rules)`, emit at most one decision per resource. That decision's `coalesced_event_ids` lists every contributing event id in a deterministic order, and its `decision` is the highest-severity one by the order `REQUIRE_APPROVAL > NOTIFY > CONTINUE > IGNORE`.
- WHEN the same event id appears twice in one wake cycle THE SYSTEM SHALL count it once.
- THE SYSTEM SHALL read rules from a YAML file under `docs/spikes/757/` covering GitHub PR events, with at least the rules `no_state_change`, `ci_failed`, `ready_to_merge`, `review_comment_p1` and `review_comment_p3`.

Fixtures and tests (D-C)
- WHEN the fixture with an unchanged digest is decided THE SYSTEM SHALL produce `IGNORE` and the classifier call counter SHALL be 0.
- WHEN the CI-failure fixture is decided THE SYSTEM SHALL produce `NOTIFY` with `rule_id=ci_failed`.
- WHEN the ready-to-merge fixture is decided with a fake `aar_` reference THE SYSTEM SHALL produce `REQUIRE_APPROVAL` whose `approval_ref` equals that reference.
- WHEN two fixture events for the same watched PR arrive in one wake cycle THE SYSTEM SHALL produce exactly one `NOTIFY`.
- IF the rule a test depends on is removed from the loaded rule set THEN that test's assertion SHALL fail (proven by a mutation test per rule that runs the scenario without the rule and asserts the outcome differs).
- THE SYSTEM SHALL run these tests in the repository's default `pytest` collection (`testpaths = ["tests"]`) so CI runs them.

Report (D-D)
- THE SYSTEM SHALL add `docs/spikes/757-duet-sessions.md`. It answers Q1 to Q10 from the issue, re-verifies the shared current-state map on default branches with the commit SHA of each source read, records the measurements the issue lists (marking each as measured, fixture-only, or not measurable in this run), and contains the D8 ownership map.
- THE SYSTEM SHALL end the report with exactly one verdict token from `NO_NEW_CONTRACT | EXTEND_DEVLOOP_SESSION | ADD_AGENT_SESSION_CONTRACT | CREATE_PROACTIVE_AGENT_EPIC`.
- THE SYSTEM SHALL list wiring `decide()` into mctl-claude-remote `channel.py` as a proposed follow-up only.
- WHILE this spike is open, every commit for it SHALL reference `Refs #757` and never `Closes #757`.

## Out of scope

- A session store, an execution pool, session isolation, or Telegram coalescing (owned by #760).
- Any change to `orchestrator/policy_checkpoint.py` or `orchestrator/action_approvals.py`.
- Any change to the Telegram conversation plane or to mctl-telegram.
- Notification delivery (#712).
- Wiring into mctl-claude-remote `channel.py`, the Valkey route policy, or any deployed config.
- Any production change, GitHub mutation, or new Temporal workflow.
- Cross-repository imports: the envelope shape is copied, not imported.

## Open questions

- The exact `mctl.events/v1` field set lives in mctlhq/mctl-claude-remote `events/mctl_events/envelope.py`, which is not in this clone. The fixture shape must be copied from that file at a cited commit during implementation. If it differs from the field names assumed in design.md (for example, how the subject or a revision/state reference is carried), the fixtures follow the source.
- The envelope is reference-only, so it may carry no CI conclusion or mergeability. The prototype then derives `observed_state_digest` and the rule match from reference fields only (event type, subject, head revision/state ref). If those are insufficient to tell "CI failed" from "CI passed", the fixture adds a typed `observed` sidecar standing in for the re-observation `channel.py` would do, and the report records this as a gap that the follow-up must fill.
- The current deployed route policy (`mctl-events-policy` in `services/labs/claude-remote/values.yaml`) admits only `github.pull_request.*` and `github.pull_request_review.submitted` from source `mctl-api`. The fixtures should use these types. Check runs and check suites may not be routed today, and the report should state this.
- Whether "two events in one wake cycle" is bounded by a time window or by one Channel delivery batch is not specified. This proposal treats a wake cycle as the batch passed to `decide_wake_cycle`, and leaves the window as a follow-up parameter.
