# Tasks: issue-99-feat-roadmap-control-plane-derive-depend

- [ ] 1. Publish `roadmap/schemas/roadmap-ready-set.schema.json`: a `oneOf` over
      `$defs.roadmapReadySet` and `$defs.roadmapReadySetList`, `additionalProperties:
      false` throughout, `$defs.issueRef` copied from `roadmap-health.schema.json`,
      required `apiVersion`/`kind`/`epic`/`source`/`ready`/`summary`/`items`, per-item
      `state` enum `ready|blocked|complete|unknown`, a nested
      `completion: {status, reason}` whose enums are byte-identical to
      `roadmap-health.schema.json` `$defs.completion`, authored-order `dependsOn` /
      `externalDependsOn`, and discriminated `blockers`
      (`kind: workItem` with `id`, or `kind: external` with `issue`).
      — DoD: the schema loads under `Draft202012Validator`, `check_schema` passes, and a
      hand-written example document from the issue validates while a document with an
      unknown field, an unknown `state` or an undiscriminated blocker is rejected.

- [ ] 2. Promote `completion._colliding_bindings` to `completion.colliding_bindings`,
      keeping `_colliding_bindings = colliding_bindings` as a module-level alias.
      — DoD: no logic diff inside the function; `python -m unittest
      roadmap.tests.test_completion` passes unmodified; both names resolve to the same
      object.

- [ ] 3. Write the pure core of `roadmap/scripts/ready.py` (depends on 2): the
      `READY/BLOCKED/COMPLETE/UNKNOWN` constants, `BLOCKING_REASONS = {"open",
      "closed_not_planned", "closed_duplicate"}`, the three-way predecessor
      classification (satisfied / blocking / indeterminate) built on
      `completion.item_status`, and `compute(document, observed, unobserved)` emitting
      `items` sorted by id, `ready` as sorted ready ids, and `summary` counts over all
      items and over required items.
      — DoD: `compute()` performs no I/O, takes no clock or runtime argument, imports
      nothing beyond `completion`, `github_graph`, `validate`; `state` is `complete` for a
      delivered item, `ready` only for a bound+observed+incomplete item whose every
      authored predecessor is complete, `blocked` when any predecessor reason is in
      `BLOCKING_REASONS`, `unknown` otherwise; every non-satisfied predecessor appears in
      `blockers`.

- [ ] 4. Extend `ready.compute()` to external dependencies (depends on 3): evaluate each
      `externalDependsOn` `issueRef` through `completion.item_status` on the resolved
      `IssueKey`, echo them in the item's `externalDependsOn`, and emit
      `kind: external` blockers.
      — DoD: an external issue observed closed-as-completed satisfies the edge; observed
      open makes the dependent `blocked`; absent from the snapshot (hence in
      `unobserved`) makes the dependent `unknown`, never `ready`.

- [ ] 5. Implement `ready.consistency_errors(document)` (depends on 3, 4): reject a
      `ready` item with blockers or with an own reason outside `BLOCKING_REASONS`; a
      `blocked` item with no blocker whose reason is in `BLOCKING_REASONS`; a `complete`
      item with any blocker; an `unknown` item with neither an indeterminate own reason
      nor an indeterminate blocker; a `ready` list that is not exactly the sorted ready
      ids; `summary` counts that disagree with `items`; a `workItem` blocker naming an id
      that is not an item of the same document.
      — DoD: each rule has a targeted negative test that mutates one field of a valid
      document and asserts exactly one error message; a valid document returns `[]`.

- [ ] 6. Implement `ready.assess()` and `ready.render()` (depends on 3, 4, 5), reusing
      `health.assess()`'s observation contract: `FixtureGraphSource` with
      `require_complete=False`, `github_graph.snapshot_errors()`,
      `unobserved = authored_keys - observed requested keys`, `observed_graph()`,
      `reconcile._manifest_label()` and `health._epic()`-shaped epic identity; validate
      the emitted document against the new schema and `consistency_errors()` before
      returning; `render()` collapses one document or emits `RoadmapReadySetList` ordered
      by manifest path.
      — DoD: a single manifest yields a bare `RoadmapReadySet`, two or more yield a
      `RoadmapReadySetList` (never a bare array); the document carries the manifest path,
      the sha256 of the validated bytes and the snapshot's `source`, and no other
      timestamp or absolute path.

