---
name: git-flow
description: "Apply a standard non-interactive git workflow for isolated repository changes: create a feature branch, commit cleanly, open a PR, pass the review gate, merge with a merge commit, and optionally create and push a release tag when the task depends on a tagged version. Use when asked to make repository changes and the user expects disciplined git hygiene without interactive git commands."
user-invocable: true
---

# Git Flow

Use a standard non-interactive git flow for repository changes.

## Workflow (mctlhq repos — default)

Every mctlhq repository forbids direct commits to `main`; the git graph must
show the merge-commit pattern, not a flat line.

1. Create or switch to an isolated feature branch for the task
   (`feat/description`, `fix/`, `ci/`, `docs/`, `chore/`).
2. Make the requested changes without reverting unrelated user edits.
3. Stage only the intended files.
4. Create a single clear commit unless the user asked for a different history shape.
5. Push the branch and open a PR: `gh pr create`.
6. Wait for CI and the review gate (Claude review for non-trivial changes;
   0 unaddressed P1/P2 findings).
7. Merge with a merge commit: `gh pr merge <N> --merge --delete-branch`
   (never squash).
8. If the task depends on a versioned release or a platform deploy by repo
   tag, create and push a new git tag after the merge and report the exact
   tag name.

## Fallback (repos WITHOUT PR infrastructure only)

Only for personal/external repositories that have no CI, no review bot, and no
branch protection (never for mctlhq repos): rebase the feature branch onto
`origin/main`, fast-forward merge it into `main`, and push `main` directly.
If unsure whether a repo qualifies, use the PR workflow.

## Rules

- Prefer non-interactive git commands only.
- Never use destructive commands such as `git reset --hard` unless the user explicitly asked for them.
- If the worktree contains unrelated changes, leave them intact and isolate only the task-specific changes.
- If rebase or merge surfaces a conflict with user changes, stop and resolve carefully rather than discarding anything.
- When a deployment pipeline consumes a repository tag, do not reuse an old tag. Create a fresh tag that points at the intended release commit and push it explicitly.
- If the user only asked for code changes and did not ask for commit/push, do not force the full workflow.
- Tags use semantic versioning without a `v` prefix (`1.3.0`, not `v1.3.0`); exception: mctl-openclaw keeps upstream `v`-prefixed tags.

## Expected Result

Report the branch used, the commit created, the PR number and its review
outcome, any tag created, and whether the merge succeeded (or, in the
fallback path, whether rebase, fast-forward merge, and push succeeded).
