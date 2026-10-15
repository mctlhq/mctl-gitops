# Design: issue-161-ci-roadmap-fail-validation-when-a-change

## Current state
- `roadmap/schemas/epic-definition.schema.json` requires `spec.lifecycle` (enum `proposed|active|paused|completed|archived`, line 37). Each work item requires `id`, `phase` and a boolean `required` (lines 100-106). `issue` is optional: an unbound item instead carries `title` and `owner`, and `validate.semantic_errors` enforces that.
- `roadmap/scripts/validate.py` runs offline and checks three layers: schema, per-manifest semantics and corpus. Its helpers `_load_manifest`, `_load_schema`, `validate_document`, `_manifest_paths` and `DEFAULT_SCHEMA` can be reused. It never reads `lifecycle`. `corpus_errors` makes `metadata.name` unique across `roadmap/epics/*`, so `metadata.name` is a stable epic identity.
- `lifecycle` is read only by `roadmap/scripts/publish.py` (around line 276), which copies it into the RoadmapPublication. `completion.py`, `health.py`, `reconcile.py`, `plan.py` and `ready.py` never read it. `completion.item_status` already treats an unbound item as `incomplete/unbound`, the same notion of "unbound" the guard uses.
- `.github/workflows/roadmap-validate.yml` runs on `pull_request` and on `push` to `main`, filtered to `roadmap/**` and the workflow itself, with `permissions: {}`. It uses `actions/checkout@3d3c42e5...` with no `fetch-depth`, so the checkout is shallow (depth 1). On `pull_request`, that checkout is the synthetic merge commit. The workflow then runs `validate.py roadmap/epics`, offline reconcile/health/ready/plan/apply replays against fixtures, and the unittest suite. Nothing compares against a base.
- `roadmap/tests/mutations.py` holds pure, deep-copying mutators. Most act on GitHubGraphSnapshot fixtures; `unbind(document, ...)` already mutates an EpicDefinition. The tests import it through `sys.path.insert(0, "roadmap/tests")`, and the workflow imports it in the same way.
- Exit-code convention in `roadmap/README.md`: `0` converged, `1` drift, `2` usage/IO/auth/validation error.
- Current corpus: 18 manifests. 12 are `completed` (including `agent-finops.yaml`, whose three required items are all bound), 3 are `paused` and 2 are `active`. So a green run on the current tree exercises the guard heavily.
- The investigation clone is itself shallow (`git rev-parse --is-shallow-repository` = true, one commit, 04a2816). This is exactly the condition under which a base-aware check must fail rather than pass.

Deployed state checked:
- No deployed service is involved. The change is a GitHub Actions workflow plus offline Python scripts in `mctlhq/.github`, with no tenant, hostname or runtime config. I did not call the mctl MCP tools for service config because no service is being changed.
- `$MCTL_GITOPS_ROOT`: I listed it (`README.md`, `agent-platform`, `agents-state`, ...). I did not use it, because no gitops path configures this workflow.
- I could not observe this workflow's past runs or the branch protection settings on `mctlhq/.github` (no GitHub API access in this run). See Open questions.

## Proposed solution

### 1. `roadmap/scripts/lifecycle_guard.py` (new, pure core + thin CLI)
- **CLI**: `lifecycle_guard.py (--base-ref REF | --base-dir DIR) [--head-dir roadmap/epics] [--repo .] [--schema ...]`.
  - Exit `0`: no violations.
  - Exit `1`: violations.
  - Exit `2`: base or head error.
  - Output is one `PASS`/`FAIL <path>` line per head manifest, in the same style as `validate.py`.
- **Base loading** (`load_base_from_git(repo, ref, subdir)`): runs `git` through `subprocess` with fixed argv (no shell).
  1. `git rev-parse --verify --quiet REF^{commit}`. On failure it raises `BaseError("base-unresolvable", ...)`. The message adds a hint when `git rev-parse --is-shallow-repository` is true.
  2. `git ls-tree -z --name-only REF -- roadmap/epics/`, filtered to `*.yaml`/`*.yml`. A non-zero exit raises `base-unreadable`. An empty listing is a valid observation (no manifests in base).
  3. `git show REF:<path>` for each manifest. A failure raises `base-unreadable` naming the path.
  4. Parse with `yaml.safe_load` and run a minimal structural check. Base manifests are NOT validated against the current schema, because a later schema change must not make history unreadable. The check needs: root mapping, `metadata.name` (str), `spec.lifecycle` (str), and `spec.workItems` as a list of mappings, each with a str `id` and a bool `required`. Anything else raises `base-malformed` naming the path.
  `load_base_from_dir(dir)` does the same from a directory. Unit tests use it.
