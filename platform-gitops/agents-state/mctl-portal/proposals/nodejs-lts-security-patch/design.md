# Design: nodejs-lts-security-patch

## Current state
Per `context/architecture.md` and `context/current-version.md`, mctl-portal declares
`engines.node: 22 || 24` and is served via nginx + Docker → mctl-gitops → ArgoCD to
tenant `admins`. The Docker base image is currently pinned to some earlier patch
version within the 22.x or 24.x line (exact pin not tracked in `context/`, to be
confirmed from the Dockerfile at implementation time). Node.js released security
fixes in June 2026 (7 CVEs, including HTTP/2 DoS, permission bypass, mTLS SNI bypass)
and July 2026 (a further batch across the 22.x/24.x/26.x lines), landing in
22.23.2 and 24.18.1/24.20.0.

## Proposed solution
Update the Docker base image tag (and any `.nvmrc` / CI runtime pins, if present) to
the latest patched version within whichever major line mctl-portal currently
targets in production — Node 22.23.2+ or Node 24.20.0+. This is purely a base-image
version bump: the `engines` field in `package.json` already permits both majors and
does not need to change. No application source changes are anticipated since these
are runtime security patches (HTTP/2, permission model, TLS), not JS-language or API
breaking changes.

Rollout: bump the pin, rebuild the Docker image via the existing CI pipeline, run the
full test suite (unit/integration/e2e) against the new image, then deploy through
the standard mctl-gitops → ArgoCD path to tenant `admins`.

## Alternatives
- **Wait for the next scheduled dependency-refresh cycle instead of patching now** —
  rejected. Several of the fixed CVEs are HIGH severity and DoS/auth-bypass in
  nature; mctl-portal is internet-facing, so deferring is an avoidable risk for a
  low-effort change.
- **Jump to Node 26.x (current line)** — rejected. Not an LTS line yet (informational
  release only per the researcher); adopting a non-LTS line for a production backend
  is out of proportion to the risk being addressed and would require an `engines`
  field change and broader compatibility validation.
- **Pin only one of the two supported majors (drop 22 or 24 from `engines`)** —
  rejected. Out of scope for a security patch; narrowing supported majors is a
  separate decision with its own tradeoffs and is not needed to close these CVEs.

## Platform impact
- **Migrations:** none. Runtime base-image version bump only.
- **Backward compatibility:** fully backward compatible. Both target majors (22, 24)
  remain within the existing `engines` constraint; no application code or API
  contract changes.
- **Resource impact (especially for `labs`):** not applicable — mctl-portal runs
  only in tenant `admins`; tenant `labs` does not run this service. Within `admins`,
  a Node.js patch-version bump carries no expected CPU/memory footprint change (the
  researcher's tenant-`admins` metrics — ~67% CPU limit, ~65% memory limit usage —
  are unrelated to this change and not expected to shift).
- **Risks and mitigations:**
  - *Risk:* an undocumented behavioral change in the patched Node version (e.g.
    stricter TLS/SNI matching per CVE-2026-48928) breaks an existing integration
    (Dex JWT auth, Vault ExternalSecret fetches, mctl-api calls). *Mitigation:* run
    full CI suite plus a staging smoke test covering auth (Dex login), an mctl-api
    call, and a Vault-backed secret fetch before promoting to `admins`.
  - *Risk:* base image rebuild surfaces an unrelated toolchain incompatibility.
    *Mitigation:* rebuild in CI first and gate the deploy on a green pipeline; keep
    the previous image tag available for immediate rollback.
