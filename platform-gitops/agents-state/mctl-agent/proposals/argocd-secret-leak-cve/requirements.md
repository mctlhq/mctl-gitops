# Patch platform Argo CD against CVE-2026-42880 (CVSS 9.6 plaintext secret leak)

## Context
CVE-2026-42880 (CVSS 9.6) affects Argo CD's ServerSideDiff endpoint and allows any
authenticated read-only user to retrieve plaintext Kubernetes Secrets through a crafted
diff request. The mctl-agent service depends on the platform's Argo CD installation to
manage its own deployment manifests and to rotate its GitHub App credentials stored in
Vault (path `secret/platform/github-app`). A read-only attacker who can reach the Argo
CD API — including any developer with SSO access — can therefore exfiltrate the GitHub
App private key and the Anthropic API key that mctl-agent uses for the diagnose phase.

The fix is a straight version bump: Argo CD v3.3.9 (patch series) or v3.2.11 carry no
API changes and no schema migrations. Because the upgrade touches only the platform-layer
Argo CD pods, mctl-agent itself requires no code change; however mctl-agent is the
primary stakeholder driving urgency given its privileged credential surface.

## User stories
- AS a platform engineer I WANT the Argo CD version on the `admins` cluster to be bumped
  to v3.3.9 (or v3.2.11) SO THAT the ServerSideDiff secret-leak vector is closed before
  any read-only user can exploit it.
- AS the mctl-agent service I WANT my Vault-managed GitHub App credentials and Anthropic
  API key to remain confidential SO THAT automated fix PRs and LLM diagnosis cannot be
  hijacked by a credential thief.
- AS a security auditor I WANT evidence that the patched version is running in production
  SO THAT I can mark CVE-2026-42880 as remediated in the vulnerability tracker.

## Acceptance criteria (EARS notation)
- WHEN the Argo CD deployment is updated to v3.3.9 or v3.2.11 THE SYSTEM SHALL report
  the new version string via `argocd version --server` with no error.
- WHEN an authenticated read-only user sends a ServerSideDiff request containing a
  Kubernetes Secret reference THE SYSTEM SHALL return an authorization error (HTTP 403)
  and SHALL NOT include plaintext secret data in the response body.
- WHILE the Argo CD upgrade rollout is in progress THE SYSTEM SHALL maintain continuous
  availability of the `POST /api/v1/alerts` and `POST /mcp` endpoints of mctl-agent
  (health checks must not fail for more than 30 seconds).
- IF the upgraded Argo CD pod fails its readiness probe within 5 minutes of rollout THE
  SYSTEM SHALL automatically roll back to the previous Argo CD image tag.
- WHEN the upgrade completes successfully THE SYSTEM SHALL synchronise the `mctl-agent`
  Application in Argo CD without manual intervention, confirming that the reconciliation
  loop is intact.

## Out of scope
- Changes to mctl-agent Go source code or its dependencies.
- Rotation of GitHub App or Anthropic API credentials (a separate incident-response
  action if evidence of prior exploitation exists).
- Patching Argo CD on the `labs` tenant — tracked separately; `labs` memory budget
  constraints must be evaluated independently before any rollout there.
- Argo CD RBAC policy redesign beyond what is required by the patch.
