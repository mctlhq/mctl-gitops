# Design: issue-161-ci-roadmap-fail-validation-when-a-change

## Current state

Verified against current `mctlhq/.github` main.

- `roadmap/schemas/epic-definition.schema.json` requires `spec.lifecycle`; each work item requires `id`, `phase` and boolean `required`, while `issue` is optional.
- `roadmap/scripts/validate.py` validates schema, per-document semantics and corpus invariants, but does not compare lifecycle changes against a base tree.
- `.github/workflows/roadmap-validate.yml` runs on roadmap/workflow changes with `permissions: {}` and currently checks out shallow history, then validates only the final tree.
- The failure in #152 is therefore invisible to the current CI: an older PR can add required work while a concurrent main-line change marks the epic completed.

The guard must be semantic and diff-aware, and it must fail closed when the base or the property it needs cannot be observed.

## Proposed solution

### 1. `roadmap/scripts/lifecycle_guard.py`

Add a pure checker plus a thin CLI:

```text
lifecycle_guard.py (--base-ref REF | --base-dir DIR)
                   [--head-dir roadmap/epics]
                   [--repo .]
                   [--schema ...]
```

Exit codes follow the roadmap convention:

- `0`: evaluated, no violations;
- `1`: lifecycle invariant violation;
- `2`: base/head could not be evaluated safely.

#### Base loading from Git

`load_base_from_git(repo, ref, subdir)` uses fixed argv with no shell:

1. Resolve `REF^{commit}` with `git rev-parse --verify --quiet`. Failure is `base-unresolvable`; include a shallow-checkout hint when applicable.
2. Enumerate the manifest tree **recursively** with `git ls-tree -rz --name-only REF -- roadmap/epics/`, then keep only paths ending in `.yaml` or `.yml`. The `-r` is required: without it, Git may return the directory tree entry rather than its manifest blobs, which would make an existing base look empty. The extension filter is required too: a non-manifest file under `roadmap/epics/` at the base (a `README`, a `.gitkeep`) is not a manifest and must not reach the structural check, or the guard would exit 2 on something that is not a lifecycle violation. A non-zero `ls-tree` exit is `base-unreadable` and names the subdir. An empty filtered listing after a successful `ls-tree` is a valid observation (no manifests in base), not an error.
3. Read each YAML blob with `git show REF:<path>`. Failure is `base-unreadable` and names the path.
4. Parse YAML and perform the minimal historical structural validation needed by this guard: mapping root; `metadata.name`; `spec.lifecycle`; `spec.workItems`; each item has string `id` and boolean `required`. Historical manifests are not forced through today's full schema. Invalid historical input is `base-malformed`.

`load_base_from_dir` provides the same structure for unit tests.

#### Head loading

Load current manifests with the existing `validate` helpers.

The guard must run both:

- `validate.validate_document` for each manifest; and
- `validate.corpus_errors` for the whole head corpus.

Any failure is `head-invalid` / exit 2. In particular, duplicate `metadata.name` values must never make pairing ambiguous.

#### Pairing and violations

Pair a head epic to the base by `metadata.name`, falling back to the same relative path.

Only a head epic whose lifecycle is `completed` is checked. Reopening to `active` or `paused` in the same change therefore explicitly opts out of the completed invariant.

For a paired epic:

- `RequiredItemAdded`: an id is required in head and absent from the base required set;
- `RequiredFlagRaised`: the id existed in base with `required: false` and is `required: true` in head.

For a manifest with no base counterpart that is born `completed`:

- if it has **any** `required: true` work item, report `BornCompletedUnverified`.

This is intentionally stricter than checking only whether `issue` is present. The offline job cannot prove that a bound GitHub issue is closed, and `bound != closed`. Treating a bound required item as safe would violate the same "could not observe" principle the check is meant to enforce.

A legitimate new epic with required work must first land as `active` or `paused`; a later reviewed lifecycle transition to `completed` happens after the normal roadmap state/completion evidence exists.

