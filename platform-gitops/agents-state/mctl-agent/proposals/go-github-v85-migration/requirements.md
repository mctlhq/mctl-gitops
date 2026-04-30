# Upgrade google/go-github from v68 to v85

## Context
mctl-agent uses `google/go-github` as its sole GitHub client library, primarily to create fix
PRs in `mctlhq/mctl-gitops` — the final and most critical step of the self-healing pipeline.
As of v1.5.0 the service is on v68, while the upstream library reached v85.0.0 on 2026-04-20.
The gap of 17 major versions carries documented breaking changes: a parameter-type change in
`ActivityService.MarkThreadDone` and fixes to custom org role options. Because Go module major
versions require explicit import path changes (`/v68` → `/v85`), the migration requires
touching every file that imports the library.

Allowing this gap to grow further increases the risk of a forced migration under incident
pressure, where the PR-creation path is broken by a hard dependency conflict introduced by
another library upgrade. Migrating now, while the PR-creation code is well-understood and
test coverage is solid, is materially cheaper and safer.

## User stories
- AS a platform engineer I WANT mctl-agent to use `google/go-github v85` SO THAT the GitHub
  PR creation pipeline is built against a supported library version with current API
  semantics.
- AS an on-call engineer I WANT the fix-PR pipeline to behave identically before and after
  the upgrade SO THAT the migration introduces no regression in the self-healing workflow.
- AS a security engineer I WANT the dependency tree to track near-current library versions
  SO THAT any future CVE in go-github is a small-delta patch, not a multi-version migration.

## Acceptance criteria (EARS)
- WHEN mctl-agent starts after the upgrade THE SYSTEM SHALL import
  `github.com/google/go-github/v85` and all references to the v68 import path SHALL be
  absent from the compiled binary.
- WHEN the fix pipeline creates a PR in `mctlhq/mctl-gitops` THE SYSTEM SHALL call the
  v85 `PullRequestsService.Create` API and receive a non-error response for valid inputs,
  matching the behaviour of the v68 call under the same inputs.
- WHEN `ActivityService.MarkThreadDone` is called THE SYSTEM SHALL pass the parameter using
  the type signature required by v85 (as documented in the v85 changelog).
- IF any call site in mctl-agent used a custom org role option that was broken in v68 THE
  SYSTEM SHALL use the corrected v85 API for that option.
- WHEN `go build ./...` is executed against the migrated codebase THE SYSTEM SHALL complete
  with zero compilation errors and zero `go vet` warnings attributable to the migration.
- WHILE mctl-agent is running after the upgrade THE SYSTEM SHALL produce no increase in
  error-rate on GitHub API calls compared to the pre-upgrade baseline measured over a 24-hour
  window.

## Out of scope
- Adopting any new v85 features beyond what is required to fix breaking-change call sites.
- Upgrading other GitHub-related dependencies (e.g., the GitHub App token rotation
  CronWorkflow).
- Changing the PR creation logic, branch naming conventions, or `mctlhq/mctl-gitops`
  repository structure.
- Adding new GitHub API call sites not currently present in v1.5.0.
