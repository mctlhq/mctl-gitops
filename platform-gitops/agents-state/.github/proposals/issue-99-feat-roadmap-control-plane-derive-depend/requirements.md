# Dependency-aware RoadmapReadySet derived from EpicDefinition

## Context

`roadmap/scripts/completion.py` can already answer whether an epic's required work
is delivered and which required items are not (`completion.blocking`), but
`blocking` is a list of unfinished required items, not a ready queue: it contains an
open required item whether that item's own `dependsOn` predecessors are delivered or
still open. Today a client that wants to know *which bound work items are executable
now* has to re-read `roadmap/epics/<name>.yaml`, rebuild the `dependsOn` /
`externalDependsOn` DAG by hand, and join it against observed GitHub issue state --
exactly the repeated hand reconstruction that `roadmap/README.md` ("Why this exists")
says makes critical-path reasoning non-deterministic.

Issue #99 asks for a third derived projection beside `RoadmapDiff`
(`roadmap/scripts/reconcile.py`) and `RoadmapHealth` / completion
(`roadmap/scripts/health.py`, `roadmap/scripts/completion.py`): a `RoadmapReadySet`
that is a pure function of the exact manifest bytes plus one observed
`GitHubGraphSnapshot`, with no clock, no workflow runtime state and no model. It is
the prerequisite for `epic-status-api` (`mctlhq/mctl-api#333`) and
`governed-wave-start` (`mctlhq/mctl-api#334`), which are already authored as work
items depending on `ready-work-items` in `roadmap/epics/roadmap-control-plane.yaml`.
The value is operational: a wave can be started from a reviewed manifest and observed
evidence instead of from operator memory or issue-body prose.

## User stories

- AS a platform operator I WANT the exact set of work items whose predecessors are
  all delivered SO THAT I can start the next DevLoops without rebuilding the epic DAG
  by hand.
- AS an MCP / API consumer (`mctl-api#333`) I WANT one versioned, schema-validated
  `RoadmapReadySet` document per epic SO THAT I can render epic status without
  re-implementing dependency resolution.
- AS a wave launcher (`mctl-api#334`) I WANT `ready` to exclude every unbound,
  unobserved or ambiguous item SO THAT I never launch work against an issue nobody
  could observe.
- AS a reviewer I WANT identical manifest bytes plus identical snapshot bytes to
  produce byte-identical output SO THAT reviewing a ready set is reviewing a fact, not
  a sample of a moving system.
- AS a maintainer of `RoadmapHealth` I WANT readiness added as a separate document and
  script SO THAT existing health states, completion output and exit codes are
  untouched.

## Acceptance criteria (EARS)

Scope of the projection: the `spec.workItems` of one validated `EpicDefinition`. The
epic root binding (`spec.github.issue`) is not a work item and receives no readiness
state.

Item-level states

- WHEN a work item's bound issue is observed closed with a completion reason the
  existing completion contract accepts (`completion._DELIVERED`) THE SYSTEM SHALL
  report that item `state: complete` with empty `blockers`.
- WHEN a work item is itself observed incomplete (`completion.item_status` returns
  `incomplete` with reason `open`, `closed_not_planned` or `closed_duplicate`) and
  every authored predecessor is `complete` THE SYSTEM SHALL report that item
  `state: ready` with empty `blockers`.
- WHEN such an item has at least one authored predecessor that is itself observed
  incomplete THE SYSTEM SHALL report that item `state: blocked` and SHALL list every
  observed-incomplete predecessor in `blockers` with that predecessor's completion
  `status` and `reason`.
- IF a work item is itself `unknown` under `completion.item_status` (reason
  `unobserved`, `state_not_observed`, `binding_ambiguous` or
  `closed_reason_unrecognized`) THEN THE SYSTEM SHALL report that item
  `state: unknown` carrying that same reason, and SHALL NOT report it `ready`,
  `blocked` or `complete`.
- IF a work item has no `issue` binding THEN THE SYSTEM SHALL report it
  `state: unknown` with reason `unbound`, never `ready`.
- IF a work item's bound issue was observed and GitHub says it does not exist
  (`issue_not_found`) THEN THE SYSTEM SHALL report it `state: unknown` with reason
  `issue_not_found`.
