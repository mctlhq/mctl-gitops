# Backstage FetchUrlReader SSRF via HTTP redirect — CVE-2026-24048

## Context
CVE-2026-24048 is a Server-Side Request Forgery (SSRF) vulnerability in Backstage's `FetchUrlReader`. The reader is used by the catalog-import plugin, TechDocs, and the proxy plugin — all active in mctl-portal — to fetch content from external URLs. The vulnerability arises because `FetchUrlReader` follows HTTP redirects without re-validating each redirect destination against the `backend.reading.allow` allowlist. An attacker who controls a whitelisted hostname (e.g., a public GitHub repository or a shared documentation host) can serve an HTTP 3xx redirect pointing to an internal address (such as the Vault sidecar, the Kubernetes API, or mctl-api) and cause the Backstage backend to make an authenticated request to that internal target on their behalf.

mctl-portal integrates with Vault (for secrets), the Kubernetes API (for the kubernetes plugin), and mctl-api (for tenant/status reads), all of which are reachable from within the pod network. The fix is included in Backstage v1.50.4 and `@backstage/backend-defaults` ≥0.15.0, which also covers the scaffolder fix (CVE-2026-24046).

## User stories
- AS a platform engineer I WANT every URL fetched by the Backstage backend to be validated against the allow-list at each redirect hop SO THAT a compromised or malicious external host cannot redirect backend requests to internal infrastructure.
- AS a security officer I WANT CVE-2026-24048 remediated promptly SO THAT internal services (Vault, Kubernetes API, mctl-api) cannot be reached via SSRF through mctl-portal.
- AS an end user I WANT catalog-import, TechDocs, and the proxy plugin to continue working normally after the fix SO THAT my daily workflows are unaffected.

## Acceptance criteria (EARS)
- WHEN `FetchUrlReader` receives an HTTP redirect response THE SYSTEM SHALL validate the redirect destination URL against `backend.reading.allow` before following it.
- IF the redirect destination does not match any entry in the `backend.reading.allow` allowlist THEN THE SYSTEM SHALL abort the request and return an error rather than following the redirect.
- WHILE the Backstage backend is serving catalog-import, TechDocs, or proxy plugin requests THE SYSTEM SHALL enforce allow-list validation on every HTTP hop, not only the initial request URL.
- WHEN a request is blocked because a redirect resolves to a disallowed URL THE SYSTEM SHALL log the blocked destination at warn level without exposing internal network topology in user-facing error messages.
- IF `@backstage/backend-defaults` is at version ≥0.15.0 THEN THE SYSTEM SHALL apply the per-hop redirect validation introduced by that release.
- WHEN the patched package is deployed THE SYSTEM SHALL continue to resolve all catalog-info.yaml imports and TechDocs sources that use allowed external hosts without regression.

## Out of scope
- Restricting which external hosts are in `backend.reading.allow` (an operational configuration decision outside this proposal).
- SSRF protection for the proxy plugin's upstream targets (managed separately via the proxy allowlist configuration).
- Network-level egress controls (Kubernetes NetworkPolicy or service mesh egress rules) — these are complementary but not part of this fix.
- Any Backstage plugin upgrade beyond `@backstage/backend-defaults`.
