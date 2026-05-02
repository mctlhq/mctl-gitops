# google/go-github Upgrade: v68 → v85

## Context
mctl-agent uses `google/go-github` to create fix PRs in the `mctlhq/mctl-gitops` repository. This is the primary output of the self-healing pipeline: a diagnosed alert results in a Git PR that applies the remediation. The service authenticates using a GitHub App installation token rotated every 30 minutes via a CronWorkflow (Vault path `secret/platform/github-app`).

The service currently pins `google/go-github v68`. The latest release is v85.0.0 (2024-04-20). Versions prior to v85 do not reject cross-host HTTP redirects when following GitHub API calls — an attacker who can intercept or inject a redirect can obtain the `Authorization: Bearer <installation-token>` header, compromising the GitHub App and allowing arbitrary repository writes. This vulnerability is directly relevant because the token used has write access to `mctlhq/mctl-gitops`.

Additionally, the 17-major-version gap means accumulated correctness fixes, API improvements, and context-propagation improvements are unavailable.

## User stories
- AS a platform engineer I WANT the go-github client to reject cross-host redirects SO THAT the GitHub App installation token cannot be leaked to a third-party host via a redirect attack.
- AS a developer I WANT the go-github client to be within 2 major versions of the latest release SO THAT security and correctness fixes are available without requiring a large migration.
- AS an on-call engineer I WANT PR creation failures to surface a typed error from go-github v85 SO THAT the root cause can be diagnosed faster from structured error information.

## Acceptance criteria (EARS)
- WHEN the go-github client follows an HTTP redirect to a different host, THE SYSTEM SHALL strip the `Authorization` header before following the redirect (v85 default behaviour).
- WHEN the service creates a fix PR, THE SYSTEM SHALL use go-github v85 or later.
- WHEN a GitHub API call returns an error, THE SYSTEM SHALL log the structured error type (available via the v85 error type system) at ERROR level.
- WHILE the service is operating normally, THE SYSTEM SHALL retain full PR creation functionality: create branch, commit patch file, open PR with correct title/body, assign labels.
- IF the GitHub App token is about to expire during a PR creation, THE SYSTEM SHALL propagate the context deadline and return a retryable error (existing behaviour must not regress).
- WHEN `go mod tidy` is run after the upgrade, THE SYSTEM SHALL produce a clean module graph with no import-path conflicts between v68 and v85 symbols.

## Out of scope
- Switching from GitHub App authentication to PAT or OAuth — auth mechanism is out of scope.
- Upgrading other dependencies (go-chi, sqlite, etc.) — handled in separate proposals.
- Adding new GitHub API calls beyond what the service currently uses (PR creation, branch management).
- Modifying the CronWorkflow that rotates the GitHub App token.
