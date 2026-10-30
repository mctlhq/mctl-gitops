# Tasks: issue-735-fix-evidence-never-bind-a-pr-subject-to

- [ ] 1. `orchestrator/evidence_producer.py`: replace the Amendment 2 subject
  fallback in `build()` so that `subject is None and pending_pr` yields
  `Gap("subject", "observation_failed", required=True)` (or the pushed head,
  defensively) and never calls a reader. — DoD: no code path in `build()`
  reaches `subprocess` or a head reader; existing tests `:727`, `:835` pass.
- [ ] 2. (depends on 1) Delete `read_pr_head_sha`, `PrHeadReader`, and the
  `read_pr_head` parameter of `build()` and `produce()`; keep
  `READ_TIMEOUT_SECONDS`. Update the tail-budget comment (~105-114), the
  `pending_pr` comment, and the `note_subject_pr` docstring. — DoD:
  `grep -rn "read_pr_head\|PrHeadReader" orchestrator tests` returns nothing;
  ruff/mypy clean.
- [ ] 3. `RunEvidence.note_pushed_head`: when `pending_pr` is set, bind the
  subject to the pushed SHA at push time and clear `pending_pr`.
  `note_subject_pr`: when no usable head is given and the current subject is
  already a `pull_request` for the same `(repository, number)`, keep it.
  `note_subject_pr_url(url, head_sha=None)` forwards `head_sha`. — DoD: order
  of `note_subject_pr_url` / `note_pushed_head` does not change the result;
  a second head-less naming of the same PR does not drop the subject.
- [ ] 4. (depends on 3) `orchestrator/run_implementer.py`: add
  `pr_head_sha: str | None = None` to `ImplementResult`; set it from
  `existing.head_sha` in the preflight `open`, `merged`, `closed` and
  `needs-triage` returns of `implement_one`; at line ~2890 call
  `evidence.note_subject_pr_url(result.pr_url, result.pr_head_sha)`. Fix the
  `:2861` docstring. — DoD: a preflight-adopted PR seals a subject at the
  preflight `headRefOid` with no additional `gh` call.
- [ ] 5. Shepherd: no code change; confirm `process_one` with empty
  `headRefOid` reaches `note_subject_pr(..., "")` and nothing else. — DoD:
  test T4 passes.
- [ ] 6. PR description states the gap-code choice (`observation_failed`,
  no mctl-api change) and that `:882` is kept because it tests the local
  `_capture_head_sha` bound, not the deleted function.

## Tests

All in `tests/test_evidence_producer.py` unless noted; each must go red under
the named mutation.

- [ ] T1. Replace `:463` (`test_flag_on_a_pr_head_read_at_seal_time_binds_the_subject`)
  with `test_a_pr_named_without_a_head_is_a_required_subject_gap`:
  `note_subject_pr_url(...)` with no head, `gh` forbidden (monkeypatch
  `subprocess.run` in `evidence_producer` to raise `AssertionError`), expect
  `subject is None`, `provenance is None`, `("subject", "observation_failed",
  True)` in gaps, `INCOMPLETE`. Mutation: restore the seal-time read in
  `build()`.
- [ ] T2. Adapt `:449`: drop the `read_pr_head=unreadable` argument; same
  assertions (gap, INCOMPLETE). Mutation: bind the subject with an empty
  revision instead of the gap.
- [ ] T3. Adapt `:727` and `:835`: drop `read_pr_head=` arguments; both
  orders still bind to the pushed SHA. Mutation: `note_pushed_head` stops
  binding a pending PR.
- [ ] T4. Shepherd `process_one` with `PRSnapshot(head_sha="")` (pattern of
  `:850`), `subprocess.run` patched to raise: expect `evidence.subject is
  None`, `pending_pr == ("mctlhq/mctl-agents", 9)`, and the sealed envelope
  carries the required subject gap. Mutation: shepherd re-reads the head via
  `gh` when `headRefOid` is empty.
- [ ] T5. Implementer: `implement_one` with `_preflight_existing_result`
  stubbed to `ExistingResult(action="open", pr_url=".../pull/7",
  head_sha=SHA)` and `update_status_yaml` stubbed, run inside
  `ep.run(STAGE_IMPLEMENTER, environ={})` through
  `_record_implementer_evidence`: expect subject at `SHA`. Mutation: drop
  `pr_head_sha` from the preflight return.
- [ ] T6. Same PR named twice, first with `SHA`, then without a head: subject
  stays at `SHA`. Mutation: revert the keep-rule in `note_subject_pr`.
- [ ] T7. Golden ids: `tests/test_execution_evidence.py` golden vectors
  (`:299-315`) and `test_evidence_producer.py:113/125` unchanged and green.
- [ ] T8. Keep `:882` (`_note_pushed_head` 10 s bound) and `:850` unchanged.
- [ ] T9. Full suite: `uv run pytest` green; `ruff` and `mypy` clean.

## Rollback

Revert the PR. No data, schema or API change is involved; envelopes sealed
in the meantime with a required `subject` gap stay valid under the existing
contract. If only the implementer part misbehaves, setting
`MCTL_EVIDENCE_AMENDMENT_2=false` in the CWFTs drops the `subject` block
entirely as an emergency stop (envelopes revert to the pre-amendment shape).
