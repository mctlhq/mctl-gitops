# Tasks: issue-147-roadmap-client-lifecycle-retire-the-open

- [ ] 1. Confirm the step-1 precondition still holds before editing: read
      `roadmap/epics/client-lifecycle.yaml` at `main` and verify
      `onboarding-integration.dependsOn` is exactly `[safe-broadcast,
      product-update-feed]` (i.e. #146 / `26846e6` is present and no later commit
      re-added `operator-identity-lookup`). — DoF/DoD: the list contains no
      `operator-identity-lookup`; if it does, stop and report instead of editing,
      because removing the item would then orphan an authored dependency
      endpoint and `plan.assert_authored()` (`roadmap/scripts/plan.py:212`) would
      refuse a later apply.

- [ ] 2. Create branch `feat/agents-issue-147-roadmap-client-lifecycle-retire-the-open`
      and remove the `identity` phase entry from `spec.phases` in
      `roadmap/epics/client-lifecycle.yaml` (depends on 1) — DoD: the two lines
      `    - id: identity` and `      title: Operator identity lookup` are gone;
      `spec.phases` is `lifecycle`, `broadcast`, `updates`, `onboarding` in that
      order and otherwise byte-identical.

- [ ] 3. Remove the five-line comment block above the identity work items
      (current lines 31-35, "The mctl-telegram half of #400 is delivered ...
      startable when there is no code left to write in that repository.")
      (depends on 2) — DoD: no comment remains between `  workItems:` and the
      first work item; no other comment anywhere in the file is touched.

- [ ] 4. Remove the `lookup-deployment` work item (current lines 36-41, bound to
      `mctlhq/mctl-gitops#1182`) (depends on 3) — DoD: the id
      `lookup-deployment` does not appear anywhere in the file, including in any
      `dependsOn`.

- [ ] 5. Remove the `operator-identity-lookup` work item (current lines 43-50,
      bound to `mctlhq/mctl-telegram#400`, `dependsOn: [lookup-deployment]`)
      (depends on 4) — DoD: the id `operator-identity-lookup` does not appear
      anywhere in the file; `spec.workItems` now starts with
      `    - id: client-reachability-preferences`; the file is 80 lines.

- [ ] 6. Assert the untouched remainder is byte-identical (depends on 5) — DoD:
      `git diff 26846e6 -- roadmap/epics/client-lifecycle.yaml` shows only
      removed lines and zero added lines; the work items
      `client-reachability-preferences` (#438), `login-bot-update-receiver`
      (#619), `safe-broadcast` (#439), `product-update-feed` (#440) and
      `onboarding-integration` (#679) appear unchanged, and `metadata`,
      `spec.title`, `spec.goal`, `spec.lifecycle`, `spec.github`,
      `spec.completion` and `spec.successCriteria` are unchanged. `git diff
      --stat` lists exactly one file.

- [ ] 7. Open the pull request (depends on 6) — DoD: the body contains `Refs
      mctlhq/.github#141` and `Closes mctlhq/.github#147`, uses no closing
      keyword for #141, #22, #400 or #1182, and states that #1182 and #400 remain
      sub-issues of #22 (two informational `HierarchyUnexpectedChild` notes)
      until an operator detaches them, and that closing or detaching them is an
      out-of-scope operator follow-up. All checks on
      `.github/workflows/roadmap-validate.yml` are green.

## Tests

No test file is added or modified: this change removes authored data, and the
existing suite already pins the invariants it touches.

- [ ] T1. `python3 -m pip install -r roadmap/requirements.txt` then `python3
      roadmap/scripts/validate.py roadmap/epics` — exit `0`, `PASS
      roadmap/epics/client-lifecycle.yaml`, and `PASS` for all 17 manifests
      (corpus uniqueness of GitHub bindings and epic names still holds).
- [ ] T2. `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` — `OK`,
      318 tests, run from the repository root so the tests that read
      `.github/workflows/roadmap-publish.yml` can find it.
- [ ] T3. Zero-write proof. Build a converged synthetic snapshot of the
      **pre-change** manifest (so #1182 and #400 are still sub-issues of #22)
      with `roadmap/tests/mutations.synthetic_snapshot()`, then run `python3
      roadmap/scripts/plan.py roadmap/epics/client-lifecycle.yaml --corpus
      roadmap/epics --snapshot <snapshot>` — exit `0`, `operations: []`, and
      exactly two notes of type `HierarchyUnexpectedChild`, for
      `mctlhq/mctl-gitops#1182` and `mctlhq/mctl-telegram#400`, each with
      `observedParent` `mctlhq/.github#22`.
- [ ] T4. `python3 roadmap/scripts/health.py roadmap/epics/client-lifecycle.yaml
      --corpus roadmap/epics --snapshot <same snapshot>` — `state: healthy`
      (the two notes are informational and must not produce `drift`), and
      `completion.required.total` is 5, down from 7.
- [ ] T5. `python3 roadmap/scripts/ready.py roadmap/epics/client-lifecycle.yaml
      --corpus roadmap/epics --snapshot <same snapshot>` — exit `0`, and no
      item with id `lookup-deployment` or `operator-identity-lookup` in `items`
      or `ready`. Readiness of the surviving items is unchanged.
- [ ] T6. Grep the whole repository for `lookup-deployment`,
      `operator-identity-lookup`, `mctl-gitops#1182` and `mctl-telegram#400` —
      zero matches, confirming no fixture, test, workflow or document was left
      pointing at the removed ids.

## Rollback

The change is one file and no writes leave the repository, so rollback is a
revert and nothing else.

1. `git revert` the merge commit (or re-add the four removed hunks to
   `roadmap/epics/client-lifecycle.yaml`), restoring the `identity` phase, the
   comment block, `lookup-deployment` and `operator-identity-lookup` with
   `dependsOn: [lookup-deployment]`.
2. Merge the revert to `main`. The push re-triggers
   `.github/workflows/roadmap-publish.yml`, which recomputes `roadmap-state` from
   the restored manifest bytes; the two `HierarchyUnexpectedChild` notes
   disappear again because the manifest owns those children once more, and
   `completion.required.total` returns to 7.
3. Nothing on `roadmap-state` needs hand-repair: it is generated state, never
   read back as desired state, and the monotonic `capturedAt` guard
   (`publication_order.py newer`) keeps the revert's publication from looking
   older than the one it replaces.
4. No GitHub graph repair is needed in either direction: this change authorizes
   zero operations, so no sub-issue or dependency edge was ever written or
   removed by it. #1182 and #400 keep whatever parent and state an operator gave
   them, independent of the manifest.
5. If step 1 of #141 (`26846e6`) has meanwhile been reverted too, revert this
   change **first**, so `onboarding-integration` never names an
   `operator-identity-lookup` that the manifest no longer declares (which
   `validate.py` would reject as `unknown dependsOn target`).
