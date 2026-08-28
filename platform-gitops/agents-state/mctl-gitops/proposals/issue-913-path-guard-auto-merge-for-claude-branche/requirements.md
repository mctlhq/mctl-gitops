# Path-guard auto-merge for claude/* branches

## Context

`.github/workflows/auto-merge.yml`'s `auto-merge` job merges any PR whose
head branch starts with `claude/` as soon as one review is submitted with
state `approved` (`pull_request_review` / `submitted`), with `gh pr merge
--merge --delete-branch`. The condition only inspects the branch name
(`startsWith(github.event.pull_request.head.ref, 'claude/')`) — it never
looks at which files the PR actually touches. A `claude/*` PR that edits
`.github/workflows/**`, `platform-gitops/bootstrap/**`, or secrets-wiring
(`ExternalSecret` manifests, Vault paths, RBAC) gets the exact same
one-approval fast path as a routine `platform-gitops/services/**` values
bump.

This matters because `claude/*` is the default branch prefix produced by
interactive Claude Code sessions (see `labs/claude-remote`), not a
curated, narrowly-scoped automation identity like the `feat/agents-*`
implementer branches or the `agent/optimize/*` optimizer branches (the
latter is deliberately kept off `claude/*` specifically so it stays
review-gated — `platform-gitops/services/labs/mctl-agent/values.yaml`
line ~89: "Optimizer PRs use agent/optimize/* branches, which stay
review-gated (claude/* would auto-merge)"). Anyone who can get one
approval on a `claude/*` PR can currently ship an unreviewed change to
CI/CD workflow permissions, bootstrap templates, or ArgoCD RBAC — the
exact class of change `CLAUDE.md` says must go through a reviewed PR.

## User stories

- AS a platform maintainer I WANT auto-merge on `claude/*` branches
  restricted to a narrow, explicit set of low-risk paths SO THAT routine
  service-values changes keep shipping fast without waiting on a human,
  while anything touching workflows, bootstrap, or secrets machinery still
  gets a human's eyes before it lands on `main`.
- AS a reviewer approving a `claude/*` PR I WANT to know immediately, via
  a bot comment, when auto-merge was skipped and why SO THAT I don't have
  to guess whether my approval alone was enough to merge.
- AS a security auditor I WANT the allowlist itself to live in a path that
  is NOT on the allowlist SO THAT widening the fast path always requires a
  reviewed PR, not a `claude/*` self-approval.

## Acceptance criteria (EARS)

- WHEN a `pull_request_review` with `state == approved` is submitted on a
  PR whose head branch starts with `claude/` THE SYSTEM SHALL compute the
  full set of files changed by that PR before attempting to merge.
- IF every changed file's path starts with one of the allowlisted prefixes
  (`platform-gitops/services/`, `platform-gitops/agents-state/`) THEN THE
  SYSTEM SHALL proceed with `gh pr merge --merge --delete-branch` exactly
  as it does today.
- IF at least one changed file's path does NOT start with an allowlisted
  prefix THEN THE SYSTEM SHALL skip the merge and post a PR comment
  identifying the out-of-allowlist file(s) and explaining that manual
  merge is required.
- WHEN the workflow posts a path-guard comment on a PR THE SYSTEM SHALL
  include a stable marker so a later re-run (e.g. a second reviewer's
  approval on the same PR) does not post a duplicate comment.
- WHILE the allowlist check step is running THE SYSTEM SHALL fetch the
  changed-file list via the GitHub API with pagination, not a single
  unpaginated call, so PRs with more than 100 changed files are still
  evaluated correctly.
- IF the changed-file list cannot be retrieved (API error) THEN THE SYSTEM
  SHALL fail the job without merging, rather than silently merging.
- WHEN evaluating the allowlist THE SYSTEM SHALL use the PR's base branch
  copy of the allowlist logic (not the PR head's), so a `claude/*` PR
  cannot alter its own gate to approve itself.

## Out of scope

- The `workflow_dispatch` allowlist / trust boundary for `gitops-bump.yaml`
  and `release-deploy.yaml` — tracked as a separate issue per the parent
  issue's "Out of scope" section.
- Changing the review-count/approval requirement itself (still one
  `approved` review triggers the job).
- The `mctl-agent` pr-steward automation (`labs/mctl-agent`,
  `PR_STEWARD_*` env vars) that drives auto-merge for other repos
  (`mctl-telegram`, `mctl-pairdesk`, etc.) — that is a separate code path
  in a separate service and is unaffected by this proposal, which only
  touches `mctl-gitops`'s own `auto-merge.yml`.
- Branch-protection / required-status-check configuration for `main` —
  this proposal only changes what `auto-merge.yml` itself does.

## Open questions

- Should the allowlist also cover `platform-gitops/tenants/**` or
  `platform-gitops/mcp/**`? The issue gives `services/**` and
  `agents-state/**` as the explicit "e.g." starting set and says "extend
  deliberately" — interpreted as: ship the minimal two-prefix allowlist
  now, widen later via its own reviewed PR when a concrete need appears.
- Should a blocked PR also get a label (e.g. `needs-manual-merge`) instead
  of / in addition to a comment for easier triage-queue filtering? The
  issue only asks for a comment; a label is a natural follow-up but not
  required by the acceptance criteria, so left out of this proposal.
- Should `request-review`'s Copilot-reviewer step also change? No —
  the issue is scoped to the `auto-merge` job only; `request-review` just
  requests a review and adds no privilege.
