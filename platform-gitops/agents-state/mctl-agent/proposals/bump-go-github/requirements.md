# Upgrade google/go-github v68 to v85

## Context
mctl-agent uses `google/go-github` directly to open fix PRs against `mctlhq/mctl-gitops` on behalf of
a short-lived GitHub App installation token that is rotated every 30 minutes via a CronWorkflow.
The service is currently on v68, which is 17 major versions behind the latest release (v85.0.0,
released 2026-04-20).

v85 closes three concrete security gaps absent in v68: (1) cross-host redirect rejection that would
otherwise silently forward the Authorization header to an attacker-controlled host, (2) URL path
validation that rejects `..` segments in GitHub API URLs, and (3) webhook payload size limits in
`ValidatePayloadFromBody`. Because the agent's PR-creation path executes on every remediation cycle,
the credential-leak vector is continuously exposed until this upgrade is applied.

## User stories
- AS a platform engineer I WANT the agent's GitHub API client to reject cross-host redirects SO THAT
  the GitHub App installation token is never forwarded to an attacker-controlled host.
- AS a security reviewer I WANT the agent to validate URL paths before sending requests to the GitHub
  API SO THAT path traversal attempts are blocked at the client layer.
- AS an on-call engineer I WANT webhook payload size enforcement in the GitHub client SO THAT a
  malformed oversized payload cannot exhaust agent memory during ingestion.

## Acceptance criteria (EARS)
- WHEN the GitHub API client follows a redirect to a different host THEN THE SYSTEM SHALL reject the
  redirect and return an error without forwarding the Authorization header.
- WHEN a GitHub API URL is constructed that contains `..` path segments THEN THE SYSTEM SHALL return
  an error before the request is dispatched.
- WHEN `ValidatePayloadFromBody` processes an inbound webhook payload THEN THE SYSTEM SHALL enforce
  the default payload size limit introduced in v85.
- WHILE the agent is running its PR-creation pipeline THEN THE SYSTEM SHALL authenticate exclusively
  against `api.github.com` and never silently redirect credentials to a third-party host.
- IF the `go-github` library version in `go.mod` is less than v85 THEN THE SYSTEM SHALL fail CI with
  a dependency audit error.

## Out of scope
- Upgrading any other GitHub-related dependency (e.g., `golang/x/oauth2`).
- Changes to the GitHub App token rotation CronWorkflow (`cwft-rotate-github-token`).
- Modifying the PR-creation business logic or adding new PR fields.
- Addressing the 17-version feature delta beyond the security fixes listed above.