- WHEN an item is not `complete` and no predecessor is observed incomplete but at
  least one predecessor is indeterminate (unbound, not found, unobserved,
  state not observed, binding ambiguous, closed reason unrecognized) THE SYSTEM SHALL
  report that item `state: unknown` and SHALL list every indeterminate predecessor in
  `blockers` with its status and reason.
- WHILE an item has both an observed-incomplete predecessor and an indeterminate
  predecessor THE SYSTEM SHALL report `blocked`, because non-readiness is already
  proven -- the same certainty-first precedence `completion.compute` uses when it
  prefers `incomplete` over `unknown` for epic status.

Dependency sources

- WHILE a manifest exists THE SYSTEM SHALL derive predecessors only from that work
  item's authored `dependsOn` and `externalDependsOn`, and SHALL NOT read GitHub
  labels, issue titles, issue bodies, comments, observed `blockedBy` edges or
  `parent`/`subIssues` hierarchy as dependency sources.
- WHEN a work item authors `externalDependsOn` THE SYSTEM SHALL represent each external
  reference as a predecessor whose completion is evaluated from the captured snapshot
  with the same rules as a bound work item.
- IF an `externalDependsOn` issue's completion cannot be proven from the captured graph
  THEN THE SYSTEM SHALL report the dependent item `unknown`, never `ready`.
- WHILE evaluating readiness THE SYSTEM SHALL treat a predecessor that is `complete` as
  satisfied without inspecting that predecessor's own predecessors, because the
  validator (`roadmap/scripts/validate.py`) already rejects dependency cycles, so one
  hop over an acyclic authored graph is well founded.
- WHILE an item is `required: false` THE SYSTEM SHALL still assign it a readiness state,
  and SHALL still treat it as a real predecessor of any item that authors it in
  `dependsOn`.

Evidence and invariants

- WHILE any authored identity was not observed in the snapshot THE SYSTEM SHALL treat it
  as withheld, never as absent or complete, and SHALL report every item whose readiness
  depends on it as `unknown`.
- IF no snapshot could be obtained, read or validated at all THEN THE SYSTEM SHALL emit
  no `RoadmapReadySet`, print the failure to stderr and exit with the observation
  failure code, because a ready set with no `source` provenance would be a claim about
  a graph nobody looked at.
- WHILE a snapshot was obtained but did not observe every authored identity THE SYSTEM
  SHALL still emit a ready set (with the affected items `unknown`) and SHALL exit with
  the observation failure code.
- WHEN the ready set is emitted THE SYSTEM SHALL include the epic name, the
  repository-relative manifest path, the SHA-256 of the exact validated manifest bytes
  and the snapshot's own `source` block, and SHALL add no timestamp, hostname, absolute
  path or random value of its own.
- WHEN the same manifest bytes and the same snapshot bytes are evaluated twice THE
  SYSTEM SHALL produce byte-identical JSON, independent of the order of
  `spec.workItems` in the YAML and of the order of `issues` in the snapshot.
- WHILE ordering output THE SYSTEM SHALL sort `items` by work-item id and `blockers`
  deterministically, and SHALL preserve authored order only in the echoed `dependsOn`
  and `externalDependsOn` arrays.
- WHILE only workflow runtime state changes (DevLoop queued/running/waiting, Temporal
  execution status, ownership records) THE SYSTEM SHALL produce an unchanged ready set,
  because no runtime source is an input to the projection.
- WHILE readiness is computed THE SYSTEM SHALL NOT perform any write, and SHALL NOT
  change any `RoadmapHealth` state, `completion` block, diagnostic code or CLI exit code
  of `reconcile.py`, `health.py`, `plan.py` or `apply.py`.

Contract, CLI and consistency

- WHEN the projection is published THE SYSTEM SHALL provide
  `roadmap/schemas/roadmap-ready-set.schema.json` defining `RoadmapReadySet` and a
  `RoadmapReadySetList` envelope, `additionalProperties: false` throughout, and SHALL
  validate every emitted document against it before returning it.
- WHEN more than one manifest is selected THE SYSTEM SHALL emit a `RoadmapReadySetList`
  whose `items` are ordered by manifest path, never a bare JSON array.