Deleted head manifests are ignored. Removing required work or lowering `required` does not violate the guard.

The base lifecycle is deliberately not used to waive a violation: an active base that becomes completed in the merge result while gaining required work is exactly the stale-PR shape this guard must catch.

### 2. `.github/workflows/roadmap-validate.yml`

Set checkout `fetch-depth: 0` so the required base commits and merge base are available.

Keep `permissions: {}` and perform no network/API calls from the guard.

For pull requests:

- pass base/head SHAs through `env:`;
- compute `git merge-base "$BASE_SHA" "$HEAD_SHA"`;
- a failed merge-base lookup fails the job;
- run `lifecycle_guard.py --base-ref "$base"` against the checked-out merge-result tree.

For normal pushes to main:

- use `github.event.before` as the base ref.

For an all-zero `github.event.before`, use **two workflow steps** rather than exiting 0 from the guard step:

1. a notice step, conditionally run only for the zero-base case, emits `::warning::lifecycle guard: no base commit for this push; guard NOT evaluated`;
2. the real guard step has an `if:` condition that makes it **skipped** for that case.

This distinction matters: a shell `exit 0` inside the guard step would render that check green, contradicting the requirement that an unevaluated guard must not be reported as passed.

### 3. Tests

Add `roadmap/tests/test_lifecycle_guard.py` and pure manifest mutators in `roadmap/tests/mutations.py`.

Coverage includes:

- unchanged corpus;
- #152 required-item mutation;
- optional addition;
- optional -> required;
- reopen to active and paused;
- stale-base shape (base active, head completed + new required item);
- new completed manifest with unbound required work;
- new completed manifest with a **bound** required item, which still fails `BornCompletedUnverified` because closure is not observable offline;
- deletion/removal/lowering required;
- path move with stable `metadata.name`;
- unknown/shallow base;
- malformed/unreadable base;
- invalid/duplicate head corpus;
- recursive base enumeration with multiple manifests under `roadmap/epics/`, so removing `-r` from `git ls-tree` breaks a test;
- no-op/revert mutation proving the guard is load-bearing.

### 4. README

Document under `## Validation`:

- merge-base/head comparison on PRs and before/head on pushes;
- `RequiredItemAdded`, `RequiredFlagRaised`, `BornCompletedUnverified`;
- exit 2 on unobservable base/head;
- legitimate extension paths: add optional work, or reopen the completed epic to active/paused;
- a new epic with required work must not be introduced already completed because this offline guard cannot prove closed state.

## Evidence plan

The PR must show:

1. current/converged input is green;
2. the #152 mutation is red with `RequiredItemAdded`;
3. the same mutation with the guard workflow step removed becomes green, proving the guard is the control that catches it;
4. a unit-level no-op/revert of `check()` breaks the mutation assertion;
5. #162 rebased on current main remains green.

Do not describe item 3 as "red when the guard is removed"; that would be logically impossible.

## Alternatives rejected

- **Final-tree-only validation:** cannot identify required work added after completion.
- **Use binding as proof of closure for a born-completed epic:** rejected; an issue reference proves identity, not closed state.
- **Live GitHub lookup in CI:** rejected for this issue; the workflow intentionally has `permissions: {}` and is offline.
- **State-based `completed` vs computed completion check:** complementary follow-up, not a substitute for this diff-aware guard.
- **Text diff parsing:** brittle under YAML reformat/moves; semantic manifest comparison is the intended boundary.

## Platform impact

- No migrations, schema, runtime or GitOps changes.
- Full-history checkout adds modest CI cost.
- Existing completed epics are unaffected unless a change grows their required set while leaving them completed.
- New completed manifests with required work become intentionally stricter: introduce them active/paused, then complete them through the normal observed-state path.
- Rollback is a normal revert of the script/tests/workflow/README changes.