- [ ] 7. Implement the `ready.py` CLI (depends on 6) mirroring `reconcile.py`/`plan.py`:
      positional manifests, `--corpus`, `--schema`, `--ready-schema`, `--snapshot`,
      `--live`, `--capture` (implies `--live`), `--api-base`, `--output`; full corpus
      validation before any network call; `--snapshot` and `--live/--capture` mutually
      exclusive. Exit `0` produced, `2` usage/IO, `3` desired state invalid, `4`
      observation failure (including a snapshot that could not be obtained at all, where
      no document is emitted).
      — DoD: `python roadmap/scripts/ready.py roadmap/epics/lifecycle-ownership.yaml
      --corpus roadmap/epics --snapshot <fixture>` prints a schema-valid ready set and
      exits 0; passing both `--snapshot` and `--live` exits 2; an unreadable snapshot
      exits 4 and prints nothing to stdout.

- [ ] 8. Add `set_state(snapshot, issue, state, reason)` and
      `synthetic_snapshot(document, states)` to `roadmap/tests/mutations.py` (depends on
      2): pure, deep-copying, derived from `reconcile.desired_graph()` for converged
      relations, always stamping `source.mode: synthetic-fixture` and never a
      `capturedAt` that claims a live read.
      — DoD: `github_graph.snapshot_errors()` returns `[]` for a generated snapshot;
      `reconcile.py` reports zero drift against the manifest it was generated from; the
      generated `source.mode` is `synthetic-fixture` for every input.

- [ ] 9. Write `roadmap/tests/test_ready.py` covering T1-T14 below (depends on 3-8),
      deriving graphs from the manifest under test the way `test_completion.py` does so
      that new work items cannot break old assertions.
      — DoD: `python -m unittest discover -s roadmap/tests -p 'test_*.py'` passes, and
      every emitted document in the suite is validated against
      `roadmap-ready-set.schema.json` and `ready.consistency_errors()`.

- [ ] 10. Document readiness in `roadmap/README.md` (depends on 7): a `## Readiness`
      section between `## Completion` and `## Dogfood: epic #66` with the state table,
      the `blocked`-beats-`unknown` precedence rule, the `blocked` vs `unknown` split for
      unbound/not-found predecessors, the external-dependency rule, the invariants and
      the CLI plus exit codes; add `ready.py` to the `## Layout` tree and
      `roadmap-ready-set.schema.json` to the schema list.
      — DoD: every command shown in the README runs as written from a clean checkout.

- [ ] 11. Extend `.github/workflows/roadmap-validate.yml` (depends on 7, 10) with offline
      `ready.py` steps for `human-input` against the converged fixture and for
      `roadmap-control-plane` and `claude-remote-inbound-channels` against their immutable
      live captures, each followed by an inline `python3 -` assertion that `kind ==
      "RoadmapReadySet"`, that `ready` equals the sorted ids of `state == "ready"` items,
      and that no item is both `ready` and unbound.
      — DoD: the workflow stays `permissions: {}`, never passes `--live`, and the job is
      green on a pull request touching `roadmap/**`.

## Tests

- [ ] T1. Linear chain: with `lifecycle-ownership`, only `ownership-contract` is ready on
      an all-open graph; closing it makes `devloop-ownership` ready and leaves
      `ownership-inspection` blocked.
- [ ] T2. Fan-out: closing `ownership-contract` and `devloop-ownership` reports
      `ownership-inspection` and `executor-fencing` ready in the same ready set.
- [ ] T3. Fan-in with one predecessor open: with `ownership-inspection` and
      `executor-fencing` closed but `ownership-reconciler` open, `guarded-recovery` is
      `blocked` with exactly one `workItem` blocker `ownership-reconciler` / `open`.
