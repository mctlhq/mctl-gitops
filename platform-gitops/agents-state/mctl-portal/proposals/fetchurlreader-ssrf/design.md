# Design: fetchurlreader-ssrf

## Current state
`@backstage/backend-defaults` (below version 0.15.0) implements `FetchUrlReader` with a single allow-list check on the initial request URL. When the target server returns an HTTP 3xx redirect, the Node.js `fetch` (or `node-fetch`) client follows the redirect transparently without the `FetchUrlReader` wrapper re-checking the new destination against `backend.reading.allow`. This means an attacker who can influence a whitelisted URL (e.g., via a GitHub raw-content redirect or a documentation CDN they control) can pivot the backend's outbound request to any internal address reachable from the pod network.

In mctl-portal, the following surfaces are exposed:
- **catalog-import**: fetches `catalog-info.yaml` from arbitrary URLs.
- **TechDocs**: fetches MkDocs source files from GitHub or S3.
- **proxy plugin**: forwards API calls to external backends that may themselves redirect.

All three use `FetchUrlReader` internally via `@backstage/backend-defaults`.

## Proposed solution
Bump `@backstage/backend-defaults` to ≥0.15.0. This package version introduces per-hop redirect validation in `FetchUrlReader`: before following any redirect, the reader resolves the `Location` header value and re-evaluates it against `backend.reading.allow`. Disallowed redirect targets cause the request to fail with a descriptive error.

**Note:** `@backstage/backend-defaults` ≥0.15.0 is the same version target as for the scaffolder fix (CVE-2026-24046). Both CVEs can be resolved in a single package bump and a single deployment. The tasks for this proposal reference the same `packages/backend/package.json` edit and deployment pipeline.

| Package | Current (max vulnerable) | Target |
|---|---|---|
| `@backstage/backend-defaults` | < 0.15.0 | ≥ 0.15.0 |

No `app-config.yaml` changes are required. The existing `backend.reading.allow` configuration continues to define the allowlist; the fix makes enforcement stricter by applying it to every redirect hop rather than only the first URL.

**Coordination note:** If CVE-2026-24046 (scaffolder-symlink-traversal-v2) is being addressed concurrently, a single branch can bump both `@backstage/plugin-scaffolder-backend` and `@backstage/backend-defaults` together to avoid two separate deployment cycles.

## Alternatives

### Option A — Disable HTTP redirects in FetchUrlReader (rejected)
Configure `fetch` to not follow redirects at all (e.g., `redirect: 'error'`). This eliminates the SSRF vector but breaks legitimate catalog-import and TechDocs flows that rely on CDN or GitHub redirect chains. Rejected as too disruptive to normal operations.

### Option B — Egress NetworkPolicy blocking RFC-1918 ranges (rejected)
Add a Kubernetes NetworkPolicy that prevents the backend pod from making outbound connections to RFC-1918 addresses. This is a valid defence-in-depth measure but does not fix the vulnerability for internal services that are reachable via the cluster DNS (e.g., `vault.vault.svc.cluster.local` resolves to a non-RFC-1918 address in some cluster configurations). Rejected as the sole fix; acceptable as a complementary control.

### Option C — Application-level URL deny-list middleware (rejected)
Wrap `FetchUrlReader` with a custom middleware that inspects every response for a `Location` header and blocks requests to known internal hostnames. This is fragile (relies on maintaining an explicit deny-list of internal addresses), complex to implement correctly, and duplicates what the upstream fix already provides. Rejected in favour of taking the upstream fix.

## Platform impact

**Migrations:** None. No schema changes, no secret rotations, no changes to `app-config.yaml`.

**Backward compatibility:** All legitimate redirect chains that resolve to URLs matching `backend.reading.allow` continue to work. Only redirect chains that exit the allowlist are newly blocked — these were already unsafe and should not have been followed.

**Resource impact:** The additional URL validation per redirect hop is a string-matching operation with negligible CPU and memory overhead. No impact on the `labs` tenant — this change is scoped to the `admins` tenant deployment of mctl-portal.

**Risks and mitigations:**
- Risk: A TechDocs or catalog-import source relies on an intermediate redirect that goes through a host not in `backend.reading.allow`. Mitigation: review `app-config.yaml` allow-list entries against known TechDocs and catalog sources before deploying; add any missing entries beforehand.
- Risk: The bump introduces a transitive dependency conflict. Mitigation: full TypeScript type-check and test suite in CI will catch this before the image is pushed.
- Risk: False-positive redirect blocks disrupt catalog ingestion. Mitigation: post-deploy, check the Backstage backend logs for any new `warn`-level messages about blocked redirects and adjust the allow-list accordingly before closing the incident.
