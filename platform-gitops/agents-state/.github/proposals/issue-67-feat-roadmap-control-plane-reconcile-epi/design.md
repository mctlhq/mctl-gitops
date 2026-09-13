# Design: issue-67-feat-roadmap-control-plane-reconcile-epi

## Current state

`mctlhq/.github` already contains the declarative roadmap contract and offline validation path:

```text
roadmap/README.md
roadmap/requirements.txt
roadmap/schemas/epic-definition.schema.json
roadmap/epics/human-input.yaml
roadmap/scripts/validate.py
roadmap/tests/test_validate.py
.github/workflows/roadmap-validate.yml
```

`validate.py` owns structural validation, per-manifest graph invariants, and corpus invariants. The important split is that `validate_document()` checks one manifest, while `corpus_errors()` checks uniqueness across manifests (`metadata.name` and GitHub issue bindings). The current CI is deliberately offline and runs with `permissions: {}`.

What is missing is observed-state reconciliation: read the native GitHub graph, normalize it, compare it to the desired graph, and emit a deterministic machine-readable diff.

## Proposed solution

Add a read-only reconciler alongside the validator. Keep it stdlib-first, offline-testable, and incapable of GitHub writes.

New files:

```text
roadmap/schemas/github-graph-snapshot.schema.json
roadmap/schemas/roadmap-diff.schema.json
roadmap/scripts/github_graph.py
roadmap/scripts/reconcile.py
roadmap/fixtures/human-input/live-capture.json          # optional immutable evidence capture
roadmap/fixtures/human-input/converged-fixture.json     # synthetic green test fixture
roadmap/tests/test_reconcile.py
roadmap/tests/mutations.py
```

Modified files:

```text
.github/workflows/roadmap-validate.yml
roadmap/README.md
```

No new pip dependency is required.

### Layer 0 — validation preflight

`reconcile.py` loads all selected manifests before any network access. For each manifest it runs the same schema + semantic validation as today. Then it runs the existing corpus invariants across the whole selected set.

The key rule is:

```text
load selected manifests
  → validate_document(each)
  → corpus_errors(all valid selected manifests)
  → only then derive desired graph / read GitHub
```

This prevents a reconciler run from bypassing the global invariant that one GitHub issue may bind to at most one authored work item across the manifest corpus. Any schema, semantic, or corpus failure exits 2 and performs no GitHub read.

### Layer 1 — desired graph (`reconcile.py`)

`desired_graph(document)` runs only after validation succeeds. It produces:

- `bindings`: work-item id → canonical issue key;
- `hierarchy`: `(parent, child)` edges; root is `spec.github.issue` when `parent` is absent;
- `dependencies`: `(blocked, blocker)` edges from `dependsOn` plus `externalDependsOn`;
- suppressions for relations touching intentionally unbound items.

Repository comparison is case-insensitive, but authored spelling may be retained for display. `spec.phases` never creates an edge.

### Layer 2 — provider-neutral observed snapshot (`github_graph.py`)

The snapshot schema is independent of GitHub transport details. It carries explicit provenance so synthetic fixtures cannot masquerade as live evidence.

Example live capture:

```json
{
  "apiVersion": "roadmap.mctl.ai/v1alpha1",
  "kind": "GitHubGraphSnapshot",
  "source": {
    "mode": "live-capture",
    "capturedAt": "2026-09-13T19:00:00Z",
    "apiBase": "https://api.github.com"
  },
  "issues": []
}
```

Example synthetic fixture:

```json
{
  "apiVersion": "roadmap.mctl.ai/v1alpha1",
  "kind": "GitHubGraphSnapshot",
  "source": {
    "mode": "synthetic-fixture",
    "derivedFrom": "live-capture.json"
  },
  "issues": []
}
```

A synthetic fixture does not carry a live `capturedAt` claim. If no immutable live capture is committed, `derivedFrom` is omitted.

Two sources implement one protocol:

- `FixtureGraphSource(path)` loads a schema-valid snapshot without network access.
- `LiveGraphSource(token, api_base)` uses GitHub REST GETs only.

### Layer 3 — live GitHub adapter: REST GET-only

The live adapter intentionally does **not** use GraphQL in this slice. The safety contract is expressed at the HTTP method level and stays literal: every request is GET, every request body is absent, and any attempt to construct a non-GET request raises before transmission.

For each referenced issue the adapter uses the native REST surfaces:

```text
GET /repos/{owner}/{repo}/issues/{number}
GET /repos/{owner}/{repo}/issues/{number}/parent
GET /repos/{owner}/{repo}/issues/{number}/sub_issues
GET /repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by
```

The issue GET supplies existence/state and the canonical/final identity needed for redirect/transfer detection. Redirect handling must retain both the originally requested key and the final resolved key so the diff can emit `BindingRedirected` rather than collapsing a transfer into `BindingIssueNotFound`.

All requests funnel through one helper. Tests inject a stub opener and assert:

- only GET is ever sent;
- no request body is sent;
- forcing any other method/body raises `WriteAttempted` before I/O.

The adapter requires only read access (`issues: read`; `contents: read` is sufficient for manifest/content reads when used by a later runtime). CI in this repository never supplies a token and never runs live mode.

