# Tasks: issue-306-spike-journey-level-correlation-across-g

- [ ] 1. Pin the evidence. Record the 40-hex commits read for mctlhq/.github, mctl-api,
  mctl-agents, mctl-gitops, mctl-docs and mctl-telegram. Read:
  - mctl-api `internal/workitems/` (WorkItem, intents, executions, snapshots, `IntentHash`)
    and the `MCTL_SUBMIT_CREATES_EXECUTION` handling;
  - mctl-agents DevLoop tracing (`MCTL_TRACE_WORKFLOW_TYPES`, `MCTL_TRACE_ARGO_PARAM`);
  - the mctl-docs#116 attribute catalog;
  - the mctl-telegram#617 request correlation.
  — DoD: a pins table is in the report. Every unread source is marked
  `unknown (not observed)`.
- [ ] 2. Build the D1 identity map (depends on 1). Add one row each for `trace_id`, request
  correlation id, `execution_id`/attempt, Temporal workflow id and run id, `aar_`,
  `intent_hash`/`artifact_hash`/proposal digest, WorkItem intent entry, the mctl-api#701
  decision record and `work_item_id`. Columns: minter, trust, lifetime, cardinality,
  multi-trace, retry/resume/`continue_as_new` behaviour, presence on P1-P5, verdict reason.
  — DoD: no cell is guessed, and every cell carries an evidence tag.
- [ ] 3. Write D2, the lifecycle (depends on 2). Cover the minting event and minter, the
  boundary (delegated objective), retry/resume/amend behaviour, the relation to content
  hashes, and multiple children. Test the WorkItem framing against the counterexamples:
  epic wave, one Telegram request that spawns several issues, P2/P3 paths without a
  WorkItem. — DoD: each counterexample is resolved as "covered by an existing key" or
  "requires a new id", with evidence.
- [ ] 4. Write D3, the propagation matrix (depends on 1). For each boundary from
  ingress/MCP through to durable evidence, state whether the `wi_` is asserted,
  propagated, absent or unknown. Include the deployed value of
  `MCTL_SUBMIT_CREATES_EXECUTION`, or `unknown`. — DoD: every gap names an owning repo.
  Nothing requires private payloads.
- [ ] 5. Write D4, the OTel contract (depends on 2, 4). Cover attribute name and placement
  (root and boundary spans, not resource, no external baggage), catalog owner mctl-docs,
  cardinality, Tempo queryability, interaction with the `mctl.workflow.*`,
  `mctl.execution.*` and `mctl.work_item.*` attributes, and retention. — DoD: the
  durable-record source of truth is stated explicitly.
- [ ] 6. Write D5, the sampling decision (depends on 1). Use the baseline from
  `services/admins/mctl-agents-worker*/values.yaml`. Record ADOPT, DEFER or REJECT for
  coordinated journey sampling, with privacy, cardinality and cost analysis, and with the
  behaviour of debug and incident overrides. — DoD: the cost is bounded (spans added: 0
  unless justified) and one decision is recorded.
- [ ] 7. Write D6 and the worked journey (depends on 2-5). Answer the four operator queries
  as durable joins plus optional trace lookups. Write the `.github#306` journey with at
  least two distinct trace ids and an `aar_` decision between them, every fact labelled
  observed or illustrative. — DoD: no query relies on sampled traces alone.
- [ ] 8. Write the verdict and follow-ups (depends on 3-7). State exactly one of
  `REUSE_WORK_ITEM_ID`, `ADOPT_INTENT_ID`, `NO_CHANGE` as a GO/NO-GO on `mctl.intent.id`.
  List candidate follow-ups with one owner repo each, duplicate-checked against
  mctl-api#285, mctl-agent#97, mctl-agents#195/#196, mctl-telegram#617, mctl-docs#116 and
  mctl-api#701. File none. — DoD: the verdict reason cites the evidence from tasks 2-4.
- [ ] 9. Write `docs/spikes/journey-intent-correlation.md` from tasks 1-8, in the structure
  of `docs/spikes/agent-ui-ag-ui.md`. — DoD: the file exists and contains no secrets,
  tokens, prompts or message bodies.
- [ ] 10. Add `roadmap/spikes/journey-intent-correlation.yaml` with:
  - `SpikeDefinition`, owner `mctlhq/.github`, issue `mctlhq/.github#306`;
  - outcomes `REUSE_WORK_ITEM_ID`, `ADOPT_INTENT_ID`, `NO_CHANGE`;
  - `lifecycle: proposed`, `execution.devloop: true`;
  - `evidence.report: docs/spikes/journey-intent-correlation.md`;
  - no `decision`, and a header comment saying the owner records the decision.

  — DoD: the schema and the semantic validator pass.
- [ ] 11. Add one bullet under `# Spikes` in `AGENTS.md` that links the report for
  mctlhq/.github#306. — DoD: the link resolves.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the
  new manifest.
- [ ] T2. `python -m unittest discover roadmap/tests` passes, including
  `roadmap/tests/test_validate_spike.py` (committed corpus, unique issue bindings).
- [ ] T3. Manual check: the report's verdict is one of the manifest `outcomes`, and the
  manifest has no `decision` block.
- [ ] T4. Manual check: the worked journey shows at least two distinct trace ids under one
  journey key, with an approval/decision boundary between them.
- [ ] T5. Manual check: a grep of the report for bearer strings, `token=`, prompt or
  completion text and Telegram message content finds nothing. Only ids and digests appear.

## Rollback

The change is documentation and one roadmap manifest. Revert the merge commit in
mctlhq/.github. No producer, gitops or data change has to be undone. If the owner rejects
the verdict, edit the manifest lifecycle (`archived`, or `decided` with the owner's
verdict) in a follow-up PR instead of deleting the report.
