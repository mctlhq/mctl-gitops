# Drop the operator-identity-lookup dependency from client-lifecycle onboarding-integration

## Context

`roadmap/epics/client-lifecycle.yaml` currently authors work item
`onboarding-integration` (bound to `mctlhq/mctl-telegram#679`) as depending on
three predecessors: `operator-identity-lookup` (`mctlhq/mctl-telegram#400`),
`safe-broadcast` (`mctlhq/mctl-telegram#439`) and `product-update-feed`
(`mctlhq/mctl-telegram#440`). Issue #145 carries step 1 of the two Client
Lifecycle steps from the owner-approved reconciliation proposal behind
mctlhq/.github#141: remove the `operator-identity-lookup` entry from that
`dependsOn` list and change nothing else in the corpus.

This matters because `dependsOn` is the only authored direction of the
dependency relation (`roadmap/README.md`, "Source-of-truth rules"), and the
governed write boundary converges the live GitHub `blocked_by` graph onto it.
Dropping the authored edge is therefore not a cosmetic manifest tidy-up: it is
the reviewable input that authorizes exactly one `RemoveDependency` mutation
against `mctl-telegram#679`. The reconciliation proposal pinned that operation's
identity in advance as `opId f955af581e0687da`, and because
`plan._op_id()` hashes the manifest digest together with the operation
endpoints, the recorded `opId` is reproducible only for one exact byte-level
form of the edit. Sequencing matters too: step 2 (retiring the
`operator-identity-lookup` item and the `identity` phase) must not merge before
this step's governed apply lands.

## User stories

- AS the roadmap owner I WANT `onboarding-integration` to depend only on
  `safe-broadcast` and `product-update-feed` SO THAT the manifest states the
  real precondition set for `mctl-telegram#679` instead of an edge the
  reconciliation review retired.
- AS a reviewer of the governed apply I WANT the plan produced from the merged
  manifest to contain exactly the one operation whose `opId` the approved
  proposal already named SO THAT approving the plan is the same decision the
  owner already made, with no re-derivation of intent.
- AS an operator running `apply.py --execute` I WANT the removal to stay a
  single, precondition-guarded `DELETE .../dependencies/blocked_by/{id}` on an
  issue this manifest owns SO THAT the blast radius of step 1 is one edge.
- AS a consumer of `RoadmapReadySet` (a wave launcher, `mctl-api`) I WANT this
  edit to change no item's readiness state SO THAT no work becomes startable as
  a side effect of a bookkeeping correction.

## Acceptance criteria (EARS)

- WHEN the change is applied to `roadmap/epics/client-lifecycle.yaml` THE
  SYSTEM SHALL contain, for work item `onboarding-integration`, a `dependsOn`
  list whose members are exactly `safe-broadcast` and `product-update-feed`, in
  that order.
- WHEN the diff of the pull request is inspected THE SYSTEM SHALL show exactly
  one changed file and exactly one deleted line, `        -
  operator-identity-lookup`, with no other insertion, deletion or
  reformatting anywhere in the corpus.
- WHILE the edit is in place THE SYSTEM SHALL keep `roadmap/epics/client-lifecycle.yaml`
  byte-identical to the form whose SHA-256 is
  `e74a0ffc68efcb7c1e932085b2aa453c67536c4b55573891b3f280b60951c615`, because
  `plan.py` derives `opId` from the manifest digest and the approved proposal
  pinned `f955af581e0687da`.
- WHEN `python roadmap/scripts/validate.py roadmap/epics` is run THE SYSTEM
  SHALL print `PASS` for all 17 manifests and exit `0`.
- WHEN `python -m unittest discover -s roadmap/tests -p 'test_*.py'` is run THE
  SYSTEM SHALL report `OK` for the full suite (318 tests at `664634d`).
- WHEN `plan.py` is run for `roadmap/epics/client-lifecycle.yaml` against a
  snapshot that still observes the pre-edit converged graph THE SYSTEM SHALL
  emit a `RoadmapApplyPlan` with `summary.operations == 1`,
  `summary.refusals == 0`, `summary.notes == 0`, and that one operation SHALL be
  `type: RemoveDependency`, `owner: onboarding-integration`,
  `blocked: mctlhq/mctl-telegram#679`, `blocker: mctlhq/mctl-telegram#400`,
  `precondition.type: DependencyPresent`, `opId: f955af581e0687da`.
