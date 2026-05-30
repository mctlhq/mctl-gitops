# Design: issue-25-ci-add-claude-review-yml-automated-pr-re

## Current state

`mctlhq/mctl-openclaw` inherits nearly all of its CI from the upstream
`openclaw/openclaw` workflow files. The set of workflows under
`.github/workflows/` (confirmed by directory listing) is:

- `ci.yml` — the main upstream CI pipeline; its `preflight` job is gated on
  `github.repository == 'openclaw/openclaw'` so it skips automatically on the
  fork.
- `mctl-ci.yml` — a lightweight overlay CI that runs only on paths under
  `src/mctl-skills/**`, `src/mctl-identity/**`, `Dockerfile`, and
  `.github/workflows/mctl-ci.yml`.
- `workflow-sanity.yml` — lints all `.github/workflows/*.yml` files with
  `actionlint` and a tab-check script; runs on every PR.
- Approximately 45 other workflow files covering docs, releases, CodeQL,
  labeler, auto-response, etc.

**Absent**: `.github/workflows/claude-review.yml`. There is no reference to
`anthropics/claude-code-action` in any existing workflow file (confirmed by
grep across `.github/workflows/`). The `CLAUDE_CODE_OAUTH_TOKEN` repository
secret is provisioned (per issue body, set 2026-05-27) but currently has no
consuming workflow.

The repository is TypeScript ESM strict-mode, pnpm workspaces, Vitest for
tests, and oxfmt/oxlint for formatting and linting
(`.github/instructions/copilot.instructions.md`). The extension architecture
enforces a hard boundary: extension prod code must not import from
`src/plugin-sdk-internal/**` or sibling extensions' `src/**`; core must not
reach into `extensions/*/src/**` (`CLAUDE.md` / `AGENTS.md` Architecture
section).

The `workflow-sanity.yml` workflow runs `actionlint` on all workflow files in
every PR, so any new workflow added must be valid YAML and pass `actionlint`.
The repo's `.github/actionlint.yaml` config allows the standard GitHub-hosted
runner labels (`ubuntu-24.04`) and is permissive about shellcheck warnings.
`zizmor.yml` disables the `unpinned-uses`, `excessive-permissions`, and
`artipacked` rules, so pinned SHA actions are acceptable but not enforced by
pre-commit; the issue spec requires SHA pinning regardless.

## Proposed solution

Add a single file: `.github/workflows/claude-review.yml`.

### Trigger

```
on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review]
```

Draft PRs are excluded by an explicit `if:` condition on the job (not the
`on:` block), matching the pattern used in `ci.yml` line 44:
`if: ... !github.event.pull_request.draft`.

### Job structure

One job, `claude-review`, running on `ubuntu-24.04` (the runner used by all
other mctl overlay jobs in `mctl-ci.yml` and `workflow-sanity.yml`).

