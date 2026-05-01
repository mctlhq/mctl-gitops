# Audit and Restrict ARGOCD_TOKEN Scope to Mitigate CVE-2025-55190

## Context
CVE-2025-55190 (CVSS 10.0) affects all ArgoCD versions prior to the patched release. Any holder of a project-scoped ArgoCD API token can call `/api/v1/projects/{project}/detailed` and receive the full repository credential set (usernames, passwords, SSH keys) stored in the ArgoCD project — without any explicit secrets-read permission being required. This is an authorization logic flaw in the ArgoCD server itself.

mctl-api retrieves its `ARGOCD_TOKEN` from Vault (`secrets.mctl.ai`) using the `auth/kubernetes` method and uses it exclusively to query application status from ArgoCD (see `context/architecture.md`, External integrations). If the current token is project-scoped, it falls directly in the vulnerable class: any process that can read the token (e.g., via a container breakout, a Vault policy misconfiguration, or a log leak) could use it to exfiltrate every repository credential in the ArgoCD project. The mctl-api scope for this proposal is not the ArgoCD server upgrade (a platform concern) but the three steps mctl-api owns: audit the token's current scope, rotate to a minimally-scoped replacement, and update the Vault policy to enforce the minimal scope going forward.

## User stories
- AS a security engineer I WANT to know definitively whether the current `ARGOCD_TOKEN` is project-scoped SO THAT I can assess the current blast radius of CVE-2025-55190
- AS a platform operator I WANT the `ARGOCD_TOKEN` used by mctl-api to be scoped only to application-status reads SO THAT even if the token is exfiltrated it cannot be used to retrieve repository credentials
- AS a platform operator I WANT the Vault policy for `mctl-api`'s ArgoCD secret to enforce the minimal-scope token SO THAT future token rotations cannot accidentally reintroduce a broader scope

## Acceptance criteria (EARS)

### Audit
- WHEN the audit task is executed THE SYSTEM SHALL produce a written record of the current `ARGOCD_TOKEN`'s ArgoCD RBAC role and associated permissions
- IF the current token has `projects, get` or broader project-level permissions THEN THE SYSTEM SHALL treat it as project-scoped and proceed with immediate rotation
- IF the current token already has only `applications, get` and `applications, list` permissions (or equivalent read-only application-status subset) THEN THE SYSTEM SHALL document it as compliant and skip rotation

### Token rotation
- WHEN a replacement token is issued THEN THE SYSTEM SHALL verify it has only the permissions required for application-status queries: `applications, get` and `applications, list` on the target AppProject
- WHEN the new token is stored in Vault THE SYSTEM SHALL store it under the same secret path used by mctl-api so that no code change is required on mctl-api's side
- WHILE the new token is being rolled out THE SYSTEM SHALL keep the old token valid until the mctl-api deployment has fully restarted and health checks pass, then revoke the old token

### Vault policy
- WHEN the Vault policy for mctl-api's ArgoCD secret is updated THE SYSTEM SHALL restrict the writeable scope so that only tokens with the ArgoCD RBAC role `mctl-api-appstatus-ro` (or equivalent minimal role) can be stored at that path
- IF a Vault write to the ArgoCD token path is attempted with a token that does not match the approved role pattern THEN THE SYSTEM SHALL deny the write and emit a Vault audit log entry

### Verification
- WHEN the new token is active THE SYSTEM SHALL confirm via a direct HTTP call to `/api/v1/projects/{project}/detailed` that it receives HTTP 403 (not 200) — proving the token cannot exercise the CVE
- WHILE the new minimal-scope token is in use THE SYSTEM SHALL continue to return accurate application status from the existing `GET /services/{name}/status` endpoint in mctl-api

## Out of scope
- Upgrading the ArgoCD server itself (platform team responsibility)
- Patching or modifying ArgoCD's authorization logic
- Changes to any other Vault secrets used by mctl-api (Backstage, Argo Workflows, etc.)
- Automated Vault policy enforcement via OPA/Sentinel (future hardening)
- Changes to how mctl-api calls the ArgoCD API (no code change expected — only the token value changes)