- [ ] T4. Acceptance criterion: closing `mctlhq/mctl-api#293`, `mctlhq/mctl-agents#352`
      and `mctlhq/mctl-agents#353` as `completed` resolves `guarded-recovery` as `ready`
      with empty `blockers`.
- [ ] T5. Acceptance criterion: `human-input` on a fresh all-open graph lists exactly
      `human-input-core` among ready **required** items.
- [ ] T6. Optional ready item: with `human-input-api` closed, `portal-card`
      (`required: false`) is `ready` and appears in `ready` with `required: false`.
- [ ] T7. Optional item as a real blocker: an optional item named in another item's
      `dependsOn` and observed open makes that item `blocked`.
- [ ] T8. Unbound item: `human-input`'s `devloop-e2e` is `unknown` / `unbound`, and
      `unified-identity`'s `principal-model` is `unknown` / `unbound` and never `ready`
      despite having no `dependsOn`; no `unified-identity` item is `ready`.
- [ ] T9. Unobserved predecessor: removing one predecessor's observation from the snapshot
      makes its dependent `unknown` with an `unobserved` blocker, never `ready` and never
      silently absent; the run exits 4.
- [ ] T10. Binding faults via `mutations`: `mark_missing` on a predecessor yields an
      `issue_not_found` blocker and an `unknown` dependent; `redirect` on a predecessor
      that is closed-as-completed still satisfies the edge; `add_second_parent` yields
      `binding_ambiguous` and an `unknown` dependent.
- [ ] T11. External dependency, three ways: `mctlhq/mctl-telegram#443` closed-completed
      lets `telegram-adapter` be ready once its local predecessors are complete; open
      makes it `blocked` with a `kind: external` blocker; unobserved makes it `unknown`.
- [ ] T12. Byte identity: two `compute()` runs over the same inputs, and runs over a
      manifest whose `spec.workItems` are shuffled and a snapshot whose `issues` are
      shuffled, all produce byte-identical `json.dumps(..., sort_keys=True)`.
- [ ] T13. Runtime independence: mutating only snapshot `updatedAt` values (and adding no
      runtime field) leaves the ready set byte-identical; asserted structurally by
      `inspect.signature(ready.compute)` accepting no runtime/workflow parameter and
      `ready.py` importing no Temporal/DevLoop/ownership module.
- [ ] T14. No regression in the sibling axes: `RoadmapHealth` state, `completion` block
      and exit code for the `roadmap-control-plane` live capture are unchanged before and
      after this change, and the ready set's per-item `completion` block equals the
      matching `completion.compute()` entry for the same inputs.

## Rollback

Fully additive and reversible with no data or graph impact, because nothing is written
to GitHub and no persisted artifact is rewritten.

1. Immediate mitigation without a revert: stop invoking `roadmap/scripts/ready.py`. No
   other script imports it, so `validate.py`, `reconcile.py`, `health.py`, `plan.py` and
   `apply.py` keep working unchanged.
2. If CI is the problem: drop the `ready.py` steps from
   `.github/workflows/roadmap-validate.yml` in a one-file pull request. The pre-existing
   validate/reconcile/health/plan/apply steps are untouched by this change.
3. Full revert: `git revert` the merge commit. The only files touched outside the new
   `roadmap/scripts/ready.py`, `roadmap/schemas/roadmap-ready-set.schema.json` and
   `roadmap/tests/test_ready.py` are the public alias in `completion.py`, two added
   helpers in `roadmap/tests/mutations.py`, README text and the CI workflow -- none of
   which any other module depends on, so the revert cannot leave a half state.
4. Consumer safety during rollback: `mctl-api#333` / `#334` are not yet implemented, so
   no live consumer loses a contract. If a consumer already reads `RoadmapReadySet`, it
   degrades to "no ready set available" and must not fall back to `completion.blocking`
   as a ready queue -- that list is dependency-blind by design.
