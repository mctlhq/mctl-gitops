# Integration Credential Leak Fix (CVE-2026-29185)

## Context
CVE-2026-29185 was disclosed in `@backstage/integration`. The package is
responsible for resolving SCM (Source Code Manager) URLs and attaching the
appropriate host credentials before making server-side requests. An
encoded path-traversal sequence in a crafted SCM URL can cause the library to
match the wrong host entry in the integration configuration, redirecting the
outbound request — along with the attached GitHub token — to an
attacker-controlled host. Any Backstage backend feature that fetches SCM
content (catalog import, scaffolder, TechDocs fetch) is affected.

mctl-portal has an active GitHub integration used by the scaffolder (commits
to `mctl-gitops`), catalog import, and PR/issue widgets. A compromised GitHub
token could allow an attacker to make commits to mctl-gitops and therefore
to any ArgoCD-managed tenant. The fix is to upgrade `@backstage/integration`
to >=1.20.1. This should be applied in the same patch cycle as the
`techdocs-path-traversal-fix` proposal (Backstage v1.50.3 bump).

## User stories
- AS a platform engineer I WANT the integration library to reject encoded
  path-traversal sequences in SCM URLs SO THAT GitHub credentials are never
  sent to hosts not listed in the integration configuration.
- AS a security officer I WANT evidence that CVE-2026-29185 is remediated
  SO THAT the finding can be closed in the vulnerability tracker.
- AS a developer using the scaffolder I WANT my scaffolder templates to
  continue committing to `mctl-gitops` without interruption SO THAT service
  onboarding is unaffected by the security patch.

## Acceptance criteria (EARS notation)
- WHEN the integration library resolves an SCM URL that contains an encoded
  path-traversal sequence (e.g., `%2F..%2F`) THE SYSTEM SHALL reject the URL
  and return an error without attaching any host credentials to the request.
- WHEN a legitimate scaffolder template commits to a GitHub repository listed
  in the integration configuration THE SYSTEM SHALL attach the correct
  credential and complete the commit successfully.
- WHEN the mctl-portal container image is built THE SYSTEM SHALL include
  `@backstage/integration` at version >=1.20.1.
- WHILE the patch upgrade is in progress THE SYSTEM SHALL remain available
  in the existing version until the new image passes all smoke tests.
- IF a resolved SCM URL hostname does not match any entry in the integration
  configuration THEN THE SYSTEM SHALL deny the request and log a warning
  without exposing any stored credential.

## Out of scope
- Auditing historical logs for evidence of prior exploitation — a separate
  incident-response activity.
- Rotating the GitHub token as a precautionary measure — recommended but
  tracked separately by the security team.
- Changes to which GitHub organisations are permitted in the integration
  configuration.
- Remediation of CVE-2026-23947 (`@backstage/plugin-techdocs-node`) — tracked
  under `techdocs-path-traversal-fix`.