- WHEN `roadmap/scripts/ready.py` is invoked THE SYSTEM SHALL accept the same manifest
  and corpus boundaries as `reconcile.py` and `health.py` (positional manifests,
  `--corpus`, `--schema`, `--snapshot`, `--live`, `--capture`, `--api-base`,
  `--output`), SHALL validate the whole corpus before any network call, and SHALL treat
  `--snapshot` and `--live`/`--capture` as mutually exclusive.
- WHEN a caller consumes a ready set it did not compute THE SYSTEM SHALL offer
  `ready.consistency_errors(document)` that rejects an internally contradictory
  document: a `ready` item with non-empty `blockers`, a `blocked` item with no
  observed-incomplete blocker, a `complete` item with any blocker, an `unknown` item
  with neither an indeterminate own reason nor an indeterminate blocker, a `ready` id
  list that does not equal the ids of the `ready` items, summary counts that disagree
  with `items`, a blocker naming an id that is not a work item of the same manifest, or
  an echoed `dependsOn` that does not equal the manifest's authored edges.
- IF the authored desired state (manifest or corpus) does not validate THEN THE SYSTEM
  SHALL emit no ready set and exit with the invalid code, observing nothing -- the same
  ordering `health.py` uses.
- WHEN readiness states are computed THE SYSTEM SHALL NOT let them influence the exit
  code: an epic with zero ready items is not an error, mirroring completion's
  separation from the health exit code.

## Out of scope

- Starting, queueing or approving DevLoops; selecting priority between independent
  ready items; any wave launch. Those belong to `mctl-api#333` / `mctl-api#334`.
- Runtime or queue visibility (DevLoop queued/running/waiting, Temporal execution state,
  mutex/ownership inspection). Tracked by `mctlhq/.github#95` and the lifecycle
  ownership epic.
- Any change to `RoadmapHealth` states, precedence, diagnostics, `completion` semantics
  or the `roadmap-health.schema.json` contract.
- Creating or repairing issue bindings for unbound work items, and any other write:
  `github_apply.py` remains the only module that may mutate GitHub.
- Transitive critical-path length, slack, scheduling or estimation.
- Making optional items required, or excluding optional items from the projection.
- Reading dependencies from issue prose, labels or observed `blockedBy` edges as a
  fallback when a manifest exists.

## Open questions

- **`blocked` vs `unknown` precedence when both apply.** The issue defines `blocked` as
  "at least one internal predecessor observed incomplete" and `unknown` as "readiness
  cannot be proven". An item with one open predecessor and one unobserved predecessor
  satisfies both. Proceeding with `blocked` wins, because non-readiness is already
  proven and `completion.compute` already prefers the certain `incomplete` over
  `unknown`; the indeterminate predecessors are still listed in `blockers` so nothing is
  hidden.
- **Unbound or not-found predecessor: `blocked` or `unknown`?** `completion.item_status`
  calls both `incomplete` (they are evidence of undelivered work). The issue's `unknown`
  clause explicitly lists "unbound" and "not found" predecessors. Proceeding with the
  issue: only reasons `open`, `closed_not_planned` and `closed_duplicate` make a
  dependent `blocked`; `unbound` and `issue_not_found` make it `unknown`. This is a
  readiness-layer refinement and changes nothing in `completion.py`.
- **Output serialization.** The issue illustrates YAML. Proceeding with JSON, like every
  other derived document in `roadmap/scripts`, validated against a JSON Schema; the YAML
  in the issue is read as an illustrative shape, not a format requirement.
- **Exit code scheme.** No prior art for "a projection that is never itself a failure".
  Proceeding with `0` a ready set was produced, `2` usage/IO, `3` invalid desired state,
  `4` observation failure -- deliberately reusing `health.py`'s severe codes and leaving
  `1` unused rather than overloading it with "nothing is ready".
- **Extra fields beyond the illustration.** Proceeding with a per-item `phase` (always
  derivable, required by the epic schema, and needed by wave grouping downstream) and a
  `summary` counts block plus a top-level sorted `ready` id list, by analogy with
  `completion.blocking` and `completion.required`.
- **Fixture for the `lifecycle-ownership` acceptance criterion.** No
  `roadmap/fixtures/lifecycle-ownership/` capture exists. Proceeding with a
  deterministic synthetic snapshot builder in `roadmap/tests/mutations.py` that always
  stamps `source.mode: synthetic-fixture`, so a test graph can never masquerade as live
  evidence; a real live capture can be added later without changing the contract.
