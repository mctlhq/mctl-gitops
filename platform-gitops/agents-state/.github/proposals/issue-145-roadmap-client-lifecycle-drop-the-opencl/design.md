# Design: issue-145-roadmap-client-lifecycle-drop-the-opencl

## Current state

`mctlhq/.github` holds the declarative roadmap control plane under `roadmap/`.
The desired graph lives in `roadmap/epics/*.yaml` (17 `EpicDefinition`
manifests); everything else is derived, observed or generated
(`roadmap/README.md`, "Source-of-truth rules": `parent` is authored and
`children` derived, `dependsOn` is authored and `blocks` derived).

### The manifest under change

`roadmap/epics/client-lifecycle.yaml` (epic `client-lifecycle`, root
`mctlhq/.github#22`, `lifecycle: active`) authors 7 work items across 5 phases.
The item this issue targets is at lines 87-98:

```yaml
    - id: onboarding-integration
      title: Integrate identity, consent, reachability and product communication into the client lifecycle
      owner: mctl-telegram
      phase: onboarding
      required: true
      issue:
        repository: mctlhq/mctl-telegram
        number: 679
      dependsOn:
        - operator-identity-lookup
        - safe-broadcast
        - product-update-feed
```

`operator-identity-lookup` (lines 43-50) is bound to `mctlhq/mctl-telegram#400`
and itself depends on `lookup-deployment` (`mctlhq/mctl-gitops#1182`). The
manifest's own comment at lines 31-35 records why #400 is modelled as the parent
bug rather than the startable item: the mctl-telegram half is delivered and only
the deployment half in `mctl-gitops#1182` remains.

A repo-wide search for `onboarding-integration`, `operator-identity-lookup`,
`lookup-deployment` and `client-lifecycle` matches exactly one file —
`roadmap/epics/client-lifecycle.yaml`. No fixture under `roadmap/fixtures/`, no
test under `roadmap/tests/`, and no step in `.github/workflows/` names this epic
or any of its work-item ids. The three committed snapshots
(`human-input/converged-fixture.json`,
`roadmap-control-plane/live-capture.json`,
`claude-remote-inbound-channels/live-capture.json`) cover other epics only.

### How an authored `dependsOn` edge reaches GitHub

1. `validate.py` (`semantic_errors`, lines 258-268) checks that every `dependsOn`
   target names an existing local work-item id, is not self-referential, and
   that the dependency graph is acyclic (`_cycle`, line 319). `corpus_errors`
   (line 333) additionally enforces unique `metadata.name` and unique issue
   bindings across all manifests.
2. `reconcile.desired_graph()` (lines 130-133) turns each `dependsOn` target into
   a desired edge `(owner_item_id, blocked_key, blocker_key)`, skipping unbound
   items and self-edges, and deduplicates via a set (line 150).
3. `reconcile._dependency_entries()` compares desired edges against the observed
   `blockedBy` graph. A desired edge absent live yields `DependencyMissing`; an
   edge observed on an issue this manifest *owns* but no longer desired yields
   `DependencyUnexpected` (lines 420-434). The "owns" restriction comes from
   `owners_by_key`, built from `desired.authored_bindings()`.
4. `plan.py` maps `DependencyUnexpected -> RemoveDependency` (`OPERATION_FOR`,
   line 57) and attaches `precondition: {type: DependencyPresent, ...}` (lines
   147-163). `plan.assert_authored()` (line 212) refuses the whole plan if any
   operation endpoint is not in `DesiredGraph.authored_keys()`.
5. `plan._op_id()` (line 91) derives the operation id as
   `sha256(manifest_sha256 + "\n" + kind + "\n" + "blocked=<label>" + "\n" +
   "blocker=<label>")[:16]`. The manifest digest is an input, so the `opId` is a
   function of the exact manifest bytes.
6. `apply.py --live --execute` performs at most one allow-listed write per
   operation — for this kind, `DELETE /repos/{o}/{r}/issues/{blocked}/dependencies/blocked_by/{id}`
   (`roadmap/README.md`, "Diff entry to operation") — behind guards including
   `--approved-sha256` bound to the manifest bytes and a clean-checkout /
   git-revision assertion (`roadmap/README.md`, "CLI", guards 1-6).

### CI today

