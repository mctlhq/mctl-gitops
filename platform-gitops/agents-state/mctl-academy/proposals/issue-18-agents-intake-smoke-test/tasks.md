# Tasks: issue-18-agents-intake-smoke-test

- [ ] 1. Implementer creates branch `chore/smoke-test-issue-18` (or another
      non-`_`-prefixed `chore/…` name per `CONTRIBUTING.md`) off `main` in
      `mctlhq/mctl-academy` — DoD: branch exists, is not `main`, does not
      start with `_`.
- [ ] 2. Add `SMOKE-TEST.md` at the repository root with the content
      specified in `design.md` (names issue #18, cites `PLAN.md` section
      10, links back to this proposal path) (depends on 1) — DoD: file
      exists at repo root; diff for this PR touches exactly this one file
      (no changes under `content/`, `content/schemas/`, `.github/workflows/`,
      or anywhere else).
- [ ] 3. Commit with a `chore:` conventional-commit subject under 72 chars,
      e.g. `chore: add Phase 0 agent dev-loop smoke test marker`, body
      explaining it exists solely for issue #18 verification (depends on 2)
      — DoD: `git log` shows one commit, correct prefix, no
      `Co-Authored-By` trailer, English only, no emoji.
- [ ] 4. Open the pull request against `main` (depends on 3) — DoD: PR is
      open, not a draft, references issue #18 in its description.
- [ ] 5. Confirm `ci.yml` passes (`lint:content`, `test:content`,
      `build:preview`) (depends on 4) — DoD: all three CI steps green. They
      are expected to pass trivially since nothing under `content/` or
      `scripts/` changed.
- [ ] 6. Confirm `claude-review.yml` classifies the PR correctly and
      auto-approves via its documented trivial-diff fast path ("docs or
      comments only") (depends on 4) — DoD: workflow run shows `skip=false`
      (file is outside `content/{questions,lessons,sources}`, so the
      content-only skip does not apply) and a single approving review with
      a one-line reason, no P1/P2 findings.
- [ ] 7. Merge with a merge commit (never squash) once review and CI are
      green (depends on 5, 6) — DoD: `main` contains a merge commit, not a
      squashed/rebased one; `SMOKE-TEST.md` is present on `main`.

## Tests

- [ ] T1. Pipeline-mechanics check: confirm a `DevLoopWorkflow` with id
      `dev-loop-mctlhq-mctl-academy-18` appears in the Temporal UI and that
      `mctl_list_agent_executions` shows this investigate execution (the
      one producing this proposal) — no code change, this simply confirms
      the pipeline is observable end-to-end as `PLAN.md` section 9
      prescribes.
- [ ] T2. Approval two-step, correct order: send the Temporal `approve`
      signal for `dev-loop-mctlhq-mctl-academy-18`, then merge this
      proposal's `.status.yaml` `proposed -> accepted` flip PR in
      `mctl-gitops`. Confirm the implement CWFT runs and opens the PR
      described in tasks 1-7. DoD: PR appears in `mctlhq/mctl-academy`
      within one Temporal Schedule tick of the flip merging.
- [ ] T3. Deliberate failure mode — signal without flip: on a throwaway
      second issue (or a documented dry run), send `approve` without
      merging the `.status.yaml` flip. Confirm the implement CWFT runs and
      exits with `skipped_reason` rather than opening a PR or erroring.
      DoD: `mctl_get_workflow_status` / `mctl_get_workflow_logs` for that
      run shows `skipped_reason` set — matches `PLAN.md` section 5's
      documented silent no-op.
- [ ] T4. Deliberate failure mode — flip without signal: merge a
      `.status.yaml` flip without sending the Temporal `approve` signal.
      Confirm the `DevLoopWorkflow` remains parked at `wait_condition`
      indefinitely (checked via the Temporal UI, not by waiting it out).
      DoD: workflow status shows it is still running / blocked, not
      completed or failed.
- [ ] T5. Post-merge sanity: `mctl_get_service_status` is not applicable
      (this repo has no deployed service yet); instead confirm `main`'s
      `ci.yml` run on the merge commit is green. DoD: latest `main` CI run
      passing.

## Rollback

If the smoke test reveals a pipeline defect, or once the exercise is
confirmed working and the operator prefers not to keep the marker file
permanently:

1. Open a follow-up `chore/remove-smoke-test-marker` branch that deletes
   `SMOKE-TEST.md`. This PR will itself be a small additional exercise of
   the normal (non-agent) code-review path — `claude-review.yml`'s trivial
   fast path applies again (a pure deletion, docs-only).
2. If the pipeline defect is upstream (Temporal, the CWFTs, or the
   `mctl-agents` poller) rather than in this proposal's content, no revert
   in `mctl-academy` is needed — the fix belongs in `mctl-agents` /
   `mctl-gitops`, and this proposal's `SMOKE-TEST.md`, if already merged,
   can stay as the record that surfaced the defect.
3. If the PR from task 4 has not yet merged, closing it and deleting the
   branch is sufficient; nothing in `main` needs to change.
4. No data migrations, no deployed service state, and no `content/` changes
   are involved anywhere in this proposal, so rollback carries no risk of
   touching the question bank, attempts, or evidence snapshots.
