# Patch Backstage SSRF via FetchUrlReader Redirect (CVE-2026-24048)

## Context
CVE-2026-24048 discloses a Server-Side Request Forgery (SSRF) vulnerability in Backstage's `FetchUrlReader`. The reader follows HTTP redirects when fetching URLs that match the `backend.reading.allow` allowlist. Because allowlist validation is only applied to the initial URL, an attacker can supply a permitted URL that redirects — through one or more hops — to an internal address (e.g., `mctl-api`, Vault, Prometheus). The backend then fetches and may return the internal resource.

mctl-portal relies on `FetchUrlReader` in two critical plugins: the catalog backend (importing `catalog-info.yaml` files from external URLs) and the proxy plugin (routing API calls to external services). The internal services reachable from the backend pod — `mctl-api`, Vault, and Prometheus — all serve sensitive data or privileged operations. An SSRF exploit in this context would allow an attacker who can supply a crafted catalog entity URL or proxy target to exfiltrate secrets, read internal API state, or reach Vault without authentication. The fix requires upgrading the affected Backstage backend package and auditing the current `backend.reading.allow` configuration to confirm it follows the principle of least privilege.

## User stories
- AS a platform engineer I WANT `FetchUrlReader` to validate redirect destinations against the `backend.reading.allow` allowlist SO THAT an attacker cannot bypass the allowlist by chaining HTTP redirects.
- AS a security officer I WANT the `backend.reading.allow` configuration audited and tightened SO THAT only the minimum required external origins are permitted.
- AS a developer I WANT catalog entity imports and proxy plugin functionality to continue working after the patch SO THAT developer workflows are not disrupted.

## Acceptance criteria (EARS)
- WHEN `FetchUrlReader` follows an HTTP redirect THE SYSTEM SHALL re-evaluate the redirect target URL against the `backend.reading.allow` allowlist before fetching it.
- IF a redirect target URL does not match the `backend.reading.allow` allowlist THE SYSTEM SHALL abort the fetch and return an error; it SHALL NOT follow the redirect.
- WHILE the backend is processing catalog entity imports THE SYSTEM SHALL not issue any HTTP request to a destination not covered by `backend.reading.allow`, including redirect intermediaries.
- WHEN a catalog entity URL resolves through a redirect chain to an internal IP range (RFC 1918) or the cluster-internal DNS zone THE SYSTEM SHALL reject the request at the first redirect that leaves the allowlist.
- WHEN the patched package is deployed THE SYSTEM SHALL successfully fetch catalog entities from all currently allowed origins without requiring changes to template or entity YAML files.
- IF `backend.reading.allow` contains an entry that covers a broader range than strictly necessary THE SYSTEM SHALL have a documented justification or the entry SHALL be removed as part of this proposal's audit task.

## Out of scope
- Changes to the proxy plugin's own allowlist or route configuration (the proxy plugin has its own `backend.proxies` config; its SSRF surface is separate).
- Network-level egress controls or Kubernetes NetworkPolicy changes (these are desirable defence-in-depth measures but are a separate infrastructure concern).
- Patching CVE-2026-32235 or CVE-2026-32236 (auth-backend OAuth redirect issues, separate CVEs not in scope).
- Changes to how catalog entities are authored or stored in source control.
