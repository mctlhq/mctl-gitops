# Design: fetchurl-ssrf

## Current state
mctl-portal is a Backstage internal developer portal (see `context/architecture.md`). The backend is a Node.js/TypeScript Backstage application running under the `admins` tenant, accessible at `https://app.mctl.ai`.

`FetchUrlReader` is a core Backstage backend utility that reads content from external URLs on behalf of backend plugins. It is configured via `backend.reading.allow` in `app-config.yaml`. The current implementation validates the initial URL against the allowlist but does not re-validate after an HTTP 3xx redirect. Plugins that use `FetchUrlReader` include:

- **catalog** — fetches `catalog-info.yaml` from entity source URLs (GitHub, GitLab, or direct HTTPS).
- **proxy** — some proxy routes internally delegate URL reads via `FetchUrlReader`.
- **techdocs** — fetches documentation source content.

The backend pod has network access to internal services: `mctl-api`, Vault (via ExternalSecret), and Prometheus/Loki. These internal services trust the backend's service account or network identity and may not perform additional authentication for requests originating from inside the cluster. An SSRF exploit would allow an attacker to reach them without direct access.

The specific Backstage package containing `FetchUrlReader` is part of the core backend packages. The patch for CVE-2026-24048 adds a redirect-follower wrapper that re-applies allowlist validation at each redirect hop.

## Proposed solution
The fix has two parts:

**Part 1 — Package upgrade**

Upgrade the Backstage backend package that contains the patched `FetchUrlReader`. Based on the CVE advisory, this is the core backend reading infrastructure (the exact package name is `@backstage/backend-defaults` or `@backstage/backend-common` depending on the Backstage release line; the CVE fix is confirmed present in the Backstage v1.50.4 release and the individually patched package releases preceding it). Identify and bump the specific package to its patched version.

**Part 2 — Configuration audit**

Review `app-config.yaml` (and `app-config.production.yaml`) for `backend.reading.allow`. For each entry:
1. Confirm the entry is actively required by an in-use feature.
2. Confirm the entry is scoped as narrowly as possible (prefer `https://github.com/my-org` over `https://github.com`).
3. Remove or narrow any entry that cannot be justified.
4. Document the final allowlist with a comment per entry explaining its purpose.

The audit output should be committed as a configuration change alongside the package upgrade.

**Deployment** follows the standard ArgoCD image + config update via mctl-gitops.

## Alternatives

**Option A — Block all redirects in FetchUrlReader via monkey-patch or middleware**: Override the `fetch` implementation used by the reader to never follow redirects (set `redirect: 'error'`). This would prevent the SSRF but would also break any legitimate catalog entity source that uses a redirect (e.g., a GitHub URL that redirects to the raw content CDN). Rejected because it would cause false-positive failures for legitimate workflows and is fragile — it requires maintaining a custom override across Backstage upgrades.

**Option B — Add a Kubernetes NetworkPolicy to block the backend's egress to internal services**: Prevent the backend pod from reaching `mctl-api`, Vault, and Prometheus at the network layer. This would eliminate the SSRF blast radius regardless of application-level bugs. However, the backend legitimately needs to reach `mctl-api` for read operations (see architecture), and Prometheus for the observability plugin. Designing a NetworkPolicy fine-grained enough to allow legitimate traffic while blocking SSRF redirects is complex and not achievable without deep policy work. Rejected as the primary fix; recommended as complementary defence-in-depth in a follow-up.

**Option C — Disable catalog entity imports from external URLs**: Set `catalog.providers` to only use in-cluster sources (Git integration via Dex/mctl-gitops). This would fully eliminate the `FetchUrlReader` attack surface for the catalog. However, the portal currently uses external catalog entity URLs for GitHub-hosted `catalog-info.yaml` files, and disabling this would break developer workflows. Rejected because the upstream fix is available and less disruptive.

## Platform impact

**Migrations**: No database schema changes. The `backend.reading.allow` configuration change is a non-breaking reduction of the allowlist scope; plugins that relied on the removed entries must be re-evaluated (the audit in Part 2 ensures no actively used entry is removed).

**Backward compatibility**: The patched `FetchUrlReader` is backward compatible — it only adds redirect re-validation. Legitimate redirects that stay within the allowlist continue to work. Only redirect chains that escape the allowlist are blocked, which was unintended behaviour.

**Resource impact**: Re-validating redirect URLs is O(1) per redirect hop — no measurable CPU or memory impact. The `labs` tenant is not affected; mctl-portal runs under `admins` only.

**Risks and mitigations**:
- Risk: A currently-used catalog entity source relies on a redirect to a destination outside the explicitly listed allowlist entries, causing catalog import failures after the patch. Mitigation: run catalog refresh in a staging environment with the patched package and audit any new fetch errors in the backend logs before promoting to production.
- Risk: The configuration audit removes an entry that is used by a less-visible feature (e.g., techdocs source or a rarely-used proxy route). Mitigation: search `app-config.yaml` and plugin code for all `readUrl` usages before finalising the allowlist.
- Risk: The package upgrade introduces a transitive dependency conflict with other backend packages. Mitigation: run `yarn why` and `yarn dedupe` after upgrade; run the full backend test suite before building the image.
