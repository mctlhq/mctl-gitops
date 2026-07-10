---
name: git-flow
description: "Apply a standard non-interactive git workflow for isolated repository changes: create or use a feature branch, commit cleanly, optionally create and push a release tag when the task depends on a tagged version, rebase on origin/main, fast-forward merge to main, and push. Use when asked to make repository changes and the user expects disciplined git hygiene without interactive git commands."
user-invocable: true
---

# Git Flow

Use a standard non-interactive git flow for repository changes.

## Workflow

1. Create or switch to an isolated working branch for the task.
2. Make the requested changes without reverting unrelated user edits.
3. Stage only the intended files.
4. Create a single clear commit unless the user asked for a different history shape.
5. If the task depends on a versioned release or a platform deploy by repo tag, create and push a new git tag after the commit and report the exact tag name.
6. Fetch `origin/main`.
7. Rebase the working branch onto `origin/main`.
8. Fast-forward merge the branch into `main`.
9. Push the updated `main`.

## Rules

- Prefer non-interactive git commands only.
- Never use destructive commands such as `git reset --hard` unless the user explicitly asked for them.
- If the worktree contains unrelated changes, leave them intact and isolate only the task-specific changes.
- If rebase or merge surfaces a conflict with user changes, stop and resolve carefully rather than discarding anything.
- When a deployment pipeline consumes a repository tag, do not reuse an old tag. Create a fresh tag that points at the intended release commit and push it explicitly.
- If the user only asked for code changes and did not ask for commit/push, do not force the full workflow.
- Tags use semantic versioning without a `v` prefix (`1.3.0`, not `v1.3.0`).

## Expected Result

Report the branch used, the commit created, any tag created, whether rebase and fast-forward merge succeeded, and whether `main` was pushed.
