# Add claude-review.yml Automated PR-Reviewer Workflow

## Context

`mctlhq/mctl-openclaw` is a fork/overlay of the upstream `openclaw/openclaw`
repository. It does not currently have `.github/workflows/claude-review.yml`,
while sister mctlhq repos (`mctl-agent`, `mctl-api`, `mctl-gitops`) already
ship it. The workflow drives automated PR reviews via
`anthropics/claude-code-action`, consuming the per-repo secret
`CLAUDE_CODE_OAUTH_TOKEN` that was provisioned on 2026-05-27. Until the
workflow file is present, the secret is inert and PRs to this repo receive no
automated review signal.

The implementation is small — a single new workflow file — but the bootstrap
PR that adds it must be merged directly because `claude-code-action` compares
the workflow file in the PR against the copy on `main` and refuses to run when
they differ (anti-tamper check). Every subsequent PR will benefit from live
automated review once the workflow is on `main`.

## User stories

- AS a contributor to `mctlhq/mctl-openclaw` I WANT automated Claude review
  comments on my PR SO THAT I get actionable TypeScript/plugin-SDK feedback
  without waiting for a human reviewer to start.
- AS a maintainer I WANT the review model and allowed-tools to match the other
  mctlhq repos SO THAT the review behavior is consistent and predictable across
  the fleet.
- AS a maintainer I WANT the review prompt tuned to this repo's language and
  architecture SO THAT Claude does not emit irrelevant Go or generic-JS
  findings on TypeScript ESM/Vitest/plugin-SDK code.
- AS a maintainer merging the bootstrap PR I WANT clear documentation that the
  first PR (the one that adds the file) must be merged without waiting for a
  passing claude-review check SO THAT I do not block the rollout on an
  unsatisfiable gate.

## Acceptance criteria (EARS)

- WHEN a pull request against `mctlhq/mctl-openclaw` is opened, reopened,
  synchronized, or marked ready-for-review AND the PR is not a draft THE
  SYSTEM SHALL trigger the `claude-review` workflow job.
- WHILE the PR is in draft state THE SYSTEM SHALL NOT trigger the
  `claude-review` job (draft-skip guard active).
- WHEN the `claude-review` job runs THE SYSTEM SHALL check out the repository
  using `actions/checkout` pinned to SHA
  `de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6).
- WHEN the `claude-review` job runs THE SYSTEM SHALL invoke
  `anthropics/claude-code-action` pinned to SHA
  `51ea8ea73a139f2a74ff649e3092c25a904aed7e` (v1).
- WHEN the action runs THE SYSTEM SHALL pass the secret
  `secrets.CLAUDE_CODE_OAUTH_TOKEN` as `claude_code_oauth_token`.
- WHEN the action runs THE SYSTEM SHALL use model `claude-opus-4-8`.
- WHEN the action runs THE SYSTEM SHALL restrict tool use to
  `mcp__github_inline_comment__create_inline_comment`,
  `Bash(gh pr comment:*)`, `Bash(gh pr diff:*)`, and `Bash(gh pr view:*)`.
- WHEN the review prompt is evaluated THE SYSTEM SHALL instruct the model to
  assess TypeScript ESM strict-mode code (no `@ts-nocheck`, no `any`) and
  Vitest test conventions rather than Go conventions.
- WHEN the review prompt is evaluated THE SYSTEM SHALL instruct the model to
  enforce plugin-SDK boundary discipline: extension prod code must not import
  core `src/**` directly; core must not reach into `extensions/*/src/**`.
- WHEN the review prompt is evaluated THE SYSTEM SHALL instruct the model to
  classify findings as P1 (correctness/security), P2 (design/maintainability),
  or P3 (style/minor).
- WHEN the diff is trivial (documentation-only, changelog-only, config
  formatting) THE SYSTEM SHALL instruct the model to short-circuit and skip
  substantive review output.
- IF the PR that adds `claude-review.yml` is the PR under review THEN THE
  SYSTEM SHALL allow direct merge without a passing claude-review check because
  the anti-tamper mechanism produces an expected non-passing result for
  bootstrap PRs.
- WHEN the workflow file is present on `main` THEN all subsequent PRs SHALL
  receive automated review via the live `CLAUDE_CODE_OAUTH_TOKEN` secret.

## Out of scope

- Changes to any existing `.github/workflows/*.yml` files other than the new
  `claude-review.yml`.
- Changes to TypeScript source code under `src/`, `extensions/`, `packages/`,
  or `ui/`.
- Repository secret creation or rotation (secret already provisioned).
- Modifications to `CODEOWNERS` or protected-branch rules.
- Backfilling automated reviews on already-merged PRs.

## Open questions

- The issue does not specify a `timeout-minutes` for the claude-review job.
  Sister repos use 10 minutes; that value is adopted here as a safe default.
- The issue does not specify a `concurrency` group strategy. The proposal
  adopts `cancel-in-progress: true` scoped to the PR number, matching the
  pattern used in `mctl-ci.yml` and `ci.yml`.
- The issue says "merge directly" but does not specify whether the bootstrap
  PR should use a squash, merge commit, or rebase merge. The proposal assumes
  the repo's default merge strategy (likely squash, common in mctlhq repos)
  and leaves the merge method to the maintainer.
