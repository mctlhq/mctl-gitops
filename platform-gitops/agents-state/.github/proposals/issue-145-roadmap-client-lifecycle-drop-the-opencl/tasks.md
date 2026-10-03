# Tasks: issue-145-roadmap-client-lifecycle-drop-the-opencl

- [ ] 1. In `roadmap/epics/client-lifecycle.yaml`, delete the single line
      `        - operator-identity-lookup` from the `dependsOn` list of work item
      `onboarding-integration` (currently line 96). Keep block style; do not
      rewrite the list into flow style; do not reorder, reindent or reflow the two
      surviving entries; do not touch any comment. — DoD: `git diff --stat` shows
      `1 file changed, 0 insertions(+), 1 deletion(-)`, and `git diff` shows only
      that one removed line.

- [ ] 2. Confirm nothing else in the corpus moved (depends on 1). — DoD:
      `git status --porcelain` lists only `roadmap/epics/client-lifecycle.yaml`;
      `roadmap/epics/communication-agent.yaml` and every other manifest, schema,
      script, fixture and workflow are unmodified.

- [ ] 3. Verify the manifest digest matches the approved bytes (depends on 1). —
      DoD: `sha256sum roadmap/epics/client-lifecycle.yaml` prints
      `e74a0ffc68efcb7c1e932085b2aa453c67536c4b55573891b3f280b60951c615`. If it
      does not, the edit is not byte-identical to the approved form — fix the edit,
      do not adjust the expectation.

- [ ] 4. Open the pull request (depends on 2, 3). Title in the repo's roadmap
      convention, body referencing the parent as `Refs mctlhq/.github#141` and
      naming this as step 1 of 2. Record in the body: the expected single governed
      operation (`RemoveDependency`, `mctl-telegram#679` blocked by
      `mctl-telegram#400`, `opId f955af581e0687da`), and the explicit warning that
      step 2 must not merge before this step's governed apply lands because
      `plan.assert_authored()` would then refuse the whole `client-lifecycle`
      plan with exit `3`. — DoD: the pull request contains no closing keyword
      (`Closes`/`Fixes`/`Resolves`) for #141 or for any bound roadmap issue, and
      `roadmap-validate.yml` is green on it.

- [ ] 5. Do NOT run the governed apply, and do NOT open or land step 2, in this
      pull request. — DoD: no `apply.py --execute` invocation and no second
      manifest edit is part of this change; the follow-up is left to the operator
      sequencing recorded in task 4.

## Tests

- [ ] T1. `python3 roadmap/scripts/validate.py roadmap/epics` — expect `PASS` for
      all 17 manifests and exit `0`.

- [ ] T2. `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` — expect
      `OK` (318 tests at `664634d`), no new failures or errors.

- [ ] T3. Plan the edited manifest against a snapshot that still observes the
      pre-edit converged graph, and assert the single governed operation:

      ```bash
      python3 - <<'PY'
      import json, pathlib, sys, yaml
      sys.path.insert(0, "roadmap/scripts"); sys.path.insert(0, "roadmap/tests")
      import mutations
      pre = yaml.safe_load(
          pathlib.Path("roadmap/epics/client-lifecycle.yaml").read_text(encoding="utf-8")
      )
      for item in pre["spec"]["workItems"]:
          if item["id"] == "onboarding-integration":
              item["dependsOn"] = [
                  "operator-identity-lookup", "safe-broadcast", "product-update-feed"
              ]
      pathlib.Path("/tmp/cl-pre.json").write_text(
          json.dumps(mutations.synthetic_snapshot(pre), indent=2, sort_keys=True) + "\n",
          encoding="utf-8",
      )
      PY

      python3 roadmap/scripts/plan.py roadmap/epics/client-lifecycle.yaml \
        --corpus roadmap/epics --snapshot /tmp/cl-pre.json \
        --output /tmp/cl-plan.json   # exit code 1 = non-empty plan, expected
      ```

      Expect `summary == {"operations": 1, "notes": 0, "refusals": 0}`;
      `epic.manifest.sha256 == e74a0ffc68efcb7c1e932085b2aa453c67536c4b55573891b3f280b60951c615`;
      and the one operation equal to `type: RemoveDependency`,
      `owner: onboarding-integration`, `blocked: mctlhq/mctl-telegram#679`,
      `blocker: mctlhq/mctl-telegram#400`,
      `precondition.type: DependencyPresent`, `opId: f955af581e0687da`.

- [ ] T4. `python3 roadmap/scripts/ready.py roadmap/epics/client-lifecycle.yaml
      --corpus roadmap/epics --snapshot /tmp/cl-pre.json --output /tmp/cl-ready.json`
      — expect exit `0`, `ready == ["client-reachability-preferences",
      "lookup-deployment"]`, and `onboarding-integration` with `state: blocked`,
      `dependsOn: ["safe-broadcast", "product-update-feed"]` and blockers exactly
      `product-update-feed` and `safe-broadcast`. This proves the edit makes
      nothing newly startable.

- [ ] T5. Negative / sequencing check, run on a throwaway copy of the tree and
      never committed: additionally delete the `operator-identity-lookup` work
      item, then re-run T3's plan command. Expect `validate.py` to still pass but
      `plan.py` to exit `3` with `REFUSED: RemoveDependency targets an identity
      this manifest does not author: mctlhq/mctl-telegram#400`. This is the
      evidence for the step-2-must-come-second warning in task 4; discard the copy
      afterwards.

- [ ] T6. No new or modified test file, fixture or workflow is introduced. — DoD:
      `roadmap/tests/`, `roadmap/fixtures/` and `.github/workflows/` are byte
      identical to `main`; the existing offline suite is sufficient because no
      committed fixture references the `client-lifecycle` epic.

## Rollback

The change is one deleted line in one file and, before the governed apply runs,
has no effect outside `mctlhq/.github`.

- **Before merge:** close the pull request. Nothing else to undo.
- **After merge, before the governed apply:** revert the merge commit
  (`git revert -m 1 <merge-sha>`) and merge the revert. `roadmap-validate.yml`
  re-runs offline and `roadmap-publish.yml` republishes from the restored bytes,
  so the `RoadmapPublication` returns to the pre-edit dependency graph on its next
  capture. The live GitHub graph was never touched, so there is nothing to
  reconcile.
- **After the governed apply has removed the live edge:** revert the merge as
  above. The restored manifest re-authors the edge, so the next `reconcile.py`
  run reports `DependencyMissing` for
  `mctl-telegram#679 -> mctl-telegram#400` and `plan.py` emits a single
  `AddDependency` operation with an `AddDependency`-side
  `precondition: DependencyAbsent`. Running `apply.py --live --execute` for
  `roadmap/epics/client-lifecycle.yaml` with the restored bytes' own
  `--approved-sha256` re-adds exactly that one edge, returning the live graph to
  its prior shape. Note the restored digest is the pre-edit
  `c0de0d6c9fd919e09b9a9c4c2ac8d89e4d530e871962a510df4e8e3a050e7b91`, so the
  re-add operation carries a different `opId` than `f955af581e0687da`; that is
  expected, since `opId` is a function of the manifest bytes.
- **If step 2 was already merged when the rollback is needed:** revert step 2
  first, then step 1, so the manifest never sits in the state where
  `mctl-telegram#400` is unauthored while the live edge still exists — that state
  refuses the whole `client-lifecycle` plan (exit `3`) and blocks every governed
  operation for the epic, including the rollback's own `AddDependency`.

