# Design: auth-backend-metadata-ssrf

## Current state
`mctl-portal` uses `@backstage/plugin-auth-backend` at a version prior to 0.27.1. The plugin supports an experimental feature, `auth.experimentalClientIdMetadataDocuments`, that fetches an OIDC-style metadata document keyed to the OAuth client ID. The current state of this flag in `app-config.yaml` is unknown — it may be absent (which defaults to `false` in most versions but is not guaranteed), or it may have been enabled during earlier experimentation. In either case, versions before 0.27.1 contain a redirect-following bug that skips allowlist re-validation.

The backend has outbound HTTP access to internal cluster services (Vault, mctl-api, Kubernetes API) via in-cluster DNS. An SSRF exploit could enumerate or exfiltrate data from those endpoints using the backend pod's service account credentials. See `context/architecture.md` — External integrations and Auth sections.

## Proposed solution
Two complementary changes, shipped in the same PR as `auth-backend-redirect-bypass`:

1. **Package bump** — `@backstage/plugin-auth-backend` to `^0.27.1` (shared with Proposal 2). The patch fixes the redirect-following logic to re-validate redirect targets against the allowlist.

2. **Explicit config flag** — Add or confirm the following in `app-config.yaml` (and `app-config.production.yaml` if used):
   ```yaml
   auth:
     experimentalClientIdMetadataDocuments:
       enabled: false
   ```
   This disables the feature entirely at the application layer, providing defence-in-depth independent of the package-level fix. If the flag is already `false`, the commit still makes it explicit and auditable.

3. **CI configuration drift check** — Add a step (e.g., `grep` or a small Node script) in the CI pipeline that asserts `auth.experimentalClientIdMetadataDocuments.enabled` is not `true` in any `app-config*.yaml` file. This prevents accidental re-enablement in the future.

## Alternatives

**Option A — Package bump only, no config change.**
Relies entirely on the upstream patch to block the SSRF. If a future version re-introduces a regression, or if the patch has incomplete coverage, there is no application-layer safety net. Dropped in favour of defence-in-depth.

**Option B — Network egress policy to block unexpected outbound requests.**
A Kubernetes `NetworkPolicy` could restrict the backend pod to only known egress targets. This is a strong long-term control but requires a separate infra review and could break legitimate outbound calls (GitHub, Dex, Prometheus) if misconfigured. Valuable as a follow-on hardening task, not as the primary fix here. Dropped for scope.

**Option C — Remove the OIDC experimental provider entirely.**
The Dex JWT flow does not require the CIMD feature; disabling the provider would eliminate the attack surface. However, removing the provider is a larger change with possible breakage for any other configured auth provider that depends on it. The config flag approach achieves the same SSRF mitigation with zero behavioural change for users. Dropped.

## Platform impact

**Migrations:** The `app-config.yaml` change is a non-breaking addition. Existing auth flows are unaffected because the CIMD feature was either already disabled or not actively used.

**Backward compatibility:** Setting `enabled: false` is the safe default. No user-visible behaviour changes.

**Resource impact:** The CIMD fetch is removed from the hot path, resulting in a marginal reduction in outbound HTTP calls during auth. No memory increase. The `labs` tenant does not run mctl-portal; no labs impact.

**Risks and mitigations:**
- Risk: the flag was actually in use by an undocumented integration. Mitigation: grep the codebase and config history for any reference to `experimentalClientIdMetadataDocuments` before merging; confirm with the team that no integration depends on it.
- Risk: the CI drift check has a false positive due to a comment line containing `true`. Mitigation: use a structured YAML parser (not a plain `grep`) in the check script.
- Risk: the shared package bump with Proposal 2 means a rollback of this proposal also rolls back the redirect-bypass fix. Mitigation: both proposals are designed to always travel together; the rollback procedure documents this explicitly.
