# Design: issue-147-roadmap-client-lifecycle-retire-the-open

## Current state

`roadmap/` in `mctlhq/.github` is the declarative roadmap control plane described
in `roadmap/README.md`. Authored desired state lives in
`roadmap/epics/*.yaml` as `apiVersion: roadmap.mctl.ai/v1alpha1`,
`kind: EpicDefinition`; GitHub issue state is observed, never copied into the
manifest. Everything downstream is derived.

`roadmap/epics/client-lifecycle.yaml` (107 lines) binds epic root
`mctlhq/.github#22` and declares five phases and seven work items:

- lines 19-29, `spec.phases`: `identity`, `lifecycle`, `broadcast`, `updates`,
  `onboarding`.
- lines 31-35, a five-line comment explaining why the deployment half
  (`mctl-gitops#1182`) is the work item and `mctl-telegram#400` is the parent bug
  that closes behind it. It describes those two items and nothing else.
- lines 36-41, `lookup-deployment` — `phase: identity`, `required: true`, bound to
  `mctlhq/mctl-gitops#1182`.
- lines 43-50, `operator-identity-lookup` — `phase: identity`, `required: true`,
  bound to `mctlhq/mctl-telegram#400`, `dependsOn: [lookup-deployment]`.
- lines 52-97, the five items that stay: `client-reachability-preferences`
  (#438), `login-bot-update-receiver` (#619), `safe-broadcast` (#439),
  `product-update-feed` (#440), `onboarding-integration` (#679). After #146
  (`26846e6`), `onboarding-integration.dependsOn` is `[safe-broadcast,
  product-update-feed]` — it no longer names `operator-identity-lookup`.

Two structural facts from the code decide how small this change can be.

First, the schema (`roadmap/schemas/epic-definition.schema.json`) requires
`spec.phases` and `spec.workItems` to each have `minItems: 1`, and a `phase`
entry carries only `id` and `title` — no back-reference to work items. The
semantic validator (`roadmap/scripts/validate.py:203-247`) checks that phase ids
are unique and that every `workItem.phase` names a declared phase; it has **no**
check that every declared phase owns at least one work item. So an orphaned
`identity` phase would still validate. Removing it is an authoring-hygiene
decision the issue makes explicitly, not a validator requirement — and because
four phases remain, `minItems: 1` is satisfied either way.

Second, the write boundary (`roadmap/README.md`, "Diff entry to operation";
`roadmap/scripts/plan.py`) maps `HierarchyUnexpectedChild` to a **note**, never
an operation: "removing children this manifest does not own" is deliberately
absent from the plan vocabulary, because it would delete state the manifest never
described. That is what makes unauthoring these two items a zero-write change.

Nothing else in the repository references the removed identifiers. A repo-wide
grep for `client-lifecycle`, `lookup-deployment`, `operator-identity-lookup`,
`1182` and `#400` across `*.py`, `*.json`, `*.yaml`, `*.yml` and `*.md` returns
matches only inside `roadmap/epics/client-lifecycle.yaml` itself. There is no
committed capture for this epic — `roadmap/fixtures/` holds only
`human-input/`, `roadmap-control-plane/` and `claude-remote-inbound-channels/` —
and `.github/workflows/roadmap-validate.yml` exercises reconcile/health/ready/plan
against only those three epics. `client-lifecycle` reaches CI solely through the
whole-corpus `validate.py roadmap/epics` step (line 28) and through the corpus
preflight every evaluator runs.

I verified the end state in a scratch copy of `roadmap/` (the clone is
read-only), applying exactly the four removals below:

- `python3 roadmap/scripts/validate.py roadmap/epics` -> exit `0`, `PASS` for all
  17 manifests.
- `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` -> `Ran 318
  tests ... OK`, no test edited.
- `plan.py roadmap/epics/client-lifecycle.yaml --corpus roadmap/epics --snapshot
  <graph>`, where `<graph>` is `roadmap/tests/mutations.synthetic_snapshot()` of
  the **pre-change** manifest (so #1182 and #400 are still sub-issues of #22) ->
  exit `0`, `operations: 0`, and exactly two notes:
  `HierarchyUnexpectedChild` for `mctl-gitops#1182` and for `mctl-telegram#400`,
  each with `observedParent: mctlhq/.github#22` and `owner: epic`. This is the
  issue's predicted outcome, reproduced.
- `health.py` on the same snapshot -> `state: healthy`, and
  `completion.required.total` drops from 7 to 5.
- `ready.py` on the same snapshot -> `ready: ["client-reachability-preferences"]`,
  unchanged by the removal.

## Proposed solution

One edit to one file, `roadmap/epics/client-lifecycle.yaml`. No script, schema,
test, fixture, workflow or other manifest changes.

1. Delete the `identity` phase entry from `spec.phases` (current lines 20-21).
   `spec.phases` becomes `lifecycle`, `broadcast`, `updates`, `onboarding`, in
   that order, otherwise byte-identical.
2. Delete the comment block at current lines 31-35 in `spec.workItems`.
3. Delete the `lookup-deployment` work item (current lines 36-41).
4. Delete the `operator-identity-lookup` work item (current lines 43-50),
   including its `dependsOn: [lookup-deployment]`.

`spec.workItems` then begins directly with `- id: client-reachability-preferences`
and the blank-line separation between the remaining items is preserved exactly as
today. The resulting file is 80 lines.

Why removal rather than any softer form: the manifest's only vocabulary for "this
is authored work" is presence, plus `required: true|false`. `EpicDefinition` has
no `status`, `retired` or `archived` field on a work item — the schema is
`additionalProperties: false` at every level, and the validator layer 1 explicitly
"rejects undeclared fields such as authored `blocks`/`children`/`status`"
(`roadmap/README.md`, "Validation"). Observed GitHub state is a separate axis
computed by `completion.py`. So unauthoring is the only way to say "this is no
longer epic work", and the ordering constraint that made this step unsafe before
#146 is already discharged.

Why the phase goes with the items: a phase is pure presentation grouping
(`id` + `title`) consumed via `workItem.phase` — `ready.py:238` copies
`item["phase"]` into each ready-set entry. With no work items referencing
`identity`, the phase cannot appear in any derived artifact, so keeping it would
be authored state with no consumer and a title ("Operator identity lookup")
that advertises retired work in the epic's phase list.

Why this change writes nothing to GitHub: after the edit, the only diff entries
the two retired issues can produce are `HierarchyUnexpectedChild`, which
`plan.py` records as notes. The empty plan is the safety property — the retired
issues stay exactly as they are on GitHub until an operator closes or detaches
them, which is by design and out of scope here.

Publication refresh needs no extra step: `.github/workflows/roadmap-publish.yml`
runs on every `roadmap/**` change on `main`, so the merge itself triggers a fresh
`RoadmapPublication` on the `roadmap-state` branch (subject to the usual
`publication_order.py` skip and rate-budget guards). No governed apply runs, so
no `publication_request.py` dispatch is involved.

## Alternatives

**Flip both items to `required: false` instead of removing them.** Keeps the
issue references visible in the manifest and unblocks `allRequired` completion,
because `completion.py` looks at required items only. Dropped: the items would
still be authored work, so they would still be bound in
`DesiredGraph.authored_keys()`, still appear in `ready.py` output, and still
carry authored hierarchy — meaning the manifest would continue to claim
ownership of #1182 and #400 and a future drift could plan real writes against
them. It also contradicts the owner-approved decision in #141, which retires the
branch rather than de-prioritizing it, and would leave the `identity` phase
alive.

**Remove the two work items but keep the `identity` phase.** Passes validation
(there is no orphan-phase check) and yields the same zero-operation plan.
Dropped: it leaves an unreferenced phase whose title names retired work, which
`validate.py` cannot catch and a later reader would have to reverse-engineer. The
issue names the phase removal explicitly.

**Remove the items and also update `spec.successCriteria`.** Arguably tidier,
since the first criterion describes the removed phase. Dropped: the issue scopes
the diff to the four removals and states nothing else in the file changes, and the
acceptance criterion is "diff limited to the removals above". Widening the diff
would also make byte-identity of the untouched sections harder to assert in
review. Recorded as an open question instead.

**Close/detach #1182 and #400 in the same change.** Dropped: structurally
impossible through this path. `plan.py`'s operation vocabulary is
`AddSubIssue`, `MoveSubIssue`, `AddDependency`, `RemoveDependency` and nothing
else, and `github_apply.py` holds a four-endpoint allow-list with no issue-state
or child-removal primitive. It is an operator action, and the issue puts it out of
scope.

## Platform impact

**Migrations.** None. No schema version change, no `apiVersion` bump, no data
migration. `roadmap-state` is generated state that is never read back as desired
state (`roadmap/README.md`, "Publication"), so the next publication simply
recomputes from the new manifest bytes.

**Backward compatibility.** The manifest stays schema-valid at
`roadmap.mctl.ai/v1alpha1`. Consumers of the publication (mctl-api#333) read
`ready-set.json` / `health.json` / `snapshot.json` and do not hold references to
work-item ids, so two ids disappearing from the `client-lifecycle` entries is a
normal content change. `RoadmapDiff`, `RoadmapHealth`, `RoadmapReadySet` and
`RoadmapApplyPlan` shapes are untouched. Every artifact that carries the manifest
`sha256` changes value, as it does for any manifest edit.

**Derived-state deltas.** `completion.required.total` for `client-lifecycle`
drops from 7 to 5, and `#1182` / `#400` disappear from `completion.items`,
`blocking` and the ready set. The epic's `ready` list does not change: it is
driven by `client-reachability-preferences`, which has no `dependsOn`. Two new
informational `HierarchyUnexpectedChild` diagnostics appear for this epic and
persist until an operator detaches the issues from #22. They are informational in
severity and "always emitted and never optional in emission"
(`roadmap/README.md`, "Diff types"), so `health.py` stays `healthy` and
`plan.py` exits `0`.

**Resource impact.** Two fewer bound issues in the union the publisher observes,
so a capture costs 8 fewer GETs (`publish.py cost` = repositories + 4 x issues).
Marginally under the documented 1000/hour budget headroom; no scheduling change.

**Risks and mitigations.**

- *Risk: an accidental byte change to a work item that stays* (whitespace,
  reflowed `dependsOn`). Mitigation: review the diff for exactly four removed
  hunks and zero added lines; task T3 pins this with a mechanical assertion that
  the five surviving work items and the non-`phases` parts of `spec` are
  byte-identical to `26846e6`.
- *Risk: the two informational notes are read as new drift and someone "fixes"
  them with a governed apply.* Mitigation: the plan is empty, so there is nothing
  to apply; the PR body states that #1182/#400 stay sub-issues of #22 until an
  operator detaches them, and that this is `plan.py` working as designed.
- *Risk: the retired issues are silently forgotten and linger open under #22.*
  Mitigation: out-of-scope follow-up recorded in the PR body as an operator
  action; the two persistent `HierarchyUnexpectedChild` notes are themselves the
  standing reminder in every publication.
- *Risk: ordering — running this before #146's apply landed.* Already discharged:
  `RemoveDependency` `f955af581e0687da` applied on 2026-09-30, so
  `mctl-telegram#679` is blocked only by #439 and #440 and
  `plan.assert_authored()` (`roadmap/scripts/plan.py:212`) has no endpoint
  outside the authored set. Task 1 re-confirms it against the live graph before
  editing.
- *Risk: CI does not cover this epic directly.* Accepted and mitigated by the
  whole-corpus `validate.py roadmap/epics` step and the corpus preflight; the
  local plan/health/ready runs in T2 close the gap for this change.