`.github/workflows/roadmap-validate.yml` runs, on any `roadmap/**` change:
`validate.py roadmap/epics`, offline `reconcile.py` / `health.py` / `ready.py` /
`plan.py` / `apply.py` replays against the three committed fixtures, and
`python3 -m unittest discover -s roadmap/tests -p 'test_*.py'`. Nothing in it
runs `--live`, so CI cannot reach GitHub. `.github/workflows/roadmap-publish.yml`
triggers on push to `main` under `roadmap/**` and republishes the
`RoadmapPublication` to the generated `roadmap-state` branch.

## Proposed solution

Delete exactly one line from `roadmap/epics/client-lifecycle.yaml`:

```diff
       dependsOn:
-        - operator-identity-lookup
         - safe-broadcast
         - product-update-feed
```

Nothing else changes — no other file, no reformatting, no comment update. The
`operator-identity-lookup` work item, the `lookup-deployment` work item and the
`identity` phase all stay exactly as authored.

### Why block style, and why exactly one line

The issue's snippet prints the target as flow style. That is the one place the
issue is self-contradictory, and the choice is load-bearing rather than
stylistic, because `plan._op_id()` hashes the manifest digest. Both candidate
forms were produced from the clone and measured:

| form | manifest SHA-256 | resulting `opId` |
| --- | --- | --- |
| block style, one line deleted | `e74a0ffc68efcb7c1e932085b2aa453c67536c4b55573891b3f280b60951c615` | `f955af581e0687da` |
| flow style, list rewritten | `d88211c8a3e00f9388bc5e32c964d7d9b8cd93e08453ef2c5392a14c2df18947` | `4fc7300e9d5bcbb3` |

The approved proposal
(`platform-gitops/agents-state/.github/proposals/issue-141-roadmap-pause-communication-agent-and-re/`)
recorded `opId f955af581e0687da`. Only the block-style one-line deletion
reproduces it. The flow-style rewrite would still validate and still yield one
correct-looking `RemoveDependency`, but under a different `opId` — which is the
apply path's idempotency key and the audit record's name for what was written.
Preserving the recorded id is what keeps the owner's prior approval attached to
this change instead of requiring a fresh decision. The design therefore treats
block style as normative and the issue's flow-style snippet as illustrative.
It is also the form that satisfies the issue's own stronger statement, "the diff
is the single `dependsOn` line".

### Verified behaviour of the edited manifest

Executed against a copy of the clone at `664634d`:

- `python3 roadmap/scripts/validate.py roadmap/epics` -> `PASS` for all 17
  manifests, exit `0`.
- `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` -> `Ran 318
  tests ... OK`.
- `plan.py roadmap/epics/client-lifecycle.yaml --corpus roadmap/epics
  --snapshot <pre-edit converged synthetic snapshot>` -> exit `1` (non-empty
  plan) with `summary {"operations": 1, "notes": 0, "refusals": 0}` and the one
  operation being `RemoveDependency`, `owner: onboarding-integration`,
  `blocked: mctlhq/mctl-telegram#679`, `blocker: mctlhq/mctl-telegram#400`,
  `precondition.type: DependencyPresent`, `opId f955af581e0687da`, against
  manifest digest `e74a0ff...`. The snapshot was built with
  `roadmap/tests/mutations.synthetic_snapshot()` from the pre-edit document, so
  it models the live graph as still converged on the old edge set — which is the
  state the governed apply will actually meet.
- `ready.py` on the same snapshot -> `ready: ["client-reachability-preferences",
  "lookup-deployment"]`, and `onboarding-integration` stays `state: blocked` with
  blockers `product-update-feed` and `safe-broadcast`. Identical to the pre-edit
  ready set: the edit removes a redundant blocker, not the binding constraint, so
  nothing becomes newly startable.

### Why the two steps must stay separate, in this order

This was measured too. Applying step 2 on top of step 1 (deleting the
`operator-identity-lookup` work item) still validates (`PASS`), but planning it
against the same pre-edit snapshot produces:

```
REFUSED: RemoveDependency targets an identity this manifest does not author: mctlhq/mctl-telegram#400
exit 3
```

That is `plan.assert_authored()` doing its job: `mctl-telegram#679` is still
owned, so `_dependency_entries` still reports the stale observed `blocked_by`
edge, but `#400` is no longer an authored binding, so no operation may touch it.
The whole `client-lifecycle` plan is refused — not just that operation. The
practical consequence is that if step 2 merges first, or the two are combined in
one pull request, the stale `#679 blocked by #400` edge becomes unremovable
through the governed path until a human re-authors `#400` in the manifest. The
issue's sequencing constraint is therefore a hard mechanical requirement, and
this design states it as an acceptance criterion rather than a convention.