- **Head loading**: uses `validate._manifest_paths`, `validate._load_manifest` and `validate.validate_document`. A failure produces `head-invalid` and exit 2.
- **Pure checker** `check(base: dict[path, doc], head: dict[path, doc]) -> list[Violation]`, where `Violation(code, epic, path, item_ids, message)`:
  - Pair each head epic with a base epic by `metadata.name`, falling back to the same relative path.
  - Skip an epic unless its head `spec.lifecycle == "completed"`. This skips every reopening to `active`/`paused` automatically, including `completed -> active`. It also means a completed epic deleted in head is never visited.
  - Paired: compute `new_required = R_head - R_base`, where `R` is the set of required ids. Ids also present in base with `required: false` become `RequiredFlagRaised`. All other ids in `new_required` become `RequiredItemAdded`. That covers both new items and an item renamed under a new id.
  - Unpaired (born in head) and `completed`: each required item with no `issue` becomes `BornCompletedUnbound`. Bound required items are listed on an informational line ("closure not verified offline"), never stated as closed.
  - The base lifecycle is deliberately not consulted. An `active` base epic flipped to `completed` while it gains required items (the stale-base #152 shape) also fails.
- The error class `BaseError(kind, detail)` is mapped in `main()` to `print(f"{kind}: {detail}", file=sys.stderr)` and return 2.

### 2. `.github/workflows/roadmap-validate.yml`
- Checkout: `with: fetch-depth: 0`. The repo is small, and full history is the simplest way to guarantee that the merge base exists.
- New step "Guard completed epics against new required work", placed right after "Validate EpicDefinition manifests". Values reach the step through `env:` (`EVENT`, `BASE_SHA: ${{ github.event.pull_request.base.sha }}`, `HEAD_SHA: ${{ github.event.pull_request.head.sha }}`, `BEFORE: ${{ github.event.before }}`), never interpolated into the script:
  ```bash
  set -euo pipefail
  if [ "$EVENT" = "pull_request" ]; then
    base=$(git merge-base "$BASE_SHA" "$HEAD_SHA") || { echo "::error::merge-base lookup failed"; exit 1; }
  elif [ -z "$BEFORE" ] || [ "$BEFORE" = "0000000000000000000000000000000000000000" ]; then
    echo "::warning::lifecycle guard: no base commit for this push; guard NOT evaluated"; exit 0
  else
    base="$BEFORE"
  fi
  python3 roadmap/scripts/lifecycle_guard.py --base-ref "$base" --head-dir roadmap/epics
  ```
  The head is the checked-out tree. On `pull_request` that is the merge commit, i.e. what would land.
- `permissions: {}` is unchanged. The guard does no network I/O.

### 3. Tests
- `roadmap/tests/test_lifecycle_guard.py` builds small in-memory manifests (same base shape as `test_validate.py::_base`) and runs `check()` directly. It also runs `main()` against temp git repos (`git init`, commit base, commit head) to cover `--base-ref`, an unknown SHA, a shallow clone (`git clone --depth 1 file://...`) and a malformed or unreadable base blob.
- `roadmap/tests/mutations.py` gains pure manifest mutators: `add_required_item(document, item_id, phase, title, owner, issue=None)`, `set_required(document, item_id, value)` and `set_lifecycle(document, value)`. The #152 mutation is `add_required_item(agent_finops, "trajectory-economics", ...)` on the real `roadmap/epics/agent-finops.yaml`. Tests assert that `check()` is empty on the corpus against itself, that it is `RequiredItemAdded` on the mutation, and that it is empty again after `set_lifecycle(..., "active")`.

### 4. `roadmap/README.md`
One paragraph under `## Validation`: what the guard compares (merge base vs head on PRs, `before` vs head on pushes), the three violation codes, that an unreadable base fails with exit 2, and the two legitimate ways to extend a completed epic (add the item with `required: false`, or set `lifecycle: active`/`paused` in the same change).

## Alternatives
- **Add the rule to `validate.py`, reading only the final tree**: dropped. The final tree cannot distinguish an item added after completion from one that was always there, which is the core point of the issue. A tree-only rule like "completed epics may not have unbound required items" would pass #152 if the new item had been bound to an open issue.
- **A state-based completion check (`lifecycle: completed` vs `completion.py` outcome) instead**: dropped as a substitute. It needs live or snapshot GitHub state, which CI does not have (`permissions: {}`, no token, offline replays only). It is also complementary, not equivalent: it is the out-of-scope follow-up.
- **Compare against `github.event.pull_request.base.sha` directly, or use `git diff` text hunks**: comparing against `base.sha` directly can include unrelated main-line commits. Text-diff parsing is brittle against YAML reformatting. Semantic comparison of parsed manifests at the merge base is robust and is what the issue asks for.
- **Targeted `git fetch --depth=... origin $BASE_SHA` instead of `fetch-depth: 0`**: viable, but the depth needed for `merge-base` is unknown in general, and a too-shallow fetch would fail (closed, but noisily). Full history is cheap for this repo.

## Platform impact
- **Migrations**: none. No schema or manifest changes. The current corpus passes against its own parent, because no completed epic gains required items.
- **Backward compatibility**: new failures appear only for the violating shapes. Authors who extend completed epics must use `required: false` or reopen the epic, and the README documents both.
- **Resources**: `fetch-depth: 0` adds seconds to the checkout. The guard does about 20 `git show` calls.
- **Risks and mitigations**:
  - Push with an all-zero `before`. Mitigation: an explicit warning annotation, not a pass claim.
  - A stale PR base, where main completes an epic after the PR's last run. Mitigation: the rule ignores the base lifecycle, so the merge-commit head still fails on re-run, and the post-merge `push` run against `before` catches it on `main`. Requiring up-to-date branches would close the gap fully (Open questions).
  - A rename of `metadata.name` together with a file move evades pairing. Mitigation: the born-completed rule still catches unbound required items. This is documented.
  - `pull_request` from forks: `fetch-depth: 0` and `merge-base` work with no token.

## Open questions
- Born-completed manifests with bound required items: offline closure is unverifiable. The proposal fails only unbound ones and prints the rest as "not verified". Should a snapshot or live verification be required instead?
- Whether `mctlhq/.github` branch protection requires branches to be up to date before merging. I could not observe this. If it does not, the stale-base window is closed only by the post-merge `push` run.
- The meaning of "red again when the guard step is removed" (see requirements.md Open questions).
