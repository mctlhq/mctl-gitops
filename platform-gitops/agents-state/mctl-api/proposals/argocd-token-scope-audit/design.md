# Design: argocd-token-scope-audit

## Current state
mctl-api reads `ARGOCD_TOKEN` from Vault at path `secret/mctl-api/argocd` using the Kubernetes service-account `auth/kubernetes` method (see `context/architecture.md`, External integrations). The token is used exclusively to call the ArgoCD REST API for application status. The token's current RBAC role and scope are undocumented — it may be a project-scoped token created with wide permissions at initial setup.

CVE-2025-55190 (CVSS 10.0) demonstrates that any project-scoped token can call `/api/v1/projects/{project}/detailed` and receive all repository credentials stored in the ArgoCD project, regardless of whether `projects, get-secret` was explicitly granted. This is an authorization bypass in the ArgoCD server. The ArgoCD server upgrade is the platform team's responsibility; the mctl-api team owns the token it holds.

There is currently no documented constraint in the Vault policy at `secret/mctl-api/argocd` that restricts which ArgoCD RBAC roles are acceptable for the stored token.

## Proposed solution

### Phase 1: Audit (no production changes)
Query the ArgoCD API with the current token to determine its RBAC bindings:
```
GET /api/v1/accounts/{account}       # identify the ArgoCD account name
GET /api/v1/projects/{project}       # probe project-level access
```
Attempt to call `/api/v1/projects/{project}/detailed` — a 200 response confirms the token is in the vulnerable class. Record findings in the incident tracker.

### Phase 2: Create a minimal-scope ArgoCD token
Create a new ArgoCD local account or service account bound to a minimal AppProject RBAC policy. The policy grants only what mctl-api needs:

```yaml
# argocd-cm patch (platform team applies to ArgoCD namespace)
accounts.mctl-api-appstatus: apiKey

# argocd-rbac-cm patch
p, role:mctl-api-appstatus-ro, applications, get,  mctl-project/*, allow
p, role:mctl-api-appstatus-ro, applications, list, mctl-project/*, allow
g, mctl-api-appstatus, role:mctl-api-appstatus-ro
```

Generate the token:
```
argocd account generate-token --account mctl-api-appstatus
```

This token has no `projects` permissions and therefore cannot trigger CVE-2025-55190.

### Phase 3: Rotate in Vault
Store the new token in Vault at the existing path so mctl-api requires no code changes:
```
vault kv put secret/mctl-api/argocd token=<new-token>
```

Update the Vault policy `mctl-api-argocd-write` (used by the platform team for secret rotation) to add a metadata annotation documenting the required role. Because HashiCorp Vault does not natively validate secret values against schemas, the enforcement is procedural: the policy document is updated to state the requirement, and a separate CI job (see Task 4) validates the stored token's ArgoCD RBAC role on each rotation.

### Phase 4: Restart mctl-api and verify
Trigger a rolling restart of the mctl-api Deployment. After all pods are healthy:
1. Confirm application status queries still return correct data.
2. Confirm `/api/v1/projects/{project}/detailed` returns HTTP 403 with the new token.
3. Revoke the old token via `argocd account delete-token`.

### No mctl-api code changes required
The token is read from Vault at startup via the existing Vault integration. The new token value is a drop-in replacement.

## Alternatives

### Option A: Rotate to a Kubernetes service-account token with ArgoCD RBAC
Use ArgoCD's Kubernetes RBAC integration instead of a local ArgoCD account. More complex setup, requires platform team coordination on the ArgoCD side. Minimal additional security benefit over a properly scoped local account token. Rejected: higher effort for equivalent security outcome.

### Option B: Remove ArgoCD integration entirely and poll Kubernetes directly
mctl-api already has `client-go` and could query Application CRDs directly from Kubernetes. This would eliminate the ArgoCD token entirely. Rejected: scope creep — querying ArgoCD Application CRDs requires additional Kubernetes RBAC setup, and the ArgoCD integration provides health rollup that would need to be reimplemented.

### Option C: Wait for ArgoCD server patch before rotating
The platform team will eventually upgrade ArgoCD to a version with the CVE patched. However, the mctl-api token remains over-scoped regardless of the server version, and a patched server does not retroactively fix an over-privileged token. Rejected: the token rotation is a defence-in-depth measure independent of the server patch.

## Platform impact

### Migrations
No database migrations. Vault secret at `secret/mctl-api/argocd` is updated in place. The ArgoCD RBAC config changes are applied by the platform team to the `argocd` namespace; they are out of the mctl-api deployment manifest.

### Backward compatibility
No changes to mctl-api's source code, API surface, or deployment manifests. The only change visible to mctl-api is a new token value read from Vault on restart.

### Resource impact
No additional CPU, memory, or network overhead. No impact on the `labs` tenant.

### Risks and mitigations
- **Risk:** The new minimal-scope token does not have sufficient permissions and application status queries begin failing. **Mitigation:** Phase 2 tests the new token against a staging ArgoCD instance before Phase 3 rotation; old token is not revoked until Phase 4 health checks pass.
- **Risk:** Vault policy update is missed and a future rotation reintroduces a broad-scope token. **Mitigation:** CI job (Task 4) runs on every Vault secret rotation event (via Vault audit log → CI trigger) and fails the pipeline if the stored token passes the CVE probe.
- **Risk:** ArgoCD account `mctl-api-appstatus` is misconfigured with additional permissions. **Mitigation:** The RBAC policy is reviewed and approved in a PR before being applied; the CVE probe in Task 3 serves as automated verification.
