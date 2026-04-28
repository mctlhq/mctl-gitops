# Close CVE-2026-29185: path traversal in SCM URLs leaking the GitHub App token

## Context
CVE-2026-29185 describes a vulnerability in `@backstage/integration`: encoded
path-traversal sequences (e.g. `%2F..%2F`, `%252F`) in user-supplied SCM URLs allow
redirection of requests to arbitrary SCM API endpoints with server-side credentials —
chiefly the GitHub App token. The vulnerability affects catalog-import, scaffolder git
actions, and the github-actions plugin.

In mctl-portal all three affected points are heavily used: catalog-import is used for
registering services, scaffolder git actions for commits to mctl-gitops, and the
github-actions plugin for surfacing CI status. The GitHub App token used by the platform
grants broad read/write access in the organisation. The fix is available in
`@backstage/integration` v1.20.1, included in Backstage v1.50.3.

## User stories
- AS a platform engineer I WANT all SCM URLs provided by users to be validated and
  normalized before use SO THAT path-traversal sequences cannot redirect requests to
  arbitrary SCM API endpoints with server-side GitHub App credentials.
- AS a security officer I WANT Backstage upgraded to v1.50.3 SO THAT CVE-2026-29185 is
  closed and the GitHub App token cannot be exfiltrated through crafted SCM URLs.
- AS a developer I WANT catalog-import, scaffolder git actions, and the github-actions
  plugin to continue working correctly after the upgrade SO THAT existing workflows are
  not disrupted.

## Acceptance criteria (EARS)
- WHEN a user submits a SCM URL containing path-traversal sequences (encoded or
  double-encoded) to catalog-import, scaffolder git actions, or the github-actions plugin
  THE SYSTEM SHALL reject the URL with a validation error before making any outbound
  request.
- WHEN `@backstage/integration` v1.20.1+ processes a SCM URL THE SYSTEM SHALL normalize
  and validate the URL to ensure it resolves to an allowed SCM host without path
  manipulation.
- WHILE Backstage v1.50.3 is running THE SYSTEM SHALL not forward server-side GitHub App
  tokens to endpoints other than the configured SCM integration hosts.
- WHEN a catalog-import is performed with a valid repository URL THE SYSTEM SHALL
  successfully register the component without errors or regressions.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-29185.
- WHEN `@backstage/integration` processes a URL with a non-allowed host THEN THE SYSTEM
  SHALL return an error and not attach authentication headers to the request.

## Out of scope
- Upgrading Backstage beyond version 1.50.3 (only this CVE is targeted).
- Changes in the `labs` tenant.
- Restricting the SCM-host allowlist (may be a separate proposal).
- Audit of custom plugins for similar URL-validation vulnerabilities.
- Replacing the GitHub App with another authentication mechanism.
