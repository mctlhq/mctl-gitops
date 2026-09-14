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

`validate.py` owns structural validation, per-manifest graph invariants, and corpus invariants. `validate_document()` checks one manifest; `corpus_errors()` checks corpus-wide uniqueness of `metadata.name` and GitHub issue bindings. CI is deliberately offline and runs with `permissions: {}`.

What is missing is observed-state reconciliation: read the native GitHub graph, normalize it, compare it to desired state, and emit a deterministic machine-readable diff.

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

The reconciler separates the **canonical corpus** from the **selected reconciliation targets**.

Default corpus root:

```text
roadmap/epics/
```

Before any network access:

```text
load canonical corpus
  → validate_document(each corpus manifest)
  → corpus_errors(all corpus manifests)
  → select requested manifest(s) for reconciliation
  → only then derive desired graph / read GitHub
```

A CLI request for one manifest therefore cannot bypass globally unique `metadata.name` or GitHub-binding ownership. Tests may inject a temporary corpus root explicitly. Any schema, semantic, or corpus failure exits 2 and performs zero GitHub reads.

### Layer 1 — desired graph (`reconcile.py`)

`desired_graph(document)` runs only after validation succeeds. It produces:

- `bindings`: work-item id → authored issue key;
- `hierarchy`: `(parent, child)` edges; root is `spec.github.issue` when `parent` is absent;
- `dependencies`: `(blocked, blocker)` edges from `dependsOn` plus `externalDependsOn`;
- suppressions for intentionally unbound items.

Repository comparison is case-insensitive. `spec.phases` never creates an edge.

### Layer 2 — provider-neutral observed snapshot (`github_graph.py`)

Snapshots carry explicit provenance so synthetic fixtures cannot masquerade as live evidence.

Live capture:

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

Synthetic fixture:

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

A synthetic fixture does not carry a live `capturedAt` claim. If no immutable live capture exists, `derivedFrom` is omitted.

### Layer 3 — live GitHub adapter: REST GET-only

The live adapter intentionally does **not** use GraphQL. Every request is GET, every request body is absent, and any attempt to construct a non-GET request raises before transmission.

For each referenced issue:

```text
GET /repos/{owner}/{repo}/issues/{number}
GET /repos/{owner}/{repo}/issues/{number}/parent
GET /repos/{owner}/{repo}/issues/{number}/sub_issues
GET /repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by
```

The `/parent` route is verified against GitHub's official REST documentation: **Get parent issue** is exposed at exactly `GET /repos/{owner}/{repo}/issues/{issue_number}/parent`, requires only `Issues: read` for private resources, and documents 200/301/404/410 responses. This closes the prior P3 uncertainty; the implementation should use the normal GitHub REST API-version header already used by the repository/client.

The issue GET supplies existence/state and requested-vs-resolved identity for redirects/transfers. The requested key is recorded from the request URL before transmission, never from the response, because a 301 on a transferred issue may be followed by the HTTP client before any response reaches the adapter; the resolved key is then derived from the response body's `repository_url` and `number`, not from the final request URL. A redirect is therefore detected by comparing those two recorded keys, which works identically whether the client follows the 301 or surfaces it. All requests funnel through one helper; tests inject a stub opener and prove GET-only/no-body behavior.

CI never runs live mode.

### Layer 4 — normalization and redirect semantics

`observed_graph(snapshot)` lowercases repository identity for comparison, sorts/deduplicates relations, drops self-edges, and builds a canonical graph representation.

Resolution produces:

```text
requested issue key -> resolved canonical issue key
```

For a transfer/redirect:

1. emit one `BindingRedirected` containing requested and resolved identities;
2. rewrite desired hierarchy/dependency endpoints through the resolution map;
3. compare those relations using the resolved canonical key;
4. do **not** suppress relations merely because a redirect occurred.

Suppression is reserved for unresolved/ambiguous bindings and intentionally unbound desired work. This keeps stale binding drift visible without creating fake secondary hierarchy/dependency drift.

### Layer 5 — deterministic diff

`diff(desired, observed)` returns separate collections:

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

Binding results are computed first. Unresolved/ambiguous endpoints suppress dependent comparisons; redirected endpoints are canonicalized and continue through relation comparison.

Determinism is part of the contract: exact manifest-byte SHA-256, stable sort keys, source metadata copied from the snapshot, no generated diff timestamp/randomness, and byte-identical JSON for identical inputs.

### Layer 6 — fixture model and mutation tests

The green fixture is explicitly synthetic:

```text
roadmap/fixtures/human-input/converged-fixture.json
```

If a real capture is useful, keep it separately as:

```text
roadmap/fixtures/human-input/live-capture.json
```

and never hand-edit it to make tests pass.

Mutation tests derive red cases from the synthetic green fixture, including parent, dependency, binding, and redirect cases, then restore and assert green again.

### Layer 7 — CLI and CI

CLI shape:

```text
python roadmap/scripts/reconcile.py roadmap/epics/human-input.yaml \
  --corpus roadmap/epics \
  --snapshot roadmap/fixtures/human-input/converged-fixture.json
```

`--corpus` defaults to `roadmap/epics`; it mainly exists so tests can inject a temporary corpus. Positional manifests select which valid corpus members are diffed, not which documents participate in corpus invariants.

Modes:

- `--snapshot`: offline fixture/capture replay;
- `--live`: GET-only GitHub read;
- `--capture`: live mode plus snapshot write;
- `--output`: optional diff destination.

Exit codes: 0 converged, 1 drift, 2 usage/IO/auth/validation error.

`.github/workflows/roadmap-validate.yml` adds only offline fixture reconciliation. `permissions: {}` remains unchanged and no secret is introduced.

## Alternatives rejected

1. **GraphQL for sub-issues.** Rejected because the slice's safety contract is HTTP GET-only.
2. **Corpus validation only across positional inputs.** Rejected because selecting one manifest must not bypass globally unique desired ownership.
3. **Suppress redirected bindings.** Rejected because a resolvable transfer has a canonical identity; canonicalize and compare instead.
4. **Hand-edit a captured snapshot into a converged fixture.** Rejected because the result would no longer be live evidence.
5. **Read live GitHub state in CI.** Rejected because it requires external state and makes tests non-deterministic.
6. **Implement write reconciliation now.** Rejected; detector correctness comes first.
7. **Parse dependency prose.** Rejected; only native relations are authoritative.

## Platform impact

- No migration and no authored `EpicDefinition` schema change.
- No new runtime dependency.
- Fixture mode is offline CPU work.
- Live mode is O(issues) REST GET traffic.
- No write capability exists in the module.
- A later `mctl-agents` workflow can invoke the detector; write/apply stays a separate governed phase.

## Risks and mitigations

- **GitHub REST relation shape changes:** isolate provider details in `LiveGraphSource`.
- **Transferred issues:** preserve requested/resolved identities, emit `BindingRedirected`, canonicalize relation comparison to the resolved key.
- **False cascades:** only unresolved/ambiguous bindings suppress dependent comparisons.
- **Fixture rot:** synthetic green fixture proves detector behaviour, not live truth; optional live capture is separate evidence.
- **Future apply misuse:** no mutation primitive exists in this slice.
