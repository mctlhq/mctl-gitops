# Tasks: issue-68-feat-roadmap-control-plane-governed-epic

- [ ] 1. Add `roadmap/schemas/roadmap-apply-plan.schema.json` defining `RoadmapApplyPlan` and
      `RoadmapApplyPlanList` (v1alpha1): `epic.manifest.{path,sha256}`, `source` provenance, `planId`, `summary`,
      `operations` (`AddSubIssue`, `MoveSubIssue`, `AddDependency`, `RemoveDependency`, each with `opId`,
      typed targets and a `precondition`), `notes`, `refusals` — DoD: `additionalProperties: false` at every
      level, one `oneOf` branch per operation type fixing its own required evidence (mirroring
      `roadmap/schemas/roadmap-diff.schema.json`), `issueRef` reused verbatim, schema passes
      `Draft202012Validator.check_schema`.
- [ ] 2. Add `roadmap/schemas/roadmap-apply-result.schema.json` defining `RoadmapApplyResult` /
      `RoadmapApplyResultList` with per-operation `outcome` in `applied|alreadySatisfied|skipped|failed`, `reason`
      required for the last two, and a required `audit` block (`actor`, `proposal` or null, `manifest.{path,
      sha256, gitRevision}`, `planId`, `targets`) (depends on 1) — DoD: `gitRevision` is `^[0-9a-f]{40}$`, every
      target is the `issueRef` shape, and no free-text field exists that an issue title or body could occupy.
- [ ] 3. Implement `roadmap/scripts/plan.py`: pure `plan(diff, *, manifest_path, manifest_sha256)` mapping the
      four actionable `RoadmapDiff` types to operations, the two informational types to notes, and the three
      binding-family types to `refusals` with zero operations (depends on 1) — DoD: no clock, no randomness, no
      absolute path; operations sorted with the `reconcile._sorted` comparator; `opId` and `planId` are SHA-256
      derivations over manifest hash and canonical endpoints; identical inputs give byte-identical JSON.
- [ ] 4. Add the owned-target assertion in `plan.py`: recompute `reconcile.desired_graph(document).authored_keys()`
      and raise `PlanRefused` if either endpoint of any operation is outside it (depends on 3) — DoD: a
      hand-crafted diff naming a foreign issue produces a refusal, never an operation.
- [ ] 5. Add the `plan.py` CLI mirroring `reconcile.py` (`--corpus`, `--schema`, `--snapshot`, `--live`,
      `--capture`, `--output`), reusing `reconcile.load_corpus()` and `reconcile.LoadedManifest.sha256` (depends
      on 3) — DoD: whole-corpus validation happens before any network call; exit 0 empty plan, 1 non-empty plan,
      2 error, 3 refused; `--live` and `--snapshot` remain mutually exclusive as in `reconcile.main`.
- [ ] 6. Extract the shared origin/HTTPS/userinfo/redirect checks from `github_graph.LiveGraphSource` into a
      reusable base so the write client inherits them, leaving `github_graph.py`'s `WriteAttempted` funnel and
      four-endpoint read surface unchanged — DoD: `python -m unittest discover -s roadmap/tests` still passes with
      no test edits; `github_graph.py` still contains no mutation primitive.
- [ ] 7. Implement `roadmap/scripts/github_apply.py` with `MutationRefused` and a closed
      `(method, path-template)` allow-list of exactly the four sub-issue and dependency endpoints, refusing before
      transmission on anything outside it, on any `GET`, and on any target outside the caller-supplied owned set
      (depends on 6) — DoD: a unit test proves each refusal path raises before a socket is opened.
- [ ] 8. Implement `github_apply.FakeMutator`, applying the same operations to an in-memory
      `GitHubGraphSnapshot` dict under the same request-shape assertions as the live client (depends on 7) —
      DoD: the mutated snapshot still validates against `github-graph-snapshot.schema.json`.
- [ ] 9. Implement `roadmap/scripts/apply.py`: per-operation precondition re-read, then
      `alreadySatisfied` / `applied` / `skipped(PreconditionChanged)` / `failed`, with the owned-target assertion
      re-run immediately before each write (depends on 3, 7) — DoD: no write is ever issued without a preceding
      re-read of that operation's own endpoints.
- [ ] 10. Add the `apply.py` guards: `--execute` required for any write, git-revision resolution with refusal on a
      dirty tree or manifest bytes that differ from the committed bytes, `--approved-sha256` equality check
      (`ApprovalHashMismatch`), and `--max-operations` (default 25) refusing rather than truncating (depends on 9)
      — DoD: each guard has a test that asserts zero writes reached the mutator.
- [ ] 11. Emit `RoadmapApplyResult` from `apply.py` with the full audit block and a `_forbidden_content_errors()`
      pre-emission check, validating the document against the result schema before returning it (depends on 2, 9)
      — DoD: exit 0 all applied/already satisfied, 1 skipped, 2 usage/IO/auth, 3 refused, 4 failed; a result
      containing an issue title fails the content check.
- [ ] 12. Extend `roadmap/README.md`: replace the "Planned write boundary" section with the implemented apply
      contract — operation table, refusal rules, precondition/idempotency model, audit fields, CLI usage and exit
      codes — and rewrite "RoadmapProposal integration" as the concrete decompose-to-apply flow (depends on 11) —
      DoD: every documented flag and exit code exists in the code.
