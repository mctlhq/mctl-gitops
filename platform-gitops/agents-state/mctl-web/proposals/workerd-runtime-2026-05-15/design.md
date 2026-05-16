# Design: workerd-runtime-2026-05-15

## Current state
The Cloudflare Worker in `cloudflare-worker/` is deployed via wrangler through `deploy.yml`. The existing proposal `workerd-v8-148-upgrade` proposes pinning wrangler to ≥ 4.88.0, which bundles workerd v1.20260506.1 (V8 14.8). Since that proposal was written, Cloudflare released:
- workerd v1.20260511.1 (2026-05-11)
- workerd v1.20260515.1 (2026-05-15) — latest as of today

The `workers-sdk` package `miniflare@4.20260515.0` (released 2026-05-15) confirms the new runtime is publicly available and bundles workerd 1.20260515.1. The dated release format used by Cloudflare means each release represents an incremental V8 and infrastructure snapshot; the changelog is expressed as a commit diff rather than human-readable notes.

mctl-web does not currently have an explicit `workerd` version pin in `cloudflare-worker/package.json`; the effective version is determined by the installed wrangler release.

## Proposed solution
Pin `wrangler` in `cloudflare-worker/package.json` to the version that ships with workerd v1.20260515.1. Based on the miniflare release pattern, this corresponds to a wrangler release in the `4.20260515.x` range. The implementation should:

1. Identify the wrangler version that bundles workerd v1.20260515.1 (via `npm info wrangler` or the workers-sdk changelog).
2. Update `"wrangler"` in `cloudflare-worker/package.json` to that version or `>=<that-version>`.
3. Optionally add `"workerd": "1.20260515.1"` as an explicit devDependency for documentation purposes and local drift prevention.
4. Run `wrangler dev` locally to confirm the runtime starts without error.
5. Verify the existing rate-limit behaviour (5/5 min `/api/submit`, 3/5 min `/api/contact`, 10/min `/api/github/login`) is unaffected.

## Alternatives

**Option A — Do not pin workerd; rely on wrangler to select its bundled version.**  
Current state. Leaves the exact runtime version implicit and subject to change on `npm install`. Rejected — explicit pin is the documented pattern for environment parity.

**Option B — Wait for `workerd-v8-148-upgrade` to be implemented first.**  
That proposal targets v1.20260506.1. Implementing it and then immediately following with this proposal for v1.20260515.1 is wasteful. The current proposal can supersede it by targeting the newer version directly.

**Option C — Pin to a specific V8 version flag rather than the dated release.**  
workerd does not expose a stable V8-version-based package alias; dated releases are the canonical versioning scheme. Rejected — not supported by the package registry.

## Platform impact
- **Migrations:** none — the workerd runtime is backward-compatible within the dated-release series; no Worker source code changes are required.
- **Backward compatibility:** full. The Worker API surface (fetch, caches, rate-limit KV) is unchanged.
- **Resource impact:** zero — the Worker runs entirely on Cloudflare infrastructure, not on the Kubernetes cluster. No memory or CPU impact on `admins` or `labs` tenants.
- **Risks and mitigations:** very low. Cloudflare's dated releases are production-hardened before tagging. Risk of a regression is mitigated by running the smoke test (`/api/github/login`, `/api/submit`, `/api/contact`) against the deployed Worker via the CI pipeline before promoting.
