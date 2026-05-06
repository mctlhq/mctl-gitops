# Design: workerd-v8-148-upgrade

## Current state
The Cloudflare Worker located in `cloudflare-worker/` is deployed via wrangler
through the `deploy.yml` GitHub Actions workflow (see `context/architecture.md`
— this service is the only one with its own deploy pipeline, as an exception to
mctl-gitops). wrangler bundles a specific version of workerd as its embedded
runtime. As of 2026-04-25 (last recorded version update) wrangler 4.86.0 is
in use, which bundles workerd v1.20260430.1 running V8 14.7. Local development
via `wrangler dev` uses the same embedded runtime, but if the version is not
pinned explicitly the installed wrangler version may vary between developers
and CI runners, creating environment drift.

## Proposed solution
Pin wrangler to `^4.88.0` (or exact `4.88.0`) in the `devDependencies` section
of `cloudflare-worker/package.json`. wrangler 4.88.0 bundles workerd
v1.20260506.1, which ships V8 14.8.

This single-file change is sufficient to:
1. Deliver V8 14.8 JIT and memory layout improvements to all `/api/*` handler
   executions on Cloudflare infrastructure.
2. Align `wrangler dev` (local) with the production runtime, removing
   environment drift.
3. Keep CI deterministic: `npm ci` in the deploy workflow will install exactly
   this version.

No other source files need to change. The Worker code itself, its secrets, rate
limit configuration, and Cloudflare routing rules are unaffected. There is no
schema migration, no data-plane change, and no Kubernetes manifest change.

The deploy process remains: push to the deploy branch → `deploy.yml` triggers
→ `npm ci` in `cloudflare-worker/` → `wrangler deploy` → Cloudflare propagates
globally within seconds.

## Alternatives

**Option A — Upgrade wrangler without pinning (rely on `^` range).**
Already using a caret range means a later `npm ci` could silently pull a
different patch version. Rejected: determinism is required for reproducible
builds and local/production parity.

**Option B — Use `wrangler dev --local` with a manually downloaded workerd
binary.**
Decouples the workerd version from wrangler but introduces a separate binary
management process. Rejected: higher operational complexity for no meaningful
gain; the embedded workerd shipped with wrangler is the officially supported
pairing.

**Option C — Wait for the existing `workerd-runtime-upgrade` proposal (targeting
wrangler 4.86.0 / workerd v1.20260430.1) to land, then follow up.**
Delays the V8 14.8 benefit by at least one release cycle and risks the older
proposal blocking on review. Rejected: the effort to target 4.88.0 directly is
identical to targeting 4.86.0 (same single-line change), so there is no reason
to land an intermediate version.

## Platform impact

### Migrations
None. No data schema changes, no API contract changes, no Kubernetes manifest
changes.

### Backward compatibility
The Worker API surface (`/api/github/login`, `/api/github/callback`,
`/api/submit`, `/api/contact`) is unchanged. Response shapes, status codes, and
rate-limit headers remain identical. V8 14.8 is backward-compatible with ES2022
Worker code.

### Resource impact (especially for `labs`)
The Worker runs on Cloudflare's global edge infrastructure, not on the
Kubernetes cluster. There is zero memory or CPU impact on the `admins` or
`labs` tenants. The `labs` tenant memory constraint is not affected by this
change.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| V8 14.8 JIT introduces a behavioural regression in Worker JS | Low — V8 14.8 is production-hardened by Cloudflare before release | Smoke tests on all `/api/*` endpoints immediately post-deploy; rollback path is to revert the version pin |
| wrangler 4.88.0 has a wrangler-level bug unrelated to workerd | Low | Pin to exact version `4.88.0` rather than `^4.88.0` to avoid silent upgrades; monitor Cloudflare workers-sdk release notes |
| Local developer environments cached at an older wrangler version | Low | `npm ci` enforces the lockfile; developers running `npm install` will be prompted to update |
