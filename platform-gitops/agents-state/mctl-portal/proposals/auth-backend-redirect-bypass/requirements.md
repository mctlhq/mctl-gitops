# Auth Backend OAuth Redirect-URI Bypass Fix

## Context
CVE-2026-32235 (CVSS 5.9 Medium) affects `@backstage/plugin-auth-backend` prior to v0.27.1. The experimental OIDC provider's redirect-URI validation can be bypassed by a crafted `redirect_uri` parameter, allowing an attacker to redirect OAuth authorization codes to a host outside the configured allowlist. The authorization code can then be exchanged for a valid Backstage session token.

mctl-portal uses `plugin-auth-backend` as the sole authentication gateway for Dex JWT SSO. A successful exploit grants an attacker a valid session for any user who can be lured through a crafted login URL, resulting in full platform auth bypass — access to the service catalog, scaffolder, kubernetes viewer, and all downstream APIs including mctl-api and Argo Workflows.

## User stories
- AS a platform security officer I WANT the auth-backend's redirect-URI validation to be enforced without bypass SO THAT authorization codes cannot be stolen and replayed by an attacker.
- AS an end user I WANT my Dex SSO login flow to continue working normally SO THAT I am not disrupted by the security patch.
- AS a platform engineer I WANT the fix deployed in the same PR as the SSRF fix (Proposal 3) SO THAT both CVEs sharing the same package bump are resolved atomically.

## Acceptance criteria (EARS)
- WHEN `@backstage/plugin-auth-backend` is installed, THE SYSTEM SHALL resolve to version 0.27.1 or higher in the lock-file.
- WHEN an OAuth login request arrives with a `redirect_uri` that is not present in the configured `auth.providers.<provider>.callbackUrl` allowlist, THE SYSTEM SHALL reject the request with HTTP 400 and log a WARNING entry identifying the disallowed URI.
- WHEN an OAuth login request arrives with a `redirect_uri` that exactly matches an allowlisted callback URL, THE SYSTEM SHALL proceed with the authorization flow normally.
- WHILE the Backstage backend is running, THE SYSTEM SHALL not issue a session token for any user whose authorization code was delivered to an unallowlisted URI.
- IF `auth.providers.oidc.experimentalCallbackUrlAllowlist` is not explicitly configured, THEN THE SYSTEM SHALL default to rejecting all redirect URIs that do not match the single configured `callbackUrl`.

## Out of scope
- Changes to the Dex configuration or the upstream identity provider.
- Hardening of non-OIDC auth providers (GitHub OAuth, guest provider).
- Session invalidation for tokens already issued prior to the patch (not feasible without a full session purge; tracked separately).
- The SSRF vector in the CIMD metadata fetch (addressed in the `auth-backend-metadata-ssrf` proposal, shipped in the same PR).
