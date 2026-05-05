# Design: auth-backend-redirect-bypass

## Current state
`mctl-portal` uses `@backstage/plugin-auth-backend` at a version prior to 0.27.1 to expose an OIDC provider that delegates to Dex (`ops.mctl.me/api/dex`). During the OAuth authorization flow the backend validates the inbound `redirect_uri` against an allowlist derived from the configured `callbackUrl`. In versions before 0.27.1 this validation in the experimental OIDC provider can be bypassed by a specially crafted URI (e.g., using URL encoding or parameter pollution), causing the backend to forward the authorization code to the attacker-controlled host before validating the response.

Session tokens are stored in Postgres. The backend is deployed in the `admins` tenant via ArgoCD. See `context/architecture.md` — Auth section.

## Proposed solution
Bump `@backstage/plugin-auth-backend` to `^0.27.1` in `packages/backend/package.json`. This is the same package version bump required by Proposal 3 (`auth-backend-metadata-ssrf`); both proposals are shipped in a single PR to keep lock-file churn minimal.

The patch in v0.27.1 normalizes the inbound `redirect_uri` before comparison (decoding percent-encoding, stripping fragments, canonicalizing the host) so that crafted variants cannot bypass the string-equality check.

No Backstage `app-config.yaml` changes are required for the redirect bypass fix specifically. The OIDC provider's existing `callbackUrl` configuration remains the source of truth for the allowlist.

Steps:
1. Update `packages/backend/package.json`: `"@backstage/plugin-auth-backend": "^0.27.1"`.
2. Run `yarn install && yarn dedupe` (shared with Proposal 3 — single combined step in the PR).
3. Validate the full Dex SSO login flow in the staging environment.
4. Deploy via ArgoCD to the `admins` tenant.

## Alternatives

**Option A — Implement a custom request-validation middleware in front of the auth-backend.**
This could normalize and validate `redirect_uri` before it reaches the plugin. However, it duplicates logic that the upstream patch already provides, introduces custom code to maintain, and risks subtle incompatibilities with future plugin versions. Dropped.

**Option B — Disable the experimental OIDC provider and switch to a stable provider.**
The stable provider does not support Dex JWT without additional configuration. Switching mid-flight is a significant auth change that needs its own design review and testing cycle. Too much scope for an urgent CVE patch. Dropped.

**Option C — Rate-limit or block login endpoints at the ingress layer.**
Reduces exploit opportunity but does not close the vulnerability. An attacker can still craft a request within the rate limit. Not a fix. Dropped.

## Platform impact

**Migrations:** None. The allowlist configuration format is unchanged.

**Backward compatibility:** The canonical login flow is unaffected. Requests with a legitimate `redirect_uri` matching `callbackUrl` pass through exactly as before. Only crafted bypass URIs are newly rejected.

**Resource impact:** Negligible CPU/memory delta from the version bump. The `labs` tenant does not run mctl-portal; no labs impact.

**Risks and mitigations:**
- Risk: the normalized URI comparison is overly strict and rejects a legitimate redirect URI used by a Backstage plugin (e.g., the scaffolder or a proxy plugin). Mitigation: run a full Playwright e2e login flow in staging before promoting; test with all configured OAuth clients.
- Risk: shipping both auth-backend proposals in one PR increases the blast radius of a regression. Mitigation: tasks are sequenced so that each fix has an independent acceptance test; if one fails, the PR is blocked and rolled back atomically.
