# Design: issue-68-feat-roadmap-control-plane-governed-epic

## Current state

Everything the roadmap control plane does today lives under `roadmap/` in `mctlhq/.github` and is read-only by
construction.

**Desired state.** `roadmap/epics/*.yaml` hold `roadmap.mctl.ai/v1alpha1` `EpicDefinition` manifests.
`roadmap/schemas/epic-definition.schema.json` is `additionalProperties: false` throughout and rejects authored
`blocks`/`children`/`status`; `spec.github.project` exists as a free-form map but nothing reads it.
`roadmap/scripts/validate.py` adds the semantic layer (`semantic_errors`, `corpus_errors`, `issue_key`,
`canonical_repository`): unique ids, acyclic `parent` and `dependsOn` graphs, globally unique GitHub bindings
across the corpus.

**Observed state.** `roadmap/scripts/github_graph.py` owns everything that touches GitHub.
`LiveGraphSource._request` raises `WriteAttempted` before transmission on a non-GET method or a request body,
`_is_allowed` refuses to send the bearer token off the configured API origin, and `_SameOriginRedirectHandler`
holds redirects to the same rule. Only four endpoints are used: `GET /issues/{n}`, `/parent`, `/sub_issues`,
`/dependencies/blocked_by`. GraphQL is deliberately unused, so "read-only" is checkable by construction rather
than promised by convention. `observed_graph()` normalizes a `GitHubGraphSnapshot` into `ObservedGraph`
(`resolution`, `missing`, `observed`, `parents`, `children`, `blocked_by`, `states`).
`roadmap/schemas/github-graph-snapshot.schema.json` has no project representation at all.

**Diff.** `roadmap/scripts/reconcile.py` builds a `DesiredGraph` (`desired_graph()`, with `authored_bindings()`,
`owned_keys()`, `authored_keys()`) and compares. `load_corpus()` validates the *whole* corpus before any network
call and returns `LoadedManifest(document, sha256)` — the digest is taken from the same read that was parsed,
precisely because "the manifest hash is what audit and exact-hash approval rely on" (docstring, `reconcile.py`).
`_manifest_label()` renders a repository-relative, never absolute, path. `diff()` emits a `RoadmapDiff` carrying
`epic.manifest.{path, sha256}` and the snapshot's `source` provenance, with nine entry types across three
families and no clock or random value of its own. Exit codes: 0 converged, 1 drift, 2 error.

**Health and completion.** `roadmap/scripts/health.py` derives `RoadmapHealth`
(`healthy`/`drift`/`invalid`/`observation_failed`, precedence most-severe-first) and
`roadmap/scripts/completion.py` computes `allRequired`, failing closed on an unrecognised `stateReason`.

**Proof.** `roadmap/tests/mutations.py` holds pure deep-copy mutators (`drop_parent_edge`, `repoint_parent`, ...)
and the suite proves the detector in both directions. `.github/workflows/roadmap-validate.yml` runs with
`permissions: {}`, offline fixtures only; live mode never runs in CI.