- WHILE the edit is merged and the governed apply has not yet run THE SYSTEM
  SHALL keep `ready.py` reporting `onboarding-integration` as `blocked` with
  blockers `safe-broadcast` and `product-update-feed`, and the epic's ready set
  as `["client-reachability-preferences", "lookup-deployment"]` — unchanged from
  before the edit.
- WHILE the edit is merged THE SYSTEM SHALL still author work items
  `lookup-deployment`, `operator-identity-lookup` and the `identity` phase, and
  SHALL still bind `mctlhq/mctl-telegram#400`, so that `mctl-telegram#400`
  remains an authored identity of this manifest.
- IF the `dependsOn` list is rewritten in YAML flow style (`dependsOn:
  [safe-broadcast, product-update-feed]`) THEN THE SYSTEM SHALL be considered
  non-compliant, because that form yields manifest digest
  `d88211c8a3e00f9388bc5e32c964d7d9b8cd93e08453ef2c5392a14c2df18947` and
  `opId 4fc7300e9d5bcbb3`, which does not match the approved
  `f955af581e0687da`.
- IF the step-2 change (removing the `operator-identity-lookup` work item)
  merges before this step's governed apply lands THEN THE SYSTEM SHALL refuse
  the whole `client-lifecycle` plan with exit code `3` and
  `REFUSED: RemoveDependency targets an identity this manifest does not author:
  mctlhq/mctl-telegram#400`, so the two steps SHALL NOT be combined in one pull
  request and step 2 SHALL NOT merge first.
- WHEN the pull request body is written THE SYSTEM SHALL reference the parent as
  `Refs mctlhq/.github#141` and SHALL NOT use any GitHub closing keyword
  (`Closes`, `Fixes`, `Resolves`) for #141 or for any bound roadmap issue.

## Out of scope

- Removing the `operator-identity-lookup` work item, the `lookup-deployment`
  work item (`mctlhq/mctl-gitops#1182`), or the `identity` phase. That is step 2
  and a separate pull request that must not merge before this step's governed
  apply lands.
- Closing, reopening, relabelling or commenting on any GitHub issue, including
  `mctl-telegram#440`, `#400`, `#679` and `mctl-gitops#1182`.
- Any edit to `roadmap/epics/communication-agent.yaml` (paused in #144,
  `664634d`) or to any other manifest in `roadmap/epics/`.
- Any Communication Agent implementation work in `mctlhq/mctl-telegram`.
- Executing the governed apply itself. `apply.py --live --execute` is a separate,
  manually triggered, approval-bound operator step (`roadmap/README.md`, "CLI");
  this proposal only produces the merged bytes that authorize it.
- Adding a committed snapshot fixture for `client-lifecycle`, changing
  `.github/workflows/roadmap-validate.yml`, or touching any roadmap script or
  schema.

## Open questions

- The issue prints the target state as YAML flow style (`dependsOn:
  [safe-broadcast, product-update-feed]`) while the file is authored in block
  style, and also asks for "the single `dependsOn` line" as the whole diff. These
  two readings conflict. Resolved in favour of block style: only the one-line
  deletion reproduces the proposal's recorded `opId f955af581e0687da`
  (verified — see design.md). The flow-style rewrite is treated as illustrative
  prose, not as the literal bytes.
- The issue title says "OpenClaw-only dependency", but the dependency being
  dropped is `operator-identity-lookup`, bound to `mctlhq/mctl-telegram#400`
  (the admin:users operator lookup tier), and no OpenClaw component appears
  anywhere in `roadmap/epics/client-lifecycle.yaml`. The issue body is treated
  as authoritative over the title; the title wording is assumed to be shorthand
  from the parent discussion and needs no manifest change.
- Who runs the governed apply for the resulting `RemoveDependency`, and when,
  is not stated in the issue. Assumed to be the existing manual operator step
  after merge, unchanged by this proposal; recorded here so the reviewer can
  schedule step 2 behind it.

