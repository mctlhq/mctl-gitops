# Auth Backend CIMD Metadata SSRF Fix

## Context
CVE-2026-32236 (Low severity) affects `@backstage/plugin-auth-backend` prior to v0.27.1. When `auth.experimentalClientIdMetadataDocuments.enabled` is set to `true`, the plugin fetches a metadata document from a URL derived from the client ID. If that URL redirects, the plugin follows the redirect without re-validating the destination against the configured allowlist, creating a Server-Side Request Forgery (SSRF) vector. An attacker who can influence the metadata document URL can direct the backend to make authenticated HTTP requests to internal network targets (e.g., the Kubernetes API server, Vault, or mctl-api).

The package-level fix is bundled with the same v0.27.1 bump that addresses CVE-2026-32235 (the redirect-URI bypass, Proposal 2). This proposal exists as a separate spec to ensure the SSRF vector is explicitly acceptance-tested and that the required `app-config.yaml` change (disabling the feature flag if not already done) is tracked and verified independently.

## User stories
- AS a platform security officer I WANT the CIMD metadata fetch to either not follow redirects or to re-validate redirect targets against the allowlist SO THAT the Backstage backend cannot be used as an SSRF proxy against internal services.
- AS a platform engineer I WANT the config flag `auth.experimentalClientIdMetadataDocuments.enabled` explicitly set to `false` in `app-config.yaml` SO THAT the SSRF vector is disabled at the application level even as a defence-in-depth measure independent of the package fix.
- AS a platform engineer I WANT this fix shipped in the same PR as the redirect-URI bypass fix (Proposal 2) SO THAT both CVEs are resolved atomically with a single `yarn.lock` update.

## Acceptance criteria (EARS)
- WHEN `@backstage/plugin-auth-backend` is installed, THE SYSTEM SHALL resolve to version 0.27.1 or higher in the lock-file.
- WHEN `auth.experimentalClientIdMetadataDocuments.enabled` is evaluated at startup, THE SYSTEM SHALL read `false` from the active `app-config.yaml` and log an INFO entry confirming the feature is disabled.
- WHILE `auth.experimentalClientIdMetadataDocuments.enabled` is `false`, THE SYSTEM SHALL not issue any outbound HTTP request to a client-ID-derived metadata URL during an authentication flow.
- IF `auth.experimentalClientIdMetadataDocuments.enabled` is `true` and the metadata URL issues a redirect, THEN THE SYSTEM SHALL re-validate the redirect target against the configured auth allowlist before following it, and SHALL abort the request with an error log if the target is not allowlisted.
- IF a CI configuration drift check detects that `auth.experimentalClientIdMetadataDocuments.enabled` is absent from `app-config.yaml` or set to `true`, THEN THE SYSTEM SHALL fail the check and block the deployment.

## Out of scope
- The OAuth redirect-URI bypass (CVE-2026-32235) — addressed in `auth-backend-redirect-bypass`.
- SSRF hardening of the `proxy` plugin or other outbound HTTP clients in Backstage.
- Network-layer egress restrictions (a separate infrastructure concern).
- Enabling or extending the CIMD feature in the future (requires a new proposal and security review).