Steps:
1. `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6) — pinned
   SHA as specified in the issue; consistent with how `workflow-sanity.yml`
   references `actions/checkout@v6` (the SHA is the v6 resolution).
2. `anthropics/claude-code-action@51ea8ea73a139f2a74ff649e3092c25a904aed7e`
   (v1) — pinned SHA as specified.

### Action inputs

| Input | Value |
|---|---|
| `claude_code_oauth_token` | `${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}` |
| `model` | `claude-opus-4-8` |
| `allowed_tools` | `mcp__github_inline_comment__create_inline_comment,Bash(gh pr comment:*),Bash(gh pr diff:*),Bash(gh pr view:*)` |
| `prompt` | See review prompt below |

### Review prompt design

The prompt replaces Go-specific guidance with TypeScript ESM guidance drawn
directly from this repo's conventions:

**Trivial-diff short-circuit**: if the diff is documentation-only, changelog-
only, or config-formatting with no logic changes, respond with a single line
noting the trivial scope and skip further analysis.

**Severity classification** (preserved from sister-repo convention):
- P1: correctness bugs, security issues, broken runtime behavior
- P2: design issues, violation of plugin-SDK boundary, type-safety erosion,
  Vitest test convention violations
- P3: style, naming, minor improvements

**TypeScript ESM rules** sourced from `CLAUDE.md` and
`.github/instructions/copilot.instructions.md`:
- No `@ts-nocheck` or broad `@ts-ignore` without explanation
- No `any`; prefer real types, `unknown`, or narrow adapters
- Strict ESM imports: `.js` extension for cross-package imports; `import type`
  for type-only imports
- No static+dynamic import of the same prod module (dynamic-import boundary
  rule)
- Files over ~700 LOC should be flagged as a P2 split candidate

**Plugin-SDK boundary** (from `CLAUDE.md` Architecture):
- Extension prod code must not import `src/**`, `src/plugin-sdk-internal/**`,
  or sibling extension `src/**`
- Core code must not reach into `extensions/*/src/**` or `onboard.js`
- New seams must be backwards-compatible

**Test conventions** (from `CLAUDE.md` Tests):
- Tests must be Vitest (`*.test.ts` colocated, `*.e2e.test.ts` for e2e)
- No Jest flags (`--runInBand`, etc.)
- Mocks must be cleaned up; no leaked timers/globals/module state
- Prefer injection over broad module mocking

### Permissions block

```yaml
permissions:
  contents: read
  pull-requests: write
```

`contents: read` for checkout; `pull-requests: write` for inline comments via
the MCP tool. No other permissions needed.

### Concurrency

```yaml
concurrency:
  group: claude-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

Cancels a queued or in-progress review run when a new commit is pushed to the
same PR (matching pattern from `mctl-ci.yml`).

### Bootstrap caveat handling

No special code is needed in the workflow file itself. The anti-tamper check
in `claude-code-action` compares the workflow file in the PR branch against the
default-branch copy. On the bootstrap PR the file does not exist on `main`, so
the check fails or is skipped. The issue documents this as expected behavior
and instructs the maintainer to merge directly. No `if:` guard or skip label
is needed in the workflow file.

## Alternatives

### Alternative A: use `pull_request_target` instead of `pull_request`

`pull_request_target` runs in the context of the base branch, giving the action
access to repository secrets even for fork PRs. Some claude-code-action
deployments require this. However, `pull_request_target` with code checkout is
a documented security risk (`zizmor` flags it as a dangerous trigger). The
existing `auto-response.yml` uses it with an explicit `zizmor: ignore` comment
and a trusted-base-checkout-only guard. The issue spec does not mention fork PR
support, and `CLAUDE_CODE_OAUTH_TOKEN` is a repository secret that is already
accessible to `pull_request` on non-fork branches (all PRs within
`mctlhq/mctl-openclaw`). Using `pull_request` avoids the `pull_request_target`
security footgun. Rejected.

### Alternative B: copy the workflow verbatim without language-tuning the prompt

The issue explicitly asks to adjust the review prompt for TypeScript ESM rather
than Go. Shipping a Go-tuned prompt would produce irrelevant findings (e.g.,
missing Go error-return checks) on a TypeScript codebase. Rejected.

### Alternative C: add a `paths:` filter to skip non-TS changes

Limiting triggers to `paths: ['src/**', 'extensions/**', 'packages/**', ...]`
would avoid running the reviewer on pure-docs PRs. However, the trivial-diff
short-circuit in the prompt already handles this gracefully, and a `paths:`
filter could silently skip reviews on workflow-only or config-only changes that
also deserve review. The prompt-level short-circuit is more flexible and
visible. Rejected.

## Platform impact

- **New file only**: `.github/workflows/claude-review.yml` is the sole change.
  No existing files are modified.
- **Secret dependency**: the workflow consumes `CLAUDE_CODE_OAUTH_TOKEN` which
  is already present. No new secret provisioning required.
- **CI minutes**: `anthropics/claude-code-action` typically completes in under
  two minutes for typical diffs. `timeout-minutes: 10` caps runaway executions.
  Applies to every non-draft PR going forward.
- **`workflow-sanity.yml` compatibility**: the new file will be linted by
  `actionlint` on its first PR. The file must be valid YAML with no tabs
  (enforced by the tab-check job in `workflow-sanity.yml`). Pinned SHA actions
  satisfy the `zizmor.yml` config (which has `unpinned-uses: disable: true`
  anyway).
- **Backward compatibility**: the change is purely additive. No existing
  workflow, source file, or configuration is altered.
- **Rollback**: delete `.github/workflows/claude-review.yml` from `main` in a
  follow-up commit. The secret is inert without the file.
- **Risk**: low. The only new runtime behavior is that `claude-code-action` is
  invoked on PRs. If the action misbehaves (rate-limited, token expired, API
  error), it fails the workflow step but does not block PR merge unless a branch
  protection rule requires it. The issue does not mention adding a required
  status check for `claude-review`, so failures are advisory.
