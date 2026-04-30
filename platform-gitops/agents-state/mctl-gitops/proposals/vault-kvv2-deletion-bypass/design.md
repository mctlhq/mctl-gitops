# Design: vault-kvv2-deletion-bypass

## Current state

Vault runs at `secrets.mctl.ai`. Tenant secrets are stored in KVv2 mounts (e.g.,
`secret/data/admins/<svc>`, `secret/data/labs/<svc>`). Policies are typically written with glob
suffixes (`secret/data/labs/*`) to avoid per-secret policy duplication.

CVE-2026-3605 means that any token whose policy contains a glob path with `delete` or `destroy`
capability — even if it was granted only to allow metadata cleanup — can silently destroy any
secret matching the glob. The External Secrets Operator's `vault-backend` ClusterSecretStore uses
a Vault token/role that must have read access to all tenant secret paths. If that token or a
tenant-scoped token is compromised, this CVE becomes an impact multiplier.

See `context/architecture.md` for the ESO → Vault → ExternalSecret flow.

## Proposed solution

### Phase 1 — Immediate interim mitigation (policy tightening)

1. Enumerate all Vault policies that include `delete` or `destroy` capabilities with glob paths.
2. Rewrite those policies to either:
   - Remove `delete`/`destroy` from the glob rule and add explicit non-glob paths only where
     deletion is genuinely required, OR
   - Replace the glob with the narrowest possible path prefix that still satisfies operational needs.
3. Apply the updated policies via Terraform (under `infrastructure/`) or directly via the Vault
   API, then commit the canonical HCL files to this repo.
4. Verify all ExternalSecrets still resolve after the policy change.

Phase 1 is safe to deploy without a Vault version upgrade and carries no memory impact on `labs`.

### Phase 2 — Scheduled upgrade to the patched Vault release

1. Identify the minimum Vault CE release that includes the CVE-2026-3605 fix (v2.0.0 is the
   confirmed fix version per the advisory).
2. Assess the v2.0.0 breaking changes (Docker helper migration, mandatory auth on previously
   unauthenticated endpoints, non-canonical URL rejection). Prepare a compatibility matrix for
   all ESO ClusterSecretStore configurations.
3. Execute the upgrade in a staging environment first; validate ESO sync, ArgoCD Application
   health, and all tenant workloads.
4. Schedule a maintenance window for production; upgrade and smoke-test.

Note: a Vault major upgrade carries more risk than a patch release. Phase 1 must land before
Phase 2 is scheduled.

## Alternatives

**A. Upgrade Vault immediately without Phase 1** — Vault v2.0.0 has breaking changes that
require pre-testing; deploying it without a compatibility assessment risks taking down ESO and
all secret-dependent workloads. Dropped.

**B. Vault Sentinel / EGP policies as the sole control** — Sentinel policies can enforce deletion
restrictions at evaluation time. However, Sentinel is an Enterprise feature not available on the
OSS Vault CE we operate. Dropped.

**C. Explicit path policies only (no globs ever)** — Fully replacing globs with per-secret
explicit paths is operationally brittle as the path list grows with every new service. Dropped
in favour of minimally scoped globs that exclude `delete`/`destroy`.

## Platform impact

- **Migrations:** Policy HCL files updated in `infrastructure/`; no Kubernetes manifest changes
  in Phase 1.
- **Backward compatibility:** Phase 1 removes `delete`/`destroy` from glob policies; any
  automation that relied on glob-based deletion will need explicit path grants — expected to be
  rare (secret lifecycle is managed via Terraform, not runtime deletion).
- **Resource impact for `labs`:** No new components; policy changes are server-side. Zero memory
  increase for `labs`.
- **Risks:** If a Phase 1 policy is too restrictive, an ExternalSecret sync will fail with a 403
  (visible in ESO controller logs and Kubernetes events). Mitigated by testing all ESO paths in
  a dry-run before applying. Phase 2 Vault upgrade risk is contained by staging validation.
