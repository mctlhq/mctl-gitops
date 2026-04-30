# Design: vault-kvv2-deletion-bypass

## Current state
Vault is deployed at `secrets.mctl.ai` and serves as the exclusive secret store for the
platform (see `context/architecture.md`, External integrations section). All secrets flow
through the `vault-backend` ClusterSecretStore managed by External Secrets Operator (ESO).
Both `admins` and `labs` tenants use ExternalSecret resources that reference paths under
the KVv2 secrets engine.

Vault policies for each tenant are glob-based, following the pattern
`secret/data/<tenant>/*`, granting `read`, `list`, and (in some policies) `delete` or
`destroy` capabilities. Under CVE-2026-3605, a caller with a glob policy that includes
delete/destroy capability can target metadata and destroy endpoints for paths outside their
read scope, bypassing path-level authorization. The Vault version currently in use is
unpatched against this CVE (exact version to be confirmed from the running Vault Pod).

The `vault-ssrf-acme-patch` proposal (already written) addresses CVE-2026-5052 and targets
a Vault version upgrade as well; coordination between the two proposals is necessary to
avoid redundant upgrade cycles.

## Proposed solution
**Primary path — Vault version upgrade.**
Upgrade Vault to the first release that patches CVE-2026-3605. Vault v2.0.0 was released
on 2026-04-14 with significant changes (authentication requirements on previously
unauthenticated endpoints, non-canonical URL path rejection). Confirm whether v2.0.0 or a
later patch release is the fix target. The upgrade manifest lives under
`platform-gitops/services/admins/vault/` (or the equivalent bootstrap path). ArgoCD
performs a rolling update of the Vault StatefulSet.

**Interim mitigation — Policy tightening.**
Until the upgrade is applied, audit all KVv2 policies and remove `delete`, `destroy`, and
`metadata` write capabilities from any policy that uses glob patterns, unless those
capabilities are explicitly required for the token holder's function. The policy audit
results are committed as a Vault policy HCL file update and applied via `vault policy
write` (or the equivalent Terraform/Vault provider resource). This mitigation is
independently valuable as a defence-in-depth measure even after the upgrade.

**Policy audit approach:**
1. Enumerate all Vault policies: `vault policy list`.
2. For each policy, inspect for glob patterns combined with `delete`, `destroy`, or
   `metadata` write capabilities.
3. Produce a least-privilege replacement policy: if a tenant only needs `read` and `list`,
   remove `delete`/`destroy` entirely; if `delete` is genuinely needed, scope it to an
   explicit path rather than a glob.
4. Apply the revised policies; verify ESO ClusterSecretStore health remains `Ready`.

## Alternatives

**Alternative 1 — Sentinel / EGP policy to block glob-delete paths.**
Use Vault Sentinel (Enterprise) or an Endpoint Governing Policy to add a custom rule that
rejects delete requests matching the vulnerable pattern. Dropped because the platform runs
Vault OSS (no Sentinel license), and replicating this in a custom auth plugin is high
effort with low confidence compared to upgrading.

**Alternative 2 — Restrict all KVv2 policies to explicit paths (no globs) immediately.**
Replace all glob-based policies with exhaustive explicit path lists before upgrading.
Dropped as the primary fix because maintaining explicit path lists at scale is operationally
brittle and would require policy updates on every new secret path creation. It is acceptable
as a targeted tightening for the specific delete/destroy capabilities (see interim
mitigation above) but not as the complete solution.

**Alternative 3 — Rotate all secrets immediately and disable KVv2 delete capability
platform-wide.**
Emergency rotation of all secrets plus removal of all delete capabilities from every policy.
Dropped because it is operationally disruptive (risks breaking ESO syncs during rotation)
and disproportionate to the actual exploit complexity, which requires an authenticated user
with an existing glob policy.

## Platform impact

**Migrations**
- Vault upgrade: the StatefulSet rolling update is standard. Vault v2.0.0 introduces
  authentication requirements on previously unauthenticated endpoints — review any internal
  health-check or monitoring probes that call Vault without a token (e.g., Prometheus
  scrape of `/v1/sys/health`) and update them to use authenticated calls or the updated
  unauthenticated status endpoint.
- Policy tightening: no data migration; policies are updated in-place. ESO will continue
  to use existing read tokens unaffected.

**Backward compatibility**
- Vault v2.0.0 rejects non-canonical URL paths. Any tooling (scripts, Terraform providers,
  CLI calls) that constructs Vault API URLs with double slashes or trailing slashes must
  be updated before the upgrade.
- Removing delete capability from glob policies does not affect ESO, which only uses `read`
  and `list` operations. Applications that explicitly delete secrets via the Vault API
  must be identified and assessed.

**Resource impact**
- Vault upgrade: same Pod count and resource requests. No new components introduced.
  No impact on `labs` memory budget.
- Policy tightening: zero resource impact (policy objects are negligibly small).

**Risks and mitigations**
- Risk: Vault v2.0.0 is a major release with breaking changes; upgrade may cause
  unexpected behavior in auth methods or secret engines.
  Mitigation: test the upgrade in a staging environment first; coordinate with the
  `vault-ssrf-acme-patch` upgrade plan to avoid two sequential major upgrades.
- Risk: tightened policies inadvertently remove a capability a workload actually uses.
  Mitigation: enumerate all Vault token usage patterns before tightening; maintain a
  rollback policy HCL file for each modified policy.
- Risk: ESO ClusterSecretStore loses `Ready` status during Vault restart.
  Mitigation: Vault HA mode (if enabled) provides a standby node; ESO has a built-in
  retry backoff; monitor ESO conditions post-upgrade.
