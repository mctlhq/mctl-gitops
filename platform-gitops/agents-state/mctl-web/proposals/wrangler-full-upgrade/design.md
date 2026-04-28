# Design: wrangler-full-upgrade

## Current state
As documented in `context/architecture.md`, the Cloudflare Worker is deployed via Wrangler through a GitHub Actions workflow (`deploy.yml`) that lives in the mctl-web repository—an explicit exception to the centralised mctl-gitops build system. Wrangler appears in two places:

1. `deploy.yml` — the Actions step that installs and runs `wrangler deploy`.
2. `cloudflare-worker/package.json` — the local dev/test dependency used for `wrangler dev`.

The existing `wrangler-cve-0933` proposal brought the floor to v4.59.1. v4.86.0 adds resource-leak fixes in worker teardown (stability for the `/api/*` worker), stack traces in `wrangler tail` (observability), `wrangler dev --tunnel` for Quick Tunnel sharing, and AI Search namespace management commands. There is no breaking change declared across the 27-release span.

## Proposed solution
Pin wrangler to exactly `4.86.0` in both `deploy.yml` and `cloudflare-worker/package.json`. Using an exact pin (rather than a semver range) prevents silent upgrades that could introduce regressions between CI runs.

**Changes required:**

1. `deploy.yml`: update the `wrangler` install step (e.g., `npm install -g wrangler@4.86.0` or the `cloudflare/wrangler-action` version tag if that action is used).
2. `cloudflare-worker/package.json`: bump the `"wrangler"` devDependency entry from `">=4.59.1"` (or whatever the current value is) to `"4.86.0"`.
3. Re-run `npm install` inside `cloudflare-worker/` and commit the updated `package-lock.json`.
4. Smoke-test with `wrangler dev` locally and `wrangler tail` against the staging Worker.

No Nuxt build changes, no Kubernetes manifest changes, and no secrets rotation are required.

## Alternatives

### Option A: Upgrade to latest at CI time (no pin)
Use `wrangler@latest` in `deploy.yml`. This keeps the tool current automatically but allows silent breaking changes between pipeline runs. Rejected because reproducibility of CI is a platform requirement.

### Option B: Stay at v4.59.1 indefinitely
The CVE floor is met, so no security pressure. However, resource leaks in worker teardown remain, and 27 releases of accumulated improvements are foregone. Rejected because the stability and observability benefits of v4.86.0 are directly relevant to the `/api/*` Worker.

### Option C: Upgrade to an intermediate version (e.g., v4.70.0)
Partially captures improvements but still leaves a gap to current. Adds a future upgrade task for no benefit. Rejected in favour of going directly to v4.86.0.

## Platform impact

### Migrations
No data migrations. `package-lock.json` inside `cloudflare-worker/` will be regenerated.

### Backward compatibility
Wrangler is a CLI deploy tool; it does not affect the Worker's runtime behaviour or public API surface. The Worker endpoints (`/api/github/login`, `/api/github/callback`, `/api/submit`, `/api/contact`) are unchanged.

### Resource impact
Wrangler runs exclusively in GitHub Actions CI. There is zero memory or CPU impact on the `admins` Kubernetes tenant and zero impact on the `labs` tenant.

### Risks and mitigations
- **Risk:** A silent breaking change between v4.59.1 and v4.86.0 disrupts the deploy pipeline.
  **Mitigation:** The changelog shows no declared breaking changes. A staging deploy smoke-test (task 3) will catch regressions before production promotion.
- **Risk:** `wrangler dev --tunnel` or new commands change CLI flag behaviour relied on in `deploy.yml`.
  **Mitigation:** The deploy step only calls `wrangler deploy`; new sub-commands do not affect it.