### Pull request shape

One commit, one file, one deleted line. Body references the parent with `Refs
mctlhq/.github#141` and uses no closing keyword, so merging neither closes #141
nor retires `mctl-telegram#679`. Merging triggers `roadmap-validate.yml` (already
green offline) and `roadmap-publish.yml`, which republishes the
`RoadmapPublication` from the new manifest bytes.

## Alternatives

1. **Rewrite the list in flow style, exactly as the issue's snippet prints it.**
   Rejected: measured to change the manifest digest and therefore the `opId` to
   `4fc7300e9d5bcbb3`, breaking the match with the approved
   `f955af581e0687da` and detaching the governed apply from the owner's recorded
   approval. It also touches three lines where one suffices, and diverges from
   the block style every other `dependsOn` in the corpus uses.

2. **Combine step 1 and step 2 in one pull request** (drop the edge and retire
   the `operator-identity-lookup` / `lookup-deployment` items and the `identity`
   phase together). Rejected on evidence: reproduced `PlanRefused` exit `3` for
   the whole epic, leaving the stale live edge unremovable through the governed
   path. Also explicitly out of scope per the issue.

3. **Express the retired precondition as `externalDependsOn:
   [mctlhq/mctl-telegram#400]` instead of deleting the edge.** Rejected twice
   over: `validate.semantic_errors` (lines 304-311) rejects an
   `externalDependsOn` target that is locally bound ("use dependsOn instead"), so
   the corpus would fail validation; and even if it validated,
   `desired_graph` (lines 135-140) derives the same dependency edge from
   `externalDependsOn`, so the live `blocked_by` relation would be preserved —
   the opposite of the intent.

4. **Do nothing in the manifest and remove the live GitHub edge by hand.**
   Rejected: it inverts the source-of-truth rule. The next `reconcile.py` run
   would report `DependencyMissing` and the next governed apply would re-add the
   edge via `AddDependency`. The manifest is the desired graph; the live graph is
   converged onto it, never the reverse.

## Platform impact

- **Migrations:** none. No schema, script, fixture, workflow or generated
  artifact changes. `roadmap/schemas/epic-definition.schema.json` is untouched,
  and `dependsOn` remains an optional list of local ids.
- **Backward compatibility:** the manifest stays `roadmap.mctl.ai/v1alpha1` and
  schema-valid. `completion.mode: allRequired` is unchanged and
  `onboarding-integration` stays `required: true`, so epic completion semantics
  do not move. No consumer reads work-item ids from this epic (verified by the
  repo-wide search), so no published contract shifts.
- **Resource impact:** negligible. One extra `roadmap-publish.yml` run on merge
  (one capture, ~545 GETs per the workflow header comment, within the existing
  hourly budget logic). The governed apply is one `DELETE` request.
- **Readiness / wave-launch impact:** none, measured. The ready set is unchanged
  and `onboarding-integration` stays `blocked`. No item becomes startable, so no
  `mctl_start_epic_wave` behaviour changes and no investigator cost is incurred
  as a side effect.
- **Risk: `opId` drift from an over-eager edit.** A reformatted list, a stray
  trailing newline change or a bundled comment tweak changes the manifest digest
  and the `opId`. Mitigation: the acceptance criteria pin both the digest
  (`e74a0ff...`) and the `opId` (`f955af581e0687da`), and task T2 recomputes them
  before the pull request is opened.
- **Risk: premature step 2.** Mitigated by stating the `PlanRefused` failure mode
  as an acceptance criterion and recording it in the pull request body, so the
  reviewer sequencing step 2 sees the mechanical reason rather than a convention.
- **Risk: the live graph is not actually converged on the old edge.** If GitHub
  does not currently hold `#679 blocked by #400`, the plan is simply empty (exit
  `0`) and nothing is written; `apply.py`'s `DependencyPresent` precondition makes
  the write idempotent either way, reporting `alreadySatisfied`. Either outcome is
  safe and needs no manifest change.
- **Risk: a binding-family refusal at apply time** (someone transferred or
  deleted `#400`, `#679`, or another bound issue). Then the whole plan is refused
  with zero operations by design (`roadmap/README.md`, "Refusal rules"), and the
  correct response is a separate human manifest edit, not a retry.
- **Security:** no new permissions, no token scope change, no model in the apply
  path. The change is merged manifest text, which is the only channel through
  which anything can influence the GitHub graph (`roadmap/README.md`,
  "RoadmapProposal integration").