- [ ] 13. Add offline plan/apply steps to `.github/workflows/roadmap-validate.yml` (depends on 11) — DoD:
      `permissions: {}` is unchanged, no token is referenced, live mode is never invoked, and the new steps run
      against fixtures only.
- [ ] 14. Follow-up issue in `mctlhq/mctl-agents`: `RoadmapApplyWorkflow` invoking `plan.py` + `apply.py` in a
      deterministic activity with no model invocation, plus `roadmap-decompose` emitting an `EpicDefinition` draft
      that must pass `validate.py` against the corpus before its PR to `roadmap/epics/` is opened (depends on 12)
      — DoD: issue filed, linked to #68 and bound into `roadmap/epics/roadmap-control-plane.yaml` in a later PR.
- [ ] 15. Follow-up issue in `mctlhq/mctl-api`: add `manifestSha256` and an `epicDefinitionPullRequest` reference
      to `RoadmapProposal`, bind approval to the exact draft bytes, and expose the approved hash to the apply
      workflow (depends on 12) — DoD: issue filed and linked to #68.
- [ ] 16. Follow-up issue: Projects v2 support — extend `github-graph-snapshot.schema.json` with observed project
      fields and `roadmap-diff.schema.json` with a project family before any project mutation is planned
      (depends on 12) — DoD: issue filed, and this proposal's out-of-scope note points at it.
- [ ] 17. Follow-up issue: issue creation for `BindingUnbound` work items, including the manifest write-back
      question and an external idempotency key (depends on 12) — DoD: issue filed and linked to #68.

## Tests

- [ ] T1. `test_plan.py`: the converged `roadmap/fixtures/human-input/converged-fixture.json` produces a plan with
      zero operations and zero refusals.
- [ ] T2. `test_plan.py`: each `roadmap/tests/mutations.py` mutator applied to the converged fixture produces
      exactly one operation of the matching type and no operation in a neighbouring family; restoring the fixture
      returns to an empty plan — the both-directions convention the reconciler suite already uses.
- [ ] T3. `test_plan.py`: determinism — planning the same manifest and snapshot twice, and with the manifest's
      work items reordered in memory, yields byte-identical JSON; the plan contains no timestamp and no absolute
      path.
- [ ] T4. `test_plan.py`: `BindingIssueNotFound`, `BindingRedirected` and `BindingAmbiguous` each refuse the whole
      plan with zero operations; `BindingUnbound` and `HierarchyUnexpectedChild` produce notes only.
- [ ] T5. `test_plan.py`: a synthesized diff whose entry names an issue outside `authored_keys()` raises
      `PlanRefused`.
- [ ] T6. `test_apply.py`: applying a one-operation plan through `FakeMutator` converges the snapshot, and
      re-running `reconcile.py` against the mutated snapshot exits 0 with zero drift.
- [ ] T7. `test_apply.py`: replay — applying the same plan a second time records every operation as
      `alreadySatisfied` and issues zero writes.
- [ ] T8. `test_apply.py`: a graph changed between plan and apply yields `skipped` with `PreconditionChanged` and
      zero writes.
- [ ] T9. `test_apply.py`: without `--execute` nothing is written; with a dirty tree, a mismatched
      `--approved-sha256`, or more operations than `--max-operations`, the run refuses with zero writes.
- [ ] T10. `test_apply.py`: `github_apply` refuses a `GET`, an off-allow-list path, a cross-origin URL and a
      target outside the owned set, each before transmission.
- [ ] T11. `test_apply.py`: the emitted `RoadmapApplyResult` validates against its schema, carries actor, proposal,
      manifest path/sha256/gitRevision, planId and targets, and contains no issue title or body; the content check
      rejects a deliberately polluted result.
- [ ] T12. `test_apply.py`: the Human Input acceptance path — start from the converged fixture with hierarchy and
      dependency edges removed, plan and apply, then reconcile to zero drift, proving a merged manifest converges
      the epic with no hand-maintained duplicate graph declarations.
- [ ] T13. CI: `python roadmap/scripts/validate.py roadmap/epics` and
      `python -m unittest discover -s roadmap/tests -p 'test_*.py'` pass, and the new offline plan/apply workflow
      steps are green with `permissions: {}`.

## Rollback

Nothing in this change is destructive to the existing control plane, and no state is migrated.

1. **Stop writes without reverting code.** Withhold the `issues: write` token from the apply job, or drop
   `--execute` from every caller. `apply.py` then plans and re-reads only and writes nothing; `validate.py`,
   `reconcile.py`, `health.py` and CI are unaffected.
2. **Revert the merge.** `plan.py`, `apply.py`, `github_apply.py`, the two schemas, the two test modules and the
   new CI steps are additive; reverting the PR restores the previous tree exactly. The only edit to existing code
   is the extracted origin-check helper in `github_graph.py` (task 6), which is behaviour-preserving and covered
   by the existing suite.
3. **Undo applied mutations.** Every write is recorded in the `RoadmapApplyResult` as an `applied` operation with
   its `opId` and typed targets, so the inverse set is mechanical: `AddSubIssue` is undone by removing that
   sub-issue, `AddDependency` by removing that blocked-by edge, and so on. Because the manifest is the desired
   state, the supported way to reverse an intentional convergence is to revert the manifest PR and re-run apply;
   the graph then converges back to the previous authored state.
4. **Blast radius if step 3 is needed.** `--max-operations` (default 25) bounds any single run, and binding-family
   refusal means no run can touch an issue whose identity was not settled, so the reversal set is always small,
   enumerated and confined to identities the manifest authored.
