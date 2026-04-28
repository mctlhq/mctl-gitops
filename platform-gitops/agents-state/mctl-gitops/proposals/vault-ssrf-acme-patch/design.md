# Design: vault-ssrf-acme-patch

## Current state
Per `context/architecture.md`, Vault runs at `secrets.mctl.ai` and is the sole secret store for
the platform. All tenants (`admins` and `labs`) consume secrets through the External Secrets
Operator (ESO) via the `vault-backend` ClusterSecretStore. ESO ExternalSecret manifests live
under `platform-gitops/argo-workflows/secrets/`. The Vault server version is managed via
Terraform under `infrastructure/`.

The current Vault CE version falls in the range 1.14.0–1.21.4 and is therefore vulnerable to
CVE-2026-5052 (HCSEC-2026-06). The ACME PKI challenge validators (http-01 and tls-alpn-01) do
not validate that the resolved target of a challenge is a public IP address, allowing an attacker
with DNS control to steer validation traffic toward internal cluster services.

## Proposed solution

### Decision tree: mitigation-first, upgrade if needed

Because Vault CE v2.0.0 contains breaking changes (Docker helper interface, auth endpoint
requirements), and because `labs` is near its memory limit, the preferred path is to evaluate
the lower-cost mitigation before committing to the full upgrade.

**Step 1 — Determine ACME usage.**
Audit Vault PKI mount configurations to confirm whether http-01 or tls-alpn-01 ACME challenge
endpoints are enabled and actively used. If they are not used by any tenant, proceed with the
mitigation path. If they are used, proceed with the upgrade path.

**Path A — Mitigation: disable ACME challenge (preferred if ACME is unused)**

Disable the ACME challenge endpoint on all Vault PKI mounts via the Vault API or Terraform
`vault_pki_secret_backend_config_acme` resource:

```
acme_enabled = false
```

This removes the vulnerable code path entirely without requiring a Vault version bump. A
Terraform change under `infrastructure/` is committed and merged; ArgoCD / Terraform apply
propagates the configuration. The change is immediately reversible by re-enabling the flag.

This path requires no Docker helper migration, no auth endpoint changes, and has no memory
impact on `labs`.

**Path B — Full upgrade to Vault CE v2.0.0 (if ACME is actively used)**

If ACME challenge is actively used and cannot be disabled, upgrade Vault to CE v2.0.0 via the
Terraform `vault` module version pin under `infrastructure/`. The upgrade must be preceded by a
structured breaking-change review (see tasks).

v2.0.0 known breaking changes to address before rollout:
- **Docker helper interface change** — the Vault Docker image no longer includes the legacy
  helper binary at the old path. Any init containers, sidecar scripts, or Terraform provisioners
  that invoke the old helper path must be updated.
- **Auth endpoint requirement changes** — certain auth methods (Kubernetes auth, AppRole) have
  adjusted endpoint paths or requirement fields. The `vault-backend` ClusterSecretStore
  configuration and any Terraform `vault_auth_backend` / `vault_kubernetes_auth_backend_config`
  resources must be validated against v2.0.0 behaviour before apply.

Rollout sequence (Path B):
1. Update Terraform variable / module version to target Vault CE v2.0.0.
2. Apply breaking-change adaptations (Docker helper paths, auth endpoint configs).
3. Run `terraform plan` in a non-production context; review the plan for unexpected destroy/replace operations.
4. Execute `terraform apply` against the cluster; Vault pod rolls over.
5. Validate Vault health endpoint, `vault-backend` ClusterSecretStore, and all ExternalSecrets.

### Memory impact assessment (required for both paths)
Before executing Path B, compare Vault CE v2.0.0 memory consumption figures (release notes,
HashiCorp blog, or direct benchmark) against the current version. The `labs` tenant is close to
its memory quota. Vault runs in the `admins` namespace (not `labs`), but any node-level memory
pressure can affect `labs` pods. If v2.0.0 shows a materially higher memory footprint, the
recommendation is to stay on Path A.

