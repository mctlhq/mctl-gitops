# Allowlist values_path/values_glob and drop 'git add -A' in gitops-bump/release-deploy workflows

## Context

`.github/workflows/gitops-bump.yaml` and `.github/workflows/release-deploy.yaml`
both accept free-form `values_path` / `values_glob` strings via
`workflow_dispatch` and, after patching the image tag, stage changes with
`git add -A` before pushing directly to `main` using a GitHub App token
(`mctl-agents`) that is on the `main-protection` ruleset's bypass list (see
`CLAUDE.md`'s "Branch Protection Exception" section). That bypass is
intentionally scoped to "only ever touch a single `image.tag` field" — but
nothing in the workflow enforces that scope today. Anyone able to dispatch
either workflow (or any automation that constructs the dispatch payload,
e.g. a compromised or buggy caller) can pass a `values_path` like
`.github/workflows/x.yaml` or `../elsewhere` and have the bump job read/write
outside the two directories that actually hold image-tag data. Separately,
`git add -A` stages the entire working tree, not just the file(s) the bump
script touched — if some other process leaves stray modified/untracked files
in the runner's checkout, they get swept into the commit and pushed to `main`
with no review, silently widening the blast radius of every bump commit.

This closes that gap by validating `values_path`/`values_glob` against a
prefix allowlist before any file is read or written, and by replacing
`git add -A` with an explicit `git add -- <resolved files>` so the commit can
only ever contain the file(s) the bump step actually intended to change.

## User stories

- AS the mctl-gitops maintainer I WANT `values_path`/`values_glob` dispatch
  inputs restricted to known gitops-data directories SO THAT a bad or
  malicious dispatch cannot modify arbitrary files (workflow definitions,
  RBAC, secrets wiring) via the branch-protection bypass.
- AS the mctl-gitops maintainer I WANT the bump commit to stage only the
  specific file(s) resolved for this run SO THAT unrelated working-tree state
  can never be swept into a direct-to-main commit.
- AS an app-repo maintainer using Pattern A release automation (see
  `platform-gitops/platform-skills/catalog/mctl-platform/references/deploy.md`)
  I WANT my existing `values_path`/`values_glob` dispatch inputs to keep
  working unchanged SO THAT this hardening does not break my release pipeline.

## Acceptance criteria (EARS)

- WHEN `gitops-bump.yaml` or `release-deploy.yaml` is dispatched with a
  `values_path` or `values_glob` that does not resolve entirely under one of
  the allowlisted prefixes, THE SYSTEM SHALL fail the run before modifying or
  committing any file, with a clear error naming the offending path and the
  allowed prefixes.
- IF `values_path` or `values_glob` contains a `..` path segment or is an
  absolute path (starts with `/`), THEN THE SYSTEM SHALL reject the run with
  a clear error and SHALL NOT attempt to resolve or open the path.
- WHEN a `values_glob` expands to one or more files, THE SYSTEM SHALL
  validate every expanded file path against the allowlist, not just the glob
  pattern string, and SHALL fail the run if any expanded file falls outside
  the allowlist.
- WHEN the bump step has resolved the list of files it actually modified,
  THE SYSTEM SHALL stage exactly those files with `git add -- <file> [...]`
  and SHALL NOT use `git add -A` or `git add .`.
- WHILE either workflow is otherwise unmodified in its trigger, permissions,
  App-token-minting, and tag-bump regex logic, THE SYSTEM SHALL continue to
  support the two current call shapes: default `values_path` derived from
  `platform-gitops/services/<team>/<component>/values.yaml` (release-deploy
  only) and explicit `values_path`/`values_glob` overrides for platform
  bootstrap services and CWFT glob bumps.
- WHEN a caller dispatches with no `values_path`/`values_glob` override and
  `release-deploy.yaml` falls back to its default
  `platform-gitops/services/<team>/<component>/values.yaml`, THE SYSTEM SHALL
  validate that default path against the same allowlist (defense in depth,
  even though it is server-constructed from validated `team_name`/
  `component_name` values).
- IF both `values_path` and `values_glob` are set, THEN THE SYSTEM SHALL
  continue to fail fast on that mutual-exclusivity check, unchanged from
  today, before allowlist validation runs.

## Out of scope

- `auto-merge.yml` path guard (tracked separately, per the issue).
- `platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml`
  (the `mctl_deploy_service`-driven commit path) — its `team_name`/
  `component_name` inputs are already validated server-side by
  `tpl-validate-tenant.yaml` before it ever runs, and it does not accept a
  free-form `values_path`/`values_glob` from the caller, so it is a
  different trust boundary from the two `workflow_dispatch` entry points
  this issue targets.
- Changing who may dispatch these workflows (Actions run permissions,
  branch/environment protection on the dispatch itself) — this proposal only
  narrows what a dispatch is allowed to touch once it runs.
- Changing the `mctl-agents` App's ruleset bypass scope or token permissions.
- Adding new allowlisted prefixes beyond the three identified call shapes
  below unless a real caller is found to need one (see Open questions).

## Open questions

- The issue's suggested allowlist (`platform-gitops/services/` and
  `cluster-templates/`) is incomplete: reading
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`,
  `mctl-api.yaml`, and `mctl-portal.yaml` in this clone shows they each carry
  an `image:`/`tag:` block, and
  `platform-gitops/platform-skills/catalog/mctl-platform/references/deploy.md`
  documents that Pattern A release repos (which include mctl-agent, mctl-api,
  mctl-portal) pass `values_path`/`values_glob` overrides precisely "if that
  repo's gitops values file isn't at the default
  `platform-gitops/services/<team>/<component>/values.yaml`" — i.e. these
  platform-bootstrap services are bumped via `values_path` pointing into
  `platform-gitops/bootstrap/templates/mctl-platform/`, not
  `platform-gitops/services/`. Resolved by adding a third allowlist prefix,
  `platform-gitops/bootstrap/templates/mctl-platform/`, rather than only the
  two the issue names. Also resolved: the actual CWFT/cronworkflow directory
  is `platform-gitops/argo-workflows/cluster-templates/`, not a bare
  `cluster-templates/` — the allowlist uses the full real path so a
  same-named directory elsewhere in the tree can't be used to smuggle a
  match.
- No live caller inventory (e.g. other repos' `release-please.yml` dispatch
  steps) was available in this read-only clone to exhaustively confirm every
  `values_path`/`values_glob` value in current use. The three prefixes above
  are grounded in the files that actually carry `image:`/`tag:` data in this
  repo plus the documented calling convention; if a real caller is found
  post-merge to need a fourth prefix, extend the allowlist in a follow-up PR
  rather than widening it speculatively now.
- Whether validation should live duplicated in each workflow's inline Python
  (matching the existing convention — both workflows already duplicate the
  entire tag-bump regex script rather than sharing a file) or be factored
  into a shared `scripts/*.py` checked into the repo. Resolved in design.md
  in favor of duplication, consistent with existing structure, to avoid
  introducing an asymmetry where one workflow calls a script the other
  doesn't.
