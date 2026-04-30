# Design: wrangler-upgrade-security

## Current state
`deploy.yml` installs wrangler (version unknown from context, but assumed < 4.59.1 given the advisory). `wrangler pages deploy --commit-hash ${{ github.sha }}` is the likely invocation. CVE-2026-0933 affects all wrangler >= 2.0.15 < 4.59.1 in this code path. Workerd is bundled inside the wrangler npm package.

## Proposed solution
Pin wrangler to `4.87.0` in the location where it is installed in CI:
- If `deploy.yml` runs `npm install -g wrangler` or `npx wrangler@latest`, replace with `npx wrangler@4.87.0` or add `"wrangler": "4.87.0"` to `devDependencies` in `package.json` and run `npm ci` before deploying.
- Commit the change; wrangler@4.87.0 bundles workerd v1.20260430.1 which contains the UaF fix.
- No Wrangler configuration (`wrangler.toml`) changes are expected; v4.87.0 maintains backward compatibility with v4.x configs.

## Alternatives
1. **Stay on current version + apply `--commit-hash` sanitisation manually** — fragile; the CVE is in wrangler's internals, not in the caller's escaping. Rejected.
2. **Switch to Cloudflare's direct API for Pages deployments** — large scope change, removes the Worker-side deploy path. Rejected per ADR 0001 (do not remove/replace the Cloudflare Worker mechanism without strong rationale).
3. **Pin to 4.59.1 (minimum fix)** — sufficient for CVE but misses the workerd UaF fix and other stability patches in 4.87.0. Rejected in favour of latest stable.

## Platform impact
- **Migrations:** None; wrangler@4.87.0 is backward-compatible with v4.x configs and CLI flags.
- **Backward compatibility:** Full; Pages project name, `--compatibility-date`, and other flags remain supported.
- **Resource impact:** No change to runtime memory or CPU. Worker bundle size is unchanged. No impact on `labs` tenant.
- **Risks and mitigations:** Low. Risk of CLI breaking change is mitigated by reviewing the wrangler 4.59-4.87 changelogs for any deprecation of flags used in `deploy.yml` before merging.