### GitOps convention
Every change — whether Path A or Path B — is a git commit to this repository under
`infrastructure/`. No ad-hoc `vault operator` or `kubectl` mutations outside of Terraform and
the ArgoCD App-of-Apps reconciliation cycle.

## Alternatives

### Alternative 1 — NetworkPolicy to block ACME egress (dropped)
Apply a Kubernetes NetworkPolicy that prevents Vault pods from making outbound connections to
RFC-1918 addresses, neutralising the SSRF at the network layer without modifying Vault config or
version. Dropped because: NetworkPolicy operates at L3/L4; ACME validation traffic uses normal
port 80/443 over arbitrary IPs, making a blanket block too broad (it would break legitimate
external ACME traffic) or too narrow (it would not cover all internal ranges in all environments).
The mitigation is fragile and leaves the vulnerable code path technically reachable.

### Alternative 2 — Skip v2.0.0 and wait for a v2.0.x patch release (dropped)
Wait for a Vault CE v2.0.x release that backports only the SSRF fix without the other v2.0.0
breaking changes. Dropped because: HashiCorp has not announced a backport to the 1.x line. The
SSRF fix is only available in v2.0.0+. Delaying leaves the platform exposed. Path A (ACME
disable) is available as an immediate, safe mitigation if the full upgrade is deferred.

### Alternative 3 — Rotate to a managed PKI CA outside Vault (dropped)
Migrate certificate issuance to cert-manager with an external ACME provider (Let's Encrypt,
ZeroSSL), removing Vault PKI ACME from the blast radius entirely. Dropped because: scope is far
larger than a CVE patch cycle, carries cert rotation risk across all tenants, and does not address
the underlying Vault vulnerability for other PKI use cases.

## Platform impact

### Migrations
**Path A:** Vault PKI ACME configuration change via Terraform. No data migration. The
`vault_pki_secret_backend_config_acme` resource change is a Terraform-managed API call; existing
certificates issued by the PKI mount are unaffected.

**Path B:** In addition to the version bump, any Vault auth backend Terraform resources that use
changed endpoint names must be updated. Init containers or sidecar scripts referencing the old
Docker helper path must be patched. A `terraform plan` review is mandatory before apply.

### Backward compatibility
**Path A:** Fully backward-compatible. Disabling ACME only removes the vulnerable challenge
endpoint; the Vault PKI CA, intermediate CAs, certificate issuance via the `sign` / `issue`
endpoints, and all other Vault functionality remain unchanged.

**Path B:** Vault CE v2.0.0 is a major release with documented breaking changes. All breaking
changes must be addressed before apply; the working assumption is that the `vault-backend`
ClusterSecretStore (Kubernetes auth) will require configuration validation.

### Resource impact
- Vault runs in the `admins` namespace. The `labs` tenant does not run Vault directly.
- **Path A** has zero resource impact on any tenant.
- **Path B** requires a memory footprint comparison. If v2.0.0 increases Vault memory usage and
  causes node-level pressure, `labs` pods (which are near their memory limit) could be evicted.
  This is flagged as a risk. Mitigations: verify resource limits before rollout; consider a
  maintenance window during low-traffic hours.

### Risks and mitigations
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ACME is actively used; Path A blocks a tenant workflow | Medium | Medium | Confirm ACME usage in audit (Task 1) before disabling |
| Vault v2.0.0 Docker helper change breaks Vault startup | Medium | High | Review and patch all helper invocations before apply (Task 3) |
| Vault v2.0.0 auth endpoint change breaks ESO ClusterSecretStore | Medium | Critical | Validate ClusterSecretStore config against v2.0.0 docs before apply (Task 3) |
| Vault v2.0.0 increases memory, evicts labs pods | Low–Medium | High | Memory assessment required (Task 2); fall back to Path A if headroom insufficient |
| Vault pod fails to start after upgrade | Low | Critical | Rollback via git revert of Terraform change (see tasks.md) |
| Existing cached Kubernetes Secrets lost during Vault downtime | Low | High | ESO does not delete synced Kubernetes Secrets on Vault unavailability; downtime is brief |
