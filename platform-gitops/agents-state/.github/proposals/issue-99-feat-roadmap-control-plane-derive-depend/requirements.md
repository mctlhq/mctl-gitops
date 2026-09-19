# Dependency-aware RoadmapReadySet derived from EpicDefinition and observed GitHub state

## Context

`roadmap/scripts/health.py` and `roadmap/scripts/completion.py` already answer two
questions deterministically for one `EpicDefinition`: is the epic healthy, and is the
required work complete. What neither answers is the operational question an operator or
an MCP client actually asks before starting work: *which bound work items are executable
right now*. `completion.compute()` emits `blocking` — every required item whose status is
not `complete` — and that list is deliberately not a ready queue: in
`roadmap/epics/lifecycle-ownership.yaml`, `guarded-recovery` (mctlhq/mctl-api#294) appears
in `blocking` whether or not its three authored predecessors `ownership-inspection`,
`executor-fencing` and `ownership-reconciler` are closed. Clients therefore rebuild the
`dependsOn` DAG by hand, or worse, read dependency intent out of issue-body prose — the
exact drift `roadmap/README.md` ("Source-of-truth rules") exists to eliminate.

This proposal adds a third derived projection beside health and completion:
`RoadmapReadySet`, a pure function of the exact manifest bytes plus one
`GitHubGraphSnapshot`. It classifies every work item as `complete`, `ready`, `blocked` or
`unknown`, names the blockers that produced a `blocked` or `unknown` verdict, and keeps
the invariant the rest of this directory is built on: unobserved state is never projected
as absence, and nothing that cannot be proven is ever reported `ready`. It adds no clock,
no network call beyond the existing read-only adapter, no LLM and no workflow-runtime
input, and it changes neither `RoadmapHealth` nor `completion` output.

## User stories

- AS an operator I WANT a deterministic list of executable work items for one epic SO
  THAT I can start the right DevLoops without reconstructing the dependency DAG by hand.
- AS an MCP/API client (mctl-api#333, `epic-status-api`) I WANT a published, schema-validated
  readiness contract SO THAT I can render epic status without re-implementing graph rules.
- AS a reviewer I WANT every `blocked` and `unknown` verdict to name its evidence SO THAT
  I can tell "this is genuinely waiting on #350" apart from "nobody observed #350".
- AS a platform engineer I WANT readiness to fail closed on unbound, unobserved,
  ambiguous or not-found bindings SO THAT an unstarted wave is never launched on a guess.
- AS a maintainer I WANT the readiness projection to reuse the existing completion
  vocabulary SO THAT two derived views of the same epic can never disagree about whether
  an item is done.

## Acceptance criteria (EARS)

Projection and CLI

- WHEN `roadmap/scripts/ready.py <manifest> --snapshot <file>` is invoked THE SYSTEM SHALL
  emit one `roadmap.mctl.ai/v1alpha1` `RoadmapReadySet` document validating against
  `roadmap/schemas/roadmap-ready-set.schema.json`.
- WHEN more than one manifest is selected THE SYSTEM SHALL emit a `RoadmapReadySetList`
  envelope whose `items` are ordered by manifest path, mirroring
  `health.render()` in `roadmap/scripts/health.py`.
- WHEN a ready set is emitted THE SYSTEM SHALL carry the epic name, the manifest path
  relative to the repository root, the SHA-256 of the exact manifest bytes and the
  snapshot's own `source` provenance block verbatim, exactly as `health._epic()` does.
- WHEN the same manifest bytes and the same snapshot bytes are supplied twice THE SYSTEM
  SHALL produce byte-identical JSON, in any input order, on any machine.
- WHILE computing a ready set THE SYSTEM SHALL perform no I/O beyond the snapshot source
  it was given, read no clock, and consume no randomness.
- WHEN `--live` is given THE SYSTEM SHALL observe through the existing read-only
  `github_graph.LiveGraphSource` and SHALL accept `--capture` on the same terms as
  `roadmap/scripts/reconcile.py`; `--snapshot` and `--live` SHALL remain mutually exclusive.
- WHEN manifests are selected positionally THE SYSTEM SHALL still schema-, semantic- and
  corpus-validate the entire `--corpus` first, as `reconcile.validate_corpus()` requires.

Per-item readiness

- WHEN a work item's bound issue is observed closed with a reason the existing completion
  contract accepts as delivered THE SYSTEM SHALL report `state: complete`.
- WHEN a work item is observed incomplete and every internal `dependsOn` predecessor and
  every `externalDependsOn` reference is observed complete THE SYSTEM SHALL report
  `state: ready` with `blockers: []`.
- IF a work item is observed incomplete AND at least one predecessor is observed
  incomplete THEN THE SYSTEM SHALL report `state: blocked` and list every such predecessor
  in `blockers` with its completion `status` and `reason`.
- IF a work item is observed incomplete AND no predecessor is observed incomplete AND at
  least one predecessor's completion cannot be proven THEN THE SYSTEM SHALL report
  `state: unknown` and list every unprovable predecessor in `blockers`.
- WHILE at least one predecessor is observed incomplete THE SYSTEM SHALL report `blocked`
  even when another predecessor is `unknown`, mirroring `completion.compute()` where an
  observed `incomplete` outranks an `unknown`.
- IF a work item has no `issue` binding THEN THE SYSTEM SHALL report
  `state: unknown`, `reason: unbound`, and SHALL never report it `ready`.
- IF a work item's own state is unobserved, ambiguous, not found, or closed with a reason
  the completion contract does not recognise THEN THE SYSTEM SHALL report `state: unknown`
  with that same reason, and SHALL never report it `ready` or `blocked`.
- WHEN an `externalDependsOn` reference cannot be proven complete from the captured graph
  THE SYSTEM SHALL report the dependent item `unknown`, never `ready`.
- WHILE an item is `required: false` THE SYSTEM SHALL still assign it a readiness state,
  and WHEN a required item authors a `dependsOn` edge onto an optional item THE SYSTEM
  SHALL treat that optional item as a real predecessor.
- WHEN per-item completion status is needed THE SYSTEM SHALL obtain it from
  `completion.item_status()` rather than re-deriving GitHub state semantics, and SHALL
  echo it in the item's `completion` block.

Determinism, ordering and evidence

- WHEN items are emitted THE SYSTEM SHALL sort them by work-item `id`, and SHALL sort
  `blockers` by (kind, id or repository, number).
- WHILE emitting an item THE SYSTEM SHALL preserve the authored order of `dependsOn` and
  `externalDependsOn` — the one contract-explicit exception to derived ordering.
- WHEN readiness is derived THE SYSTEM SHALL use only authored `EpicDefinition` edges plus
  observed issue state; GitHub labels, issue-body prose, `parent`/`subIssues` hierarchy
  and phase order SHALL NOT create dependency edges.
- WHILE a ready set is being produced THE SYSTEM SHALL admit no input vocabulary other
  than the validated `EpicDefinition` and a schema-valid `GitHubGraphSnapshot`, so DevLoop
  or Temporal runtime state (queued, running, waiting) cannot enter it.

Consistency and exit codes

- WHEN `ready.consistency_errors()` is run over a ready set THE SYSTEM SHALL reject a
  document whose summary counts disagree with its items, whose top-level `ready` list is
  not exactly the items in state `ready`, whose `ready` or `complete` item carries a
  blocker, whose `blocked` item carries no `incomplete` blocker, whose `unknown` item
  carries neither an own-unknown reason nor an `unknown` blocker, or whose blocker names
  an id or issue absent from that item's authored `dependsOn`/`externalDependsOn`.
- WHEN `RoadmapHealth` or `completion` output is produced by the existing entry points
  THE SYSTEM SHALL emit exactly the documents it emits today — no new field, no changed
  status, no changed exit code.
- WHEN the run completes with every item classified and none `unknown` THE SYSTEM SHALL
  exit `0`; with at least one `unknown` item, `1`; on usage/IO error, `2`; on an invalid
  manifest or corpus, `3`; on an observation failure or unusable snapshot, `4` — the same
  code space as `roadmap/scripts/health.py`.

Named acceptance cases from the issue

- WHEN `roadmap/epics/lifecycle-ownership.yaml` is evaluated against a snapshot in which
  mctl-api#293, mctl-agents#352 and mctl-agents#353 are closed as completed THE SYSTEM
  SHALL report `guarded-recovery` as `ready`.
- WHEN `roadmap/epics/human-input.yaml` is evaluated against
  `roadmap/fixtures/human-input/converged-fixture.json` (every issue open) THE SYSTEM
  SHALL report `human-input-core` as the only `ready` item and `devloop-e2e` as
  `unknown/unbound`.
- WHEN `roadmap/epics/unified-identity.yaml` is evaluated THE SYSTEM SHALL report
  `principal-model` as `unknown` with reason `unbound`, never `ready`.
- WHEN `roadmap/epics/roadmap-control-plane.yaml` is evaluated against
  `roadmap/fixtures/roadmap-control-plane/live-capture.json` THE SYSTEM SHALL report
  `ready-work-items` (#99) and `temporal-health` (#85) as `ready`, and `epic-status-api`
  and `governed-wave-start` as `blocked` on `ready-work-items`.

## Out of scope

- Starting, queueing or approving DevLoops, and any write to GitHub.
- Prioritising between independent `ready` items, or selecting a wave.
- Runtime queue, mutex, Temporal or Argo visibility (#95 / execution projection).
- Creating or repairing missing issue bindings for unbound work items.
- Changing `required: false` items into required ones, or changing `completion.mode`.
- Adding readiness to the `RoadmapHealth` document or its schema.
- The mctl-api `epic-status-api` (#333) and `governed-wave-start` (#334) consumers; this
  proposal only publishes the contract they will read.
- Liveness/`UNEXPECTED_SILENCE` semantics, which need a notion of "now".

## Open questions

- Precedence when one predecessor is observed incomplete and another is unprovable: this
  proposal reports `blocked` (certainty outranks ignorance, mirroring
  `completion.compute()`), and still lists the unknown predecessor in `blockers`. A
  reviewer preferring `unknown` to dominate should say so before implementation.
- An item whose own issue is closed as `not_planned` or `duplicate` is `incomplete` under
  the completion contract; this proposal therefore lets it be `ready`/`blocked` on its
  predecessors. Treating it as `unknown` instead is defensible and is a one-line change.
- Readiness ignores the `parent` hierarchy edge entirely, per `roadmap/README.md`
  ("Hierarchy and dependency are deliberately separate"). Confirmed as intended.
- `blockers` reports only direct predecessors. Transitive root-cause chains are
  derivable by a client from the emitted set; emitting them was dropped as redundant.
- Exit code `1` is defined as "at least one item is `unknown`" rather than "no ready
  items". The latter reads better as a wave gate; the former matches this directory's
  habit of making the non-zero code mean "the answer is not fully trustworthy".
- The top-level `ready` list includes optional items. Callers exclude them using each
  item's `required` flag, per the issue's "callers may choose to exclude optional items".
