# Upgrade go-github from v68 to v85.0.0 (Authorization Header Leakage Fix)

## Context
mctl-agent uses `google/go-github` (currently pinned at v68) to open fix PRs in the `mctlhq/mctl-gitops` repository as part of its self-healing pipeline. On 2026-04-20, `google/go-github` v85.0.0 was released. Among its changes is cross-host redirect rejection: previously, if a GitHub API call was redirected to a different host, the client would forward the `Authorization` header containing the GitHub installation token to that external host. v85.0.0 rejects cross-host redirects, preventing this leakage.

The GitHub installation token used by mctl-agent is rotated every 30 minutes via a CronWorkflow (Vault path `secret/platform/github-app`) and carries write access to `mctlhq/mctl-gitops`. If this token were leaked to an attacker-controlled host via a cross-host redirect, the attacker would gain the ability to create or modify branches and PRs in the gitops repository for up to 30 minutes — a direct path to unauthorized infrastructure changes. Upgrading to v85.0.0 eliminates this attack vector. The upgrade involves breaking API changes that require a targeted migration pass before the version bump can be merged.

## User stories
- AS a security engineer I WANT mctl-agent to use go-github v85.0.0 SO THAT the GitHub installation token cannot be leaked to a third-party host via a cross-host HTTP redirect.
- AS a developer I WANT a clear, task-by-task migration plan for the breaking API changes SO THAT the upgrade does not introduce regressions in PR-creation logic.
- AS an SRE I WANT the upgrade to be independently deployable and rollbackable SO THAT any regression in the gitops PR workflow can be reverted without affecting other services.

## Acceptance criteria (EARS)
- WHEN mctl-agent initiates a GitHub API call that results in a cross-host HTTP redirect THEN THE SYSTEM SHALL reject the redirect and return an error rather than forwarding the Authorization header.
- WHEN mctl-agent calls `GetOrgRole`, `CreateCustomOrgRole`, or `UpdateCustomOrgRole` THEN THE SYSTEM SHALL use the updated v85 function signatures without compilation error.
- WHEN mctl-agent calls `MarkThreadDone` THEN THE SYSTEM SHALL pass a `string` thread ID (not `int64`) as required by the v85 API.
- WHEN the go-github version is updated in `go.mod` to v85.0.0 THE SYSTEM SHALL compile without error across all packages that import go-github.
- WHILE the upgrade PR is open THE SYSTEM SHALL maintain all existing test coverage for the GitHub PR-creation skill; no test may be deleted or marked skip to accommodate the migration.
- IF any call site uses a go-github v68 function signature that changed in v85 THEN THE SYSTEM SHALL surface a compile-time error (not a runtime error), caught in CI before any image is pushed.
- WHEN mctl-agent opens a fix PR in `mctlhq/mctl-gitops` after the upgrade THE SYSTEM SHALL complete the operation successfully with a 201 response from the GitHub API.

## Out of scope
- Upgrading any other dependency (Go toolchain, chi, sqlite) — separate proposals.
- Changes to the GitHub App authentication mechanism or the token-rotation CronWorkflow.
- Adding new go-github API features (org roles, etc.) not already used by mctl-agent.
- Changes to PR content, branch naming, or gitops repository structure.
- Adopting the new go-github structured-output or pagination helpers not currently in use.
