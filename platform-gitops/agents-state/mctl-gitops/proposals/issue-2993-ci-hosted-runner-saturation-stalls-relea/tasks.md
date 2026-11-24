# Tasks: issue-2993-ci-hosted-runner-saturation-stalls-relea

- [ ] 1. `validate-manifests.yml`: extend the workflow-level `concurrency` to
  group `pull_request` runs by PR number with `cancel-in-progress`, keep the
  `push` group from #2935 and the per-run, non-cancelling group for
  `merge_group`; update the comment block — DoD: a second push to a PR cancels
  the first head's run; the merge-group run of this PR itself completes.
- [ ] 2. `cloudflare-plan.yml`, `yamllint.yml`, `security.yml`: add the same
  PR-number cancelling group for `pull_request`, per-run non-cancelling for
  `merge_group`/`workflow_dispatch`/`schedule`, per-ref cancelling for
  yamllint `push` — DoD: label changes and new heads collapse to one run per PR.
- [ ] 3. `build-image.yaml`: add a group that cancels only preview-deploy
  builds (`build_id` prefix `preview-deploy`) for the same team, component and
  `git_ref`; every other caller per-run without cancel — DoD: two preview
  dispatches for one component and ref leave one running; a release-deploy
  build is never in a shared group.
- [ ] 4. (depends on 1-3) `tests/test_workflow_concurrency.py`: pin each group
  expression, assert merge_group and `rd-*` builds resolve to run-scoped groups,
  assert `agy-review.yml` and `claude-review.yml` have no workflow-level
  concurrency, and assert the preview prefix matches
  `wft-preview-deploy.yaml` (`metadata.name: preview-deploy`, `build_id =
  "{{workflow.name}}"`) — DoD: test passes in `validate` and fails on a
  mutated expression.
- [ ] 5. `scripts/ci-queue-latency.py` plus fixtures under
  `tests/fixtures/ci_queue_latency/` and `tests/test_ci_queue_latency.py` —
  DoD: prints merge-group start latency, queue-head enqueue-to-merge,
  release dispatch-to-bump-merge and superseded-while-queued counts from
  fixtures; read-only token only.
- [ ] 6. Operator step (not code): list long-queued runs with
  `gh run list --status queued`, inspect the 2026-10-07 `Cloudflare MCP portal
  health` and 2026-11-08 `CodeQL` runs, cancel them, and record what they held
  in the ADR — DoD: no mctl-gitops run older than 24 h is queued.
- [ ] 7. (depends on 5, 6) `docs/adr/0004-ci-runner-capacity.md`: before
  measurement (2026-11-22/23), after measurement (window after 1-3 merge,
  including a DevLoop burst), paid-plan figures confirmed by the org owner,
  self-hosted constraints from design.md, and the decision — DoD: ADR merged
  with a named decision and its owner.
- [ ] 8. (only if task 7 adopts self-hosted; depends on 7)
  `tests/test_self_hosted_fork_boundary.py`: fail any workflow that has a
  `pull_request`, `pull_request_target` or `issue_comment` trigger and a job
  whose `runs-on` includes `self-hosted` or `mctl-trusted-linux`; split the
  `push: main` path of `validate-manifests.yml` into
  `validate-manifests-main.yml` on `[self-hosted, mctl-trusted-linux]` — DoD:
  CI test green on main, red on a fixture that violates it; runner group
  `mctl-gitops-trusted` restricted to mctl-gitops and that workflow file
  (org setting, recorded in the ADR).

## Tests

- [ ] T1. `pytest tests/test_workflow_concurrency.py` passes; mutating the
  merge_group branch to a shared group makes it fail.
- [ ] T2. On the implementing PR: push two commits within a minute; the first
  head's `Validate Manifests` and `Cloudflare Plan` runs end `cancelled`.
- [ ] T3. Enqueue the implementing PR; its merge-group `validate`,
  `reserved-hosts` and `cloudflare-plan` checks run to completion and the PR
  merges.
- [ ] T4. Trigger two preview-deploy builds for the same component and ref; the
  older `build-preview-deploy-*` run ends `cancelled`, the newer succeeds; a
  concurrent `release-deploy` build for the same component is not cancelled.
- [ ] T5. `pytest tests/test_ci_queue_latency.py` against fixtures.
- [ ] T6. (if self-hosted adopted) A throwaway PR with a `pull_request` job on
  `[self-hosted, mctl-trusted-linux]` fails `tests/test_self_hosted_fork_boundary.py`
  and its job is never picked up by the runner group (stays queued, then is
  cancelled).

## Rollback

Each change is a workflow-file edit: revert the PR (through the merge queue)
to restore the previous `concurrency` blocks; no state is migrated. Cancelled
runs can be re-run. If self-hosted runners were adopted, set the moved job's
`runs-on` back to `ubuntu-latest` and disable the runner group in the org
settings; the hosted path is unchanged and resumes immediately.