`--capture <path>` is a live-operator action that writes a `source.mode: live-capture` snapshot. A committed live capture is evidence and is not hand-converged in place.

### Layer 4 — normalization

`observed_graph(snapshot)` lowercases repository identity for comparison, sorts and deduplicates relation lists, drops self-edges, and builds a canonical graph representation.

A `found: false` issue becomes a binding failure and marks dependent desired edges as suppressed. The normalizer also detects impossible/ambiguous parent data rather than arbitrarily picking one parent.

### Layer 5 — deterministic diff

`diff(desired, observed)` returns three separate collections:

| collection | type | meaning |
| --- | --- | --- |
| binding | `BindingIssueNotFound` | bound issue absent |
| binding | `BindingRedirected` | requested issue resolves to another canonical repo/number |
| binding | `BindingAmbiguous` | binding/parent observation is ambiguous |
| binding | `BindingUnbound` | informational desired work without issue binding |
| hierarchy | `HierarchyMissingParent` | expected parent edge missing |
| hierarchy | `HierarchyWrongParent` | child has a different observed parent |
| hierarchy | `HierarchyUnexpectedChild` | informational observed child not owned by manifest |
| dependency | `DependencyMissing` | expected blocked-by edge missing |
| dependency | `DependencyUnexpected` | observed blocked-by edge not authored |

Binding entries are computed first. Any desired relation that depends on an unresolved/ambiguous endpoint is suppressed from hierarchy/dependency comparison so one bad binding cannot create a cascade of fake drift.

Determinism is part of the contract:

- exact manifest bytes → SHA-256 in `RoadmapDiff`;
- stable sort keys for every collection;
- no generated timestamp in the diff;
- source metadata copied from the snapshot;
- `json.dumps(..., sort_keys=True, indent=2)`;
- identical manifest + snapshot bytes produce byte-identical output.

### Layer 6 — fixture model and mutation tests

The green fixture is explicitly synthetic:

```text
roadmap/fixtures/human-input/converged-fixture.json
```

It represents the desired fully converged graph even if the real GitHub graph is not currently converged. It may be derived from a real capture, but it must be marked `source.mode: synthetic-fixture` and never pretend to be the captured state.

If a real capture is useful for audit/debugging, keep it separately as:

```text
roadmap/fixtures/human-input/live-capture.json
```

and never hand-edit it to make tests pass.

`roadmap/tests/mutations.py` derives all red cases from the single synthetic green fixture. Tests mutate one parent edge, one dependency edge, or one binding, assert only the expected family turns red, then restore and assert green again.

### Layer 7 — CLI and CI

CLI shape:

```text
python roadmap/scripts/reconcile.py roadmap/epics/human-input.yaml \
  --snapshot roadmap/fixtures/human-input/converged-fixture.json
```

Modes:

- `--snapshot`: offline fixture/capture replay;
- `--live`: GET-only GitHub read using token from environment;
- `--capture`: live mode plus snapshot write;
- `--output`: optional diff destination.

Exit codes:

- `0`: no drift-severity entries;
- `1`: drift detected;
- `2`: usage/IO/credentials/schema/semantic/corpus validation error.

`.github/workflows/roadmap-validate.yml` adds only an offline fixture reconciliation step. `permissions: {}` remains unchanged and no secret/token is introduced.

## Alternatives rejected

1. **GraphQL for sub-issues.** Rejected for this slice because it conflicts with the explicit HTTP GET-only safety contract. REST exposes the required native issue, parent, sub-issue, and blocked-by reads and makes redirect/transfer handling explicit.
2. **Only call `validate_document()` per manifest.** Rejected because it bypasses existing corpus invariants and allows duplicate desired ownership across selected manifests.
3. **Hand-edit a captured snapshot into a converged test fixture.** Rejected because the resulting artifact would no longer be live evidence while still carrying live provenance. Synthetic and captured artifacts are separate.
4. **Read live GitHub state in CI.** Rejected because the pilot spans repositories, would require a token, and would make green/red tests non-deterministic.
5. **Implement write reconciliation now.** Rejected; this issue proves detector correctness first.
6. **Parse `Depends on` prose.** Rejected; only native relations are authoritative for this detector.

## Platform impact

- No migration and no authored `EpicDefinition` schema change.
- `validate.py` keeps its current contract; reconciliation reuses its validation/corpus invariants rather than forking them.
- No new runtime dependency.
- Fixture mode is pure offline CPU work.
- Live mode is O(issues) REST GET traffic and remains comfortably inside normal rate limits for the pilot.
- No write capability exists in the module.
- A later `mctl-agents` workflow can invoke this proven detector, but write/apply remains a separate governed phase.

## Risks and mitigations

- **GitHub REST relation shape changes:** isolate all provider details in `LiveGraphSource`; detector/tests consume the provider-neutral snapshot contract.
- **Transferred issues:** issue GET preserves requested vs canonical resolved identity and emits `BindingRedirected`.
- **False cascades:** binding failures suppress dependent edge comparisons.
- **Fixture rot:** synthetic green fixture proves detector behaviour, not live truth; optional live capture can be regenerated independently.
- **Future apply misuse:** no mutation primitive exists here, and mutation tests remain a prerequisite for enabling writes elsewhere.
