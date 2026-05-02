# Design: wrangler-4-87-upgrade

## Current state
The `cloudflare-worker/` directory contains a self-contained `package.json` that pins a
specific wrangler version used by both local development (`wrangler dev`) and the GitHub Actions
`deploy.yml` workflow. The architecture doc notes that this is the only mctl service that ships
its own CI pipeline rather than delegating to mctl-gitops. The exact wrangler version currently
in use was not confirmed from `package.json` directly, but the architecture lists the
workers-sdk/wrangler as a tracked dependency and recent inbox entries reference 4.87.0 as the
latest release.

## Proposed solution
Update the `wrangler` version specifier in `cloudflare-worker/package.json` to `4.87.0` (exact
pin, consistent with the security-hardened pinning strategy adopted in previous wrangler
proposals). Run `npm install` inside `cloudflare-worker/` and commit both `package.json` and
`package-lock.json`.

**Why exact pin rather than `^` range:**
The wrangler proposals that preceded this one (`wrangler-ci-injection-audit`,
`wrangler-upgrade-security`) established exact version pinning as the project's policy for the
Worker deploy tool. A supply-chain compromise in any wrangler patch release would have direct
write access to production Cloudflare Pages via the CI runner. Exact pins ensure the version
deployed in CI is the version audited.

**Module fallback V2 note:**
The `new_module_registry` compatibility flag that activates V2 module-fallback is NOT enabled
in this proposal. The flag requires separate testing and an explicit decision. Upgrading wrangler
to 4.87.0 does not implicitly activate the flag — it merely makes the V2 code path available
when the flag is set in a future change.

## Alternatives

### A — Keep wrangler at the current version until a security advisory forces an upgrade
Rejected. Accumulating version debt in the deploy toolchain increases the diff at the next forced
upgrade and may hide functional regressions that are easier to isolate when upgrading
incrementally.

### B — Use `latest` / floating `^4.x` range
Rejected. Established project policy (from prior wrangler proposals) is exact pins for the
Worker deploy tool to support auditability and reproducibility in CI.

### C — Migrate deploy pipeline to mctl-gitops (centralise wrangler management)
Out of scope for this proposal. The architecture explicitly notes the exception; changing it is
an architectural decision requiring an ADR, not a dependency bump.

## Platform impact

**Migrations:** None. wrangler 4.87.0 is backward-compatible with the existing `wrangler.toml`
and Worker source; no code changes are required.

**Backward compatibility:** Full. The Worker's `/api/*` routes, rate-limit configuration, and
secret references remain unchanged.

**Resource impact:** Zero runtime or Kubernetes impact. wrangler is a CI-only tool; the
deployed Worker binary is determined by the Worker source code and workerd runtime, not the
wrangler CLI version.

**Risks and mitigations:**
- *Risk:* wrangler 4.87.0 changes the output format of `wrangler deploy` in a way that breaks
  any CI step that parses the deploy log. *Mitigation:* Review the CI log output in a test
  deployment before merging to main; the `deploy.yml` workflow should be verified end-to-end.
- *Risk:* Router-worker refactor introduces a regression in routing for one of the four
  `/api/*` endpoints. *Mitigation:* Smoke-test all four endpoints after the first deployment
  to a preview environment before promoting to production.
- *Risk:* Version mismatch between `wrangler dev` locally and CI if developers have a global
  wrangler install. *Mitigation:* Document in the repo that `cloudflare-worker/` must be run
  with the local `npx wrangler` rather than a global install.
