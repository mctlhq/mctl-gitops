# Tasks: issue-904-fix-work-context-accept-mcp-resume-surfa

- [ ] 1. Add `"mcp"` to `SURFACE_KINDS` in `orchestrator/work_context/contract.py` and to
  `WORK_CONTEXT_SURFACE_KINDS` in `orchestrator/context_snapshot.py`, with updated
  comments saying `mcp` is a surface label with no client identity. Mirror the change in
  any `orchestrator/execution_evidence.py` copy that T11 asserts. — DoD: the parity test
  `tests/test_context_snapshot.py` (around line 1043) passes unchanged, and
  `tests/test_execution_evidence.py` T11 passes.
- [ ] 2. (depends on 1) Confirm that `DevLoopWorkflow._resume_provenance`, the
  `accept_execution_request` validator and `_validate_work_context_args` accept `mcp`
  with no further edits. Review replay safety (no `workflow.patched` needed, because
  past refusals are recorded events). — DoD: a short note in the PR description, and
  the T2 and T3 tests are green.
- [ ] 3. (depends on 1) In `tests/test_work_context_contract.py`, replace `"mcp"` in
  `test_out_of_vocabulary_origin_surface_is_unknown` with a truly unknown surface, and
  add a `WORK_ITEM_FOUND` test for `origin_surface="mcp"`. — DoD: both tests pass.
- [ ] 4. Make `WorkContextRef.surface_transition` `bool | None`. `to_dict` omits the key
  when it is None, and `from_dict` reads an absent key as None. `_work_context_ref` in
  `orchestrator/run_issue_investigator.py` returns None unless the current surface or
  actor and the baseline are both known. — DoD: existing snapshot fixtures re-serialise
  byte-identical, and a new test shows that unknown provenance never yields `false`.
- [ ] 5. (depends on 1; implements the mctl-agents side of #573) Add `surface`,
  `actor_kind` and `actor_id` to `investigate_params` in
  `orchestrator/temporal/workflows/dev_loop.py` (around lines 3565-3602) for a
  dispatched or resumed execution, from `self._current_surface` and
  `self._current_actor`, omitted when empty like the other params. Keep it replay-safe
  the same way as the `temporal_workflow_id` params (activity input is not compared on
  replay; cite tests/test_workflow_replay.py). Do NOT edit mctl-gitops or mctl-api: the
  CWFT declaration and the mctl-api registry declaration are follow-up PRs (design.md
  Slice B 1a). The PR body says `Refs mctlhq/mctl-agents#573`, not a closing keyword.
  — DoD: T5 and T6 pass in this repository, and T6 fails when the new keys are removed
  from `investigate_params`.
- [ ] 6. Add a typed `ResumeIntentUnavailable` error in `orchestrator/context_assembly.py`,
  raised when the pinned `resume_intent` is `text_redacted` or unreadable. The
  placeholder candidate is never built for the pinned slot. — DoD: no code path renders
  `[text removed by retention]` as a pinned or primary source.
- [ ] 7. (depends on 6) In `orchestrator/run_issue_investigator.py`, catch
  `ResumeIntentUnavailable` and seal an ADR 013 request through `_seal_draft` with a
  fixed, ID-only question and reason, plus a `structured` response that accepts only a
  replacement `intent_id`. Skip the model run. — DoD: `request.json` validates under
  `human_input.HumanInputRequest`, contains no intent text, and the DevLoop parks in
  `WAITING_FOR_INPUT`.
- [ ] 8. (depends on 7) On continuation, read the replacement `intent_id` from mctl-api,
  verify that its work item and principal match, and pin it. Re-park if it is also
  redacted, bounded by `MAX_CLARIFICATION_ROUNDS`. — DoD: the text appears only in the
  sealed snapshot source, never in `request.json`, `answered.json` or `value`.
- [ ] 9. Update `docs/adr/011-work-item-resume-contract.md` and
  `docs/adr/013-human-input-contract.md` (the redacted-intent park, the `mcp` surface,
  and the optional `surface_transition`), plus a rollout-order note in
  `docs/runbooks/`. — DoD: the docs name the order: images, then the gitops CWFT
  parameters, then the mctl-api registry declaration, then admission.
- [ ] 10. In the PR description, list the two follow-ups the implementer does not
  do: the mctl-gitops investigate CWFT parameters and the mctl-api operations-registry
  declaration (design.md Slice B 1a, rollout steps 2-3). — DoD: both are named with
  the exact files.

## Tests

- [ ] T1. Vocabulary parity: the existing `cs.WORK_CONTEXT_SURFACE_KINDS == SURFACE_KINDS`
  test is kept, and the set contains `mcp`.
- [ ] T2. DevLoop: a `resume` signal and an `accept_execution_request` with
  `surface="mcp"`, `actor_kind=human` are accepted. `surface="carrier-pigeon"` is
  refused with `surface-or-actor-unrecognised`. A foreign `actor_kind` is refused.
- [ ] T3. Each legacy surface (`github`, `telegram`, `web`, `cli`, `api`) is still
  accepted.
- [ ] T4. Same principal, `mcp` to `mcp`, executions labelled with different client or
  model names in test metadata: `_take_resume_provenance` returns False and the approval
  is not cleared. With unchanged proposal content the approval releases. With changed
  content the release is refused.
- [ ] T5. End-to-end: a Telegram-origin item resumed with `surface=mcp` seals
  `current_surface="mcp"`, `surface_transition=true` and `actor_id == requested_by`.
- [ ] T6. Mutation: monkeypatch the surface and actor forwarding out of
  `investigate_params`, then assert that T5 fails, `current_surface` is empty and
  `surface_transition` is absent (not false).
- [ ] T7. Unknown provenance: `_work_context_ref` with `surface=None` seals no
  `surface_transition` key. Old fixtures with `surface_transition: false` round-trip
  byte-identical.
- [ ] T8. A redacted pinned intent seals a `request.json` that contains only IDs, the
  model is not invoked, and the DevLoop state is `WAITING_FOR_INPUT`.
- [ ] T9. Redaction after enqueue: the intent is readable when the request is created
  and `text_redacted` when the investigator reads it. Result: the same park as T8.
- [ ] T10. Rebind: an answer carrying a replacement `intent_id` is pinned. The
  replacement text is absent from `request.json`, `answered.json` and the response.
  An `intent_id` from a different work item or principal is refused.
- [ ] T11. Ownership: the lifecycle owner and fencing epoch are unchanged across an `mcp`
  resume.
- [ ] T12. Mixed version: an old-vocabulary `_validate_work_context_args` given
  `--surface mcp` exits non-zero, and an old-vocabulary DevLoop refuses. Neither seals.

## Rollback

Each slice is independently revertible. Reverting Task 1 restores the old refusal of MCP
resumes (fail closed, with no data written). Reverting Task 4 is safe because
documents with an absent `surface_transition` stay readable only if the reader that
treats the key as optional is kept. So revert the producer (`_work_context_ref`) before
the schema reader. Reverting Tasks 6-8 restores today's placeholder behaviour, so revert
them only together with mctl-api#871's request-side refusal still in force. Do not
enable MCP execution admission in mctl-api until all images and the #573 template are
deployed. If admission was enabled early, disable it first.