**The gap.** `roadmap/README.md` "Planned write boundary" and "RoadmapProposal integration" describe exactly this
issue and nothing implements it. `roadmap/epics/roadmap-control-plane.yaml` lists `governed-apply` (this issue,
#68) as `required: true` in phase `apply`, depending on `reconciler` (#67), and it is the sole entry in the
dogfood run's `blocking: ["governed-apply"]`.

## Proposed solution

Add a deterministic apply engine beside the reconciler, in three new modules and two new schemas, and keep the
existing read path byte-for-byte untouched.

```text
roadmap/
  schemas/
    roadmap-apply-plan.schema.json      (new) RoadmapApplyPlan / RoadmapApplyPlanList
    roadmap-apply-result.schema.json    (new) RoadmapApplyResult / RoadmapApplyResultList
  scripts/
    plan.py                             (new) RoadmapDiff -> RoadmapApplyPlan, pure
    github_apply.py                     (new) closed allow-list write client + offline fake
    apply.py                            (new) executes a plan, emits RoadmapApplyResult
  tests/
    test_plan.py                        (new)
    test_apply.py                       (new)
```

### 1. `plan.py` — the only thing that decides what may be written

`plan(diff, *, manifest_path, manifest_sha256) -> dict` is a pure function of a `RoadmapDiff` document. It does
no I/O, has no clock and no randomness, exactly like `reconcile.diff()`. A `RoadmapApplyPlan` holds:

```jsonc
{
  "apiVersion": "roadmap.mctl.ai/v1alpha1",
  "kind": "RoadmapApplyPlan",
  "epic": {"name": "...", "manifest": {"path": "roadmap/epics/human-input.yaml", "sha256": "..."}},
  "source": { /* copied verbatim from the diff's snapshot provenance */ },
  "planId": "sha256 over manifest sha256 + ordered opIds",
  "summary": {"operations": 2, "notes": 1, "refusals": 0},
  "operations": [ /* ordered, each with opId, type, targets, precondition */ ],
  "notes":      [ /* informational diff entries, non-actionable */ ],
  "refusals":   [ /* reasons the plan is empty and must stay empty */ ]
}
```

Diff entry to operation, one-to-one, nothing else:

| `RoadmapDiff` entry | severity | plan outcome | GitHub call at apply time |
| --- | --- | --- | --- |
| `HierarchyMissingParent` | drift | `AddSubIssue` | `POST /repos/{o}/{r}/issues/{parent}/sub_issues` |
| `HierarchyWrongParent` | drift | `MoveSubIssue` | `DELETE .../issues/{observedParent}/sub_issue` then `POST .../issues/{expectedParent}/sub_issues` |
| `DependencyMissing` | drift | `AddDependency` | `POST /repos/{o}/{r}/issues/{blocked}/dependencies/blocked_by` |
| `DependencyUnexpected` | drift | `RemoveDependency` | `DELETE /repos/{o}/{r}/issues/{blocked}/dependencies/blocked_by/{id}` |
| `HierarchyUnexpectedChild` | informational | note | none |
| `BindingUnbound` | informational | note | none |
| `BindingIssueNotFound` | drift | **refusal** | none |
| `BindingRedirected` | drift | **refusal** | none |
| `BindingAmbiguous` | drift | **refusal** | none |

**Fail closed on identity.** Any binding-family drift refuses the whole plan for that manifest — zero operations,
not a partial apply. The reconciler already treats these as "the authored identity no longer names the object we
think it names": a redirect means somebody transferred the issue, a not-found means it was deleted, an ambiguity
means two authored bindings collapsed onto one live object. Each is an externally changed binding, and the only
correct response is a human editing the manifest in a PR. Relation suppression in `_resolve_endpoints` already
withholds the relations touching an unsettled endpoint, so refusing on the binding family is consistent with how
the detector already handles the same evidence.

**Targets are provably owned.** `plan.py` recomputes `desired_graph(document).authored_keys()` from the same
validated manifest and asserts that both endpoints of every operation are in that set, raising `PlanRefused`
otherwise. Operation targets are therefore a subset of the manifest's authored identities by construction, not by
review.

**Deterministic ids.** `opId = sha256(manifest_sha256 || type || canonical endpoints)`, hex, truncated to 16
chars; `planId = sha256(manifest_sha256 || ordered opIds)`. Operations are ordered with the same
`json.dumps(..., sort_keys=True)` comparator `reconcile._sorted` uses, so identical manifest and snapshot bytes
produce a byte-identical plan.

**Preconditions.** Each operation records the state it expects to find, in the vocabulary of `ObservedGraph`:
`AddSubIssue` expects `parents[child] == ()`; `MoveSubIssue` expects `parents[child] == (observedParent,)`;
`AddDependency` expects `(blocked, blocker) not in blocked_by`; `RemoveDependency` expects it present. The
precondition is what makes replay safe and what makes an externally changed graph visible at write time.

CLI mirrors `reconcile.py` (`--corpus`, `--schema`, `--snapshot`, `--live`, `--capture`, `--output`) and reuses
`reconcile.load_corpus()`, so corpus-wide validation still happens before any network call. Exit codes: 0 empty
plan (converged), 1 non-empty plan, 2 error, 3 refused.

### 2. `github_apply.py` — a separate module, on purpose

The write client does **not** go into `github_graph.py`. That module's safety property is that it contains no
mutation primitive at all; adding one would turn a structural guarantee into a code-review convention and
invalidate the proof #67 established. `github_apply.py` is a new module with the mirror-image guard:

```python
ALLOWED = {
    ("POST",   "/repos/{owner}/{repo}/issues/{number}/sub_issues"),
    ("DELETE", "/repos/{owner}/{repo}/issues/{number}/sub_issue"),
    ("POST",   "/repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by"),
    ("DELETE", "/repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by/{dependency}"),
}
```

`MutationRefused` is raised before transmission for any (method, path-template) pair outside that set, for any
`GET` (reads belong to `github_graph`), and for any target that is not in the caller-supplied owned-identity set.
Origin, HTTPS, userinfo and redirect rules are reused from `github_graph.LiveGraphSource` by extracting the
shared `_is_allowed`/`_SameOriginRedirectHandler` logic into a small common base — the read module keeps its own
`WriteAttempted` funnel unchanged.

`github_apply.FakeMutator` applies the same operations to an in-memory `GitHubGraphSnapshot` dict, so the whole
apply path is provable offline against the existing fixtures, with the same request-shape checks the live client
performs. This is the write-side analogue of `FixtureGraphSource`.

### 3. `apply.py` — execute, re-read, record

```text
validated corpus (git revision R)
  -> reconcile (GET-only)      -> RoadmapDiff
  -> plan.py (pure)            -> RoadmapApplyPlan
  -> per operation: GET re-read of exactly its endpoints
       precondition satisfied already  -> alreadySatisfied, no write
       precondition matches plan       -> one allow-listed write -> applied
       anything else                   -> skipped (PreconditionChanged), no write
  -> RoadmapApplyResult (+ audit)
  -> reconcile again           -> expect zero drift
```

Guards, in order:

1. `--execute` is required. Without it the run plans and re-reads and writes nothing.
2. The manifest's git revision is resolved with `git rev-parse HEAD` and `git status --porcelain`; a dirty tree,
   or manifest bytes that differ from the bytes committed at that revision, refuses the run. The audit record
   must be able to say "these bytes, at this revision".
3. If `--approved-sha256` is given (the `RoadmapProposal` approval hash), it must equal the manifest digest from
   `LoadedManifest.sha256`, otherwise `ApprovalHashMismatch` and exit non-zero with zero writes.
4. Before each write, the owned-identity assertion from `plan.py` is re-run against the live operation. Defense in
   depth: a hand-edited plan file cannot widen the target set.
5. A per-run operation cap (`--max-operations`, default 25) bounds blast radius; exceeding it refuses the run
   rather than truncating silently.

`RoadmapApplyResult` per operation: `opId`, `type`, `targets`, `outcome` in
`applied | alreadySatisfied | skipped | failed`, and `reason` for the last two. Plus one `audit` block:

```jsonc
"audit": {
  "actor": "mctl-agents[bot]",
  "proposal": {"id": "...", "url": "..."},          // or null
  "manifest": {"path": "roadmap/epics/human-input.yaml", "sha256": "...", "gitRevision": "<40 hex>"},
  "planId": "...",
  "targets": [{"repository": "mctlhq/mctl-agents", "number": 333}]
}
```

`roadmap-apply-result.schema.json` is `additionalProperties: false` throughout and types every target as the
existing `issueRef` shape, so there is no field an issue title or body could be written into. A
`_forbidden_content_errors()` check runs before emission as a belt-and-braces assertion that no free-text field
carries provider prose. Exit codes: 0 all applied or already satisfied, 1 something skipped, 2 usage/IO/auth,
3 refused, 4 an operation failed.

### 4. LLM containment

`apply.py` accepts no free-form target. Its inputs are a corpus directory, a manifest path inside that corpus, a
snapshot or live flag, and an approval hash. Every mutation target is derived from validated manifest bytes.
A model can influence the graph only by proposing *manifest text* in a pull request that a human merges — the
same review gate that already guards `roadmap/epics/`. There is no path from model output to a GitHub mutation
target that does not pass through a merged, hash-pinned manifest.

### 5. RoadmapProposal integration

The authoring flow `roadmap/README.md` already sketches becomes concrete:

```text
intent
  -> RoadmapProposal              (mctl-api: persistence + authz; adds manifestSha256 + epicDefinitionPullRequest)
  -> roadmap-decompose            (mctl-agents: model step, emits an EpicDefinition draft only)
  -> validate.py against corpus   (draft must pass schema + semantic + corpus validation, offline)
  -> PR to mctlhq/.github roadmap/epics/<name>.yaml
  -> approval bound to sha256 of the exact draft bytes
  -> human merge
  -> RoadmapApplyWorkflow         (mctl-agents: deterministic activity, no model)
```

`roadmap-decompose` is a model step that writes YAML and opens a PR. It never touches a GitHub graph endpoint;
its output is judged by `validate.py`, not trusted. `mctl-api` stays the `RoadmapProposal` persistence and
authorization boundary and stores the approved hash; `mctl-agents` stays the deterministic GitHub mutation
boundary and runs `plan.py` + `apply.py` in an activity with no model invocation. Because approval is bound to
content rather than to a PR number, a force-push after approval changes the digest and invalidates the approval
automatically.

The slice implementable in this repository is the engine and the two contracts. The Temporal workflow in
`mctl-agents` and the `RoadmapProposal` field additions in `mctl-api` are follow-ups against the published
schemas, and are listed as such in `tasks.md`.

### 6. CI

`.github/workflows/roadmap-validate.yml` gains offline steps only, keeping `permissions: {}`: plan the converged
`human-input` fixture and assert an empty operation list, plan a `mutations.py`-drifted copy and assert exactly
one operation, then apply through `FakeMutator` and reconcile again expecting exit 0. Live apply never runs in
CI, for the same reason live read never does.

## Alternatives

**Add a write mode to `github_graph.py` / `reconcile.py --apply`.** Fewer files, and the observed-graph helpers
are right there. Dropped: `github_graph.py`'s value is that it has no mutation primitive to misuse, which is
checkable by reading one function. Putting a writer in the same module replaces that proof with a policy, and
`reconcile.py`'s "never mutates anything" contract — relied on by `health.py`, the CI job and the manual live runs
— would become conditional on a flag.

**Let an agent converge the graph with `gh` / a GitHub MCP tool.** Fast to build and already possible today.
Dropped: it puts an LLM directly in the apply path, which the issue forbids; targets would come from model output
rather than from reviewed bytes; there is no precondition check, so retry duplicates edges; and nothing binds the
action to a manifest hash, so audit could not say which reviewed state authorized the write.

**One GraphQL mutation batch (relations and Projects v2 fields together).** It is the only way to reach Projects
v2 and would cover the whole `Scope` bullet list in one slice. Dropped for the first release: the read side is
REST-only precisely so that its safety property is structural, and a GraphQL document is an open-ended mutation
surface that an allow-list of four endpoints is not. Projects also have no observed representation in
`github-graph-snapshot.schema.json` and no `RoadmapDiff` family, so there is nothing deterministic to converge
until the read side gains them. Projects are deferred to a follow-up that extends the snapshot and diff first.

**Manage the graph with Terraform / the GitHub provider.** Mature drift handling and plan/apply semantics for
free. Dropped: the state file becomes a second desired-state store competing with the manifest, which is exactly
the multiple-representations problem `roadmap/README.md` exists to end; and the provider's issue-relation support
does not cover native sub-issues and blocked-by relations, which are the two things this slice must converge.

## Platform impact

**Migrations.** None to data. Two new schema files and three new scripts under `roadmap/`. No existing schema,
script, manifest or fixture changes shape; `github_graph.py` changes only by extracting its origin-check helper
for reuse, with its `WriteAttempted` funnel and endpoint set untouched.

**Backward compatibility.** `validate.py`, `reconcile.py`, `health.py` and `completion.py` keep their CLIs, exit
codes and output contracts. `RoadmapDiff` gains no field; the plan is a separate document. Existing consumers of
`RoadmapDiff`/`RoadmapHealth` are unaffected. `roadmap/epics/roadmap-control-plane.yaml` needs no edit — #68 is
already bound as `governed-apply`; merging this simply moves it to closed and unblocks `allRequired`.

**Resource impact.** Apply issues at most a few GET re-reads plus one or two writes per drift entry, bounded by
`--max-operations`. Nothing new runs on a schedule. CI gains offline fixture steps measured in seconds and no new
dependency: `jsonschema` and `PyYAML` from `roadmap/requirements.txt` cover it, and the write client uses
`urllib` like the read client.

**Risks and mitigations.**

| risk | mitigation |
| --- | --- |
| A bad merge converges the wrong graph | Apply is merge-triggered and manual, never a cron; refusal on any binding drift; `--max-operations` cap |
| Token with `issues: write` leaks or is misused | Closed (method, path) allow-list; owned-target assertion at plan time and again before each write; same-origin credential rule reused from the read client |
| Graph changed between plan and apply | Per-operation precondition re-read; mismatch is `skipped`, never an overwrite |
| Retry/replay duplicates edges | Precondition already satisfied yields `alreadySatisfied` with zero writes; deterministic `opId` gives a stable idempotency key |
| A `MoveSubIssue` half-completes | The result records the intermediate state and marks the operation `failed` naming the orphaned child; the next replay finishes it; the run exits non-zero |
| Audit leaks issue prose | `additionalProperties: false` result schema with `issueRef`-only targets, plus a pre-emission content check |
| The apply engine is treated as a second source of truth | The engine authors nothing: it never writes a manifest, never creates issues, and never removes children it does not own |
| GitHub sub-issue / dependency API changes | Endpoints are declared in one allow-list constant; `FakeMutator` and live client share the same request-shape assertions, so a drift in the contract fails loudly in one place |
